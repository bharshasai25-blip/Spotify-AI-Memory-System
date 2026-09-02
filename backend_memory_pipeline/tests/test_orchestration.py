import pytest
from datetime import datetime,timezone
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryControlOrchestrator,
    MemoryCorrectionCommandV1,
    MemoryExplanationRequestV1,
    MemoryQueryOrchestrator,
    MemoryWriteOrchestrator,
    OrchestrationError
)
from backend_memory_pipeline.ingestion.ingestion import (
    ConsentState,
    EventType,
    IngestionService,
    MemoryControlAction
)
from backend_memory_pipeline.event_validation.event_validation import (
    EventValidator,
    ValidationStatus
)
from backend_memory_pipeline.memory_extraction.memory_extraction import (
    ExtractedMemoryCandidate,
    ExtractionDecision,
    MemoryExtractionService,
    MemoryType,
    PolicyClass,
    TemporalScope
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    DefaultPolicyEngine,
    MemoryControlAction,
    PolicyConsentService,
    PolicyDecisionType,
    PolicyRequestV1
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    InMemoryMemoryStore,
    MemoryLifecycleService,
    MemoryLifecycleAction,
    MemoryStatus
)
from backend_memory_pipeline.graph_memory.graph import (
    GraphMemoryService,
    InMemoryGraphStore
)
from backend_memory_pipeline.embedding.embedding import (
    EmbeddingService,
    InMemoryEmbeddingStore
)
from backend_memory_pipeline.retrieval.retrieval import (
    InMemoryRetrievalStore,
    RetrievalRequestV1,
    RetrievalService
)
from backend_memory_pipeline.context_composition.context_composition import (
    ContextCompositionRequestV1,
    ContextCompositionService
)
from backend_memory_pipeline.response_generation.response_generation import (
    DeterministicMemoryGroundedGenerator,
    ResponseGenerationRequestV1,
    ResponseGenerationService
)
def make_event(
    event_id="EVENT_001",
    subject_id="TEST_USER_001",
    event_type=EventType.AI_INTERACTION,
    text="I prefer calm acoustic music.",
    consent_state=ConsentState.OPTED_IN,
    metadata=None
):
    return {
        "event_id":event_id,
        "source_event_id":f"SOURCE_{event_id}",
        "subject_id":subject_id,
        "subject_scope":subject_id,
        "session_id":"SESSION_001",
        "event_type":event_type,
        "source":"synthetic_test",
        "surface":"chat",
        "locale":"en-IN",
        "timestamp":datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
        "consent_state":consent_state,
        "idempotency_key":f"IDEMP_{event_id}",
        "correlation_id":f"CORR_{event_id}",
        "text":text,
        "entity":None,
        "context_entities":{},
        "metadata":metadata or {}
    }
def make_policy_request(
    subject_id="TEST_USER_001",
    consent_state=ConsentState.OPTED_IN
):
    return PolicyRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        purpose="personalization",
        surface="chat",
        locale="en-IN",
        consent_state=consent_state
    )

def make_response_service():
    return ResponseGenerationService(
        generator=DeterministicMemoryGroundedGenerator()
    )

def build_query_orchestrator():
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    retrieval_store=InMemoryRetrievalStore(
        graph_store,
        embedding_store
    )
    return MemoryQueryOrchestrator(
        retrieval_service=RetrievalService(
            retrieval_store
        ),
        context_service=ContextCompositionService(),
        response_service=make_response_service()
    )
def make_query_requests(
    subject_id="TEST_USER_001",
    query="What music do I prefer?"
):
    requested_at=datetime(
        2026,
        8,
        25,
        12,
        0,
        0,
        tzinfo=timezone.utc
    )
    retrieval_request=RetrievalRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        intent=query,
        surface="chat",
        locale="en-IN",
        requested_at=requested_at
    )
    context_request=ContextCompositionRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        requested_at=requested_at,
        surface="chat",
        locale="en-IN"
    )
    response_request=ResponseGenerationRequestV1(
        subject_id=subject_id,
        subject_scope=subject_id,
        query=query,
        surface="chat",
        locale="en-IN",
        requested_at=requested_at
    )
    return retrieval_request,context_request,response_request

def test_write_orchestrator_processes_valid_event():
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(
            DefaultPolicyEngine()
        ),
        lifecycle_service=MemoryLifecycleService(
            lifecycle_store
        ),
        graph_service=GraphMemoryService(
            graph_store
        ),
        embedding_service=EmbeddingService(
            embedding_store
        )
    )
    result=orchestrator.process_event(
        make_event(),
        authorized_subject_id="TEST_USER_001",
        policy_request=make_policy_request()
    )
    assert result.ingestion.status=="accepted"
    assert result.validation.status==ValidationStatus.VALID
    assert result.extraction.candidates
    assert result.policy_decisions
    assert result.policy_decisions[0].decision==PolicyDecisionType.ALLOW
    assert result.lifecycle_results
    assert result.graph_results
    assert result.embedding_results
def test_write_orchestrator_persists_created_memory():
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(),
        lifecycle_service=MemoryLifecycleService(
            lifecycle_store
        ),
        graph_service=GraphMemoryService(
            graph_store
        ),
        embedding_service=EmbeddingService(
            embedding_store
        )
    )
    result=orchestrator.process_event(
        make_event(),
        authorized_subject_id="TEST_USER_001"
    )
    lifecycle_result=result.lifecycle_results[0]
    memory_id=lifecycle_result.created_memory_id
    assert memory_id is not None
    memory=lifecycle_store.get(memory_id)
    assert memory is not None
    assert memory.subject_id=="TEST_USER_001"
def test_write_orchestrator_synchronizes_graph_and_embedding():
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(),
        lifecycle_service=MemoryLifecycleService(
            lifecycle_store
        ),
        graph_service=GraphMemoryService(
            graph_store
        ),
        embedding_service=EmbeddingService(
            embedding_store
        )
    )
    result=orchestrator.process_event(
        make_event(),
        authorized_subject_id="TEST_USER_001"
    )
    memory_id=result.lifecycle_results[0].created_memory_id
    assert memory_id is not None
    assert graph_store.get_memory(memory_id) is not None
    assert embedding_store.get(memory_id) is not None
def test_write_orchestrator_rejects_subject_mismatch():
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(),
        lifecycle_service=MemoryLifecycleService(),
        graph_service=GraphMemoryService(
            InMemoryGraphStore()
        ),
        embedding_service=EmbeddingService(
            InMemoryEmbeddingStore()
        )
    )
    with pytest.raises(OrchestrationError):
        orchestrator.process_event(
            make_event(
                subject_id="TEST_USER_001"
            ),
            authorized_subject_id="TEST_USER_999"
        )
def test_write_orchestrator_stops_when_event_is_invalid():
    invalid_event=make_event()
    invalid_event["timestamp"]=datetime(
        2026,
        8,
        25,
        10,
        0,
        0
    )
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService()
    )
    with pytest.raises(OrchestrationError,match="Ingestion failed"):
        orchestrator.process_event(
            invalid_event,
            authorized_subject_id="TEST_USER_001"
        )
    #assert result.validation.status!=ValidationStatus.VALID
    #assert result.lifecycle_results==[]
    #assert result.graph_results==[]
    #assert result.embedding_results==[]
def test_write_orchestrator_returns_no_memory_when_extraction_has_no_candidates():
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService()
    )
    result=orchestrator.process_event(
        make_event(
            event_type=EventType.PLAYBACK,
            text=None,
            metadata={"playback_action":"play"}
        ),
        authorized_subject_id="TEST_USER_001"
    )
    assert result.validation.status==ValidationStatus.VALID
    assert result.extraction.candidates==[]
    assert result.lifecycle_results==[]
    assert result.graph_results==[]
    assert result.embedding_results==[]
def test_write_orchestrator_respects_opted_out_consent():
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(),
        lifecycle_service=MemoryLifecycleService(
            lifecycle_store
        ),
        graph_service=GraphMemoryService(
            graph_store
        ),
        embedding_service=EmbeddingService(
            embedding_store
        )
    )
    with pytest.raises(OrchestrationError,match="Memory extraction failed"):
        orchestrator.process_event(
            make_event(
                consent_state=ConsentState.OPTED_OUT
            ),
            authorized_subject_id="TEST_USER_001"
        )
    assert lifecycle_store.all()==[]
    #assert result.validation.status==ValidationStatus.VALID
    #assert result.policy_decisions
    #assert result.policy_decisions[0].decision==PolicyDecisionType.DENY
    #assert result.lifecycle_results==[]
    #assert result.graph_results==[]
    #assert result.embedding_results==[]
def test_query_orchestrator_returns_no_memory_response_when_store_is_empty():
    orchestrator=build_query_orchestrator()
    retrieval_request,context_request,response_request=make_query_requests()
    result=orchestrator.process_query(
        retrieval_request,
        context_request,
        response_request
    )
    assert result.retrieval.decision.value=="no_results"
    assert result.context.decision.value=="no_context"
    assert result.response.memory_grounded is False
    assert result.response.decision.value=="no_context"
def test_query_orchestrator_preserves_query():
    orchestrator=build_query_orchestrator()
    query="What music do I prefer?"
    retrieval_request,context_request,response_request=make_query_requests(
        query=query
    )
    result=orchestrator.process_query(
        retrieval_request,
        context_request,
        response_request
    )
    assert result.response.query==query
    assert result.retrieval.query_intent==query
    assert result.context.query_intent==query
def test_query_orchestrator_executes_all_three_stages():
    class StubRetrieval:
        def retrieve(self,request):
            from backend_memory_pipeline.retrieval.retrieval import RetrievalResultV1
            return RetrievalResultV1(
                decision="no_results",
                subject_id=request.subject_id,
                query_intent=request.intent,
                candidates=[],
                candidate_count=0,
                graph_candidate_count=0,
                vector_candidate_count=0,
                returned_count=0
            )
    class StubContext:
        def compose(self,retrieval_result,request):
            return ContextCompositionService().compose(
                retrieval_result,
                request
            )
    class StubResponse:
        def generate(self,context,request):
            return make_response_service().generate(
                context,
                request
            )
    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=StubRetrieval(),
        context_service=StubContext(),
        response_service=StubResponse()
    )
    retrieval_request,context_request,response_request=make_query_requests()
    result=orchestrator.process_query(
        retrieval_request,
        context_request,
        response_request
    )
    assert result.retrieval.decision.value=="no_results"
    assert result.context.decision.value=="no_context"
    assert result.response.decision.value=="no_context"
def test_query_orchestrator_wraps_retrieval_failure():
    class FailingRetrieval:
        def retrieve(self,request):
            raise RuntimeError("Retrieval failed")

    policy_service=PolicyConsentService()

    consent_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(2026,8,25,10,0,0,tzinfo=timezone.utc),
        correlation_id="CONSENT_RETRIEVAL_FAILURE_001"
    )

    policy_service.apply_consent_control(consent_request)

    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=FailingRetrieval(),
        policy_consent_service=policy_service,
        response_service=make_response_service())

    retrieval_request,context_request,response_request=make_query_requests()

    with pytest.raises(OrchestrationError,match="Retrieval failed"):
        orchestrator.process_query(retrieval_request,
            context_request,response_request)
        
def test_query_orchestrator_wraps_context_failure():
    class FailingContext:
        def compose(self,retrieval_result,request):
            raise RuntimeError("Context failed")
    class ValidRetrieval:
        def retrieve(self,request):
            from backend_memory_pipeline.retrieval.retrieval import RetrievalResultV1
            return RetrievalResultV1(
                decision="no_results",
                subject_id=request.subject_id,
                query_intent=request.intent,
                candidates=[],
                candidate_count=0,
                graph_candidate_count=0,
                vector_candidate_count=0,
                returned_count=0)
    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=ValidRetrieval(),
        context_service=FailingContext(),
        response_service=make_response_service())
    retrieval_request,context_request,response_request=make_query_requests()
    with pytest.raises(OrchestrationError,match="Context composition failed"):
        orchestrator.process_query(
            retrieval_request,
            context_request,
            response_request)
        
def test_query_orchestrator_wraps_response_failure():
    class ValidRetrieval:
        def retrieve(self,request):
            from backend_memory_pipeline.retrieval.retrieval import RetrievalResultV1
            return RetrievalResultV1(
                decision="no_results",
                subject_id=request.subject_id,
                query_intent=request.intent,
                candidates=[],
                candidate_count=0,
                graph_candidate_count=0,
                vector_candidate_count=0,
                returned_count=0
            )
    class ValidContext:
        def compose(self,retrieval_result,request):
            return ContextCompositionService().compose(
                retrieval_result,
                request
            )
    class FailingResponse:
        def generate(self,context,request):
            raise RuntimeError("Response failed")
    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=ValidRetrieval(),
        context_service=ValidContext(),
        response_service=FailingResponse()
    )
    retrieval_request,context_request,response_request=make_query_requests()
    with pytest.raises(OrchestrationError,match="Response generation failed"):
        orchestrator.process_query(
            retrieval_request,
            context_request,
            response_request
        )
def test_control_orchestrator_can_opt_in():
    orchestrator=MemoryControlOrchestrator()
    request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            25,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="CONTROL_001"
    )
    result=orchestrator.apply_consent_control(request)
    assert result.consent_state is not None
    assert result.consent_state.state_record.state==ConsentState.OPTED_IN
def test_control_orchestrator_can_pause_and_resume():
    orchestrator=MemoryControlOrchestrator()
    pause_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.PAUSE,
        timestamp=datetime(
            2026,
            8,
            25,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="PAUSE_001"
    )
    pause_result=orchestrator.apply_consent_control(
        pause_request
    )
    assert pause_result.consent_state.state_record.state==ConsentState.PAUSED
    resume_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.RESUME,
        timestamp=datetime(
            2026,
            8,
            25,
            11,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="RESUME_001"
    )
    resume_result=orchestrator.apply_consent_control(
        resume_request
    )
    assert resume_result.consent_state.state_record.state==ConsentState.OPTED_IN
def test_control_orchestrator_propagates_consent_failure():
    class FailingPolicyService:
        def apply_consent_control(self,request):
            raise RuntimeError("Consent control failed")
    orchestrator=MemoryControlOrchestrator(
        policy_consent_service=FailingPolicyService()
    )
    request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            25,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="CONTROL_001"
    )
    with pytest.raises(OrchestrationError,match="Consent control failed"):
        orchestrator.apply_consent_control(request)
       
def test_orchestration_write_result_is_immutable():
    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService()
    )
    result=orchestrator.process_event(
        make_event(
            event_type=EventType.PLAYBACK,
            text=None,
            metadata={"playback_action":"play"}
        ),
        authorized_subject_id="TEST_USER_001"
    )
    with pytest.raises((AttributeError,TypeError)):
        result.validation=result.validation

def test_memory_control_orchestrator_preserves_consent_control_result():
    service=PolicyConsentService()
    orchestrator=MemoryControlOrchestrator(
        policy_consent_service=service
    )
    request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            27,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="CORR_TEST_001"
    )
    result=orchestrator.apply_consent_control(
        request
    )
    assert result.consent_state is not None
    assert result.consent_state.previous_state==ConsentState.UNKNOWN
    assert result.consent_state.current_state==ConsentState.OPTED_IN
    assert result.consent_state.changed is True
    assert result.consent_state.correlation_id=="CORR_TEST_001"
    assert result.consent_state.reason
    assert result.consent_state.state_record.state==result.consent_state.current_state
    assert result.consent_state.state_record.last_action==result.consent_state.action
    assert result.consent_state.state_record.correlation_id=="CORR_TEST_001"
    assert result.lifecycle_result is None

def test_memory_control_orchestrator_corrects_existing_memory():
    lifecycle=MemoryLifecycleService()
    policy=PolicyConsentService()

    consent_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            27,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="CONSENT_001"
    )

    policy.apply_consent_control(
        consent_request
    )

    initial_candidate=ExtractedMemoryCandidate(
        candidate_id="candidate_initial_001",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        source_event_id="SOURCE_INITIAL_001",
        source_event_ids=["SOURCE_INITIAL_001"],
        source_session_ids=["SESSION_001"],
        source_event_type=EventType.EXPLICIT_PREFERENCE,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        decision=ExtractionDecision.MEMORY_CANDIDATE,
        normalized_fact="I prefer calm acoustic music.",
        evidence_texts=[
            "I prefer calm acoustic music."
        ],
        entities=[],
        confidence=0.98,
        relevance_score=None,
        temporal_scope=TemporalScope.PERSISTENT,
        policy_class=PolicyClass.STANDARD,
        policy_flags=[],
        reason="Initial explicit preference.",
        evidence_count=1,
        explicit_evidence_count=1,
        behavioral_evidence_count=0
    )

    policy_request=PolicyRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        purpose="personalization",
        surface="chat",
        locale="en-IN",
        consent_state=ConsentState.OPTED_IN
    )

    initial_policy_decision=policy.evaluate(
        initial_candidate,
        policy_request
    )

    assert initial_policy_decision.decision==PolicyDecisionType.ALLOW

    initial_result=lifecycle.create_from_approved_candidate(
        initial_candidate,
        initial_policy_decision,
        datetime(
            2026,
            8,
            27,
            10,
            5,
            0,
            tzinfo=timezone.utc
        )
    )

    existing_memory_id=(
        initial_result.created_memory_id
        or initial_result.memory_id
    )

    assert existing_memory_id is not None

    existing_memory=lifecycle.store.get(
        existing_memory_id
    )

    assert existing_memory is not None
    assert existing_memory.status==MemoryStatus.ACTIVE

    orchestrator=MemoryControlOrchestrator(
        policy_consent_service=policy,
        lifecycle_service=lifecycle
    )

    command=MemoryCorrectionCommandV1(
        target_memory_id=existing_memory_id,
        corrected_statement="I prefer instrumental jazz.",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        session_id="SESSION_002",
        surface="chat",
        locale="en-IN",
        effective_at=datetime(
            2026,
            8,
            27,
            10,
            10,
            0,
            tzinfo=timezone.utc
        ),
        reason="User corrected the previous preference.",
        correlation_id="CORRECTION_001",
        metadata={
            "source":"test"
        }
    )

    result=orchestrator.process_memory_correction(
        command
    )

    assert result.target_memory_id==existing_memory_id
    assert result.extraction is not None
    assert result.extraction.candidates

    replacement_candidate=result.extraction.candidates[0]

    assert (
        replacement_candidate.normalized_fact
        =="I prefer instrumental jazz."
    )
    assert (
        replacement_candidate.memory_type
        ==MemoryType.EXPLICIT_PREFERENCE
    )
    assert (
        replacement_candidate.correction_target_memory_id
        ==existing_memory_id
    )

    assert result.policy_decision is not None
    assert (
        result.policy_decision.decision
        ==PolicyDecisionType.ALLOW
    )

    lifecycle_result=result.lifecycle_result

    assert (
        lifecycle_result.action
        ==MemoryLifecycleAction.CORRECT
    )
    assert (
        lifecycle_result.previous_memory_id
        ==existing_memory_id
    )
    assert lifecycle_result.created_memory_id is not None
    assert (
        lifecycle_result.created_memory_id
        !=existing_memory_id
    )

    old_memory=lifecycle.store.get(
        existing_memory_id
    )

    new_memory=lifecycle.store.get(
        lifecycle_result.created_memory_id
    )

    assert old_memory is not None
    assert new_memory is not None

    assert old_memory.status==MemoryStatus.CORRECTED
    assert old_memory.valid_to is not None
    assert old_memory.retrieval_eligible is False
    assert old_memory.embedding_eligible is False

    assert new_memory.status==MemoryStatus.ACTIVE
    assert new_memory.normalized_fact=="I prefer instrumental jazz."
    assert (
        new_memory.correction_of_memory_id
        ==existing_memory_id
    )
    assert new_memory.retrieval_eligible is True
    assert new_memory.embedding_eligible is True  

def test_write_orchestrator_adds_explicit_preference():
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    policy_service=PolicyConsentService(
        DefaultPolicyEngine()
    )

    consent_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            28,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="CONSENT_EXPLICIT_001"
    )

    policy_service.apply_consent_control(
        consent_request
    )

    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=policy_service,
        lifecycle_service=MemoryLifecycleService(
            lifecycle_store
        ),
        graph_service=GraphMemoryService(
            graph_store
        ),
        embedding_service=EmbeddingService(
            embedding_store
        )
    )

    effective_at=datetime(
        2026,
        8,
        28,
        10,
        5,
        0,
        tzinfo=timezone.utc
    )

    result=orchestrator.add_explicit_preference(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        session_id="SESSION_EXPLICIT_001",
        preference="I prefer instrumental jazz.",
        surface="chat",
        locale="en-IN",
        effective_at=effective_at,
        correlation_id="EXPLICIT_001",
        idempotency_key="IDEMP_EXPLICIT_001"
    )

    assert result.ingestion.status=="accepted"
    assert result.validation.status==ValidationStatus.VALID
    assert result.extraction.candidates
    assert result.policy_decisions
    assert result.policy_decisions[0].decision==PolicyDecisionType.ALLOW
    assert result.lifecycle_results
    assert result.graph_results
    assert result.embedding_results

    event=result.ingestion.event

    assert event.event_type==EventType.EXPLICIT_PREFERENCE
    assert event.subject_id=="TEST_USER_001"
    assert event.subject_scope=="TEST_USER_001"
    assert event.session_id=="SESSION_EXPLICIT_001"
    assert event.text=="I prefer instrumental jazz."
    assert event.source=="mcp"
    assert event.correlation_id=="EXPLICIT_001"
    assert event.idempotency_key=="IDEMP_EXPLICIT_001"

    lifecycle_result=result.lifecycle_results[0]

    memory_id=(
        lifecycle_result.created_memory_id
        or lifecycle_result.memory_id
    )

    assert memory_id is not None

    memory=lifecycle_store.get(memory_id)

    assert memory is not None
    assert memory.subject_id=="TEST_USER_001"
    assert memory.normalized_fact=="I prefer instrumental jazz."

def test_add_explicit_preference_rejects_subject_scope_mismatch():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="subject_scope must match subject_id"
    ):
        orchestrator.add_explicit_preference(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_999",
            session_id="SESSION_001",
            preference="I prefer jazz.",
            surface="chat",
            locale="en-IN",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0,
                tzinfo=timezone.utc
            )
        )

def test_add_explicit_preference_requires_subject_id():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="subject_id is required"
    ):
        orchestrator.add_explicit_preference(
            subject_id="",
            subject_scope="",
            session_id="SESSION_001",
            preference="I prefer jazz.",
            surface="chat",
            locale="en-IN",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0,
                tzinfo=timezone.utc
            )
        )


def test_add_explicit_preference_requires_session_id():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="session_id is required"
    ):
        orchestrator.add_explicit_preference(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id="",
            preference="I prefer jazz.",
            surface="chat",
            locale="en-IN",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0,
                tzinfo=timezone.utc
            )
        )


def test_add_explicit_preference_requires_preference():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="preference is required"
    ):
        orchestrator.add_explicit_preference(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id="SESSION_001",
            preference="",
            surface="chat",
            locale="en-IN",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0,
                tzinfo=timezone.utc
            )
        )


def test_add_explicit_preference_requires_surface():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="surface is required"
    ):
        orchestrator.add_explicit_preference(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id="SESSION_001",
            preference="I prefer jazz.",
            surface="",
            locale="en-IN",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0,
                tzinfo=timezone.utc
            )
        )


def test_add_explicit_preference_requires_locale():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="locale is required"
    ):
        orchestrator.add_explicit_preference(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id="SESSION_001",
            preference="I prefer jazz.",
            surface="chat",
            locale="",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0,
                tzinfo=timezone.utc
            )
        )

def test_add_explicit_preference_requires_timezone_aware_timestamp():
    orchestrator=MemoryWriteOrchestrator()

    with pytest.raises(
        OrchestrationError,
        match="effective_at must be timezone-aware"
    ):
        orchestrator.add_explicit_preference(
            subject_id="TEST_USER_001",
            subject_scope="TEST_USER_001",
            session_id="SESSION_001",
            preference="I prefer jazz.",
            surface="chat",
            locale="en-IN",
            effective_at=datetime(
                2026,
                8,
                28,
                10,
                0,
                0
            )
        )

def test_add_explicit_preference_respects_unknown_consent():
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()

    orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(),
        lifecycle_service=MemoryLifecycleService(
            lifecycle_store
        ),
        graph_service=GraphMemoryService(
            graph_store
        ),
        embedding_service=EmbeddingService(
            embedding_store
        )
    )

    result=orchestrator.add_explicit_preference(
        subject_id="TEST_USER_002",
        subject_scope="TEST_USER_002",
        session_id="SESSION_002",
        preference="I prefer jazz.",
        surface="chat",
        locale="en-IN",
        effective_at=datetime(
            2026,
            8,
            28,
            10,
            0,
            0,
            tzinfo=timezone.utc
        )
    )

    assert result.validation.status==ValidationStatus.VALID
    assert result.extraction.candidates
    assert result.policy_decisions
    assert result.policy_decisions[0].decision!=PolicyDecisionType.ALLOW
    assert result.lifecycle_results==[]
    assert result.graph_results==[]
    assert result.embedding_results==[]
    assert lifecycle_store.all()==[]

def test_query_orchestrator_explains_memory_use():
    lifecycle_store=InMemoryMemoryStore()
    lifecycle=MemoryLifecycleService(
        lifecycle_store
    )
    policy=PolicyConsentService(
        DefaultPolicyEngine()
    )

    consent_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            28,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="EXPLAIN_CONSENT_001"
    )

    policy.apply_consent_control(
        consent_request
    )

    candidate=ExtractedMemoryCandidate(
        candidate_id="candidate_explain_001",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        source_event_id="SOURCE_EXPLAIN_001",
        source_event_ids=["SOURCE_EXPLAIN_001"],
        source_session_ids=["SESSION_EXPLAIN_001"],
        source_event_type=EventType.EXPLICIT_PREFERENCE,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        decision=ExtractionDecision.MEMORY_CANDIDATE,
        normalized_fact="I prefer instrumental jazz.",
        evidence_texts=[
            "I prefer instrumental jazz."
        ],
        entities=[],
        confidence=0.98,
        relevance_score=None,
        temporal_scope=TemporalScope.PERSISTENT,
        policy_class=PolicyClass.STANDARD,
        policy_flags=[],
        reason="Explicit user preference.",
        evidence_count=1,
        explicit_evidence_count=1,
        behavioral_evidence_count=0
    )

    policy_request=PolicyRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        purpose="personalization",
        surface="chat",
        locale="en-IN",
        consent_state=ConsentState.OPTED_IN
    )

    policy_decision=policy.evaluate(
        candidate,
        policy_request
    )

    assert policy_decision.decision==PolicyDecisionType.ALLOW

    lifecycle_result=lifecycle.create_from_approved_candidate(
        candidate,
        policy_decision,
        datetime(
            2026,
            8,
            28,
            10,
            5,
            0,
            tzinfo=timezone.utc
        )
    )

    memory_id=(
        lifecycle_result.created_memory_id
        or lifecycle_result.memory_id
    )

    assert memory_id is not None

    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=RetrievalService(
            InMemoryRetrievalStore(
                InMemoryGraphStore(),
                InMemoryEmbeddingStore()
            )
        ),
        policy_consent_service=policy,
        context_service=ContextCompositionService(),
        response_service=make_response_service(),
        lifecycle_service=lifecycle
    )

    request=MemoryExplanationRequestV1(
        memory_id=memory_id,
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        current_intent="Why is this music recommendation relevant?",
        surface="chat",
        locale="en-IN",
        correlation_id="EXPLAIN_001"
    )

    result=orchestrator.explain_memory_use(
        request
    )

    assert result.memory_id==memory_id
    assert result.subject_id=="TEST_USER_001"
    assert result.explanation
    assert "stored for personalization" in result.explanation
    assert result.relevance_reason is not None
    assert result.confidence==0.98
    assert result.timestamp is not None

def test_query_orchestrator_explanation_rejects_wrong_subject():
    lifecycle_store=InMemoryMemoryStore()
    lifecycle=MemoryLifecycleService(
        lifecycle_store
    )
    policy=PolicyConsentService()

    owner_consent_request=ConsentControlRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            28,
            10,
            0,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="EXPLAIN_OWNER_CONSENT_001"
    )

    policy.apply_consent_control(
        owner_consent_request
    )

    wrong_subject_consent_request=ConsentControlRequestV1(
        subject_id="TEST_USER_999",
        subject_scope="TEST_USER_999",
        action=MemoryControlAction.OPT_IN,
        timestamp=datetime(
            2026,
            8,
            28,
            10,
            1,
            0,
            tzinfo=timezone.utc
        ),
        correlation_id="EXPLAIN_WRONG_SUBJECT_CONSENT_001"
    )

    policy.apply_consent_control(
        wrong_subject_consent_request
    )

    candidate=ExtractedMemoryCandidate(
        candidate_id="candidate_owner_001",
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        source_event_id="SOURCE_OWNER_001",
        source_event_ids=["SOURCE_OWNER_001"],
        source_session_ids=["SESSION_OWNER_001"],
        source_event_type=EventType.EXPLICIT_PREFERENCE,
        memory_type=MemoryType.EXPLICIT_PREFERENCE,
        decision=ExtractionDecision.MEMORY_CANDIDATE,
        normalized_fact="I prefer acoustic music.",
        evidence_texts=[
            "I prefer acoustic music."
        ],
        entities=[],
        confidence=0.95,
        relevance_score=None,
        temporal_scope=TemporalScope.PERSISTENT,
        policy_class=PolicyClass.STANDARD,
        policy_flags=[],
        reason="Explicit preference.",
        evidence_count=1,
        explicit_evidence_count=1,
        behavioral_evidence_count=0
    )

    policy_request=PolicyRequestV1(
        subject_id="TEST_USER_001",
        subject_scope="TEST_USER_001",
        purpose="personalization",
        surface="chat",
        locale="en-IN",
        consent_state=ConsentState.OPTED_IN
    )

    policy_decision=policy.evaluate(
        candidate,
        policy_request
    )

    lifecycle_result=lifecycle.create_from_approved_candidate(
        candidate,
        policy_decision,
        datetime(
            2026,
            8,
            28,
            10,
            5,
            0,
            tzinfo=timezone.utc
        )
    )

    memory_id=(
        lifecycle_result.created_memory_id
        or lifecycle_result.memory_id
    )

    assert memory_id is not None

    orchestrator=MemoryQueryOrchestrator(
        retrieval_service=RetrievalService(
            InMemoryRetrievalStore(
                InMemoryGraphStore(),
                InMemoryEmbeddingStore()
            )
        ),
        policy_consent_service=policy,
        context_service=ContextCompositionService(),
        response_service=make_response_service(),
        lifecycle_service=lifecycle
    )

    request=MemoryExplanationRequestV1(
        memory_id=memory_id,
        subject_id="TEST_USER_999",
        subject_scope="TEST_USER_999",
        current_intent=None,
        surface="chat",
        locale="en-IN",
        correlation_id="EXPLAIN_OWNER_001"
    )

    with pytest.raises(
        OrchestrationError,
        match="does not belong"
    ):
        orchestrator.explain_memory_use(
            request
        )                                          

