from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from mcp.server.auth.provider import AccessToken
from backend_memory_pipeline.mcp import tools
from backend_memory_pipeline.mcp.schemas import (
    SearchMemoryInput,
    AddExplicitPreferenceInput,
    CorrectMemoryInput,
    DeleteMemoryInput,
    ExplainMemoryUseInput,
)
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryExplanationResultV1,
    MemoryCorrectionResultV1,
    MemoryControlResultV1,
    OrchestrationError,
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryLifecycleAction,
    MemoryLifecycleResultV1,
    MemoryStatus,
)
from backend_memory_pipeline.retrieval.retrieval import (
    RetrievalCandidateV1,
    RetrievalDecision,
    RetrievalResultV1,
)
from backend_memory_pipeline.policy_consent.policy_consent import PolicyDecisionType
USER_ID="user_001"
OTHER_USER_ID="user_999"
NOW=datetime.now(timezone.utc)
def authenticated_token(subject_id=USER_ID):
    return AccessToken(
        token="test-token",
        client_id="spotify-ai-memory-client",
        scopes=["memory"],
        subject=subject_id,
        claims={
            "subject_id":subject_id,
            "username":"test-user",
            "token_id":"token-001",
        },
    )
@pytest.fixture
def authenticated_user():
    with patch(
        "backend_memory_pipeline.mcp.tools.get_access_token",
        return_value=authenticated_token(),
    ):
        yield
@pytest.fixture
def unauthenticated_user():
    with patch(
        "backend_memory_pipeline.mcp.tools.get_access_token",
        return_value=None,
    ):
        yield
def test_authenticated_subject_is_used_for_search(authenticated_user):
    orchestrator=Mock()
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.RETRIEVED,
        subject_id=USER_ID,
        query_intent="What music do I like?",
        candidates=[],
        candidate_count=0,
        graph_candidate_count=0,
        vector_candidate_count=0,
        returned_count=0,
        retrieval_version="1.0",
        provenance={},
    )
    request=SearchMemoryInput(
        query="What music do I like?",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
        max_items=5,
        max_characters=10000,
    )
    result=tools.search_memory(request,orchestrator)
    orchestrator.retrieve_memory.assert_called_once()
    retrieval_request=orchestrator.retrieve_memory.call_args.args[0]
    assert retrieval_request.subject_id==USER_ID
    assert retrieval_request.subject_scope==USER_ID
    assert result.memory_grounded is False
    assert result.correlation_id
def test_search_cannot_use_caller_supplied_subject_id(authenticated_user):
    orchestrator=Mock()
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.NO_RESULTS,
        subject_id=USER_ID,
        query_intent="Find my preferences",
        candidates=[],
        candidate_count=0,
        graph_candidate_count=0,
        vector_candidate_count=0,
        returned_count=0,
        retrieval_version="1.0",
        provenance={},
    )
    request=SearchMemoryInput(
        query="Find my preferences",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
    )
    request_dict=request.model_dump()
    request_dict["subject_id"]=OTHER_USER_ID
    assert "subject_id" not in request.model_dump()
    tools.search_memory(request,orchestrator)
    retrieval_request=orchestrator.retrieve_memory.call_args.args[0]
    assert retrieval_request.subject_id==USER_ID
    assert retrieval_request.subject_scope==USER_ID
    assert retrieval_request.subject_id!=OTHER_USER_ID
def test_search_returns_only_authenticated_subject_memories(authenticated_user):
    orchestrator=Mock()
    candidate=RetrievalCandidateV1(
        memory_id="memory-001",
        subject_id=USER_ID,
        memory_type="explicit_preference",
        normalized_fact="I like jazz music.",
        status=MemoryStatus.ACTIVE,
        confidence=0.95,
        vector_score=0.90,
        graph_score=0.80,
        explicitness_score=1.0,
        recency_score=0.90,
        repetition_score=0.70,
        surface_score=1.0,
        negative_feedback_score=0.0,
        final_score=0.91,
        source_event_ids=["event-001"],
        source_session_ids=["session-001"],
        relevance_reason="Matches the current music preference query.",
        provenance={"subject_scope":USER_ID},
    )
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.RETRIEVED,
        subject_id=USER_ID,
        query_intent="What music do I like?",
        candidates=[candidate],
        candidate_count=1,
        graph_candidate_count=1,
        vector_candidate_count=1,
        returned_count=1,
        retrieval_version="1.0",
        provenance={"subject_id":USER_ID},
    )
    request=SearchMemoryInput(
        query="What music do I like?",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
    )
    result=tools.search_memory(request,orchestrator)
    assert len(result.context_items)==1
    assert result.context_items[0]["memory_id"]=="memory-001"
    assert result.context_items[0]["normalized_fact"]=="I like jazz music."
    retrieval_request=orchestrator.retrieve_memory.call_args.args[0]
    assert retrieval_request.subject_id==USER_ID
    assert retrieval_request.subject_scope==USER_ID
def test_search_maps_limits_and_metadata(authenticated_user):
    orchestrator=Mock()
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.NO_RESULTS,
        subject_id=USER_ID,
        query_intent="preferences",
        candidates=[],
        candidate_count=0,
        graph_candidate_count=0,
        vector_candidate_count=0,
        returned_count=0,
        retrieval_version="1.0",
        provenance={},
    )
    request=SearchMemoryInput(
        query="preferences",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
        max_items=7,
        max_characters=2500,
    )
    tools.search_memory(request,orchestrator)
    retrieval_request=orchestrator.retrieve_memory.call_args.args[0]
    assert retrieval_request.top_k==7
    assert retrieval_request.candidate_limit==7
    assert retrieval_request.metadata["source"]=="mcp"
    assert retrieval_request.metadata["max_characters"]==2500
def test_search_enforces_max_character_limit(authenticated_user):
    orchestrator=Mock()
    candidates=[
        RetrievalCandidateV1(
            memory_id="memory-001",
            subject_id=USER_ID,
            memory_type="explicit_preference",
            normalized_fact="A"*100,
            status=MemoryStatus.ACTIVE,
            confidence=0.95,
            vector_score=0.90,
            graph_score=0.80,
            explicitness_score=1.0,
            recency_score=0.90,
            repetition_score=0.70,
            surface_score=1.0,
            negative_feedback_score=0.0,
            final_score=0.91,
            source_event_ids=["event-001"],
            source_session_ids=["session-001"],
            relevance_reason="Matches the current memory search.",
            provenance={},
        ),
        RetrievalCandidateV1(
            memory_id="memory-002",
            subject_id=USER_ID,
            memory_type="explicit_preference",
            normalized_fact="B"*100,
            status=MemoryStatus.ACTIVE,
            confidence=0.90,
            vector_score=0.85,
            graph_score=0.75,
            explicitness_score=1.0,
            recency_score=0.80,
            repetition_score=0.60,
            surface_score=1.0,
            negative_feedback_score=0.0,
            final_score=0.85,
            source_event_ids=["event-002"],
            source_session_ids=["session-002"],
            relevance_reason="Matches the current memory search.",
            provenance={},
        ),
    ]
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.RETRIEVED,
        subject_id=USER_ID,
        query_intent="preferences",
        candidates=candidates,
        candidate_count=2,
        graph_candidate_count=2,
        vector_candidate_count=2,
        returned_count=2,
        retrieval_version="1.0",
        provenance={},
    )
    request=SearchMemoryInput(
        query="preferences",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
        max_items=5,
        max_characters=150,
    )
    result=tools.search_memory(request,orchestrator)
    assert len(result.context_items)==1
    assert len(result.context_items[0]["normalized_fact"])==100
def test_add_explicit_preference_uses_authenticated_subject(authenticated_user):
    orchestrator=Mock()
    lifecycle_result=SimpleNamespace(
        created_memory_id="memory-001",
        memory_id=None,
    )
    policy_result=SimpleNamespace(
        decision=PolicyDecisionType.ALLOW,
    )
    orchestrator.add_explicit_preference.return_value=SimpleNamespace(
        lifecycle_results=[lifecycle_result],
        policy_decisions=[policy_result],
    )
    request=AddExplicitPreferenceInput(
        preference="I prefer jazz music.",
        session_id="session-001",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    result=tools.add_explicit_preference(request,orchestrator)
    orchestrator.add_explicit_preference.assert_called_once()
    kwargs=orchestrator.add_explicit_preference.call_args.kwargs
    assert kwargs["subject_id"]==USER_ID
    assert kwargs["subject_scope"]==USER_ID
    assert kwargs["preference"]=="I prefer jazz music."
    assert kwargs["session_id"]=="session-001"
    assert kwargs["surface"]=="chat"
    assert kwargs["locale"]=="en-IN"
    assert kwargs["effective_at"]==NOW
    assert kwargs["metadata"]["source"]=="mcp"
    assert result.accepted is True
    assert result.memory_ids==["memory-001"]
    assert result.correlation_id
def test_add_explicit_preference_cannot_target_another_subject(authenticated_user):
    orchestrator=Mock()
    orchestrator.add_explicit_preference.return_value=SimpleNamespace(
        lifecycle_results=[],
        policy_decisions=[],
    )
    request=AddExplicitPreferenceInput(
        preference="I like rock.",
        session_id="session-001",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    tools.add_explicit_preference(request,orchestrator)
    kwargs=orchestrator.add_explicit_preference.call_args.kwargs
    assert kwargs["subject_id"]==USER_ID
    assert kwargs["subject_scope"]==USER_ID
    assert kwargs["subject_id"]!=OTHER_USER_ID
def test_add_explicit_preference_retains_memory_result(authenticated_user):
    orchestrator=Mock()
    lifecycle_result=SimpleNamespace(
        created_memory_id="memory-123",
        memory_id=None,
    )
    policy_result=SimpleNamespace(
        decision=PolicyDecisionType.ALLOW,
    )
    orchestrator.add_explicit_preference.return_value=SimpleNamespace(
        lifecycle_results=[lifecycle_result],
        policy_decisions=[policy_result],
    )
    request=AddExplicitPreferenceInput(
        preference="I prefer classical music.",
        session_id="session-123",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    result=tools.add_explicit_preference(request,orchestrator)
    assert result.accepted is True
    assert result.memory_ids==["memory-123"]
def test_correct_memory_uses_authenticated_subject(authenticated_user):
    orchestrator=Mock()
    lifecycle_result=SimpleNamespace(
        changed=True,
        created_memory_id="memory-replacement",
        memory_id="memory-replacement",
    )
    orchestrator.process_memory_correction.return_value=SimpleNamespace(
        target_memory_id="memory-original",
        lifecycle_result=lifecycle_result,
    )
    request=CorrectMemoryInput(
        memory_id="memory-original",
        corrected_statement="I prefer classical music.",
        session_id="session-001",
        reason="Previous preference was incorrect.",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    result=tools.correct_memory(request,orchestrator)
    orchestrator.process_memory_correction.assert_called_once()
    command=orchestrator.process_memory_correction.call_args.args[0]
    assert command.target_memory_id=="memory-original"
    assert command.subject_id==USER_ID
    assert command.subject_scope==USER_ID
    assert command.corrected_statement=="I prefer classical music."
    assert command.reason=="Previous preference was incorrect."
    assert command.metadata["source"]=="mcp"
    assert result.corrected is True
    assert result.target_memory_id=="memory-original"
    assert result.replacement_memory_id=="memory-replacement"
    assert result.correlation_id
def test_correct_memory_cannot_target_another_subject(authenticated_user):
    orchestrator=Mock()
    orchestrator.process_memory_correction.side_effect=OrchestrationError(
        "Memory does not belong to the requested subject."
    )
    request=CorrectMemoryInput(
        memory_id="other-user-memory",
        corrected_statement="I like classical music.",
        session_id="session-001",
        reason="Correction.",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    with pytest.raises(OrchestrationError,match="does not belong"):
        tools.correct_memory(request,orchestrator)
    command=orchestrator.process_memory_correction.call_args.args[0]
    assert command.subject_id==USER_ID
    assert command.subject_scope==USER_ID
def test_delete_memory_uses_authenticated_subject(authenticated_user):
    orchestrator=Mock()
    lifecycle_result=SimpleNamespace(
        changed=True,
        memory_id="memory-001",
        created_memory_id=None,
    )
    orchestrator.apply_lifecycle_action.return_value=SimpleNamespace(
        lifecycle_result=lifecycle_result,
        consent_state=None,
    )
    request=DeleteMemoryInput(
        memory_id="memory-001",
        reason="User requested deletion.",
        effective_at=NOW,
    )
    result=tools.delete_memory(request,orchestrator)
    orchestrator.apply_lifecycle_action.assert_called_once()
    lifecycle_request=orchestrator.apply_lifecycle_action.call_args.args[0]
    assert lifecycle_request.action==MemoryLifecycleAction.DELETE
    assert lifecycle_request.memory_id=="memory-001"
    assert lifecycle_request.subject_id==USER_ID
    assert lifecycle_request.subject_scope==USER_ID
    assert lifecycle_request.reason=="User requested deletion."
    assert lifecycle_request.metadata["source"]=="mcp"
    assert result.deleted is True
    assert result.memory_id=="memory-001"
    assert result.correlation_id
def test_delete_memory_cannot_delete_another_subject_memory(authenticated_user):
    orchestrator=Mock()
    orchestrator.apply_lifecycle_action.side_effect=OrchestrationError(
        "Memory does not belong to the requested subject."
    )
    request=DeleteMemoryInput(
        memory_id="other-user-memory",
        reason="Delete it.",
        effective_at=NOW,
    )
    with pytest.raises(OrchestrationError,match="does not belong"):
        tools.delete_memory(request,orchestrator)
    lifecycle_request=orchestrator.apply_lifecycle_action.call_args.args[0]
    assert lifecycle_request.subject_id==USER_ID
    assert lifecycle_request.subject_scope==USER_ID
def test_explain_memory_use_uses_authenticated_subject(authenticated_user):
    orchestrator=Mock()
    orchestrator.explain_memory_use.return_value=MemoryExplanationResultV1(
        memory_id="memory-001",
        subject_id=USER_ID,
        explanation="This memory was used because it matches your current music preference.",
        relevance_reason="The current request asks about preferred music.",
        source="mcp",
        confidence=0.95,
        timestamp=NOW,
    )
    request=ExplainMemoryUseInput(
        memory_id="memory-001",
        current_intent="What music should I listen to?",
        surface="chat",
        locale="en-IN",
    )
    result=tools.explain_memory_use(request,orchestrator)
    orchestrator.explain_memory_use.assert_called_once()
    explanation_request=orchestrator.explain_memory_use.call_args.args[0]
    assert explanation_request.memory_id=="memory-001"
    assert explanation_request.subject_id==USER_ID
    assert explanation_request.subject_scope==USER_ID
    assert explanation_request.current_intent=="What music should I listen to?"
    assert explanation_request.surface=="chat"
    assert explanation_request.locale=="en-IN"
    assert result.subject_id==USER_ID
    assert result.source=="mcp"
    assert result.correlation_id
def test_explain_memory_use_cannot_expose_another_subject_memory(authenticated_user):
    orchestrator=Mock()
    orchestrator.explain_memory_use.side_effect=OrchestrationError(
        "Memory does not belong to the requested subject."
    )
    request=ExplainMemoryUseInput(
        memory_id="other-user-memory",
        current_intent="Why was this memory used?",
        surface="chat",
        locale="en-IN",
    )
    with pytest.raises(OrchestrationError,match="does not belong"):
        tools.explain_memory_use(request,orchestrator)
    explanation_request=orchestrator.explain_memory_use.call_args.args[0]
    assert explanation_request.memory_id=="other-user-memory"
    assert explanation_request.subject_id==USER_ID
    assert explanation_request.subject_scope==USER_ID
def test_unauthenticated_search_is_rejected(unauthenticated_user):
    orchestrator=Mock()
    request=SearchMemoryInput(
        query="preferences",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
    )
    with pytest.raises(OrchestrationError,match="authentication is required"):
        tools.search_memory(request,orchestrator)
    orchestrator.retrieve_memory.assert_not_called()
def test_unauthenticated_add_preference_is_rejected(unauthenticated_user):
    orchestrator=Mock()
    request=AddExplicitPreferenceInput(
        preference="I like jazz.",
        session_id="session-001",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    with pytest.raises(OrchestrationError,match="authentication is required"):
        tools.add_explicit_preference(request,orchestrator)
    orchestrator.add_explicit_preference.assert_not_called()
def test_unauthenticated_correction_is_rejected(unauthenticated_user):
    orchestrator=Mock()
    request=CorrectMemoryInput(
        memory_id="memory-001",
        corrected_statement="I like rock.",
        session_id="session-001",
        reason="Correction.",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    with pytest.raises(OrchestrationError,match="authentication is required"):
        tools.correct_memory(request,orchestrator)
    orchestrator.process_memory_correction.assert_not_called()
def test_unauthenticated_deletion_is_rejected(unauthenticated_user):
    orchestrator=Mock()
    request=DeleteMemoryInput(
        memory_id="memory-001",
        reason="Delete.",
        effective_at=NOW,
    )
    with pytest.raises(OrchestrationError,match="authentication is required"):
        tools.delete_memory(request,orchestrator)
    orchestrator.apply_lifecycle_action.assert_not_called()
def test_unauthenticated_explanation_is_rejected(unauthenticated_user):
    orchestrator=Mock()
    request=ExplainMemoryUseInput(
        memory_id="memory-001",
        current_intent="Why?",
        surface="chat",
        locale="en-IN",
    )
    with pytest.raises(OrchestrationError,match="authentication is required"):
        tools.explain_memory_use(request,orchestrator)
    orchestrator.explain_memory_use.assert_not_called()
def test_search_generates_correlation_id(authenticated_user):
    orchestrator=Mock()
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.NO_RESULTS,
        subject_id=USER_ID,
        query_intent="test",
        candidates=[],
        candidate_count=0,
        graph_candidate_count=0,
        vector_candidate_count=0,
        returned_count=0,
        retrieval_version="1.0",
        provenance={},
    )
    request=SearchMemoryInput(
        query="test",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
    )
    result=tools.search_memory(request,orchestrator)
    assert isinstance(result.correlation_id,str)
    assert result.correlation_id.strip()
def test_add_preference_generates_correlation_id(authenticated_user):
    orchestrator=Mock()
    orchestrator.add_explicit_preference.return_value=SimpleNamespace(
        lifecycle_results=[],
        policy_decisions=[],
    )
    request=AddExplicitPreferenceInput(
        preference="I like jazz.",
        session_id="session-001",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    result=tools.add_explicit_preference(request,orchestrator)
    assert isinstance(result.correlation_id,str)
    assert result.correlation_id.strip()
def test_correction_generates_correlation_id(authenticated_user):
    orchestrator=Mock()
    orchestrator.process_memory_correction.return_value=SimpleNamespace(
        target_memory_id="memory-001",
        lifecycle_result=SimpleNamespace(
            changed=True,
            created_memory_id="memory-002",
            memory_id="memory-002",
        ),
    )
    request=CorrectMemoryInput(
        memory_id="memory-001",
        corrected_statement="I like jazz.",
        session_id="session-001",
        reason="Correction.",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    result=tools.correct_memory(request,orchestrator)
    assert isinstance(result.correlation_id,str)
    assert result.correlation_id.strip()
def test_delete_generates_correlation_id(authenticated_user):
    orchestrator=Mock()
    orchestrator.apply_lifecycle_action.return_value=SimpleNamespace(
        lifecycle_result=SimpleNamespace(
            changed=True,
            memory_id="memory-001",
            created_memory_id=None,
        ),
        consent_state=None,
    )
    request=DeleteMemoryInput(
        memory_id="memory-001",
        reason="Delete.",
        effective_at=NOW,
    )
    result=tools.delete_memory(request,orchestrator)
    assert isinstance(result.correlation_id,str)
    assert result.correlation_id.strip()
def test_explanation_generates_correlation_id(authenticated_user):
    orchestrator=Mock()
    orchestrator.explain_memory_use.return_value=MemoryExplanationResultV1(
        memory_id="memory-001",
        subject_id=USER_ID,
        explanation="This memory was relevant.",
        relevance_reason="Intent match.",
        source="mcp",
        confidence=0.90,
        timestamp=NOW,
    )
    request=ExplainMemoryUseInput(
        memory_id="memory-001",
        current_intent="What do I like?",
        surface="chat",
        locale="en-IN",
    )
    result=tools.explain_memory_use(request,orchestrator)
    assert isinstance(result.correlation_id,str)
    assert result.correlation_id.strip()
def test_search_delegates_to_query_orchestrator(authenticated_user):
    orchestrator=Mock()
    orchestrator.retrieve_memory.return_value=RetrievalResultV1(
        decision=RetrievalDecision.NO_RESULTS,
        subject_id=USER_ID,
        query_intent="test",
        candidates=[],
        candidate_count=0,
        graph_candidate_count=0,
        vector_candidate_count=0,
        returned_count=0,
        retrieval_version="1.0",
        provenance={},
    )
    request=SearchMemoryInput(
        query="test",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
    )
    tools.search_memory(request,orchestrator)
    orchestrator.retrieve_memory.assert_called_once()
def test_add_preference_delegates_to_write_orchestrator(authenticated_user):
    orchestrator=Mock()
    orchestrator.add_explicit_preference.return_value=SimpleNamespace(
        lifecycle_results=[],
        policy_decisions=[],
    )
    request=AddExplicitPreferenceInput(
        preference="I like jazz.",
        session_id="session-001",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    tools.add_explicit_preference(request,orchestrator)
    orchestrator.add_explicit_preference.assert_called_once()
def test_correction_delegates_to_control_orchestrator(authenticated_user):
    orchestrator=Mock()
    orchestrator.process_memory_correction.return_value=SimpleNamespace(
        target_memory_id="memory-001",
        lifecycle_result=SimpleNamespace(
            changed=True,
            created_memory_id="memory-002",
            memory_id="memory-002",
        ),
    )
    request=CorrectMemoryInput(
        memory_id="memory-001",
        corrected_statement="I like jazz.",
        session_id="session-001",
        reason="Correction.",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    tools.correct_memory(request,orchestrator)
    orchestrator.process_memory_correction.assert_called_once()
def test_delete_delegates_to_control_orchestrator(authenticated_user):
    orchestrator=Mock()
    orchestrator.apply_lifecycle_action.return_value=SimpleNamespace(
        lifecycle_result=SimpleNamespace(
            changed=True,
            memory_id="memory-001",
            created_memory_id=None,
        ),
        consent_state=None,
    )
    request=DeleteMemoryInput(
        memory_id="memory-001",
        reason="Delete.",
        effective_at=NOW,
    )
    tools.delete_memory(request,orchestrator)
    orchestrator.apply_lifecycle_action.assert_called_once()
def test_explanation_delegates_to_query_orchestrator(authenticated_user):
    orchestrator=Mock()
    orchestrator.explain_memory_use.return_value=MemoryExplanationResultV1(
        memory_id="memory-001",
        subject_id=USER_ID,
        explanation="This memory was relevant.",
        relevance_reason="Intent match.",
        source="mcp",
        confidence=0.90,
        timestamp=NOW,
    )
    request=ExplainMemoryUseInput(
        memory_id="memory-001",
        current_intent="What do I like?",
        surface="chat",
        locale="en-IN",
    )
    tools.explain_memory_use(request,orchestrator)
    orchestrator.explain_memory_use.assert_called_once()
def test_search_wraps_unexpected_errors(authenticated_user):
    orchestrator=Mock()
    orchestrator.retrieve_memory.side_effect=RuntimeError("database unavailable")
    request=SearchMemoryInput(
        query="preferences",
        surface="chat",
        locale="en-IN",
        requested_at=NOW,
    )
    with pytest.raises(
        OrchestrationError,
        match="MCP memory search failed",
    ):
        tools.search_memory(request,orchestrator)
def test_add_preference_wraps_unexpected_errors(authenticated_user):
    orchestrator=Mock()
    orchestrator.add_explicit_preference.side_effect=RuntimeError(
        "pipeline failure"
    )
    request=AddExplicitPreferenceInput(
        preference="I like jazz.",
        session_id="session-001",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    with pytest.raises(
        OrchestrationError,
        match="MCP explicit preference processing failed",
    ):
        tools.add_explicit_preference(request,orchestrator)
def test_correction_wraps_unexpected_errors(authenticated_user):
    orchestrator=Mock()
    orchestrator.process_memory_correction.side_effect=RuntimeError(
        "correction failure"
    )
    request=CorrectMemoryInput(
        memory_id="memory-001",
        corrected_statement="I like jazz.",
        session_id="session-001",
        reason="Correction.",
        surface="chat",
        locale="en-IN",
        effective_at=NOW,
    )
    with pytest.raises(
        OrchestrationError,
        match="MCP memory correction failed",
    ):
        tools.correct_memory(request,orchestrator)
def test_delete_wraps_unexpected_errors(authenticated_user):
    orchestrator=Mock()
    orchestrator.apply_lifecycle_action.side_effect=RuntimeError(
        "deletion failure"
    )
    request=DeleteMemoryInput(
        memory_id="memory-001",
        reason="Delete.",
        effective_at=NOW,
    )
    with pytest.raises(
        OrchestrationError,
        match="MCP memory deletion failed",
    ):
        tools.delete_memory(request,orchestrator)
def test_explanation_wraps_unexpected_errors(authenticated_user):
    orchestrator=Mock()
    orchestrator.explain_memory_use.side_effect=RuntimeError(
        "explanation failure"
    )
    request=ExplainMemoryUseInput(
        memory_id="memory-001",
        current_intent="Why?",
        surface="chat",
        locale="en-IN",
    )
    with pytest.raises(
        OrchestrationError,
        match="MCP memory explanation failed",
    ):
        tools.explain_memory_use(request,orchestrator)