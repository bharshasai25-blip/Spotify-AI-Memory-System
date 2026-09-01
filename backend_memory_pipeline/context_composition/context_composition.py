from datetime import datetime
from enum import Enum
import math
from typing import Any,Optional,Protocol
from pydantic import BaseModel,ConfigDict,Field,model_validator
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryStatus
from backend_memory_pipeline.retrieval.retrieval import RetrievalCandidateV1,RetrievalResultV1,RetrievalDecision
class ContextDecision(str,Enum):
    COMPOSED="composed"
    NO_CONTEXT="no_context"
class ContextExclusionReason(str,Enum):
    DUPLICATE="duplicate"
    CONFLICTING_MEMORY="conflicting_memory"
    BUDGET_EXCEEDED="budget_exceeded"
    INELIGIBLE_STATUS="ineligible_status"
    INVALID_CANDIDATE="invalid_candidate"
class ContextCompositionErrorCode(str,Enum):
    INVALID_RETRIEVAL_RESULT="INVALID_RETRIEVAL_RESULT"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    INVALID_CANDIDATE="INVALID_CANDIDATE"
    INVALID_BUDGET="INVALID_BUDGET"
    CONTEXT_CONFLICT="CONTEXT_CONFLICT"
class ContextCompositionError(Exception):
    def __init__(self,code:ContextCompositionErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class ContextCompositionRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    requested_at:datetime
    max_items:int=Field(default=5,ge=1,le=50)
    max_characters:int=Field(default=12000,ge=100,le=100000)
    max_tokens:int=Field(default=3000,ge=1,le=20000)
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_request(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware.")
        return self
class ContextItemV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    memory_type:str=Field(min_length=1,max_length=128)
    content:str=Field(min_length=1,max_length=10000)
    rank:int=Field(ge=1)
    relevance_score:float=Field(ge=0.0,le=1.0)
    confidence:float=Field(ge=0.0,le=1.0)
    recorded_at:datetime
    valid_from:datetime
    valid_to:Optional[datetime]=None
    source_event_ids:list[str]=Field(default_factory=list)
    source_session_ids:list[str]=Field(default_factory=list)
    provenance:dict[str,Any]=Field(default_factory=dict)
class ContextExclusionV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    reason:ContextExclusionReason
    details:str=Field(min_length=1,max_length=2000)
class ContextCompositionResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    decision:ContextDecision
    subject_id:str
    query_intent:str
    items:list[ContextItemV1]=Field(default_factory=list)
    exclusions:list[ContextExclusionV1]=Field(default_factory=list)
    item_count:int=Field(ge=0)
    character_count:int=Field(ge=0)
    estimated_token_count:int=Field(ge=0)
    composition_version:str="1.0"
    provenance:dict[str,Any]=Field(default_factory=dict)
class ContextComposer(Protocol):
    def compose(self,retrieval_result:RetrievalResultV1,request:ContextCompositionRequestV1)->ContextCompositionResultV1:
        ...
class ContextCompositionService:
    def __init__(self,composer:Optional[ContextComposer]=None,composition_version:str="1.0"):
        self.composer=composer or RuleBasedContextComposer(composition_version)
    def compose(self,retrieval_result:RetrievalResultV1,request:ContextCompositionRequestV1)->ContextCompositionResultV1:
        return self.composer.compose(retrieval_result,request)
class RuleBasedContextComposer:
    def __init__(self,composition_version:str="1.0"):
        self.composition_version=composition_version
    def compose(self,retrieval_result:RetrievalResultV1,request:ContextCompositionRequestV1)->ContextCompositionResultV1:
        self._validate_input(retrieval_result,request)
        if retrieval_result.decision==RetrievalDecision.NO_RESULTS:
            return ContextCompositionResultV1(
                decision=ContextDecision.NO_CONTEXT,
                subject_id=request.subject_id,
                query_intent=retrieval_result.query_intent,
                items=[],
                exclusions=[],
                item_count=0,
                character_count=0,
                estimated_token_count=0,
                composition_version=self.composition_version,
                provenance={
                    "retrieval_version":retrieval_result.retrieval_version,
                    "reason":"Retrieval returned no eligible memories."
                }
            )
        if not retrieval_result.candidates:
            return ContextCompositionResultV1(
               decision=ContextDecision.NO_CONTEXT,
               subject_id=request.subject_id,
               query_intent=retrieval_result.query_intent,
               items=[],
               exclusions=[],
               item_count=0,
               character_count=0,
               estimated_token_count=0,
               composition_version=self.composition_version,
               provenance={
                   "retrieval_version":retrieval_result.retrieval_version,
                   "reason":"Retrieval result contained no candidates."
                }
           )        
        selected=[]
        exclusions=[]
        seen_facts:set[str]=set()
        selected_types:dict[str,int]={}
        character_count=0
        token_count=0
        ordered_candidates=self._order_candidates(retrieval_result.candidates)
        for candidate in ordered_candidates:
            exclusion=self._validate_candidate(candidate,request)
            if exclusion is not None:
                exclusions.append(exclusion)
                continue
            normalized_fact=candidate.normalized_fact.strip().casefold()
            if normalized_fact in seen_facts:
                exclusions.append(
                    ContextExclusionV1(
                        memory_id=candidate.memory_id,
                        subject_id=candidate.subject_id,
                        reason=ContextExclusionReason.DUPLICATE,
                        details="Equivalent memory content was already selected."
                    )
                )
                continue
            if self._conflicts_with_selected(candidate,selected):
                exclusions.append(
                    ContextExclusionV1(
                        memory_id=candidate.memory_id,
                        subject_id=candidate.subject_id,
                        reason=ContextExclusionReason.CONFLICTING_MEMORY,
                        details="Candidate conflicts with a higher-ranked selected memory."
                    )
                )
                continue
            content=self._format_content(candidate)
            item_characters=len(content)
            item_tokens=self._estimate_tokens(content)
            if len(selected)>=request.max_items:
                exclusions.append(
                    ContextExclusionV1(
                        memory_id=candidate.memory_id,
                        subject_id=candidate.subject_id,
                        reason=ContextExclusionReason.BUDGET_EXCEEDED,
                        details="Maximum context item budget was reached."
                    )
                )
                continue
            if character_count+item_characters>request.max_characters:
                exclusions.append(
                    ContextExclusionV1(
                        memory_id=candidate.memory_id,
                        subject_id=candidate.subject_id,
                        reason=ContextExclusionReason.BUDGET_EXCEEDED,
                        details="Maximum character budget would be exceeded."
                    )
                )
                continue
            if token_count+item_tokens>request.max_tokens:
                exclusions.append(
                    ContextExclusionV1(
                        memory_id=candidate.memory_id,
                        subject_id=candidate.subject_id,
                        reason=ContextExclusionReason.BUDGET_EXCEEDED,
                        details="Maximum token budget would be exceeded."
                    )
                )
                continue
            item=ContextItemV1(
                memory_id=candidate.memory_id,
                subject_id=candidate.subject_id,
                memory_type=candidate.memory_type,
                content=content,
                rank=len(selected)+1,
                relevance_score=candidate.final_score,
                confidence=candidate.confidence,
                recorded_at=self._datetime_from_provenance(candidate,"recorded_at"),
                valid_from=self._datetime_from_provenance(candidate,"valid_from"),
                valid_to=self._optional_datetime_from_provenance(candidate,"valid_to"),
                source_event_ids=list(candidate.source_event_ids),
                source_session_ids=list(candidate.source_session_ids),
                provenance={
                    **candidate.provenance,
                    "retrieval_rank":len(selected)+1
                }
            )
            selected.append(item)
            seen_facts.add(normalized_fact)
            selected_types[candidate.memory_type]=selected_types.get(candidate.memory_type,0)+1
            character_count+=item_characters
            token_count+=item_tokens
        decision=ContextDecision.COMPOSED if selected else ContextDecision.NO_CONTEXT
        return ContextCompositionResultV1(
            decision=decision,
            subject_id=request.subject_id,
            query_intent=retrieval_result.query_intent,
            items=selected,
            exclusions=exclusions,
            item_count=len(selected),
            character_count=character_count,
            estimated_token_count=token_count,
            composition_version=self.composition_version,
            provenance={
                "retrieval_version":retrieval_result.retrieval_version,
                "retrieved_candidate_count":retrieval_result.candidate_count,
                "selected_memory_types":selected_types,
                "surface":request.surface,
                "locale":request.locale
            }
        )
    @staticmethod
    def _validate_input(retrieval_result:RetrievalResultV1,request:ContextCompositionRequestV1)->None:
        if not isinstance(retrieval_result,RetrievalResultV1):
            raise ContextCompositionError(
                ContextCompositionErrorCode.INVALID_RETRIEVAL_RESULT,
                "Input must be a RetrievalResultV1."
            )
        if not isinstance(request,ContextCompositionRequestV1):
            raise ContextCompositionError(
                ContextCompositionErrorCode.INVALID_BUDGET,
                "Input must be a ContextCompositionRequestV1."
            )
        if retrieval_result.subject_id!=request.subject_id:
            raise ContextCompositionError(
                ContextCompositionErrorCode.SUBJECT_MISMATCH,
                "Retrieval result subject does not match context request subject."
            )
        if not request.subject_scope.strip():
            raise ContextCompositionError(
                ContextCompositionErrorCode.SUBJECT_MISMATCH,
                "Context request subject scope is required."
            )
    @staticmethod
    def _validate_candidate(candidate:RetrievalCandidateV1,request:ContextCompositionRequestV1)->Optional[ContextExclusionV1]:
        if candidate.subject_id!=request.subject_id:
            return ContextExclusionV1(
                memory_id=candidate.memory_id,
                subject_id=candidate.subject_id,
                reason=ContextExclusionReason.INVALID_CANDIDATE,
                details="Candidate subject does not match request subject."
            )
        if candidate.status!=MemoryStatus.ACTIVE:
            return ContextExclusionV1(
                memory_id=candidate.memory_id,
                subject_id=candidate.subject_id,
                reason=ContextExclusionReason.INELIGIBLE_STATUS,
                details="Only active memories may enter composed context."
            )
        if candidate.confidence<0.0 or candidate.final_score<0.0:
            return ContextExclusionV1(
                memory_id=candidate.memory_id,
                subject_id=candidate.subject_id,
                reason=ContextExclusionReason.INVALID_CANDIDATE,
                details="Candidate contains an invalid ranking score."
            )
        return None
    @staticmethod
    def _order_candidates(candidates:list[RetrievalCandidateV1])->list[RetrievalCandidateV1]:
        return sorted(
            candidates,
            key=lambda candidate:(
                -candidate.final_score,
                -candidate.confidence,
                -candidate.explicitness_score,
                candidate.memory_id
            )
        )
    @staticmethod
    def _format_content(candidate:RetrievalCandidateV1)->str:
        return candidate.normalized_fact.strip()
    @staticmethod
    def _estimate_tokens(text:str)->int:
        return max(1,math.ceil(len(text)/4))
    @staticmethod
    def _conflicts_with_selected(candidate:RetrievalCandidateV1,selected:list[ContextItemV1])->bool:
        candidate_type=candidate.memory_type
        if candidate_type!="explicit_preference":
            return False
        candidate_tokens=set(RuleBasedContextComposer._tokens(candidate.normalized_fact))
        for item in selected:
            if item.memory_type!="explicit_preference":
                continue
            selected_tokens=set(RuleBasedContextComposer._tokens(item.content))
            if not candidate_tokens or not selected_tokens:
                continue
            overlap=len(candidate_tokens&selected_tokens)
            denominator=max(1,min(len(candidate_tokens),len(selected_tokens)))
            if overlap/denominator>=0.8 and candidate.normalized_fact.strip().casefold()!=item.content.strip().casefold():
                return True
        return False
    @staticmethod
    def _tokens(text:str)->list[str]:
        return [
            token
            for token in "".join(
                character.lower() if character.isalnum() else " "
                for character in text
            ).split()
            if len(token)>1
        ]
    @staticmethod
    def _datetime_from_provenance(candidate:RetrievalCandidateV1,key:str)->datetime:
        value=candidate.provenance.get(key)
        if not isinstance(value,datetime):
            raise ContextCompositionError(
                ContextCompositionErrorCode.INVALID_CANDIDATE,
                f"Candidate provenance field {key} is missing or invalid."
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise ContextCompositionError(
                ContextCompositionErrorCode.INVALID_CANDIDATE,
                f"Candidate provenance field {key} must be timezone-aware."
            )
        return value
    @staticmethod
    def _optional_datetime_from_provenance(candidate:RetrievalCandidateV1,key:str)->Optional[datetime]:
        value=candidate.provenance.get(key)
        if value is None:
            return None
        if not isinstance(value,datetime):
            raise ContextCompositionError(
                ContextCompositionErrorCode.INVALID_CANDIDATE,
                f"Candidate provenance field {key} is invalid."
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise ContextCompositionError(
                ContextCompositionErrorCode.INVALID_CANDIDATE,
                f"Candidate provenance field {key} must be timezone-aware."
            )
        return value