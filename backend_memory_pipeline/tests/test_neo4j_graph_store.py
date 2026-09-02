import os
from datetime import datetime,timezone
from backend_memory_pipeline.persistence.neo4j.graph_store import Neo4jGraphStore
from backend_memory_pipeline.graph_memory.graph import GraphMemoryRecordV1,GraphNodeV1,GraphNodeType,GraphRelationshipV1,GraphRelationshipType
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryStatus
def create_store():
    return Neo4jGraphStore(
        uri=os.getenv("NEO4J_URI","bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME","neo4j"),
        password=os.getenv("NEO4J_PASSWORD","password"),
        database=os.getenv("NEO4J_DATABASE","neo4j"),
    )
def create_memory():
    now=datetime.now(timezone.utc)
    return GraphMemoryRecordV1(
        memory_id="neo4j-test-memory",
        subject_id="neo4j-test-user",
        subject_scope="neo4j-test-user",
        memory_type="explicit_preference",
        normalized_fact="User likes Arijit Singh.",
        confidence=1.0,
        source_event_ids=["neo4j-test-event"],
        source_session_ids=["neo4j-test-session"],
        created_at=now,
        recorded_at=now,
        valid_from=now,
        valid_to=None,
        status=MemoryStatus.ACTIVE,
        retention_class="standard",
        retrieval_eligible=True,
        embedding_eligible=True,
        entities=[],
        correction_of_memory_id=None,
        supersedes_memory_id=None,
        metadata={"source":"mcp"},
    )
def test_neo4j_memory_crud():
    store=create_store()
    memory=create_memory()
    try:
        store.verify_connectivity()
        assert store.get_memory(memory.memory_id) is None
        changed=store.upsert_memory(memory)
        assert changed is True
        loaded=store.get_memory(memory.memory_id)
        assert loaded is not None
        assert loaded.memory_id==memory.memory_id
        assert loaded.subject_id=="neo4j-test-user"
        assert loaded.normalized_fact=="User likes Arijit Singh."
        assert loaded.metadata["source"]=="mcp"
        version=store.get_graph_version(memory.memory_id)
        assert version==1
        node=GraphNodeV1(
            node_id="subject:neo4j-test-user",
            node_type=GraphNodeType.SUBJECT,
            subject_id="neo4j-test-user",
            properties={
                "subject_id":"neo4j-test-user",
                "subject_scope":"neo4j-test-user",
            },
        )
        assert store.put_node(node) is True
        relationship=GraphRelationshipV1(
            relationship_id="subject_memory:neo4j-test-user:neo4j-test-memory",
            relationship_type=GraphRelationshipType.SUBJECT_HAS_MEMORY,
            from_node_id="subject:neo4j-test-user",
            to_node_id="memory:neo4j-test-memory",
            subject_id="neo4j-test-user",
            properties={
                "status":"active",
                "recorded_at":memory.recorded_at,
            },
        )
        memory_node=GraphNodeV1(
            node_id="memory:neo4j-test-memory",
            node_type=GraphNodeType.MEMORY,
            subject_id="neo4j-test-user",
            properties={
                "memory_id":memory.memory_id,
                "subject_id":memory.subject_id,
                "status":memory.status.value,
            },
        )
        assert store.put_node(memory_node) is True
        assert store.put_relationship(relationship) is True
        assert store.get_node("subject:neo4j-test-user") is not None
        assert store.get_relationship(relationship.relationship_id) is not None
    finally:
        store.delete_memory(memory.memory_id)
        store.close()