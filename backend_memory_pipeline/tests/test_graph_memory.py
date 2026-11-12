from datetime import datetime,timezone,timedelta
import pytest
from backend_memory_pipeline.graph_memory.graph import (
    GraphMemoryError,
    GraphMemoryErrorCode,
    GraphMemoryService,
    GraphNodeType,
    GraphOperation,
    GraphRelationshipType,
    InMemoryGraphStore,
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryRecordV1,
    MemoryStatus,
    MemoryType,
    RetentionClass,
)
def create_memory(
    memory_id="memory-1",
    subject_id="user-1",
    status=MemoryStatus.ACTIVE,
    entities=None,
    correction_of_memory_id=None,
    supersedes_memory_id=None,
):
    now=datetime.now(timezone.utc)
    return MemoryRecordV1(
        memory_id=memory_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        normalized_fact="User likes Arijit Singh.",
        confidence=0.95,
        source_event_ids=[f"event-{memory_id}"],
        source_session_ids=[f"session-{memory_id}"],
        created_at=now,
        recorded_at=now,
        valid_from=now,
        valid_to=now if status in {
            MemoryStatus.SUPERSEDED,
            MemoryStatus.EXPIRED,
            MemoryStatus.CORRECTED,
            MemoryStatus.DELETED,
        } else None,
        status=status,
        retention_class=RetentionClass.STANDARD,
        retrieval_eligible=status==MemoryStatus.ACTIVE,
        embedding_eligible=status==MemoryStatus.ACTIVE,
        entities=entities or [],
        correction_of_memory_id=correction_of_memory_id,
        supersedes_memory_id=supersedes_memory_id,
        metadata={"source":"mcp"},
    )
def test_upsert_memory_creates_subject_memory_and_entity_graph():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory(
        entities=[
            {
                "canonical_id":"artist:arijit-singh",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
                "mention":"Arijit Singh",
            }
        ]
    )
    result=service.upsert_memory(memory)
    assert result.operation==GraphOperation.UPSERT
    assert result.memory_id==memory.memory_id
    assert result.subject_id==memory.subject_id
    assert result.changed is True
    assert result.graph_version==1
    assert result.memory_node.node_type==GraphNodeType.MEMORY
    assert result.memory_node.node_id=="memory:memory-1"
    assert store.get_memory(memory.memory_id) is not None
    assert store.get_node("subject:user-1") is not None
    assert store.get_node("memory:memory-1") is not None
    assert store.get_node("entity:artist:arijit-singh") is not None
    relationships=store.all_relationships()
    relationship_types={relationship.relationship_type for relationship in relationships}
    assert GraphRelationshipType.SUBJECT_HAS_MEMORY in relationship_types
    assert GraphRelationshipType.MEMORY_REFERENCES_ENTITY in relationship_types
def test_upsert_same_memory_without_changes_is_idempotent():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    first=service.upsert_memory(memory)
    second=service.upsert_memory(memory)
    assert first.changed is True
    assert second.changed is False
    assert second.operation==GraphOperation.UPDATE
    assert second.graph_version==first.graph_version
def test_upsert_memory_increments_graph_version_when_memory_changes():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    first=service.upsert_memory(memory)
    changed_memory=memory.model_copy(
        update={
            "normalized_fact":"User strongly likes Arijit Singh."
        }
    )
    second=service.upsert_memory(changed_memory)
    assert first.graph_version==1
    assert second.graph_version==2
    assert second.changed is True
def test_upsert_memory_honors_expected_graph_version():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    service.upsert_memory(memory)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User strongly likes Arijit Singh."
        }
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.upsert_memory(
            updated,
            expected_graph_version=0,
        )
    assert exc_info.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_upsert_memory_accepts_matching_expected_graph_version():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    service.upsert_memory(memory)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User strongly likes Arijit Singh."
        }
    )
    result=service.upsert_memory(
        updated,
        expected_graph_version=1,
    )
    assert result.changed is True
    assert result.graph_version==2
def test_upsert_memory_rejects_subject_scope_mismatch():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    invalid_memory=memory.model_copy(
        update={
            "subject_scope":"another-user"
        }
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.upsert_memory(invalid_memory)
    assert exc_info.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_existing_memory_cannot_be_reassigned_to_another_subject():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    service.upsert_memory(memory)
    conflicting=memory.model_copy(
        update={
            "subject_id":"user-2",
            "subject_scope":"user-2",
        }
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.upsert_memory(conflicting)
    assert exc_info.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_get_memory_enforces_subject_isolation():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    service.upsert_memory(memory)
    loaded=service.get_memory(
        memory.memory_id,
        "user-1",
    )
    assert loaded.memory_id==memory.memory_id
    with pytest.raises(GraphMemoryError) as exc_info:
        service.get_memory(
            memory.memory_id,
            "user-2",
        )
    assert exc_info.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_get_missing_memory_is_rejected():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    with pytest.raises(GraphMemoryError) as exc_info:
        service.get_memory(
            "missing-memory",
            "user-1",
        )
    assert exc_info.value.code==GraphMemoryErrorCode.MEMORY_NOT_FOUND
def test_duplicate_entities_create_only_one_memory_entity_relationship():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory(
        entities=[
            {
                "canonical_id":"artist:arijit-singh",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
            },
            {
                "canonical_id":"artist:arijit-singh",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
            },
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
    memory=create_memory(
        entities=[
            {
                "canonical_id":"",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
            }
        ]
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.upsert_memory(memory)
    assert exc_info.value.code==GraphMemoryErrorCode.INVALID_ENTITY
def test_supersedes_relationship_is_created():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    old_memory=create_memory(
        memory_id="memory-old",
        status=MemoryStatus.SUPERSEDED,
    )
    new_memory=create_memory(
        memory_id="memory-new",
        supersedes_memory_id="memory-old",
    )
    service.upsert_memory(old_memory)
    result=service.upsert_memory(new_memory)
    relationships=[
        relationship
        for relationship in result.relationships
        if relationship.relationship_type==GraphRelationshipType.MEMORY_SUPERSEDES
    ]
    assert len(relationships)==1
    assert relationships[0].from_node_id=="memory:memory-new"
    assert relationships[0].to_node_id=="memory:memory-old"
def test_correction_relationship_is_created():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    old_memory=create_memory(
        memory_id="memory-old",
        status=MemoryStatus.CORRECTED,
    )
    corrected_memory=create_memory(
        memory_id="memory-corrected",
        correction_of_memory_id="memory-old",
    )
    service.upsert_memory(old_memory)
    result=service.upsert_memory(corrected_memory)
    relationships=[
        relationship
        for relationship in result.relationships
        if relationship.relationship_type==GraphRelationshipType.MEMORY_CORRECTS
    ]
    assert len(relationships)==1
    assert relationships[0].from_node_id=="memory:memory-corrected"
    assert relationships[0].to_node_id=="memory:memory-old"
def test_close_memory_requires_closed_status():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    with pytest.raises(GraphMemoryError) as exc_info:
        service.close_memory(memory)
    assert exc_info.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_close_memory_requires_valid_to():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory(
        status=MemoryStatus.SUPERSEDED,
    ).model_copy(
        update={
            "valid_to":None
        }
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.close_memory(memory)
    assert exc_info.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_close_memory_updates_graph():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    active_memory=create_memory()
    service.upsert_memory(active_memory)
    closed_memory=create_memory(
        status=MemoryStatus.SUPERSEDED,
    )
    result=service.close_memory(closed_memory)
    assert result.operation==GraphOperation.CLOSE
    assert result.changed is True
    assert result.memory_node.properties["status"]==MemoryStatus.SUPERSEDED.value
    stored=store.get_memory(active_memory.memory_id)
    assert stored is not None
    assert stored.status==MemoryStatus.SUPERSEDED
def test_pending_deletion_is_upserted_without_final_graph_deletion():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    active_memory=create_memory()
    service.upsert_memory(active_memory)
    pending_memory=create_memory(
        status=MemoryStatus.PENDING_DELETION,
    )
    result=service.delete_memory(pending_memory)
    assert result.operation==GraphOperation.UPDATE
    assert result.changed is True
    stored=store.get_memory(active_memory.memory_id)
    assert stored is not None
    assert stored.status==MemoryStatus.PENDING_DELETION
    assert store.get_node("memory:memory-1") is not None
def test_deleted_memory_is_removed_from_graph_store():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    active_memory=create_memory()
    service.upsert_memory(active_memory)
    deleted_memory=create_memory(
        status=MemoryStatus.DELETED,
    )
    result=service.delete_memory(deleted_memory)
    assert result.operation==GraphOperation.DELETE
    assert result.changed is True
    assert store.get_memory(active_memory.memory_id) is None
    assert store.get_node("memory:memory-1") is None
    assert store.get_node("subject:user-1") is not None
def test_delete_memory_requires_existing_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    deleted_memory=create_memory(
        status=MemoryStatus.DELETED,
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.delete_memory(deleted_memory)
    assert exc_info.value.code==GraphMemoryErrorCode.MEMORY_NOT_FOUND
def test_delete_memory_rejects_active_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    active_memory=create_memory()
    service.upsert_memory(active_memory)
    with pytest.raises(GraphMemoryError) as exc_info:
        service.delete_memory(active_memory)
    assert exc_info.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_delete_memory_rejects_closed_but_not_deleted_memory():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    active_memory=create_memory()
    service.upsert_memory(active_memory)
    expired_memory=create_memory(
        status=MemoryStatus.EXPIRED,
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        service.delete_memory(expired_memory)
    assert exc_info.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_deleted_memory_graph_version_increments():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    service.upsert_memory(memory)
    deleted_memory=create_memory(
        status=MemoryStatus.DELETED,
    )
    service.delete_memory(deleted_memory)
    assert store.get_graph_version(memory.memory_id)==2
def test_relationships_are_removed_when_memory_is_deleted():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory(
        entities=[
            {
                "canonical_id":"artist:arijit-singh",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
            }
        ]
    )
    service.upsert_memory(memory)
    assert len(store.all_relationships())>=2
    deleted_memory=create_memory(
        status=MemoryStatus.DELETED,
        entities=memory.entities,
    )
    service.delete_memory(deleted_memory)
    assert all(
        relationship.from_node_id!="memory:memory-1"
        and relationship.to_node_id!="memory:memory-1"
        for relationship in store.all_relationships()
    )
def test_memory_provenance_is_returned_in_graph_result():
    store=InMemoryGraphStore()
    service=GraphMemoryService(store)
    memory=create_memory()
    result=service.upsert_memory(memory)
    assert result.provenance["source_event_ids"]==memory.source_event_ids
    assert result.provenance["source_session_ids"]==memory.source_session_ids
    assert result.provenance["recorded_at"]==memory.recorded_at
    assert result.provenance["valid_from"]==memory.valid_from
    assert result.provenance["valid_to"]==memory.valid_to
    assert result.provenance["status"]==memory.status.value