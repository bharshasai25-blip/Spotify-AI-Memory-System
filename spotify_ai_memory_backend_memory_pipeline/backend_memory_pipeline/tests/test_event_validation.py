import pytest
from datetime import datetime,timezone,timedelta
from backend_memory_pipeline.event_validation.event_validation import (
    EventValidationError,
    EventValidationErrorCode,
    EventValidationService,
    EventValidator,
    ValidationStatus
)
from backend_memory_pipeline.ingestion.ingestion import (
    ConsentState,
    EventType,
    InteractionEventV1
)


def make_event(**overrides):
    data={
        "event_id":"EVENT_001",
        "source_event_id":"SOURCE_001",
        "subject_id":"TEST_USER_001",
        "subject_scope":"TEST_USER_001",
        "session_id":"SESSION_001",
        "event_type":EventType.AI_INTERACTION,
        "source":"synthetic_test",
        "surface":"chat",
        "locale":"en-IN",
        "timestamp":datetime(2026,8,24,10,5,0,tzinfo=timezone.utc),
        "consent_state":ConsentState.OPTED_IN,
        "idempotency_key":"IDEMP_001",
        "correlation_id":"CORR_001",
        "text":"I like jazz",
        "entity":None,
        "context_entities":{},
        "metadata":{}
    }
    data.update(overrides)
    data.update(overrides)
    event_metadata=dict(data.get("metadata") or {})
    if data["event_type"]==EventType.PLAYBACK:
        event_metadata.setdefault("playback_action","play")
    data["metadata"]=event_metadata
    return InteractionEventV1(**data)

def test_valid_ai_interaction_is_accepted():
    validator=EventValidator()
    event=make_event()
    result=validator.validate(event)
    assert result.status==ValidationStatus.VALID
    assert result.safe_for_extraction is True
    assert result.errors==[]

def test_valid_event_validation_service():
    service=EventValidationService()
    event=make_event()
    result=service.validate(event)
    assert result.status==ValidationStatus.VALID
    assert result.event_id=="EVENT_001"

def test_subject_scope_mismatch_is_rejected():
    validator=EventValidator()
    event=make_event(subject_scope="OTHER_USER_001")
    result=validator.validate(event)
    assert result.status==ValidationStatus.REJECTED
    assert result.safe_for_extraction is False
    assert "Subject scope does not match event subject." in result.errors

def test_missing_subject_is_rejected():
    validator=EventValidator()
    with pytest.raises(ValueError):
        make_event(subject_id="")

def test_missing_subject_scope_is_rejected():
    validator=EventValidator()
    with pytest.raises(ValueError):
        make_event(subject_scope="")

def test_unsupported_schema_version_is_rejected():
    validator=EventValidator()
    event=make_event()
    event_copy=event.model_copy(update={"schema_version":"9.9"})
    result=validator.validate(event_copy)
    assert result.status==ValidationStatus.REJECTED
    assert "Unsupported schema version." in result.errors

def test_invalid_timestamp_is_rejected():
    validator=EventValidator()
    event=make_event()
    naive_timestamp=datetime(2026,8,24,10,5,0)
    event_copy=event.model_copy(update={"timestamp":naive_timestamp})
    result=validator.validate(event_copy)
    assert result.status==ValidationStatus.REJECTED
    assert "Event timestamp must be timezone-aware." in result.errors

def test_ai_interaction_requires_text():
    with pytest.raises(ValueError,match="text is required for ai_interaction events"):
        make_event(text=None)

def test_empty_ai_text_is_rejected_by_contract():
    with pytest.raises(ValueError):
        make_event(text="   ")

def test_non_ai_event_can_omit_text():
    validator=EventValidator()
    event=make_event(
        event_type=EventType.PLAYBACK,
        text=None
    )
    result=validator.validate(event)
    assert result.status==ValidationStatus.VALID
    assert result.safe_for_extraction is True

def test_all_supported_event_types_are_accepted():
    validator=EventValidator()
    for event_type in EventType:
        text="interaction text" if event_type==EventType.AI_INTERACTION else None
        event=make_event(
            event_type=event_type,
            text=text
        )
        result=validator.validate(event)
        assert result.status==ValidationStatus.VALID

def test_all_supported_consent_states_are_accepted():
    validator=EventValidator()
    for consent_state in ConsentState:
        event=make_event(
            consent_state=consent_state
        )
        result=validator.validate(event)
        assert result.status==ValidationStatus.VALID

def test_missing_source_is_rejected():
    validator=EventValidator()
    with pytest.raises(ValueError):
        make_event(source="")

def test_missing_locale_is_rejected():
    validator=EventValidator()
    with pytest.raises(ValueError):
        make_event(locale="")

def test_invalid_entity_field_is_rejected():
    validator=EventValidator()
    event=make_event(
        entity={
            "entity_id":"TRACK_001",
            "unsupported_field":"bad"
        }
    )
    result=validator.validate(event)
    assert result.status==ValidationStatus.REJECTED
    assert any("Unsupported entity fields" in error for error in result.errors)

def test_invalid_entity_confidence_is_rejected():
    validator=EventValidator()
    event=make_event(
        entity={
            "entity_id":"TRACK_001",
            "entity_type":"track",
            "confidence":1.5
        }
    )
    result=validator.validate(event)
    assert result.status==ValidationStatus.REJECTED
    assert "Entity confidence must be between 0 and 1." in result.errors

def test_valid_entity_is_accepted():
    validator=EventValidator()
    event=make_event(
        entity={
            "entity_id":"TRACK_001",
            "entity_type":"track",
            "name":"Example Track",
            "canonical_id":"TRACK_001",
            "source":"catalog",
            "confidence":0.98
        }
    )
    result=validator.validate(event)
    assert result.status==ValidationStatus.VALID

def test_invalid_context_entities_are_rejected():
    validator=EventValidator()
    event=make_event()
    object.__setattr__(event,"context_entities",[])
    result=validator.validate(event)
    assert result.status==ValidationStatus.REJECTED
    assert "context_entities must be an object." in result.errors

def test_invalid_metadata_is_rejected():
    validator=EventValidator()
    event=make_event()
    object.__setattr__(
        event,
        "metadata",
        {"access_token":"secret-value"}
    )
    result=validator.validate(event)
    assert result.status==ValidationStatus.REJECTED
    assert any(
        "Sensitive credential fields" in error
        for error in result.errors
    )

def test_large_metadata_produces_warning():
    validator=EventValidator()
    large_metadata={f"field_{i}":i for i in range(101)}
    event=make_event(metadata=large_metadata)
    result=validator.validate(event)
    assert result.status==ValidationStatus.VALID
    assert any(
        "large number of fields" in warning
        for warning in result.warnings
    )

def test_long_text_is_rejected():
    validator=EventValidator()
    event=make_event(text="x"*50001)
    result=validator.validate(event)
    assert result.status==ValidationStatus.REJECTED
    assert "Event text exceeds maximum supported length." in result.errors

def test_validate_or_raise_accepts_valid_event():
    service=EventValidationService()
    event=make_event()
    result=service.validate_or_raise(event)
    assert result.status==ValidationStatus.VALID

def test_validate_or_raise_rejects_invalid_event():
    service=EventValidationService()
    event=make_event(subject_scope="OTHER_USER_001")
    with pytest.raises(EventValidationError) as exc:
        service.validate_or_raise(event)
    assert exc.value.code==EventValidationErrorCode.INVALID_EVENT

def test_validator_rejects_non_event_input():
    validator=EventValidator()
    with pytest.raises(EventValidationError) as exc:
        validator.validate({"user_id":"TEST_USER_001"})
    assert exc.value.code==EventValidationErrorCode.INVALID_EVENT

def test_result_contains_subject_and_event_type():
    validator=EventValidator()
    event=make_event()
    result=validator.validate(event)
    assert result.subject_id==event.subject_id
    assert result.event_type==event.event_type

def test_validation_is_deterministic():
    validator=EventValidator()
    event=make_event()
    result_one=validator.validate(event)
    result_two=validator.validate(event)
    assert result_one.model_dump()==result_two.model_dump()