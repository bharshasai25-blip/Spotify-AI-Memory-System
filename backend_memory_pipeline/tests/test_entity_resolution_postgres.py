import pytest
from backend_memory_pipeline.entity_resolution.entity_resolution import (
    CatalogEntityV1,
    EntityResolutionService,
    EntityResolutionStatus,
    EntityType,
    ExtractedEntityMention,
    ExtractedMemoryCandidate,
    RuleBasedEntityResolver)
from backend_memory_pipeline.persistence.postgres.entity_repository import (
    PostgreSQLCatalogRepository)
from backend_memory_pipeline.ingestion.ingestion import EventType
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryType


@pytest.fixture
def repository():
    return PostgreSQLCatalogRepository()


@pytest.fixture
def service(repository):
    resolver = RuleBasedEntityResolver(catalog=repository)
    return EntityResolutionService(resolver=resolver)


@pytest.fixture
def cleanup_entities(repository):
    entity_ids = []
    yield entity_ids
    for entity_id in entity_ids:
        repository.delete(entity_id)

def create_candidate(
    subject_id: str,
    mention: str,
    entity_type: str,
    candidate_id: str = "candidate-postgres-001",
):
    return ExtractedMemoryCandidate(
        candidate_id=candidate_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        source_event_id=f"event-{candidate_id}",
        source_event_ids=[f"event-{candidate_id}"],
        source_event_type=EventType.SAVE,
        memory_type=MemoryType.CANDIDATE_PREFERENCE,
        decision="memory_candidate",
        normalized_fact=f"User likes {mention}",
        confidence=0.80,
        reason="Behavioral preference candidate for PostgreSQL entity-resolution testing.",
        evidence_count=1,
        explicit_evidence_count=0,
        behavioral_evidence_count=1,
        entities=[
            ExtractedEntityMention(
                mention=mention,
                entity_type=entity_type,
            )
        ],
    )


def test_postgres_repository_stores_and_retrieves_entity(
    repository,
    cleanup_entities,
):
    entity = {
        "entity_id": "pg-artist-001",
        "entity_type": EntityType.ARTIST,
        "canonical_name": "Arijit Singh",
        "aliases": ["Arijit"],
    }

    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    catalog_entity = CatalogEntityV1(**entity)
    repository.put(catalog_entity)
    cleanup_entities.append(catalog_entity.entity_id)

    stored = repository.get(catalog_entity.entity_id)

    assert stored is not None
    assert stored.entity_id == "pg-artist-001"
    assert stored.entity_type == EntityType.ARTIST
    assert stored.canonical_name == "Arijit Singh"
    assert "Arijit" in stored.aliases


def test_postgres_canonical_name_resolution(
    repository,
    service,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-artist-002",
        entity_type=EntityType.ARTIST,
        canonical_name="PG Test Artist Canonical",
        aliases=[],
    )
    repository.put(entity)
    cleanup_entities.append(entity.entity_id)

    candidate = create_candidate(
        subject_id="user-001",
        mention="PG Test Artist Canonical",
        entity_type="artist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.RESOLVED
    assert len(result.resolved_entities) == 1

    resolved = result.resolved_entities[0]

    assert resolved.canonical_id == "pg-artist-002"
    assert resolved.canonical_name == "PG Test Artist Canonical"
    assert resolved.entity_type == EntityType.ARTIST
    assert resolved.resolution_status == EntityResolutionStatus.RESOLVED
    assert resolved.confidence == 0.99
    assert resolved.matched_field == "canonical_name"


def test_postgres_alias_resolution(
    repository,
    service,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-artist-003",
        entity_type=EntityType.ARTIST,
        canonical_name="Arijit Singh",
        aliases=["Arijit"],
    )
    repository.put(entity)
    cleanup_entities.append(entity.entity_id)

    candidate = create_candidate(
        subject_id="user-001",
        mention="Arijit",
        entity_type="artist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.RESOLVED

    resolved = result.resolved_entities[0]

    assert resolved.canonical_id == "pg-artist-003"
    assert resolved.canonical_name == "Arijit Singh"
    assert resolved.matched_field == "alias"
    assert resolved.matched_value == "Arijit"
    assert resolved.confidence == 0.95


def test_postgres_entity_type_filtering(
    repository,
    service,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    artist = CatalogEntityV1(
        entity_id="pg-artist-004",
        entity_type=EntityType.ARTIST,
        canonical_name="The Weeknd",
        aliases=[],
    )

    album = CatalogEntityV1(
        entity_id="pg-album-001",
        entity_type=EntityType.ALBUM,
        canonical_name="The Weeknd",
        aliases=[],
    )

    repository.put(artist)
    repository.put(album)

    cleanup_entities.extend([
        artist.entity_id,
        album.entity_id,
    ])

    candidate = create_candidate(
        subject_id="user-001",
        mention="The Weeknd",
        entity_type="artist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.RESOLVED

    resolved = result.resolved_entities[0]

    assert resolved.canonical_id == "pg-artist-004"
    assert resolved.entity_type == EntityType.ARTIST


def test_postgres_unknown_entity_is_unresolved(
    repository,
    service,
):
    candidate = create_candidate(
        subject_id="user-001",
        mention="This Artist Does Not Exist",
        entity_type="artist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.UNRESOLVED
    assert len(result.resolved_entities) == 1

    resolved = result.resolved_entities[0]

    assert resolved.resolution_status == EntityResolutionStatus.UNRESOLVED
    assert resolved.canonical_id is None
    assert resolved.canonical_name is None
    assert resolved.confidence == 0.0


def test_postgres_public_entity_can_be_resolved_by_different_subjects(
    repository,
    service,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-artist-005",
        entity_type=EntityType.ARTIST,
        canonical_name="A. R. Rahman",
        aliases=["AR Rahman"],
        owner_subject_id=None,
    )

    repository.put(entity)
    cleanup_entities.append(entity.entity_id)

    candidate = create_candidate(
        subject_id="user-999",
        mention="A. R. Rahman",
        entity_type="artist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.RESOLVED

    resolved = result.resolved_entities[0]

    assert resolved.canonical_id == "pg-artist-005"
    assert resolved.owner_subject_id is None


def test_postgres_subject_owned_entity_is_resolved_for_owner(
    repository,
    service,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-playlist-001",
        entity_type=EntityType.PLAYLIST,
        canonical_name="My Workout Playlist",
        aliases=["Workout"],
        owner_subject_id="user-001",
    )

    repository.put(entity)
    cleanup_entities.append(entity.entity_id)

    candidate = create_candidate(
        subject_id="user-001",
        mention="My Workout Playlist",
        entity_type="playlist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.RESOLVED

    resolved = result.resolved_entities[0]

    assert resolved.canonical_id == "pg-playlist-001"
    assert resolved.owner_subject_id == "user-001"


def test_postgres_subject_owned_entity_is_rejected_for_other_subject(
    repository,
    service,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-playlist-002",
        entity_type=EntityType.PLAYLIST,
        canonical_name="Private Playlist",
        aliases=["Private"],
        owner_subject_id="user-001",
    )

    repository.put(entity)
    cleanup_entities.append(entity.entity_id)

    candidate = create_candidate(
        subject_id="user-002",
        mention="Private Playlist",
        entity_type="playlist",
    )

    result = service.resolve(candidate)

    assert result.resolution_status == EntityResolutionStatus.REJECTED

    resolved = result.resolved_entities[0]

    assert resolved.resolution_status == EntityResolutionStatus.REJECTED
    assert resolved.canonical_id is None


def test_postgres_repository_persists_across_repository_instances():
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-persistence-001",
        entity_type=EntityType.ARTIST,
        canonical_name="Persistent Artist",
        aliases=["Persistent"],
    )

    repository_one = PostgreSQLCatalogRepository()
    repository_two = None

    try:
        repository_one.put(entity)

        repository_two = PostgreSQLCatalogRepository()

        stored = repository_two.get(entity.entity_id)

        assert stored is not None
        assert stored.entity_id == entity.entity_id
        assert stored.canonical_name == "Persistent Artist"
        assert "Persistent" in stored.aliases
    finally:
        repository_one.delete(entity.entity_id)
        if repository_two is not None:
            repository_two.delete(entity.entity_id)


def test_postgres_full_resolution_chain(
    repository,
    cleanup_entities,
):
    from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

    entity = CatalogEntityV1(
        entity_id="pg-full-chain-001",
        entity_type=EntityType.TRACK,
        canonical_name="Tum Hi Ho",
        aliases=["Tum Hi Ho Song"],
    )

    repository.put(entity)
    cleanup_entities.append(entity.entity_id)

    resolver = RuleBasedEntityResolver(
        catalog=repository
    )

    service = EntityResolutionService(
        resolver=resolver
    )

    candidate = create_candidate(
        subject_id="user-001",
        mention="Tum Hi Ho Song",
        entity_type="track",
        candidate_id="candidate-full-chain-001",
    )

    result = service.resolve(candidate)

    assert result.candidate_id == "candidate-full-chain-001"
    assert result.subject_id == "user-001"
    assert result.resolution_status == EntityResolutionStatus.RESOLVED

    resolved = result.resolved_entities[0]

    assert resolved.canonical_id == "pg-full-chain-001"
    assert resolved.canonical_name == "Tum Hi Ho"
    assert resolved.entity_type == EntityType.TRACK
    assert resolved.matched_field == "alias"
    assert resolved.confidence == 0.95