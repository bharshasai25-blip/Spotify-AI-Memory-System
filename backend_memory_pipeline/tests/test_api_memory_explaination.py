import os
from datetime import datetime,timezone

import pytest
from fastapi.testclient import TestClient

from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import (
    get_memory_write_orchestrator,
    get_memory_query_orchestrator,
    get_memory_store,
    get_graph_store,
    get_embedding_store,
    get_session_manager, 
    get_revoked_token_store,
    get_user_repository
)
from backend_memory_pipeline.ingestion.ingestion import (
    ConsentState
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    MemoryControlAction
)
from backend_memory_pipeline.ingestion.ingestion import IngestionService


@pytest.fixture(autouse=True)
def reset_api_state():
    repository=get_user_repository()
    repository._users.clear()
    repository._subjects.clear()
    get_revoked_token_store().clear()

    get_memory_write_orchestrator.cache_clear()
    get_memory_query_orchestrator.cache_clear()
    get_memory_store.cache_clear()
    get_graph_store.cache_clear()
    get_embedding_store.cache_clear()
    get_session_manager.cache_clear()

    original_secret=os.environ.get("API_AUTH_SECRET")
    os.environ["API_AUTH_SECRET"] = (
        "test-api-auth-secret-2026-abcdefghijklmnopqrstuvwxyz"
    )

    yield

    repository._users.clear()
    repository._subjects.clear()
    get_revoked_token_store().clear()

    get_memory_write_orchestrator.cache_clear()
    get_memory_query_orchestrator.cache_clear()
    get_memory_store.cache_clear()
    get_graph_store.cache_clear()
    get_embedding_store.cache_clear()
    get_session_manager.cache_clear()

    if original_secret is None:
        os.environ.pop("API_AUTH_SECRET",None)
    else:
        os.environ["API_AUTH_SECRET"]=original_secret


@pytest.fixture
def client():
    return TestClient(app)


def register_and_login(client,username="testuser"):
    response=client.post(
        "/v1/auth/register",
        json={
            "username":username,
            "password":"testpassword123"
        }
    )

    assert response.status_code==200

    body=response.json()

    assert body["access_token"]
    assert body["subject_id"]

    return body


def auth_headers(auth):
    return {
        "Authorization":f"Bearer {auth['access_token']}"
    }


def seed_memory(subject_id):
    orchestrator=get_memory_write_orchestrator()

    consent_request=ConsentControlRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(2026,8,28,10,0,0,tzinfo=timezone.utc),
        correlation_id=IngestionService.new_correlation_id())

    orchestrator.policy_consent.apply_consent_control(consent_request)

    result=orchestrator.add_explicit_preference(
        subject_id=subject_id,
        subject_scope=subject_id,
        session_id="SESSION_API_EXPLANATION_001",
        preference="I prefer instrumental jazz.",
        surface="chat",
        locale="en-IN",
        effective_at=datetime(2026,8,28,10,5,0,tzinfo=timezone.utc),
        correlation_id=IngestionService.new_correlation_id(),
        idempotency_key=IngestionService.new_idempotency_key())
    

    assert result.lifecycle_results
    lifecycle_result=result.lifecycle_results[0]

    memory_id=(lifecycle_result.created_memory_id or lifecycle_result.memory_id)
    assert memory_id is not None
    print("LIFECYCLE RESULT:", lifecycle_result)
    return memory_id


def test_explain_memory_use_returns_explanation(client):
    auth=register_and_login(client)

    memory_id=seed_memory(
        auth["subject_id"]
    )

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(auth),
        params={
            "surface":"chat",
            "locale":"en-IN"
        }
    )

    assert response.status_code==200
    body=response.json()
    #assert body["status"]=="success"
    assert body["schema_version"]=="1.0"
    assert body["memory_id"]==memory_id
    assert body["subject_id"]==auth["subject_id"]
    assert body["explanation"]
    assert body["correlation_id"]


def test_explain_memory_use_accepts_current_intent(client):
    auth=register_and_login(client)

    memory_id=seed_memory(
        auth["subject_id"]
    )

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(auth),
        params={
            "current_intent":"Why is this jazz recommendation relevant?",
            "surface":"chat",
            "locale":"en-IN"
        }
    )

    assert response.status_code==200
    body=response.json()
    #assert body["status"]=="success"
    assert body["schema_version"]=="1.0"
    assert body["memory_id"]==memory_id
    assert body["explanation"]
    assert body["relevance_reason"] is not None


def test_explain_memory_use_returns_source_and_confidence(client):
    auth=register_and_login(client)

    memory_id=seed_memory(
        auth["subject_id"]
    )

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(auth),
        params={
            "surface":"chat",
            "locale":"en-IN"
        }
    )

    assert response.status_code==200
    body=response.json()
    assert body["source"] is not None
    assert body["confidence"] is not None
    assert 0.0<=body["confidence"]<=1.0
    assert body["timestamp"] is not None


def test_explain_memory_use_preserves_correlation_id(client):
    auth=register_and_login(client)

    memory_id=seed_memory(auth["subject_id"])
    correlation_id=IngestionService.new_correlation_id()

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(auth),
        params={
            "surface":"chat",
            "locale":"en-IN",
            "correlation_id":correlation_id
        }
    )

    assert response.status_code==200
    body=response.json()
    assert body["correlation_id"]==correlation_id


def test_explain_memory_use_requires_surface(client):
    auth=register_and_login(client)

    memory_id=seed_memory(
        auth["subject_id"]
    )

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(auth),
        params={
            "locale":"en-IN"
        }
    )

    assert response.status_code==422


def test_explain_memory_use_requires_locale(client):
    auth=register_and_login(client)

    memory_id=seed_memory(
        auth["subject_id"]
    )

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(auth),
        params={
            "surface":"chat"
        }
    )

    assert response.status_code==422


def test_explain_memory_use_rejects_unknown_memory_when_consent_is_unknown(client):
    auth=register_and_login(client)

    response=client.get(
        "/v1/memories/MEMORY_DOES_NOT_EXIST/explanation",
        headers=auth_headers(auth),
        params={
            "surface":"chat",
            "locale":"en-IN"
        }
    )

    assert response.status_code==403
    body=response.json()
    assert "not permitted" in body["message"].lower()


def test_explain_memory_use_requires_authentication(client):
    response=client.get(
        "/v1/memories/MEMORY_DOES_NOT_EXIST/explanation",
        params={
            "surface":"chat",
            "locale":"en-IN"
        }
    )

    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"


def test_explain_memory_use_rejects_cross_subject_access(client):
    owner=register_and_login(client,username="memoryowner")
    other_user=register_and_login(client,username="otheruser")
    memory_id=seed_memory(owner["subject_id"])

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(other_user),
        params={"surface":"chat","locale":"en-IN"})

    assert response.status_code==403
    body=response.json()
    assert "not permitted" in body["message"].lower()


def test_explain_memory_use_does_not_expose_other_subject_memory(client):
    owner=register_and_login(client,username="memoryowner")
    other_user=register_and_login(client,username="otheruser")
    memory_id=seed_memory(owner["subject_id"])

    response=client.get(
        f"/v1/memories/{memory_id}/explanation",
        headers=auth_headers(other_user),
        params={
            "surface":"chat",
            "locale":"en-IN"
        }
    )

    assert response.status_code==403
    body=response.json()
    assert body["schema_version"]=="1.0"
    assert memory_id not in body["message"]
    assert owner["subject_id"] not in body["message"]