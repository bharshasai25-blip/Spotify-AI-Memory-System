from __future__ import annotations
import os
import time
from typing import Any, Optional
import requests
from urllib.parse import urlparse

class MusicBrainzClientError(Exception):
    """Base exception for MusicBrainz client errors."""

class MusicBrainzRequestError(MusicBrainzClientError):
    """Raised when a MusicBrainz request fails."""

class MusicBrainzClient:
    BASE_URL = "https://musicbrainz.org/ws/2"
    MUSICBRAINZ_ENTITY_PATHS = {
    "artist": "artist",
    "track": "recording",
    "album": "release"}
    DEFAULT_USER_AGENT = f"SpotifyAIMemorySystem/1.0 ({os.getenv('MUSICBRAINZ_CONTACT_EMAIL', 'contact@example.com')})"

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: float = 10.0,
        min_request_interval: float = 1.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        if min_request_interval < 0:
            raise ValueError("min_request_interval cannot be negative")

        self.timeout = timeout
        self.min_request_interval = min_request_interval
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent or self.DEFAULT_USER_AGENT,
                "Accept": "application/json",
            }
        )
        self._last_request_at: Optional[float] = None

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return

        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_request_interval - elapsed

        if remaining > 0:
            time.sleep(remaining)

    def _get(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        response = None
        last_request_error: Optional[requests.RequestException] = None
        # Retry transient service errors (including HTTP 503) a maximum of
        # twice after the initial request. Do not retry permanent 4xx errors.
        for attempt in range(3):
            self._wait_for_rate_limit()
            try:
                response = self.session.get(
                   url,
                   params=params,
                   timeout=self.timeout,
            )
                self._last_request_at = time.monotonic()
                last_request_error = None
            except requests.RequestException as exc:
                self._last_request_at = time.monotonic()
                last_request_error = exc
                if attempt >= 2:
                    raise MusicBrainzRequestError(
                        f"MusicBrainz request failed after 3 attempts: {exc}"
                    ) from exc
                time.sleep(2 ** attempt)
                continue

            if response.status_code not in {429, 500, 502, 503, 504} or attempt >= 2:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                retry_delay = max(2 ** attempt, float(retry_after)) if retry_after else 2 ** attempt
            except (TypeError, ValueError):
                retry_delay = 2 ** attempt
            time.sleep(retry_delay)

        if response is None:
            raise MusicBrainzRequestError(
                f"MusicBrainz request failed: {last_request_error or 'no response'}"
            )

        if response.status_code == 404:
            raise MusicBrainzRequestError(
                f"MusicBrainz resource not found: {path}"
            )

        if response.status_code == 429:
            raise MusicBrainzRequestError(
                "MusicBrainz rate limit exceeded after retrying"
            )

        if not response.ok:
            raise MusicBrainzRequestError(
                f"MusicBrainz request failed with HTTP "
                f"{response.status_code} after retries: {response.text[:500]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise MusicBrainzRequestError(
                "MusicBrainz returned invalid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise MusicBrainzRequestError(
                "MusicBrainz response must be a JSON object"
            )

        return payload

    def get_entity(
        self,
        entity_type: str,
        mbid: str,
        includes: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        if not entity_type or not entity_type.strip():
            raise ValueError("entity_type is required")

        if not mbid or not mbid.strip():
            raise ValueError("mbid is required")

        params = {
            "fmt": "json",
        }

        if includes:
            params["inc"] = "+".join(includes)

        return self._get(
            f"{self.MUSICBRAINZ_ENTITY_PATHS.get(entity_type.strip().lower(), entity_type.strip().lower())}/{mbid.strip()}",
            params=params,
        )

    def search_entity(
        self,
        entity_type: str,
        query: str,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not entity_type or not entity_type.strip():
            raise ValueError("entity_type is required")

        if not query or not query.strip():
            raise ValueError("query is required")

        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        if offset < 0:
            raise ValueError("offset cannot be negative")

        params = {
            "query": query.strip(),
            "fmt": "json",
            "limit": limit,
            "offset": offset,
        }
           
        return self._get(
            f"{self.MUSICBRAINZ_ENTITY_PATHS.get(entity_type.strip().lower(), entity_type.strip().lower())}",
            params=params,
        )

    def get_entity_with_relationships(
        self,
        entity_type: str,
        mbid: str,
    ) -> dict[str, Any]:
        includes = ["url-rels", "aliases"]
        if entity_type.strip().lower() == "track":
          includes.append("artist-credits")
        entity_payload = self.get_entity(
            entity_type=entity_type,
            mbid=mbid,
            includes=includes,
        )
        print("===== MUSICBRAINZ RELATIONS DEBUG =====")
        print("ENTITY TYPE:", entity_type)
        print("MBID:", mbid)
        print("MUSICBRAINZ ARTIST CREDIT:", entity_payload.get("artist-credit"))
        print("MUSICBRAINZ MBID:", entity_payload.get("id"))
        print("RELATIONS:", entity_payload.get("relations"))
        print("=======================================")
        return entity_payload

    @staticmethod
    def extract_spotify_urls(
        entity_payload: dict[str, Any],
    ) -> list[str]:
        spotify_urls: list[str] = []

        print("ENTITY TYPE PAYLOAD RELATIONS:", entity_payload.get("relations"))   
        for relationship in entity_payload.get("relations", []):
            if not isinstance(relationship, dict):
                continue

            url_data = relationship.get("url")
            if not isinstance(url_data, dict):
                continue

            resource = url_data.get("resource")
            print("RELATIONSHIP URL RESOURCE:", resource)
            if not isinstance(resource, str):
                continue

            if "open.spotify.com/" in resource:
                spotify_urls.append(resource)

        print("EXTRACTED SPOTIFY URLS:", spotify_urls)
        return list(dict.fromkeys(spotify_urls))


    @staticmethod
    def extract_spotify_mappings(
        entity_payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        mappings: list[dict[str, str]] = []

        for spotify_url in MusicBrainzClient.extract_spotify_urls(entity_payload):
            parsed = urlparse(spotify_url.strip())
            parts = [part for part in parsed.path.rstrip("/").split("/") if part]
            if parsed.scheme != "https" or parsed.netloc.casefold() not in {"open.spotify.com", "www.open.spotify.com"} or len(parts) != 2:
                continue
            spotify_type, spotify_id = parts
            if spotify_type not in {"track", "artist", "album"} or not spotify_id:
                continue
            mappings.append({"provider":"spotify","external_id":spotify_id,"external_url":f"https://open.spotify.com/{spotify_type}/{spotify_id}"})

        return mappings    