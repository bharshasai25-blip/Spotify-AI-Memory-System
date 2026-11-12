from __future__ import annotations
from typing import Any
from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

class MusicBrainzMapper:
    @staticmethod
    def to_catalog_entity(
        payload: dict[str, Any],
        entity_type: str,
    ) -> CatalogEntityV1:
        mbid = payload.get("id")
        name = payload.get("name") or payload.get("title")

        if not isinstance(mbid, str) or not mbid.strip():
            raise ValueError("MusicBrainz payload is missing a valid MBID")

        if not isinstance(name, str) or not name.strip():
            raise ValueError("MusicBrainz payload is missing a valid entity name")

        aliases: list[str] = []
        for alias in payload.get("aliases", []):
            if not isinstance(alias, dict):
                continue

            alias_name = alias.get("name")
            if isinstance(alias_name, str) and alias_name.strip():
                aliases.append(alias_name.strip())

        canonical_entity_id = f"musicbrainz:{entity_type.lower()}:{mbid.strip()}"
        artist_names=[]
        artist_credit=payload.get("artist-credit", [])
        if isinstance(artist_credit,list):
            for part in artist_credit:
                if not isinstance(part,dict): continue
                artist_name=part.get("name")
                if not isinstance(artist_name,str) and isinstance(part.get("artist"),dict): artist_name=part["artist"].get("name")
                if isinstance(artist_name,str) and artist_name.strip(): artist_names.append(artist_name.strip())
        releases=payload.get("releases", [])
        release_names=[release.get("title").strip() for release in releases if isinstance(release,dict) and isinstance(release.get("title"),str) and release.get("title").strip()] if isinstance(releases,list) else []

        metadata = {
            "musicbrainz_id": mbid.strip(),
            "musicbrainz_type": payload.get("type"),
            "country": payload.get("country"),
            "sort_name": payload.get("sort-name"),
             # Keep recording artist credit so same-title recordings can be
            # disambiguated during later entity resolution.
            "artist_credit": artist_credit,
            "artist_names": list(dict.fromkeys(artist_names)),
            "release_names": list(dict.fromkeys(release_names))[:10],
            "disambiguation": payload.get("disambiguation", ""),
            "length_ms": payload.get("length"),
        }

        return CatalogEntityV1(
            entity_id=canonical_entity_id  ,
            entity_type=entity_type.lower(),
            canonical_name=name.strip(),
            aliases=list(dict.fromkeys(aliases)),
            normalized_name=name.strip().casefold(),
            owner_subject_id=None,
            metadata=metadata,
        )