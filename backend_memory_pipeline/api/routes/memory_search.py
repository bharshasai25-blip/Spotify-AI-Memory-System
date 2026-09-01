from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_query_orchestrator,
)

from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    MemorySearchRequestV1,
    MemorySearchResponseV1,
)

from backend_memory_pipeline.orchestration.orchestration import (
    MemoryQueryOrchestrator,
    OrchestrationError,
)

from backend_memory_pipeline.retrieval.retrieval import (
    RetrievalRequestV1,
)


router = APIRouter(
    prefix="/v1",
    tags=["memory-search"],
)


@router.post(
    "/memories/search",
    response_model=MemorySearchResponseV1,
    responses={
        400: {
            "model": APIErrorResponseV1,
            "description": "Invalid memory search request.",
        },
        401: {
            "model": APIErrorResponseV1,
            "description": "Authentication required.",
        },
        403: {
            "model": APIErrorResponseV1,
            "description": "Authenticated subject does not match requested subject.",
        },
        500: {
            "model": APIErrorResponseV1,
            "description": "Memory retrieval failed.",
        },
    },
)
def search_memory(
    request: MemorySearchRequestV1,
    current_subject: CurrentSubject,
    orchestrator: MemoryQueryOrchestrator = Depends(
        get_memory_query_orchestrator
    ),
) -> MemorySearchResponseV1:

    correlation_id = str(uuid4())

    try:
        retrieval_request = RetrievalRequestV1(
            subject_id=current_subject.subject_id,
            subject_scope=current_subject.subject_id,
            intent=request.intent,
            surface=request.surface,
            locale=request.locale,
            requested_at=request.requested_at,
            top_k=request.top_k,
            candidate_limit=request.candidate_limit,
            vector_weight=request.vector_weight,
            graph_weight=request.graph_weight,
            min_score=request.min_score,
            metadata={
                **request.metadata,
                "correlation_id": correlation_id,
            },
        )

        result = orchestrator.retrieve_memory(
            retrieval_request
        )

    except OrchestrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory retrieval failed.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory retrieval failed.",
        ) from exc

    return MemorySearchResponseV1(
        decision=result.decision.value,
        subject_id=current_subject.subject_id,
        query_intent=request.intent,
        candidates=[
            candidate.model_dump()
            for candidate in result.candidates
        ],
        candidate_count=result.candidate_count,
        graph_candidate_count=result.graph_candidate_count,
        vector_candidate_count=result.vector_candidate_count,
        returned_count=len(result.candidates),
        retrieval_version=result.retrieval_version,
        correlation_id=correlation_id,
        metadata={
            "requested_top_k": request.top_k,
            "requested_candidate_limit": request.candidate_limit,
            "vector_weight": request.vector_weight,
            "graph_weight": request.graph_weight,
        },
    )