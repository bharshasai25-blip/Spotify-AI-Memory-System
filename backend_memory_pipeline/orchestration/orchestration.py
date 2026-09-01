from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from uuid import uuid4
from typing import Any,Optional,Protocol
from backend_memory_pipeline.ingestion.ingestion import IngestionService,IngestionResult,EventType,ConsentState,InteractionEventV1
from backend_memory_pipeline.event_validation.event_validation import EventValidator,EventValidationResult,ValidationStatus
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryExtractionService,MemoryExtractionResult,ExtractedMemoryCandidate,ExtractionDecision
from backend_memory_pipeline.entity_resolution.entity_resolution import EntityResolutionService,EntityResolutionResultV1
from backend_memory_pipeline.policy_consent.policy_consent import PolicyConsentService,PolicyDecisionType,PolicyDecisionV1,PolicyRequestV1,ConsentControlRequestV1,ConsentControlResultV1
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryLifecycleService,MemoryLifecycleResultV1,MemoryLifecycleRequestV1,MemoryLifecycleAction
from backend_memory_pipeline.graph_memory.graph import GraphMemoryService,GraphWriteResultV1
from backend_memory_pipeline.embedding.embedding import EmbeddingService,EmbeddingWriteResultV1
from backend_memory_pipeline.retrieval.retrieval import RetrievalService,RetrievalRequestV1,RetrievalResultV1,RetrievalDecision
from backend_memory_pipeline.context_composition.context_composition import ContextCompositionService,ContextCompositionRequestV1,ContextCompositionResultV1
from backend_memory_pipeline.response_generation.response_generation import ResponseGenerationService,ResponseGenerationRequestV1,GeneratedResponseV1
class OrchestrationError(Exception):
    pass
class EvidenceHistoryStore(Protocol):
    def get(self,subject_id:str)->list[InteractionEventV1]:
        ...
    def append(self,event:InteractionEventV1)->None:
        ...
class InMemoryEvidenceHistoryStore:
    def __init__(self,max_events_per_subject:int=100):
        self.max_events_per_subject=max_events_per_subject
        self._history:dict[str,list[InteractionEventV1]]={}
    def get(self,subject_id:str)->list[InteractionEventV1]:
        return list(self._history.get(subject_id,[]))
    def append(self,event:InteractionEventV1)->None:
        history=self._history.setdefault(event.subject_id,[])
        history.append(event)
        if len(history)>self.max_events_per_subject:
            del history[:-self.max_events_per_subject]
    def clear(self,subject_id:Optional[str]=None)->None:
        if subject_id is None:
            self._history.clear()
        else:
            self._history.pop(subject_id,None)
@lru_cache(maxsize=1)
def get_evidence_history_store()->InMemoryEvidenceHistoryStore:
    return InMemoryEvidenceHistoryStore()
@dataclass(frozen=True)
class MemoryWriteResultV1:
    ingestion:IngestionResult
    validation:EventValidationResult
    extraction:MemoryExtractionResult
    entity_resolution:Optional[EntityResolutionResultV1]
    policy_decisions:list[PolicyDecisionV1]
    lifecycle_results:list[MemoryLifecycleResultV1]
    graph_results:list[GraphWriteResultV1]
    embedding_results:list[EmbeddingWriteResultV1]
@dataclass(frozen=True)
class MemoryQueryResultV1:
    retrieval:RetrievalResultV1
    context:ContextCompositionResultV1
    response:GeneratedResponseV1
@dataclass(frozen=True)
class MemoryExplanationRequestV1:
    memory_id:str
    subject_id:str
    subject_scope:str
    current_intent:Optional[str]
    surface:str
    locale:str
    correlation_id:str
@dataclass(frozen=True)
class MemoryExplanationResultV1:
    memory_id:str
    subject_id:str
    explanation:str
    relevance_reason:Optional[str]
    source:Optional[str]
    confidence:Optional[float]
    timestamp:Optional[datetime]
@dataclass(frozen=True)
class MemoryControlResultV1:
    consent_state:Optional[ConsentControlResultV1]
    lifecycle_result:Optional[MemoryLifecycleResultV1]
@dataclass(frozen=True)
class MemoryCorrectionCommandV1:
    target_memory_id:str
    corrected_statement:str
    subject_id:str
    subject_scope:str
    session_id:str
    surface:str
    locale:str
    effective_at:datetime
    reason:str
    correlation_id:str
    metadata:dict[str,Any]
@dataclass(frozen=True)
class MemoryCorrectionResultV1:
    target_memory_id:str
    extraction:MemoryExtractionResult
    entity_resolution:Optional[EntityResolutionResultV1]
    policy_decision:PolicyDecisionV1
    lifecycle_result:MemoryLifecycleResultV1
    graph_result:Optional[GraphWriteResultV1]
    embedding_result:Optional[EmbeddingWriteResultV1]
class MemoryWriteOrchestrator:
    def __init__(
        self,
        ingestion_service:Optional[IngestionService]=None,
        event_validator:Optional[EventValidator]=None,
        extraction_service:Optional[MemoryExtractionService]=None,
        entity_resolution_service:Optional[EntityResolutionService]=None,
        policy_consent_service:Optional[PolicyConsentService]=None,
        lifecycle_service:Optional[MemoryLifecycleService]=None,
        graph_service:Optional[GraphMemoryService]=None,
        embedding_service:Optional[EmbeddingService]=None,
        evidence_history_store:Optional[EvidenceHistoryStore]=None
    ):
        self.ingestion=ingestion_service or IngestionService()
        self.validator=event_validator or EventValidator()
        self.extractor=extraction_service or MemoryExtractionService()
        self.entity_resolver=entity_resolution_service
        self.policy_consent=policy_consent_service or PolicyConsentService()
        self.lifecycle=lifecycle_service or MemoryLifecycleService()
        self.graph=graph_service or GraphMemoryService()
        self.embedding=embedding_service or EmbeddingService()
        self.evidence_history=evidence_history_store or get_evidence_history_store()
    def process_event(
        self,
        data:dict[str,Any],
        authorized_subject_id:Optional[str]=None,
        policy_request:Optional[PolicyRequestV1]=None
    )->MemoryWriteResultV1:
        try:
            ingestion_result=self.ingestion.ingest_mapping(
                data,
                authorized_subject_id=authorized_subject_id
            )
        except Exception as exc:
            raise OrchestrationError(f"Ingestion failed: {exc}") from exc
        event=ingestion_result.event
        try:
            validation_result=self.validator.validate(event)
        except Exception as exc:
            raise OrchestrationError(f"Event validation failed: {exc}") from exc
        if validation_result.status!=ValidationStatus.VALID:
            self.evidence_history.append(event)
            return MemoryWriteResultV1(
                ingestion=ingestion_result,
                validation=validation_result,
                extraction=MemoryExtractionResult(
                    event_id=event.event_id,
                    subject_id=event.subject_id,
                    decision=ExtractionDecision.NO_MEMORY,
                    candidates=[],
                    source_event_id=event.source_event_id,
                    evidence_event_ids=[],
                    evidence_session_ids=[],
                    no_memory_reason="Event failed validation."
                ),
                entity_resolution=None,
                policy_decisions=[],
                lifecycle_results=[],
                graph_results=[],
                embedding_results=[])
        history=self.evidence_history.get(event.subject_id)
        try:
            extraction_result=self.extractor.extract(
                event,
                evidence_history=history,
                validation_result=validation_result
            )
        except Exception as exc:
            raise OrchestrationError(f"Memory extraction failed: {exc}") from exc
        if not extraction_result.candidates:
            self.evidence_history.append(event)
            return MemoryWriteResultV1(
                ingestion=ingestion_result,
                validation=validation_result,
                extraction=extraction_result,
                entity_resolution=None,
                policy_decisions=[],
                lifecycle_results=[],
                graph_results=[],
                embedding_results=[]
            )
        entity_result=None
        if self.entity_resolver is not None:
            try:
                entity_result=self.entity_resolver.resolve(
                    extraction_result.candidates
                )
            except Exception as exc:
                raise OrchestrationError(f"Entity resolution failed: {exc}") from exc
            extraction_result=self._apply_entity_resolution_to_result(
                extraction_result,
                entity_result
            )
        if policy_request is None:
            policy_request=self._build_policy_request(event)
        policy_decisions=[]
        lifecycle_results=[]
        graph_results=[]
        embedding_results=[]
        for candidate in extraction_result.candidates:
            candidate_entity_result=entity_result
            try:
                policy_decision=self.policy_consent.evaluate(
                    candidate,
                    policy_request,
                    candidate_entity_result
                )
            except Exception as exc:
                raise OrchestrationError(f"Policy evaluation failed: {exc}") from exc
            policy_decisions.append(policy_decision)
            if policy_decision.decision!=PolicyDecisionType.ALLOW:
                continue
            try:
                lifecycle_result=self.lifecycle.create_from_approved_candidate(
                    candidate,
                    policy_decision,
                    event.timestamp
                )
            except Exception as exc:
                raise OrchestrationError(f"Memory lifecycle failed: {exc}") from exc
            lifecycle_results.append(lifecycle_result)
            memory_id=lifecycle_result.created_memory_id or lifecycle_result.memory_id
            if memory_id is None:
                continue
            memory=self.lifecycle.store.get(memory_id)
            if memory is None:
                raise OrchestrationError(
                    f"Created memory {memory_id} could not be loaded."
                )
            try:
                graph_result=self.graph.upsert_memory(memory)
            except Exception as exc:
                raise OrchestrationError(f"Graph synchronization failed: {exc}") from exc
            graph_results.append(graph_result)
            if memory.embedding_eligible:
                try:
                    embedding_result=self.embedding.upsert_memory_embedding(memory)
                except Exception as exc:
                    raise OrchestrationError(
                        f"Embedding synchronization failed: {exc}"
                    ) from exc
                embedding_results.append(embedding_result)
        self.evidence_history.append(event)
        return MemoryWriteResultV1(
            ingestion=ingestion_result,
            validation=validation_result,
            extraction=extraction_result,
            entity_resolution=entity_result,
            policy_decisions=policy_decisions,
            lifecycle_results=lifecycle_results,
            graph_results=graph_results,
            embedding_results=embedding_results
        )
    @staticmethod
    def _build_policy_request(event:InteractionEventV1)->PolicyRequestV1:
        return PolicyRequestV1(
            subject_id=event.subject_id,
            subject_scope=event.subject_scope,
            purpose="personalization",
            surface=event.surface,
            locale=event.locale,
            consent_state=event.consent_state
        )
    @staticmethod
    def _apply_entity_resolution_to_result(
        extraction_result:MemoryExtractionResult,
        resolution:EntityResolutionResultV1
    )->MemoryExtractionResult:
        resolved_by_mention={
            item.mention:item
            for item in resolution.resolved_entities
        }
        updated_candidates=[]
        for candidate in extraction_result.candidates:
            updated_entities=[]
            for mention in candidate.entities:
                resolved=resolved_by_mention.get(mention.mention)
                if resolved is None:
                    updated_entities.append(mention)
                    continue
                updated_entities.append(
                    mention.model_copy(
                        update={
                            "canonical_id":resolved.canonical_id,
                            "resolution_status":resolved.resolution_status.value
                        }
                    )
                )
            updated_candidate=candidate.model_copy(
                update={"entities":updated_entities}
            )
            updated_candidates.append(updated_candidate)
        return extraction_result.model_copy(
            update={"candidates":updated_candidates}
        )
class MemoryQueryOrchestrator:
    def __init__(
        self,
        retrieval_service:RetrievalService,
        policy_consent_service:Optional[PolicyConsentService]=None,
        context_service:Optional[ContextCompositionService]=None,
        response_service:Optional[ResponseGenerationService]=None,
        lifecycle_service:Optional[MemoryLifecycleService]=None
    ):
        self.retrieval=retrieval_service
        self.policy_consent=policy_consent_service or PolicyConsentService()
        self.context=context_service or ContextCompositionService()
        self.response=response_service or ResponseGenerationService()
        self.lifecycle=lifecycle_service
    def process_query(
        self,
        retrieval_request:RetrievalRequestV1,
        context_request:ContextCompositionRequestV1,
        response_request:ResponseGenerationRequestV1
    )->MemoryQueryResultV1:
        try:
            consent_record=self.policy_consent.get_consent_state(
                retrieval_request.subject_id
            )
        except Exception as exc:
            raise OrchestrationError(f"Consent lookup failed: {exc}") from exc
        consent_state=consent_record.state
        if not self._memory_access_allowed(consent_state):
            retrieval_result=self._no_memory_retrieval_result(
                retrieval_request,
                consent_state
            )
        else:
            try:
                retrieval_result=self.retrieval.retrieve(
                    retrieval_request
                )
            except Exception as exc:
                raise OrchestrationError(f"Retrieval failed: {exc}") from exc
        try:
            context_result=self.context.compose(
                retrieval_result,
                context_request
            )
        except Exception as exc:
            raise OrchestrationError(
                f"Context composition failed: {exc}"
            ) from exc
        try:
            response_result=self.response.generate(
                context_result,
                response_request
            )
        except Exception as exc:
            raise OrchestrationError(
                f"Response generation failed: {exc}"
            ) from exc
        return MemoryQueryResultV1(
            retrieval=retrieval_result,
            context=context_result,
            response=response_result
        )
    def retrieve_memory(
        self,
        retrieval_request:RetrievalRequestV1
    )->RetrievalResultV1:
        try:
            consent_record=self.policy_consent.get_consent_state(
                retrieval_request.subject_id
            )
        except Exception as exc:
            raise OrchestrationError(f"Consent lookup failed: {exc}") from exc
        if not self._memory_access_allowed(consent_record.state):
            return self._no_memory_retrieval_result(
                retrieval_request,
                consent_record.state
            )
        try:
            return self.retrieval.retrieve(retrieval_request)
        except Exception as exc:
            raise OrchestrationError(f"Retrieval failed: {exc}") from exc
    def explain_memory_use(
        self,
        request:MemoryExplanationRequestV1
    )->MemoryExplanationResultV1:
        if not request.memory_id.strip():
            raise OrchestrationError("memory_id is required.")
        if not request.subject_id.strip():
            raise OrchestrationError("subject_id is required.")
        if request.subject_id!=request.subject_scope:
            raise OrchestrationError("subject_scope must match subject_id.")
        try:
            consent_record=self.policy_consent.get_consent_state(
                request.subject_id
            )
        except Exception as exc:
            raise OrchestrationError(f"Consent lookup failed: {exc}") from exc
        if not self._memory_access_allowed(consent_record.state):
            raise OrchestrationError(
                "Memory access is not permitted by the current consent state."
            )
        if self.lifecycle is None:
            raise OrchestrationError(
                "Memory lifecycle service is required for explain_memory_use()."
            )
        memory=self.lifecycle.store.get(request.memory_id)
        if memory is None:
            raise OrchestrationError(
                f"Memory {request.memory_id} was not found."
            )
        if (
            memory.subject_id!=request.subject_id
            or memory.subject_scope!=request.subject_scope
        ):
            raise OrchestrationError(
                "Memory does not belong to the requested subject."
            )
        relevance_reason=None
        if request.current_intent:
            relevance_reason=(
                "Memory was retrieved because it is available for the requested "
                "subject and may be relevant to the current intent."
            )
        explanation=(
            "This memory was stored for personalization because it was accepted "
            "by the memory policy and consent rules. The stored memory is: "
            f"'{memory.normalized_fact}'."
        )
        return MemoryExplanationResultV1(
            memory_id=memory.memory_id,
            subject_id=memory.subject_id,
            explanation=explanation,
            relevance_reason=relevance_reason,
            source=(
                memory.metadata.get("source")
                if isinstance(memory.metadata,dict)
                else None
            ),
            confidence=memory.confidence,
            timestamp=memory.recorded_at
        )
    @staticmethod
    def _memory_access_allowed(consent_state:ConsentState)->bool:
        return consent_state==ConsentState.OPTED_IN
    @staticmethod
    def _no_memory_retrieval_result(
        request:RetrievalRequestV1,
        consent_state:ConsentState
    )->RetrievalResultV1:
        return RetrievalResultV1(
            decision=RetrievalDecision.NO_RESULTS,
            subject_id=request.subject_id,
            query_intent=request.intent,
            candidates=[],
            candidate_count=0,
            graph_candidate_count=0,
            vector_candidate_count=0,
            returned_count=0,
            retrieval_version="1.0",
            provenance={
                "memory_access_allowed":False,
                "consent_state":consent_state.value,
                "reason":"Memory retrieval is not permitted."
            }
        )
class MemoryControlOrchestrator:
    def __init__(
        self,
        policy_consent_service:Optional[PolicyConsentService]=None,
        lifecycle_service:Optional[MemoryLifecycleService]=None,
        extraction_service:Optional[MemoryExtractionService]=None,
        event_validator:Optional[EventValidator]=None,
        ingestion_service:Optional[IngestionService]=None,
        entity_resolution_service:Optional[EntityResolutionService]=None,
        graph_service:Optional[GraphMemoryService]=None,
        embedding_service:Optional[EmbeddingService]=None
    ):
        self.policy_consent=policy_consent_service or PolicyConsentService()
        self.lifecycle=lifecycle_service or MemoryLifecycleService()
        self.extractor=extraction_service or MemoryExtractionService()
        self.entity_resolver=entity_resolution_service
        self.validator=event_validator or EventValidator()
        self.ingestion=ingestion_service or IngestionService()
        self.graph=graph_service
        self.embedding=embedding_service
    def apply_consent_control(
        self,
        request:ConsentControlRequestV1
    )->MemoryControlResultV1:
        try:
            consent_result=self.policy_consent.apply_consent_control(request)
        except Exception as exc:
            raise OrchestrationError(
                f"Consent control failed: {exc}"
            ) from exc
        return MemoryControlResultV1(
            consent_state=consent_result,
            lifecycle_result=None
        )
    def process_memory_correction(
        self,
        command:MemoryCorrectionCommandV1
    )->MemoryCorrectionResultV1:
        if not isinstance(command,MemoryCorrectionCommandV1):
            raise OrchestrationError(
                "Input must be a MemoryCorrectionCommandV1."
            )
        if not command.target_memory_id.strip():
            raise OrchestrationError("target_memory_id is required.")
        if not command.corrected_statement.strip():
            raise OrchestrationError("corrected_statement is required.")
        if not command.subject_id.strip():
            raise OrchestrationError("subject_id is required.")
        if command.subject_id!=command.subject_scope:
            raise OrchestrationError("subject_scope must match subject_id.")
        if not command.session_id.strip():
            raise OrchestrationError("session_id is required.")
        if (
            command.effective_at.tzinfo is None
            or command.effective_at.utcoffset() is None
        ):
            raise OrchestrationError(
                "effective_at must be timezone-aware."
            )
        if not command.reason.strip():
            raise OrchestrationError("reason is required.")
        target_memory=self.lifecycle.store.get(command.target_memory_id)
        if target_memory is None:
            raise OrchestrationError(
                f"Memory {command.target_memory_id} was not found."
            )
        if (
            target_memory.subject_id!=command.subject_id
            or target_memory.subject_scope!=command.subject_scope
        ):
            raise OrchestrationError(
                "Memory does not belong to the requested subject."
            )
        try:
            consent_record=self.policy_consent.get_consent_state(
                command.subject_id
            )
        except Exception as exc:
            raise OrchestrationError(
                f"Consent lookup failed: {exc}"
            ) from exc
        if consent_record.state!=ConsentState.OPTED_IN:
            raise OrchestrationError(
                "Memory correction is not permitted by the current consent state."
            )
        event_id=IngestionService.new_event_id()
        source_event_id=IngestionService.new_source_event_id()
        correction_event={
            "event_id":event_id,
            "source_event_id":source_event_id,
            "subject_id":command.subject_id,
            "subject_scope":command.subject_scope,
            "session_id":command.session_id,
            "event_type":EventType.EXPLICIT_PREFERENCE,
            "source":"mcp",
            "surface":command.surface,
            "locale":command.locale,
            "timestamp":command.effective_at,
            "consent_state":consent_record.state,
            "idempotency_key":str(uuid4()),
            "correlation_id":command.correlation_id,
            "text":command.corrected_statement.strip(),
            "entity":None,
            "context_entities":{},
            "metadata":{
                **command.metadata,
                "correction_target_memory_id":command.target_memory_id,
                "correction_reason":command.reason
            }
        }
        try:
            canonical_event=self.ingestion.ingest_mapping(
                correction_event
            ).event
        except Exception as exc:
            raise OrchestrationError(
                f"Correction event construction failed: {exc}"
            ) from exc
        try:
            validation_result=self.validator.validate(canonical_event)
        except Exception as exc:
            raise OrchestrationError(
                f"Correction event validation failed: {exc}"
            ) from exc
        if validation_result.status!=ValidationStatus.VALID:
            raise OrchestrationError(
                "Correction event failed event validation."
            )
        try:
            extraction_result=self.extractor.extract(
                canonical_event,
                evidence_history=[],
                validation_result=validation_result
            )
        except Exception as exc:
            raise OrchestrationError(
                f"Memory correction extraction failed: {exc}"
            ) from exc
        if not extraction_result.candidates:
            raise OrchestrationError(
                "Corrected statement did not produce a replacement memory candidate."
            )
        replacement_candidate=extraction_result.candidates[0]
        replacement_candidate=replacement_candidate.model_copy(
            update={
                "correction_target_memory_id":command.target_memory_id
            }
        )
        entity_result=None
        if self.entity_resolver is not None:
            try:
                entity_result=self.entity_resolver.resolve(
                    replacement_candidate
                )
            except Exception as exc:
                raise OrchestrationError(
                    f"Memory correction entity resolution failed: {exc}"
                ) from exc
            replacement_candidate=self._apply_entity_resolution(
                replacement_candidate,
                entity_result
            )
        policy_request=PolicyRequestV1(
            subject_id=command.subject_id,
            subject_scope=command.subject_scope,
            purpose="personalization",
            surface=command.surface,
            locale=command.locale,
            consent_state=consent_record.state
        )
        try:
            policy_decision=self.policy_consent.evaluate(
                replacement_candidate,
                policy_request,
                entity_result
            )
        except Exception as exc:
            raise OrchestrationError(
                f"Memory correction policy evaluation failed: {exc}"
            ) from exc
        if policy_decision.decision!=PolicyDecisionType.ALLOW:
            raise OrchestrationError(
                "Corrected memory was not approved by policy."
            )
        lifecycle_request=MemoryLifecycleRequestV1(
            action=MemoryLifecycleAction.CORRECT,
            subject_id=command.subject_id,
            subject_scope=command.subject_scope,
            target_memory_id=command.target_memory_id,
            effective_at=command.effective_at,
            reason=command.reason,
            correlation_id=command.correlation_id,
            metadata={
                **command.metadata,
                "source":"mcp",
                "source_event_id":source_event_id
            }
        )
        try:
            lifecycle_result=self.lifecycle.correct(
                lifecycle_request,
                replacement_candidate,
                policy_decision
            )
        except Exception as exc:
            raise OrchestrationError(
                f"Memory correction lifecycle failed: {exc}"
            ) from exc
        graph_result=None
        embedding_result=None
        new_memory_id=(
            lifecycle_result.created_memory_id
            or lifecycle_result.memory_id
        )
        if new_memory_id is not None:
            memory=self.lifecycle.store.get(new_memory_id)
            if memory is None:
                raise OrchestrationError(
                    f"Corrected memory {new_memory_id} could not be loaded."
                )
            if self.graph is not None:
                try:
                    graph_result=self.graph.upsert_memory(memory)
                except Exception as exc:
                    raise OrchestrationError(
                        f"Corrected memory graph synchronization failed: {exc}"
                    ) from exc
            if self.embedding is not None and memory.embedding_eligible:
                try:
                    embedding_result=self.embedding.upsert_memory_embedding(
                        memory
                    )
                except Exception as exc:
                    raise OrchestrationError(
                        f"Corrected memory embedding synchronization failed: {exc}"
                    ) from exc
        return MemoryCorrectionResultV1(
            target_memory_id=command.target_memory_id,
            extraction=MemoryExtractionResult(
                event_id=extraction_result.event_id,
                subject_id=extraction_result.subject_id,
                decision=extraction_result.decision,
                candidates=[replacement_candidate],
                source_event_id=extraction_result.source_event_id,
                evidence_event_ids=extraction_result.evidence_event_ids,
                evidence_session_ids=extraction_result.evidence_session_ids,
                detected_language=extraction_result.detected_language,
                no_memory_reason=extraction_result.no_memory_reason
            ),
            entity_resolution=entity_result,
            policy_decision=policy_decision,
            lifecycle_result=lifecycle_result,
            graph_result=graph_result,
            embedding_result=embedding_result
        )
    @staticmethod
    def _apply_entity_resolution(
        candidate:ExtractedMemoryCandidate,
        resolution:EntityResolutionResultV1
    )->ExtractedMemoryCandidate:
        resolved_by_mention={
            item.mention:item
            for item in resolution.resolved_entities
        }
        updated_entities=[]
        for mention in candidate.entities:
            resolved=resolved_by_mention.get(mention.mention)
            if resolved is None:
                updated_entities.append(mention)
                continue
            updated_entities.append(
                mention.model_copy(
                    update={
                        "canonical_id":resolved.canonical_id,
                        "resolution_status":resolved.resolution_status.value
                    }
                )
            )
        return candidate.model_copy(
            update={"entities":updated_entities}
        )
    def apply_lifecycle_action(
        self,
        request:MemoryLifecycleRequestV1,
        new_candidate:Optional[ExtractedMemoryCandidate]=None,
        policy_decision:Optional[PolicyDecisionV1]=None,
        changes:Optional[dict[str,Any]]=None
    )->MemoryControlResultV1:
        if not isinstance(request,MemoryLifecycleRequestV1):
            raise OrchestrationError(
                "Input must be a MemoryLifecycleRequestV1."
            )
        try:
            if request.action==MemoryLifecycleAction.DELETE:
                result=self.lifecycle.delete(request)
            elif request.action==MemoryLifecycleAction.EXPIRE:
                result=self.lifecycle.expire(request)
            elif request.action==MemoryLifecycleAction.RETAIN:
                result=self.lifecycle.retain(request)
            elif request.action==MemoryLifecycleAction.UPDATE:
                result=self.lifecycle.update(
                    request,
                    changes or {}
                )
            elif request.action==MemoryLifecycleAction.SUPERSEDE:
                if new_candidate is None or policy_decision is None:
                    raise OrchestrationError(
                        "Supersede requires new_candidate and policy_decision."
                    )
                result=self.lifecycle.supersede(
                    request,
                    new_candidate,
                    policy_decision
                )
            elif request.action==MemoryLifecycleAction.CORRECT:
                if new_candidate is None or policy_decision is None:
                    raise OrchestrationError(
                        "Correct requires new_candidate and policy_decision."
                    )
                result=self.lifecycle.correct(
                    request,
                    new_candidate,
                    policy_decision
                )
            else:
                raise OrchestrationError(
                    f"Unsupported lifecycle action: {request.action.value}"
                )
        except Exception as exc:
            if isinstance(exc,OrchestrationError):
                raise
            raise OrchestrationError(
                f"Lifecycle orchestration failed: {exc}"
            ) from exc
        return MemoryControlResultV1(
            consent_state=None,
            lifecycle_result=result
        )