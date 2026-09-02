import os

import pytest
from fastapi.testclient import TestClient

from backend_memory_pipeline.api.app import app
from backend_memory_pipeline.api.dependencies import (
    get_revoked_token_store,
    get_user_repository
)


@pytest.fixture(autouse=True)
def reset_api_state():
    repository=get_user_repository()
    repository._users.clear()
    repository._subjects.clear()
    get_revoked_token_store().clear()

    original_secret=os.environ.get("API_AUTH_SECRET")
    os.environ["API_AUTH_SECRET"] = (
        "test-api-auth-secret-2026-abcdefghijklmnopqrstuvwxyz"
    )

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

    body=response.json()

    assert body["access_token"]
    assert body["subject_id"]

    return body


def auth_headers(auth):
    return {
        "Authorization":f"Bearer {auth['access_token']}"
    }


def preference_payload(
    preference="I prefer instrumental jazz."
):
    return {
        "preference":preference,
        "surface":"chat",
        "locale":"en-IN",
        "effective_at":"2026-08-28T10:00:00+00:00"
    }


def test_add_explicit_preference_creates_memory(client):
    auth=register_and_login(client)

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=preference_payload()
    )

    assert response.status_code==200

    body=response.json()

    assert body["schema_version"]=="1.0"
    assert body["status"] in {
        "accepted",
        "processed"
    }
    assert body["subject_id"]==auth["subject_id"]
    assert body["correlation_id"]
    assert body["source_event_id"]

    if body["memory_created"]:
        assert body["memory_id"] is not None


def test_add_explicit_preference_rejects_empty_preference(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["preference"]=""

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422


def test_add_explicit_preference_rejects_whitespace_preference(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["preference"]="   "

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422


def test_add_explicit_preference_rejects_empty_surface(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["surface"]=""

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422


def test_add_explicit_preference_rejects_empty_locale(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["locale"]=""

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422


def test_add_explicit_preference_rejects_naive_datetime(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["effective_at"]="2026-08-28T10:00:00"

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422


def test_add_explicit_preference_accepts_metadata(client):
    auth=register_and_login(client)

    payload=preference_payload(
        "I prefer calm acoustic music."
    )

    payload["metadata"]={
        "source":"api_test",
        "test_case":"metadata"
    }

    payload["context_entities"]={
        "genre":"acoustic"
    }

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==200

    body=response.json()

    assert body["subject_id"]==auth["subject_id"]
    assert body["correlation_id"]


def test_add_explicit_preference_preserves_correlation_id(client):
    auth=register_and_login(client)

    correlation_id="API_EXPLICIT_PREFERENCE_001"

    payload=preference_payload()
    payload["correlation_id"]=correlation_id

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==200

    body=response.json()

    assert body["correlation_id"]==correlation_id


def test_add_explicit_preference_preserves_idempotency_key(client):
    auth=register_and_login(client)

    idempotency_key="API_EXPLICIT_IDEMPOTENCY_001"

    payload=preference_payload()
    payload["idempotency_key"]=idempotency_key

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==200

    body=response.json()

    assert body["subject_id"]==auth["subject_id"]
    assert body["source_event_id"]


def test_add_explicit_preference_rejects_unexpected_fields(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["unexpected_field"]="not allowed"

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422


def test_add_explicit_preference_requires_authentication(client):
    response=client.post(
        "/v1/memories/preferences",
        json=preference_payload()
    )

    assert response.status_code==401
    assert response.headers["www-authenticate"]=="Bearer"


def test_add_explicit_preference_response_contains_provenance(client):
    auth=register_and_login(client)

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=preference_payload(
            "I prefer calm acoustic music."
        )
    )

    assert response.status_code==200

    body=response.json()

    assert body["source_event_id"]
    assert body["correlation_id"]
    assert body["subject_id"]==auth["subject_id"]


def test_add_explicit_preference_does_not_accept_client_subject_id(client):
    auth=register_and_login(client)

    payload=preference_payload()
    payload["subject_id"]="ANOTHER_USER"

    response=client.post(
        "/v1/memories/preferences",
        headers=auth_headers(auth),
        json=payload
    )

    assert response.status_code==422