from datetime import datetime,timezone
from backend_memory_pipeline.embedding.embedding import (
    EmbeddingService,
    InMemoryEmbeddingStore,
    DeterministicEmbeddingProvider,
)
from backend_memory_pipeline.event_validation.event_validation import EventValidator
from backend_memory_pipeline.graph_memory.graph import (
    GraphMemoryService,
    InMemoryGraphStore,
)
from backend_memory_pipeline.ingestion.ingestion import IngestionService
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryExtractionService
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    InMemoryMemoryStore,
    MemoryLifecycleService,
)
from backend_memory_pipeline.orchestration.orchestration import MemoryWriteOrchestrator
from backend_memory_pipeline.policy_consent.policy_consent import (
    DefaultPolicyEngine,
    PolicyConsentService,
)
from backend_memory_pipeline.retrieval.retrieval import (
    InMemoryRetrievalStore,
    RetrievalRequestV1,
    RetrievalService,
    DeterministicQueryEmbeddingProvider,
)
def test_written_memory_is_visible_to_retrieval_through_shared_stores():
    """
    Verify that a memory written by MemoryWriteOrchestrator
    is available to RetrievalService through the same graph
    and embedding stores.
    """
    lifecycle_store=InMemoryMemoryStore()
    graph_store=InMemoryGraphStore()
    embedding_store=InMemoryEmbeddingStore()
    lifecycle_service=MemoryLifecycleService(lifecycle_store)
    graph_service=GraphMemoryService(graph_store)
    embedding_service=EmbeddingService(
        store=embedding_store,
        provider=DeterministicEmbeddingProvider(),
    )
    policy_service=PolicyConsentService(DefaultPolicyEngine())
    write_orchestrator=MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=policy_service,
        lifecycle_service=lifecycle_service,
        graph_service=graph_service,
        embedding_service=embedding_service,
    )
    retrieval_store=InMemoryRetrievalStore(
        graph_store=graph_store,
        embedding_store=embedding_store,
    )
    retrieval_service=RetrievalService(
        retrieval_store=retrieval_store,
        query_provider=DeterministicQueryEmbeddingProvider(),
    )
    requested_at=datetime.now(timezone.utc)
    event={
        "event_id":"EVENT_INTEGRATION_001",
        "source_event_id":"SOURCE_EVENT_INTEGRATION_001",
        "subject_id":"USER_001",
        "subject_scope":"USER_001",
        "session_id":"SESSION_INTEGRATION_001",
        "event_type":"explicit_preference",
        "source":"chat",
        "surface":"chat",
        "locale":"en-US",
        "timestamp":requested_at,
        "consent_state":"opted_in",
        "idempotency_key":"IDEMPOTENCY_INTEGRATION_001",
        "text":"I prefer calm acoustic music.",
        "entity":None,
        "context_entities":{},
        "metadata":{},
    }
    write_result=write_orchestrator.process_event(
        event,
        authorized_subject_id="USER_001",
    )
    assert write_result.validation.status.value=="valid"
    assert len(write_result.lifecycle_results)>=1
    assert len(write_result.graph_results)>=1
    assert len(write_result.embedding_results)>=1
    memory_id=(
        write_result.lifecycle_results[0].created_memory_id
        or write_result.lifecycle_results[0].memory_id
    )
    assert memory_id is not None
    graph_memory=graph_store.get_memory(memory_id)
    assert graph_memory is not None
    assert graph_memory.memory_id==memory_id
    assert graph_memory.subject_id=="USER_001"
    assert graph_memory.subject_scope=="USER_001"
    embedding=embedding_store.get(memory_id)
    assert embedding is not None
    assert embedding.memory_id==memory_id
    assert embedding.subject_id=="USER_001"
    assert embedding.subject_scope=="USER_001"
    assert embedding.dimensions==384
    retrieval_request=RetrievalRequestV1(
        subject_id="USER_001",
        subject_scope="USER_001",
        intent="calm acoustic music",
        surface="chat",
        locale="en-US",
        requested_at=requested_at,
        top_k=5,
        candidate_limit=50,
        vector_weight=0.55,
        graph_weight=0.45,
        min_score=0.0,
        metadata={"integration_test":True},
    )
    retrieval_result=retrieval_service.retrieve(retrieval_request)
    assert retrieval_result.decision.value=="retrieved"
    retrieved_memory_ids={
        candidate.memory_id
        for candidate in retrieval_result.candidates
    }
    assert memory_id in retrieved_memory_ids