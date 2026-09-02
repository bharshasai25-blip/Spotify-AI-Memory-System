from fastapi import APIRouter,Depends,HTTPException,status
from fastapi.responses import JSONResponse
from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_query_orchestrator
)

from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    MemoryExplanationRequestV1,
    MemoryExplanationResponseV1
)

from backend_memory_pipeline.ingestion.ingestion import IngestionService

from backend_memory_pipeline.orchestration.orchestration import (
    MemoryExplanationRequestV1 as OrchestrationMemoryExplanationRequestV1,
    MemoryQueryOrchestrator,
    OrchestrationError
)


router=APIRouter(
    prefix="/v1",
    tags=["memory-explanation"]
)


@router.get(
    "/memories/{memory_id}/explanation",
    response_model=MemoryExplanationResponseV1,
    responses={
        400: {"model": APIErrorResponseV1},
        401: {"model": APIErrorResponseV1},
        403: {"model": APIErrorResponseV1},
        404: {"model": APIErrorResponseV1},
        500: {"model": APIErrorResponseV1},
    },
)
def explain_memory_use(
    memory_id: str,
    current_subject: CurrentSubject,
    request: MemoryExplanationRequestV1 = Depends(),
    orchestrator: MemoryQueryOrchestrator = Depends(
        get_memory_query_orchestrator
    ),
) -> MemoryExplanationResponseV1:
    if not memory_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="memory_id is required.",
        )

    correlation_id = (
        request.correlation_id
        or IngestionService.new_correlation_id()
    )

    orchestration_request = OrchestrationMemoryExplanationRequestV1(
        memory_id=memory_id,
        subject_id=current_subject.subject_id,
        subject_scope=current_subject.subject_id,
        current_intent=request.current_intent,
        surface=request.surface,
        locale=request.locale,
        correlation_id=correlation_id,
    )

    try:
        result = orchestrator.explain_memory_use(
            orchestration_request
        )

    except OrchestrationError as exc:
        message = str(exc)

        if "was not found" in message.lower():
            return JSONResponse(
              status_code=status.HTTP_404_NOT_FOUND,
              content=APIErrorResponseV1(
                code="MEMORY_NOT_FOUND",
                message=message,
                correlation_id=correlation_id,
            ).model_dump(mode="json"),
        )

        if "does not belong" in message.lower():
            return JSONResponse(
              status_code=status.HTTP_403_FORBIDDEN,
              content=APIErrorResponseV1(
                code="MEMORY_ACCESS_FORBIDDEN",
                message=message,
                correlation_id=correlation_id,
            ).model_dump(mode="json"),
        )

        if "not permitted" in message.lower():
            return JSONResponse(
              status_code=status.HTTP_403_FORBIDDEN,
              content=APIErrorResponseV1(
                code="MEMORY_ACCESS_FORBIDDEN",
                message=message,
                correlation_id=correlation_id,
            ).model_dump(mode="json"),
        )
        
        return JSONResponse(
          status_code=status.HTTP_400_BAD_REQUEST,
          content=APIErrorResponseV1(
            code="MEMORY_EXPLANATION_INVALID",
            message=message,
            correlation_id=correlation_id,
        ).model_dump(mode="json"),
    )


    except Exception as exc:
        return JSONResponse(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          content=APIErrorResponseV1(
            code="MEMORY_EXPLANATION_FAILED",
            message="Memory explanation processing failed.",
            correlation_id=correlation_id,
        ).model_dump(mode="json"),
    )

    return MemoryExplanationResponseV1(
        memory_id=result.memory_id,
        subject_id=result.subject_id,
        explanation=result.explanation,
        relevance_reason=result.relevance_reason,
        source=result.source,
        confidence=result.confidence,
        timestamp=result.timestamp,
        correlation_id=correlation_id,
    )