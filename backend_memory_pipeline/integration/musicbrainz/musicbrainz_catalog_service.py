from __future__ import annotations
from typing import Any
from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_client import MusicBrainzClient
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_mapper import MusicBrainzMapper
from backend_memory_pipeline.persistence.postgres.entity_repository import PostgreSQLCatalogRepository
from backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity

class MusicBrainzCatalogService:
    def __init__(
        self,
        client: MusicBrainzClient,
        repository: PostgreSQLCatalogRepository,
        mapper: type[MusicBrainzMapper] = MusicBrainzMapper,
    ) -> None:
        self.client = client
        self.repository = repository
        self.mapper = mapper

    def catalog_entity_by_mbid(
        self,
        entity_type: str,
        mbid: str,
    ) -> CatalogEntityV1:
        payload = self.client.get_entity_with_relationships(
            entity_type=entity_type,
            mbid=mbid,
        )
        entity = self.mapper.to_catalog_entity(
            payload=payload,
            entity_type=entity_type,
        )
        self.repository.put(entity)
        self._persist_spotify_mappings(entity, payload)
        return entity

    @staticmethod
    def _normalize(value: Any) -> str:
        return " ".join(str(value or "").strip().casefold().split())

    @classmethod
    def _recording_artist_names(cls, result: dict[str, Any]) -> list[str]:
        credit = result.get("artist-credit", [])
        names: list[str] = []
        if isinstance(credit, list):
            for item in credit:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("name"), str):
                    names.append(item["name"])
                artist = item.get("artist")
                if isinstance(artist, dict) and isinstance(artist.get("name"), str):
                    names.append(artist["name"])
        return list(dict.fromkeys(names))

    def search_candidates(
        self,
        entity_type: str,
        query: str,
        limit: int = 10,
        context_artist: str | None = None,
        exact_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return exact MusicBrainz candidates without writing to the catalog.

        Candidate discovery is deliberately read-only. Persistence happens only
        after a candidate has been selected or a unique exact match is proven.
        """
        normalized_type = entity_type.strip().lower()
        search_query = query
        if normalized_type == "track" and context_artist:
            escaped_title = query.replace('"', '\\"')
            escaped_artist = context_artist.replace('"', '\\"')
            search_query = f'recording:"{escaped_title}" AND artist:"{escaped_artist}"'
        search_result = self.client.search_entity(
            entity_type=entity_type, query=search_query, limit=limit
        )
        result_key = {"artist": "artists", "track": "recordings", "album": "releases"}.get(
            normalized_type, f"{normalized_type}s"
        )
        results = search_result.get(result_key, [])
        if not isinstance(results, list):
            return []
        wanted_name = self._normalize(query)
        exact_results = [
            item for item in results
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("id", "").strip()
            and (not exact_only or self._normalize(item.get("title") or item.get("name")) == wanted_name)
        ]
        if normalized_type == "track" and context_artist:
            wanted_artist = self._normalize(context_artist)
            exact_results = [
                item for item in exact_results
                if wanted_artist in {self._normalize(name) for name in self._recording_artist_names(item)}
            ]
        candidates = []
        for item in exact_results:
            releases = item.get("releases") or []
            release_names = [
                release.get("title") for release in releases
                if isinstance(release, dict) and isinstance(release.get("title"), str)
            ] if isinstance(releases, list) else []
            name = str(item.get("title") or item.get("name") or query).strip()
            artist_names = self._recording_artist_names(item)
            candidate = {
                "mbid": item["id"].strip(),
                "entity_type": normalized_type,
                "name": name,
                "artist_names": artist_names,
                "disambiguation": str(item.get("disambiguation") or "").strip(),
                "length_ms": item.get("length"),
                "release_names": list(dict.fromkeys(release_names))[:5],
                "score": item.get("score"),
                "already_cataloged": False,
            }
            canonical_id = f"musicbrainz:{normalized_type}:{item['id'].strip()}"
            try:
                existing = self.repository.get(canonical_id)
            except (AttributeError, NotImplementedError):
                existing = None
            if isinstance(existing, CatalogEntityV1):
                candidate["already_cataloged"] = True
                candidate["canonical_id"] = existing.entity_id
                try:
                    mappings = self.repository.list_external_mappings(existing.entity_id)
                except (AttributeError, NotImplementedError):
                    mappings = []
                direct = next((mapping.get("external_url") for mapping in mappings if isinstance(mapping, dict) and str(mapping.get("provider", "")).casefold() == "spotify" and mapping.get("external_url")), None)
            else:
                direct = None
            #from backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity
            candidate.update(spotify_link_for_catalog_entity(name, normalized_type, ", ".join(artist_names), direct))
            candidates.append(candidate)
        return candidates

    def search_and_catalog_entity(
        self,
        entity_type: str,
        query: str,
        limit: int = 10,
        context_artist: str | None = None,
    ) -> CatalogEntityV1:
        normalized_type = entity_type.strip().lower()
        search_query = query
        if normalized_type == "track" and context_artist:
            # MusicBrainz calls tracks "recordings" and supports Lucene fields.
            # Quoting each term makes the artist part of the search itself.
            escaped_title = query.replace('"', '\\"')
            escaped_artist = context_artist.replace('"', '\\"')
            search_query = f'recording:"{escaped_title}" AND artist:"{escaped_artist}"'
        search_result = self.client.search_entity(
            entity_type=entity_type,
            query=search_query,
            limit=limit)
        
        if normalized_type == "artist":
            result_key = "artists"
        elif normalized_type == "track":
            result_key = "recordings"
        elif normalized_type == "album":
            result_key = "releases"
        else:
            result_key = f"{normalized_type}s"
        results = search_result.get(result_key, [])
        print(f"MUSICBRAINZ QUERY: {search_query}")
        print(f"MUSICBRAINZ RESULT KEY: {result_key}")
        print(f"MUSICBRAINZ RESULTS COUNT: {len(results) if isinstance(results, list) else 'not a list'}")
        for item in results if isinstance(results, list) else []:
            if isinstance(item, dict):
                print(f"RECORDING RESULT: title={item.get('title')!r}, mbid={item.get('id')!r}, artists={self._recording_artist_names(item)!r}")
        if not isinstance(results, list) or not results:
            raise ValueError(f"No MusicBrainz {entity_type} found for query: {query}")
        wanted_name = self._normalize(query)
        exact_results = [
            item for item in results
            if isinstance(item, dict)
            and self._normalize(item.get("title") or item.get("name")) == wanted_name
        ]
        print(f"EXACT TITLE MATCHES: {len(exact_results)}")

        if normalized_type == "track" and context_artist:
            wanted_artist = self._normalize(context_artist)
            exact_results = [
                item for item in exact_results
                if wanted_artist in {self._normalize(name) for name in self._recording_artist_names(item)}
            ]
        print(f"EXACT TITLE + ARTIST MATCHES: {len(exact_results)}")
        for item in exact_results:
            print(f"EXACT MATCH DETAILS: mbid={item.get('id')!r}, title={item.get('title')!r}, length={item.get('length')!r}, disambiguation={item.get('disambiguation')!r}, releases={item.get('releases')!r}")
        # Never blindly choose results[0]: require a unique exact title match,
        # and for tracks with context, an exact artist-credit match as well.
        if len(exact_results) != 1:
            if len(exact_results) == 0:
               reason = "no exact title-and-artist match" if normalized_type == "track" and context_artist else "no exact-name match"
            else:
               reason = f"multiple exact matches ({len(exact_results)})"   
            print(f"MUSICBRAINZ MATCH FAILURE: reason={reason!r}, query={query!r}, context_artist={context_artist!r}, exact_matches={len(exact_results)}")
            raise ValueError(f"MusicBrainz returned {reason} for {entity_type}: {query}")
        print(f"MUSICBRAINZ MATCH SUCCESS: query={query!r}, context_artist={context_artist!r}, mbid={exact_results[0].get('id')!r}")
        selected = exact_results[0]
        mbid = selected.get("id")
        if not isinstance(mbid, str) or not mbid.strip():
            raise ValueError("MusicBrainz search result is missing a valid MBID")
        return self.catalog_entity_by_mbid(entity_type=entity_type, mbid=mbid)

    def _persist_spotify_mappings(
        self,
        entity: CatalogEntityV1,
        payload: dict[str, Any],
    ) -> None:
        mappings = self.client.extract_spotify_mappings(payload)
        # Persist only entity-specific Spotify pages, never search URLs or a
        # mapping for a different Spotify entity type.
        expected_path = {"track":"track", "artist":"artist", "album":"album"}.get(entity.entity_type.value)
        valid_mappings = []
        from urllib.parse import urlparse
        for mapping in mappings:
            url = mapping.get("external_url") or ""
            parsed = urlparse(url)
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.scheme != "https" or parsed.netloc.casefold() not in {"open.spotify.com", "www.open.spotify.com"}:
                continue
            if not expected_path or len(parts) != 2 or parts[0] != expected_path or not parts[1] or "?" in parts[1] or "#" in parts[1]:
                continue
            valid_mappings.append({**mapping,"external_id":parts[1],"external_url":f"https://open.spotify.com/{parts[0]}/{parts[1]}"})
        for mapping in valid_mappings:
            mapping_id = (
                f"{entity.entity_id}:"
                f"{mapping['provider']}:"
                f"{mapping['external_id']}"
            )
            self.repository.add_external_mapping(
                mapping_id=mapping_id,
                canonical_entity_id=entity.entity_id,
                provider=mapping["provider"],
                external_id=mapping["external_id"],
                external_url=mapping.get("external_url"),
            )

    def enrich(
        self,
        entity_type: str,
        query: str,
    ) -> CatalogEntityV1:
        return self.search_and_catalog_entity(entity_type=entity_type,query=query)

    def enrich_with_context(
        self,
        entity_type: str,
        query: str,
        context_artist: str,
    ) -> CatalogEntityV1:
        return self.search_and_catalog_entity(
            entity_type=entity_type,
            query=query,
            context_artist=context_artist,
        )        