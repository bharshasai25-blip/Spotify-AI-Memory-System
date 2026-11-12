import pytest
from datetime import datetime,timezone,timedelta
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryStatus
from backend_memory_pipeline.retrieval.retrieval import (
    RetrievalCandidateV1,
    RetrievalDecision,
    RetrievalResultV1
)
from backend_memory_pipeline.context_composition.context_composition import (
    ContextCompositionError,
    ContextCompositionErrorCode,
    ContextCompositionRequestV1,
    ContextCompositionService,
    ContextDecision,
    ContextExclusionReason,
    RuleBasedContextComposer
)
def make_request(
    subject_id="TEST_USER_001",
    surface="chat",
    locale="en-IN",
    max_items=5,
    max_characters=12000,
    max_tokens=3000,
    requested_at=None
):
    return ContextCompositionRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        requested_at=requested_at or datetime(2026,8,25,12,0,0,tzinfo=timezone.utc),
        max_items=max_items,
        max_characters=max_characters,
        max_tokens=max_tokens,
        surface=surface,
        locale=locale
    )
def make_candidate(
    memory_id="MEMORY_001",
    subject_id="TEST_USER_001",
    memory_type="explicit_preference",
    normalized_fact="User prefers calm acoustic music.",
    final_score=0.90,
    confidence=0.95,
    explicitness_score=1.0,
    recency_score=0.90,
    repetition_score=0.60,
    surface_score=0.50,
    negative_feedback_score=0.0,
    recorded_at=None,
    valid_from=None,
    valid_to=None,
    source_event_ids=None,
    source_session_ids=None
):
    recorded_at=recorded_at or datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    valid_from=valid_from or recorded_at
    return RetrievalCandidateV1(
        memory_id=memory_id,
        subject_id=subject_id,
        memory_type=memory_type,
        normalized_fact=normalized_fact,
        status=MemoryStatus.ACTIVE,
        confidence=confidence,
        vector_score=0.90,
        graph_score=0.80,
        explicitness_score=explicitness_score,
        recency_score=recency_score,
        repetition_score=repetition_score,
        surface_score=surface_score,
        negative_feedback_score=negative_feedback_score,
        final_score=final_score,
        source_event_ids=source_event_ids or ["SOURCE_001"],
        source_session_ids=source_session_ids or ["SESSION_001"],
        relevance_reason="Strong hybrid relevance.",
        provenance={
            "recorded_at":recorded_at,
            "valid_from":valid_from,
            "valid_to":valid_to,
            "embedding_id":f"embedding:{memory_id}",
            "retrieval_version":"1.0"
        }
    )
def make_result(
    candidates=None,
    subject_id="TEST_USER_001",
    decision=RetrievalDecision.RETRIEVED,
    query_intent="I want calm acoustic music."
):
    if candidates is None:
       candidates=[make_candidate()]
    return RetrievalResultV1(
        decision=decision,
        subject_id=subject_id,
        query_intent=query_intent,
        candidates=candidates,
        candidate_count=len(candidates),
        graph_candidate_count=len(candidates),
        vector_candidate_count=len(candidates),
        returned_count=len(candidates),
        retrieval_version="1.0",
        provenance={"surface":"chat"}
    )
def test_valid_context_request_is_accepted():
    request=make_request()
    assert request.subject_id=="TEST_USER_001"
    assert request.max_items==5
def test_context_request_requires_subject_scope_match():
    with pytest.raises(ValueError,match="subject_scope must match subject_id"):
        ContextCompositionRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            requested_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc),
            surface="chat",
            locale="en-IN"
        )
def test_context_request_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError,match="requested_at must be timezone-aware"):
        ContextCompositionRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            requested_at=datetime(2026,8,25,12,0,0),
            surface="chat",
            locale="en-IN"
        )
def test_context_request_accepts_budget_limits():
    request=make_request(
        max_items=3,
        max_characters=500,
        max_tokens=100
    )
    assert request.max_items==3
    assert request.max_characters==500
    assert request.max_tokens==100
def test_valid_retrieval_result_is_composed():
    service=ContextCompositionService()
    result=service.compose(
        make_result(),
        make_request()
    )
    assert result.decision==ContextDecision.COMPOSED
    assert result.item_count==1
    assert len(result.items)==1
def test_composed_item_preserves_memory_identity():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_123"
                )
            ]
        ),
        make_request()
    )
    item=result.items[0]
    assert item.memory_id=="MEMORY_123"
    assert item.subject_id=="TEST_USER_001"
def test_composed_item_preserves_content():
    service=ContextCompositionService()
    candidate=make_candidate(
        normalized_fact="User prefers instrumental jazz."
    )
    result=service.compose(
        make_result(candidates=[candidate]),
        make_request()
    )
    assert result.items[0].content=="User prefers instrumental jazz."
def test_composed_item_preserves_provenance():
    service=ContextCompositionService()
    candidate=make_candidate()
    result=service.compose(
        make_result(candidates=[candidate]),
        make_request()
    )
    item=result.items[0]
    assert item.source_event_ids==["SOURCE_001"]
    assert item.source_session_ids==["SESSION_001"]
    assert item.provenance["embedding_id"]=="embedding:MEMORY_001"
    assert item.provenance["retrieval_rank"]==1
def test_context_item_rank_starts_at_one():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_001",
                    final_score=0.95
                ),
                make_candidate(
                    memory_id="MEMORY_002",
                    final_score=0.85,
                    normalized_fact="User likes jazz music."
                )
            ]
        ),
        make_request()
    )
    assert result.items[0].rank==1
    assert result.items[1].rank==2
def test_candidates_are_ordered_by_final_score():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_LOW",
                    normalized_fact="User likes jazz.",
                    final_score=0.60
                ),
                make_candidate(
                    memory_id="MEMORY_HIGH",
                    normalized_fact="User prefers acoustic jazz.",
                    final_score=0.95
                )
            ]
        ),
        make_request()
    )
    assert result.items[0].memory_id=="MEMORY_HIGH"
    assert result.items[1].memory_id=="MEMORY_LOW"
def test_candidates_are_deterministically_ordered_on_tie():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_B",
                    normalized_fact="User likes jazz.",
                    final_score=0.90
                ),
                make_candidate(
                    memory_id="MEMORY_A",
                    normalized_fact="User likes blues.",
                    final_score=0.90
                )
            ]
        ),
        make_request()
    )
    assert result.items[0].memory_id=="MEMORY_A"
    assert result.items[1].memory_id=="MEMORY_B"
def test_duplicate_memory_content_is_excluded():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_001",
                    normalized_fact="User prefers calm acoustic music.",
                    final_score=0.95
                ),
                make_candidate(
                    memory_id="MEMORY_002",
                    normalized_fact="User prefers calm acoustic music.",
                    final_score=0.85
                )
            ]
        ),
        make_request()
    )
    assert result.item_count==1
    assert len(result.exclusions)==1
    assert result.exclusions[0].reason==ContextExclusionReason.DUPLICATE
def test_duplicate_detection_is_case_insensitive():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_001",
                    normalized_fact="User Prefers Calm Acoustic Music.",
                    final_score=0.95
                ),
                make_candidate(
                    memory_id="MEMORY_002",
                    normalized_fact="user prefers calm acoustic music.",
                    final_score=0.85
                )
            ]
        ),
        make_request()
    )
    assert result.item_count==1
    assert result.exclusions[0].reason==ContextExclusionReason.DUPLICATE
def test_non_active_candidate_is_excluded():
    service=ContextCompositionService()
    candidate=make_candidate()
    candidate=candidate.model_copy(
        update={"status":MemoryStatus.EXPIRED}
    )
    result=service.compose(
        make_result(candidates=[candidate]),
        make_request()
    )
    assert result.decision==ContextDecision.NO_CONTEXT
    assert result.item_count==0
    assert result.exclusions[0].reason==ContextExclusionReason.INELIGIBLE_STATUS
def test_cross_subject_candidate_is_excluded():
    service=ContextCompositionService()
    candidate=make_candidate(
        subject_id="TEST_USER_999"
    )
    result=service.compose(
        make_result(candidates=[candidate]),
        make_request()
    )
    assert result.decision==ContextDecision.NO_CONTEXT
    assert result.exclusions[0].reason==ContextExclusionReason.INVALID_CANDIDATE
def test_retrieval_result_subject_mismatch_is_rejected():
    service=ContextCompositionService()
    result=make_result(
        subject_id="TEST_USER_999"
    )
    with pytest.raises(ContextCompositionError) as exc:
        service.compose(
            result,
            make_request(
                subject_id="TEST_USER_001"
            )
        )
    assert exc.value.code==ContextCompositionErrorCode.SUBJECT_MISMATCH
def test_no_retrieval_results_produce_no_context():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[],
            decision=RetrievalDecision.NO_RESULTS
        ),
        make_request()
    )
    assert result.decision==ContextDecision.NO_CONTEXT
    assert result.items==[]
    assert result.item_count==0
    assert result.estimated_token_count==0
def test_max_items_budget_is_enforced():
    service=ContextCompositionService()
    candidates=[
        make_candidate(
            memory_id="MEMORY_001",
            memory_type="explicit_preference",
            normalized_fact="User prefers calm acoustic music.",
            final_score=0.98
        ),
        make_candidate(
            memory_id="MEMORY_002",
            memory_type="episode",
            normalized_fact="User listened to a jazz playlist yesterday.",
            final_score=0.97
        ),
        make_candidate(
            memory_id="MEMORY_003",
            memory_type="exclusion",
            normalized_fact="Do not recommend heavy metal music.",
            final_score=0.96
        ),
        make_candidate(
            memory_id="MEMORY_004",
            memory_type="candidate_preference",
            normalized_fact="User often explores instrumental music.",
            final_score=0.95
        ),
        make_candidate(
            memory_id="MEMORY_005",
            memory_type="episode",
            normalized_fact="User recently played an acoustic playlist.",
            final_score=0.94
        )
    ]
    result=service.compose(
        make_result(candidates=candidates),
        make_request(max_items=2)
    )
    assert result.item_count==2
    budget_exclusions=[
        exclusion
        for exclusion in result.exclusions
        if exclusion.reason==ContextExclusionReason.BUDGET_EXCEEDED
    ]
    assert len(budget_exclusions)>=1
def test_character_budget_is_enforced():
    service=ContextCompositionService()
    candidates=[
        make_candidate(
            memory_id="MEMORY_001",
            normalized_fact="A"*300,
            final_score=0.95
        ),
        make_candidate(
            memory_id="MEMORY_002",
            normalized_fact="B"*300,
            final_score=0.90
        )
    ]
    result=service.compose(
        make_result(candidates=candidates),
        make_request(
            max_characters=400,
            max_tokens=500
        )
    )
    assert result.item_count==1
    assert any(
        exclusion.reason==ContextExclusionReason.BUDGET_EXCEEDED
        for exclusion in result.exclusions
    )
def test_token_budget_is_enforced():
    service=ContextCompositionService()
    candidates=[
        make_candidate(
            memory_id="MEMORY_001",
            normalized_fact="A"*200,
            final_score=0.95
        ),
        make_candidate(
            memory_id="MEMORY_002",
            normalized_fact="B"*200,
            final_score=0.90
        )
    ]
    result=service.compose(
        make_result(candidates=candidates),
        make_request(
            max_characters=2000,
            max_tokens=60
        )
    )
    assert result.item_count==1
    assert any(
        exclusion.reason==ContextExclusionReason.BUDGET_EXCEEDED
        for exclusion in result.exclusions
    )
def test_character_and_token_counts_are_reported():
    service=ContextCompositionService()
    result=service.compose(
        make_result(),
        make_request()
    )
    assert result.character_count==len(result.items[0].content)
    assert result.estimated_token_count>=1
def test_explicit_preference_is_preserved():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_type="explicit_preference"
                )
            ]
        ),
        make_request()
    )
    assert result.items[0].memory_type=="explicit_preference"
def test_exclusion_memory_is_preserved():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_type="exclusion",
                    normalized_fact="Do not recommend heavy metal music."
                )
            ]
        ),
        make_request()
    )
    assert result.items[0].memory_type=="exclusion"
def test_conflicting_explicit_preferences_are_filtered():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[
                make_candidate(
                    memory_id="MEMORY_001",
                    normalized_fact="User prefers calm acoustic music.",
                    final_score=0.95
                ),
                make_candidate(
                    memory_id="MEMORY_002",
                    normalized_fact="User prefers calm acoustic music because of other reasons.",
                    final_score=0.85
                )
            ]
        ),
        make_request()
    )
    assert result.item_count==1
def test_context_composition_preserves_retrieval_version():
    service=ContextCompositionService()
    retrieval=make_result()
    retrieval=retrieval.model_copy(
        update={"retrieval_version":"2.1"}
    )
    result=service.compose(
        retrieval,
        make_request()
    )
    assert result.provenance["retrieval_version"]=="2.1"
def test_context_composition_version_is_preserved():
    composer=RuleBasedContextComposer(
        composition_version="2.0"
    )
    service=ContextCompositionService(
        composer=composer
    )
    result=service.compose(
        make_result(),
        make_request()
    )
    assert result.composition_version=="2.0"
def test_service_delegates_to_composer():
    class StubComposer:
        def compose(self,retrieval_result,request):
            return make_context_result()
    def make_context_result():
        from backend_memory_pipeline.context_composition.context_composition import ContextCompositionResultV1
        return ContextCompositionResultV1(
            decision=ContextDecision.NO_CONTEXT,
            subject_id="TEST_USER_001",
            query_intent="stub",
            items=[],
            exclusions=[],
            item_count=0,
            character_count=0,
            estimated_token_count=0
        )
    service=ContextCompositionService(
        composer=StubComposer()
    )
    result=service.compose(
        make_result(),
        make_request()
    )
    assert result.decision==ContextDecision.NO_CONTEXT
    assert result.query_intent=="stub"
def test_invalid_retrieval_input_is_rejected():
    service=ContextCompositionService()
    with pytest.raises(ContextCompositionError) as exc:
        service.compose(
            {"bad":"input"},
            make_request()
        )
    assert exc.value.code==ContextCompositionErrorCode.INVALID_RETRIEVAL_RESULT
def test_invalid_request_input_is_rejected():
    service=ContextCompositionService()
    with pytest.raises(ContextCompositionError) as exc:
        service.compose(
            make_result(),
            {"bad":"request"}
        )
    assert exc.value.code==ContextCompositionErrorCode.INVALID_BUDGET
def test_invalid_candidate_provenance_is_rejected():
    service=ContextCompositionService()
    candidate=make_candidate()
    candidate=candidate.model_copy(
        update={
            "provenance":{
                "recorded_at":"not-a-datetime",
                "valid_from":datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
                "valid_to":None
            }
        }
    )
    with pytest.raises(ContextCompositionError) as exc:
        service.compose(
            make_result(candidates=[candidate]),
            make_request()
        )
    assert exc.value.code==ContextCompositionErrorCode.INVALID_CANDIDATE
def test_context_composition_is_deterministic():
    service=ContextCompositionService()
    retrieval=make_result(
        candidates=[
            make_candidate(
                memory_id="MEMORY_A",
                normalized_fact="User likes jazz.",
                final_score=0.90
            ),
            make_candidate(
                memory_id="MEMORY_B",
                normalized_fact="User likes blues.",
                final_score=0.80
            )
        ]
    )
    request=make_request()
    first=service.compose(retrieval,request)
    second=service.compose(retrieval,request)
    assert first.model_dump()==second.model_dump()
def test_empty_candidate_list_from_retrieved_result_produces_no_context():
    service=ContextCompositionService()
    result=service.compose(
        make_result(
            candidates=[],
            decision=RetrievalDecision.RETRIEVED
        ),
        make_request()
    )
    assert result.decision==ContextDecision.NO_CONTEXT
    assert result.item_count==0
def test_context_item_temporal_fields_are_preserved():
    service=ContextCompositionService()
    recorded_at=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc)
    valid_from=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc)
    valid_to=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    candidate=make_candidate(
        recorded_at=recorded_at,
        valid_from=valid_from,
        valid_to=valid_to
    )
    result=service.compose(
        make_result(candidates=[candidate]),
        make_request()
    )
    item=result.items[0]
    assert item.recorded_at==recorded_at
    assert item.valid_from==valid_from
    assert item.valid_to==valid_to
def test_surface_compatible_memory_is_preserved():
    service=ContextCompositionService()
    candidate=make_candidate(
        final_score=0.90
    )
    result=service.compose(
        make_result(candidates=[candidate]),
        make_request(surface="chat")
    )
    assert result.decision==ContextDecision.COMPOSED
    assert result.provenance["surface"]=="chat"