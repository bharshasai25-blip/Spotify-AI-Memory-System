import pytest
from backend_memory_pipeline.entity_resolution.entity_resolution import (
    CatalogEntityV1,
    EntityResolutionError,
    EntityResolutionErrorCode,
    EntityResolutionService,
    EntityResolutionStatus,
    EntityType,
    InMemoryCatalogRepository,
    ResolvedEntityV1,
    RuleBasedEntityResolver,
    normalize_entity_text
)
from backend_memory_pipeline.memory_extraction.memory_extraction import (
    ExtractedEntityMention,
    ExtractedMemoryCandidate,
    ExtractionDecision,
    MemoryType,
    PolicyClass,
    TemporalScope
)
def make_catalog():
    return [
        CatalogEntityV1(
            entity_id="ARTIST_001",
            entity_type=EntityType.ARTIST,
            canonical_name="Taylor Swift",
            aliases=["Taylor", "T. Swift"]
        ),
        CatalogEntityV1(
            entity_id="TRACK_001",
            entity_type=EntityType.TRACK,
            canonical_name="Anti-Hero",
            aliases=["Anti Hero"]
        ),
        CatalogEntityV1(
            entity_id="PLAYLIST_001",
            entity_type=EntityType.PLAYLIST,
            canonical_name="Chill Vibes",
            aliases=["Chill Vibes Playlist"],
            owner_subject_id="TEST_USER_001"
        ),
        CatalogEntityV1(
            entity_id="PLAYLIST_002",
            entity_type=EntityType.PLAYLIST,
            canonical_name="Chill Vibes",
            aliases=[],
            owner_subject_id="TEST_USER_999"
        ),
        CatalogEntityV1(
            entity_id="SHOW_001",
            entity_type=EntityType.SHOW,
            canonical_name="Tech Talks",
            aliases=["Tech Talk"]
        )
    ]
def make_candidate(
    candidate_id="CANDIDATE_001",
    subject_id="TEST_USER_001",
    mentions=None
):
    return ExtractedMemoryCandidate(
        candidate_id=candidate_id,
        subject_id=subject_id,
        subject_scope=subject_id,
        source_event_id="SOURCE_001",
        source_event_ids=["SOURCE_001"],
        source_session_ids=["SESSION_001"],
        source_event_type="ai_interaction",
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        decision=ExtractionDecision.MEMORY_CANDIDATE,
        normalized_fact="User prefers this content.",
        evidence_texts=["I prefer this content."],
        entities=mentions or [],
        confidence=0.98,
        relevance_score=None,
        temporal_scope=TemporalScope.CURRENT,
        policy_class=PolicyClass.STANDARD,
        policy_flags=[],
        reason="Explicit preference evidence.",
        evidence_count=1,
        explicit_evidence_count=1,
        behavioral_evidence_count=0
    )
def test_normalize_entity_text():
    assert normalize_entity_text("  Taylor   Swift  ")=="taylor swift"
def test_exact_canonical_match_is_resolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Taylor Swift",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    entity=result.resolved_entities[0]
    assert entity.canonical_id=="ARTIST_001"
    assert entity.canonical_name=="Taylor Swift"
    assert entity.confidence==0.99
    assert entity.matched_field=="canonical_name"
def test_case_and_whitespace_variation_is_resolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="  tAYLOR   swIFT ",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    assert result.resolved_entities[0].canonical_id=="ARTIST_001"
def test_alias_match_is_resolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="T. Swift",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    entity=result.resolved_entities[0]
    assert entity.resolution_status==EntityResolutionStatus.RESOLVED
    assert entity.canonical_id=="ARTIST_001"
    assert entity.confidence==0.95
    assert entity.matched_field=="alias"
def test_track_alias_is_resolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Anti Hero",
        entity_type="track"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    entity=result.resolved_entities[0]
    assert entity.canonical_id=="TRACK_001"
    assert entity.entity_type==EntityType.TRACK
    assert entity.resolution_status==EntityResolutionStatus.RESOLVED
def test_unknown_entity_is_unresolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Unknown Artist",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.UNRESOLVED
    assert result.unresolved_mentions==["Unknown Artist"]
    entity=result.resolved_entities[0]
    assert entity.canonical_id is None
    assert entity.confidence==0.0
def test_ambiguous_entity_is_rejected_as_ambiguous():
    repository=InMemoryCatalogRepository([
        CatalogEntityV1(
            entity_id="PLAYLIST_001",
            entity_type=EntityType.PLAYLIST,
            canonical_name="Focus",
            aliases=[]
        ),
        CatalogEntityV1(
            entity_id="PLAYLIST_002",
            entity_type=EntityType.PLAYLIST,
            canonical_name="Focus",
            aliases=[]
        )
    ])
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Focus",
        entity_type="playlist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.AMBIGUOUS
    assert result.ambiguous_mentions==["Focus"]
    entity=result.resolved_entities[0]
    assert entity.canonical_id is None
    assert entity.confidence==0.75
def test_subject_owned_playlist_for_current_user_is_resolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Chill Vibes",
        entity_type="playlist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    entity=result.resolved_entities[0]
    assert entity.canonical_id=="PLAYLIST_001"
    assert entity.owner_subject_id=="TEST_USER_001"
def test_subject_owned_playlist_from_another_user_is_rejected():
    repository=InMemoryCatalogRepository([
        CatalogEntityV1(
            entity_id="PLAYLIST_999",
            entity_type=EntityType.PLAYLIST,
            canonical_name="Private Mix",
            owner_subject_id="TEST_USER_999"
        )
    ])
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Private Mix",
        entity_type="playlist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.REJECTED
    entity=result.resolved_entities[0]
    assert entity.canonical_id is None
    assert "outside" in entity.reason
def test_public_entity_can_be_resolved_for_any_subject():
    repository=InMemoryCatalogRepository([
        CatalogEntityV1(
            entity_id="ARTIST_100",
            entity_type=EntityType.ARTIST,
            canonical_name="Public Artist"
        )
    ])
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Public Artist",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(
            subject_id="TEST_USER_999",
            mentions=[mention]
        )
    )
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    assert result.resolved_entities[0].canonical_id=="ARTIST_100"
def test_unknown_entity_type_becomes_unknown():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Taylor Swift",
        entity_type="unknown_custom_type"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    entity=result.resolved_entities[0]
    assert entity.entity_type==EntityType.UNKNOWN
def test_entity_type_filter_prevents_wrong_type_match():
    repository=InMemoryCatalogRepository([
        CatalogEntityV1(
            entity_id="ARTIST_001",
            entity_type=EntityType.ARTIST,
            canonical_name="Focus"
        ),
        CatalogEntityV1(
            entity_id="PLAYLIST_001",
            entity_type=EntityType.PLAYLIST,
            canonical_name="Focus"
        )
    ])
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Focus",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    assert result.resolved_entities[0].canonical_id=="ARTIST_001"
def test_multiple_entities_are_resolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mentions=[
        ExtractedEntityMention(
            mention="Taylor Swift",
            entity_type="artist"
        ),
        ExtractedEntityMention(
            mention="Anti-Hero",
            entity_type="track"
        )
    ]
    result=resolver.resolve_candidate(
        make_candidate(mentions=mentions)
    )
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    assert len(result.resolved_entities)==2
    assert {
        entity.canonical_id
        for entity in result.resolved_entities
    }=={"ARTIST_001","TRACK_001"}
def test_mixed_resolved_and_unresolved_entities_are_unresolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mentions=[
        ExtractedEntityMention(
            mention="Taylor Swift",
            entity_type="artist"
        ),
        ExtractedEntityMention(
            mention="Unknown Artist",
            entity_type="artist"
        )
    ]
    result=resolver.resolve_candidate(
        make_candidate(mentions=mentions)
    )
    assert result.resolution_status==EntityResolutionStatus.UNRESOLVED
    assert result.unresolved_mentions==["Unknown Artist"]
def test_mixed_resolved_and_ambiguous_entities_are_ambiguous():
    repository=InMemoryCatalogRepository([
        CatalogEntityV1(
            entity_id="ARTIST_001",
            entity_type=EntityType.ARTIST,
            canonical_name="Taylor Swift"
        ),
        CatalogEntityV1(
            entity_id="ARTIST_002",
            entity_type=EntityType.ARTIST,
            canonical_name="Focus"
        ),
        CatalogEntityV1(
            entity_id="ARTIST_003",
            entity_type=EntityType.ARTIST,
            canonical_name="Focus"
        )
    ])
    resolver=RuleBasedEntityResolver(repository)
    mentions=[
        ExtractedEntityMention(
            mention="Taylor Swift",
            entity_type="artist"
        ),
        ExtractedEntityMention(
            mention="Focus",
            entity_type="artist"
        )
    ]
    result=resolver.resolve_candidate(
        make_candidate(mentions=mentions)
    )
    assert result.resolution_status==EntityResolutionStatus.AMBIGUOUS
    assert result.ambiguous_mentions==["Focus"]
def test_candidate_without_entities_returns_unresolved():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    candidate=make_candidate(mentions=[])
    result=resolver.resolve_candidate(candidate)
    assert result.resolution_status==EntityResolutionStatus.UNRESOLVED
    assert result.resolved_entities==[]
    assert result.unresolved_mentions==[]
def test_invalid_candidate_type_is_rejected():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    with pytest.raises(EntityResolutionError) as exc:
        resolver.resolve_candidate({"candidate_id":"bad"})
    assert exc.value.code==EntityResolutionErrorCode.INVALID_CANDIDATE
def test_repository_duplicate_entity_id_is_rejected():
    with pytest.raises(EntityResolutionError) as exc:
        InMemoryCatalogRepository([
            CatalogEntityV1(
                entity_id="DUP_001",
                entity_type=EntityType.ARTIST,
                canonical_name="Artist A"
            ),
            CatalogEntityV1(
                entity_id="DUP_001",
                entity_type=EntityType.ARTIST,
                canonical_name="Artist B"
            )
        ])
    assert exc.value.code==EntityResolutionErrorCode.INVALID_CATALOG_RECORD
def test_service_requires_configured_resolver():
    service=EntityResolutionService()
    candidate=make_candidate(
        mentions=[
            ExtractedEntityMention(
                mention="Taylor Swift",
                entity_type="artist"
            )
        ]
    )
    with pytest.raises(EntityResolutionError) as exc:
        service.resolve(candidate)
    assert exc.value.code==EntityResolutionErrorCode.INVALID_CANDIDATE
def test_service_resolves_candidate():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    service=EntityResolutionService(resolver)
    candidate=make_candidate(
        mentions=[
            ExtractedEntityMention(
                mention="Taylor Swift",
                entity_type="artist"
            )
        ]
    )
    result=service.resolve(candidate)
    assert result.resolution_status==EntityResolutionStatus.RESOLVED
    assert result.resolved_entities[0].canonical_id=="ARTIST_001"
def test_resolution_result_preserves_candidate_and_subject():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    candidate=make_candidate(
        candidate_id="CANDIDATE_999",
        subject_id="TEST_USER_001",
        mentions=[
            ExtractedEntityMention(
                mention="Taylor Swift",
                entity_type="artist"
            )
        ]
    )
    result=resolver.resolve_candidate(candidate)
    assert result.candidate_id=="CANDIDATE_999"
    assert result.subject_id=="TEST_USER_001"
def test_resolved_entity_has_reason_and_match_metadata():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    mention=ExtractedEntityMention(
        mention="Taylor Swift",
        entity_type="artist"
    )
    result=resolver.resolve_candidate(
        make_candidate(mentions=[mention])
    )
    entity=result.resolved_entities[0]
    assert entity.reason
    assert entity.matched_field=="canonical_name"
    assert entity.matched_value=="Taylor Swift"
def test_resolution_is_deterministic():
    repository=InMemoryCatalogRepository(make_catalog())
    resolver=RuleBasedEntityResolver(repository)
    candidate=make_candidate(
        mentions=[
            ExtractedEntityMention(
                mention="Taylor Swift",
                entity_type="artist"
            )
        ]
    )
    result_one=resolver.resolve_candidate(candidate)
    result_two=resolver.resolve_candidate(candidate)
    assert result_one.model_dump()==result_two.model_dump()