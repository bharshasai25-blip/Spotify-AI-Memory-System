from unittest.mock import Mock
from backend_memory_pipeline.entity_resolution.entity_resolution import (
    CatalogEntityV1,
    EntityResolutionStatus,
    EntityType,
    RuleBasedEntityResolver,
)
from backend_memory_pipeline.memory_extraction.memory_extraction import (
    ExtractedEntityMention,
    ExtractedMemoryCandidate,
    MemoryType,
)

ARJIT_MBID = "ed3f4831-e3e0-4dc0-9381-f5649e9df221"

def make_candidate(candidate_id: str) -> ExtractedMemoryCandidate:
    return ExtractedMemoryCandidate(
        candidate_id=candidate_id,
        subject_id="user-001",
        subject_scope="user-001",
        source_event_id="event-001",
        source_event_ids=["event-001"],
        source_event_type="ai_interaction",
        memory_type=MemoryType.CANDIDATE_PREFERENCE,
        decision="memory_candidate",
        normalized_fact="user likes Arijit Singh",
        confidence=0.90,
        reason="Behavioral evidence indicates a candidate preference.",
        evidence_count=1,
        explicit_evidence_count=0,
        behavioral_evidence_count=1,
        entities=[
            ExtractedEntityMention(
                mention="Arijit Singh",
                entity_type="artist",
            )
        ],
    )

def make_entity() -> CatalogEntityV1:
    return CatalogEntityV1(
        entity_id=f"musicbrainz:artist:{ARJIT_MBID}",
        entity_type=EntityType.ARTIST,
        canonical_name="Arijit Singh",
        aliases=["Arjit Singh"],
        normalized_name="arijit singh",
        owner_subject_id=None,
        metadata={"musicbrainz_id": ARJIT_MBID},
    )

def test_unknown_artist_is_enriched_and_then_resolved():
    catalog = Mock()
    enrichment_service = Mock()
    entity = make_entity()
    catalog.search.side_effect = [
        [],
        [entity],
    ]
    enrichment_service.enrich.return_value = entity
    resolver = RuleBasedEntityResolver(
        catalog=catalog,
        enrichment_service=enrichment_service,
    )
    candidate = make_candidate("candidate-musicbrainz-001")
    result = resolver.resolve_candidate(candidate)
    assert result.resolution_status == EntityResolutionStatus.RESOLVED
    assert len(result.resolved_entities) == 1
    resolved = result.resolved_entities[0]
    assert resolved.canonical_id == f"musicbrainz:artist:{ARJIT_MBID}"
    assert resolved.canonical_name == "Arijit Singh"
    assert resolved.resolution_status == EntityResolutionStatus.RESOLVED
    enrichment_service.enrich.assert_called_once_with(
        entity_type="artist",
        query="Arijit Singh",
    )
    assert catalog.search.call_count == 2

def test_existing_catalog_match_is_offered_for_confirmation_before_memory_write():
    class SearchOnlyEnrichment:
        def search_candidates(self, entity_type, query, context_artist=None): return []
        def enrich(self, entity_type, query): raise AssertionError("Discovery must not catalog before confirmation")
    catalog = Mock()
    entity = make_entity()
    catalog.search.return_value = [entity]
    resolver = RuleBasedEntityResolver(catalog=catalog,enrichment_service=SearchOnlyEnrichment())
    candidate = make_candidate("candidate-musicbrainz-002")
    result = resolver.resolve_candidate(candidate)
    assert result.resolution_status == EntityResolutionStatus.AMBIGUOUS
    resolved=result.resolved_entities[0]
    assert resolved.candidate_options[0]["mbid"] == ARJIT_MBID
    assert resolved.candidate_options[0]["already_cataloged"] is True
    catalog.search.assert_called_once()

def test_unknown_entity_remains_unresolved_when_enrichment_is_not_configured():
    catalog = Mock()
    catalog.search.return_value = []
    resolver = RuleBasedEntityResolver(
        catalog=catalog,
        enrichment_service=None,
    )
    candidate = make_candidate("candidate-musicbrainz-003")
    result = resolver.resolve_candidate(candidate)
    assert result.resolution_status == EntityResolutionStatus.UNRESOLVED
    assert result.resolved_entities[0].canonical_id is None
    catalog.search.assert_called_once()

def test_multiple_musicbrainz_candidates_are_returned_for_confirmation_without_cataloging():
    class SearchOnlyEnrichment:
        def __init__(self):
            self.catalog_entity_by_mbid_called = False
        def search_candidates(self, entity_type, query, context_artist=None):
            if entity_type != "track": return []
            return [
                {"mbid": "recording-1", "entity_type": "track", "name": "Galliyan", "artist_names": ["Ankit Tiwari"]},
                {"mbid": "recording-2", "entity_type": "track", "name": "Galliyan", "artist_names": ["Ankit Tiwari"]},
            ]
        def catalog_entity_by_mbid(self, entity_type, mbid):
            self.catalog_entity_by_mbid_called = True
            raise AssertionError("Ambiguous candidates must not be cataloged before confirmation")
    catalog = Mock()
    catalog.search.return_value = []
    enrichment = SearchOnlyEnrichment()
    resolver = RuleBasedEntityResolver(catalog=catalog, enrichment_service=enrichment)
    candidate = make_candidate("candidate-track-ambiguous").model_copy(update={
        "normalized_fact": "user likes Galliyan by Ankit Tiwari",
        "entities": [
            ExtractedEntityMention(mention="Galliyan", entity_type="track"),
            ExtractedEntityMention(mention="Ankit Tiwari", entity_type="artist"),
        ],
    })
    result = resolver.resolve_candidate(candidate)
    assert result.resolution_status == EntityResolutionStatus.AMBIGUOUS
    track_result = next(item for item in result.resolved_entities if item.entity_type == EntityType.TRACK)
    assert [item["mbid"] for item in track_result.candidate_options] == ["recording-1", "recording-2"]
    assert enrichment.catalog_entity_by_mbid_called is False
    assert catalog.search.call_count == 1    