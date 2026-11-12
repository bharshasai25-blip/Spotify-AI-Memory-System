from backend_memory_pipeline.integration.musicbrainz.musicbrainz_client import MusicBrainzClient
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_mapper import MusicBrainzMapper
from backend_memory_pipeline.persistence.postgres.entity_repository import PostgreSQLCatalogRepository

ARJIT_MBID = "ed3f4831-e3e0-4dc0-9381-f5649e9df221"
ARJIT_SPOTIFY_ID = "4YRxDV8wJFPHPTeXepOstw"
ARJIT_SPOTIFY_URL = f"https://open.spotify.com/artist/{ARJIT_SPOTIFY_ID}"

ARJIT_PAYLOAD = {
    "id": ARJIT_MBID,
    "type": "Person",
    "name": "Arijit Singh",
    "sort-name": "Singh, Arijit",
    "country": "IN",
    "aliases": [
        {
            "name": "Arjit Singh",
            "type": "Search hint",
        }
    ],
    "relations": [
        {
            "type": "free streaming",
            "url": {
                "resource": ARJIT_SPOTIFY_URL,
            },
        }
    ],
}


def test_musicbrainz_payload_maps_to_catalog_entity():
    entity = MusicBrainzMapper.to_catalog_entity(
        ARJIT_PAYLOAD,
        "artist",
    )

    assert entity.entity_id == f"musicbrainz:artist:{ARJIT_MBID}"
    assert entity.canonical_name == "Arijit Singh"
    assert entity.aliases == ["Arjit Singh"]
    assert entity.normalized_name == "arijit singh"
    assert entity.owner_subject_id is None
    assert entity.metadata["musicbrainz_id"] == ARJIT_MBID


def test_spotify_url_is_extracted_from_musicbrainz_relationship():
    urls = MusicBrainzClient.extract_spotify_urls(ARJIT_PAYLOAD)

    assert urls == [ARJIT_SPOTIFY_URL]


def test_spotify_mapping_is_extracted_from_musicbrainz_relationship():
    mappings = MusicBrainzClient.extract_spotify_mappings(ARJIT_PAYLOAD)

    assert mappings == [
        {
            "provider": "spotify",
            "external_id": ARJIT_SPOTIFY_ID,
            "external_url": ARJIT_SPOTIFY_URL,
        }
    ]


def test_musicbrainz_entity_and_spotify_mapping_persist_to_postgres():
    entity = MusicBrainzMapper.to_catalog_entity(
        ARJIT_PAYLOAD,
        "artist",
    )
    repository = PostgreSQLCatalogRepository()

    repository.put(entity)

    mapping = MusicBrainzClient.extract_spotify_mappings(
        ARJIT_PAYLOAD
    )[0]

    mapping_id = (
        f"{entity.entity_id}:"
        f"{mapping['provider']}:"
        f"{mapping['external_id']}"
    )

    repository.add_external_mapping(
        mapping_id=mapping_id,
        canonical_entity_id=entity.entity_id,
        provider=mapping["provider"],
        external_id=mapping["external_id"],
        external_url=mapping["external_url"],
    )

    stored_entity = repository.get(entity.entity_id)
    stored_mappings = repository.list_external_mappings(
        entity.entity_id
    )

    assert stored_entity is not None
    assert stored_entity.entity_id == entity.entity_id
    assert stored_entity.canonical_name == "Arijit Singh"

    assert len(stored_mappings) >= 1

    spotify_mapping = next(
        item
        for item in stored_mappings
        if item["provider"] == "spotify"
    )

    assert spotify_mapping["external_id"] == ARJIT_SPOTIFY_ID
    assert spotify_mapping["external_url"] == ARJIT_SPOTIFY_URL