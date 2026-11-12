import pytest
from datetime import datetime,timezone,timedelta
from backend_memory_pipeline.embedding.embedding import EmbeddingService,EmbeddingError,EmbeddingErrorCode
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
from backend_memory_pipeline.persistence.qdrant.embedding_store import QdrantEmbeddingStore
def create_memory(
    memory_id,
    subject_id="user-vector-1",
    normalized_fact="User likes rock music.",
    status=MemoryStatus.ACTIVE,
    retrieval_eligible=True,
    embedding_eligible=True,
    valid_to=None
):
    timestamp=datetime.now(timezone.utc)
    if status!=MemoryStatus.ACTIVE and valid_to is None:
        valid_to=timestamp+timedelta(days=1)
    return MemoryRecordV1(
        memory_id=memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_type="explicit_preference",
        normalized_fact=normalized_fact,
        confidence=0.99,
        source_event_ids=[f"event-{memory_id}"],
        source_session_ids=[f"session-{memory_id}"],
        created_at=timestamp,
        recorded_at=timestamp,
        valid_from=timestamp,
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
@pytest.fixture
def qdrant_store():
    collection_name="spotify_memory_vector_search_test"
    store=QdrantEmbeddingStore(
        url="http://localhost:6333",
        collection_name=collection_name,
        dimensions=384
    )
    store.verify_connectivity()
    store.ensure_collection(dimensions=384)
    yield store
    try:
        store.client.delete_collection(collection_name)
    except Exception:
        pass
    store.close()
@pytest.fixture
def embedding_service(qdrant_store):
    return EmbeddingService(store=qdrant_store)
def create_embedding(embedding_service,memory):
    return embedding_service.upsert_memory_embedding(
        memory=memory,
        correlation_id=f"correlation-{memory.memory_id}"
    )
def insert_modified_embedding(
    qdrant_store,
    embedding_record,
    **payload_changes
):
    payload=qdrant_store._record_to_payload(embedding_record)
    payload.update(payload_changes)
    qdrant_store.client.upsert(
        collection_name=qdrant_store.collection_name,
        points=[
            {
                "id":qdrant_store._point_id(embedding_record.memory_id),
                "vector":embedding_record.vector,
                "payload":payload
            }
        ],
        wait=True
    )
def test_qdrant_vector_search_returns_matching_memory(
    embedding_service,
    qdrant_store
):
    memory=create_memory(
        memory_id="memory-rock",
        normalized_fact="User likes rock music."
    )
    create_embedding(embedding_service,memory)
    stored=qdrant_store.get("memory-rock")
    assert stored is not None
    results=qdrant_store.search(
        query_vector=stored.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=5
    )
    assert len(results)>=1
    assert results[0].record.memory_id=="memory-rock"
    assert results[0].record.subject_id=="user-vector-1"
    assert results[0].score==pytest.approx(1.0,rel=1e-5,abs=1e-5)
def test_qdrant_vector_search_returns_results_in_similarity_order(
    embedding_service,
    qdrant_store
):
    rock=create_memory(
        memory_id="memory-rock",
        normalized_fact="User likes rock music."
    )
    jazz=create_memory(
        memory_id="memory-jazz",
        normalized_fact="User likes jazz music."
    )
    classical=create_memory(
        memory_id="memory-classical",
        normalized_fact="User likes classical music."
    )
    create_embedding(embedding_service,rock)
    create_embedding(embedding_service,jazz)
    create_embedding(embedding_service,classical)
    query_embedding=qdrant_store.get("memory-rock")
    assert query_embedding is not None
    results=qdrant_store.search(
        query_vector=query_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=3
    )
    assert len(results)==3
    assert results[0].record.memory_id=="memory-rock"
    assert results[0].score>=results[1].score
    assert results[1].score>=results[2].score
def test_qdrant_vector_search_is_subject_scoped(
    embedding_service,
    qdrant_store
):
    user_one_memory=create_memory(
        memory_id="memory-user-one",
        subject_id="user-vector-1",
        normalized_fact="User likes rock music."
    )
    user_two_memory=create_memory(
        memory_id="memory-user-two",
        subject_id="user-vector-2",
        normalized_fact="User likes rock music."
    )
    create_embedding(embedding_service,user_one_memory)
    create_embedding(embedding_service,user_two_memory)
    query_embedding=qdrant_store.get("memory-user-one")
    assert query_embedding is not None
    results=qdrant_store.search(
        query_vector=query_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=10
    )
    result_ids={result.record.memory_id for result in results}
    assert "memory-user-one" in result_ids
    assert "memory-user-two" not in result_ids
    assert all(
        result.record.subject_id=="user-vector-1"
        for result in results
    )
def test_qdrant_vector_search_requires_matching_subject_scope(
    qdrant_store
):
    with pytest.raises(EmbeddingError) as exc_info:
        qdrant_store.search(
            query_vector=[0.0]*384,
            subject_id="user-vector-1",
            subject_scope="user-vector-2",
            limit=5
        )
    assert exc_info.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_qdrant_vector_search_rejects_wrong_query_dimensions(
    qdrant_store
):
    with pytest.raises(EmbeddingError) as exc_info:
        qdrant_store.search(
            query_vector=[0.0]*128,
            subject_id="user-vector-1",
            subject_scope="user-vector-1",
            limit=5
        )
    assert exc_info.value.code==EmbeddingErrorCode.DIMENSION_MISMATCH
def test_qdrant_vector_search_rejects_empty_query_vector(
    qdrant_store
):
    with pytest.raises(EmbeddingError) as exc_info:
        qdrant_store.search(
            query_vector=[],
            subject_id="user-vector-1",
            subject_scope="user-vector-1",
            limit=5
        )
    assert exc_info.value.code==EmbeddingErrorCode.INVALID_PROVIDER
def test_qdrant_vector_search_respects_limit(
    embedding_service,
    qdrant_store
):
    for index in range(1,8):
        memory=create_memory(
            memory_id=f"memory-limit-{index}",
            normalized_fact=f"User likes music style {index}."
        )
        create_embedding(embedding_service,memory)
    query_embedding=qdrant_store.get("memory-limit-1")
    assert query_embedding is not None
    results=qdrant_store.search(
        query_vector=query_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=3
    )
    assert len(results)<=3
def test_qdrant_vector_search_excludes_inactive_memory(
    embedding_service,
    qdrant_store
):
    active_memory=create_memory(
        memory_id="memory-active",
        status=MemoryStatus.ACTIVE,
        retrieval_eligible=True,
        embedding_eligible=True
    )
    expired_memory=create_memory(
        memory_id="memory-expired",
        status=MemoryStatus.EXPIRED,
        retrieval_eligible=False,
        embedding_eligible=False
    )
    create_embedding(embedding_service,active_memory)
    active_embedding=qdrant_store.get("memory-active")
    assert active_embedding is not None
    expired_embedding_vector=[0.01]*384
    expired_payload={
        "embedding_id":"embedding:memory-expired",
        "memory_id":"memory-expired",
        "subject_id":"user-vector-1",
        "subject_scope":"user-vector-1",
        "dimensions":384,
        "model_name":"all-MiniLM-L6-v2",
        "model_version":"v1",
        "approved_text_fields":["normalized_fact"],
        "content_hash":"test-expired-hash",
        "memory_status":MemoryStatus.EXPIRED.value,
        "retrieval_eligible":False,
        "embedding_eligible":False,
        "source_event_ids":["event-memory-expired"],
        "source_session_ids":["session-memory-expired"],
        "recorded_at":expired_memory.recorded_at.isoformat(),
        "created_at":expired_memory.created_at.isoformat(),
        "deleted":False,
        "metadata_json":"{}"
    }
    qdrant_store.client.upsert(
        collection_name=qdrant_store.collection_name,
        points=[
            {
                "id":qdrant_store._point_id("memory-expired"),
                "vector":expired_embedding_vector,
                "payload":expired_payload
            }
        ],
        wait=True
    )
    results=qdrant_store.search(
        query_vector=active_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=10
    )
    result_ids={result.record.memory_id for result in results}
    assert "memory-active" in result_ids
    assert "memory-expired" not in result_ids
def test_qdrant_vector_search_excludes_retrieval_ineligible_memory(
    embedding_service,
    qdrant_store
):
    eligible_memory=create_memory(
        memory_id="memory-eligible",
        retrieval_eligible=True,
        embedding_eligible=True
    )
    ineligible_memory=create_memory(
        memory_id="memory-ineligible",
        retrieval_eligible=False,
        embedding_eligible=True
    )
    create_embedding(embedding_service,eligible_memory)
    create_embedding(embedding_service,ineligible_memory)
    stored=qdrant_store.get("memory-ineligible")
    assert stored is not None
    insert_modified_embedding(
        qdrant_store,
        stored,
        retrieval_eligible=False
    )
    query_embedding=qdrant_store.get("memory-eligible")
    assert query_embedding is not None
    results=qdrant_store.search(
        query_vector=query_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=10
    )
    result_ids={result.record.memory_id for result in results}
    assert "memory-eligible" in result_ids
    assert "memory-ineligible" not in result_ids
def test_qdrant_vector_search_excludes_embedding_ineligible_memory(
    embedding_service,
    qdrant_store
):
    eligible_memory=create_memory(
        memory_id="memory-eligible",
        retrieval_eligible=True,
        embedding_eligible=True
    )
    ineligible_memory=create_memory(
        memory_id="memory-no-embedding",
        retrieval_eligible=True,
        embedding_eligible=True
    )
    create_embedding(embedding_service,eligible_memory)
    create_embedding(embedding_service,ineligible_memory)
    stored=qdrant_store.get("memory-no-embedding")
    assert stored is not None
    insert_modified_embedding(
        qdrant_store,
        stored,
        embedding_eligible=False
    )
    query_embedding=qdrant_store.get("memory-eligible")
    assert query_embedding is not None
    results=qdrant_store.search(
        query_vector=query_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=10
    )
    result_ids={result.record.memory_id for result in results}
    assert "memory-eligible" in result_ids
    assert "memory-no-embedding" not in result_ids
def test_qdrant_vector_search_excludes_deleted_embedding(
    embedding_service,
    qdrant_store
):
    active_memory=create_memory(
        memory_id="memory-active",
        retrieval_eligible=True,
        embedding_eligible=True
    )
    deleted_memory=create_memory(
        memory_id="memory-deleted",
        retrieval_eligible=True,
        embedding_eligible=True
    )
    create_embedding(embedding_service,active_memory)
    create_embedding(embedding_service,deleted_memory)
    deleted_record=qdrant_store.get("memory-deleted")
    assert deleted_record is not None
    insert_modified_embedding(
        qdrant_store,
        deleted_record,
        deleted=True
    )
    query_embedding=qdrant_store.get("memory-active")
    assert query_embedding is not None
    results=qdrant_store.search(
        query_vector=query_embedding.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=10
    )
    result_ids={result.record.memory_id for result in results}
    assert "memory-active" in result_ids
    assert "memory-deleted" not in result_ids
def test_qdrant_vector_search_returns_embedding_metadata(
    embedding_service,
    qdrant_store
):
    memory=create_memory(
        memory_id="memory-metadata",
        normalized_fact="User likes acoustic music."
    )
    create_embedding(embedding_service,memory)
    stored=qdrant_store.get("memory-metadata")
    assert stored is not None
    results=qdrant_store.search(
        query_vector=stored.vector,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=5
    )
    assert len(results)>=1
    result=results[0]
    assert result.record.memory_id=="memory-metadata"
    assert result.record.embedding_id=="embedding:memory-metadata"
    assert result.record.model_name=="all-MiniLM-L6-v2"
    assert result.record.model_version=="v1"
    assert result.record.dimensions==384
    assert result.record.retrieval_eligible is True
    assert result.record.embedding_eligible is True
def test_qdrant_vector_search_empty_collection_returns_empty_results(
    qdrant_store
):
    results=qdrant_store.search(
        query_vector=[0.0]*384,
        subject_id="user-vector-1",
        subject_scope="user-vector-1",
        limit=5
    )
    assert results==[]