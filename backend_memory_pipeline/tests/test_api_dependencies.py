from backend_memory_pipeline.api.dependencies import (
    get_graph_store,
    get_neo4j_graph_store,
    get_embedding_store,
    get_qdrant_embedding_store,
    get_memory_store,
    get_memory_write_orchestrator,
    get_memory_query_orchestrator,
    get_entity_repository,
    get_entity_resolution_service)

def test_shared_stores_are_singletons():
    memory_store_1=get_memory_store()
    memory_store_2=get_memory_store()
    graph_store_1=get_graph_store()
    graph_store_2=get_graph_store()
    embedding_store_1=get_embedding_store()
    embedding_store_2=get_embedding_store()
    assert memory_store_1 is memory_store_2
    assert graph_store_1 is graph_store_2
    assert embedding_store_1 is embedding_store_2
def test_write_and_query_orchestrators_use_shared_stores():
    write_orchestrator=get_memory_write_orchestrator()
    query_orchestrator=get_memory_query_orchestrator()
    assert write_orchestrator.lifecycle.store is get_memory_store()
    assert write_orchestrator.graph.store is get_neo4j_graph_store()
    assert write_orchestrator.embedding.store is get_qdrant_embedding_store()
    assert query_orchestrator.retrieval.store.graph_store is get_neo4j_graph_store()
    assert query_orchestrator.retrieval.store.embedding_store is get_qdrant_embedding_store()
def test_write_and_query_orchestrators_share_graph_and_embedding_stores():
    write_orchestrator=get_memory_write_orchestrator()
    query_orchestrator=get_memory_query_orchestrator()
    assert write_orchestrator.lifecycle.store is get_memory_store()
    assert write_orchestrator.graph.store is get_neo4j_graph_store()
    assert write_orchestrator.embedding.store is get_qdrant_embedding_store()
    assert query_orchestrator.retrieval.store.graph_store is get_neo4j_graph_store()
    assert query_orchestrator.retrieval.store.embedding_store is get_qdrant_embedding_store()
def test_entity_resolution_dependencies_are_singletons():
    repository_1=get_entity_repository()
    repository_2=get_entity_repository()
    service_1=get_entity_resolution_service()
    service_2=get_entity_resolution_service()
    assert repository_1 is repository_2
    assert service_1 is service_2
def test_write_orchestrator_uses_shared_entity_resolution_service():
    write_orchestrator=get_memory_write_orchestrator()
    assert write_orchestrator.entity_resolver is get_entity_resolution_service()    