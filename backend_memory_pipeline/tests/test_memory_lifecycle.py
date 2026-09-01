import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.memory_extraction.memory_extraction import (
    ExtractedMemoryCandidate,
    ExtractionDecision,
    MemoryType,
    PolicyClass,
    TemporalScope
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentDecision,
    PolicyDecisionType,
    PolicyDecisionV1,
    RetentionClass,
    SensitivityLevel
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    InMemoryMemoryStore,
    LifecycleErrorCode,
    MemoryLifecycleAction,
    MemoryLifecycleError,
    MemoryLifecycleRequestV1,
    MemoryLifecycleService,
    MemoryRecordV1,
    MemoryStatus
)
def make_candidate(
    candidate_id="CANDIDATE_001",
    subject_id="TEST_USER_001",
    memory_type=MemoryType.EXPLICIT_PREFERENCE,
    normalized_fact="User prefers calm acoustic music.",
    confidence=0.95,
    source_event_ids=None,
    source_session_ids=None
):
    source_event_ids=source_event_ids or ["SOURCE_001"]
    source_session_ids=source_session_ids or ["SESSION_001"]
    return ExtractedMemoryCandidate(
        candidate_id=candidate_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        source_event_id=source_event_ids[-1],
        source_event_ids=source_event_ids,
        source_session_ids=source_session_ids,
        source_event_type="ai_interaction",
        memory_type=memory_type,
        decision=ExtractionDecision.MEMORY_CANDIDATE,
        normalized_fact=normalized_fact,
        evidence_texts=["I prefer calm acoustic music."],
        entities=[],
        confidence=confidence,
        relevance_score=None,
        temporal_scope=TemporalScope.PERSISTENT,
        policy_class=PolicyClass.STANDARD,
        policy_flags=[],
        reason="Approved test candidate.",
        evidence_count=len(source_event_ids),
        explicit_evidence_count=1,
        behavioral_evidence_count=0
    )
def make_policy(
    candidate_id="CANDIDATE_001",
    subject_id="TEST_USER_001",
    decision=PolicyDecisionType.ALLOW,
    retention_class=RetentionClass.LONG,
    retrieval_eligible=True,
    embedding_eligible=True
):
    return PolicyDecisionV1(
        candidate_id=candidate_id,
        subject_id=subject_id,
        decision=decision,
        consent_decision=ConsentDecision.ALLOWED,
        sensitivity=SensitivityLevel.STANDARD,
        retention_class=retention_class,
        retrieval_eligible=retrieval_eligible,
        embedding_eligible=embedding_eligible,
        policy_flags=[],
        denied_reasons=[],
        review_reasons=[],
        allowed_reasons=["Approved for lifecycle processing."],
        policy_version="1.0"
    )
def make_request(
    action,
    subject_id="TEST_USER_001",
    memory_id=None,
    target_memory_id=None,
    effective_at=None,
    reason="Lifecycle test operation."
):
    return MemoryLifecycleRequestV1(
        action=action,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_id=memory_id,
        target_memory_id=target_memory_id,
        effective_at=effective_at or datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
        reason=reason,
        correlation_id="CORR_001"
    )
def test_create_from_approved_candidate():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    candidate=make_candidate()
    policy=make_policy()
    result=service.create_from_approved_candidate(
        candidate,
        policy,
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    assert result.action==MemoryLifecycleAction.CREATE
    assert result.status==MemoryStatus.ACTIVE
    assert result.changed is True
    assert result.created_memory_id is not None
    memory=store.get(result.created_memory_id)
    assert memory is not None
    assert memory.subject_id=="TEST_USER_001"
    assert memory.memory_type==MemoryType.EXPLICIT_PREFERENCE
    assert memory.retrieval_eligible is True
    assert memory.embedding_eligible is True
def test_creation_requires_policy_allow():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    candidate=make_candidate()
    policy=make_policy(decision=PolicyDecisionType.REVIEW)
    with pytest.raises(MemoryLifecycleError) as exc:
        service.create_from_approved_candidate(candidate,policy)
    assert exc.value.code==LifecycleErrorCode.POLICY_NOT_ALLOWED
def test_creation_rejects_denied_policy():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    candidate=make_candidate()
    policy=make_policy(decision=PolicyDecisionType.DENY)
    with pytest.raises(MemoryLifecycleError) as exc:
        service.create_from_approved_candidate(candidate,policy)
    assert exc.value.code==LifecycleErrorCode.POLICY_NOT_ALLOWED
def test_creation_rejects_subject_mismatch():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    candidate=make_candidate(subject_id="TEST_USER_001")
    policy=make_policy(subject_id="TEST_USER_999")
    with pytest.raises(MemoryLifecycleError) as exc:
        service.create_from_approved_candidate(candidate,policy)
    assert exc.value.code==LifecycleErrorCode.SUBJECT_MISMATCH
def test_equivalent_active_memory_is_retained_and_reinforced():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    candidate=make_candidate()
    policy=make_policy()
    first=service.create_from_approved_candidate(
        candidate,
        policy,
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    second_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        source_event_ids=["SOURCE_001","SOURCE_002"],
        source_session_ids=["SESSION_001","SESSION_002"],
        confidence=0.99
    )
    second_policy=make_policy(candidate_id="CANDIDATE_002")
    second=service.create_from_approved_candidate(
        second_candidate,
        second_policy,
        datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
    )
    assert second.action==MemoryLifecycleAction.RETAIN
    assert second.memory_id==first.memory_id
    assert second.changed is True
    memory=store.get(first.memory_id)
    assert set(memory.source_event_ids)=={"SOURCE_001","SOURCE_002"}
    assert set(memory.source_session_ids)=={"SESSION_001","SESSION_002"}
    assert memory.confidence==0.99
def test_supersede_closes_old_memory_and_creates_new_memory():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    original_candidate=make_candidate(
        normalized_fact="User prefers energetic music."
    )
    policy=make_policy()
    created=service.create_from_approved_candidate(
        original_candidate,
        policy,
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    new_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers calm acoustic music."
    )
    new_policy=make_policy(candidate_id="CANDIDATE_002")
    request=make_request(
        MemoryLifecycleAction.SUPERSEDE,
        target_memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc),
        reason="New explicit preference supersedes the old preference."
    )
    result=service.supersede(request,new_candidate,new_policy)
    assert result.action==MemoryLifecycleAction.SUPERSEDE
    assert result.previous_memory_id==created.memory_id
    assert result.created_memory_id is not None
    old_memory=store.get(created.memory_id)
    new_memory=store.get(result.created_memory_id)
    assert old_memory.status==MemoryStatus.SUPERSEDED
    assert old_memory.valid_to==request.effective_at
    assert old_memory.retrieval_eligible is False
    assert old_memory.embedding_eligible is False
    assert new_memory.status==MemoryStatus.ACTIVE
    assert new_memory.supersedes_memory_id==created.memory_id
def test_supersede_deleted_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    delete_request=make_request(
        MemoryLifecycleAction.DELETE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
    )
    service.delete(delete_request)
    replacement=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers jazz."
    )
    replacement_policy=make_policy(candidate_id="CANDIDATE_002")
    supersede_request=make_request(
        MemoryLifecycleAction.SUPERSEDE,
        target_memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.supersede(
            supersede_request,
            replacement,
            replacement_policy
        )
    assert exc.value.code==LifecycleErrorCode.ALREADY_DELETED
def test_supersede_expired_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    expire_request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    service.expire(expire_request)
    replacement=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers jazz."
    )
    replacement_policy=make_policy(candidate_id="CANDIDATE_002")
    supersede_request=make_request(
        MemoryLifecycleAction.SUPERSEDE,
        target_memory_id=created.memory_id,
        effective_at=datetime(2026,8,27,10,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.supersede(
            supersede_request,
            replacement,
            replacement_policy
        )
    assert exc.value.code==LifecycleErrorCode.ALREADY_EXPIRED
def test_supersede_rejects_replacement_candidate_from_another_subject():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(subject_id="TEST_USER_001"),
        make_policy(subject_id="TEST_USER_001"),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    replacement=make_candidate(
        candidate_id="CANDIDATE_002",
        subject_id="TEST_USER_999",
        normalized_fact="User prefers jazz."
    )
    replacement_policy=make_policy(
        candidate_id="CANDIDATE_002",
        subject_id="TEST_USER_999"
    )
    supersede_request=make_request(
        MemoryLifecycleAction.SUPERSEDE,
        target_memory_id=created.memory_id
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.supersede(
            supersede_request,
            replacement,
            replacement_policy
        )
    assert exc.value.code==LifecycleErrorCode.SUBJECT_MISMATCH
def test_correct_closes_old_memory_and_creates_replacement():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    original_candidate=make_candidate(
        normalized_fact="User prefers energetic music."
    )
    policy=make_policy()
    created=service.create_from_approved_candidate(
        original_candidate,
        policy,
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    corrected_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers acoustic music."
    )
    corrected_policy=make_policy(candidate_id="CANDIDATE_002")
    request=make_request(
        MemoryLifecycleAction.CORRECT,
        target_memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,13,0,0,tzinfo=timezone.utc),
        reason="User explicitly corrected the old preference."
    )
    result=service.correct(
        request,
        corrected_candidate,
        corrected_policy
    )
    assert result.action==MemoryLifecycleAction.CORRECT
    assert result.previous_memory_id==created.memory_id
    assert result.created_memory_id is not None
    old_memory=store.get(created.memory_id)
    new_memory=store.get(result.created_memory_id)
    assert old_memory.status==MemoryStatus.CORRECTED
    assert old_memory.valid_to==request.effective_at
    assert old_memory.retrieval_eligible is False
    assert new_memory.status==MemoryStatus.ACTIVE
    assert new_memory.correction_of_memory_id==created.memory_id
def test_correction_requires_policy_approval_for_replacement():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    corrected_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers jazz."
    )
    denied_policy=make_policy(
        candidate_id="CANDIDATE_002",
        decision=PolicyDecisionType.DENY
    )
    request=make_request(
        MemoryLifecycleAction.CORRECT,
        target_memory_id=created.memory_id
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.correct(
            request,
            corrected_candidate,
            denied_policy
        )
    assert exc.value.code==LifecycleErrorCode.POLICY_NOT_ALLOWED
def test_correction_denied_policy_does_not_mutate_existing_memory():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    corrected_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers jazz."
    )
    denied_policy=make_policy(
        candidate_id="CANDIDATE_002",
        decision=PolicyDecisionType.DENY
    )
    request=make_request(
        MemoryLifecycleAction.CORRECT,
        target_memory_id=created.memory_id
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.correct(
            request,
            corrected_candidate,
            denied_policy
        )
    assert exc.value.code==LifecycleErrorCode.POLICY_NOT_ALLOWED
    old_memory=store.get(created.memory_id)
    assert old_memory.status==MemoryStatus.ACTIVE
    assert old_memory.valid_to is None
    assert old_memory.retrieval_eligible is True
    assert old_memory.embedding_eligible is True
def test_correction_of_expired_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    expire_request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    service.expire(expire_request)
    corrected_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers jazz."
    )
    corrected_policy=make_policy(candidate_id="CANDIDATE_002")
    request=make_request(
        MemoryLifecycleAction.CORRECT,
        target_memory_id=created.memory_id,
        effective_at=datetime(2026,8,27,10,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.correct(
            request,
            corrected_candidate,
            corrected_policy
        )
    assert exc.value.code==LifecycleErrorCode.ALREADY_EXPIRED
def test_correction_of_pending_deletion_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    delete_request=make_request(
        MemoryLifecycleAction.DELETE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
    )
    service.delete(delete_request)
    corrected_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers jazz."
    )
    corrected_policy=make_policy(candidate_id="CANDIDATE_002")
    request=make_request(
        MemoryLifecycleAction.CORRECT,
        target_memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.correct(
            request,
            corrected_candidate,
            corrected_policy
        )
    assert exc.value.code==LifecycleErrorCode.ALREADY_DELETED
def test_correct_rejects_replacement_candidate_from_another_subject():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(subject_id="TEST_USER_001"),
        make_policy(subject_id="TEST_USER_001"),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    corrected_candidate=make_candidate(
        candidate_id="CANDIDATE_002",
        subject_id="TEST_USER_999",
        normalized_fact="User prefers jazz."
    )
    corrected_policy=make_policy(
        candidate_id="CANDIDATE_002",
        subject_id="TEST_USER_999"
    )
    request=make_request(
        MemoryLifecycleAction.CORRECT,
        target_memory_id=created.memory_id
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.correct(
            request,
            corrected_candidate,
            corrected_policy
        )
    assert exc.value.code==LifecycleErrorCode.SUBJECT_MISMATCH
def test_expire_closes_memory_and_disables_retrieval():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        reason="Retention period expired."
    )
    result=service.expire(request)
    assert result.action==MemoryLifecycleAction.EXPIRE
    assert result.status==MemoryStatus.EXPIRED
    assert result.changed is True
    memory=store.get(created.memory_id)
    assert memory.status==MemoryStatus.EXPIRED
    assert memory.valid_to==request.effective_at
    assert memory.retrieval_eligible is False
    assert memory.embedding_eligible is False
def test_expire_already_expired_memory_is_idempotent():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    first=service.expire(request)
    second=service.expire(request)
    assert first.changed is True
    assert second.changed is False
    assert second.status==MemoryStatus.EXPIRED
def test_expire_deleted_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    delete_request=make_request(
        MemoryLifecycleAction.DELETE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
    )
    service.delete(delete_request)
    expire_request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.expire(expire_request)
    assert exc.value.code==LifecycleErrorCode.ALREADY_DELETED
def test_retain_active_memory_does_not_change_state():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.RETAIN,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
    )
    result=service.retain(request)
    assert result.action==MemoryLifecycleAction.RETAIN
    assert result.status==MemoryStatus.ACTIVE
    assert result.changed is False
    memory=store.get(created.memory_id)
    assert memory.status==MemoryStatus.ACTIVE
def test_update_active_memory_changes_allowed_fields():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.UPDATE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
    )
    result=service.update(
        request,
        {
            "normalized_fact":"User prefers instrumental acoustic music.",
            "confidence":0.99
        }
    )
    assert result.action==MemoryLifecycleAction.UPDATE
    assert result.changed is True
    memory=store.get(created.memory_id)
    assert memory.normalized_fact=="User prefers instrumental acoustic music."
    assert memory.confidence==0.99
def test_update_rejects_unknown_fields():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.UPDATE,
        memory_id=created.memory_id
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.update(
            request,
            {"subject_id":"TEST_USER_999"}
        )
    assert exc.value.code==LifecycleErrorCode.INVALID_TRANSITION
def test_update_inactive_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    expire_request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    service.expire(expire_request)
    update_request=make_request(
        MemoryLifecycleAction.UPDATE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,27,10,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.update(
            update_request,
            {"normalized_fact":"Updated fact."}
        )
    assert exc.value.code==LifecycleErrorCode.INVALID_TRANSITION
def test_delete_moves_memory_to_pending_deletion():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.DELETE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        reason="User requested deletion."
    )
    result=service.delete(request)
    assert result.action==MemoryLifecycleAction.DELETE
    assert result.status==MemoryStatus.PENDING_DELETION
    assert result.changed is True
    memory=store.get(created.memory_id)
    assert memory.status==MemoryStatus.PENDING_DELETION
    assert memory.retrieval_eligible is False
    assert memory.embedding_eligible is False
    assert memory.valid_to==request.effective_at
def test_delete_already_deleted_or_pending_deletion_is_idempotent():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.DELETE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    first=service.delete(request)
    second=service.delete(request)
    assert first.changed is True
    assert second.changed is False
    assert second.status in {MemoryStatus.PENDING_DELETION,MemoryStatus.DELETED}
def test_delete_terminal_superseded_memory_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    original=service.create_from_approved_candidate(
        make_candidate(
            normalized_fact="User prefers energetic music."
        ),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    replacement=make_candidate(
        candidate_id="CANDIDATE_002",
        normalized_fact="User prefers acoustic music."
    )
    service.supersede(
        make_request(
            MemoryLifecycleAction.SUPERSEDE,
            target_memory_id=original.memory_id,
            effective_at=datetime(2026,8,25,11,0,0,tzinfo=timezone.utc)
        ),
        replacement,
        make_policy(candidate_id="CANDIDATE_002")
    )
    delete_request=make_request(
        MemoryLifecycleAction.DELETE,
        memory_id=original.memory_id,
        effective_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.delete(delete_request)
    assert exc.value.code==LifecycleErrorCode.INVALID_TRANSITION
def test_cross_subject_memory_access_is_rejected():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(subject_id="TEST_USER_001"),
        make_policy(subject_id="TEST_USER_001"),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.DELETE,
        subject_id="TEST_USER_999",
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.delete(request)
    assert exc.value.code==LifecycleErrorCode.SUBJECT_MISMATCH
def test_effective_time_cannot_precede_valid_from():
    store=InMemoryMemoryStore()
    service=MemoryLifecycleService(store)
    created=service.create_from_approved_candidate(
        make_candidate(),
        make_policy(),
        datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    )
    request=make_request(
        MemoryLifecycleAction.EXPIRE,
        memory_id=created.memory_id,
        effective_at=datetime(2026,8,25,9,0,0,tzinfo=timezone.utc)
    )
    with pytest.raises(MemoryLifecycleError) as exc:
        service.expire(request)
    assert exc.value.code==LifecycleErrorCode.TEMPORAL_CONFLICT
def test_memory_record_requires_timezone_aware_dates():
    naive=datetime(2026,8,25,10,0,0)
    with pytest.raises(ValueError,match="created_at must be timezone-aware"):
        MemoryRecordV1(
            memory_id="MEMORY_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            normalized_fact="User prefers jazz.",
            confidence=0.9,
            source_event_ids=["SOURCE_001"],
            source_session_ids=["SESSION_001"],
            created_at=naive,
            recorded_at=naive,
            valid_from=naive,
            status=MemoryStatus.ACTIVE,
            retention_class=RetentionClass.LONG,
            retrieval_eligible=True,
            embedding_eligible=True
        )
def test_memory_record_rejects_invalid_temporal_interval():
    start=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    end=datetime(2026,8,25,9,0,0,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match="valid_to cannot be earlier than valid_from"):
        MemoryRecordV1(
            memory_id="MEMORY_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            normalized_fact="User prefers jazz.",
            confidence=0.9,
            source_event_ids=["SOURCE_001"],
            source_session_ids=["SESSION_001"],
            created_at=start,
            recorded_at=start,
            valid_from=start,
            valid_to=end,
            status=MemoryStatus.EXPIRED,
            retention_class=RetentionClass.LONG,
            retrieval_eligible=False,
            embedding_eligible=False
        )
def test_memory_record_requires_subject_scope_match():
    now=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match="subject scope must match"):
        MemoryRecordV1(
            memory_id="MEMORY_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            memory_type=MemoryType.EXPLICIT_PREFERENCE,
            normalized_fact="User prefers jazz.",
            confidence=0.9,
            source_event_ids=["SOURCE_001"],
            source_session_ids=["SESSION_001"],
            created_at=now,
            recorded_at=now,
            valid_from=now,
            status=MemoryStatus.ACTIVE,
            retention_class=RetentionClass.LONG,
            retrieval_eligible=True,
            embedding_eligible=True
        )
def test_lifecycle_request_requires_target_for_supersede():
    with pytest.raises(ValueError,match="target_memory_id is required"):
        make_request(MemoryLifecycleAction.SUPERSEDE)
def test_lifecycle_request_requires_target_for_correct():
    with pytest.raises(ValueError,match="target_memory_id is required"):
        make_request(MemoryLifecycleAction.CORRECT)
def test_lifecycle_request_requires_memory_id_for_expire():
    with pytest.raises(ValueError,match="memory_id is required"):
        make_request(MemoryLifecycleAction.EXPIRE)
def test_lifecycle_request_requires_memory_id_for_delete():
    with pytest.raises(ValueError,match="memory_id is required"):
        make_request(MemoryLifecycleAction.DELETE)
def test_lifecycle_request_requires_timezone_aware_effective_at():
    with pytest.raises(ValueError,match="effective_at must be timezone-aware"):
        make_request(
            MemoryLifecycleAction.EXPIRE,
            memory_id="MEMORY_001",
            effective_at=datetime(2026,8,25,10,0,0)
        )
def test_lifecycle_request_rejects_subject_scope_mismatch():
    with pytest.raises(ValueError,match="subject_scope must match subject_id"):
        MemoryLifecycleRequestV1(
            action=MemoryLifecycleAction.DELETE,
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            memory_id="MEMORY_001",
            effective_at=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
            reason="Test request.",
            correlation_id="CORR_001"
        )