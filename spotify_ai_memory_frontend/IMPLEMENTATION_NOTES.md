# Frontend update notes

This update adds the Spotify-inspired dark theme, left sidebar navigation, top-right consent controls, profile page, recommendations page, preferences management, memory library filters, persistent chat transcript UI, and API-backed logout.

## Run locally

From the `frontend` directory:

```bash
npm install
npm run dev
```

Set `VITE_API_BASE_URL` if the API is not available at `http://localhost:8000`.

## API dependencies

The frontend expects these routes in the matching backend update:

- `GET /v1/profile`
- `GET /v1/memories?query=&start=&end=`
- `GET /v1/recommendations`
- `GET /v1/chat/history?conversation_id=...`
- `GET /v1/memory/control`
- Existing auth, event, preference, memory correction/deletion, and consent routes.

Recommendations only show catalog entities with a stored Spotify external URL. The current backend does not implement Spotify's discovery/recommendation API; this page uses memory-linked catalog items already stored by the existing pipeline.
