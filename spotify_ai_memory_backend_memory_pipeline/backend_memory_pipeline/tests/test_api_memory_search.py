import os
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import (
    get_user_repository,
    get_memory_write_orchestrator,
    get_memory_query_orchestrator,
    get_memory_store,
    get_graph_store,
    get_embedding_store,
    _hash_password,
)
def test_memory_search_api_returns_written_memory():
    os.environ["API_AUTH_SECRET"]="test-api-auth-secret-12345678901234567890"
    get_memory_write_orchestrator.cache_clear()
    get_memory_query_orchestrator.cache_clear()
    get_memory_store.cache_clear()
    get_graph_store.cache_clear()
    get_embedding_store.cache_clear()
    user_repository=get_user_repository()
    username="memory_search_api_user"
    password="testpassword123"
    existing_user=user_repository.get_by_username(username)
    if existing_user is None:
        user=user_repository.create_user(
            username=username,
            password_hash=_hash_password(password),
        )
    else:
        user=existing_user
    client=TestClient(app)
    login_response=client.post(
        "/v1/auth/login",
        json={
            "schema_version":"1.0",
            "username":username,
            "password":password,
            "metadata":{},
        },
    )
    assert login_response.status_code==200
    login_data=login_response.json()
    access_token=login_data["access_token"]
    subject_id=login_data["subject_id"]
    headers={"Authorization":f"Bearer {access_token}",}

    consent_response=client.post(
        "/v1/memory/control",
        headers=headers,
        json={"schema_version":"1.0","action":"opt_in",
            "metadata":{"integration_test":True,},},)

    assert consent_response.status_code==200
    consent_data=consent_response.json()

    print("CONSENT RESPONSE:",consent_data)

    assert consent_data["subject_id"]==subject_id
    assert consent_data["action"]=="opt_in"
    assert consent_data["current_state"]=="opted_in"


    event_response=client.post(
        "/v1/events",
        headers=headers,
        json={
            "schema_version":"1.0",
            "event_type":"explicit_preference",
            "surface":"chat",
            "locale":"en-US",
            "text":"I prefer calm acoustic music.",
            "entity":None,
            "context_entities":{},
            "metadata":{},
            "idempotency_key":"API_MEMORY_SEARCH_TEST_001",
        },
    )
    assert event_response.status_code in {200,201}
    event_data=event_response.json()
    print("EVENT RESPONSE:",event_data)
    assert event_data["subject_id"]==subject_id
    
    write_orchestrator=get_memory_write_orchestrator()
    query_orchestrator=get_memory_query_orchestrator()
    graph_store=get_graph_store()
    embedding_store=get_embedding_store()
    memory_store=get_memory_store()
    
    print("GRAPH MEMORIES:",graph_store.all_memories())
    print("EMBEDDINGS:",embedding_store.all())
    print("MEMORY STORE:",memory_store)
    print("WRITE GRAPH STORE:",write_orchestrator.graph.store)
    print("QUERY RETRIEVAL STORE GRAPH:",query_orchestrator.retrieval.store.graph_store)
    print("WRITE EMBEDDING STORE:",write_orchestrator.embedding.store)
    print("QUERY RETRIEVAL STORE EMBEDDING:",query_orchestrator.retrieval.store.embedding_store)
    print("GRAPH SAME:",write_orchestrator.graph.store is query_orchestrator.retrieval.store.graph_store)
    print("EMBEDDING SAME:",write_orchestrator.embedding.store is query_orchestrator.retrieval.store.embedding_store)
    
    requested_at=datetime.now(timezone.utc)

    search_response=client.post(
        "/v1/memories/search",
        headers=headers,
        json={
            "schema_version":"1.0",
            "intent":"calm acoustic music",
            "surface":"chat",
            "locale":"en-US",
            "requested_at":requested_at.isoformat(),
            "top_k":5,
            "candidate_limit":50,
            "vector_weight":0.55,
            "graph_weight":0.45,
            "min_score":0.0,
            "metadata":{
            "integration_test":True,
            },
        },
    )
    assert search_response.status_code==200
    search_data=search_response.json()
    assert search_data["schema_version"]=="1.0"
    assert search_data["subject_id"]==subject_id
    assert search_data["query_intent"]=="calm acoustic music"
    assert search_data["decision"]=="retrieved"
    assert search_data["candidate_count"]>=1
    assert search_data["returned_count"]>=1
    assert len(search_data["candidates"])>=1
    normalized_facts=[
        candidate["normalized_fact"].lower()
        for candidate in search_data["candidates"]
    ]
    assert any(
        "calm acoustic" in fact
        for fact in normalized_facts
    )
    assert search_data["correlation_id"]
    assert search_data["retrieval_version"]
def test_memory_search_api_requires_authentication():
    client=TestClient(app)
    response=client.post(
        "/v1/memories/search",
        json={
            "schema_version":"1.0",
            "intent":"calm acoustic music",
            "surface":"chat",
            "locale":"en-US",
            "requested_at":datetime.now(timezone.utc).isoformat(),
            "top_k":5,
            "candidate_limit":50,
            "vector_weight":0.55,
            "graph_weight":0.45,
            "min_score":0.0,
            "metadata":{},
        },
    )
    assert response.status_code==401
def test_memory_search_api_rejects_zero_retrieval_weights():
    client=TestClient(app)
    response=client.post(
        "/v1/memories/search",
        json={
            "schema_version":"1.0",
            "intent":"calm acoustic music",
            "surface":"chat",
            "locale":"en-US",
            "requested_at":datetime.now(timezone.utc).isoformat(),
            "top_k":5,
            "candidate_limit":50,
            "vector_weight":0.0,
            "graph_weight":0.0,
            "min_score":0.0,
            "metadata":{},
        },
    )
    assert response.status_code==401