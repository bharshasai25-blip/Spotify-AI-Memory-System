import os
import pytest
from fastapi.testclient import TestClient
from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import (
    get_memory_query_orchestrator,
    get_user_repository
)
@pytest.fixture(autouse=True)
def reset_api_state():
    repository=get_user_repository()
    repository._users.clear()
    repository._subjects.clear()
    get_memory_query_orchestrator.cache_clear()
    original_secret=os.environ.get("API_AUTH_SECRET")
    os.environ["API_AUTH_SECRET"]="test-api-auth-secret-2026-abcdefghijklmnopqrstuvwxyz"
    yield
    repository._users.clear()
    repository._subjects.clear()
    get_memory_query_orchestrator.cache_clear()
    if original_secret is None:
        os.environ.pop("API_AUTH_SECRET",None)
    else:
        os.environ["API_AUTH_SECRET"]=original_secret
@pytest.fixture
def client():
    return TestClient(app)
def register_and_login(client,username="chatuser"):
    register_response=client.post(
        "/v1/auth/register",
        json={
            "username":username,
            "password":"testpassword123"
        }
    )
    assert register_response.status_code==200
    body=register_response.json()
    return body
def make_chat_request(query="What music do I prefer?"):
    return {
        "query":query,
        "surface":"chat",
        "locale":"en-IN",
        "requested_at":"2026-08-26T12:00:00+00:00",
        "max_response_characters":12000,
        "include_memory_references":True,
        "metadata":{
            "source":"api_test"
        }
    }
def test_chat_requires_authentication(client):
    response=client.post(
        "/v1/chat",
        json=make_chat_request("TEST_USER_001")
    )
    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"
'''    
def test_chat_rejects_cross_subject_request(client):
    auth=register_and_login(client)
    response=client.post(
        "/v1/chat",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json=make_chat_request("DIFFERENT_USER")
    )
    print("STATUS:",response.status_code)
    print("BODY:",response.json())
    assert response.status_code==403
    assert "Authenticated subject does not match" in response.json()["detail"]
'''    
def test_chat_returns_no_memory_fallback_when_store_is_empty(client):
    auth=register_and_login(client)
    response=client.post(
        "/v1/chat",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json=make_chat_request(
            "What music do I prefer?"
        )
    )

    print("CHAT STATUS:", response.status_code)
    print("CHAT RESPONSE:", response.text)

    assert response.status_code==200
    body=response.json()
    assert body["schema_version"]=="1.0"
    assert body["response"]["subject_id"]==auth["subject_id"]
    assert body["response"]["query"]=="What music do I prefer?"
    assert body["response"]["decision"]=="no_context"
    assert body["response"]["memory_grounded"] is False
    assert body["response"]["context_item_count"]==0
    assert body["response"]["response_text"]
    assert body["correlation_id"]
def test_chat_preserves_query(client):
    auth=register_and_login(client)
    query="What kind of music do I prefer?"
    response=client.post(
        "/v1/chat",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json=make_chat_request(
            query
        )
    )
    assert response.status_code==200
    assert response.json()["response"]["query"]==query
def test_chat_respects_memory_reference_setting(client):
    auth=register_and_login(client)
    payload=make_chat_request(auth["subject_id"])
    payload["include_memory_references"]=False
    response=client.post(
        "/v1/chat",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json=payload
    )
    assert response.status_code==200
    assert response.json()["response"]["memory_references"]==[]
def test_chat_rejects_empty_query(client):
    auth=register_and_login(client)
    payload=make_chat_request(auth["subject_id"])
    payload["query"]="   "
    response=client.post(
        "/v1/chat",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json=payload
    )
    assert response.status_code==422
'''    
def test_chat_rejects_subject_scope_mismatch(client):
    auth=register_and_login(client)
    payload=make_chat_request(auth["subject_id"])
    payload["subject_scope"]="DIFFERENT_USER"
    response=client.post(
        "/v1/chat",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json=payload
    )
    assert response.status_code==403
    assert "Authenticated subject does not match requested subject scope." in response.json()["detail"]
'''    