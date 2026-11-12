import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.auth.authentication import AuthContext
from backend_memory_pipeline.auth.authorization import AuthorizationError,AuthorizationRequest,AuthorizationService


def create_context(subject_id="TEST_SUBJECT_001",scopes=None,authenticated=True):
    if scopes is None:
        scopes={"memory:read","memory:write","memory:correct","memory:delete","memory:explain"}
    return AuthContext(
        subject_id=subject_id,
        authenticated=authenticated,
        authenticated_at=datetime.now(timezone.utc),
        auth_method="mock",
        scopes=frozenset(scopes),
        token_id="TEST_TOKEN"
    )

def create_authorization_service():
    return AuthorizationService()

def test_authorize_memory_read():
    service=create_authorization_service()
    context=create_context(scopes={"memory:read"})
    service.authorize(
        auth_context=context,
        operation="memory:read",
        subject_id="TEST_SUBJECT_001",
        resource_subject_id="TEST_SUBJECT_001"
    )

def test_authorize_memory_write():
    service=create_authorization_service()
    context=create_context(scopes={"memory:write"})
    service.authorize(
        auth_context=context,
        operation="memory:write",
        subject_id="TEST_SUBJECT_001",
        resource_subject_id="TEST_SUBJECT_001"
    )

def test_authorize_memory_correct():
    service=create_authorization_service()
    context=create_context(scopes={"memory:correct"})
    service.authorize(
        auth_context=context,
        operation="memory:correct",
        subject_id="TEST_SUBJECT_001",
        resource_subject_id="TEST_SUBJECT_001"
    )

def test_authorize_memory_delete():
    service=create_authorization_service()
    context=create_context(scopes={"memory:delete"})
    service.authorize(
        auth_context=context,
        operation="memory:delete",
        subject_id="TEST_SUBJECT_001",
        resource_subject_id="TEST_SUBJECT_001"
    )

def test_authorize_memory_explain():
    service=create_authorization_service()
    context=create_context(scopes={"memory:explain"})
    service.authorize(
        auth_context=context,
        operation="memory:explain",
        subject_id="TEST_SUBJECT_001",
        resource_subject_id="TEST_SUBJECT_001"
    )

def test_missing_required_scope_is_rejected():
    service=create_authorization_service()
    context=create_context(scopes={"memory:read"})
    with pytest.raises(AuthorizationError,match="Missing required scope"):
        service.authorize(
            auth_context=context,
            operation="memory:write",
            subject_id="TEST_SUBJECT_001",
            resource_subject_id="TEST_SUBJECT_001"
        )

def test_subject_mismatch_is_rejected():
    service=create_authorization_service()
    context=create_context(subject_id="TEST_SUBJECT_001")
    with pytest.raises(AuthorizationError,match="Authenticated subject does not match requested subject"):
        service.authorize(
            auth_context=context,
            operation="memory:read",
            subject_id="TEST_SUBJECT_002",
            resource_subject_id="TEST_SUBJECT_002"
        )

def test_cross_subject_resource_access_is_rejected():
    service=create_authorization_service()
    context=create_context(subject_id="TEST_SUBJECT_001")
    with pytest.raises(AuthorizationError,match="Cross-subject access is not authorized"):
        service.authorize(
            auth_context=context,
            operation="memory:read",
            subject_id="TEST_SUBJECT_001",
            resource_subject_id="TEST_SUBJECT_002"
        )

def test_unauthenticated_context_is_rejected():
    service=create_authorization_service()
    context=create_context(authenticated=False)
    with pytest.raises(AuthorizationError,match="Authenticated identity is required"):
        service.authorize(
            auth_context=context,
            operation="memory:read",
            subject_id="TEST_SUBJECT_001",
            resource_subject_id="TEST_SUBJECT_001"
        )

def test_missing_authenticated_subject_is_rejected():
    service=create_authorization_service()
    context=create_context(subject_id="")
    with pytest.raises(AuthorizationError,match="Authenticated subject identity is missing"):
        service.authorize(
            auth_context=context,
            operation="memory:read",
            subject_id="TEST_SUBJECT_001",
            resource_subject_id="TEST_SUBJECT_001"
        )

def test_missing_operation_is_rejected():
    service=create_authorization_service()
    context=create_context()
    with pytest.raises(AuthorizationError,match="Authorization operation is required"):
        service.authorize(
            auth_context=context,
            operation="",
            subject_id="TEST_SUBJECT_001",
            resource_subject_id="TEST_SUBJECT_001"
        )

def test_unsupported_operation_is_rejected():
    service=create_authorization_service()
    context=create_context()
    with pytest.raises(AuthorizationError,match="Unsupported authorization operation"):
        service.authorize(
            auth_context=context,
            operation="memory:export",
            subject_id="TEST_SUBJECT_001",
            resource_subject_id="TEST_SUBJECT_001"
        )

def test_missing_subject_is_rejected():
    service=create_authorization_service()
    context=create_context()
    with pytest.raises(AuthorizationError,match="Subject identity is required"):
        service.authorize(
            auth_context=context,
            operation="memory:read",
            subject_id="",
            resource_subject_id=None
        )

def test_missing_resource_subject_is_allowed_when_not_required():
    service=create_authorization_service()
    context=create_context(subject_id="TEST_SUBJECT_001",scopes={"memory:read"})
    service.authorize(
        auth_context=context,
        operation="memory:read",
        subject_id="TEST_SUBJECT_001"
    )

def test_authorization_request_wrapper():
    service=create_authorization_service()
    context=create_context(subject_id="TEST_SUBJECT_001",scopes={"memory:write"})
    request=AuthorizationRequest(
        operation="memory:write",
        subject_id="TEST_SUBJECT_001",
        resource_subject_id="TEST_SUBJECT_001"
    )

    service.authorize_request(context,request)
def test_synthetic_identity_can_use_same_authorization_contract():
    service=create_authorization_service()
    context=create_context(
        subject_id="USER_000001",
        scopes={"memory:read","memory:write"}
    )
    service.authorize(
        auth_context=context,
        operation="memory:read",
        subject_id="USER_000001",
        resource_subject_id="USER_000001"
    )
    service.authorize(
        auth_context=context,
        operation="memory:write",
        subject_id="USER_000001",
        resource_subject_id="USER_000001"
    )
    
def test_synthetic_cross_subject_isolation():
    service=create_authorization_service()
    context=create_context(
        subject_id="USER_000001",
        scopes={"memory:read"}
    )
    with pytest.raises(AuthorizationError,match="Cross-subject access is not authorized"):
        service.authorize(
            auth_context=context,
            operation="memory:read",
            subject_id="USER_000001",
            resource_subject_id="USER_000002"
        )