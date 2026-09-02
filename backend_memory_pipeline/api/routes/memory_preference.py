from datetime import datetime,timezone

from fastapi import APIRouter,Depends,HTTPException,status

from backend_memory_pipeline.api.dependencies import (
    CurrentSubject,
    get_memory_write_orchestrator,
    get_session_manager
)

from backend_memory_pipeline.api.schemas import (
    APIErrorResponseV1,
    AddExplicitPreferenceRequestV1,
    AddExplicitPreferenceResponseV1
)

from backend_memory_pipeline.ingestion.ingestion import IngestionService

from backend_memory_pipeline.orchestration.orchestration import (
    MemoryWriteOrchestrator,
    OrchestrationError
)

from backend_memory_pipeline.session_management.session_management import (
    SessionManager,
    SessionManagerError,
    SessionStartRequestV1
)


router=APIRouter(
    prefix="/v1",
    tags=["memory-preference"]
)


@router.post(
    "/memories/preferences",
    response_model=AddExplicitPreferenceResponseV1,
    responses={
        400:{
            "model":APIErrorResponseV1,
            "description":"Explicit preference request was rejected."
        },
        401:{
            "model":APIErrorResponseV1,
            "description":"Authentication required."
        },
        409:{
            "model":APIErrorResponseV1,
            "description":"Explicit preference request conflicts with an existing request."
        },
        500:{
            "model":APIErrorResponseV1,
            "description":"Explicit preference processing failed."
        }
    }
)
def add_explicit_preference(
    request:AddExplicitPreferenceRequestV1,
    current_subject:CurrentSubject,
    session_manager:SessionManager=Depends(
        get_session_manager
    ),
    orchestrator:MemoryWriteOrchestrator=Depends(
        get_memory_write_orchestrator
    )
)->AddExplicitPreferenceResponseV1:

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
                    session_context="memory_explicit_preference",
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

    correlation_id=(
        request.correlation_id
        or IngestionService.new_correlation_id()
    )

    try:
        result=orchestrator.add_explicit_preference(
            subject_id=current_subject.subject_id,
            subject_scope=current_subject.subject_id,
            session_id=session_id,
            preference=request.preference,
            surface=request.surface,
            locale=request.locale,
            effective_at=request.effective_at,
            correlation_id=correlation_id,
            idempotency_key=request.idempotency_key,
            entity=request.entity,
            context_entities=request.context_entities,
            metadata={
                **request.metadata,
                "api_surface":"memory_explicit_preference"
            }
        )

    except OrchestrationError as exc:
        message=str(exc)

        if (
            "already" in message.lower()
            or "duplicate" in message.lower()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Explicit preference processing failed."
        ) from exc

    memory_id=None
    memory_created=False

    if result.lifecycle_results:
        lifecycle_result=result.lifecycle_results[0]

        memory_id=(
            lifecycle_result.created_memory_id
            or lifecycle_result.memory_id
        )

        memory_created=(
            lifecycle_result.changed
            and memory_id is not None
        )

    source_event_id=result.ingestion.event.source_event_id

    if memory_created:
        response_status="accepted"
        message="Explicit preference was stored successfully."
    else:
        response_status="processed"
        message=(
            "Explicit preference was processed but no memory was created."
        )

    return AddExplicitPreferenceResponseV1(
        status=response_status,
        subject_id=current_subject.subject_id,
        memory_id=memory_id,
        memory_created=memory_created,
        source_event_id=source_event_id,
        correlation_id=correlation_id,
        message=message,
        metadata={
            **request.metadata,
            "session_id":session_id,
            "event_id":result.ingestion.event.event_id
        }
    )