from datetime import datetime,timezone
from typing import Any
from mcp.server.auth.middleware.auth_context import get_access_token
from backend_memory_pipeline.ingestion.ingestion import IngestionService,ConsentState
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryLifecycleAction,MemoryLifecycleRequestV1
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryWriteOrchestrator,
    MemoryQueryOrchestrator,
    MemoryControlOrchestrator,
    MemoryExplanationRequestV1,
    MemoryCorrectionCommandV1,
    OrchestrationError,
)
from backend_memory_pipeline.retrieval.retrieval import RetrievalRequestV1
from backend_memory_pipeline.mcp.schemas import (
    SearchMemoryInput,
    SearchMemoryOutput,
    ListUserMemoriesInput,
    ListUserMemoriesOutput,
    AddExplicitPreferenceInput,
    AddExplicitPreferenceOutput,
    CorrectMemoryInput,
    CorrectMemoryOutput,
    DeleteMemoryInput,
    DeleteMemoryOutput,
    ExplainMemoryUseInput,
    ExplainMemoryUseOutput,
)
def _get_authenticated_subject_id()->str:
    access_token=get_access_token()
    if access_token is None:
        raise OrchestrationError("MCP authentication is required.")
    subject_id=access_token.subject
    if subject_id is None or not str(subject_id).strip():
        raise OrchestrationError("Authenticated MCP subject is missing.")
    return str(subject_id)
def _new_correlation_id()->str:
    return IngestionService.new_correlation_id()
def _utc_now()->datetime:
    return datetime.now(timezone.utc)
def _get_memory_id_from_lifecycle_result(result:Any)->str|None:
    return result.created_memory_id or result.memory_id
def search_memory(
    request:SearchMemoryInput,
    orchestrator:MemoryQueryOrchestrator
)->SearchMemoryOutput:
    subject_id=_get_authenticated_subject_id()
    correlation_id=_new_correlation_id()
    retrieval_request=RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent=request.query,
        surface=request.surface,
        locale=request.locale,
        requested_at=request.requested_at,
        top_k=request.max_items,
        candidate_limit=request.max_items,
        metadata={
            "source":"mcp",
            "correlation_id":correlation_id,
            "max_characters":request.max_characters,
        },
    )
    try:
        result=orchestrator.retrieve_memory(retrieval_request)
    except OrchestrationError:
        raise
    except Exception as exc:
        raise OrchestrationError(f"MCP memory search failed: {exc}") from exc
    context_items=[]
    character_count=0
    for candidate in result.candidates:
        item={
            "memory_id":candidate.memory_id,
            "memory_type":candidate.memory_type,
            "normalized_fact":candidate.normalized_fact,
            "confidence":candidate.confidence,
            "final_score":candidate.final_score,
            "relevance_reason":candidate.relevance_reason,
            "source_event_ids":list(candidate.source_event_ids),
            "source_session_ids":list(candidate.source_session_ids),
            "provenance":dict(candidate.provenance),
        }
        item_characters=len(candidate.normalized_fact)
        if context_items and character_count+item_characters>request.max_characters:
            break
        context_items.append(item)
        character_count+=item_characters
    return SearchMemoryOutput(
        decision=result.decision.value,
        context_items=context_items,
        memory_grounded=bool(context_items),
        correlation_id=correlation_id,
    )
def add_explicit_preference(
    request:AddExplicitPreferenceInput,
    orchestrator:MemoryWriteOrchestrator
)->AddExplicitPreferenceOutput:
    subject_id=_get_authenticated_subject_id()
    correlation_id=_new_correlation_id()
    try:
        consent_record=orchestrator.policy_consent.get_consent_state(subject_id)
    except Exception as exc:
        raise OrchestrationError(f"Consent lookup failed: {exc}") from exc

    if consent_record.state!=ConsentState.OPTED_IN:
        return AddExplicitPreferenceOutput(
            accepted=False,
            memory_ids=[],
            correlation_id=correlation_id,
            selection_required=False,
            selection_context=None,
            reason=f"Memory storage is not permitted by the current consent state: {consent_record.state.value}.",
        )
    try:
        result=orchestrator.add_explicit_preference(
            subject_id=subject_id,
            subject_scope=subject_id,
            session_id=request.session_id,
            preference=request.preference,
            surface=request.surface,
            locale=request.locale,
            effective_at=request.effective_at,
            correlation_id=correlation_id,
            entity=request.entity,
            context_entities=request.context_entities,
            metadata={
                **request.metadata,
                "source":"mcp",
            },
        )    
    except OrchestrationError:
        raise
    except Exception as exc:
        raise OrchestrationError(
            f"MCP explicit preference processing failed: {exc}"
        ) from exc
    memory_ids=[]
    for lifecycle_result in result.lifecycle_results:
        memory_id=_get_memory_id_from_lifecycle_result(lifecycle_result)
        if memory_id is not None and memory_id not in memory_ids:
            memory_ids.append(memory_id)
    accepted=any(
        decision.decision.value=="allow"
        for decision in result.policy_decisions
    )
    selection_groups=[]
    for resolution in (result.entity_resolution or []):
        for resolved in resolution.resolved_entities:
            if not resolved.candidate_options:
                continue
            context_entities=request.context_entities or {}
            artists=context_entities.get("artists", []) if isinstance(context_entities,dict) else []
            context_artist=None
            if isinstance(artists,list):
                for artist in artists:
                    if isinstance(artist,dict) and isinstance(artist.get("name"),str):
                        context_artist=artist["name"].strip()
                        if context_artist: break
            selection_groups.append({"entity_type":resolved.entity_type.value,"entity_name":resolved.mention,"context_artist":context_artist if resolved.entity_type.value=="track" else None,"candidates":resolved.candidate_options})
    selection_context=None
    if selection_groups:
        first=selection_groups[0]
        selection_context={"preference":request.preference,"entity_type":first["entity_type"],"entity_name":first["entity_name"],"context_artist":first["context_artist"],"candidates":first["candidates"],"groups":selection_groups}
    return AddExplicitPreferenceOutput(
        accepted=accepted,
        memory_ids=memory_ids,
        correlation_id=correlation_id,
        selection_required=selection_context is not None,
        selection_context=selection_context,
    )
def correct_memory(
    request:CorrectMemoryInput,
    orchestrator:MemoryControlOrchestrator
)->CorrectMemoryOutput:
    subject_id=_get_authenticated_subject_id()
    correlation_id=_new_correlation_id()
    command=MemoryCorrectionCommandV1(
        target_memory_id=request.memory_id,
        corrected_statement=request.corrected_statement,
        subject_id=subject_id,
        subject_scope=subject_id,
        session_id=request.session_id,
        surface=request.surface,
        locale=request.locale,
        effective_at=request.effective_at,
        reason=request.reason,
        correlation_id=correlation_id,
        metadata={
            **request.metadata,
            "source":"mcp",
        },
    )
    try:
        result=orchestrator.process_memory_correction(command)
    except OrchestrationError:
        raise
    except Exception as exc:
        raise OrchestrationError(
            f"MCP memory correction failed: {exc}"
        ) from exc
    replacement_memory_id=(
        result.lifecycle_result.created_memory_id
        or result.lifecycle_result.memory_id
    )
    return CorrectMemoryOutput(
        corrected=result.lifecycle_result.changed,
        target_memory_id=result.target_memory_id,
        replacement_memory_id=replacement_memory_id,
        correlation_id=correlation_id,
    )

def list_user_memories(
    request:ListUserMemoriesInput,
    orchestrator:MemoryControlOrchestrator,
)->ListUserMemoriesOutput:
    subject_id=_get_authenticated_subject_id()
    correlation_id=_new_correlation_id()
    try:
        store=orchestrator.lifecycle.store
        records=store.list_by_subject(subject_id)
    except Exception as exc:
        raise OrchestrationError(f"Unable to list the authenticated user's memories: {exc}") from exc
    memories=[]
    for memory in records:
        if memory.subject_id!=subject_id or memory.subject_scope!=subject_id:
            continue
        if not request.include_inactive and memory.status.value!="active":
            continue
        if memory.memory_type.value=="non_memory":
            continue
        memories.append({
            "memory_id":memory.memory_id,
            "memory_type":memory.memory_type.value,
            "normalized_fact":memory.normalized_fact,
            "status":memory.status.value,
            "created_at":memory.created_at.isoformat(),
            "entities":memory.entities,
        })
        if len(memories)>=request.max_items:
            break
    return ListUserMemoriesOutput(
        memories=memories,
        correlation_id=correlation_id,
    )

def delete_memory(
    request:DeleteMemoryInput,
    orchestrator:MemoryControlOrchestrator
)->DeleteMemoryOutput:
    subject_id=_get_authenticated_subject_id()
    correlation_id=_new_correlation_id()
    lifecycle_request=MemoryLifecycleRequestV1(
        action=MemoryLifecycleAction.DELETE,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_id=request.memory_id,
        effective_at=request.effective_at,
        reason=request.reason,
        correlation_id=correlation_id,
        metadata={
            **request.metadata,
            "source":"mcp",
        },
    )
    try:
        result=orchestrator.apply_lifecycle_action(
            lifecycle_request
        )
    except OrchestrationError:
        raise
    except Exception as exc:
        raise OrchestrationError(
            f"MCP memory deletion failed: {exc}"
        ) from exc
    lifecycle_result=result.lifecycle_result
    if lifecycle_result is None:
        raise OrchestrationError(
            "Memory deletion did not produce a lifecycle result."
        )
    return DeleteMemoryOutput(
        deleted=lifecycle_result.changed,
        memory_id=request.memory_id,
        correlation_id=correlation_id,
    )
def explain_memory_use(
    request:ExplainMemoryUseInput,
    orchestrator:MemoryQueryOrchestrator
)->ExplainMemoryUseOutput:
    subject_id=_get_authenticated_subject_id()
    correlation_id=_new_correlation_id()
    explanation_request=MemoryExplanationRequestV1(
        memory_id=request.memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        current_intent=request.current_intent,
        surface=request.surface,
        locale=request.locale,
        correlation_id=correlation_id,
    )
    try:
        result=orchestrator.explain_memory_use(
            explanation_request
        )
    except OrchestrationError:
        raise
    except Exception as exc:
        raise OrchestrationError(
            f"MCP memory explanation failed: {exc}"
        ) from exc
    return ExplainMemoryUseOutput(
        memory_id=result.memory_id,
        subject_id=result.subject_id,
        explanation=result.explanation,
        relevance_reason=result.relevance_reason,
        source=result.source,
        confidence=result.confidence,
        timestamp=result.timestamp,
        correlation_id=correlation_id,
    )