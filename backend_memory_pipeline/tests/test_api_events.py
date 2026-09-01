import os
import pytest
from fastapi.testclient import TestClient
from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import (
    get_memory_write_orchestrator,
    get_session_manager,
    get_user_repository,
    get_revoked_token_store
)
@pytest.fixture(autouse=True)
def reset_api_state():
    repository=get_user_repository()
    repository._users.clear()
    repository._subjects.clear()
    get_memory_write_orchestrator.cache_clear()
    get_session_manager.cache_clear()
    get_revoked_token_store().clear()
    original_secret=os.environ.get("API_AUTH_SECRET")
    os.environ["API_AUTH_SECRET"]="test-api-auth-secret-2026-abcdefghijklmnopqrstuvwxyz"
    yield
    repository._users.clear()
    repository._subjects.clear()
    get_revoked_token_store().clear()
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
    register_response=client.post(
        "/v1/auth/register",
        json={
            "username":username,
            "password":"testpassword123"
        }
    )
    assert register_response.status_code==200
    return register_response.json()
def make_event(
    event_type="ai_interaction",
    text="I prefer calm acoustic music.",
    idempotency_key=None,
    metadata=None,
    entity=None,
    surface="chat",
    locale="en-IN"
):
    payload={
        "event_type":event_type,
        "surface":surface,
        "locale":locale,
        "text":text,
        "entity":entity,
        "context_entities":{},
        "metadata":metadata or {}
    }
    if idempotency_key is not None:
        payload["idempotency_key"]=idempotency_key
    return payload
def submit_event(client,token,event):
    return client.post(
        "/v1/events",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json=event
    )
def test_ai_interaction_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="ai_interaction",
        text="I prefer calm acoustic music."
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    print("STATUS:",response.status_code)
    print("BODY:",response.json())
    assert response.status_code==200
'''
def test_ai_interaction_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="ai_interaction",
        text="I prefer calm acoustic music."
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["event_id"]
    assert body["subject_id"]==auth["subject_id"]
    assert body["duplicate"] is False
    assert body["correlation_id"]
    assert body["metadata"]["event_type"]=="ai_interaction"
    assert body["metadata"]["session_id"].startswith("session:")
'''    
def test_playback_play_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="playback",
        text=None,
        metadata={
            "playback_action":"play"
        },
        surface="player"
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["metadata"]["event_type"]=="playback"
def test_playback_pause_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="playback",
        text=None,
        metadata={
            "playback_action":"pause"
        },
        surface="player"
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    assert response.json()["status"]=="accepted"
def test_save_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="save",
        text=None,
        idempotency_key="IDEMP_SAVE_001",
        surface="player"
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["metadata"]["event_type"]=="save"
def test_follow_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="follow",
        text=None,
        idempotency_key="IDEMP_FOLLOW_001",
        surface="artist"
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["metadata"]["event_type"]=="follow"
def test_skip_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="skip",
        text=None,
        idempotency_key="IDEMP_SKIP_001",
        surface="player"
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["metadata"]["event_type"]=="skip"
def test_explicit_preference_event_is_accepted(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="explicit_preference",
        text="I prefer calm acoustic music."
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["status"]=="accepted"
    assert body["subject_id"]==auth["subject_id"]
    assert body["metadata"]["event_type"]=="explicit_preference"
def test_unauthenticated_event_is_rejected(client):
    event=make_event()
    response=client.post(
        "/v1/events",
        json=event
    )
    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"
def test_duplicate_event_is_idempotent(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="ai_interaction",
        text="I prefer calm acoustic music.",
        idempotency_key="SAME_IDEMPOTENCY_KEY"
    )
    first=submit_event(
        client,
        auth["access_token"],
        event
    )
    second=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert first.status_code==200
    assert second.status_code==200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["status"]=="duplicate"
    assert first.json()["event_id"]==second.json()["event_id"]
    assert first.json()["correlation_id"]!=second.json()["correlation_id"]
def test_same_idempotency_key_with_different_event_is_rejected(client):
    auth=register_and_login(client)
    first_event=make_event(
        event_type="ai_interaction",
        text="I prefer acoustic music.",
        idempotency_key="SAME_KEY"
    )
    second_event=make_event(
        event_type="ai_interaction",
        text="I prefer jazz.",
        idempotency_key="SAME_KEY"
    )
    first=submit_event(
        client,
        auth["access_token"],
        first_event
    )
    second=submit_event(
        client,
        auth["access_token"],
        second_event
    )
    assert first.status_code==200
    assert second.status_code==409
def test_invalid_playback_action_is_rejected(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="playback",
        text=None,
        metadata={
            "playback_action":"rewind"
        },
        surface="player"
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    print("STATUS:",response.status_code)
    print("BODY:",response.json())
    assert response.status_code==422
def test_ai_interaction_without_text_is_rejected(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="ai_interaction",
        text=None
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    print("STATUS:",response.status_code)
    print("BODY:",response.json())
    assert response.status_code==422
def test_unexpected_event_fields_are_rejected(client):
    auth=register_and_login(client)
    event=make_event()
    event["unexpected"]="not allowed"
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==422
def test_event_uses_session_manager_session(client):
    auth=register_and_login(client)
    event=make_event(
        event_type="ai_interaction",
        text="I prefer calm acoustic music."
    )
    response=submit_event(
        client,
        auth["access_token"],
        event
    )
    assert response.status_code==200
    body=response.json()
    assert body["metadata"]["session_id"]
    assert body["metadata"]["session_id"].startswith("session:")
def test_multiple_events_reuse_active_session(client):
    auth=register_and_login(client)
    first=submit_event(
        client,
        auth["access_token"],
        make_event(
            event_type="playback",
            text=None,
            metadata={
                "playback_action":"play"
            },
            surface="player"
        )
    )
    second=submit_event(
        client,
        auth["access_token"],
        make_event(
            event_type="playback",
            text=None,
            metadata={
                "playback_action":"pause"
            },
            surface="player"
        )
    )
    assert first.status_code==200
    assert second.status_code==200
    assert (
        first.json()["metadata"]["session_id"]
        ==second.json()["metadata"]["session_id"]
    )