import pytest
from datetime import datetime,timezone

from backend_memory_pipeline.entity_resolution.entity_resolution import (
    EntityResolutionResultV1,
    EntityResolutionStatus
)
from backend_memory_pipeline.ingestion.ingestion import ConsentState,EventType
from backend_memory_pipeline.memory_extraction.memory_extraction import (
    ExtractedEntityMention,
    ExtractedMemoryCandidate,
    ExtractionDecision,
    MemoryType,
    PolicyClass,
    TemporalScope
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    ConsentControlService,
    ConsentDecision,
    ConsentStateRecordV1,
    DefaultPolicyEngine,
    InMemoryConsentStateStore,
    MemoryControlAction,
    PolicyConsentError,
    PolicyConsentService,
    PolicyDecisionType,
    PolicyErrorCode,
    PolicyRegistryEntryV1,
    PolicyRequestV1,
    RetentionClass,
    SensitivityLevel
)
def make_candidate(
    candidate_id="CANDIDATE_001",
    subject_id="TEST_USER_001",
    memory_type=MemoryType.EXPLICIT_PREFERENCE,
    policy_class=PolicyClass.STANDARD,
    policy_flags=None,
    evidence_count=1,
    entities=None
):
    return ExtractedMemoryCandidate(
        candidate_id=candidate_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        source_event_id="SOURCE_001",
        source_event_ids=["SOURCE_001"],
        source_session_ids=["SESSION_001"],
        source_event_type=EventType.AI_INTERACTION,
        memory_type=memory_type,
        decision=ExtractionDecision.MEMORY_CANDIDATE,
        normalized_fact="User prefers calm acoustic music.",
        evidence_texts=["I prefer calm acoustic music."],
        entities=entities or [],
        confidence=0.95,
        relevance_score=None,
        temporal_scope=TemporalScope.PERSISTENT,
        policy_class=policy_class,
        policy_flags=policy_flags or [],
        reason="Test memory candidate.",
        evidence_count=evidence_count,
        explicit_evidence_count=1,
        behavioral_evidence_count=0
    )
def make_request(
    subject_id="TEST_USER_001",
    consent_state=ConsentState.OPTED_IN,
    purpose="personalization",
    surface="chat",
    locale="en-IN",
    geography=None,
    age_band=None,
    age_related_handling=None,
    requested_retention=None,
    retrieval_requested=True,
    embedding_requested=True
):
    return PolicyRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        purpose=purpose,
        surface=surface,
        locale=locale,
        consent_state=consent_state,
        geography=geography,
        age_band=age_band,
        age_related_handling=age_related_handling,
        requested_retention=requested_retention,
        retrieval_requested=retrieval_requested,
        embedding_requested=embedding_requested
    )
def make_entity_result(
    candidate_id="CANDIDATE_001",
    subject_id="TEST_USER_001",
    status=EntityResolutionStatus.RESOLVED
):
    return EntityResolutionResultV1(
        candidate_id=candidate_id,
        subject_id=subject_id,
        resolved_entities=[],
        resolution_status=status,
        unresolved_mentions=[],
        ambiguous_mentions=[]
    )

def make_control_request(
    subject_id="TEST_USER_001",
    action=MemoryControlAction.OPT_IN,
    timestamp=None,
    correlation_id="CONTROL_CORR_001"
):
    return ConsentControlRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        action=action,
        timestamp=timestamp or datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
        correlation_id=correlation_id
    )
    
def test_standard_explicit_preference_is_allowed():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
    assert result.consent_decision==ConsentDecision.ALLOWED
    assert result.sensitivity==SensitivityLevel.STANDARD
    assert result.retrieval_eligible is True
    assert result.embedding_eligible is True
    assert result.denied_reasons==[]
def test_opted_out_subject_is_denied():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request(consent_state=ConsentState.OPTED_OUT)
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.consent_decision==ConsentDecision.DENIED
    assert result.retrieval_eligible is False
    assert result.embedding_eligible is False
def test_paused_subject_is_denied():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request(consent_state=ConsentState.PAUSED)
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.consent_decision==ConsentDecision.PAUSED
    assert result.retrieval_eligible is False
    assert result.embedding_eligible is False
def test_unknown_consent_is_denied():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request(consent_state=ConsentState.UNKNOWN)
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.consent_decision==ConsentDecision.UNKNOWN
def test_not_applicable_consent_is_not_automatically_allowed():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request(consent_state=ConsentState.NOT_APPLICABLE)
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.consent_decision==ConsentDecision.UNKNOWN
def test_subject_scope_mismatch_is_rejected():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(subject_id="TEST_USER_001")
    request=make_request(subject_id="TEST_USER_002")
    with pytest.raises(PolicyConsentError) as exc:
        engine.evaluate(candidate,request)
    assert exc.value.code==PolicyErrorCode.INVALID_POLICY_INPUT
def test_sensitive_candidate_is_reviewed_when_policy_allows_review():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            sensitivity=SensitivityLevel.SENSITIVE,
            retention_class=RetentionClass.STANDARD,
            retrieval_eligible=True,
            embedding_eligible=False,
            requires_review=True
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate(
        policy_class=PolicyClass.SENSITIVE,
        policy_flags=["sensitive_inference"]
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.REVIEW
    assert result.sensitivity==SensitivityLevel.SENSITIVE
    assert "sensitive_memory" in result.policy_flags
    assert result.embedding_eligible is False
def test_prohibited_candidate_is_denied():
    candidate=make_candidate(policy_class=PolicyClass.PROHIBITED)
    engine=DefaultPolicyEngine()
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.sensitivity==SensitivityLevel.PROHIBITED
    assert result.retrieval_eligible is False
    assert result.embedding_eligible is False
def test_unregistered_memory_type_is_denied():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate(memory_type=MemoryType.CANDIDATE_PREFERENCE)
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.sensitivity==SensitivityLevel.PROHIBITED
def test_correction_signal_is_not_retrievable_memory():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        memory_type=MemoryType.CORRECTION_SIGNAL
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.retrieval_eligible is False
    assert result.embedding_eligible is False
def test_non_memory_is_denied():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        memory_type=MemoryType.NON_MEMORY
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.retrieval_eligible is False
def test_candidate_preference_with_insufficient_evidence_is_reviewed():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        memory_type=MemoryType.CANDIDATE_PREFERENCE,
        evidence_count=1,
        policy_flags=["behavioral_inference"]
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.REVIEW
    assert "insufficient_behavioral_evidence" in result.policy_flags
def test_candidate_preference_with_sufficient_evidence_can_be_allowed():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        memory_type=MemoryType.CANDIDATE_PREFERENCE,
        evidence_count=3,
        policy_flags=["behavioral_inference"]
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
    assert result.retrieval_eligible is True
    assert result.embedding_eligible is True
def test_ambiguous_entity_requires_review():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        entities=[
            ExtractedEntityMention(
                mention="Focus",
                entity_type="artist"
            )
        ]
    )
    entity_result=make_entity_result(
        status=EntityResolutionStatus.AMBIGUOUS
    )
    request=make_request()
    result=engine.evaluate(candidate,request,entity_result)
    assert result.decision==PolicyDecisionType.REVIEW
    assert "ambiguous_entity" in result.policy_flags
    assert result.retrieval_eligible is False
    assert result.embedding_eligible is False
def test_unresolved_entity_requires_review():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        entities=[
            ExtractedEntityMention(
                mention="Unknown Artist",
                entity_type="artist"
            )
        ]
    )
    entity_result=make_entity_result(
        status=EntityResolutionStatus.UNRESOLVED
    )
    request=make_request()
    result=engine.evaluate(candidate,request,entity_result)
    assert result.decision==PolicyDecisionType.REVIEW
    assert "unresolved_entity" in result.policy_flags
def test_rejected_entity_causes_policy_denial():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        entities=[
            ExtractedEntityMention(
                mention="Private Playlist",
                entity_type="playlist"
            )
        ]
    )
    entity_result=make_entity_result(
        status=EntityResolutionStatus.REJECTED
    )
    request=make_request()
    result=engine.evaluate(candidate,request,entity_result)
    assert result.decision==PolicyDecisionType.DENY
    assert any(
        "Entity resolution rejected" in reason
        for reason in result.denied_reasons
    )
def test_allowed_purpose_is_required_when_registry_restricts_purpose():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            allowed_purposes=["personalization"]
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate()
    request=make_request(purpose="analytics")
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert any(
        "purpose" in reason.lower()
        for reason in result.denied_reasons
    )
def test_allowed_geography_is_enforced():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            allowed_geographies=["IN"]
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate()
    request=make_request(geography="US")
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert any(
        "geography" in reason.lower()
        for reason in result.denied_reasons
    )
def test_age_related_policy_requires_required_inputs():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            age_restricted=True
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate()
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert any(
        "Age-related" in reason
        for reason in result.denied_reasons
    )
def test_age_related_policy_can_allow_when_approved():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            age_restricted=True
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate()
    request=make_request(
        age_band="adult",
        age_related_handling="approved"
    )
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
def test_requested_retention_cannot_exceed_policy():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            retention_class=RetentionClass.STANDARD
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate()
    request=make_request(
        requested_retention=RetentionClass.LONG
    )
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.retention_class==RetentionClass.STANDARD
    assert any(
        "retention" in reason.lower()
        for reason in result.denied_reasons
    )
def test_requested_shorter_retention_is_allowed():
    registry=[
        PolicyRegistryEntryV1(
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            allowed=True,
            retention_class=RetentionClass.LONG
        )
    ]
    engine=DefaultPolicyEngine(registry=registry)
    candidate=make_candidate()
    request=make_request(
        requested_retention=RetentionClass.SHORT
    )
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
    assert result.retention_class==RetentionClass.SHORT
def test_embedding_can_be_disabled_by_request():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request(embedding_requested=False)
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
    assert result.embedding_eligible is False
    assert result.retrieval_eligible is True
def test_retrieval_can_be_disabled_by_request():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request(retrieval_requested=False)
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
    assert result.retrieval_eligible is False
    assert result.embedding_eligible is True
def test_episode_is_allowed_by_default():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        memory_type=MemoryType.EPISODE
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
def test_exclusion_is_allowed_by_default():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(
        memory_type=MemoryType.EXCLUSION
    )
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
def test_policy_decision_contains_policy_version():
    engine=DefaultPolicyEngine(policy_version="2.1")
    candidate=make_candidate()
    request=make_request()
    result=engine.evaluate(candidate,request)
    assert result.policy_version=="2.1"
def test_service_delegates_to_engine():
    service=PolicyConsentService()
    candidate=make_candidate()
    request=make_request()
    result=service.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.ALLOW
def test_invalid_candidate_type_is_rejected():
    engine=DefaultPolicyEngine()
    request=make_request()
    with pytest.raises(PolicyConsentError) as exc:
        engine.evaluate({"candidate_id":"bad"},request)
    assert exc.value.code==PolicyErrorCode.INVALID_CANDIDATE
def test_invalid_policy_request_type_is_rejected():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    with pytest.raises(PolicyConsentError) as exc:
        engine.evaluate(candidate,{"subject_id":"TEST_USER_001"})
    assert exc.value.code==PolicyErrorCode.INVALID_POLICY_INPUT
def test_subject_scope_mismatch_between_candidate_and_request_is_rejected():
    engine=DefaultPolicyEngine()
    candidate=make_candidate(subject_id="TEST_USER_001")
    request=make_request(subject_id="TEST_USER_002")
    with pytest.raises(PolicyConsentError) as exc:
        engine.evaluate(candidate,request)
    assert exc.value.code==PolicyErrorCode.INVALID_POLICY_INPUT
def test_policy_is_deterministic():
    engine=DefaultPolicyEngine()
    candidate=make_candidate()
    request=make_request()
    result_one=engine.evaluate(candidate,request)
    result_two=engine.evaluate(candidate,request)
    assert result_one.model_dump()==result_two.model_dump()


def test_consent_control_opt_in_from_unknown():
    service=ConsentControlService()
    result=service.apply(
        make_control_request(
            action=MemoryControlAction.OPT_IN
        )
    )
    assert result.action==MemoryControlAction.OPT_IN
    assert result.previous_state==ConsentState.UNKNOWN
    assert result.current_state==ConsentState.OPTED_IN
    assert result.changed is True

def test_consent_control_opt_out_from_opted_in():
    service=ConsentControlService(default_state=ConsentState.OPTED_IN)
    result=service.apply(
        make_control_request(
            action=MemoryControlAction.OPT_OUT
        )
    )
    assert result.previous_state==ConsentState.OPTED_IN
    assert result.current_state==ConsentState.OPTED_OUT
    assert result.changed is True

def test_consent_control_pause_from_opted_in():
    service=ConsentControlService(default_state=ConsentState.OPTED_IN)
    result=service.apply(
        make_control_request(
            action=MemoryControlAction.PAUSE
        )
    )
    assert result.previous_state==ConsentState.OPTED_IN
    assert result.current_state==ConsentState.PAUSED
    assert result.changed is True

def test_consent_control_resume_from_paused():
    store=InMemoryConsentStateStore()
    service=ConsentControlService(store,default_state=ConsentState.OPTED_IN)
    pause_result=service.apply(
        make_control_request(
            action=MemoryControlAction.PAUSE,
            correlation_id="CONTROL_PAUSE"
        )
    )
    assert pause_result.current_state==ConsentState.PAUSED
    resume_result=service.apply(
        make_control_request(
            action=MemoryControlAction.RESUME,
            correlation_id="CONTROL_RESUME"
        )
    )
    assert resume_result.previous_state==ConsentState.PAUSED
    assert resume_result.current_state==ConsentState.OPTED_IN
    assert resume_result.changed is True

def test_opt_in_after_opt_out_is_reconsent():
    store=InMemoryConsentStateStore()
    service=ConsentControlService(store,default_state=ConsentState.OPTED_IN)
    opt_out=service.apply(
        make_control_request(
            action=MemoryControlAction.OPT_OUT,
            correlation_id="CONTROL_OPT_OUT"
        )
    )
    assert opt_out.current_state==ConsentState.OPTED_OUT
    opt_in=service.apply(
        make_control_request(
            action=MemoryControlAction.OPT_IN,
            correlation_id="CONTROL_OPT_IN"
        )
    )
    assert opt_in.previous_state==ConsentState.OPTED_OUT
    assert opt_in.current_state==ConsentState.OPTED_IN
    assert opt_in.changed is True

def test_resume_is_not_valid_after_opt_out():
    service=ConsentControlService(default_state=ConsentState.OPTED_OUT)
    with pytest.raises(PolicyConsentError) as exc:
        service.apply(
            make_control_request(
                action=MemoryControlAction.RESUME
            )
        )
    assert exc.value.code==PolicyErrorCode.INVALID_CONTROL_TRANSITION
def test_resume_is_not_valid_when_already_opted_in():
    service=ConsentControlService(default_state=ConsentState.OPTED_IN)
    with pytest.raises(PolicyConsentError) as exc:
        service.apply(
            make_control_request(
                action=MemoryControlAction.RESUME
            )
        )
    assert exc.value.code==PolicyErrorCode.INVALID_CONTROL_TRANSITION
def test_pause_is_not_valid_when_already_paused():
    service=ConsentControlService(default_state=ConsentState.PAUSED)
    with pytest.raises(PolicyConsentError) as exc:
        service.apply(
            make_control_request(
                action=MemoryControlAction.PAUSE
            )
        )
    assert exc.value.code==PolicyErrorCode.INVALID_CONTROL_TRANSITION
def test_opt_out_is_not_valid_when_already_opted_out():
    service=ConsentControlService(default_state=ConsentState.OPTED_OUT)
    with pytest.raises(PolicyConsentError) as exc:
        service.apply(
            make_control_request(
                action=MemoryControlAction.OPT_OUT
            )
        )
    assert exc.value.code==PolicyErrorCode.INVALID_CONTROL_TRANSITION
def test_consent_state_is_persisted():
    store=InMemoryConsentStateStore()
    service=ConsentControlService(
        store,
        default_state=ConsentState.UNKNOWN
    )
    service.apply(
        make_control_request(
            action=MemoryControlAction.OPT_IN
        )
    )
    record=service.get_state("TEST_USER_001")
    assert isinstance(record,ConsentStateRecordV1)
    assert record.state==ConsentState.OPTED_IN
    assert record.last_action==MemoryControlAction.OPT_IN
def test_consent_state_is_subject_isolated():
    store=InMemoryConsentStateStore()
    service=ConsentControlService(
        store,
        default_state=ConsentState.UNKNOWN
    )
    service.apply(
        make_control_request(
            subject_id="TEST_USER_001",
            action=MemoryControlAction.OPT_IN
        )
    )
    user_one=service.get_state("TEST_USER_001")
    user_two=service.get_state("TEST_USER_002")
    assert user_one.state==ConsentState.OPTED_IN
    assert user_two.state==ConsentState.UNKNOWN
def test_consent_control_request_rejects_subject_scope_mismatch():
    with pytest.raises(ValueError,match="subject_scope must match subject_id"):
        ConsentControlRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            action=MemoryControlAction.OPT_IN,
            timestamp=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
            correlation_id="CONTROL_001"
        )
def test_consent_control_request_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError,match="timestamp must be timezone-aware"):
        ConsentControlRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            action=MemoryControlAction.OPT_IN,
            timestamp=datetime(2026,8,25,10,0,0),
            correlation_id="CONTROL_001"
        )
def test_consent_state_record_requires_timezone_aware_changed_at():
    with pytest.raises(ValueError,match="changed_at must be timezone-aware"):
        ConsentStateRecordV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            state=ConsentState.OPTED_IN,
            changed_at=datetime(2026,8,25,10,0,0),
            last_action=MemoryControlAction.OPT_IN,
            correlation_id="CONTROL_001"
        )
def test_policy_consent_service_can_apply_consent_control():
    service=PolicyConsentService()
    result=service.apply_consent_control(
        make_control_request(
            action=MemoryControlAction.OPT_IN
        )
    )
    assert result.current_state==ConsentState.OPTED_IN
def test_policy_consent_service_returns_current_consent_state():
    service=PolicyConsentService()
    service.apply_consent_control(
        make_control_request(
            action=MemoryControlAction.OPT_IN
        )
    )
    record=service.get_consent_state("TEST_USER_001")
    assert record.state==ConsentState.OPTED_IN
def test_resume_and_opt_in_have_distinct_action_history():
    store=InMemoryConsentStateStore()
    service=ConsentControlService(
        store,
        default_state=ConsentState.OPTED_IN
    )
    service.apply(
        make_control_request(
            action=MemoryControlAction.PAUSE,
            correlation_id="PAUSE_001"
        )
    )
    resume_result=service.apply(
        make_control_request(
            action=MemoryControlAction.RESUME,
            correlation_id="RESUME_001"
        )
    )
    assert resume_result.action==MemoryControlAction.RESUME
    assert resume_result.current_state==ConsentState.OPTED_IN
    assert resume_result.state_record.last_action==MemoryControlAction.RESUME

def test_consent_control_state_feeds_policy_evaluation():
    service=PolicyConsentService()
    service.apply_consent_control(
        make_control_request(
            action=MemoryControlAction.PAUSE
        )
    )
    consent_record=service.get_consent_state("TEST_USER_001")
    candidate=make_candidate()
    request=make_request(
        consent_state=consent_record.state
    )
    result=service.evaluate(candidate,request)
    assert result.decision==PolicyDecisionType.DENY
    assert result.consent_decision==ConsentDecision.PAUSED        