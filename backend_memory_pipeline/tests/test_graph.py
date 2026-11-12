import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryLifecycleAction,
    MemoryLifecycleService,
    MemoryRecordV1,
    MemoryStatus,
    InMemoryMemoryStore
)
from backend_memory_pipeline.graph_memory.graph import (
    GraphMemoryError,
    GraphMemoryErrorCode,
    GraphMemoryRecordV1,
    GraphMemoryService,
    GraphNodeType,
    GraphOperation,
    GraphRelationshipType,
    GraphNodeV1,
    GraphRelationshipV1,
    InMemoryGraphStore
)
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryType
from backend_memory_pipeline.policy_consent.policy_consent import RetentionClass
def make_memory(
    memory_id="MEMORY_001",
    subject_id="TEST_USER_001",
    status=MemoryStatus.ACTIVE,
    normalized_fact="User prefers calm acoustic music.",
    valid_from=None,
    valid_to=None,
    entities=None,
    supersedes_memory_id=None,
    correction_of_memory_id=None,
    retrieval_eligible=True,
    embedding_eligible=True
):
    valid_from=valid_from or datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    return MemoryRecordV1(
        memory_id=memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        normalized_fact=normalized_fact,
        entities=entities or [],
        confidence=0.95,
        source_event_ids=["SOURCE_001"],
        source_session_ids=["SESSION_001"],
        created_at=valid_from,
        recorded_at=valid_from,
        valid_from=valid_from,
        valid_to=valid_to,
        status=status,
        retention_class=RetentionClass.LONG,
        retrieval_eligible=retrieval_eligible,
        embedding_eligible=embedding_eligible,
        correction_of_memory_id=correction_of_memory_id,
        supersedes_memory_id=supersedes_memory_id,
        metadata={"policy_version":"1.0"}
    )
def test_upsert_active_memory_creates_graph_node():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    result=service.upsert_memory(memory)
    assert result.operation==GraphOperation.UPSERT
    assert result.changed is True
    assert result.memory_id=="MEMORY_001"
    assert result.subject_id=="TEST_USER_001"
    assert result.memory_node.node_type==GraphNodeType.MEMORY
    assert result.memory_node.node_id=="memory:MEMORY_001"
    stored=store.get_memory("MEMORY_001")
    assert stored is not None
    assert stored.normalized_fact==memory.normalized_fact
def test_upsert_creates_subject_node():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    service.upsert_memory(make_memory())
    subject_node=store.get_node("subject:TEST_USER_001")
    assert subject_node is not None
    assert subject_node.node_type==GraphNodeType.SUBJECT
    assert subject_node.subject_id=="TEST_USER_001"
def test_upsert_creates_subject_memory_relationship():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    result=service.upsert_memory(make_memory())
    relationship_ids={
        relationship.relationship_id
        for relationship in result.relationships
    }
    assert "subject_memory:TEST_USER_001:MEMORY_001" in relationship_ids
    relationship=store.get_relationship(
        "subject_memory:TEST_USER_001:MEMORY_001"
    )
    assert relationship is not None
    assert relationship.relationship_type==GraphRelationshipType.SUBJECT_HAS_MEMORY
def test_upsert_preserves_temporal_fields():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    valid_from=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc)
    valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    memory=make_memory(
        valid_from=valid_from,
        valid_to=valid_to,
        status=MemoryStatus.SUPERSEDED,
        retrieval_eligible=False,
        embedding_eligible=False
    )
    result=service.upsert_memory(memory)
    stored=store.get_memory(memory.memory_id)
    assert stored.valid_from==valid_from
    assert stored.valid_to==valid_to
    assert stored.recorded_at==valid_from
    assert stored.status==MemoryStatus.SUPERSEDED
    assert result.provenance["valid_from"]==valid_from
    assert result.provenance["valid_to"]==valid_to
def test_upsert_preserves_provenance():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    result=service.upsert_memory(memory)
    assert result.provenance["source_event_ids"]==["SOURCE_001"]
    assert result.provenance["source_session_ids"]==["SESSION_001"]
    assert result.provenance["status"]==MemoryStatus.ACTIVE.value
def test_upsert_is_idempotent_for_identical_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    first=service.upsert_memory(memory)
    version_after_first=store.get_graph_version(memory.memory_id)
    second=service.upsert_memory(memory)
    version_after_second=store.get_graph_version(memory.memory_id)
    assert first.changed is True
    assert second.changed is False
    assert version_after_second==version_after_first
def test_upsert_updates_existing_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    service.upsert_memory(memory)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User prefers instrumental acoustic music.",
            "confidence":0.99
        }
    )
    result=service.upsert_memory(updated)
    assert result.operation==GraphOperation.UPDATE
    assert result.changed is True
    stored=store.get_memory(memory.memory_id)
    assert stored.normalized_fact=="User prefers instrumental acoustic music."
    assert stored.confidence==0.99
def test_graph_version_increments_on_change():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    initial_version=store.get_graph_version(memory.memory_id)
    service.upsert_memory(memory)
    first_version=store.get_graph_version(memory.memory_id)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User prefers jazz."
        }
    )
    service.upsert_memory(updated)
    second_version=store.get_graph_version(memory.memory_id)
    assert initial_version==0
    assert first_version==1
    assert second_version==2
def test_expected_graph_version_is_enforced():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    service.upsert_memory(memory)
    with pytest.raises(GraphMemoryError) as exc:
        service.upsert_memory(
            memory,
            expected_graph_version=0
        )
    assert exc.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_expected_graph_version_allows_correct_version():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    service.upsert_memory(memory)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User prefers jazz."
        }
    )
    result=service.upsert_memory(
        updated,
        expected_graph_version=1
    )
    assert result.changed is True
    assert result.graph_version==2
def test_entity_reference_creates_entity_node_and_relationship():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        entities=[
            {
                "canonical_id":"ARTIST_001",
                "entity_type":"artist",
                "canonical_name":"Miles Davis"
            }
        ]
    )
    result=service.upsert_memory(memory)
    entity_node=store.get_node("entity:ARTIST_001")
    relationship=store.get_relationship(
        "memory_entity:MEMORY_001:ARTIST_001"
    )
    assert entity_node is not None
    assert entity_node.node_type==GraphNodeType.ENTITY
    assert entity_node.properties["canonical_name"]=="Miles Davis"
    assert relationship is not None
    assert relationship.relationship_type==GraphRelationshipType.MEMORY_REFERENCES_ENTITY
def test_multiple_entity_mentions_do_not_create_duplicate_relationships_for_same_entity():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        entities=[
            {
                "canonical_id":"ARTIST_001",
                "entity_type":"artist",
                "canonical_name":"Miles Davis"
            },
            {
                "canonical_id":"ARTIST_001",
                "entity_type":"artist",
                "canonical_name":"Miles Davis"
            }
        ]
    )
    result=service.upsert_memory(memory)
    entity_relationships=[
        relationship
        for relationship in result.relationships
        if relationship.relationship_type==GraphRelationshipType.MEMORY_REFERENCES_ENTITY
    ]
    assert len(entity_relationships)==1
def test_invalid_entity_canonical_id_is_rejected():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        entities=[
            {
                "canonical_id":"",
                "entity_type":"artist",
                "canonical_name":"Unknown"
            }
        ]
    )
    with pytest.raises(GraphMemoryError) as exc:
        service.upsert_memory(memory)
    assert exc.value.code==GraphMemoryErrorCode.INVALID_ENTITY
def test_supersession_relationship_is_created():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    original=make_memory(
        memory_id="MEMORY_001",
        normalized_fact="User prefers energetic music."
    )
    service.upsert_memory(original)
    replacement=make_memory(
        memory_id="MEMORY_002",
        normalized_fact="User prefers calm acoustic music.",
        supersedes_memory_id="MEMORY_001"
    )
    result=service.upsert_memory(replacement)
    relationship=store.get_relationship(
        "memory_supersedes:MEMORY_002:MEMORY_001"
    )
    assert relationship is not None
    assert relationship.relationship_type==GraphRelationshipType.MEMORY_SUPERSEDES
    assert relationship.from_node_id=="memory:MEMORY_002"
    assert relationship.to_node_id=="memory:MEMORY_001"
    assert result.changed is True
def test_correction_relationship_is_created():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    original=make_memory(
        memory_id="MEMORY_001",
        normalized_fact="User prefers energetic music."
    )
    service.upsert_memory(original)
    corrected=make_memory(
        memory_id="MEMORY_002",
        normalized_fact="User prefers acoustic music.",
        correction_of_memory_id="MEMORY_001"
    )
    result=service.upsert_memory(corrected)
    relationship=store.get_relationship(
        "memory_corrects:MEMORY_002:MEMORY_001"
    )
    assert relationship is not None
    assert relationship.relationship_type==GraphRelationshipType.MEMORY_CORRECTS
    assert relationship.from_node_id=="memory:MEMORY_002"
    assert relationship.to_node_id=="memory:MEMORY_001"
    assert result.changed is True
def test_subject_isolation_on_existing_memory_update():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        subject_id="TEST_USER_001"
    )
    service.upsert_memory(memory)
    cross_subject=memory.model_copy(
        update={
            "subject_id":"TEST_USER_999",
            "subject_scope":"TEST_USER_999"
        }
    )
    with pytest.raises(GraphMemoryError) as exc:
        service.upsert_memory(cross_subject)
    assert exc.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_subject_scope_mismatch_is_rejected():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    memory=memory.model_copy(
        update={
            "subject_scope":"TEST_USER_999"
        }
    )
    with pytest.raises(GraphMemoryError) as exc:
        service.upsert_memory(memory)
    assert exc.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_non_memory_input_is_rejected():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    with pytest.raises(GraphMemoryError) as exc:
        service.upsert_memory(
            {"memory_id":"MEMORY_001"}
        )
    assert exc.value.code==GraphMemoryErrorCode.INVALID_MEMORY
def test_get_memory_returns_only_requested_subject():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        subject_id="TEST_USER_001"
    )
    service.upsert_memory(memory)
    result=service.get_memory(
        "MEMORY_001",
        "TEST_USER_001"
    )
    assert result.memory_id=="MEMORY_001"
    assert result.subject_id=="TEST_USER_001"
def test_get_memory_cross_subject_access_is_rejected():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    service.upsert_memory(
        make_memory(subject_id="TEST_USER_001")
    )
    with pytest.raises(GraphMemoryError) as exc:
        service.get_memory(
            "MEMORY_001",
            "TEST_USER_999"
        )
    assert exc.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_get_missing_memory_is_rejected():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    with pytest.raises(GraphMemoryError) as exc:
        service.get_memory(
            "MEMORY_UNKNOWN",
            "TEST_USER_001"
        )
    assert exc.value.code==GraphMemoryErrorCode.MEMORY_NOT_FOUND
def test_close_memory_accepts_superseded_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        status=MemoryStatus.SUPERSEDED,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    result=service.close_memory(memory)
    assert result.operation==GraphOperation.CLOSE
    assert result.changed is True
    stored=store.get_memory(memory.memory_id)
    assert stored.status==MemoryStatus.SUPERSEDED
def test_close_memory_accepts_expired_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        status=MemoryStatus.EXPIRED,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    result=service.close_memory(memory)
    assert result.operation==GraphOperation.CLOSE
    assert result.changed is True
def test_close_memory_accepts_corrected_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        status=MemoryStatus.CORRECTED,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    result=service.close_memory(memory)
    assert result.operation==GraphOperation.CLOSE
    assert result.changed is True
def test_close_memory_rejects_active_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    with pytest.raises(GraphMemoryError) as exc:
        service.close_memory(memory)
    assert exc.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_close_memory_requires_valid_to():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    with pytest.raises(ValueError):
        memory=make_memory(
            status=MemoryStatus.SUPERSEDED,
            retrieval_eligible=False,
            embedding_eligible=False
        )
def test_pending_deletion_is_upserted_without_final_graph_deletion():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    active=make_memory()
    service.upsert_memory(active)
    pending=active.model_copy(
        update={
            "status":MemoryStatus.PENDING_DELETION,
            "valid_to":datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
            "retrieval_eligible":False,
            "embedding_eligible":False
        }
    )
    result=service.delete_memory(pending)
    assert result.operation==GraphOperation.UPDATE
    assert result.changed is True
    stored=store.get_memory(active.memory_id)
    assert stored.status==MemoryStatus.PENDING_DELETION
    assert store.get_node("memory:MEMORY_001") is not None
def test_deleted_memory_is_removed_from_graph_store():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        status=MemoryStatus.DELETED,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    service.store.upsert_memory(
        GraphMemoryRecordV1(
            memory_id=memory.memory_id,
            subject_id=memory.subject_id,
            subject_scope=memory.subject_scope,
            memory_type=memory.memory_type.value,
            normalized_fact=memory.normalized_fact,
            confidence=memory.confidence,
            source_event_ids=memory.source_event_ids,
            source_session_ids=memory.source_session_ids,
            created_at=memory.created_at,
            recorded_at=memory.recorded_at,
            valid_from=memory.valid_from,
            valid_to=memory.valid_to,
            status=memory.status,
            retention_class=memory.retention_class.value,
            retrieval_eligible=False,
            embedding_eligible=False,
            entities=memory.entities,
            correction_of_memory_id=memory.correction_of_memory_id,
            supersedes_memory_id=memory.supersedes_memory_id,
            metadata=memory.metadata
        )
    )
    service.store.put_node(
        GraphNodeV1(
            node_id="memory:MEMORY_001",
            node_type=GraphNodeType.MEMORY,
            subject_id="TEST_USER_001"
        )
    )
    result=service.delete_memory(memory)
    assert result.operation==GraphOperation.DELETE
    assert result.changed is True
    assert store.get_memory("MEMORY_001") is None
    assert store.get_node("memory:MEMORY_001") is None
def test_delete_memory_requires_existing_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory(
        status=MemoryStatus.DELETED,
        valid_to=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        retrieval_eligible=False,
        embedding_eligible=False
    )
    with pytest.raises(GraphMemoryError) as exc:
        service.delete_memory(memory)
    assert exc.value.code==GraphMemoryErrorCode.MEMORY_NOT_FOUND
def test_delete_memory_requires_deleted_status_for_final_deletion():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    service.upsert_memory(memory)
    with pytest.raises(GraphMemoryError) as exc:
        service.delete_memory(memory)
    assert exc.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_graph_memory_schema_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        GraphMemoryRecordV1(
            memory_id="MEMORY_001",
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            memory_type=MemoryType.EXPLICIT_PREFERENCE.value,
            normalized_fact="User prefers jazz.",
            confidence=1.5,
            source_event_ids=["SOURCE_001"],
            source_session_ids=["SESSION_001"],
            created_at=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
            recorded_at=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
            valid_from=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
            status=MemoryStatus.ACTIVE,
            retention_class=RetentionClass.LONG.value,
            retrieval_eligible=True,
            embedding_eligible=True
        )
def test_graph_write_result_contains_provenance():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    result=service.upsert_memory(
        make_memory()
    )
    assert "source_event_ids" in result.provenance
    assert "source_session_ids" in result.provenance
    assert "recorded_at" in result.provenance
    assert "status" in result.provenance
def test_graph_upsert_is_deterministic_for_same_input():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=make_memory()
    first=service.upsert_memory(memory)
    second=service.upsert_memory(memory)
    assert first.memory_node.model_dump()==second.memory_node.model_dump()
    assert first.relationships==second.relationships
    assert second.changed is False