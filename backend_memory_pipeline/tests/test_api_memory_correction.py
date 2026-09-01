import os
import pytest
from fastapi.testclient import TestClient
from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import (
    get_memory_control_orchestrator,
    get_memory_write_orchestrator,
    get_session_manager,
    get_user_repository
)
@pytest.fixture(autouse=True)
def reset_api_state():
    repository=get_user_repository()
    repository._users.clear()
    repository._subjects.clear()
    get_memory_control_orchestrator.cache_clear()
    get_memory_write_orchestrator.cache_clear()
    get_session_manager.cache_clear()
    original_secret=os.environ.get("API_AUTH_SECRET")
    os.environ["API_AUTH_SECRET"]="test-api-auth-secret-2026-abcdefghijklmnopqrstuvwxyz"
    yield
    repository._users.clear()
    repository._subjects.clear()
    get_memory_control_orchestrator.cache_clear()
    get_memory_write_orchestrator.cache_clear()
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
    return response.json()
def create_initial_memory(client,token):
    consent_response=client.post(
        "/v1/memory/control",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json={
            "action":"opt_in"
        }
    )
    assert consent_response.status_code==200
    response=client.post(
        "/v1/events",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json={
            "event_type":"explicit_preference",
            "surface":"chat",
            "locale":"en-IN",
            "text":"I prefer calm acoustic music.",
            "entity":None,
            "context_entities":{},
            "metadata":{},
            "idempotency_key":"INITIAL_MEMORY_001"
        }
    )
    assert response.status_code==200
    orchestrator=get_memory_write_orchestrator()
    memories=orchestrator.lifecycle.store.all()
    assert memories
    memory=memories[-1]
    assert memory.subject_id
    return memory
def correct_memory(client,token,memory_id,corrected_statement="I prefer instrumental jazz.",reason="The previous preference was incorrect.",metadata=None):
    return client.patch(
        f"/v1/memories/{memory_id}",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json={
            "corrected_statement":corrected_statement,
            "reason":reason,
            "metadata":metadata or {}
        }
    )
def test_memory_correction_is_accepted(client):
    auth=register_and_login(client)
    memory=create_initial_memory(
        client,
        auth["access_token"]
    )
    response=correct_memory(
        client,
        auth["access_token"],
        memory.memory_id
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["subject_id"]==auth["subject_id"]
    assert body["action"]=="correct"
    assert body["target_memory_id"]==memory.memory_id
    assert body["corrected_memory_id"]
    assert body["corrected_memory_id"]!=memory.memory_id
    assert body["corrected_memory_status"]=="active"
    assert body["changed"] is True
    assert body["correlation_id"]
    assert body["effective_at"]
    assert body["reason"]=="The previous preference was incorrect."
def test_memory_correction_closes_old_memory_and_creates_new_memory(client):
    auth=register_and_login(client)
    memory=create_initial_memory(
        client,
        auth["access_token"]
    )
    response=correct_memory(
        client,
        auth["access_token"],
        memory.memory_id,
        corrected_statement="I prefer instrumental jazz."
    )
    assert response.status_code==200
    body=response.json()
    orchestrator=get_memory_write_orchestrator()
    old_memory=orchestrator.lifecycle.store.get(
        memory.memory_id
    )
    new_memory=orchestrator.lifecycle.store.get(
        body["corrected_memory_id"]
    )
    assert old_memory is not None
    assert new_memory is not None
    assert old_memory.status.value=="corrected"
    assert old_memory.valid_to is not None
    assert old_memory.retrieval_eligible is False
    assert old_memory.embedding_eligible is False
    assert new_memory.status.value=="active"
    assert new_memory.normalized_fact=="I prefer instrumental jazz."
    assert new_memory.correction_of_memory_id==memory.memory_id
    assert new_memory.memory_id!=memory.memory_id
    assert new_memory.retrieval_eligible is True
    assert new_memory.embedding_eligible is True
def test_memory_correction_preserves_metadata(client):
    auth=register_and_login(client)
    memory=create_initial_memory(
        client,
        auth["access_token"]
    )
    response=correct_memory(
        client,
        auth["access_token"],
        memory.memory_id,
        metadata={
            "source":"settings_ui",
            "reason_code":"user_correction"
        }
    )
    assert response.status_code==200
    body=response.json()
    assert body["metadata"]["source"]=="settings_ui"
    assert body["metadata"]["reason_code"]=="user_correction"
    assert body["metadata"]["lifecycle_event_id"]
    assert body["metadata"]["source_event_id"]
def test_memory_correction_returns_404_for_missing_memory(client):
    auth=register_and_login(client)
    response=correct_memory(
        client,
        auth["access_token"],
        "MEMORY_DOES_NOT_EXIST"
    )
    assert response.status_code==404
    assert "was not found" in response.json()["detail"]
def test_memory_correction_rejects_cross_subject_memory(client):
    first_auth=register_and_login(
        client,
        username="testuser1"
    )
    second_auth=register_and_login(
        client,
        username="testuser2"
    )
    memory=create_initial_memory(
        client,
        first_auth["access_token"]
    )
    response=correct_memory(
        client,
        second_auth["access_token"],
        memory.memory_id
    )
    assert response.status_code==403
    assert "does not belong" in response.json()["detail"]
def test_memory_correction_requires_authentication(client):
    response=client.patch(
        "/v1/memories/MEMORY_001",
        json={
            "corrected_statement":"I prefer jazz.",
            "reason":"Correction"
        }
    )
    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"
def test_memory_correction_rejects_empty_statement(client):
    auth=register_and_login(client)
    memory=create_initial_memory(
        client,
        auth["access_token"]
    )
    response=correct_memory(
        client,
        auth["access_token"],
        memory.memory_id,
        corrected_statement="   "
    )
    assert response.status_code==422
def test_memory_correction_rejects_empty_reason(client):
    auth=register_and_login(client)
    memory=create_initial_memory(
        client,
        auth["access_token"]
    )
    response=correct_memory(
        client,
        auth["access_token"],
        memory.memory_id,
        reason="   "
    )
    assert response.status_code==422
def test_memory_correction_rejects_unexpected_fields(client):
    auth=register_and_login(client)
    memory=create_initial_memory(
        client,
        auth["access_token"]
    )
    response=client.patch(
        f"/v1/memories/{memory.memory_id}",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json={
            "corrected_statement":"I prefer jazz.",
            "reason":"Correction",
            "unexpected":"not allowed"
        }
    )
    assert response.status_code==422
def test_memory_correction_rejects_empty_memory_id(client):
    auth=register_and_login(client)
    response=client.patch(
        "/v1/memories/%20",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json={
            "corrected_statement":"I prefer jazz.",
            "reason":"Correction"
        }
    )
    assert response.status_code==400