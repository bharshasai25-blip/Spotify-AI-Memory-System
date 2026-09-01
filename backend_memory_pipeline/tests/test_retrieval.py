import pytest
from datetime import datetime,timezone,timedelta
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryType
from backend_memory_pipeline.policy_consent.policy_consent import RetentionClass
from backend_memory_pipeline.graph_memory.graph import InMemoryGraphStore,GraphMemoryService
from backend_memory_pipeline.embedding.embedding import EmbeddingService,InMemoryEmbeddingStore
from backend_memory_pipeline.retrieval.retrieval import (
    DeterministicQueryEmbeddingProvider,
    SentenceTransformerQueryEmbeddingProvider,
    InMemoryRetrievalStore,
    RetrievalDecision,
    RetrievalError,
    RetrievalErrorCode,
    RetrievalRequestV1,
    RetrievalService
)
def make_memory(
    memory_id="MEMORY_001",
    subject_id="TEST_USER_001",
    memory_type=MemoryType.EXPLICIT_PREFERENCE,
    normalized_fact="User prefers calm acoustic music.",
    confidence=0.95,
    status=MemoryStatus.ACTIVE,
    retrieval_eligible=True,
    embedding_eligible=True,
    recorded_at=None,
    valid_from=None,
    valid_to=None,
    source_event_ids=None,
    source_session_ids=None,
    metadata=None
):
    recorded_at=recorded_at or datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    valid_from=valid_from or recorded_at
    return MemoryRecordV1(
        memory_id=memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_type=memory_type,
        normalized_fact=normalized_fact,
        entities=[],
        confidence=confidence,
        source_event_ids=source_event_ids or ["SOURCE_001"],
        source_session_ids=source_session_ids or ["SESSION_001"],
        created_at=recorded_at,
        recorded_at=recorded_at,
        valid_from=valid_from,
        valid_to=valid_to,
        status=status,
        retention_class=RetentionClass.LONG,
        retrieval_eligible=retrieval_eligible,
        embedding_eligible=embedding_eligible,
        metadata=metadata or {}
    )
def make_request(
    subject_id="TEST_USER_001",
    intent="I want calm acoustic music.",
    surface="chat",
    locale="en-IN",
    requested_at=None,
    top_k=5,
    candidate_limit=50,
    vector_weight=0.55,
    graph_weight=0.45,
    min_score=0.0
):
    return RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent=intent,
        surface=surface,
        locale=locale,
        requested_at=requested_at or datetime(2026,8,25,12,0,0,tzinfo=timezone.utc),
        top_k=top_k,
        candidate_limit=candidate_limit,
        vector_weight=vector_weight,
        graph_weight=graph_weight,
        min_score=min_score
    )
def make_retrieval_service(
    memories=None,
    dimensions=64
):
    graph_store=InMemoryGraphStore()
    graph_service=GraphMemoryService(graph_store)
    embedding_store=InMemoryEmbeddingStore()
    embedding_service=EmbeddingService(embedding_store)
    memories=memories or [make_memory()]
    for memory in memories:
        graph_service.upsert_memory(memory)
        if memory.embedding_eligible and memory.status==MemoryStatus.ACTIVE:
            embedding_service.upsert_memory_embedding(
                memory,
                dimensions=dimensions
            )
    retrieval_store=InMemoryRetrievalStore(
        graph_store,
        embedding_store
    )
    return RetrievalService(
        retrieval_store=retrieval_store,
        query_provider=DeterministicQueryEmbeddingProvider()
    )
def test_valid_request_is_accepted():
    request=make_request()
    assert request.subject_id=="TEST_USER_001"
    assert request.intent=="I want calm acoustic music."
def test_subject_scope_must_match_subject_id():
    with pytest.raises(ValueError,match="subject_scope must match subject_id"):
        RetrievalRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            intent="I want jazz.",
            surface="chat",
            locale="en-IN",
            requested_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc)
        )
def test_request_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError,match="requested_at must be timezone-aware"):
        RetrievalRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            intent="I want jazz.",
            surface="chat",
            locale="en-IN",
            requested_at=datetime(2026,8,25,12,0,0)
        )
def test_request_rejects_zero_total_hybrid_weight():
    with pytest.raises(ValueError,match="cannot both be zero"):
        RetrievalRequestV1(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            intent="I want jazz.",
            surface="chat",
            locale="en-IN",
            requested_at=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc),
            vector_weight=0.0,
            graph_weight=0.0
        )
def test_relevant_memory_is_retrieved():
    service=make_retrieval_service(
        memories=[
            make_memory(
                normalized_fact="User prefers calm acoustic music."
            )
        ]
    )
    result=service.retrieve(
        make_request(
            intent="I want calm acoustic music."
        )
    )
    assert result.decision==RetrievalDecision.RETRIEVED
    assert result.returned_count>=1
    assert result.candidates[0].memory_id=="MEMORY_001"
def test_retrieval_preserves_memory_provenance():
    service=make_retrieval_service(
        memories=[
            make_memory(
                source_event_ids=["SOURCE_001","SOURCE_002"],
                source_session_ids=["SESSION_001","SESSION_002"]
            )
        ]
    )
    result=service.retrieve(make_request())
    candidate=result.candidates[0]
    assert candidate.source_event_ids==["SOURCE_001","SOURCE_002"]
    assert candidate.source_session_ids==["SESSION_001","SESSION_002"]
    assert "recorded_at" in candidate.provenance
    assert "valid_from" in candidate.provenance
def test_retrieval_is_subject_scoped():
    service=make_retrieval_service(
        memories=[
            make_memory(
                memory_id="MEMORY_001",
                subject_id="TEST_USER_001",
                normalized_fact="User prefers jazz."
            ),
            make_memory(
                memory_id="MEMORY_002",
                subject_id="TEST_USER_002",
                normalized_fact="User prefers classical music."
            )
        ]
    )
    result=service.retrieve(
        make_request(
            subject_id="TEST_USER_001",
            intent="What music do I like?"
        )
    )
    ids={candidate.memory_id for candidate in result.candidates}
    assert "MEMORY_001" in ids
    assert "MEMORY_002" not in ids
def test_cross_subject_memories_are_never_retrieved():
    service=make_retrieval_service(
        memories=[
            make_memory(
                memory_id="MEMORY_001",
                subject_id="TEST_USER_001",
                normalized_fact="User prefers jazz."
            ),
            make_memory(
                memory_id="MEMORY_002",
                subject_id="TEST_USER_002",
                normalized_fact="User prefers jazz."
            )
        ]
    )
    result=service.retrieve(
        make_request(
            subject_id="TEST_USER_001",
            intent="I prefer jazz."
        )
    )
    assert all(
        candidate.subject_id=="TEST_USER_001"
        for candidate in result.candidates
    )
def test_expired_memory_is_excluded():
    service=make_retrieval_service(
        memories=[
            make_memory(
                status=MemoryStatus.EXPIRED,
                valid_from=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                recorded_at=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                valid_to=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc),
                retrieval_eligible=False,
                embedding_eligible=False
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.decision==RetrievalDecision.NO_RESULTS
    assert result.returned_count==0
def test_superseded_memory_is_excluded():
    service=make_retrieval_service(
        memories=[
            make_memory(
                status=MemoryStatus.SUPERSEDED,
                valid_from=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                recorded_at=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                valid_to=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc),
                retrieval_eligible=False,
                embedding_eligible=False
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.decision==RetrievalDecision.NO_RESULTS
def test_corrected_memory_is_excluded():
    service=make_retrieval_service(
        memories=[
            make_memory(
                status=MemoryStatus.CORRECTED,
                valid_from=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                recorded_at=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                valid_to=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc),
                retrieval_eligible=False,
                embedding_eligible=False
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.decision==RetrievalDecision.NO_RESULTS
def test_pending_deletion_memory_is_excluded():
    service=make_retrieval_service(
        memories=[
            make_memory(
                status=MemoryStatus.PENDING_DELETION,
                valid_from=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                recorded_at=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                valid_to=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc),
                retrieval_eligible=False,
                embedding_eligible=False
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.decision==RetrievalDecision.NO_RESULTS
def test_memory_with_retrieval_disabled_is_excluded():
    service=make_retrieval_service(
        memories=[
            make_memory(
                retrieval_eligible=False,
                embedding_eligible=True
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.decision==RetrievalDecision.NO_RESULTS
def test_memory_with_embedding_disabled_is_still_graph_candidate():
    service=make_retrieval_service(
        memories=[
            make_memory(
                embedding_eligible=False,
                retrieval_eligible=True
            )
        ]
    )
    result=service.retrieve(
        make_request(
            intent="I want calm acoustic music."
        )
    )
    assert result.graph_candidate_count>=1
def test_candidate_contains_vector_score():
    service=make_retrieval_service()
    result=service.retrieve(make_request())
    candidate=result.candidates[0]
    assert 0.0<=candidate.vector_score<=1.0
def test_candidate_contains_graph_score():
    service=make_retrieval_service()
    result=service.retrieve(make_request())
    candidate=result.candidates[0]
    assert 0.0<=candidate.graph_score<=1.0
def test_candidate_contains_reranking_scores():
    service=make_retrieval_service()
    result=service.retrieve(make_request())
    candidate=result.candidates[0]
    assert 0.0<=candidate.explicitness_score<=1.0
    assert 0.0<=candidate.recency_score<=1.0
    assert 0.0<=candidate.repetition_score<=1.0
    assert 0.0<=candidate.surface_score<=1.0
    assert 0.0<=candidate.negative_feedback_score<=1.0
    assert 0.0<=candidate.final_score<=1.0
def test_explicit_preference_receives_high_explicitness_score():
    service=make_retrieval_service(
        memories=[
            make_memory(
                memory_type=MemoryType.EXPLICIT_PREFERENCE
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.candidates[0].explicitness_score==1.0
def test_exclusion_receives_high_explicitness_score():
    service=make_retrieval_service(
        memories=[
            make_memory(
                memory_type=MemoryType.EXCLUSION
            )
        ]
    )
    result=service.retrieve(make_request())
    assert result.candidates[0].explicitness_score==0.95
def test_recent_memory_gets_higher_recency_score():
    now=datetime(2026,8,25,12,0,0,tzinfo=timezone.utc)
    recent=make_memory(
        memory_id="MEMORY_RECENT",
        recorded_at=now-timedelta(days=1)
    )
    old=make_memory(
        memory_id="MEMORY_OLD",
        recorded_at=now-timedelta(days=60)
    )
    service=make_retrieval_service(
        memories=[recent,old]
    )
    result=service.retrieve(
        make_request(
            requested_at=now,
            intent="I want calm acoustic music."
        )
    )
    scores={
        candidate.memory_id:candidate.recency_score
        for candidate in result.candidates
    }
    assert scores["MEMORY_RECENT"]>scores["MEMORY_OLD"]
def test_repeated_evidence_increases_repetition_score():
    single=make_memory(
        memory_id="MEMORY_SINGLE",
        source_event_ids=["SOURCE_001"],
        source_session_ids=["SESSION_001"]
    )
    repeated=make_memory(
        memory_id="MEMORY_REPEATED",
        source_event_ids=["SOURCE_001","SOURCE_002","SOURCE_003"],
        source_session_ids=["SESSION_001","SESSION_002","SESSION_003"]
    )
    service=make_retrieval_service(
        memories=[single,repeated]
    )
    result=service.retrieve(make_request())
    scores={
        candidate.memory_id:candidate.repetition_score
        for candidate in result.candidates
    }
    assert scores["MEMORY_REPEATED"]>scores["MEMORY_SINGLE"]
def test_surface_compatibility_increases_surface_score():
    matching=make_memory(
        memory_id="MEMORY_MATCH",
        metadata={"supported_surfaces":["chat"]}
    )
    non_matching=make_memory(
        memory_id="MEMORY_NON_MATCH",
        metadata={"supported_surfaces":["playlist"]}
    )
    service=make_retrieval_service(
        memories=[matching,non_matching]
    )
    result=service.retrieve(
        make_request(
            surface="chat"
        )
    )
    scores={
        candidate.memory_id:candidate.surface_score
        for candidate in result.candidates
    }
    assert scores["MEMORY_MATCH"]==1.0
    assert scores["MEMORY_NON_MATCH"]==0.0
def test_negative_feedback_reduces_score():
    positive=make_memory(
        memory_id="MEMORY_POSITIVE",
        metadata={"negative_feedback_score":0.0}
    )
    negative=make_memory(
        memory_id="MEMORY_NEGATIVE",
        metadata={"negative_feedback_score":0.9}
    )
    service=make_retrieval_service(
        memories=[positive,negative]
    )
    result=service.retrieve(make_request())
    scores={
        candidate.memory_id:candidate.final_score
        for candidate in result.candidates
    }
    assert scores["MEMORY_POSITIVE"]>scores["MEMORY_NEGATIVE"]
def test_top_k_limits_returned_candidates():
    memories=[
        make_memory(
            memory_id=f"MEMORY_{index:03d}",
            normalized_fact=f"User prefers music style {index}."
        )
        for index in range(1,8)
    ]
    service=make_retrieval_service(memories=memories)
    result=service.retrieve(
        make_request(
            top_k=3,
            intent="User prefers music."
        )
    )
    assert result.returned_count<=3
    assert len(result.candidates)<=3
def test_candidate_limit_bounds_candidate_pool():
    memories=[
        make_memory(
            memory_id=f"MEMORY_{index:03d}",
            normalized_fact=f"User prefers music style {index}."
        )
        for index in range(1,11)
    ]
    service=make_retrieval_service(memories=memories)
    result=service.retrieve(
        make_request(
            candidate_limit=3,
            top_k=3
        )
    )
    assert result.graph_candidate_count<=3
    assert result.vector_candidate_count<=3
def test_min_score_filters_low_scoring_candidates():
    service=make_retrieval_service(
        memories=[
            make_memory(
                normalized_fact="User prefers calm acoustic music."
            )
        ]
    )
    result=service.retrieve(
        make_request(
            intent="completely unrelated topic",
            min_score=0.99
        )
    )
    assert result.decision==RetrievalDecision.NO_RESULTS
    assert result.returned_count==0
def test_graph_only_retrieval_can_work_without_embeddings():
    service=make_retrieval_service(
        memories=[
            make_memory(
                embedding_eligible=False,
                retrieval_eligible=True,
                normalized_fact="User prefers calm acoustic music."
            )
        ]
    )
    result=service.retrieve(
        make_request(
            intent="I prefer calm acoustic music.",
            vector_weight=0.0,
            graph_weight=1.0
        )
    )
    assert result.decision==RetrievalDecision.RETRIEVED
    assert result.graph_candidate_count>=1
    assert result.candidates[0].memory_id=="MEMORY_001"
def test_vector_and_graph_weights_can_be_changed():
    service=make_retrieval_service()
    result=service.retrieve(
        make_request(
            vector_weight=1.0,
            graph_weight=0.0
        )
    )
    assert result.decision==RetrievalDecision.RETRIEVED
def test_no_results_produces_explicit_no_memory_decision():
    service=make_retrieval_service(
        memories=[
            make_memory(
                status=MemoryStatus.EXPIRED,
                valid_from=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                recorded_at=datetime(2026,8,23,10,0,0,tzinfo=timezone.utc),
                valid_to=datetime(2026,8,24,10,0,0,tzinfo=timezone.utc),
                retrieval_eligible=False,
                embedding_eligible=False
            )
        ]
    )
    result=service.retrieve(
        make_request(
            intent="Something with no eligible memories."
        )
    )
    assert result.decision==RetrievalDecision.NO_RESULTS
    assert result.candidates==[]
    assert result.returned_count==0
    assert result.provenance["fallback"]=="no_memory"
def test_retrieval_version_is_preserved():
    service=RetrievalService(
        retrieval_store=InMemoryRetrievalStore(
            InMemoryGraphStore(),
            InMemoryEmbeddingStore()
        ),
        retrieval_version="2.1"
    )
    result=service.retrieve(make_request())
    assert result.retrieval_version=="2.1"
def test_retrieval_is_deterministic_for_same_store_and_request():
    service=make_retrieval_service(
        memories=[
            make_memory(
                memory_id="MEMORY_001",
                normalized_fact="User prefers calm acoustic music."
            ),
            make_memory(
                memory_id="MEMORY_002",
                normalized_fact="User prefers jazz music."
            )
        ]
    )
    request=make_request(
        intent="I want calm acoustic music."
    )
    first=service.retrieve(request)
    second=service.retrieve(request)
    assert first.model_dump()==second.model_dump()
def test_query_embedding_provider_is_deterministic():
    provider=DeterministicQueryEmbeddingProvider()
    vector_one=provider.embed_query(
        "I want calm acoustic music.",
        "test-model",
        "1.0",
        32
    )
    vector_two=provider.embed_query(
        "I want calm acoustic music.",
        "test-model",
        "1.0",
        32
    )
    assert vector_one==vector_two
def test_invalid_embedding_dimensions_are_rejected():
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    graph_service=GraphMemoryService(graph_store)
    embedding_service=EmbeddingService(embedding_store)
    memory=make_memory()
    graph_service.upsert_memory(memory)
    embedding_service.upsert_memory_embedding(
        memory,
        dimensions=32
    )
    second=make_memory(
        memory_id="MEMORY_002",
        normalized_fact="User likes jazz."
    )
    graph_service.upsert_memory(second)
    embedding_service.upsert_memory_embedding(
        second,
        dimensions=64
    )
    retrieval_store=InMemoryRetrievalStore(
        graph_store,
        embedding_store
    )
    service=RetrievalService(retrieval_store)
    with pytest.raises(RetrievalError) as exc:
        service.retrieve(make_request())
    assert exc.value.code==RetrievalErrorCode.INVALID_EMBEDDING
def test_retrieval_handles_empty_store():
    service=RetrievalService(
        InMemoryRetrievalStore(
            InMemoryGraphStore(),
            InMemoryEmbeddingStore()
        )
    )
    result=service.retrieve(make_request())
    assert result.decision==RetrievalDecision.NO_RESULTS
    assert result.returned_count==0
def test_retrieval_candidate_contains_reason():
    service=make_retrieval_service()
    result=service.retrieve(make_request())
    assert result.candidates[0].relevance_reason
def test_retrieval_result_counts_are_consistent():
    service=make_retrieval_service(
        memories=[
            make_memory(
                memory_id="MEMORY_001",
                normalized_fact="User prefers calm acoustic music."
            ),
            make_memory(
                memory_id="MEMORY_002",
                normalized_fact="User likes jazz."
            )
        ]
    )
    result=service.retrieve(
        make_request(
            intent="User music preferences."
        )
    )
    assert result.candidate_count==max(
        result.graph_candidate_count,
        result.vector_candidate_count
    ) or result.candidate_count>=result.returned_count

def test_sentence_transformer_query_provider_returns_expected_embedding():
    provider = SentenceTransformerQueryEmbeddingProvider()
    vector = provider.embed_query(text="I want calm acoustic music.",
        model_name="all-MiniLM-L6-v2",model_version="v1",dimensions=384)

    assert len(vector) == 384
    norm = sum(value * value for value in vector) ** 0.5
    assert norm == pytest.approx(1.0, rel=1e-5)    