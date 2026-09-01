import os
import pytest
from fastapi.testclient import TestClient
from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import get_revoked_token_store, get_user_repository
@pytest.fixture(autouse=True)
def reset_user_repository():
    repository=get_user_repository()
    repository._users.clear()
    repository._subjects.clear()
    get_revoked_token_store().clear()
    original_secret=os.environ.get("API_AUTH_SECRET")
    os.environ["API_AUTH_SECRET"]="test-api-auth-secret-2026-abcdefghijklmnopqrstuvwxyz"
    yield
    repository._users.clear()
    repository._subjects.clear()
    get_revoked_token_store().clear()
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
def test_register_creates_user_and_returns_token(client):
    response=client.post(
        "/v1/auth/register",
        json={
            "username":"testuser",
            "password":"testpassword123",
            "metadata":{
                "source":"api_test"
            }
        }
    )
    assert response.status_code==200
    body=response.json()
    assert body["schema_version"]=="1.0"
    assert body["token_type"]=="bearer"
    assert body["expires_in"]>0
    assert body["username"]=="testuser"
    assert body["subject_id"]
    assert body["access_token"]
    assert body["correlation_id"]
def test_register_rejects_duplicate_username(client):
    payload={
        "username":"testuser",
        "password":"testpassword123"
    }
    first=client.post(
        "/v1/auth/register",
        json=payload
    )
    second=client.post(
        "/v1/auth/register",
        json=payload
    )
    assert first.status_code==200
    assert second.status_code==400
    assert "already exists" in second.json()["detail"]
def test_login_succeeds_after_registration(client):
    register_response=client.post(
        "/v1/auth/register",
        json={
            "username":"testuser",
            "password":"testpassword123"
        }
    )
    assert register_response.status_code==200
    subject_id=register_response.json()["subject_id"]
    login_response=client.post(
        "/v1/auth/login",
        json={
            "username":"testuser",
            "password":"testpassword123"
        }
    )
    assert login_response.status_code==200
    body=login_response.json()
    assert body["token_type"]=="bearer"
    assert body["access_token"]
    assert body["subject_id"]==subject_id
    assert body["username"]=="testuser"
def test_login_rejects_wrong_password(client):
    client.post(
        "/v1/auth/register",
        json={
            "username":"testuser",
            "password":"testpassword123"
        }
    )
    response=client.post(
        "/v1/auth/login",
        json={
            "username":"testuser",
            "password":"wrongpassword"
        }
    )
    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"
    assert response.json()["detail"]=="Invalid username or password."
def test_login_rejects_unknown_user(client):
    response=client.post(
        "/v1/auth/login",
        json={
            "username":"unknownuser",
            "password":"testpassword123"
        }
    )
    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"
def test_register_rejects_short_password(client):
    response=client.post(
        "/v1/auth/register",
        json={
            "username":"testuser",
            "password":"short"
        }
    )
    assert response.status_code==422
def test_register_rejects_short_username(client):
    response=client.post(
        "/v1/auth/register",
        json={
            "username":"ab",
            "password":"testpassword123"
        }
    )
    assert response.status_code==422
def test_register_rejects_unexpected_fields(client):
    response=client.post(
        "/v1/auth/register",
        json={
            "username":"testuser",
            "password":"testpassword123",
            "unexpected":"value"
        }
    )
    assert response.status_code==422

def test_logout_is_accepted(client):
    auth=register_and_login(client)

    response=client.post(
        "/v1/auth/logout",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json={}
    )

    assert response.status_code==200

    body=response.json()

    assert body["status"]=="accepted"
    assert body["subject_id"]==auth["subject_id"]
    assert body["username"]==auth["username"]
    assert body["token_revoked"] is True
    assert body["correlation_id"]
    assert body["timestamp"]

def test_logout_revokes_access_token(client):
    auth=register_and_login(client)

    token=auth["access_token"]

    logout_response=client.post(
        "/v1/auth/logout",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json={}
    )

    assert logout_response.status_code==200

    protected_response=client.post(
        "/v1/events",
        headers={
            "Authorization":f"Bearer {token}"
        },
        json={
            "event_type":"ai_interaction",
            "surface":"chat",
            "locale":"en-IN",
            "text":"I prefer jazz.",
            "entity":None,
            "context_entities":{},
            "metadata":{}
        }
    )

    assert protected_response.status_code==401

def test_logout_requires_authentication(client):
    response=client.post(
        "/v1/auth/logout",
        json={}
    )

    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"

def test_logout_rejects_unexpected_fields(client):
    auth=register_and_login(client)

    response=client.post(
        "/v1/auth/logout",
        headers={
            "Authorization":f"Bearer {auth['access_token']}"
        },
        json={
            "unexpected":"not allowed"
        }
    )

    assert response.status_code==422                