import pytest
from datetime import datetime,timezone,timedelta
from backend_memory_pipeline.ingestion.ingestion import (
    ConsentState,
    EventType,
    IngestionEnvelopeV1,
    IngestionError,
    IngestionErrorCode,
    IngestionService,
    InMemoryIdempotencyStore,
    InteractionEventV1,
    MemoryControlAction,
    MemoryControlEventV1,
    SessionRecordV1
)
from backend_memory_pipeline.api.schemas import EventSubmissionRequestV1
def make_session(user_id="TEST_USER_001",session_id="SESSION_001",start=None):
    start=start or datetime(2026,8,24,10,0,0,tzinfo=timezone.utc)
    end=start+timedelta(minutes=30)
    return SessionRecordV1(
        session_id=session_id,
        user_id=user_id,
        session_start=start,
        session_end=end,
        session_duration_seconds=1800,
        primary_domain="music",
        session_context="general",
        device_type="mobile",
        platform="app"
    )
def make_event(user_id="TEST_USER_001",session_id="SESSION_001",event_type=EventType.AI_INTERACTION,event_timestamp=None,event_id="EVENT_001",idempotency_key="IDEMP_001",text="I like jazz",consent_state=ConsentState.OPTED_IN,source="synthetic_test",metadata=None):
    session=make_session(user_id,session_id)
    return InteractionEventV1(
        event_id=event_id,
        source_event_id=f"SRC_{event_id}",
        subject_id=user_id,
        subject_scope=user_id,
        session_id=session_id,
        event_type=event_type,
        source=source,
        surface="chat",
        locale="en-IN",
        timestamp=event_timestamp or session.session_start+timedelta(minutes=5),
        consent_state=consent_state,
        idempotency_key=idempotency_key,
        correlation_id=f"CORR_{event_id}",
        text=text,
        metadata=metadata or {}
    )
def test_valid_session_record():
    session=make_session()
    assert session.session_id=="SESSION_001"
    assert session.user_id=="TEST_USER_001"
    assert session.session_duration_seconds==1800
def test_session_end_must_follow_start():
    start=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match="session_end must be after session_start"):
        SessionRecordV1(
            session_id="SESSION_001",
            user_id="TEST_USER_001",
            session_start=start,
            session_end=start,
            session_duration_seconds=0
        )
def test_session_duration_must_match_interval():
    start=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc)
    end=start+timedelta(minutes=30)
    with pytest.raises(ValueError,match="session_duration_seconds does not match"):
        SessionRecordV1(
            session_id="SESSION_001",
            user_id="TEST_USER_001",
            session_start=start,
            session_end=end,
            session_duration_seconds=100
        )
def test_session_timestamps_must_be_timezone_aware():
    start=datetime(2026,8,24,10,0,0)
    end=start+timedelta(minutes=30)
    with pytest.raises(ValueError,match="session_start must be timezone-aware"):
        SessionRecordV1(
            session_id="SESSION_001",
            user_id="TEST_USER_001",
            session_start=start,
            session_end=end,
            session_duration_seconds=1800
        )
def test_valid_interaction_event():
    event=make_event()
    assert event.event_type==EventType.AI_INTERACTION
    assert event.subject_id=="TEST_USER_001"
    assert event.consent_state==ConsentState.OPTED_IN
def test_event_timestamp_must_be_timezone_aware():
    session=make_session()
    with pytest.raises(ValueError,match="timestamp must be timezone-aware"):
        InteractionEventV1(
            event_id="EVENT_001",
            source_event_id="SRC_EVENT_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id=session.session_id,
            event_type=EventType.AI_INTERACTION,
            source="synthetic_test",
            surface="chat",
            locale="en-IN",
            timestamp=datetime(2026,8,24,10,5,0),
            consent_state=ConsentState.OPTED_IN,
            idempotency_key="IDEMP_001",
            correlation_id="CORR_001",
            text="I like jazz"
        )
def test_ai_interaction_requires_text():
    session=make_session()
    with pytest.raises(ValueError,match="text is required for ai_interaction events"):
        InteractionEventV1(
            event_id="EVENT_001",
            source_event_id="SRC_EVENT_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id=session.session_id,
            event_type=EventType.AI_INTERACTION,
            source="synthetic_test",
            surface="chat",
            locale="en-IN",
            timestamp=session.session_start+timedelta(minutes=5),
            consent_state=ConsentState.OPTED_IN,
            idempotency_key="IDEMP_001",
            correlation_id="CORR_001"
        )

def test_playback_event_accepts_play_action():
    event=make_event(
        event_type=EventType.PLAYBACK,
        metadata={"playback_action":"play"}
    )
    assert event.event_type==EventType.PLAYBACK
def test_playback_event_accepts_pause_action():
    event=make_event(
        event_type=EventType.PLAYBACK,
        metadata={"playback_action":"pause"}
    )
    assert event.event_type==EventType.PLAYBACK
def test_playback_event_rejects_invalid_playback_action():
    with pytest.raises(ValueError,match="playback_action must be play or pause for playback events"):
        make_event(
            event_type=EventType.PLAYBACK,
            metadata={"playback_action":"stop"}
        )

def test_save_event_is_accepted():
    event=make_event(
        event_type=EventType.SAVE
    )
    assert event.event_type==EventType.SAVE

def test_follow_event_is_accepted():
    event=make_event(
        event_type=EventType.FOLLOW
    )
    assert event.event_type==EventType.FOLLOW

def test_skip_event_is_accepted():
    event=make_event(
        event_type=EventType.SKIP
    )
    assert event.event_type==EventType.SKIP        
        
def test_empty_text_is_rejected():
    with pytest.raises(ValueError,match="text cannot be empty"):
        make_event(text="   ")
def test_ingestion_accepts_valid_envelope():
    service=IngestionService()
    event=make_event()
    session=make_session()
    envelope=IngestionEnvelopeV1(event=event,session=session)
    result=service.ingest(envelope,authorized_subject_id="TEST_USER_001")
    assert result.status=="accepted"
    assert result.duplicate is False
    assert result.event.event_id=="EVENT_001"
def test_ingestion_rejects_subject_mismatch():
    service=IngestionService()
    event=make_event()
    session=make_session()
    envelope=IngestionEnvelopeV1(event=event,session=session)
    with pytest.raises(IngestionError,match="Authenticated subject does not match event subject"):
        service.ingest(envelope,authorized_subject_id="TEST_USER_999")
def test_ingestion_rejects_session_id_mismatch():
    service=IngestionService()
    event=make_event(session_id="SESSION_001")
    wrong_session=make_session(session_id="SESSION_999")
    envelope=IngestionEnvelopeV1(event=event,session=wrong_session)
    with pytest.raises(IngestionError) as exc:
        service.ingest(envelope)
    assert exc.value.code==IngestionErrorCode.INVALID_SESSION
def test_ingestion_rejects_session_user_mismatch():
    service=IngestionService()
    event=make_event(user_id="TEST_USER_001")
    wrong_session=make_session(user_id="TEST_USER_999")
    envelope=IngestionEnvelopeV1(event=event,session=wrong_session)
    with pytest.raises(IngestionError) as exc:
        service.ingest(envelope)
    assert exc.value.code==IngestionErrorCode.INVALID_SESSION
def test_ingestion_rejects_event_outside_session():
    service=IngestionService()
    session=make_session()
    event=make_event(event_timestamp=session.session_end+timedelta(seconds=1))
    envelope=IngestionEnvelopeV1(event=event,session=session)
    with pytest.raises(IngestionError,match="Event timestamp falls outside the session interval"):
        service.ingest(envelope)
def test_ingestion_without_session_record_is_allowed():
    service=IngestionService()
    event=make_event()
    envelope=IngestionEnvelopeV1(event=event,session=None)
    result=service.ingest(envelope,authorized_subject_id="TEST_USER_001")
    assert result.status=="accepted"
def test_duplicate_same_event_is_idempotent():
    store=InMemoryIdempotencyStore()
    service=IngestionService(store)
    event=make_event()
    session=make_session()
    envelope=IngestionEnvelopeV1(event=event,session=session)
    first=service.ingest(envelope)
    second=service.ingest(envelope)
    assert first.status=="accepted"
    assert second.status=="duplicate"
    assert second.duplicate is True
def test_duplicate_idempotency_key_with_different_event_is_rejected():
    store=InMemoryIdempotencyStore()
    service=IngestionService(store)
    event1=make_event(event_id="EVENT_001",idempotency_key="SAME_KEY")
    event2=make_event(event_id="EVENT_002",idempotency_key="SAME_KEY")
    session=make_session()
    service.ingest(IngestionEnvelopeV1(event=event1,session=session))
    with pytest.raises(IngestionError) as exc:
        service.ingest(IngestionEnvelopeV1(event=event2,session=session))
    assert exc.value.code==IngestionErrorCode.DUPLICATE_EVENT
def test_ingest_mapping_accepts_valid_synthetic_style_event():
    service=IngestionService()
    session=make_session()
    payload={
        "source_event_id":"SRC_EVENT_100",
        "subject_id":"TEST_USER_001",
        "subject_scope":"TEST_USER_001",
        "session_id":"SESSION_001",
        "event_type":"ai_interaction",
        "source":"synthetic_test",
        "surface":"chat",
        "locale":"en-IN",
        "timestamp":"2026-08-24T10:05:00+00:00",
        "consent_state":"opted_in",
        "idempotency_key":"IDEMP_100",
        "correlation_id":"CORR_100",
        "text":"I like jazz",
        "session":session.model_dump()
    }
    result=service.ingest_mapping(payload,authorized_subject_id="TEST_USER_001")
    assert result.status=="accepted"
    assert result.event.subject_id=="TEST_USER_001"
    assert result.session.session_id=="SESSION_001"
def test_ingest_mapping_rejects_non_mapping():
    service=IngestionService()
    with pytest.raises(IngestionError,match="Ingestion input must be a mapping"):
        service.ingest_mapping(["invalid"])
def test_invalid_event_type_is_rejected():
    with pytest.raises(ValueError):
        make_event(event_type="unsupported")
def test_invalid_consent_state_is_rejected():
    with pytest.raises(ValueError):
        make_event(consent_state="invalid")
'''        
def test_memory_control_delete_requires_memory_id():
    with pytest.raises(ValueError,match="memory_id is required"):
        MemoryControlEventV1(
            control_event_id="CONTROL_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            action=MemoryControlAction.DELETE,
            source_event_id="SRC_CONTROL_001",
            idempotency_key="CONTROL_KEY_001",
            timestamp=datetime(2026,8,24,10,5,0,tzinfo=timezone.utc),
            correlation_id="CORR_CONTROL_001",
            source="synthetic_test",
            surface="chat",
            locale="en-IN"
        )
def test_memory_control_correct_requires_memory_id():
    with pytest.raises(ValueError,match="memory_id is required"):
        MemoryControlEventV1(
            control_event_id="CONTROL_002",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            action=MemoryControlAction.CORRECT,
            source_event_id="SRC_CONTROL_002",
            idempotency_key="CONTROL_KEY_002",
            timestamp=datetime(2026,8,24,10,5,0,tzinfo=timezone.utc),
            correlation_id="CORR_CONTROL_002",
            source="synthetic_test",
            surface="chat",
            locale="en-IN"
        )
def test_memory_control_delete_is_valid():
    control=MemoryControlEventV1(
        control_event_id="CONTROL_003",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.DELETE,
        memory_id="MEMORY_001",
        source_event_id="SRC_CONTROL_003",
        idempotency_key="CONTROL_KEY_003",
        timestamp=datetime(2026,8,24,10,5,0,tzinfo=timezone.utc),
        correlation_id="CORR_CONTROL_003",
        source="synthetic_test",
        surface="chat",
        locale="en-IN"
    )
    assert control.action==MemoryControlAction.DELETE
    assert control.memory_id=="MEMORY_001"
   
def test_memory_control_opt_out_does_not_require_memory_id():
    control=MemoryControlEventV1(
        control_event_id="CONTROL_004",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_OUT,
        source_event_id="SRC_CONTROL_004",
        idempotency_key="CONTROL_KEY_004",
        timestamp=datetime(2026,8,24,10,5,0,tzinfo=timezone.utc),
        correlation_id="CORR_CONTROL_004",
        source="synthetic_test",
        surface="chat",
        locale="en-IN"
    )
    assert control.action==MemoryControlAction.OPT_OUT
'''    
def test_memory_control_opt_out_is_valid():
    control=MemoryControlEventV1(
        control_event_id="CONTROL_004",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_OUT,
        source_event_id="SRC_CONTROL_004",
        idempotency_key="CONTROL_KEY_004",
        timestamp=datetime(
            2026,8,24,10,5,0,
            tzinfo=timezone.utc
        ),
        correlation_id="CORR_CONTROL_004",
        source="synthetic_test",
        surface="chat",
        locale="en-IN"
    )

    assert control.action==MemoryControlAction.OPT_OUT
def test_memory_control_opt_in_is_valid():
    control=MemoryControlEventV1(
        control_event_id="CONTROL_005",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        source_event_id="SRC_CONTROL_005",
        idempotency_key="CONTROL_KEY_005",
        timestamp=datetime(
            2026,8,24,10,5,0,
            tzinfo=timezone.utc
        ),
        correlation_id="CORR_CONTROL_005",
        source="synthetic_test",
        surface="chat",
        locale="en-IN"
    )

    assert control.action==MemoryControlAction.OPT_IN


def test_memory_control_pause_is_valid():
    control=MemoryControlEventV1(
        control_event_id="CONTROL_006",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.PAUSE,
        source_event_id="SRC_CONTROL_006",
        idempotency_key="CONTROL_KEY_006",
        timestamp=datetime(
            2026,8,24,10,5,0,
            tzinfo=timezone.utc
        ),
        correlation_id="CORR_CONTROL_006",
        source="synthetic_test",
        surface="chat",
        locale="en-IN"
    )

    assert control.action==MemoryControlAction.PAUSE


def test_memory_control_resume_is_valid():
    control=MemoryControlEventV1(
        control_event_id="CONTROL_007",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.RESUME,
        source_event_id="SRC_CONTROL_007",
        idempotency_key="CONTROL_KEY_007",
        timestamp=datetime(
            2026,8,24,10,5,0,
            tzinfo=timezone.utc
        ),
        correlation_id="CORR_CONTROL_007",
        source="synthetic_test",
        surface="chat",
        locale="en-IN"
    )

    assert control.action==MemoryControlAction.RESUME        
def test_generated_identifiers_are_unique():
    service=IngestionService()
    event_ids={service.new_event_id() for _ in range(100)}
    source_ids={service.new_source_event_id() for _ in range(100)}
    correlation_ids={service.new_correlation_id() for _ in range(100)}
    idempotency_keys={service.new_idempotency_key() for _ in range(100)}
    assert len(event_ids)==100
    assert len(source_ids)==100
    assert len(correlation_ids)==100
    assert len(idempotency_keys)==100
def test_memory_control_rejects_subject_scope_mismatch():
    with pytest.raises(
        ValueError,
        match="subject_scope must match subject_id"
    ):
        MemoryControlEventV1(
            control_event_id="CONTROL_005",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            action=MemoryControlAction.OPT_OUT,
            source_event_id="SRC_CONTROL_005",
            idempotency_key="CONTROL_KEY_005",
            timestamp=datetime(
                2026,8,24,10,5,0,
                tzinfo=timezone.utc
            ),
            correlation_id="CORR_CONTROL_005",
            source="synthetic_test",
            surface="chat",
            locale="en-IN"
        )    