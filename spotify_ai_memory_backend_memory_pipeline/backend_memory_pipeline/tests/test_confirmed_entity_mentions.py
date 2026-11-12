from datetime import datetime, timezone
from backend_memory_pipeline.ingestion.ingestion import ConsentState, EventType, InteractionEventV1
from backend_memory_pipeline.memory_extraction.memory_extraction import RuleBasedMemoryExtractor

def _event():
    return InteractionEventV1(
        event_id="event-selection-test",
        source_event_id="source-selection-test",
        subject_id="user-test",
        subject_scope="user-test",
        session_id="session-test",
        event_type=EventType.EXPLICIT_PREFERENCE,
        source="api",
        surface="web",
        locale="en-US",
        timestamp=datetime.now(timezone.utc),
        consent_state=ConsentState.OPTED_IN,
        idempotency_key="selection-test-key",
        correlation_id="selection-test-correlation",
        text="I like Galliyan by Ankit Tiwari",
        entity={"entity_type":"track","name":"Galliyan","canonical_name":"Galliyan","canonical_id":"musicbrainz:track:97248513-385a-4147-952f-13f32eb1efef"},
        context_entities={"artists":[{"entity_type":"artist","name":"Ankit Tiwari"}]},
        metadata={"source":"musicbrainz_selection_confirmation"},
    )

def test_confirmed_entity_mention_preserves_canonical_id_and_type():
    event = _event()
    mentions = RuleBasedMemoryExtractor._extract_entity_mentions(event, [event])
    track_mentions = [item for item in mentions if item.mention == "Galliyan"]
    assert len(track_mentions) == 1
    assert track_mentions[0].entity_type == "track"
    assert track_mentions[0].canonical_id == "musicbrainz:track:97248513-385a-4147-952f-13f32eb1efef"

def test_entity_dictionary_fields_are_not_mistaken_for_separate_mentions():
    event = _event()
    mentions = RuleBasedMemoryExtractor._extract_entity_mentions(event, [event])
    names = {item.mention for item in mentions}
    assert "track" not in names
    assert "musicbrainz:track:97248513-385a-4147-952f-13f32eb1efef" not in names
    assert "Galliyan" in names
    assert "Ankit Tiwari" in names
