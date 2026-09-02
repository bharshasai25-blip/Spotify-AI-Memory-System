import os
import pytest
from backend_memory_pipeline.mcp.auth import SpotifyMemoryTokenVerifier
from backend_memory_pipeline.api.dependencies import (
    create_access_token,
    get_revoked_token_store,
    revoke_token,
)
class TestSpotifyMemoryTokenVerifier:
    @pytest.fixture(autouse=True)
    def setup(self,monkeypatch):
        monkeypatch.setenv("API_AUTH_SECRET","test-secret-key-for-mcp-auth-123456789")
        get_revoked_token_store().clear()
    @pytest.mark.anyio
    async def test_valid_token_returns_access_token(self):
        token=create_access_token("USER_001","testuser")
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token(token)
        assert result is not None
        assert result.token==token
        assert result.client_id=="spotify-ai-memory-client"
        assert result.scopes==["memory"]
        assert result.subject=="USER_001"
    @pytest.mark.anyio
    async def test_valid_token_preserves_claims(self):
        token=create_access_token("USER_001","testuser")
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token(token)
        assert result is not None
        assert result.claims is not None
        assert result.claims["subject_id"]=="USER_001"
        assert result.claims["username"]=="testuser"
        assert "token_id" in result.claims
    @pytest.mark.anyio
    async def test_invalid_token_returns_none(self):
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token("invalid-token")
        assert result is None
    @pytest.mark.anyio
    async def test_malformed_jwt_returns_none(self):
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token("abc.def.ghi")
        assert result is None
    @pytest.mark.anyio
    async def test_empty_token_returns_none(self):
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token("")
        assert result is None
    @pytest.mark.anyio
    async def test_revoked_token_returns_none(self):
        token=create_access_token("USER_001","testuser")
        verifier=SpotifyMemoryTokenVerifier()
        authenticated_subject=__import__(
            "backend_memory_pipeline.api.dependencies",
            fromlist=["decode_access_token"]
        ).decode_access_token(token)
        revoke_token(authenticated_subject.token_id)
        result=await verifier.verify_token(token)
        assert result is None
    @pytest.mark.anyio
    async def test_token_for_different_subject_returns_that_authenticated_subject(self):
        token=create_access_token("USER_002","anotheruser")
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token(token)
        assert result is not None
        assert result.subject=="USER_002"
        assert result.claims["subject_id"]=="USER_002"
        assert result.claims["username"]=="anotheruser"
    @pytest.mark.anyio
    async def test_client_id_is_server_defined(self):
        token=create_access_token("USER_001","testuser")
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token(token)
        assert result is not None
        assert result.client_id=="spotify-ai-memory-client"
    @pytest.mark.anyio
    async def test_scope_is_memory(self):
        token=create_access_token("USER_001","testuser")
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token(token)
        assert result is not None
        assert result.scopes==["memory"]
    @pytest.mark.anyio
    async def test_token_id_is_preserved_in_claims(self):
        token=create_access_token("USER_001","testuser")
        verifier=SpotifyMemoryTokenVerifier()
        result=await verifier.verify_token(token)
        assert result is not None
        assert result.claims["token_id"]
