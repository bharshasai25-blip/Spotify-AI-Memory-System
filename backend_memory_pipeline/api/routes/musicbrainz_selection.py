from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Depends, HTTPException, status
from backend_memory_pipeline.api.dependencies import CurrentSubject, get_memory_write_orchestrator, get_musicbrainz_catalog_service, get_user_entity_action_repository
from backend_memory_pipeline.api.musicbrainz_selection_tokens import SelectionTokenError, verify_selection_token
from backend_memory_pipeline.api.schemas import MusicBrainzSelectionConfirmationRequestV1, MusicBrainzSelectionConfirmationResponseV1
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_catalog_service import MusicBrainzCatalogService
from backend_memory_pipeline.orchestration.orchestration import MemoryWriteOrchestrator, OrchestrationError
from backend_memory_pipeline.persistence.postgres.user_entity_action_repository import PostgreSQLUserEntityActionRepository

router=APIRouter(prefix="/v1/musicbrainz", tags=["musicbrainz-selection"])

@router.post("/selection/confirm", response_model=MusicBrainzSelectionConfirmationResponseV1)
def confirm_musicbrainz_selection(request:MusicBrainzSelectionConfirmationRequestV1,current_subject:CurrentSubject,service:MusicBrainzCatalogService=Depends(get_musicbrainz_catalog_service),orchestrator:MemoryWriteOrchestrator=Depends(get_memory_write_orchestrator),actions:PostgreSQLUserEntityActionRepository=Depends(get_user_entity_action_repository))->MusicBrainzSelectionConfirmationResponseV1:
    try:
        claims=verify_selection_token(request.selection_token)
    except (SelectionTokenError,RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=str(exc)) from exc
    if claims.get("subject_id")!=current_subject.subject_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="This selection does not belong to the authenticated user.")
    groups=claims.get("candidate_groups")
    if isinstance(groups,list) and groups:
        offered={(str(group.get("entity_type") or "track"),str(mbid)) for group in groups if isinstance(group,dict) for mbid in group.get("candidate_mbids",[]) if isinstance(mbid,str)}
    else:
        default_type=str(claims.get("entity_type") or "track")
        offered={(default_type,str(mbid)) for mbid in claims.get("candidate_mbids",[]) if isinstance(mbid,str)}
    selected=[]
    if request.selected_entities:
        selected=[(item["entity_type"],item["mbid"]) for item in request.selected_entities]
    else:
        default_type=str(claims.get("entity_type") or "track")
        selected=[(default_type,mbid) for mbid in request.selected_mbids]
    if not offered or any(pair not in offered for pair in selected):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="One or more selected entities were not in the offered candidate list.")
    if len(selected)>30:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Too many selected entities.")
    group_context={}
    candidate_details={}
    if isinstance(groups,list):
        for group in groups:
            if isinstance(group,dict):
                kind=str(group.get("entity_type") or "track")
                for candidate_mbid in group.get("candidate_mbids",[]):
                    if isinstance(candidate_mbid,str): group_context[(kind,candidate_mbid)]=group.get("context_artist")
                for candidate in group.get("candidates",[]):
                    if isinstance(candidate,dict) and isinstance(candidate.get("mbid"),str): candidate_details[(kind,candidate["mbid"])]=candidate
    try:
        effective_at=datetime.fromisoformat(str(claims.get("created_at"))) if claims.get("created_at") else datetime.now(timezone.utc)
        if effective_at.tzinfo is None or effective_at.utcoffset() is None: effective_at=effective_at.replace(tzinfo=timezone.utc)
    except (TypeError,ValueError):
        effective_at=datetime.now(timezone.utc)
    results=[]
    for entity_type,mbid in selected:
        if entity_type not in {"track","artist","album"}:
            raise HTTPException(status_code=400,detail="Unsupported MusicBrainz entity type.")
        try:
            canonical_id=f"musicbrainz:{entity_type}:{mbid}"
            entity=service.repository.get(canonical_id) if hasattr(service.repository,"get") else None
            if entity is None:
                entity=service.catalog_entity_by_mbid(entity_type=entity_type,mbid=mbid)
            context_artist=group_context.get((entity_type,mbid))
            context_entities={"artists":[{"entity_type":"artist","name":context_artist}]} if context_artist and entity_type=="track" else {}
            stable_key=f"spotify-memory-selection:{claims.get('selection_id')}:{entity_type}:{mbid}"
            original_preference=str(claims.get("preference") or "Music preference confirmed by user.")
            if len(selected)>1:
                detail=candidate_details.get((entity_type,mbid),{})
                release_names=detail.get("release_names") if isinstance(detail,dict) else []
                artist_names=detail.get("artist_names") if isinstance(detail,dict) else []
                disambiguation=detail.get("disambiguation") if isinstance(detail,dict) else ""
                preference_text=f"I like {entity.canonical_name}"
                if isinstance(artist_names,list) and artist_names and entity_type=="track": preference_text+=f" by {', '.join(str(name) for name in artist_names)}"
                if isinstance(release_names,list) and release_names: preference_text+=f" from {release_names[0]}"
                elif isinstance(disambiguation,str) and disambiguation.strip(): preference_text+=f" ({disambiguation.strip()})"
            else:
                preference_text=original_preference
            write_result=orchestrator.add_explicit_preference(subject_id=current_subject.subject_id,subject_scope=current_subject.subject_id,
                                                              session_id=str(claims.get("session_id") or ""),preference=preference_text,
                                                              surface=str(claims.get("surface") or "web"),locale=str(claims.get("locale") or "en-US"),
                                                              effective_at=effective_at,correlation_id=str(uuid5(NAMESPACE_URL,stable_key+":correlation")),
                                                              idempotency_key=stable_key,
                                                              entity={"entity_type":entity_type,"name":entity.canonical_name,"canonical_id":entity.entity_id},
                                                              context_entities=context_entities,metadata={"source":"musicbrainz_selection_confirmation","selection_id":claims.get("selection_id"),"selected_mbid":mbid},
                                                              event_id=str(uuid5(NAMESPACE_URL,stable_key+":event")),source_event_id=str(uuid5(NAMESPACE_URL,stable_key+":source")))
            print("CONFIRM VALIDATION:", write_result.validation.model_dump(), flush=True)
            print("CONFIRM EXTRACTION:", write_result.extraction.model_dump(), flush=True)
            print("CONFIRM ENTITY RESOLUTION:", [item.model_dump() for item in (write_result.entity_resolution or [])], flush=True)
            print("CONFIRM POLICY:", [item.model_dump() for item in (write_result.policy_decisions or [])], flush=True)
        except (OrchestrationError,ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Could not confirm the selected MusicBrainz result.") from exc
        memory_ids=[]
        for lifecycle in write_result.lifecycle_results:
            memory_id=lifecycle.created_memory_id or lifecycle.memory_id
            if memory_id and memory_id not in memory_ids: memory_ids.append(memory_id)
        allowed_decision=any(item.decision.value=="allow" for item in write_result.policy_decisions)
        created=bool(memory_ids) and allowed_decision
        if created:
            actions.set_action(current_subject.subject_id,entity.entity_id,"preference",True,{"source":"chat_selection","selection_id":claims.get("selection_id"),"mbid":mbid,"memory_ids":memory_ids})
        policy_details=[{"decision":item.decision.value,"consent_decision":item.consent_decision.value,"denied_reasons":list(item.denied_reasons),"review_reasons":list(item.review_reasons),"policy_flags":list(item.policy_flags)} for item in write_result.policy_decisions]
        results.append({"mbid":mbid,"entity_type":entity_type,"entity_id":entity.entity_id,"entity_name":entity.canonical_name,"memory_created":created,"memory_ids":memory_ids,"policy_decisions":[item.decision.value for item in write_result.policy_decisions],"policy_details":policy_details})
    memory_created=any(item["memory_created"] for item in results)
    if memory_created:
        message="The selected entity preferences were confirmed and the memory pipeline completed."
    else:
        reasons=[]
        for result in results:
            for detail in result.get("policy_details",[]):
                reasons.extend(detail.get("denied_reasons",[]))
                reasons.extend(detail.get("review_reasons",[]))
        reasons=list(dict.fromkeys(reason for reason in reasons if isinstance(reason,str) and reason.strip()))
        if any("consent state is unknown" in reason.casefold() for reason in reasons):
            message="The recording was selected, but memory consent is currently unknown. Open Memory Settings and opt in, then select Confirm again."
        elif any("consent" in reason.casefold() or "paused" in reason.casefold() or "opted out" in reason.casefold() for reason in reasons):
            message="The recording was selected, but memory was not saved because consent does not currently allow memory creation. Check Memory Settings and try again if you choose to opt in."
        elif reasons:
            message="The recording was selected, but policy prevented memory creation: " + " ".join(reasons)
        elif not any(result.get("policy_decisions") for result in results):
            message="The recording was selected, but the memory extractor produced no memory candidate. Check the backend logs for validation or extraction details."
        else:
            message="The recording was selected, but the memory pipeline did not create a memory. Check the returned policy details and backend logs."
    return MusicBrainzSelectionConfirmationResponseV1(status="accepted" if memory_created else "processed",memory_created=memory_created,results=results,message=message,correlation_id=str(uuid4()))