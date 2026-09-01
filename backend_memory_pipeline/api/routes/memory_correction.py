from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,status
from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_control_orchestrator,
    get_session_manager
)
from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    MemoryCorrectionRequestV1,
    MemoryCorrectionResponseV1
)
from backend_memory_pipeline.ingestion.ingestion import IngestionService
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryControlOrchestrator,
    MemoryCorrectionCommandV1,
    OrchestrationError
)
from backend_memory_pipeline.session_management.session_management import (
    SessionManager,
    SessionManagerError,
    SessionStartRequestV1
)
router=APIRouter(
    prefix="/v1",
    tags=["memory-correction"]
)
@router.patch(
    "/memories/{memory_id}",
    response_model=MemoryCorrectionResponseV1,
    responses={
        400:{
            "model":APIErrorResponseV1,
            "description":"Memory correction request was rejected."
        },
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication required."
        },
        403:{
            "model":APIErrorResponseV1,
            "description":"Authenticated subject does not own the target memory."
        },
        404:{
            "model":APIErrorResponseV1,
            "description":"Target memory was not found."
        },
        409:{
            "model":APIErrorResponseV1,
            "description":"Memory correction conflict."
        },
        500:{
            "model":APIErrorResponseV1,
            "description":"Memory correction processing failed."
        }
    }
)
def correct_memory(
    memory_id:str,
    request:MemoryCorrectionRequestV1,
    current_subject:CurrentSubject,
    session_manager:SessionManager=Depends(
        get_session_manager
    ),
    orchestrator:MemoryControlOrchestrator=Depends(
        get_memory_control_orchestrator
    )
)->MemoryCorrectionResponseV1:
    if not memory_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="memory_id is required."
        )
    timestamp=datetime.now(timezone.utc)
    try:
        active_session=session_manager.get_active_session(
            current_subject.subject_id,
            now=timestamp
        )
        if active_session is None:
            session_result=session_manager.start_session(
                SessionStartRequestV1(
                    subject_id=current_subject.subject_id,
                    session_start=timestamp,
                    primary_domain="music",
                    session_context="memory_correction",
                    device_type=None,
                    platform=None,
                    synthetic=False
                )
            )
            session_id=session_result.session.session_id
        else:
            session_id=active_session.session_id
            session_manager.touch_session(
                session_id,
                activity_at=timestamp,
                authorized_subject_id=current_subject.subject_id
            )
    except SessionManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message
        ) from exc
    correlation_id=IngestionService.new_correlation_id()
    command=MemoryCorrectionCommandV1(
        target_memory_id=memory_id,
        corrected_statement=request.corrected_statement,
        subject_id=current_subject.subject_id,
        subject_scope=current_subject.subject_id,
        session_id=session_id,
        surface="memory_correction",
        locale="en-IN",
        effective_at=timestamp,
        reason=request.reason,
        correlation_id=correlation_id,
        metadata={
            **request.metadata,
            "api_surface":"memory_correction"
        }
    )
    try:
        result=orchestrator.process_memory_correction(
            command
        )
    except OrchestrationError as exc:
        message=str(exc)
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
            detail="Memory correction processing failed."
        ) from exc
    lifecycle_result=result.lifecycle_result
    target_memory_id=result.target_memory_id
    corrected_memory_id=(
        lifecycle_result.created_memory_id
        or lifecycle_result.memory_id
    )
    return MemoryCorrectionResponseV1(
        status="accepted",
        subject_id=current_subject.subject_id,
        action=lifecycle_result.action.value,
        target_memory_id=target_memory_id,
        corrected_memory_id=corrected_memory_id,
        corrected_memory_status=lifecycle_result.status.value,
        #previous_memory_status="corrected",
        #current_memory_status=lifecycle_result.status.value,
        changed=lifecycle_result.changed,
        effective_at=lifecycle_result.effective_at,
        correlation_id=command.correlation_id,
        reason=lifecycle_result.reason,
        metadata={
            **request.metadata,
            "lifecycle_event_id":lifecycle_result.lifecycle_event_id,
            "source_event_id":(
                result.extraction.source_event_id
            )
        }
    )