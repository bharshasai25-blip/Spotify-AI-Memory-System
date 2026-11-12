from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend_memory_pipeline.api.dependencies import CurrentSubject, get_entity_repository, get_musicbrainz_catalog_service, get_consent_state_store, get_memory_write_orchestrator, get_user_entity_action_repository, get_memory_control_orchestrator, get_memory_store
from backend_memory_pipeline.entity_resolution.entity_resolution import EntityType
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_catalog_service import MusicBrainzCatalogService
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_client import MusicBrainzClientError
from backend_memory_pipeline.persistence.postgres.entity_repository import PostgreSQLCatalogRepository
from backend_memory_pipeline.persistence.postgres.user_entity_action_repository import PostgreSQLUserEntityActionRepository
from backend_memory_pipeline.persistence.postgres.memory_repository import PostgreSQLMemoryStore
from backend_memory_pipeline.orchestration.orchestration import MemoryWriteOrchestrator, MemoryControlOrchestrator, OrchestrationError
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryLifecycleAction, MemoryLifecycleRequestV1
from backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity

router=APIRouter(prefix='/v1/catalog',tags=['music-catalog'])

class CatalogActionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    entity_id: str = Field(min_length=1,max_length=256)
    entity_type: Literal['artist','track','album']
    action: Literal['follow','save','preference']
    active: bool
    mbid: Optional[str] = Field(default=None,max_length=64)
    name: Optional[str] = Field(default=None,max_length=1000)
    artist_name: Optional[str] = Field(default=None,max_length=1000)

@router.get('/search')
def search_catalog(current_subject: CurrentSubject, query: str = Query(default='',max_length=300), entity_type: Literal['all','artist','track','album']='all', limit: int=Query(default=30,ge=1,le=100), catalog: PostgreSQLCatalogRepository=Depends(get_entity_repository), service: MusicBrainzCatalogService=Depends(get_musicbrainz_catalog_service), actions: PostgreSQLUserEntityActionRepository=Depends(get_user_entity_action_repository)):
    q=query.strip()
    if not q:
        return {'query':query,'count':0,'results':[]}
    types=['artist','track','album'] if entity_type=='all' else [entity_type]
    found: dict[str,dict[str,Any]]={}
    for kind in types:
        try:
            existing=catalog.search_catalog(q,EntityType(kind),limit=limit)
        except Exception:
            existing=[]
        for entity in existing:
            metadata=dict(entity.metadata or {})
            mbid=metadata.get('musicbrainz_id')
            if not mbid and entity.entity_id.startswith(f'musicbrainz:{kind}:'):
                mbid=entity.entity_id.rsplit(':',1)[-1]
            mappings=catalog.list_external_mappings(entity.entity_id)
            direct=next((m.get('external_url') for m in mappings if str(m.get('provider','')).casefold()=='spotify' and m.get('external_url')),None)
            artist_names=metadata.get('artist_names') or metadata.get('artist_credit_names') or []
            if not artist_names and isinstance(metadata.get('artist_credit'),list):
                artist_names=[part.get('name') or (part.get('artist') or {}).get('name') for part in metadata['artist_credit'] if isinstance(part,dict)]
                artist_names=[name for name in artist_names if isinstance(name,str) and name.strip()]
            artist_name=', '.join(artist_names) if isinstance(artist_names,list) else ''
            item={'entity_id':entity.entity_id,'mbid':mbid,'entity_type':kind,'name':entity.canonical_name,'artist_names':artist_names if isinstance(artist_names,list) else [],'release_names':metadata.get('release_names',[]),'disambiguation':metadata.get('disambiguation',''),'length_ms':metadata.get('length_ms'),'already_cataloged':True}
            item.update(spotify_link_for_catalog_entity(item['name'],kind,artist_name,direct))
            found[entity.entity_id]=item
    try:
        for kind in types:
            mb_candidates=service.search_candidates(entity_type=kind,query=q,limit=limit,exact_only=False)
            for candidate in mb_candidates:
                mbid=candidate.get('mbid')
                if not mbid: continue
                entity_id=f'musicbrainz:{kind}:{mbid}'
                if entity_id in found: continue
                artist_name=', '.join(candidate.get('artist_names') or [])
                item={'entity_id':entity_id,'mbid':mbid,'entity_type':kind,'name':candidate.get('name') or q,'artist_names':candidate.get('artist_names') or [],'release_names':candidate.get('release_names') or [],'disambiguation':candidate.get('disambiguation') or '', 'length_ms':candidate.get('length_ms'),'already_cataloged':False}
                item.update(spotify_link_for_catalog_entity(item['name'],kind,artist_name,None))
                found[entity_id]=item
    except (MusicBrainzClientError,ValueError):
        # A catalog search should still return local entities if MusicBrainz is unavailable.
        pass
    user_actions=actions.get_actions(current_subject.subject_id)
    results=[]
    for item in found.values():
        state=user_actions.get(item['entity_id'],{})
        item.update({'is_followed':bool(state.get('follow')),'is_saved':bool(state.get('save')),'is_preferred':bool(state.get('preference'))})
        results.append(item)
    results.sort(key=lambda item:(not item['already_cataloged'],item['name'].casefold(),item.get('disambiguation','')))
    return {'query':q,'count':len(results[:limit]),'results':results[:limit]}

@router.post('/actions')
def update_catalog_action(request: CatalogActionRequest, current_subject: CurrentSubject, catalog: PostgreSQLCatalogRepository=Depends(get_entity_repository), service: MusicBrainzCatalogService=Depends(get_musicbrainz_catalog_service), consent_store=Depends(get_consent_state_store), orchestrator: MemoryWriteOrchestrator=Depends(get_memory_write_orchestrator), actions: PostgreSQLUserEntityActionRepository=Depends(get_user_entity_action_repository), control: MemoryControlOrchestrator=Depends(get_memory_control_orchestrator), memory_store: PostgreSQLMemoryStore=Depends(get_memory_store)):
    allowed={'artist':{'follow','preference'},'track':{'save','preference'},'album':{'save','preference'}}
    if request.action not in allowed.get(request.entity_type,set()):
        raise HTTPException(status_code=400,detail=f"The {request.action} action is not supported for {request.entity_type} entities.")
    entity=catalog.get(request.entity_id)
    if entity is None and request.mbid:
        try: entity=service.catalog_entity_by_mbid(request.entity_type,request.mbid)
        except Exception as exc: raise HTTPException(status_code=502,detail='Could not load the selected MusicBrainz entity.') from exc
    if entity is None:
        raise HTTPException(status_code=404,detail='Entity is not in the catalog. Refresh search results and try again.')
    if entity.entity_type.value!=request.entity_type:
        raise HTTPException(status_code=400,detail='Entity type does not match the selected catalog entity.')
    consent=consent_store.get(current_subject.subject_id)
    if consent is None or getattr(consent.state,'value',str(consent.state))!='opted_in':
        raise HTTPException(status_code=403,detail='Enable memory consent before saving, following, or preferring music entities.')
    current_actions=actions.get_actions(current_subject.subject_id).get(entity.entity_id,{})
    prior_record=actions.get_action_record(current_subject.subject_id,entity.entity_id,request.action)
    if prior_record and bool(prior_record.get('active')) == request.active:
        return {'status':'unchanged','entity_id':entity.entity_id,'action':request.action,'active':request.active,'actions':{'follow':bool(current_actions.get('follow')),'save':bool(current_actions.get('save')),'preference':bool(current_actions.get('preference'))}}
    if not prior_record and not request.active and request.action!='preference':
        return {'status':'unchanged','entity_id':entity.entity_id,'action':request.action,'active':False,'actions':{'follow':False,'save':False,'preference':False}}
    if request.action=='preference' and not request.active and prior_record and prior_record.get('active'):
        memory_ids=(prior_record.get('metadata') or {}).get('memory_ids',[]) if prior_record else []
        # Also find explicit preference memories created through Chat, which may
        # not have originated from the catalog UI action.
        for memory in memory_store.list_by_subject(current_subject.subject_id):
            if memory.status.value != 'active' or memory.memory_type.value != 'explicit_preference': continue
            if any(isinstance(ref,dict) and (ref.get('canonical_id') or ref.get('entity_id') or ref.get('entityId')) == entity.entity_id for ref in memory.entities):
                memory_ids.append(memory.memory_id)
        for memory_id in dict.fromkeys(memory_ids if isinstance(memory_ids,list) else []):
            if not isinstance(memory_id,str) or not memory_id: continue
            try:
                control.apply_lifecycle_action(MemoryLifecycleRequestV1(action=MemoryLifecycleAction.DELETE,subject_id=current_subject.subject_id,subject_scope=current_subject.subject_id,memory_id=memory_id,effective_at=datetime.now(timezone.utc),reason='Removed this entity from the preferred music list.',correlation_id=str(uuid4()),metadata={'source':'catalog_action','entity_id':entity.entity_id,'action':'remove_preference'}))
            except OrchestrationError as exc:
                if 'was not found' not in str(exc).casefold():
                    raise HTTPException(status_code=409,detail=f'Could not remove the associated preference memory: {exc}') from exc
    if request.action=='preference' and request.active:
        artist_name=request.artist_name
        if not artist_name and entity.entity_type==EntityType.TRACK:
            artist_credit=entity.metadata.get('artist-credit',[])
            if isinstance(artist_credit,list):
                names=[]
                for part in artist_credit:
                    if isinstance(part,dict):
                        if isinstance(part.get('name'),str): names.append(part['name'])
                        elif isinstance(part.get('artist'),dict) and isinstance(part['artist'].get('name'),str): names.append(part['artist']['name'])
                artist_name=', '.join(dict.fromkeys(names))
        try:
            result=orchestrator.add_explicit_preference(subject_id=current_subject.subject_id,subject_scope=current_subject.subject_id,session_id=f'catalog:{current_subject.subject_id}',preference=f'I prefer {entity.canonical_name}'+(f' by {artist_name}' if artist_name else ''),surface='catalog',locale='en-US',effective_at=datetime.now(timezone.utc),correlation_id=str(uuid4()),idempotency_key=f'catalog-preference:{current_subject.subject_id}:{entity.entity_id}:{uuid4()}',entity={'entity_type':request.entity_type,'name':entity.canonical_name,'canonical_id':entity.entity_id},context_entities={'artists':[{'entity_type':'artist','name':artist_name}]} if artist_name and request.entity_type=='track' else {},metadata={'source':'catalog_action','action':'preference','entity_id':entity.entity_id})
        except OrchestrationError as exc:
            raise HTTPException(status_code=400,detail=str(exc)) from exc
        allowed_decision=any(getattr(item.decision,'value',item.decision)=='allow' for item in result.policy_decisions)
        memory_created=any(bool(getattr(item,'changed',False) and (getattr(item,'created_memory_id',None) or getattr(item,'memory_id',None))) for item in result.lifecycle_results)
        if not allowed_decision or not memory_created:
            raise HTTPException(status_code=409,detail='The preference was not saved by the memory policy. Check consent and policy status, then try again.')
        memory_ids=[getattr(item,'created_memory_id',None) or getattr(item,'memory_id',None) for item in result.lifecycle_results]
        memory_ids=[memory_id for memory_id in memory_ids if memory_id]
    else:
        memory_ids=[]
    record=actions.set_action(current_subject.subject_id,entity.entity_id,request.action,request.active,{'source':'catalog_ui','entity_type':request.entity_type,'memory_ids':memory_ids} if request.action=='preference' and request.active else {'source':'catalog_ui','entity_type':request.entity_type})
    state=actions.get_actions(current_subject.subject_id).get(entity.entity_id,{})
    mappings=catalog.list_external_mappings(entity.entity_id)
    direct=next((mapping.get('external_url') for mapping in mappings if str(mapping.get('provider','')).casefold()=='spotify' and mapping.get('external_url')),None)
    links=spotify_link_for_catalog_entity(entity.canonical_name,entity.entity_type.value,request.artist_name,direct)
    return {'status':'updated','entity_id':entity.entity_id,'action':request.action,'active':record['active'],'actions':{'follow':bool(state.get('follow')),'save':bool(state.get('save')),'preference':bool(state.get('preference'))},**links}
