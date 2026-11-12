from unittest.mock import Mock
from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_catalog_service import MusicBrainzCatalogService

ARJIT_MBID = "ed3f4831-e3e0-4dc0-9381-f5649e9df221"
ARJIT_SPOTIFY_ID = "4YRxDV8wJFPHPTeXepOstw"
ARJIT_SPOTIFY_URL = f"https://open.spotify.com/artist/{ARJIT_SPOTIFY_ID}"

ARJIT_PAYLOAD = {
    "id": ARJIT_MBID,
    "type": "Person",
    "name": "Arijit Singh",
    "sort-name": "Singh, Arijit",
    "country": "IN",
    "aliases": [{"name": "Arjit Singh", "type": "Search hint"}],
    "relations": [
        {
            "type": "free streaming",
            "url": {"resource": ARJIT_SPOTIFY_URL},
        }
    ],
}

def test_catalog_entity_by_mbid_persists_entity_and_spotify_mapping():
    client = Mock()
    repository = Mock()
    client.get_entity_with_relationships.return_value = ARJIT_PAYLOAD
    client.extract_spotify_mappings.return_value = [
        {
            "provider": "spotify",
            "external_id": ARJIT_SPOTIFY_ID,
            "external_url": ARJIT_SPOTIFY_URL,
        }
    ]
    service = MusicBrainzCatalogService(
        client=client,
        repository=repository,
    )
    entity = service.catalog_entity_by_mbid(
        entity_type="artist",
        mbid=ARJIT_MBID,
    )
    assert isinstance(entity, CatalogEntityV1)
    assert entity.entity_id == f"musicbrainz:artist:{ARJIT_MBID}"
    assert entity.canonical_name == "Arijit Singh"
    client.get_entity_with_relationships.assert_called_once_with(
        entity_type="artist",
        mbid=ARJIT_MBID,
    )
    repository.put.assert_called_once_with(entity)
    repository.add_external_mapping.assert_called_once_with(
        mapping_id=f"musicbrainz:artist:{ARJIT_MBID}:spotify:{ARJIT_SPOTIFY_ID}",
        canonical_entity_id=entity.entity_id,
        provider="spotify",
        external_id=ARJIT_SPOTIFY_ID,
        external_url=ARJIT_SPOTIFY_URL,
    )

def test_search_and_catalog_entity_uses_musicbrainz_search_result():
    client = Mock()
    repository = Mock()
    client.search_entity.return_value = {
        "created": "2026-01-01T00:00:00.000Z",
        "count": 1,
        "offset": 0,
        "artists": [
            {
                "id": ARJIT_MBID,
                "name": "Arijit Singh",
                "score": 100,
            }
        ],
    }
    client.get_entity_with_relationships.return_value = ARJIT_PAYLOAD
    client.extract_spotify_mappings.return_value = []
    service = MusicBrainzCatalogService(
        client=client,
        repository=repository,
    )
    entity = service.search_and_catalog_entity(
        entity_type="artist",
        query="Arijit Singh",
        limit=3,
    )
    assert entity.entity_id == f"musicbrainz:artist:{ARJIT_MBID}"
    client.search_entity.assert_called_once_with(
        entity_type="artist",
        query="Arijit Singh",
        limit=3,
    )
    client.get_entity_with_relationships.assert_called_once_with(
        entity_type="artist",
        mbid=ARJIT_MBID,
    )

def test_search_and_catalog_entity_raises_when_no_results():
    client = Mock()
    repository = Mock()
    client.search_entity.return_value = {
        "count": 0,
        "offset": 0,
        "artists": [],
    }
    service = MusicBrainzCatalogService(
        client=client,
        repository=repository,
    )
    try:
        service.search_and_catalog_entity(
            entity_type="artist",
            query="DefinitelyNotARealArtist",
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "No MusicBrainz artist found" in str(exc)

def test_search_candidates_returns_exact_recordings_without_persisting():
    client = Mock()
    repository = Mock()
    client.search_entity.return_value = {
        "recordings": [
            {"id": "recording-1", "title": "Galliyan", "score": 100, "artist-credit": [{"name": "Ankit Tiwari", "artist": {"name": "Ankit Tiwari"}}], "length": 250000, "releases": [{"title": "Ek Villain"}]},
            {"id": "recording-2", "title": "Galliyan", "score": 98, "artist-credit": [{"name": "Ankit Tiwari", "artist": {"name": "Ankit Tiwari"}}], "length": 255000, "releases": [{"title": "Galliyan (Single)"}]},
            {"id": "recording-3", "title": "Galliyan Returns", "score": 90, "artist-credit": [{"name": "Ankit Tiwari", "artist": {"name": "Ankit Tiwari"}}]},
        ]
    }
    service = MusicBrainzCatalogService(client=client, repository=repository)
    candidates = service.search_candidates(entity_type="track", query="Galliyan", context_artist="Ankit Tiwari")
    assert [item["mbid"] for item in candidates] == ["recording-1", "recording-2"]
    assert all(item["name"] == "Galliyan" for item in candidates)
    client.get_entity_with_relationships.assert_not_called()
    repository.put.assert_not_called()
    repository.add_external_mapping.assert_not_called()        
def test_catalog_does_not_persist_spotify_search_url_as_track_mapping():
    client=Mock()
    repository=Mock()
    client.get_entity_with_relationships.return_value={"id":"recording-search-fallback","title":"Galliyan","artist-credit":[]}
    client.extract_spotify_mappings.return_value=[{"provider":"spotify","external_id":"Galliyan","external_url":"https://open.spotify.com/search/Galliyan%20Ankit%20Tiwari"}]
    service=MusicBrainzCatalogService(client=client,repository=repository)
    entity=service.catalog_entity_by_mbid(entity_type="track",mbid="recording-search-fallback")
    assert entity.entity_id=="musicbrainz:track:recording-search-fallback"
    repository.put.assert_called_once_with(entity)
    repository.add_external_mapping.assert_not_called()

def test_search_candidates_can_return_broad_catalog_search_results():
    client=Mock()
    repository=Mock()
    client.search_entity.return_value={"recordings":[
        {"id":"recording-1","title":"Galliyan","artist-credit":[{"name":"Ankit Tiwari"}]},
        {"id":"recording-2","title":"Galliyan Live","artist-credit":[{"name":"Ankit Tiwari"}]},
    ]}
    service=MusicBrainzCatalogService(client=client,repository=repository)
    candidates=service.search_candidates(entity_type="track",query="Galliyan",exact_only=False)
    assert [item["mbid"] for item in candidates]==["recording-1","recording-2"]
    assert all(item["spotify_url_type"]=="search" for item in candidates)
    repository.put.assert_not_called()