import os
from datetime import datetime,timezone
import pytest
from backend_memory_pipeline.graph_memory.graph import (
    GraphMemoryError,
    GraphMemoryErrorCode,
    GraphMemoryService,
    GraphNodeType,
    GraphOperation,
    GraphRelationshipType,
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryRecordV1,
    MemoryStatus,
    MemoryType,
    RetentionClass,
)
from backend_memory_pipeline.persistence.neo4j.graph_store import Neo4jGraphStore
def create_store():
    return Neo4jGraphStore(
        uri=os.getenv("NEO4J_URI","bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME","neo4j"),
        password=os.getenv("NEO4J_PASSWORD","password"),
        database=os.getenv("NEO4J_DATABASE","neo4j"),
    )
def create_memory(
    memory_id="neo4j-service-memory",
    subject_id="neo4j-service-user",
    status=MemoryStatus.ACTIVE,
    entities=None,
    correction_of_memory_id=None,
    supersedes_memory_id=None,
):
    now=datetime.now(timezone.utc)
    terminal_states={
        MemoryStatus.SUPERSEDED,
        MemoryStatus.EXPIRED,
        MemoryStatus.CORRECTED,
        MemoryStatus.DELETED,
    }
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
        valid_to=now if status in terminal_states else None,
        status=status,
        retention_class=RetentionClass.STANDARD,
        retrieval_eligible=status==MemoryStatus.ACTIVE,
        embedding_eligible=status==MemoryStatus.ACTIVE,
        entities=entities or [],
        correction_of_memory_id=correction_of_memory_id,
        supersedes_memory_id=supersedes_memory_id,
        metadata={"source":"mcp"},
    )
@pytest.fixture
def neo4j_service():
    store=create_store()
    store.verify_connectivity()
    service=GraphMemoryService(store)
    print("BEFORE TEST:",store.driver.execute_query(
    """
    MATCH (m:Memory {memory_id:"neo4j-service-memory"})
    RETURN m.memory_id AS memory_id,m.source_event_ids AS source_event_ids,m.source_session_ids AS source_session_ids
    """,
    database_=store.database,)[0])
    yield service
    cleanup_memory_ids=[
        "neo4j-service-memory",
        "neo4j-service-updated-memory",
        "neo4j-service-old-memory",
        "neo4j-service-new-memory",
        "neo4j-service-corrected-memory",
    ]
    for memory_id in cleanup_memory_ids:
        try:
            store.delete_memory(memory_id)
        except Exception:
            pass
    store.driver.execute_query(
        """
        MATCH (n:Subject {node_id:"subject:neo4j-service-user"})
        DETACH DELETE n
        """,
        database_=store.database,
    )
    store.driver.execute_query(
        """
        MATCH (n:Entity)
        WHERE n.node_id STARTS WITH "entity:artist:neo4j"
        DETACH DELETE n
        """,
        database_=store.database,
    )
    store.close()
def test_graph_memory_service_upserts_memory_into_neo4j(neo4j_service):
    memory=create_memory()
    result=neo4j_service.upsert_memory(memory)
    print("RESULT GRAPH VERSION:",result.graph_version)
    print("RAW NEO4J NODE:",dict(neo4j_service.store.driver.execute_query(
    """
    MATCH (m:Memory {memory_id:$memory_id})
    RETURN m
    """,
    {"memory_id":memory.memory_id},
    database_=neo4j_service.store.database,)[0][0]["m"]))
    assert result.operation==GraphOperation.UPSERT
    assert result.memory_id==memory.memory_id
    assert result.subject_id==memory.subject_id
    assert result.changed is True
    assert result.graph_version==1
    stored=neo4j_service.get_memory(
        memory.memory_id,
        memory.subject_id,
    )
    assert stored.memory_id==memory.memory_id
    assert stored.subject_id==memory.subject_id
    assert stored.normalized_fact=="User likes Arijit Singh."
    assert stored.metadata["source"]=="mcp"
def test_graph_memory_service_creates_subject_memory_and_entity_relationships_in_neo4j(neo4j_service):
    memory=create_memory(
        entities=[
            {
                "canonical_id":"artist:neo4j-arijit-singh",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
            }
        ]
    )
    result=neo4j_service.upsert_memory(memory)
    store=neo4j_service.store
    subject_node=store.get_node("subject:neo4j-service-user")
    memory_node=store.get_node("memory:neo4j-service-memory")
    entity_node=store.get_node("entity:artist:neo4j-arijit-singh")
    assert subject_node is not None
    assert subject_node.node_type==GraphNodeType.SUBJECT
    assert memory_node is not None
    assert memory_node.node_type==GraphNodeType.MEMORY
    assert entity_node is not None
    assert entity_node.node_type==GraphNodeType.ENTITY
    relationship_types={
        relationship.relationship_type
        for relationship in store.all_relationships()
        if relationship.subject_id=="neo4j-service-user"
    }
    assert GraphRelationshipType.SUBJECT_HAS_MEMORY in relationship_types
    assert GraphRelationshipType.MEMORY_REFERENCES_ENTITY in relationship_types
    assert len(result.relationships)>=2
def test_graph_memory_service_preserves_temporal_fields_in_neo4j(neo4j_service):
    memory=create_memory()
    neo4j_service.upsert_memory(memory)
    stored=neo4j_service.get_memory(
        memory.memory_id,
        memory.subject_id,
    )
    assert stored.created_at==memory.created_at
    assert stored.recorded_at==memory.recorded_at
    assert stored.valid_from==memory.valid_from
    assert stored.valid_to==memory.valid_to
def test_graph_memory_service_preserves_provenance_in_neo4j(neo4j_service):
    memory=create_memory()
    result=neo4j_service.upsert_memory(memory)
    assert result.provenance["source_event_ids"]==memory.source_event_ids
    assert result.provenance["source_session_ids"]==memory.source_session_ids
    assert result.provenance["recorded_at"]==memory.recorded_at
    assert result.provenance["valid_from"]==memory.valid_from
    assert result.provenance["status"]==memory.status.value
def test_graph_memory_service_enforces_subject_isolation_in_neo4j(neo4j_service):
    memory=create_memory(
        subject_id="neo4j-service-user",
    )
    neo4j_service.upsert_memory(memory)
    with pytest.raises(GraphMemoryError) as exc_info:
        neo4j_service.get_memory(
            memory.memory_id,
            "another-user",
        )
    assert exc_info.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_graph_memory_service_rejects_existing_memory_subject_change_in_neo4j(neo4j_service):
    memory=create_memory(
        subject_id="neo4j-service-user",
    )
    neo4j_service.upsert_memory(memory)
    conflicting=memory.model_copy(
        update={
            "subject_id":"another-user",
            "subject_scope":"another-user",
        }
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        neo4j_service.upsert_memory(conflicting)
    assert exc_info.value.code==GraphMemoryErrorCode.SUBJECT_MISMATCH
def test_graph_memory_service_graph_versioning_works_with_neo4j(neo4j_service):
    memory=create_memory()
    first=neo4j_service.upsert_memory(memory)
    assert first.graph_version==1
    updated=memory.model_copy(
        update={
            "normalized_fact":"User strongly likes Arijit Singh."
        }
    )
    second=neo4j_service.upsert_memory(
        updated,
        expected_graph_version=1,
    )
    assert second.changed is True
    assert second.graph_version==2
    stored=neo4j_service.get_memory(
        memory.memory_id,
        memory.subject_id,
    )
    assert stored.normalized_fact=="User strongly likes Arijit Singh."
def test_graph_memory_service_rejects_stale_graph_version_in_neo4j(neo4j_service):
    memory=create_memory()
    neo4j_service.upsert_memory(memory)
    updated=memory.model_copy(
        update={
            "normalized_fact":"User strongly likes Arijit Singh."
        }
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        neo4j_service.upsert_memory(
            updated,
            expected_graph_version=0,
        )
    assert exc_info.value.code==GraphMemoryErrorCode.GRAPH_CONFLICT
def test_graph_memory_service_creates_supersedes_relationship_in_neo4j(neo4j_service):
    old_memory=create_memory(
        memory_id="neo4j-service-old-memory",
        status=MemoryStatus.SUPERSEDED,
    )
    new_memory=create_memory(
        memory_id="neo4j-service-new-memory",
        supersedes_memory_id="neo4j-service-old-memory",
    )
    neo4j_service.upsert_memory(old_memory)
    result=neo4j_service.upsert_memory(new_memory)
    relationship=neo4j_service.store.get_relationship(
        "memory_supersedes:neo4j-service-new-memory:neo4j-service-old-memory"
    )
    assert relationship is not None
    assert relationship.relationship_type==GraphRelationshipType.MEMORY_SUPERSEDES
    assert relationship.from_node_id=="memory:neo4j-service-new-memory"
    assert relationship.to_node_id=="memory:neo4j-service-old-memory"
    assert any(
        item.relationship_type==GraphRelationshipType.MEMORY_SUPERSEDES
        for item in result.relationships
    )
def test_graph_memory_service_creates_correction_relationship_in_neo4j(neo4j_service):
    old_memory=create_memory(
        memory_id="neo4j-service-old-memory",
        status=MemoryStatus.CORRECTED,
    )
    corrected_memory=create_memory(
        memory_id="neo4j-service-corrected-memory",
        correction_of_memory_id="neo4j-service-old-memory",
    )
    neo4j_service.upsert_memory(old_memory)
    result=neo4j_service.upsert_memory(corrected_memory)
    relationship=neo4j_service.store.get_relationship(
        "memory_corrects:neo4j-service-corrected-memory:neo4j-service-old-memory"
    )
    assert relationship is not None
    assert relationship.relationship_type==GraphRelationshipType.MEMORY_CORRECTS
    assert relationship.from_node_id=="memory:neo4j-service-corrected-memory"
    assert relationship.to_node_id=="memory:neo4j-service-old-memory"
    assert any(
        item.relationship_type==GraphRelationshipType.MEMORY_CORRECTS
        for item in result.relationships
    )
def test_graph_memory_service_pending_deletion_updates_neo4j(neo4j_service):
    memory=create_memory()
    neo4j_service.upsert_memory(memory)
    pending=create_memory(
        status=MemoryStatus.PENDING_DELETION,
    )
    result=neo4j_service.delete_memory(pending)
    assert result.operation==GraphOperation.UPDATE
    stored=neo4j_service.get_memory(
        memory.memory_id,
        memory.subject_id,
    )
    assert stored.status==MemoryStatus.PENDING_DELETION
    assert stored.retrieval_eligible is False
    assert stored.embedding_eligible is False
def test_graph_memory_service_deleted_memory_is_physically_removed_from_neo4j(neo4j_service):
    memory=create_memory()
    neo4j_service.upsert_memory(memory)
    deleted=create_memory(
        status=MemoryStatus.DELETED,
    )
    result=neo4j_service.delete_memory(deleted)
    assert result.operation==GraphOperation.DELETE
    assert result.changed is True
    assert neo4j_service.store.get_memory(memory.memory_id) is None
    assert neo4j_service.store.get_node("memory:neo4j-service-memory") is None
    assert neo4j_service.store.get_relationship(
        "subject_memory:neo4j-service-user:neo4j-service-memory"
    ) is None
def test_graph_memory_service_deletion_removes_entity_relationships_from_neo4j(neo4j_service):
    memory=create_memory(
        entities=[
            {
                "canonical_id":"artist:neo4j-arijit-singh",
                "entity_type":"artist",
                "canonical_name":"Arijit Singh",
            }
        ]
    )
    neo4j_service.upsert_memory(memory)
    deleted=create_memory(
        status=MemoryStatus.DELETED,
        entities=memory.entities,
    )
    neo4j_service.delete_memory(deleted)
    assert neo4j_service.store.get_memory(memory.memory_id) is None
    assert neo4j_service.store.get_node("memory:neo4j-service-memory") is None
    assert neo4j_service.store.get_relationship(
        "memory_entity:neo4j-service-memory:artist:neo4j-arijit-singh"
    ) is None
def test_graph_memory_service_missing_memory_delete_is_rejected_in_neo4j(neo4j_service):
    deleted=create_memory(
        status=MemoryStatus.DELETED,
    )
    with pytest.raises(GraphMemoryError) as exc_info:
        neo4j_service.delete_memory(deleted)
    assert exc_info.value.code==GraphMemoryErrorCode.MEMORY_NOT_FOUND

def test_graph_memory_service_idempotent_upsert_does_not_increment_version_in_neo4j(neo4j_service):
    memory=create_memory()
    first=neo4j_service.upsert_memory(memory)
    assert first.graph_version==1
    assert first.changed is True
    second=neo4j_service.upsert_memory(memory)
    assert second.changed is False
    assert second.graph_version==1
    stored=neo4j_service.get_memory(
        memory.memory_id,
        memory.subject_id,
    )
    assert stored.memory_id==memory.memory_id
    assert stored.normalized_fact==memory.normalized_fact    