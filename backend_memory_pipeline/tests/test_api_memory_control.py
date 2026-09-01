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
def submit_control(client,token,action,metadata=None):
    return client.post(
        "/v1/memory/control",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json={
            "action":action,
            "metadata":metadata or {}
        }
    )
def test_opt_in_is_accepted(client):
    auth=register_and_login(client)
    response=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["subject_id"]==auth["subject_id"]
    assert body["action"]=="opt_in"
    assert body["previous_state"]=="unknown"
    assert body["current_state"]=="opted_in"
    assert body["changed"] is True
    assert body["correlation_id"]
    assert body["timestamp"]
    assert body["reason"]
def test_opt_out_is_accepted_after_opt_in(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert first.status_code==200
    response=submit_control(
        client,
        auth["access_token"],
        "opt_out"
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["action"]=="opt_out"
    assert body["previous_state"]=="opted_in"
    assert body["current_state"]=="opted_out"
    assert body["changed"] is True
def test_pause_is_accepted_after_opt_in(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert first.status_code==200
    response=submit_control(
        client,
        auth["access_token"],
        "pause"
    )
    assert response.status_code==200
    body=response.json()
    assert body["action"]=="pause"
    assert body["previous_state"]=="opted_in"
    assert body["current_state"]=="paused"
    assert body["changed"] is True
def test_resume_is_accepted_after_pause(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert first.status_code==200
    second=submit_control(
        client,
        auth["access_token"],
        "pause"
    )
    assert second.status_code==200
    response=submit_control(
        client,
        auth["access_token"],
        "resume"
    )
    assert response.status_code==200
    body=response.json()
    assert body["action"]=="resume"
    assert body["previous_state"]=="paused"
    assert body["current_state"]=="opted_in"
    assert body["changed"] is True
def test_unknown_state_can_opt_in(client):
    auth=register_and_login(client)
    response=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert response.status_code==200
    body=response.json()
    assert body["previous_state"]=="unknown"
    assert body["current_state"]=="opted_in"
def test_unknown_state_can_opt_out(client):
    auth=register_and_login(client)
    response=submit_control(
        client,
        auth["access_token"],
        "opt_out"
    )
    assert response.status_code==200
    body=response.json()
    assert body["previous_state"]=="unknown"
    assert body["current_state"]=="opted_out"
def test_unknown_state_can_pause(client):
    auth=register_and_login(client)
    response=submit_control(
        client,
        auth["access_token"],
        "pause"
    )
    assert response.status_code==200
    body=response.json()
    assert body["previous_state"]=="unknown"
    assert body["current_state"]=="paused"
def test_invalid_transition_is_rejected(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert first.status_code==200
    response=submit_control(
        client,
        auth["access_token"],
        "resume"
    )
    assert response.status_code==400
    assert "Consent control failed" in response.json()["detail"]
def test_opt_out_then_resume_is_rejected(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "opt_out"
    )
    assert first.status_code==200
    response=submit_control(
        client,
        auth["access_token"],
        "resume"
    )
    assert response.status_code==400
    assert "Consent control failed" in response.json()["detail"]
def test_pause_then_opt_out_is_rejected(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "pause"
    )
    assert first.status_code==200
    response=submit_control(
        client,
        auth["access_token"],
        "opt_out"
    )
    assert response.status_code==400
    assert "Consent control failed" in response.json()["detail"]
def test_unauthenticated_control_is_rejected(client):
    response=client.post(
        "/v1/memory/control",
        json={
            "action":"opt_in"
        }
    )
    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"
def test_invalid_control_action_is_rejected(client):
    auth=register_and_login(client)
    response=submit_control(
        client,
        auth["access_token"],
        "delete"
    )
    assert response.status_code==422
def test_unexpected_control_fields_are_rejected(client):
    auth=register_and_login(client)
    response=client.post(
        "/v1/memory/control",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json={
            "action":"opt_in",
            "unexpected":"not allowed"
        }
    )
    assert response.status_code==422
def test_control_metadata_is_preserved(client):
    auth=register_and_login(client)
    response=submit_control(
        client,
        auth["access_token"],
        "opt_in",
        metadata={
            "source":"settings_ui",
            "reason":"user_requested"
        }
    )
    assert response.status_code==200
    body=response.json()
    assert body["current_state"]=="opted_in"
    assert body["metadata"]["source"]=="settings_ui"
    assert body["metadata"]["reason"]=="user_requested"
    assert body["metadata"]["state_record"]["state"]=="opted_in"
def test_control_is_subject_scoped(client):
    first_auth=register_and_login(
        client,
        username="testuser1"
    )
    second_auth=register_and_login(
        client,
        username="testuser2"
    )
    first=submit_control(
        client,
        first_auth["access_token"],
        "opt_in"
    )
    second=submit_control(
        client,
        second_auth["access_token"],
        "opt_in"
    )
    assert first.status_code==200
    assert second.status_code==200
    first_body=first.json()
    second_body=second.json()
    assert first_body["subject_id"]==first_auth["subject_id"]
    assert second_body["subject_id"]==second_auth["subject_id"]
    assert first_body["previous_state"]=="unknown"
    assert second_body["previous_state"]=="unknown"
def test_repeated_same_state_action_is_rejected_as_invalid_transition(client):
    auth=register_and_login(client)
    first=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert first.status_code==200
    second=submit_control(
        client,
        auth["access_token"],
        "opt_in"
    )
    assert second.status_code==400
    assert "Consent control failed" in second.json()["detail"]