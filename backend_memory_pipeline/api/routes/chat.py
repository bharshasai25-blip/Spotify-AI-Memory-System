from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,status
from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_query_orchestrator,
    #require_subject
)
from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    ChatRequestV1,
    ChatResponseV1
)
from backend_memory_pipeline.context_composition.context_composition import (
    ContextCompositionRequestV1
)
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryQueryOrchestrator,
    OrchestrationError
)
from backend_memory_pipeline.response_generation.response_generation import (
    ResponseGenerationRequestV1
)
from backend_memory_pipeline.retrieval.retrieval import (
    RetrievalRequestV1
)
router=APIRouter(
    prefix="/v1",
    tags=["chat"]
)
@router.post(
    "/chat",
    response_model=ChatResponseV1,
    responses={
        400:{
            "model":APIErrorResponseV1,
            "description":"Invalid chat request."
        },
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication required."
        },
        403:{
            "model":APIErrorResponseV1,
            "description":"Authenticated subject does not match requested subject."
        },
        500:{
            "model":APIErrorResponseV1,
            "description":"Chat processing failed."
        }
    }
)
def chat(
    request:ChatRequestV1,
    current_subject:CurrentSubject,
    orchestrator:MemoryQueryOrchestrator=Depends(
        get_memory_query_orchestrator
    )
)->ChatResponseV1:
    correlation_id=str(uuid4())
    '''
    require_subject(
        request.subject_id,
        current_subject
    )
    if request.subject_scope!=current_subject.subject_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated subject does not match requested subject scope."
        )
    '''    
    try:
        retrieval_request=RetrievalRequestV1(
            subject_id=current_subject.subject_id,
            subject_scope=current_subject.subject_id,
            intent=request.query,
            surface=request.surface,
            locale=request.locale,
            requested_at=request.requested_at,
            metadata={
                **request.metadata,
                "correlation_id":correlation_id
            }
        )
        context_request=ContextCompositionRequestV1(
            subject_id=current_subject.subject_id,
            subject_scope=current_subject.subject_id,
            requested_at=request.requested_at,
            max_items=5,
            max_characters=request.max_response_characters,
            max_tokens=3000,
            surface=request.surface,
            locale=request.locale,
            metadata={
                **request.metadata,
                "correlation_id":correlation_id
            }
        )
        response_request=ResponseGenerationRequestV1(
            subject_id=current_subject.subject_id,
            subject_scope=current_subject.subject_id,
            query=request.query,
            surface=request.surface,
            locale=request.locale,
            requested_at=request.requested_at,
            max_response_characters=request.max_response_characters,
            include_memory_references=request.include_memory_references,
            metadata={
                **request.metadata,
                "correlation_id":correlation_id
            }
        )
        result=orchestrator.process_query(
            retrieval_request,
            context_request,
            response_request
        )
        #print("CHAT ORCHESTRATION RESULT:", result)

    except OrchestrationError as exc:
        #print("CHAT ORCHESTRATION ERROR:", repr(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat processing failed."
            #detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc
    except Exception as exc:
        #print("CHAT UNEXPECTED ERROR:", repr(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat processing failed."
            #detail=str(exc)
        ) from exc
    return ChatResponseV1(
        response=result.response,
        correlation_id=correlation_id,
        trace_id=result.response.response_metadata.get("trace_id"),
        metadata={
            "retrieval_decision":result.retrieval.decision.value,
            "context_decision":result.context.decision.value,
            "memory_grounded":result.response.memory_grounded,
            "context_item_count":result.response.context_item_count
        }
    )