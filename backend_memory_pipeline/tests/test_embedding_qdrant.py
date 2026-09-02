from datetime import datetime,timezone
import pytest
from backend_memory_pipeline.embedding.embedding import EmbeddingService,EmbeddingError,EmbeddingErrorCode
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
from backend_memory_pipeline.persistence.qdrant.embedding_store import QdrantEmbeddingStore
def create_memory(memory_id="memory-qdrant-1",subject_id="user-qdrant-1",normalized_fact="User likes rock music."):
    timestamp=datetime.now(timezone.utc)
    return {
        "memory_id":memory_id,
        "subject_id":subject_id,
        "subject_scope":subject_id,
        "memory_type":"explicit_preference",
        "normalized_fact":normalized_fact,
        "confidence":0.99,
        "source_event_ids":["event-qdrant-1"],
        "source_session_ids":["session-qdrant-1"],
        "created_at":timestamp,
        "recorded_at":timestamp,
        "valid_from":timestamp,
        "valid_to":None,
        "status":MemoryStatus.ACTIVE,
        "retention_class":"standard",
        "retrieval_eligible":True,
        "embedding_eligible":True,
        "entities":[],
        "correction_of_memory_id":None,
        "supersedes_memory_id":None,
        "metadata":{"source":"test"}
    }
@pytest.fixture
def qdrant_store():
    collection_name="spotify_memory_embeddings_test"
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
def test_qdrant_embedding_create(embedding_service,qdrant_store):
    memory=MemoryRecordV1(**create_memory())
    result=embedding_service.upsert_memory_embedding(
        memory=memory,
        correlation_id="correlation-qdrant-1"
    )
    assert result.operation.value=="create"
    assert result.changed is True
    assert result.dimensions==384
    assert result.embedding_record is not None
    assert len(result.embedding_record.vector)==384
    stored=qdrant_store.get("memory-qdrant-1")
    assert stored is not None
    assert stored.memory_id=="memory-qdrant-1"
    assert stored.embedding_id=="embedding:memory-qdrant-1"
    assert stored.subject_id=="user-qdrant-1"
    assert stored.subject_scope=="user-qdrant-1"
    assert stored.dimensions==384
    assert stored.memory_status==MemoryStatus.ACTIVE
    assert stored.retrieval_eligible is True
    assert stored.embedding_eligible is True
def test_qdrant_embedding_is_idempotent(embedding_service,qdrant_store):
    memory=MemoryRecordV1(**create_memory())
    first=embedding_service.upsert_memory_embedding(
        memory=memory,
        correlation_id="correlation-qdrant-2"
    )
    second=embedding_service.upsert_memory_embedding(
        memory=memory,
        correlation_id="correlation-qdrant-2"
    )
    assert first.changed is True
    assert second.changed is False
    assert second.operation.value=="update"
    assert second.metadata["idempotent"] is True
    assert second.embedding_record is not None
    stored=qdrant_store.get("memory-qdrant-1")
    assert stored is not None
    assert stored.memory_id=="memory-qdrant-1"
    assert stored.vector==pytest.approx(first.embedding_record.vector,rel=1e-5,abs=1e-6)
    #assert stored.vector==first.embedding_record.vector
def test_qdrant_embedding_updates_when_content_changes(embedding_service,qdrant_store):
    first_memory=MemoryRecordV1(**create_memory())
    second_memory=MemoryRecordV1(
        **create_memory(
            normalized_fact="User likes jazz music."
        )
    )
    first=embedding_service.upsert_memory_embedding(
        memory=first_memory,
        correlation_id="correlation-qdrant-3"
    )
    second=embedding_service.upsert_memory_embedding(
        memory=second_memory,
        correlation_id="correlation-qdrant-4"
    )
    assert first.changed is True
    assert second.changed is True
    assert second.operation.value=="update"
    assert second.embedding_record is not None
    assert second.content_hash!=first.content_hash
    assert second.embedding_record.vector!=first.embedding_record.vector
    stored=qdrant_store.get("memory-qdrant-1")
    assert stored is not None
    assert stored.content_hash==second.content_hash
    assert stored.vector==pytest.approx(second.embedding_record.vector,rel=1e-5,abs=1e-6)
    #assert stored.vector==second.embedding_record.vector
def test_qdrant_embedding_rejects_cross_subject_update(embedding_service):
    first_memory=MemoryRecordV1(**create_memory())
    second_memory=MemoryRecordV1(
        **create_memory(
            subject_id="different-user"
        )
    )
    embedding_service.upsert_memory_embedding(
        memory=first_memory,
        correlation_id="correlation-qdrant-5"
    )
    with pytest.raises(EmbeddingError) as exc_info:
        embedding_service.upsert_memory_embedding(
            memory=second_memory,
            correlation_id="correlation-qdrant-6"
        )
    assert exc_info.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_qdrant_embedding_delete(qdrant_store):
    memory=MemoryRecordV1(**create_memory())
    service=EmbeddingService(store=qdrant_store)
    created=service.upsert_memory_embedding(
        memory=memory,
        correlation_id="correlation-qdrant-7"
    )
    assert created.changed is True
    deleted=service.delete_memory_embedding(
        memory_id="memory-qdrant-1",
        subject_id="user-qdrant-1"
    )
    assert deleted.operation.value=="delete"
    assert deleted.changed is True
    assert deleted.embedding_id=="embedding:memory-qdrant-1"
    assert qdrant_store.get("memory-qdrant-1") is None
def test_qdrant_embedding_rejects_cross_subject_delete(qdrant_store):
    memory=MemoryRecordV1(**create_memory())
    service=EmbeddingService(store=qdrant_store)
    service.upsert_memory_embedding(
        memory=memory,
        correlation_id="correlation-qdrant-8"
    )
    with pytest.raises(EmbeddingError) as exc_info:
        service.delete_memory_embedding(
            memory_id="memory-qdrant-1",
            subject_id="different-user"
        )
    assert exc_info.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_qdrant_collection_dimension_mismatch():
    collection_name="spotify_memory_embeddings_dimension_test"
    store=QdrantEmbeddingStore(
        url="http://localhost:6333",
        collection_name=collection_name,
        dimensions=384
    )
    store.ensure_collection(dimensions=384)
    try:
        with pytest.raises(EmbeddingError) as exc_info:
            store.ensure_collection(dimensions=128)
        assert exc_info.value.code==EmbeddingErrorCode.DIMENSION_MISMATCH
    finally:
        try:
            store.client.delete_collection(collection_name)
        except Exception:
            pass
        store.close()