from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend_memory_pipeline.api.dependencies import AuthenticatedRequest, CurrentSubject, get_authenticated_request, get_conversation_repository, get_gemini_mcp_agent, get_or_touch_active_session
from backend_memory_pipeline.api.schemas import APIErrorResponseV1, ChatRequestV1, ChatResponseV1
from backend_memory_pipeline.api.musicbrainz_selection_tokens import create_selection_token
from backend_memory_pipeline.agent.gemini_mcp_agent import GeminiMCPAgent, GeminiMCPAgentError
from backend_memory_pipeline.response_generation.response_generation import GeneratedResponseV1, ResponseDecision
from backend_memory_pipeline.persistence.postgres.conversation_repository import PostgreSQLConversationRepository
router=APIRouter(prefix="/v1",tags=["chat"])
@router.get("/chat/history")
def get_chat_history(current_subject:CurrentSubject,conversation_id:str=Query(min_length=1,max_length=128),repository:PostgreSQLConversationRepository=Depends(get_conversation_repository)):
    messages=repository.list_messages(current_subject.subject_id,conversation_id,limit=5000)
    return {"conversation_id":conversation_id,"messages":messages}
@router.post("/chat",response_model=ChatResponseV1,responses={400:{"model":APIErrorResponseV1,"description":"Invalid chat request."},401:{"model":APIErrorResponseV1,"description":"Authentication required."},500:{"model":APIErrorResponseV1,"description":"Chat processing failed."}})
async def chat(request:ChatRequestV1,authenticated_request:AuthenticatedRequest=Depends(get_authenticated_request),session_id:str=Depends(get_or_touch_active_session),agent:GeminiMCPAgent=Depends(get_gemini_mcp_agent),repository:PostgreSQLConversationRepository=Depends(get_conversation_repository))->ChatResponseV1:
    correlation_id=str(uuid4())
    subject=authenticated_request.subject
    conversation_id=request.conversation_id or str(uuid4())
    history=repository.list_messages(subject.subject_id,conversation_id,limit=5000)
    # Persist the new user message before generation so the transcript remains available if generation fails.
    repository.append_message(subject.subject_id,conversation_id,"user",request.query,{"surface":request.surface,"locale":request.locale})
    try:
        result=await agent.chat(query=request.query,subject_id=subject.subject_id,subject_scope=subject.subject_id,surface=request.surface,locale=request.locale,access_token=authenticated_request.access_token,requested_at=request.requested_at,max_response_characters=request.max_response_characters,session_id=session_id,history=history[-30:])
    except GeminiMCPAgentError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f"Chat processing failed: {exc}") from exc
    '''
    repository.append_message(subject.subject_id,conversation_id,"assistant",result.response_text,{"model":result.model_version,"memory_grounded":result.memory_grounded})
    generated_response=GeneratedResponseV1(response_id=str(uuid4()),decision=ResponseDecision.GENERATED if result.memory_grounded else ResponseDecision.NO_CONTEXT,subject_id=subject.subject_id,query=request.query,response_text=result.response_text,memory_grounded=result.memory_grounded,memory_references=[],context_item_count=0,model_name=result.model_name,model_version=result.model_version,generated_at=request.requested_at,response_metadata={"surface":request.surface,"locale":request.locale,"provider":"gemini_mcp_agent","session_id":session_id,"conversation_id":conversation_id,"memory_result_available":result.memory_result is not None})
    return ChatResponseV1(conversation_id=conversation_id,response=generated_response,correlation_id=correlation_id,trace_id=None,metadata={"memory_grounded":result.memory_grounded,"provider":"gemini_mcp_agent","model":result.model_version})
    '''
    response_text=result.response_text
    response_metadata={"surface":request.surface,"locale":request.locale,"provider":"gemini_mcp_agent","session_id":session_id,"conversation_id":conversation_id,"memory_result_available":result.memory_result is not None}
    tool_result=result.memory_result if isinstance(result.memory_result,dict) else {}
    selection_context=tool_result.get("selection_context") if tool_result.get("selection_required") else None
    if isinstance(selection_context,dict):
        raw_groups=selection_context.get("groups") if isinstance(selection_context.get("groups"),list) else [{"entity_type":selection_context.get("entity_type") or "track","entity_name":selection_context.get("entity_name") or "","context_artist":selection_context.get("context_artist"),"candidates":selection_context.get("candidates",[])}]
        candidate_groups=[]
        for group in raw_groups:
            if not isinstance(group,dict): continue
            group_candidates=[item for item in group.get("candidates",[]) if isinstance(item,dict) and isinstance(item.get("mbid"),str) and item.get("mbid").strip()]
            if not group_candidates: continue
            candidate_groups.append({"entity_type":str(group.get("entity_type") or "track"),"entity_name":str(group.get("entity_name") or ""),"context_artist":group.get("context_artist"),"candidates":group_candidates,"candidate_mbids":[item["mbid"] for item in group_candidates]})
        candidate_ids=list(dict.fromkeys(mbid for group in candidate_groups for mbid in group["candidate_mbids"]))
        if candidate_ids and candidate_groups:
            selection_id=str(uuid4())
            first=candidate_groups[0]
            token=create_selection_token({"selection_id":selection_id,"subject_id":subject.subject_id,"session_id":session_id,"surface":request.surface,"locale":request.locale,"preference":str(selection_context.get("preference") or request.query),"entity_type":first["entity_type"],"entity_name":first["entity_name"],"context_artist":first.get("context_artist"),"candidate_mbids":candidate_ids,"candidate_groups":[{"entity_type":group["entity_type"],"entity_name":group["entity_name"],"context_artist":group.get("context_artist"),"candidate_mbids":group["candidate_mbids"],"candidates":[{"mbid":item.get("mbid"),"name":item.get("name"),"artist_names":item.get("artist_names",[]),"release_names":item.get("release_names",[]),"disambiguation":item.get("disambiguation","")} for item in group["candidates"]]} for group in candidate_groups],"created_at":request.requested_at.isoformat()})
            response_metadata["musicbrainz_selection"]={"selection_id":selection_id,"selection_token":token,"candidates":first["candidates"],"groups":candidate_groups,"entity_type":first["entity_type"],"entity_name":first["entity_name"],"context_artist":first.get("context_artist")}
            if len(candidate_groups)==1:
                response_text=f"I found {len(first['candidates'])} matching {first['entity_type']} result(s) for {first['entity_name'] or 'that entity'}. Select the result(s) you mean below. I will not save the memory until you confirm your selection."
            else:
                response_text=f"I found matching catalog results for {len(candidate_groups)} entities. Choose the result(s) you mean in each group below. I will not save the memory until you confirm your selections."
    repository.append_message(subject.subject_id,conversation_id,"assistant",response_text,{"model":result.model_version,"memory_grounded":result.memory_grounded,"response_metadata":response_metadata})
    generated_response=GeneratedResponseV1(response_id=str(uuid4()),decision=ResponseDecision.GENERATED if result.memory_grounded else ResponseDecision.NO_CONTEXT,subject_id=subject.subject_id,query=request.query,response_text=response_text,memory_grounded=result.memory_grounded,memory_references=[],context_item_count=0,model_name=result.model_name,model_version=result.model_version,generated_at=request.requested_at,response_metadata=response_metadata)
    return ChatResponseV1(conversation_id=conversation_id,response=generated_response,correlation_id=correlation_id,trace_id=None,metadata={"memory_grounded":result.memory_grounded,"provider":"gemini_mcp_agent","model":result.model_version})
