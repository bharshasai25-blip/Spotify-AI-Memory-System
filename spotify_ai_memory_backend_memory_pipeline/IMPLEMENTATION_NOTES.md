# Backend update notes

## Added

- `persistence/postgres/conversation_repository.py`: persists chat transcripts separately from long-term memories in the `conversation_messages` table.
- `GET /v1/chat/history`: returns a conversation transcript scoped to the authenticated subject.
- `POST /v1/chat` accepts an optional `conversation_id`, stores user and assistant messages, and supplies recent prior messages to the Gemini chat context.
- `GET /v1/profile`: returns the authenticated account's username and subject ID.
- `GET /v1/memories`: lists the authenticated user's stored memories and supports query and date filtering.
- `GET /v1/recommendations`: returns memory-linked catalog entities only when consent is opted in and only when a Spotify URL is already stored.
- `GET /v1/memory/control`: reads the persisted consent state so the frontend can show the backend's actual state.

## Existing routes reused

- `POST /v1/auth/logout` revokes the active token through the configured revoked-token store.
- `POST /v1/memories/preferences`, `PATCH /v1/memories/{memory_id}`, and `DELETE /v1/memories/{memory_id}` manage preferences and memories.
- `POST /v1/events` supports `follow` and `save` event types.

## Configuration

The conversation repository uses the same `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` environment variables as the other PostgreSQL repositories. Token revocation continues to use `REVOKED_TOKEN_STORE_BACKEND=postgres`.

## Validation status

Python syntax compilation passed. Full API runtime tests could not be executed in the packaging environment because project runtime dependencies (including `httpx2`, `psycopg`, `google.genai`, and `mcp`) are not installed there. Run the existing backend test suite in the configured project environment before deployment.
