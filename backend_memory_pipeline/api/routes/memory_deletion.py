from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_control_orchestrator
)

from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    MemoryDeletionRequestV1,
    MemoryDeletionResponseV1
)

from backend_memory_pipeline.ingestion.ingestion import (
    IngestionService
)

from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryLifecycleAction,
    MemoryLifecycleRequestV1
)

from backend_memory_pipeline.orchestration.orchestration import (
    MemoryControlOrchestrator,
    OrchestrationError
)


router = APIRouter(
    prefix="/v1",
    tags=["memory-deletion"]
)


@router.delete(
    "/memories/{memory_id}",
    response_model=MemoryDeletionResponseV1,
    responses={
        400: {
            "model": APIErrorResponseV1,
            "description": "Memory deletion request was rejected."
        },
        401: {
            "model": APIErrorResponseV1,
            "description": "Authentication required."
        },
        403: {
            "model": APIErrorResponseV1,
            "description": "Authenticated subject does not own the target memory."
        },
        404: {
            "model": APIErrorResponseV1,
            "description": "Target memory was not found."
        },
        500: {
            "model": APIErrorResponseV1,
            "description": "Memory deletion processing failed."
        }
    }
)
def delete_memory(
    memory_id: str,
    request: MemoryDeletionRequestV1,
    current_subject: CurrentSubject,
    orchestrator: MemoryControlOrchestrator = Depends(
        get_memory_control_orchestrator
    )
) -> MemoryDeletionResponseV1:

    if not memory_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="memory_id is required."
        )

    timestamp = datetime.now(timezone.utc)
    correlation_id = IngestionService.new_correlation_id()

    lifecycle_request = MemoryLifecycleRequestV1(
        action=MemoryLifecycleAction.DELETE,
        subject_id=current_subject.subject_id,
        subject_scope=current_subject.subject_id,
        memory_id=memory_id,
        target_memory_id=None,
        effective_at=timestamp,
        reason=request.reason,
        correlation_id=correlation_id,
        metadata={
            **request.metadata,
            "api_surface": "memory_deletion"
        }
    )

    try:
        result = orchestrator.apply_lifecycle_action(
            lifecycle_request
        )

    except OrchestrationError as exc:
        message = str(exc)

        if "was not found" in message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message
            ) from exc

        if "does not belong" in message:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory deletion processing failed."
        ) from exc

    lifecycle_result = result.lifecycle_result

    if lifecycle_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory deletion returned no lifecycle result."
        )

    return MemoryDeletionResponseV1(
        status="accepted",
        subject_id=current_subject.subject_id,
        action=lifecycle_result.action.value,
        memory_id=(
            lifecycle_result.memory_id
            or memory_id
        ),
        memory_status=lifecycle_result.status.value,
        changed=lifecycle_result.changed,
        effective_at=lifecycle_result.effective_at,
        correlation_id=correlation_id,
        reason=lifecycle_result.reason,
        metadata={
            **request.metadata,
            "lifecycle_event_id": (
                lifecycle_result.lifecycle_event_id
            ),
            "deletion_propagation_required": (
                lifecycle_result.audit_metadata.get(
                    "deletion_propagation_required",
                    False
                )
            ),
            "idempotent": (
                lifecycle_result.audit_metadata.get(
                    "idempotent",
                    False
                )
            )
        }
    )