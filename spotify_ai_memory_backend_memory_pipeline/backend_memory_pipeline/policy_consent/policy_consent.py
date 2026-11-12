from enum import Enum
from typing import Any,Optional,Protocol
from datetime import datetime,timezone
from pydantic import BaseModel,ConfigDict,Field,model_validator
from backend_memory_pipeline.ingestion.ingestion import ConsentState
from backend_memory_pipeline.memory_extraction.memory_extraction import ExtractedMemoryCandidate,MemoryType,PolicyClass
from backend_memory_pipeline.entity_resolution.entity_resolution import EntityResolutionResultV1,EntityResolutionStatus
class PolicyDecisionType(str,Enum):
    ALLOW="allow"
    DENY="deny"
    REVIEW="review"
    NO_MEMORY="no_memory"
class MemoryControlAction(str,Enum):
    OPT_IN="opt_in"
    OPT_OUT="opt_out"
    PAUSE="pause"
    RESUME="resume"
class ConsentDecision(str,Enum):
    ALLOWED="allowed"
    DENIED="denied"
    PAUSED="paused"
    UNKNOWN="unknown"
class SensitivityLevel(str,Enum):
    STANDARD="standard"
    SENSITIVE="sensitive"
    PROHIBITED="prohibited"
class RetentionClass(str,Enum):
    STANDARD="standard"
    SHORT="short"
    LONG="long"
    NONE="none"
class PolicyErrorCode(str,Enum):
    INVALID_CANDIDATE="INVALID_CANDIDATE"
    INVALID_POLICY_INPUT="INVALID_POLICY_INPUT"
    CONSENT_DENIED="CONSENT_DENIED"
    CONSENT_PAUSED="CONSENT_PAUSED"
    SENSITIVE_MEMORY="SENSITIVE_MEMORY"
    PROHIBITED_MEMORY="PROHIBITED_MEMORY"
    ENTITY_NOT_RESOLVED="ENTITY_NOT_RESOLVED"
    ENTITY_AMBIGUOUS="ENTITY_AMBIGUOUS"
    RETENTION_DENIED="RETENTION_DENIED"
    PURPOSE_DENIED="PURPOSE_DENIED"
    GEOGRAPHY_DENIED="GEOGRAPHY_DENIED"
    AGE_POLICY_DENIED="AGE_POLICY_DENIED"
    INVALID_CONTROL_REQUEST="INVALID_CONTROL_REQUEST"
    INVALID_CONTROL_TRANSITION="INVALID_CONTROL_TRANSITION"
    CONSENT_STATE_NOT_FOUND="CONSENT_STATE_NOT_FOUND"
class PolicyConsentError(Exception):
    def __init__(self,code:PolicyErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class ConsentControlRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    action:MemoryControlAction
    timestamp:datetime
    correlation_id:str=Field(min_length=1,max_length=128)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_request(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware.")
        return self
class ConsentStateRecordV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    state:ConsentState
    changed_at:datetime
    last_action:MemoryControlAction
    correlation_id:str=Field(min_length=1,max_length=128)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_record(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.changed_at.tzinfo is None or self.changed_at.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware.")
        return self
class ConsentControlResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    action:MemoryControlAction
    previous_state:ConsentState
    current_state:ConsentState
    changed:bool
    timestamp:datetime
    correlation_id:str
    reason:str
    state_record:ConsentStateRecordV1
class ConsentStateStore(Protocol):
    def get(self,subject_id:str)->Optional[ConsentStateRecordV1]:
        ...
    def put(self,record:ConsentStateRecordV1)->None:
        ...
class InMemoryConsentStateStore:
    def __init__(self):
        self._records:dict[str,ConsentStateRecordV1]={}
    def get(self,subject_id:str)->Optional[ConsentStateRecordV1]:
        return self._records.get(subject_id)
    def put(self,record:ConsentStateRecordV1)->None:
        self._records[record.subject_id]=record
class ConsentControlService:
    def __init__(self,store:Optional[ConsentStateStore]=None,default_state:ConsentState=ConsentState.UNKNOWN):
        self.store=store or InMemoryConsentStateStore()
        self.default_state=default_state
    def get_state(self,subject_id:str)->ConsentStateRecordV1:
        record=self.store.get(subject_id)
        if record is not None:
            return record
        now=datetime.now(timezone.utc)
        return ConsentStateRecordV1(
            subject_id=subject_id,
            subject_scope=subject_id,
            state=self.default_state,
            changed_at=now,
            last_action=MemoryControlAction.OPT_IN if self.default_state==ConsentState.OPTED_IN else MemoryControlAction.OPT_OUT if self.default_state==ConsentState.OPTED_OUT else MemoryControlAction.PAUSE if self.default_state==ConsentState.PAUSED else MemoryControlAction.OPT_IN,
            correlation_id="initial",
            metadata={"default_state":True}
        )
    def apply(self,request:ConsentControlRequestV1)->ConsentControlResultV1:
        current_record=self.store.get(request.subject_id)
        previous_state=current_record.state if current_record is not None else self.default_state
        next_state=self._transition(previous_state,request.action)
        changed=next_state!=previous_state
        record=ConsentStateRecordV1(
            subject_id=request.subject_id,
            subject_scope=request.subject_scope,
            state=next_state,
            changed_at=request.timestamp,
            last_action=request.action,
            correlation_id=request.correlation_id,
            metadata=request.metadata
        )
        self.store.put(record)
        reason=self._reason(previous_state,next_state,request.action,changed)
        return ConsentControlResultV1(
            subject_id=request.subject_id,
            action=request.action,
            previous_state=previous_state,
            current_state=next_state,
            changed=changed,
            timestamp=request.timestamp,
            correlation_id=request.correlation_id,
            reason=reason,
            state_record=record
        )
    @staticmethod
    def _transition(current_state:ConsentState,action:MemoryControlAction)->ConsentState:
        transitions={
            (ConsentState.OPTED_IN,MemoryControlAction.PAUSE):ConsentState.PAUSED,
            (ConsentState.PAUSED,MemoryControlAction.RESUME):ConsentState.OPTED_IN,
            (ConsentState.OPTED_IN,MemoryControlAction.OPT_OUT):ConsentState.OPTED_OUT,
            (ConsentState.OPTED_OUT,MemoryControlAction.OPT_IN):ConsentState.OPTED_IN,
            (ConsentState.UNKNOWN,MemoryControlAction.OPT_IN):ConsentState.OPTED_IN,
            (ConsentState.UNKNOWN,MemoryControlAction.OPT_OUT):ConsentState.OPTED_OUT,
            (ConsentState.UNKNOWN,MemoryControlAction.PAUSE):ConsentState.PAUSED
        }
        key=(current_state,action)
        if key not in transitions:
            raise PolicyConsentError(
                PolicyErrorCode.INVALID_CONTROL_TRANSITION,
                f"Invalid consent transition: {current_state.value} + {action.value}."
            )
        return transitions[key]
    @staticmethod
    def _reason(previous_state:ConsentState,current_state:ConsentState,action:MemoryControlAction,changed:bool)->str:
        if not changed:
            return f"Consent action {action.value} produced no state change."
        return f"Consent state changed from {previous_state.value} to {current_state.value} through {action.value}."
class PolicyRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    purpose:str=Field(min_length=1,max_length=128)
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    consent_state:ConsentState
    geography:Optional[str]=None
    age_band:Optional[str]=None
    age_related_handling:Optional[str]=None
    requested_retention:Optional[RetentionClass]=None
    retrieval_requested:bool=True
    embedding_requested:bool=True
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_subject_scope(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        return self
class PolicyRegistryEntryV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    memory_type:MemoryType
    allowed:bool=True
    sensitivity:SensitivityLevel=SensitivityLevel.STANDARD
    retention_class:RetentionClass=RetentionClass.STANDARD
    allowed_purposes:list[str]=Field(default_factory=list)
    allowed_geographies:list[str]=Field(default_factory=list)
    retrieval_eligible:bool=True
    embedding_eligible:bool=True
    age_restricted:bool=False
    requires_review:bool=False
class PolicyDecisionV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    candidate_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    decision:PolicyDecisionType
    consent_decision:ConsentDecision
    sensitivity:SensitivityLevel
    retention_class:RetentionClass
    retrieval_eligible:bool
    embedding_eligible:bool
    policy_flags:list[str]=Field(default_factory=list)
    denied_reasons:list[str]=Field(default_factory=list)
    review_reasons:list[str]=Field(default_factory=list)
    allowed_reasons:list[str]=Field(default_factory=list)
    policy_version:str="1.0"
class PolicyEngine(Protocol):
    def evaluate(self,candidate:ExtractedMemoryCandidate,request:PolicyRequestV1,entity_result:Optional[EntityResolutionResultV1]=None)->PolicyDecisionV1:
        ...
class DefaultPolicyEngine:
    def __init__(self,registry:Optional[list[PolicyRegistryEntryV1]]=None,policy_version:str="1.0"):
        self.policy_version=policy_version
        self.registry={entry.memory_type:entry for entry in (registry or self._default_registry())}
    def evaluate(self,candidate:ExtractedMemoryCandidate,request:PolicyRequestV1,entity_result:Optional[EntityResolutionResultV1]=None)->PolicyDecisionV1:
        self._validate_input(candidate,request)
        entry=self.registry.get(candidate.memory_type)
        if entry is None:
            return self._deny(candidate,ConsentDecision.UNKNOWN,SensitivityLevel.PROHIBITED,RetentionClass.NONE,"Memory type is not registered.")
        denied=[]
        review=[]
        allowed=[]
        flags=[]
        consent_decision=self._evaluate_consent(request.consent_state)
        if consent_decision==ConsentDecision.DENIED:
            denied.append("Memory use is denied by consent state.")
        elif consent_decision==ConsentDecision.PAUSED:
            denied.append("Memory use is paused.")
        elif consent_decision==ConsentDecision.UNKNOWN:
            denied.append("Consent state is unknown.")
        sensitivity=self._evaluate_sensitivity(candidate,entry)
        if sensitivity==SensitivityLevel.PROHIBITED:
            denied.append("Memory type or candidate is prohibited.")
        elif sensitivity==SensitivityLevel.SENSITIVE:
            flags.append("sensitive_memory")
            if entry.requires_review:
                review.append("Sensitive memory requires policy review.")
        if not entry.allowed:
            denied.append("Memory type is not allowed by policy.")
        if entry.age_restricted:
            if not request.age_band or not request.age_related_handling:
                denied.append("Age-related policy information is required.")
            elif request.age_related_handling!="approved":
                denied.append("Age-related policy does not permit this memory.")
        if entry.allowed_purposes and request.purpose not in entry.allowed_purposes:
            denied.append("Requested purpose is not allowed for this memory type.")
        if entry.allowed_geographies:
            if not request.geography:
                denied.append("Geography is required for this memory type.")
            elif request.geography not in entry.allowed_geographies:
                denied.append("Requested geography is not allowed for this memory type.")
        retention=self._resolve_retention(candidate,entry,request,denied)
        resolved_status=entity_result.resolution_status if entity_result is not None else None
        if resolved_status==EntityResolutionStatus.REJECTED:
            denied.append("Entity resolution rejected the candidate.")
        elif resolved_status==EntityResolutionStatus.AMBIGUOUS:
            review.append("Entity resolution is ambiguous.")
            flags.append("ambiguous_entity")
        elif resolved_status==EntityResolutionStatus.UNRESOLVED and candidate.entities:
            review.append("One or more entities remain unresolved.")
            flags.append("unresolved_entity")
        if candidate.policy_class==PolicyClass.SENSITIVE:
            flags.append("extractor_marked_sensitive")
            review.append("Extractor marked the candidate as sensitive.")
        if "sensitive_inference" in candidate.policy_flags:
            flags.append("sensitive_inference")
            review.append("Candidate contains a sensitive inference signal.")
        if "behavioral_inference" in candidate.policy_flags:
            flags.append("behavioral_inference")
        if candidate.memory_type==MemoryType.CANDIDATE_PREFERENCE and candidate.evidence_count<2:
            review.append("Candidate preference lacks sufficient repeated evidence.")
            flags.append("insufficient_behavioral_evidence")
        if denied:
            decision=PolicyDecisionType.DENY
        elif review:
            decision=PolicyDecisionType.REVIEW
        else:
            decision=PolicyDecisionType.ALLOW
            allowed.append("Candidate satisfies current consent and policy rules.")
        retrieval_eligible=entry.retrieval_eligible and request.retrieval_requested and decision==PolicyDecisionType.ALLOW
        embedding_eligible=entry.embedding_eligible and request.embedding_requested and decision==PolicyDecisionType.ALLOW
        if decision!=PolicyDecisionType.ALLOW:
            retrieval_eligible=False
            embedding_eligible=False
        return PolicyDecisionV1(
            candidate_id=candidate.candidate_id,
            subject_id=candidate.subject_id,
            decision=decision,
            consent_decision=consent_decision,
            sensitivity=sensitivity,
            retention_class=retention,
            retrieval_eligible=retrieval_eligible,
            embedding_eligible=embedding_eligible,
            policy_flags=list(dict.fromkeys(flags)),
            denied_reasons=denied,
            review_reasons=review,
            allowed_reasons=allowed,
            policy_version=self.policy_version
        )
    @staticmethod
    def _default_registry()->list[PolicyRegistryEntryV1]:
        return [
            PolicyRegistryEntryV1(memory_type=MemoryType.EPISODE,retention_class=RetentionClass.STANDARD),
            PolicyRegistryEntryV1(memory_type=MemoryType.EXPLICIT_PREFERENCE,retention_class=RetentionClass.LONG),
            PolicyRegistryEntryV1(memory_type=MemoryType.CANDIDATE_PREFERENCE,retention_class=RetentionClass.STANDARD,requires_review=False),
            PolicyRegistryEntryV1(memory_type=MemoryType.EXCLUSION,retention_class=RetentionClass.LONG),
            PolicyRegistryEntryV1(memory_type=MemoryType.CORRECTION_SIGNAL,allowed=False,retention_class=RetentionClass.NONE,retrieval_eligible=False,embedding_eligible=False),
            PolicyRegistryEntryV1(memory_type=MemoryType.NON_MEMORY,allowed=False,retention_class=RetentionClass.NONE,retrieval_eligible=False,embedding_eligible=False)
        ]
    @staticmethod
    def _validate_input(candidate:ExtractedMemoryCandidate,request:PolicyRequestV1)->None:
        if not isinstance(candidate,ExtractedMemoryCandidate):
            raise PolicyConsentError(PolicyErrorCode.INVALID_CANDIDATE,"Input must be an ExtractedMemoryCandidate.")
        if not isinstance(request,PolicyRequestV1):
            raise PolicyConsentError(PolicyErrorCode.INVALID_POLICY_INPUT,"Input must be a PolicyRequestV1.")
        if candidate.subject_id!=request.subject_id or candidate.subject_scope!=request.subject_scope:
            raise PolicyConsentError(PolicyErrorCode.INVALID_POLICY_INPUT,"Candidate subject scope does not match policy subject scope.")
    @staticmethod
    def _evaluate_consent(state:ConsentState)->ConsentDecision:
        if state==ConsentState.OPTED_IN:
            return ConsentDecision.ALLOWED
        if state==ConsentState.OPTED_OUT:
            return ConsentDecision.DENIED
        if state==ConsentState.PAUSED:
            return ConsentDecision.PAUSED
        return ConsentDecision.UNKNOWN
    @staticmethod
    def _evaluate_sensitivity(candidate:ExtractedMemoryCandidate,entry:PolicyRegistryEntryV1)->SensitivityLevel:
        if entry.sensitivity==SensitivityLevel.PROHIBITED:
            return SensitivityLevel.PROHIBITED
        if entry.sensitivity==SensitivityLevel.SENSITIVE:
            return SensitivityLevel.SENSITIVE
        if candidate.policy_class==PolicyClass.PROHIBITED:
            return SensitivityLevel.PROHIBITED
        if candidate.policy_class==PolicyClass.SENSITIVE:
            return SensitivityLevel.SENSITIVE
        return SensitivityLevel.STANDARD
    @staticmethod
    def _resolve_retention(candidate:ExtractedMemoryCandidate,entry:PolicyRegistryEntryV1,request:PolicyRequestV1,denied:list[str])->RetentionClass:
        if entry.retention_class==RetentionClass.NONE:
            denied.append("Memory has no permitted retention class.")
            return RetentionClass.NONE
        if request.requested_retention is not None:
            requested=request.requested_retention
            rank={
                RetentionClass.NONE:0,
                RetentionClass.SHORT:1,
                RetentionClass.STANDARD:2,
                RetentionClass.LONG:3
            }
            if rank[requested]>rank[entry.retention_class]:
                denied.append("Requested retention exceeds policy retention limit.")
                return entry.retention_class
            return requested
        return entry.retention_class
    @staticmethod
    def _deny(candidate:ExtractedMemoryCandidate,consent:ConsentDecision,sensitivity:SensitivityLevel,retention:RetentionClass,reason:str)->PolicyDecisionV1:
        return PolicyDecisionV1(
            candidate_id=candidate.candidate_id,
            subject_id=candidate.subject_id,
            decision=PolicyDecisionType.DENY,
            consent_decision=consent,
            sensitivity=sensitivity,
            retention_class=retention,
            retrieval_eligible=False,
            embedding_eligible=False,
            policy_flags=[],
            denied_reasons=[reason],
            review_reasons=[],
            allowed_reasons=[],
            policy_version="1.0"
        )
class PolicyConsentService:
    def __init__(self,engine:Optional[PolicyEngine]=None,consent_control:Optional[ConsentControlService]=None):
        self.engine=engine or DefaultPolicyEngine()
        self.consent_control=consent_control or ConsentControlService()
    def evaluate(self,candidate:ExtractedMemoryCandidate,request:PolicyRequestV1,entity_result:Optional[EntityResolutionResultV1]=None)->PolicyDecisionV1:
        return self.engine.evaluate(candidate,request,entity_result)
    def apply_consent_control(self,request:ConsentControlRequestV1)->ConsentControlResultV1:
        return self.consent_control.apply(request)
    def get_consent_state(self,subject_id:str)->ConsentStateRecordV1:
        return self.consent_control.get_state(subject_id)