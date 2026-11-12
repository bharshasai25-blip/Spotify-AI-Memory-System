

from backend_memory_pipeline.integration.musicbrainz.musicbrainz_client import MusicBrainzClient
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_catalog_service import MusicBrainzCatalogService
from backend_memory_pipeline.persistence.postgres.entity_repository import PostgreSQLCatalogRepository

mbid = "cd46de8c-e1bd-4cd4-8e07-20deeabc0b52"

client = MusicBrainzClient(
    user_agent="SpotifyAIMemorySystem/1.0 (contact@example.com)"
)
repository = PostgreSQLCatalogRepository()
service = MusicBrainzCatalogService(client=client, repository=repository)

print("Fetching recording from MusicBrainz...")
entity = service.catalog_entity_by_mbid(entity_type="track", mbid=mbid)

print("\nRefresh completed.")
print("Canonical ID:", entity.entity_id)
print("Track name:", entity.canonical_name)
print("Artist credit:", entity.metadata.get("artist_credit"))

saved_entity = repository.get(entity.entity_id)
print("\nArtist credit stored in PostgreSQL:")
print(saved_entity.metadata.get("artist_credit") if saved_entity else "Entity not found")
