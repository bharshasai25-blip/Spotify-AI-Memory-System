from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,status
import hashlib
import json
import uuid
from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_write_orchestrator,
    get_session_manager
)
from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    EventSubmissionRequestV1,
    EventSubmissionResponseV1
)
from backend_memory_pipeline.ingestion.ingestion import (
    ConsentState,
    IngestionService,
    IngestionError
)
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryWriteOrchestrator,
    OrchestrationError
)
from backend_memory_pipeline.session_management.session_management import (
    SessionManager,
    SessionManagerError,
    SessionStartRequestV1
)

def build_deterministic_event_id(
    idempotency_key:str,
    event_payload:dict
)->str:
    canonical_payload=json.dumps(
        event_payload,
        sort_keys=True,
        default=str,
        separators=(",",":")
    )
    payload_hash=hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"spotify-ai-memory:event:{idempotency_key}:{payload_hash}"
        )
    )

router=APIRouter(
    prefix="/v1",
    tags=["events"]
)
@router.post(
    "/events",
    response_model=EventSubmissionResponseV1,
    responses={
        400:{
            "model":APIErrorResponseV1,
            "description":"Event rejected."
        },
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication required."
        },
        409:{
            "model":APIErrorResponseV1,
            "description":"Duplicate event conflict."
        },
        500:{
            "model":APIErrorResponseV1,
            "description":"Event processing failed."
        }
    }
)
def submit_event(
    request:EventSubmissionRequestV1,
    current_subject:CurrentSubject,
    session_manager:SessionManager=Depends(
        get_session_manager
    ),
    orchestrator:MemoryWriteOrchestrator=Depends(
        get_memory_write_orchestrator
    )
)->EventSubmissionResponseV1:
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
                    session_context=request.surface,
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
    idempotency_key=(
    request.idempotency_key
    or IngestionService.new_idempotency_key()
)
    event_identity_payload={
    "event_type":request.event_type.value,
    "surface":request.surface,
    "locale":request.locale,
    "text":request.text,
    "entity":request.entity,
    "context_entities":request.context_entities,
    "metadata":request.metadata
}
    event_id=build_deterministic_event_id(
    idempotency_key,
    event_identity_payload
)
    source_event_id=IngestionService.new_source_event_id()
    correlation_id=IngestionService.new_correlation_id()
    event_data={
        "event_id":event_id,
        "source_event_id":source_event_id,
        "subject_id":current_subject.subject_id,
        "subject_scope":current_subject.subject_id,
        "session_id":session_id,
        "event_type":request.event_type,
        "source":"frontend",
        "surface":request.surface,
        "locale":request.locale,
        "timestamp":timestamp,
        "consent_state":ConsentState.OPTED_IN,
        "idempotency_key":idempotency_key,
        "correlation_id":correlation_id,
        "text":request.text,
        "entity":request.entity,
        "context_entities":request.context_entities,
        "metadata":request.metadata
    }
    try:
        result=orchestrator.process_event(
        event_data,
        authorized_subject_id=current_subject.subject_id
        )
    except OrchestrationError as exc:
        message=str(exc)
        if "Idempotency key is already associated with another event" in message:
          raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key is already associated with another event."
           ) from exc
        if message.startswith("Ingestion failed:"):
          raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message.removeprefix("Ingestion failed:").strip()
           ) from exc
        raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Event processing failed."
        ) from exc    
    except IngestionError as exc:
        raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=exc.message
    ) from exc    
    except ValueError as exc:
        raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc)
        ) from exc
    except Exception as exc:
        '''
        message=str(exc)
        if "Idempotency key is already associated with another event" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key is already associated with another event."
            ) from exc
        '''    
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event processing failed."
        ) from exc
    return EventSubmissionResponseV1(
        status=result.ingestion.status,
        event_id=result.ingestion.event.event_id,
        subject_id=result.ingestion.event.subject_id,
        duplicate=result.ingestion.duplicate,
        correlation_id=result.ingestion.event.correlation_id,
        memory_write_status=(
            "completed"
            if result.lifecycle_results
            else "no_memory_created"
        ),
        metadata={
            "event_type":result.ingestion.event.event_type.value,
            "session_id":session_id,
            "memory_count":len(result.lifecycle_results),
            "graph_result_count":len(result.graph_results),
            "embedding_result_count":len(result.embedding_results)
        }
    )