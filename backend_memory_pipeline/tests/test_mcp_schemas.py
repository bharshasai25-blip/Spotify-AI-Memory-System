from datetime import datetime,timezone
import pytest
from pydantic import ValidationError
from backend_memory_pipeline.mcp.schemas import (
    AddExplicitPreferenceInput,
    AddExplicitPreferenceOutput,
    CorrectMemoryInput,
    CorrectMemoryOutput,
    DeleteMemoryInput,
    DeleteMemoryOutput,
    ExplainMemoryUseInput,
    ExplainMemoryUseOutput,
    SearchMemoryInput,
    SearchMemoryOutput,
)
def aware_datetime()->datetime:
    return datetime(2026,9,2,15,0,tzinfo=timezone.utc)
class TestSearchMemoryInput:
    def test_valid_input(self):
        request=SearchMemoryInput(
            query="What music do I like?",
            surface="chat",
            locale="en-IN",
            requested_at=aware_datetime()
        )
        assert request.query=="What music do I like?"
        assert request.surface=="chat"
        assert request.locale=="en-IN"
        assert request.requested_at.tzinfo is not None
        assert request.max_items==5
        assert request.max_characters==10000
    def test_rejects_empty_query(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="",surface="chat",locale="en-IN",requested_at=aware_datetime())
    def test_rejects_whitespace_query(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="   ",surface="chat",locale="en-IN",requested_at=aware_datetime())
    def test_rejects_empty_surface(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="What music do I like?",surface="",locale="en-IN",requested_at=aware_datetime())
    def test_rejects_empty_locale(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="What music do I like?",surface="chat",locale="",requested_at=aware_datetime())
    def test_rejects_naive_requested_at(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="What music do I like?",surface="chat",locale="en-IN",requested_at=datetime(2026,9,2,15,0))
    def test_accepts_custom_limits(self):
        request=SearchMemoryInput(query="jazz",surface="chat",locale="en-IN",requested_at=aware_datetime(),max_items=10,max_characters=20000)
        assert request.max_items==10
        assert request.max_characters==20000
    def test_rejects_invalid_max_items(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="jazz",surface="chat",locale="en-IN",requested_at=aware_datetime(),max_items=0)
    def test_rejects_excessive_max_items(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="jazz",surface="chat",locale="en-IN",requested_at=aware_datetime(),max_items=21)
    def test_rejects_excessive_max_characters(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="jazz",surface="chat",locale="en-IN",requested_at=aware_datetime(),max_characters=50001)
    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            SearchMemoryInput(query="jazz",surface="chat",locale="en-IN",requested_at=aware_datetime(),subject_id="SHOULD_NOT_BE_ACCEPTED")
class TestSearchMemoryOutput:
    def test_valid_output(self):
        result=SearchMemoryOutput(
            decision="ALLOW",
            context_items=[{"memory_id":"MEMORY_001","fact":"User prefers jazz."}],
            memory_grounded=True,
            correlation_id="CORR_001"
        )
        assert result.schema_version=="1.0"
        assert result.decision=="ALLOW"
        assert result.memory_grounded is True
        assert len(result.context_items)==1
class TestAddExplicitPreferenceInput:
    def test_valid_input(self):
        request=AddExplicitPreferenceInput(
            preference="I prefer instrumental jazz.",
            session_id="SESSION_001",
            surface="chat",
            locale="en-IN",
            effective_at=aware_datetime()
        )
        assert request.preference=="I prefer instrumental jazz."
        assert request.session_id=="SESSION_001"
        assert request.metadata=={}
        assert request.entity is None
        assert request.context_entities is None
    def test_accepts_entity_data(self):
        request=AddExplicitPreferenceInput(
            preference="I like Radiohead.",
            session_id="SESSION_001",
            surface="chat",
            locale="en-IN",
            effective_at=aware_datetime(),
            entity={"entity_type":"artist","entity_id":"ARTIST_001"}
        )
        assert request.entity["entity_type"]=="artist"
    def test_rejects_empty_preference(self):
        with pytest.raises(ValidationError):
            AddExplicitPreferenceInput(preference="",session_id="SESSION_001",surface="chat",locale="en-IN",effective_at=aware_datetime())
    def test_rejects_whitespace_preference(self):
        with pytest.raises(ValidationError):
            AddExplicitPreferenceInput(preference="   ",session_id="SESSION_001",surface="chat",locale="en-IN",effective_at=aware_datetime())
    def test_rejects_empty_session_id(self):
        with pytest.raises(ValidationError):
            AddExplicitPreferenceInput(preference="I like jazz.",session_id="",surface="chat",locale="en-IN",effective_at=aware_datetime())
    def test_rejects_naive_effective_at(self):
        with pytest.raises(ValidationError):
            AddExplicitPreferenceInput(preference="I like jazz.",session_id="SESSION_001",surface="chat",locale="en-IN",effective_at=datetime(2026,9,2,15,0))
    def test_rejects_extra_subject_fields(self):
        with pytest.raises(ValidationError):
            AddExplicitPreferenceInput(preference="I like jazz.",session_id="SESSION_001",surface="chat",locale="en-IN",effective_at=aware_datetime(),subject_id="SHOULD_NOT_BE_ACCEPTED")
class TestAddExplicitPreferenceOutput:
    def test_valid_output(self):
        result=AddExplicitPreferenceOutput(accepted=True,memory_ids=["MEMORY_001"],correlation_id="CORR_001")
        assert result.schema_version=="1.0"
        assert result.accepted is True
        assert result.memory_ids==["MEMORY_001"]
class TestCorrectMemoryInput:
    def test_valid_input(self):
        request=CorrectMemoryInput(
            memory_id="MEMORY_001",
            corrected_statement="I prefer classical music.",
            session_id="SESSION_001",
            reason="The previous preference was incorrect.",
            surface="chat",
            locale="en-IN",
            effective_at=aware_datetime()
        )
        assert request.memory_id=="MEMORY_001"
        assert request.corrected_statement=="I prefer classical music."
    def test_rejects_empty_memory_id(self):
        with pytest.raises(ValidationError):
            CorrectMemoryInput(memory_id="",corrected_statement="I prefer classical music.",session_id="SESSION_001",reason="Correction.",surface="chat",locale="en-IN",effective_at=aware_datetime())
    def test_rejects_empty_corrected_statement(self):
        with pytest.raises(ValidationError):
            CorrectMemoryInput(memory_id="MEMORY_001",corrected_statement="",session_id="SESSION_001",reason="Correction.",surface="chat",locale="en-IN",effective_at=aware_datetime())
    def test_rejects_empty_reason(self):
        with pytest.raises(ValidationError):
            CorrectMemoryInput(memory_id="MEMORY_001",corrected_statement="I prefer classical music.",session_id="SESSION_001",reason="",surface="chat",locale="en-IN",effective_at=aware_datetime())
    def test_rejects_naive_effective_at(self):
        with pytest.raises(ValidationError):
            CorrectMemoryInput(memory_id="MEMORY_001",corrected_statement="I prefer classical music.",session_id="SESSION_001",reason="Correction.",surface="chat",locale="en-IN",effective_at=datetime(2026,9,2,15,0))
    def test_rejects_extra_subject_id(self):
        with pytest.raises(ValidationError):
            CorrectMemoryInput(memory_id="MEMORY_001",corrected_statement="I prefer classical music.",session_id="SESSION_001",reason="Correction.",surface="chat",locale="en-IN",effective_at=aware_datetime(),subject_id="SHOULD_NOT_BE_ACCEPTED")
class TestCorrectMemoryOutput:
    def test_valid_output(self):
        result=CorrectMemoryOutput(corrected=True,target_memory_id="MEMORY_001",replacement_memory_id="MEMORY_002",correlation_id="CORR_001")
        assert result.schema_version=="1.0"
        assert result.corrected is True
        assert result.target_memory_id=="MEMORY_001"
        assert result.replacement_memory_id=="MEMORY_002"
class TestDeleteMemoryInput:
    def test_valid_input(self):
        request=DeleteMemoryInput(memory_id="MEMORY_001",reason="User requested deletion.",effective_at=aware_datetime())
        assert request.memory_id=="MEMORY_001"
        assert request.reason=="User requested deletion."
        assert request.metadata=={}
    def test_rejects_empty_memory_id(self):
        with pytest.raises(ValidationError):
            DeleteMemoryInput(memory_id="",reason="User requested deletion.",effective_at=aware_datetime())
    def test_rejects_empty_reason(self):
        with pytest.raises(ValidationError):
            DeleteMemoryInput(memory_id="MEMORY_001",reason="",effective_at=aware_datetime())
    def test_rejects_naive_effective_at(self):
        with pytest.raises(ValidationError):
            DeleteMemoryInput(memory_id="MEMORY_001",reason="User requested deletion.",effective_at=datetime(2026,9,2,15,0))
    def test_rejects_extra_subject_id(self):
        with pytest.raises(ValidationError):
            DeleteMemoryInput(memory_id="MEMORY_001",reason="User requested deletion.",effective_at=aware_datetime(),subject_id="SHOULD_NOT_BE_ACCEPTED")
class TestDeleteMemoryOutput:
    def test_valid_output(self):
        result=DeleteMemoryOutput(deleted=True,memory_id="MEMORY_001",correlation_id="CORR_001")
        assert result.schema_version=="1.0"
        assert result.deleted is True
        assert result.memory_id=="MEMORY_001"
class TestExplainMemoryUseInput:
    def test_valid_input(self):
        request=ExplainMemoryUseInput(memory_id="MEMORY_001",current_intent="Find music for studying.",surface="chat",locale="en-IN")
        assert request.memory_id=="MEMORY_001"
        assert request.current_intent=="Find music for studying."
    def test_current_intent_defaults_to_none(self):
        request=ExplainMemoryUseInput(memory_id="MEMORY_001",surface="chat",locale="en-IN")
        assert request.current_intent is None
    def test_blank_current_intent_becomes_none(self):
        request=ExplainMemoryUseInput(memory_id="MEMORY_001",current_intent="   ",surface="chat",locale="en-IN")
        assert request.current_intent is None
    def test_rejects_empty_memory_id(self):
        with pytest.raises(ValidationError):
            ExplainMemoryUseInput(memory_id="",surface="chat",locale="en-IN")
    def test_rejects_empty_surface(self):
        with pytest.raises(ValidationError):
            ExplainMemoryUseInput(memory_id="MEMORY_001",surface="",locale="en-IN")
    def test_rejects_empty_locale(self):
        with pytest.raises(ValidationError):
            ExplainMemoryUseInput(memory_id="MEMORY_001",surface="chat",locale="")
    def test_rejects_extra_subject_id(self):
        with pytest.raises(ValidationError):
            ExplainMemoryUseInput(memory_id="MEMORY_001",surface="chat",locale="en-IN",subject_id="SHOULD_NOT_BE_ACCEPTED")
class TestExplainMemoryUseOutput:
    def test_valid_output(self):
        result=ExplainMemoryUseOutput(
            memory_id="MEMORY_001",
            subject_id="USER_001",
            explanation="This memory represents an explicit music preference.",
            relevance_reason="It may help personalize the current request.",
            source="mcp",
            confidence=0.95,
            timestamp=aware_datetime(),
            correlation_id="CORR_001"
        )
        assert result.schema_version=="1.0"
        assert result.memory_id=="MEMORY_001"
        assert result.subject_id=="USER_001"
        assert result.source=="mcp"
        assert result.confidence==0.95
    def test_accepts_optional_fields_as_none(self):
        result=ExplainMemoryUseOutput(memory_id="MEMORY_001",subject_id="USER_001",explanation="Explanation.",correlation_id="CORR_001")
        assert result.relevance_reason is None
        assert result.source is None
        assert result.confidence is None
        assert result.timestamp is None
    def test_rejects_confidence_above_one(self):
        with pytest.raises(ValidationError):
            ExplainMemoryUseOutput(memory_id="MEMORY_001",subject_id="USER_001",explanation="Explanation.",confidence=1.01,correlation_id="CORR_001")
    def test_rejects_negative_confidence(self):
        with pytest.raises(ValidationError):
            ExplainMemoryUseOutput(memory_id="MEMORY_001",subject_id="USER_001",explanation="Explanation.",confidence=-0.01,correlation_id="CORR_001")

