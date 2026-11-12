import os
import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.orchestration.orchestration import MemoryQueryOrchestrator
from backend_memory_pipeline.retrieval.retrieval import RetrievalCandidateV1,RetrievalDecision,RetrievalResultV1
from backend_memory_pipeline.context_composition.context_composition import ContextCompositionRequestV1,ContextCompositionService
from backend_memory_pipeline.response_generation.response_generation import ResponseGenerationRequestV1,ResponseGenerationService
class StubRetrievalService:
    def retrieve(self,request):
        timestamp=datetime(
            2026,
            8,
            25,
            10,
            0,
            0,
            tzinfo=timezone.utc
        )

        candidate=RetrievalCandidateV1(
            memory_id="MEMORY_001",
            subject_id=request.subject_id,
            memory_type="explicit_preference",
            normalized_fact="User prefers calm acoustic music.",
            status="active",
            confidence=0.95,
            source_event_ids=["SOURCE_001"],
            source_session_ids=["SESSION_001"],
            vector_score=0.95,
            graph_score=0.90,
            explicitness_score=1.0,
            recency_score=1.0,
            repetition_score=0.5,
            surface_score=1.0,
            negative_feedback_score=0.0,
            final_score=0.94,
            relevance_reason="Relevant approved memory.",
            provenance={
                "recorded_at":timestamp,
                "valid_from":timestamp,
                "valid_to":None,
                "embedding_id":"embedding:MEMORY_001",
                "retrieval_version":"1.0",
                "retrieval_rank":1
            }
        )

        return RetrievalResultV1(
            decision=RetrievalDecision.RETRIEVED,
            subject_id=request.subject_id,
            query_intent=request.intent,
            candidates=[candidate],
            candidate_count=1,
            graph_candidate_count=1,
            vector_candidate_count=1,
            returned_count=1,
            retrieval_version="1.0",
            provenance={
                "integration_test":True
            }
        )
def make_requests():
    requested_at=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    retrieval_request=__import__(
        "backend_memory_pipeline.retrieval.retrieval",
        fromlist=["RetrievalRequestV1"]
    ).RetrievalRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        intent="What kind of music do I prefer?",
        surface="chat",
        locale="en-IN",
        requested_at=requested_at
    )
    context_request=ContextCompositionRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        requested_at=requested_at,
        max_items=5,
        max_characters=12000,
        max_tokens=3000,
        surface="chat",
        locale="en-IN"
    )
    response_request=ResponseGenerationRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        query="What kind of music do I prefer?",
        surface="chat",
        locale="en-IN",
        requested_at=requested_at,
        max_response_characters=12000,
        include_memory_references=True
    )
    return retrieval_request,context_request,response_request
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY is not configured."
)
def test_real_gemini_query_orchestration():
    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=StubRetrievalService(),
        context_service=ContextCompositionService(),
        response_service=ResponseGenerationService()
    )
    retrieval_request,context_request,response_request=make_requests()
    result=orchestrator.process_query(
        retrieval_request,
        context_request,
        response_request
    )
    assert result.retrieval.decision==RetrievalDecision.RETRIEVED
    assert result.retrieval.candidate_count==1
    assert result.context.decision.value=="composed"
    assert result.context.item_count==1
    assert result.response.decision.value=="generated"
    assert result.response.memory_grounded is True
    assert result.response.subject_id=="TEST_USER_001"
    assert result.response.query=="What kind of music do I prefer?"
    assert result.response.model_name=="gemini"
    assert result.response.model_version=="gemini-3.5-flash-lite"
    assert result.response.response_text.strip()
    assert result.response.memory_references
    assert result.response.memory_references[0].memory_id=="MEMORY_001"
    assert "MEMORY_001" not in result.response.response_text