from datetime import datetime,timezone,timedelta
import uuid
import pytest
from backend_memory_pipeline.graph_memory.graph import GraphMemoryService,InMemoryGraphStore,GraphOperation
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
from backend_memory_pipeline.embedding.embedding import EmbeddingRecordV1,InMemoryEmbeddingStore,DeterministicEmbeddingProvider
from backend_memory_pipeline.persistence.qdrant.embedding_store import QdrantEmbeddingStore
from backend_memory_pipeline.retrieval.retrieval import RetrievalService,RetrievalRequestV1,RetrievalDecision,InMemoryRetrievalStore
@pytest.fixture
def qdrant_store():
    collection_name=f"test_retrieval_{uuid.uuid4().hex}"
    store=QdrantEmbeddingStore(
        collection_name=collection_name,
        dimensions=384
    )
    store.ensure_collection()
    yield store
    try:
        store.client.delete_collection(collection_name)
    except Exception:
        pass
@pytest.fixture
def graph_service():
    return GraphMemoryService(InMemoryGraphStore())
@pytest.fixture
def retrieval_service(qdrant_store,graph_service):
    empty_embedding_store=InMemoryEmbeddingStore()
    retrieval_store=InMemoryRetrievalStore(
        graph_store=graph_service.store,
        embedding_store=empty_embedding_store
    )
    return RetrievalService(
        retrieval_store=retrieval_store,
        vector_search_store=qdrant_store,
        vector_model_name="all-MiniLM-L6-v2",
        vector_model_version="v1",
        vector_dimensions=384
    )
def make_memory(memory_id,subject_id,fact,created_at=None,valid_from=None,valid_to=None,status=MemoryStatus.ACTIVE,retrieval_eligible=True,embedding_eligible=True):
    now=created_at or datetime.now(timezone.utc)
    return MemoryRecordV1(
        memory_id=memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_type="explicit_preference",
        normalized_fact=fact,
        confidence=0.95,
        source_event_ids=[f"event-{memory_id}"],
        source_session_ids=[f"session-{memory_id}"],
        created_at=now,
        recorded_at=now,
        valid_from=valid_from or now-timedelta(days=1),
        valid_to=valid_to,
        status=status,
        retention_class="standard",
        retrieval_eligible=retrieval_eligible,
        embedding_eligible=embedding_eligible,
        entities=[],
        correction_of_memory_id=None,
        supersedes_memory_id=None,
        metadata={"source":"test"}
    )
def add_memory_to_graph(graph_service,memory):
    result=graph_service.upsert_memory(memory)
    assert result.operation in {GraphOperation.UPSERT,GraphOperation.UPDATE}
def add_embedding_to_qdrant(qdrant_store,memory):
    provider=DeterministicEmbeddingProvider()
    vector=provider.embed(
        memory.normalized_fact,
        "all-MiniLM-L6-v2",
        "v1",
        384
    )
    record=EmbeddingRecordV1(
        embedding_id=f"embedding-{memory.memory_id}",
        memory_id=memory.memory_id,
        subject_id=memory.subject_id,
        subject_scope=memory.subject_scope,
        vector=vector,
        dimensions=384,
        model_name="all-MiniLM-L6-v2",
        model_version="v1",
        content_hash=memory.normalized_fact,
        approved_text_fields=[memory.normalized_fact],
        created_at=memory.created_at,
        recorded_at=memory.created_at,
        memory_status=memory.status,
        retrieval_eligible=memory.retrieval_eligible,
        embedding_eligible=memory.embedding_eligible,
        source_event_ids=list(memory.source_event_ids),
        source_session_ids=list(memory.source_session_ids),
        metadata={"source":"test"}
    )
    qdrant_store.upsert(record)
    return record
def test_retrieval_service_uses_qdrant_for_vector_search(retrieval_service,qdrant_store,graph_service):
    subject_id="user-qdrant-1"
    memory=make_memory(
        "memory-qdrant-1",
        subject_id,
        "User prefers calm acoustic music."
    )
    add_memory_to_graph(graph_service,memory)
    add_embedding_to_qdrant(qdrant_store,memory)
    request=RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent="User prefers calm acoustic music.",
        surface="chat",
        locale="en-IN",
        requested_at=datetime.now(timezone.utc),
        candidate_limit=10,
        vector_weight=1.0,
        graph_weight=0.0
    )
    result=retrieval_service.retrieve(request)
    assert result.decision==RetrievalDecision.RETRIEVED
    assert result.returned_count==1
    assert result.candidates[0].memory_id==memory.memory_id
    assert result.provenance["vector_source"]=="qdrant"
def test_qdrant_vector_result_is_used_when_inmemory_embedding_store_is_empty(retrieval_service,qdrant_store,graph_service):
    subject_id="user-qdrant-2"
    memory=make_memory(
        "memory-qdrant-2",
        subject_id,
        "User likes mellow jazz playlists."
    )
    add_memory_to_graph(graph_service,memory)
    add_embedding_to_qdrant(qdrant_store,memory)
    assert retrieval_service.store.embeddings(subject_id)==[]
    request=RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent="User likes mellow jazz playlists.",
        surface="chat",
        locale="en-IN",
        requested_at=datetime.now(timezone.utc),
        candidate_limit=10,
        vector_weight=1.0,
        graph_weight=0.0
    )
    result=retrieval_service.retrieve(request)
    assert result.decision==RetrievalDecision.RETRIEVED
    assert result.candidates[0].memory_id==memory.memory_id
    assert result.provenance["vector_source"]=="qdrant"
def test_qdrant_retrieval_respects_subject_isolation(retrieval_service,qdrant_store,graph_service):
    memory_a=make_memory(
        "memory-subject-a",
        "user-a",
        "User prefers classical piano music."
    )
    memory_b=make_memory(
        "memory-subject-b",
        "user-b",
        "User prefers classical piano music."
    )
    add_memory_to_graph(graph_service,memory_a)
    add_memory_to_graph(graph_service,memory_b)
    add_embedding_to_qdrant(qdrant_store,memory_a)
    add_embedding_to_qdrant(qdrant_store,memory_b)
    request=RetrievalRequestV1(
        subject_id="user-a",
        subject_scope="user-a",
        intent="User prefers classical piano music.",
        surface="chat",
        locale="en-IN",
        requested_at=datetime.now(timezone.utc),
        candidate_limit=10,
        vector_weight=1.0,
        graph_weight=0.0
    )
    result=retrieval_service.retrieve(request)
    assert result.decision==RetrievalDecision.RETRIEVED
    assert all(candidate.memory_id=="memory-subject-a" for candidate in result.candidates)
    assert "memory-subject-b" not in {candidate.memory_id for candidate in result.candidates}
def test_qdrant_retrieval_preserves_graph_candidate_union(retrieval_service,qdrant_store,graph_service):
    subject_id="user-hybrid-1"
    memory=make_memory(
        "memory-hybrid-1",
        subject_id,
        "User enjoys acoustic folk music."
    )
    add_memory_to_graph(graph_service,memory)
    add_embedding_to_qdrant(qdrant_store,memory)
    request=RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent="User enjoys acoustic folk music.",
        surface="chat",
        locale="en-IN",
        requested_at=datetime.now(timezone.utc),
        candidate_limit=10,
        vector_weight=0.7,
        graph_weight=0.3
    )
    result=retrieval_service.retrieve(request)
    assert result.decision==RetrievalDecision.RETRIEVED
    assert result.candidates[0].memory_id==memory.memory_id
    assert result.candidates[0].vector_score is not None
    assert result.candidates[0].graph_score is not None
    assert result.provenance["vector_source"]=="qdrant"
def test_graph_only_retrieval_does_not_require_qdrant(retrieval_service,graph_service):
    subject_id="user-graph-only"
    memory=make_memory(
        "memory-graph-only",
        subject_id,
        "User prefers instrumental music."
    )
    add_memory_to_graph(graph_service,memory)
    request=RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent="instrumental music",
        surface="chat",
        locale="en-IN",
        requested_at=datetime.now(timezone.utc),
        candidate_limit=10,
        vector_weight=0.0,
        graph_weight=1.0
    )
    result=retrieval_service.retrieve(request)
    assert result.decision==RetrievalDecision.RETRIEVED
    assert result.candidates[0].memory_id==memory.memory_id