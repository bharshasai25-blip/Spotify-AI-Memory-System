import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryRecordV1,
    MemoryStatus
)
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryType
from backend_memory_pipeline.policy_consent.policy_consent import RetentionClass
from backend_memory_pipeline.embedding.embedding import (DeterministicEmbeddingProvider,EmbeddingError,EmbeddingErrorCode,
    EmbeddingOperation,EmbeddingRecordV1,EmbeddingService,InMemoryEmbeddingStore,SentenceTransformerEmbeddingProvider)

def make_memory(
    memory_id="MEMORY_001",
    subject_id="TEST_USER_001",
    normalized_fact="User prefers calm acoustic music.",
    status=MemoryStatus.ACTIVE,
    retrieval_eligible=True,
    embedding_eligible=True,
    valid_to=None,
    source_event_ids=None,
    source_session_ids=None
):
    timestamp=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    return MemoryRecordV1(
        memory_id=memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        normalized_fact=normalized_fact,
        entities=[],
        confidence=0.95,
        source_event_ids=source_event_ids or ["SOURCE_001"],
        source_session_ids=source_session_ids or ["SESSION_001"],
        created_at=timestamp,
        recorded_at=timestamp,
        valid_from=timestamp,
        valid_to=valid_to,
        status=status,
        retention_class=RetentionClass.LONG,
        retrieval_eligible=retrieval_eligible,
        embedding_eligible=embedding_eligible,
        metadata={"policy_version":"1.0"}
    )
def test_active_eligible_memory_creates_embedding():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    result=service.upsert_memory_embedding(memory)
    assert result.operation==EmbeddingOperation.CREATE
    assert result.changed is True
    assert result.memory_id=="MEMORY_001"
    assert result.subject_id=="TEST_USER_001"
    assert result.embedding_record is not None
    assert result.embedding_record.embedding_id=="embedding:MEMORY_001"
def test_embedding_dimensions_match_requested_dimensions():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    result=service.upsert_memory_embedding(
        make_memory(),
        dimensions=128
    )
    assert result.dimensions==128
    assert result.embedding_record is not None
    assert result.embedding_record.dimensions==128
    assert len(result.embedding_record.vector)==128
def test_embedding_vector_is_normalized():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    result=service.upsert_memory_embedding(
        make_memory(),
        dimensions=64
    )
    vector=result.embedding_record.vector
    norm=sum(value*value for value in vector) ** 0.5
    assert norm==pytest.approx(1.0,rel=1e-6)
def test_embedding_preserves_memory_identity():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    result=service.upsert_memory_embedding(memory)
    record=result.embedding_record
    assert record.memory_id==memory.memory_id
    assert record.subject_id==memory.subject_id
    assert record.subject_scope==memory.subject_scope
def test_embedding_preserves_provenance():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory(
        source_event_ids=["SOURCE_001","SOURCE_002"],
        source_session_ids=["SESSION_001","SESSION_002"]
    )
    result=service.upsert_memory_embedding(memory)
    record=result.embedding_record
    assert record.source_event_ids==[
        "SOURCE_001",
        "SOURCE_002"
    ]
    assert record.source_session_ids==[
        "SESSION_001",
        "SESSION_002"
    ]
def test_embedding_preserves_model_metadata():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    result=service.upsert_memory_embedding(
        make_memory(),
        model_name="test-model",
        model_version="2.1",
        dimensions=256
    )
    record=result.embedding_record
    assert record.model_name=="test-model"
    assert record.model_version=="2.1"
    assert record.dimensions==256
def test_embedding_records_approved_text_fields():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    result=service.upsert_memory_embedding(
        make_memory(),
        approved_text_fields=["normalized_fact"]
    )
    assert result.embedding_record.approved_text_fields==[
        "normalized_fact"
    ]
def test_embedding_content_hash_is_deterministic():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    first=service.upsert_memory_embedding(memory)
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    second=service.upsert_memory_embedding(memory)
    assert first.content_hash==second.content_hash
    assert first.embedding_record.vector==second.embedding_record.vector
def test_identical_embedding_write_is_idempotent():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    first=service.upsert_memory_embedding(memory)
    second=service.upsert_memory_embedding(memory)
    assert first.changed is True
    assert second.changed is False
    assert second.metadata["idempotent"] is True
    assert second.embedding_id==first.embedding_id
def test_embedding_update_occurs_when_memory_text_changes():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    first=service.upsert_memory_embedding(memory)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User prefers instrumental jazz."
        }
    )
    second=service.upsert_memory_embedding(updated)
    assert second.operation==EmbeddingOperation.UPDATE
    assert second.changed is True
    assert second.content_hash!=first.content_hash
    stored=store.get(memory.memory_id)
    assert stored.content_hash==second.content_hash
def test_embedding_update_occurs_when_model_version_changes():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    first=service.upsert_memory_embedding(
        memory,
        model_name="test-model",
        model_version="1.0"
    )
    second=service.upsert_memory_embedding(
        memory,
        model_name="test-model",
        model_version="2.0"
    )
    assert second.operation==EmbeddingOperation.UPDATE
    assert second.changed is True
    assert second.model_version=="2.0"
    assert second.content_hash!=first.content_hash
def test_embedding_requires_embedding_eligibility():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory(
        embedding_eligible=False
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(memory)
    assert exc.value.code==EmbeddingErrorCode.EMBEDDING_NOT_ELIGIBLE
def test_deleted_memory_cannot_receive_new_embedding():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory(
        status=MemoryStatus.DELETED,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(memory)
    assert exc.value.code==EmbeddingErrorCode.MEMORY_DELETED
def test_pending_deletion_memory_cannot_receive_new_embedding():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory(
        status=MemoryStatus.PENDING_DELETION,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(memory)
    assert exc.value.code==EmbeddingErrorCode.MEMORY_DELETED
def test_subject_scope_mismatch_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    memory=memory.model_copy(
        update={
            "subject_scope":"TEST_USER_999"
        }
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(memory)
    assert exc.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_cross_subject_existing_embedding_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory(
        subject_id="TEST_USER_001"
    )
    service.upsert_memory_embedding(memory)
    cross_subject=memory.model_copy(
        update={
            "subject_id":"TEST_USER_999",
            "subject_scope":"TEST_USER_999"
        }
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(cross_subject)
    assert exc.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_embedding_retrieval_is_subject_scoped():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    service.upsert_memory_embedding(
        make_memory(
            subject_id="TEST_USER_001"
        )
    )
    record=service.get_memory_embedding(
        "MEMORY_001",
        "TEST_USER_001"
    )
    assert record.memory_id=="MEMORY_001"
    assert record.subject_id=="TEST_USER_001"
def test_embedding_retrieval_cross_subject_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    service.upsert_memory_embedding(
        make_memory(
            subject_id="TEST_USER_001"
        )
    )
    with pytest.raises(EmbeddingError) as exc:
        service.get_memory_embedding(
            "MEMORY_001",
            "TEST_USER_999"
        )
    assert exc.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_missing_embedding_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    with pytest.raises(EmbeddingError) as exc:
        service.get_memory_embedding(
            "MEMORY_UNKNOWN",
            "TEST_USER_001"
        )
    assert exc.value.code==EmbeddingErrorCode.EMBEDDING_NOT_FOUND
def test_delete_embedding_removes_vector_record():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    created=service.upsert_memory_embedding(memory)
    result=service.delete_memory_embedding(
        memory.memory_id,
        memory.subject_id
    )
    assert created.embedding_record is not None
    assert result.operation==EmbeddingOperation.DELETE
    assert result.changed is True
    assert store.get(memory.memory_id) is None
def test_delete_embedding_cross_subject_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    service.upsert_memory_embedding(memory)
    with pytest.raises(EmbeddingError) as exc:
        service.delete_memory_embedding(
            memory.memory_id,
            "TEST_USER_999"
        )
    assert exc.value.code==EmbeddingErrorCode.SUBJECT_MISMATCH
def test_delete_missing_embedding_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    with pytest.raises(EmbeddingError) as exc:
        service.delete_memory_embedding(
            "MEMORY_UNKNOWN",
            "TEST_USER_001"
        )
    assert exc.value.code==EmbeddingErrorCode.EMBEDDING_NOT_FOUND
def test_unsupported_embedding_field_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(
            make_memory(),
            approved_text_fields=["metadata"]
        )
    assert exc.value.code==EmbeddingErrorCode.INVALID_MEMORY
def test_empty_approved_embedding_text_is_rejected():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory(
        normalized_fact="   "
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(memory)
    assert exc.value.code==EmbeddingErrorCode.INVALID_MEMORY
    
def test_provider_dimension_mismatch_is_rejected():
    class WrongDimensionProvider:
        def embed(self,text,model_name,model_version,dimensions):
            return [0.1,0.2]
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(
        store=store,
        provider=WrongDimensionProvider()
    )
    with pytest.raises(EmbeddingError) as exc:
        service.upsert_memory_embedding(
            make_memory(),
            dimensions=384
        )
    assert exc.value.code==EmbeddingErrorCode.DIMENSION_MISMATCH
def test_deterministic_provider_is_reproducible():
    provider=DeterministicEmbeddingProvider()
    vector_one=provider.embed(
        "User prefers jazz.",
        "test-model",
        "1.0",
        32
    )
    vector_two=provider.embed(
        "User prefers jazz.",
        "test-model",
        "1.0",
        32
    )
    assert vector_one==vector_two
def test_different_text_produces_different_embedding():
    provider=DeterministicEmbeddingProvider()
    vector_one=provider.embed(
        "User prefers jazz.",
        "test-model",
        "1.0",
        32
    )
    vector_two=provider.embed(
        "User prefers classical music.",
        "test-model",
        "1.0",
        32
    )
    assert vector_one!=vector_two
def test_embedding_record_schema_rejects_dimension_mismatch():
    with pytest.raises(ValueError,match="dimensions must match vector length"):
        EmbeddingRecordV1(
            embedding_id="embedding:MEMORY_001",
            memory_id="MEMORY_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            vector=[0.1,0.2],
            dimensions=3,
            model_name="test-model",
            model_version="1.0",
            approved_text_fields=["normalized_fact"],
            content_hash="HASH_001",
            memory_status=MemoryStatus.ACTIVE,
            retrieval_eligible=True,
            embedding_eligible=True,
            source_event_ids=["SOURCE_001"],
            source_session_ids=["SESSION_001"],
            recorded_at=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
            created_at=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
        )
def test_embedding_record_preserves_deletion_status_metadata():
    timestamp=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    record=EmbeddingRecordV1(
        embedding_id="embedding:MEMORY_001",
        memory_id="MEMORY_001",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        vector=[0.5,0.5],
        dimensions=2,
        model_name="test-model",
        model_version="1.0",
        approved_text_fields=["normalized_fact"],
        content_hash="HASH_001",
        memory_status=MemoryStatus.PENDING_DELETION,
        retrieval_eligible=False,
        embedding_eligible=False,
        source_event_ids=["SOURCE_001"],
        source_session_ids=["SESSION_001"],
        recorded_at=timestamp,
        created_at=timestamp,
        deleted=False
    )
    assert record.memory_status==MemoryStatus.PENDING_DELETION
    assert record.embedding_eligible is False
    assert record.retrieval_eligible is False
def test_embedding_content_hash_changes_when_approved_fields_change():
    store=InMemoryEmbeddingStore()
    service=EmbeddingService(store)
    memory=make_memory()
    first=service.upsert_memory_embedding(
        memory,
        approved_text_fields=["normalized_fact"]
    )
    updated=memory.model_copy(
        update={
            "normalized_fact":"User prefers jazz."
        }
    )
    second=service.upsert_memory_embedding(
        updated,
        approved_text_fields=["normalized_fact"]
    )
    assert first.content_hash!=second.content_hash

def test_sentence_transformer_provider_returns_expected_embedding():
    provider = SentenceTransformerEmbeddingProvider()
    vector = provider.embed(
        text="User prefers calm acoustic music.",
        model_name="all-MiniLM-L6-v2",
        model_version="v1",
        dimensions=384)

    assert len(vector) == 384
    norm = sum(value * value for value in vector) ** 0.5
    assert norm == pytest.approx(1.0, rel=1e-5)    