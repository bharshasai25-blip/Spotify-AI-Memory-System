from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from backend_memory_pipeline.api.dependencies import CurrentSubject, get_consent_state_store, get_entity_repository, get_memory_store, get_user_entity_action_repository
from backend_memory_pipeline.persistence.postgres.entity_repository import PostgreSQLCatalogRepository
from backend_memory_pipeline.persistence.postgres.memory_repository import PostgreSQLMemoryStore
from backend_memory_pipeline.persistence.postgres.user_entity_action_repository import PostgreSQLUserEntityActionRepository
from backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity
router=APIRouter(prefix="/v1",tags=["user-content"])
@router.get("/profile")
def get_profile(current_subject:CurrentSubject):
    return {"subject_id":current_subject.subject_id,"username":current_subject.username}
@router.get("/memories")
def list_memories(current_subject:CurrentSubject,start:Optional[datetime]=Query(default=None),end:Optional[datetime]=Query(default=None),query:Optional[str]=Query(default=None,max_length=500),memory_store:PostgreSQLMemoryStore=Depends(get_memory_store)):
    records=memory_store.list_by_subject(current_subject.subject_id)
    query_text=(query or "").strip().casefold()
    result=[]
    for item in records:
        if item.status.value not in {"active","superseded"}:
            continue
        if start and item.created_at<start:
            continue
        if end and item.created_at>end:
            continue
        if query_text and query_text not in item.normalized_fact.casefold() and not any(query_text in str(entity).casefold() for entity in item.entities):
            continue
        result.append({"memory_id":item.memory_id,"subject_id":item.subject_id,"memory_type":item.memory_type.value,"normalized_fact":item.normalized_fact,"entities":item.entities,"confidence":item.confidence,"created_at":item.created_at.isoformat(),"valid_from":item.valid_from.isoformat(),"valid_to":item.valid_to.isoformat() if item.valid_to else None,"status":item.status.value,"retrieval_eligible":item.retrieval_eligible,"metadata":item.metadata})
    return {"subject_id":current_subject.subject_id,"count":len(result),"memories":result}
@router.get("/recommendations")
def get_recommendations(current_subject:CurrentSubject,catalog:PostgreSQLCatalogRepository=Depends(get_entity_repository),consent_store=Depends(get_consent_state_store),actions:PostgreSQLUserEntityActionRepository=Depends(get_user_entity_action_repository),memory_store:PostgreSQLMemoryStore=Depends(get_memory_store),limit:int=Query(default=100,ge=1,le=200)):
    consent_record=consent_store.get(current_subject.subject_id)
    if consent_record is None or consent_record.state.value!="opted_in":
        empty={"saved_tracks":[],"saved_albums": [],"followed_artists":[],"preferred_entities":[]}
        return {"subject_id":current_subject.subject_id,"count":0,"recommendations":[],"folders":empty,"reason":"Opt in to memory personalization to manage saved tracks and albums, followed artists, and preferred entities."}
    action_map=actions.get_actions(current_subject.subject_id)
    memory_preferred_ids=set()
    for memory in memory_store.list_by_subject(current_subject.subject_id):
        if memory.status.value!="active" or memory.memory_type.value!="explicit_preference": continue
        for entity_ref in memory.entities:
            if isinstance(entity_ref,dict):
                entity_id=entity_ref.get("canonical_id") or entity_ref.get("entity_id") or entity_ref.get("entityId")
                if entity_id: memory_preferred_ids.add(entity_id)
    for entity_id in memory_preferred_ids:
        action_map.setdefault(entity_id,{'follow':False,'save':False,'preference':False,'_has_preference_record':False})
    items_by_id={}
    for entity_id,state in action_map.items():
        preferred = bool(state.get('preference')) if state.get('_has_preference_record') else entity_id in memory_preferred_ids
        if not any([state.get('follow'),state.get('save'),preferred]): continue
        try:
            entity=catalog.get(entity_id)
            if entity is None: continue
            mappings=catalog.list_external_mappings(entity_id)
        except Exception:
            continue
        direct=next((m.get("external_url") for m in mappings if str(m.get("provider","")).casefold()=="spotify" and m.get("external_url")),None)
        metadata=dict(entity.metadata or {})
        artist_names=metadata.get("artist_names") or []
        if not artist_names and isinstance(metadata.get("artist-credit"),list):
            artist_names=[part.get("name") or (part.get("artist") or {}).get("name") for part in metadata["artist-credit"] if isinstance(part,dict)]
            artist_names=[name for name in artist_names if isinstance(name,str) and name.strip()]
        artist_name=", ".join(artist_names) if artist_names else ""
        links=spotify_link_for_catalog_entity(entity.canonical_name,entity.entity_type.value,artist_name,direct)
        items_by_id[entity_id]={"entity_id":entity.entity_id,"name":entity.canonical_name,"entity_type":entity.entity_type.value,"artist_names":artist_names,"actions":{"follow":bool(state.get("follow")),"save":bool(state.get("save")),"preference":preferred},"is_followed":bool(state.get("follow")),"is_saved":bool(state.get("save")),"is_preferred":preferred,**links}
    items=list(items_by_id.values())
    saved_tracks=[item for item in items if item["entity_type"]=="track" and item["is_saved"]]
    saved_albums=[item for item in items if item["entity_type"]=="album" and item["is_saved"]]
    followed_artists=[item for item in items if item["entity_type"]=="artist" and item["is_followed"]]
    preferred_entities=[item for item in items if item["entity_type"] in {"artist","track","album"} and item["is_preferred"]]
    folders={"saved_tracks":saved_tracks[:limit],"saved_albums":saved_albums[:limit],"followed_artists":followed_artists[:limit],"preferred_entities":preferred_entities[:limit]}
    return {"subject_id":current_subject.subject_id,"count":len(items),"recommendations":items[:limit],"folders":folders,"reason":None}
