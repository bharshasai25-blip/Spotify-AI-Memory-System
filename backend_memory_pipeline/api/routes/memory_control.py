from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,status
from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_control_orchestrator
)
from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    MemoryConsentControlRequestV1,
    MemoryConsentControlResponseV1
)
from backend_memory_pipeline.ingestion.ingestion import (
    IngestionService
)
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryControlOrchestrator,
    OrchestrationError
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    PolicyConsentError
)
router=APIRouter(
    prefix="/v1",
    tags=["memory-control"]
)
@router.post(
    "/memory/control",
    response_model=MemoryConsentControlResponseV1,
    responses={
        400:{
            "model":APIErrorResponseV1,
            "description":"Memory consent control request was rejected."
        },
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication required."
        },
        500:{
            "model":APIErrorResponseV1,
            "description":"Memory consent control processing failed."
        }
    }
)
def apply_memory_control(
    request:MemoryConsentControlRequestV1,
    current_subject:CurrentSubject,
    orchestrator:MemoryControlOrchestrator=Depends(
        get_memory_control_orchestrator
    )
)->MemoryConsentControlResponseV1:
    timestamp=datetime.now(timezone.utc)
    correlation_id=IngestionService.new_correlation_id()
    try:
        control_request=ConsentControlRequestV1(
            subject_id=current_subject.subject_id,
            subject_scope=current_subject.subject_id,
            action=request.action,
            timestamp=timestamp,
            correlation_id=correlation_id,
            metadata=request.metadata
        )
        result=orchestrator.apply_consent_control(
            control_request
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc
    except (
        PolicyConsentError,
        OrchestrationError
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory consent control processing failed."
        ) from exc
    consent_result=result.consent_state
    if consent_result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Memory consent control returned no consent result."
        )
    response_metadata=dict(request.metadata)
    response_metadata.update(
        {
            "state_record":{
                "subject_id":consent_result.state_record.subject_id,
                "state":consent_result.state_record.state.value,
                "changed_at":consent_result.state_record.changed_at.isoformat(),
                "last_action":consent_result.state_record.last_action.value,
                "correlation_id":consent_result.state_record.correlation_id
            }
        }
    )
    return MemoryConsentControlResponseV1(
        status="accepted",
        subject_id=consent_result.subject_id,
        action=consent_result.action.value,
        previous_state=consent_result.previous_state.value,
        current_state=consent_result.current_state.value,
        changed=consent_result.changed,
        correlation_id=consent_result.correlation_id,
        timestamp=consent_result.timestamp,
        reason=consent_result.reason,
        metadata=response_metadata
    )