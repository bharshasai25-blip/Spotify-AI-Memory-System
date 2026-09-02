from mcp.server.auth.provider import AccessToken, TokenVerifier

from backend_memory_pipeline.api.dependencies import (
    decode_access_token,
    is_token_revoked,
)


class SpotifyMemoryTokenVerifier(TokenVerifier):
    """Adapts the existing API token validation to MCP."""

    async def verify_token(
        self,
        token: str,
    ) -> AccessToken | None:
        try:
            authenticated_subject = decode_access_token(token)
        except Exception:
            return None

        if is_token_revoked(authenticated_subject.token_id):
            return None

        return AccessToken(
            token=token,
            client_id="spotify-ai-memory-client",
            scopes=["memory"],
            subject=authenticated_subject.subject_id,
            claims={
                "subject_id": authenticated_subject.subject_id,
                "username": authenticated_subject.username,
                "token_id": authenticated_subject.token_id,
            },
        )