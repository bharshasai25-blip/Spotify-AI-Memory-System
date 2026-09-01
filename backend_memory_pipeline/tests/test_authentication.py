import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.auth.authentication import AuthContext,AuthenticationError,AuthenticationService,MockAuthenticator,create_test_auth_context

def build_authentication_service():
    credentials={
        "VALID_CREDENTIAL":{
            "subject_id":"REAL_SUBJECT_001",
            "authenticated":True,
            "authenticated_at":datetime.now(timezone.utc),
            "auth_method":"mock",
            "scopes":frozenset({"memory:read","memory:write","memory:correct","memory:delete","memory:explain"}),
            "token_id":"TOKEN_001"
        },
        "READ_ONLY_CREDENTIAL":{
            "subject_id":"REAL_SUBJECT_002",
            "authenticated":True,
            "authenticated_at":datetime.now(timezone.utc),
            "auth_method":"mock",
            "scopes":frozenset({"memory:read"}),
            "token_id":"TOKEN_002"
        }
    }
    contexts={
        credential:AuthContext(**data)
        for credential,data in credentials.items()
    }
    return AuthenticationService(MockAuthenticator(contexts))
def test_valid_authentication():
    service=build_authentication_service()
    context=service.authenticate("VALID_CREDENTIAL")
    assert isinstance(context,AuthContext)
    assert context.authenticated is True
    assert context.subject_id=="REAL_SUBJECT_001"
    assert context.auth_method=="mock"
    assert context.token_id=="TOKEN_001"
    assert context.scopes==frozenset({"memory:read","memory:write","memory:correct","memory:delete","memory:explain"})
    assert context.authenticated_at.tzinfo is not None
def test_read_only_authenticated_user():
    service=build_authentication_service()
    context=service.authenticate("READ_ONLY_CREDENTIAL")
    assert context.authenticated is True
    assert context.subject_id=="REAL_SUBJECT_002"
    assert context.scopes==frozenset({"memory:read"})
def test_missing_credential():
    service=build_authentication_service()
    with pytest.raises(AuthenticationError,match="credential is required"):
        service.authenticate("")
def test_whitespace_credential():
    service=build_authentication_service()
    with pytest.raises(AuthenticationError,match="credential is required"):
        service.authenticate("   ")
def test_invalid_credential():
    service=build_authentication_service()
    with pytest.raises(AuthenticationError,match="Invalid authentication credential"):
        service.authenticate("INVALID_CREDENTIAL")
def test_unauthenticated_context_is_rejected():
    context=AuthContext(
        subject_id="REAL_SUBJECT_003",
        authenticated=False,
        authenticated_at=datetime.now(timezone.utc),
        auth_method="mock",
        scopes=frozenset({"memory:read"}),
        token_id="TOKEN_003"
    )
    service=AuthenticationService(
        MockAuthenticator({"UNAUTHENTICATED":context})
    )
    with pytest.raises(AuthenticationError,match="Authentication failed"):
        service.authenticate("UNAUTHENTICATED")
def test_missing_subject_identity_is_rejected():
    context=AuthContext(
        subject_id="",
        authenticated=True,
        authenticated_at=datetime.now(timezone.utc),
        auth_method="mock",
        scopes=frozenset({"memory:read"}),
        token_id="TOKEN_004"
    )
    service=AuthenticationService(
        MockAuthenticator({"MISSING_SUBJECT":context})
    )
    with pytest.raises(AuthenticationError,match="identity is missing"):
        service.authenticate("MISSING_SUBJECT")
def test_missing_authentication_method_is_rejected():
    context=AuthContext(
        subject_id="REAL_SUBJECT_005",
        authenticated=True,
        authenticated_at=datetime.now(timezone.utc),
        auth_method="",
        scopes=frozenset({"memory:read"}),
        token_id="TOKEN_005"
    )
    service=AuthenticationService(
        MockAuthenticator({"MISSING_METHOD":context})
    )
    with pytest.raises(AuthenticationError,match="method is missing"):
        service.authenticate("MISSING_METHOD")
def test_naive_timestamp_is_rejected():
    context=AuthContext(
        subject_id="REAL_SUBJECT_006",
        authenticated=True,
        authenticated_at=datetime.now(),
        auth_method="mock",
        scopes=frozenset({"memory:read"}),
        token_id="TOKEN_006"
    )
    service=AuthenticationService(
        MockAuthenticator({"NAIVE_TIMESTAMP":context})
    )
    with pytest.raises(AuthenticationError,match="timezone-aware"):
        service.authenticate("NAIVE_TIMESTAMP")
def test_scopes_are_preserved():
    scopes={"memory:read","memory:write"}
    context=create_test_auth_context(
        subject_id="REAL_SUBJECT_007",
        scopes=scopes
    )
    assert context.scopes==frozenset(scopes)
def test_test_context_is_authenticated():
    context=create_test_auth_context(
        subject_id="REAL_SUBJECT_008",
        scopes={"memory:read"}
    )
    assert context.authenticated is True
    assert context.subject_id=="REAL_SUBJECT_008"
    assert context.auth_method=="mock"
    assert context.authenticated_at.tzinfo is not None