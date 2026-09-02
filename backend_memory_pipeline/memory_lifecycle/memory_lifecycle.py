from datetime import datetime,timezone
from enum import Enum
from typing import Any,Optional,Protocol
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,model_validator
from backend_memory_pipeline.memory_extraction.memory_extraction import ExtractedMemoryCandidate,MemoryType
from backend_memory_pipeline.policy_consent.policy_consent import PolicyDecisionType,PolicyDecisionV1,RetentionClass
class MemoryLifecycleAction(str,Enum):
    CREATE="create"
    UPDATE="update"
    SUPERSEDE="supersede"
    EXPIRE="expire"
    RETAIN="retain"
    CORRECT="correct"
    DELETE="delete"
class MemoryStatus(str,Enum):
    ACTIVE="active"
    SUPERSEDED="superseded"
    EXPIRED="expired"
    CORRECTED="corrected"
    DELETED="deleted"
    PENDING_DELETION="pending_deletion"
class LifecycleErrorCode(str,Enum):
    INVALID_CANDIDATE="INVALID_CANDIDATE"
    POLICY_NOT_ALLOWED="POLICY_NOT_ALLOWED"
    INVALID_MEMORY="INVALID_MEMORY"
    INVALID_TRANSITION="INVALID_TRANSITION"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    MISSING_TARGET_MEMORY="MISSING_TARGET_MEMORY"
    ALREADY_DELETED="ALREADY_DELETED"
    ALREADY_EXPIRED="ALREADY_EXPIRED"
    TEMPORAL_CONFLICT="TEMPORAL_CONFLICT"
class MemoryLifecycleError(Exception):
    def __init__(self,code:LifecycleErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class MemoryRecordV1(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
    schema_version:str="1.0"
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    memory_type:MemoryType
    normalized_fact:str=Field(min_length=1,max_length=10000)
    entities:list[dict[str,Any]]=Field(default_factory=list)
    confidence:float=Field(ge=0.0,le=1.0)
    source_event_ids:list[str]=Field(default_factory=list,min_length=1)
    source_session_ids:list[str]=Field(default_factory=list)
    created_at:datetime
    recorded_at:datetime
    valid_from:datetime
    valid_to:Optional[datetime]=None
    status:MemoryStatus=MemoryStatus.ACTIVE
    retention_class:RetentionClass=RetentionClass.STANDARD
    retrieval_eligible:bool=True
    embedding_eligible:bool=True
    correction_of_memory_id:Optional[str]=None
    supersedes_memory_id:Optional[str]=None
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_temporal_state(self):
        for field_name in ("created_at","recorded_at","valid_from"):
            value=getattr(self,field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware.")
        if self.valid_to is not None:
            if self.valid_to.tzinfo is None or self.valid_to.utcoffset() is None:
                raise ValueError("valid_to must be timezone-aware.")
            if self.valid_to<self.valid_from:
                raise ValueError("valid_to cannot be earlier than valid_from.")
        if self.status in {
            MemoryStatus.SUPERSEDED,
            MemoryStatus.EXPIRED,
            MemoryStatus.CORRECTED,
            MemoryStatus.DELETED
        }:
            if self.valid_to is None:
                raise ValueError("Terminal memory states require valid_to.")
        if self.status in {
            MemoryStatus.EXPIRED,
            MemoryStatus.DELETED,
            MemoryStatus.PENDING_DELETION
        }:
            if self.retrieval_eligible:
                raise ValueError("Expired or deleted memories cannot remain retrieval eligible.")
        if not self.subject_id.strip() or not self.subject_scope.strip():
            raise ValueError("Memory subject identity and subject scope are required.")
        if self.subject_id!=self.subject_scope:
            raise ValueError("Memory subject scope must match subject identity.")
        return self
class MemoryLifecycleRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    action:MemoryLifecycleAction
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    memory_id:Optional[str]=None
    target_memory_id:Optional[str]=None
    effective_at:datetime
    reason:str=Field(min_length=1,max_length=5000)
    correlation_id:str=Field(min_length=1,max_length=128)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_request(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("effective_at must be timezone-aware.")
        if self.action in {
            MemoryLifecycleAction.SUPERSEDE,
            MemoryLifecycleAction.CORRECT
        } and not self.target_memory_id:
            raise ValueError("target_memory_id is required for supersede and correct.")
        if self.action in {
            MemoryLifecycleAction.EXPIRE,
            MemoryLifecycleAction.RETAIN,
            MemoryLifecycleAction.DELETE,
            MemoryLifecycleAction.UPDATE
        } and not self.memory_id:
            raise ValueError("memory_id is required for this lifecycle action.")
        return self
class MemoryLifecycleResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    lifecycle_event_id:str=Field(min_length=1,max_length=128)
    action:MemoryLifecycleAction
    subject_id:str
    memory_id:Optional[str]=None
    created_memory_id:Optional[str]=None
    previous_memory_id:Optional[str]=None
    status:MemoryStatus
    changed:bool
    effective_at:datetime
    reason:str
    audit_metadata:dict[str,Any]=Field(default_factory=dict)
class MemoryStore(Protocol):
    def get(self,memory_id:str)->Optional[MemoryRecordV1]:
        ...
    def put(self,memory:MemoryRecordV1)->None:
        ...
    def delete(self,memory_id:str)->None:
        ...
class InMemoryMemoryStore:
    def __init__(self):
        self._records:dict[str,MemoryRecordV1]={}
    def get(self,memory_id:str)->Optional[MemoryRecordV1]:
        return self._records.get(memory_id)
    def put(self,memory:MemoryRecordV1)->None:
        self._records[memory.memory_id]=memory
    def delete(self,memory_id:str)->None:
        self._records.pop(memory_id,None)
    def all(self)->list[MemoryRecordV1]:
        return list(self._records.values())
class MemoryLifecycleService:
    def __init__(self,store:Optional[MemoryStore]=None):
        self.store=store or InMemoryMemoryStore()
    def create_from_approved_candidate(self,candidate:ExtractedMemoryCandidate,policy:PolicyDecisionV1,effective_at:Optional[datetime]=None,metadata:Optional[dict[str,Any]]=None)->MemoryLifecycleResultV1:
        self._validate_candidate_policy(candidate,policy)
        if policy.decision!=PolicyDecisionType.ALLOW:
            raise MemoryLifecycleError(
                LifecycleErrorCode.POLICY_NOT_ALLOWED,
                "Only policy-approved candidates can become durable memories."
            )
        effective_at=effective_at or datetime.now(timezone.utc)
        self._validate_effective_at(effective_at)
        existing=self._find_equivalent(candidate)
        if existing is not None:
            return self._retain_existing(existing,candidate,policy,effective_at)
        memory_id=str(uuid4())
        memory=MemoryRecordV1(
            memory_id=memory_id,
            subject_id=candidate.subject_id,
            subject_scope=candidate.subject_scope,
            memory_type=candidate.memory_type,
            normalized_fact=candidate.normalized_fact,
            entities=[entity.model_dump() for entity in candidate.entities if entity.canonical_id],
            confidence=candidate.confidence,
            source_event_ids=list(dict.fromkeys(candidate.source_event_ids)),
            source_session_ids=list(dict.fromkeys(candidate.source_session_ids)),
            created_at=effective_at,
            recorded_at=effective_at,
            valid_from=effective_at,
            valid_to=None,
            status=MemoryStatus.ACTIVE,
            retention_class=policy.retention_class,
            retrieval_eligible=policy.retrieval_eligible,
            embedding_eligible=policy.embedding_eligible,
            metadata={
                **dict(metadata or {}),
                "policy_version":policy.policy_version,
                "policy_flags":policy.policy_flags,
                "reason":candidate.reason
            }
        )
        self.store.put(memory)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.CREATE,
            subject_id=candidate.subject_id,
            memory_id=memory.memory_id,
            created_memory_id=memory.memory_id,
            previous_memory_id=None,
            status=memory.status,
            changed=True,
            effective_at=effective_at,
            reason="Approved candidate became a durable memory.",
            audit_metadata={
                "source_event_ids":memory.source_event_ids,
                "policy_version":policy.policy_version
            }
        )
    def supersede(self,request:MemoryLifecycleRequestV1,new_candidate:ExtractedMemoryCandidate,policy:PolicyDecisionV1)->MemoryLifecycleResultV1:
        if request.action!=MemoryLifecycleAction.SUPERSEDE:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Request action must be supersede."
            )
        target_id=request.target_memory_id
        if target_id is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.MISSING_TARGET_MEMORY,
                "Target memory is required."
            )
        target=self._get_owned_memory(target_id,request.subject_id)
        self._validate_replacement_subject(new_candidate,request.subject_id)
        self._validate_candidate_policy(new_candidate,policy)
        if policy.decision!=PolicyDecisionType.ALLOW:
            raise MemoryLifecycleError(
                LifecycleErrorCode.POLICY_NOT_ALLOWED,
                "Superseding memory must be policy-approved."
            )
        if target.status in {
            MemoryStatus.DELETED,
            MemoryStatus.PENDING_DELETION
        }:
            raise MemoryLifecycleError(
                LifecycleErrorCode.ALREADY_DELETED,
                "Cannot supersede a deleted or pending-deletion memory."
            )
        if target.status==MemoryStatus.EXPIRED:
            raise MemoryLifecycleError(
                LifecycleErrorCode.ALREADY_EXPIRED,
                "Cannot supersede an expired memory."
            )
        closed=self._close_memory(
            target,
            request.effective_at,
            MemoryStatus.SUPERSEDED
        )
        self.store.put(closed)
        new_memory_id=str(uuid4())
        new_memory=MemoryRecordV1(
            memory_id=new_memory_id,
            subject_id=new_candidate.subject_id,
            subject_scope=new_candidate.subject_scope,
            memory_type=new_candidate.memory_type,
            normalized_fact=new_candidate.normalized_fact,
            entities=[entity.model_dump() for entity in new_candidate.entities if entity.canonical_id],
            confidence=new_candidate.confidence,
            source_event_ids=list(dict.fromkeys(new_candidate.source_event_ids)),
            source_session_ids=list(dict.fromkeys(new_candidate.source_session_ids)),
            created_at=request.effective_at,
            recorded_at=request.effective_at,
            valid_from=request.effective_at,
            status=MemoryStatus.ACTIVE,
            retention_class=policy.retention_class,
            retrieval_eligible=policy.retrieval_eligible,
            embedding_eligible=policy.embedding_eligible,
            supersedes_memory_id=target.memory_id,
            metadata={
                "policy_version":policy.policy_version,
                "lifecycle_reason":request.reason
            }
        )
        self.store.put(new_memory)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.SUPERSEDE,
            subject_id=request.subject_id,
            memory_id=new_memory_id,
            created_memory_id=new_memory_id,
            previous_memory_id=target.memory_id,
            status=MemoryStatus.ACTIVE,
            changed=True,
            effective_at=request.effective_at,
            reason=request.reason,
            audit_metadata={"superseded_memory_id":target.memory_id}
        )
    def correct(self,request:MemoryLifecycleRequestV1,new_candidate:ExtractedMemoryCandidate,policy:PolicyDecisionV1)->MemoryLifecycleResultV1:
        if request.action!=MemoryLifecycleAction.CORRECT:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Request action must be correct."
            )
        target_id=request.target_memory_id
        if target_id is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.MISSING_TARGET_MEMORY,
                "Target memory is required."
            )
        target=self._get_owned_memory(target_id,request.subject_id)
        self._validate_replacement_subject(new_candidate,request.subject_id)
        self._validate_candidate_policy(new_candidate,policy)
        if policy.decision!=PolicyDecisionType.ALLOW:
            raise MemoryLifecycleError(
                LifecycleErrorCode.POLICY_NOT_ALLOWED,
                "Corrected replacement must be policy-approved."
            )
        if target.status in {
            MemoryStatus.DELETED,
            MemoryStatus.PENDING_DELETION
        }:
            raise MemoryLifecycleError(
                LifecycleErrorCode.ALREADY_DELETED,
                "Cannot correct a deleted or pending-deletion memory."
            )
        if target.status==MemoryStatus.EXPIRED:
            raise MemoryLifecycleError(
                LifecycleErrorCode.ALREADY_EXPIRED,
                "Cannot correct an expired memory."
            )
        closed=self._close_memory(
            target,
            request.effective_at,
            MemoryStatus.CORRECTED
        )
        self.store.put(closed)
        replacement_id=str(uuid4())
        replacement=MemoryRecordV1(
            memory_id=replacement_id,
            subject_id=new_candidate.subject_id,
            subject_scope=new_candidate.subject_scope,
            memory_type=new_candidate.memory_type,
            normalized_fact=new_candidate.normalized_fact,
            entities=[entity.model_dump() for entity in new_candidate.entities if entity.canonical_id],
            confidence=new_candidate.confidence,
            source_event_ids=list(dict.fromkeys(new_candidate.source_event_ids)),
            source_session_ids=list(dict.fromkeys(new_candidate.source_session_ids)),
            created_at=request.effective_at,
            recorded_at=request.effective_at,
            valid_from=request.effective_at,
            status=MemoryStatus.ACTIVE,
            retention_class=policy.retention_class,
            retrieval_eligible=policy.retrieval_eligible,
            embedding_eligible=policy.embedding_eligible,
            correction_of_memory_id=target.memory_id,
            metadata={
                "policy_version":policy.policy_version,
                "lifecycle_reason":request.reason
            }
        )
        self.store.put(replacement)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.CORRECT,
            subject_id=request.subject_id,
            memory_id=replacement_id,
            created_memory_id=replacement_id,
            previous_memory_id=target.memory_id,
            status=MemoryStatus.ACTIVE,
            changed=True,
            effective_at=request.effective_at,
            reason=request.reason,
            audit_metadata={"corrected_memory_id":target.memory_id}
        )
    def update(self,request:MemoryLifecycleRequestV1,changes:dict[str,Any])->MemoryLifecycleResultV1:
        if request.action!=MemoryLifecycleAction.UPDATE:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Request action must be update."
            )
        target_id=request.memory_id
        if target_id is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.MISSING_TARGET_MEMORY,
                "Memory id is required."
            )
        existing=self._get_owned_memory(target_id,request.subject_id)
        if existing.status!=MemoryStatus.ACTIVE:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Only active memories can be updated."
            )
        allowed={
            "normalized_fact",
            "entities",
            "confidence",
            "retrieval_eligible",
            "embedding_eligible",
            "metadata"
        }
        unknown=set(changes)-allowed
        if unknown:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                f"Unsupported memory update fields: {sorted(unknown)}"
            )
        updated=existing.model_copy(update=changes)
        self.store.put(updated)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.UPDATE,
            subject_id=request.subject_id,
            memory_id=existing.memory_id,
            created_memory_id=None,
            previous_memory_id=None,
            status=updated.status,
            changed=updated.model_dump()!=existing.model_dump(),
            effective_at=request.effective_at,
            reason=request.reason,
            audit_metadata={"updated_fields":sorted(changes)}
        )
    def retain(self,request:MemoryLifecycleRequestV1)->MemoryLifecycleResultV1:
        if request.action!=MemoryLifecycleAction.RETAIN:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Request action must be retain."
            )
        target_id=request.memory_id
        if target_id is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.MISSING_TARGET_MEMORY,
                "Memory id is required."
            )
        existing=self._get_owned_memory(target_id,request.subject_id)
        if existing.status!=MemoryStatus.ACTIVE:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Only active memories can be retained."
            )
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.RETAIN,
            subject_id=request.subject_id,
            memory_id=existing.memory_id,
            created_memory_id=None,
            previous_memory_id=None,
            status=MemoryStatus.ACTIVE,
            changed=False,
            effective_at=request.effective_at,
            reason=request.reason,
            audit_metadata={"retained":True}
        )
    def expire(self,request:MemoryLifecycleRequestV1)->MemoryLifecycleResultV1:
        if request.action!=MemoryLifecycleAction.EXPIRE:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Request action must be expire."
            )
        target_id=request.memory_id
        if target_id is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.MISSING_TARGET_MEMORY,
                "Memory id is required."
            )
        existing=self._get_owned_memory(target_id,request.subject_id)
        if existing.status==MemoryStatus.EXPIRED:
            return MemoryLifecycleResultV1(
                lifecycle_event_id=str(uuid4()),
                action=MemoryLifecycleAction.EXPIRE,
                subject_id=request.subject_id,
                memory_id=existing.memory_id,
                status=MemoryStatus.EXPIRED,
                changed=False,
                effective_at=request.effective_at,
                reason="Memory was already expired.",
                audit_metadata={}
            )
        if existing.status in {
            MemoryStatus.DELETED,
            MemoryStatus.PENDING_DELETION
        }:
            raise MemoryLifecycleError(
                LifecycleErrorCode.ALREADY_DELETED,
                "Cannot expire a deleted or pending-deletion memory."
            )
        expired=self._close_memory(
            existing,
            request.effective_at,
            MemoryStatus.EXPIRED
        )
        self.store.put(expired)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.EXPIRE,
            subject_id=request.subject_id,
            memory_id=existing.memory_id,
            status=MemoryStatus.EXPIRED,
            changed=True,
            effective_at=request.effective_at,
            reason=request.reason,
            audit_metadata={
                "retrieval_eligible":False,
                "embedding_eligible":False
            }
        )
    def delete(self,request:MemoryLifecycleRequestV1)->MemoryLifecycleResultV1:
        if request.action!=MemoryLifecycleAction.DELETE:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                "Request action must be delete."
            )
        target_id=request.memory_id
        if target_id is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.MISSING_TARGET_MEMORY,
                "Memory id is required."
            )
        existing=self._get_owned_memory(target_id,request.subject_id)
        if existing.status in {
            MemoryStatus.DELETED,
            MemoryStatus.PENDING_DELETION
        }:
            return MemoryLifecycleResultV1(
                lifecycle_event_id=str(uuid4()),
                action=MemoryLifecycleAction.DELETE,
                subject_id=request.subject_id,
                memory_id=existing.memory_id,
                status=existing.status,
                changed=False,
                effective_at=request.effective_at,
                reason="Memory deletion is already in progress or has already completed.",
                audit_metadata={
                    "idempotent":True,
                    "deletion_propagation_required":existing.status==MemoryStatus.PENDING_DELETION
                }
            )
        if existing.status in {
            MemoryStatus.EXPIRED,
            MemoryStatus.SUPERSEDED,
            MemoryStatus.CORRECTED
        }:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_TRANSITION,
                f"Cannot delete memory in {existing.status.value} state through this active-memory delete path."
            )
        deleted=self._close_memory(
            existing,
            request.effective_at,
            MemoryStatus.DELETED
        )
        deleted=deleted.model_copy(
            update={
                "status":MemoryStatus.PENDING_DELETION,
                "retrieval_eligible":False,
                "embedding_eligible":False
            }
        )
        self.store.put(deleted)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.DELETE,
            subject_id=request.subject_id,
            memory_id=existing.memory_id,
            status=MemoryStatus.PENDING_DELETION,
            changed=True,
            effective_at=request.effective_at,
            reason=request.reason,
            audit_metadata={
                "deletion_propagation_required":True
            }
        )
    def _find_equivalent(self,candidate:ExtractedMemoryCandidate)->Optional[MemoryRecordV1]:
        if not isinstance(self.store,InMemoryMemoryStore):
            return None
        for memory in self.store.all():
            if memory.subject_id!=candidate.subject_id:
                continue
            if memory.status!=MemoryStatus.ACTIVE:
                continue
            if memory.memory_type!=candidate.memory_type:
                continue
            if memory.normalized_fact.strip().casefold()==candidate.normalized_fact.strip().casefold():
                return memory
        return None
    def _retain_existing(self,existing:MemoryRecordV1,candidate:ExtractedMemoryCandidate,policy:PolicyDecisionV1,effective_at:datetime)->MemoryLifecycleResultV1:
        updated=existing.model_copy(
            update={
                "source_event_ids":list(dict.fromkeys([
                    *existing.source_event_ids,
                    *candidate.source_event_ids
                ])),
                "source_session_ids":list(dict.fromkeys([
                    *existing.source_session_ids,
                    *candidate.source_session_ids
                ])),
                "confidence":max(existing.confidence,candidate.confidence),
                "recorded_at":effective_at,
                "metadata":{
                    **existing.metadata,
                    "last_reinforced_at":effective_at.isoformat(),
                    "policy_version":policy.policy_version
                }
            }
        )
        self.store.put(updated)
        return MemoryLifecycleResultV1(
            lifecycle_event_id=str(uuid4()),
            action=MemoryLifecycleAction.RETAIN,
            subject_id=existing.subject_id,
            memory_id=existing.memory_id,
            status=existing.status,
            changed=updated.model_dump()!=existing.model_dump(),
            effective_at=effective_at,
            reason="Equivalent active memory already exists; evidence was retained and lineage strengthened.",
            audit_metadata={"reinforced":True}
        )
    def _get_owned_memory(self,memory_id:str,subject_id:str)->MemoryRecordV1:
        memory=self.store.get(memory_id)
        if memory is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_MEMORY,
                f"Memory {memory_id} was not found."
            )
        if memory.subject_id!=subject_id or memory.subject_scope!=subject_id:
            raise MemoryLifecycleError(
                LifecycleErrorCode.SUBJECT_MISMATCH,
                "Memory does not belong to the requested subject."
            )
        return memory
    @staticmethod
    def _validate_effective_at(effective_at:datetime)->None:
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise MemoryLifecycleError(
                LifecycleErrorCode.TEMPORAL_CONFLICT,
                "effective_at must be timezone-aware."
            )
    @staticmethod
    def _validate_replacement_subject(candidate:ExtractedMemoryCandidate,subject_id:str)->None:
        if candidate.subject_id!=subject_id or candidate.subject_scope!=subject_id:
            raise MemoryLifecycleError(
                LifecycleErrorCode.SUBJECT_MISMATCH,
                "Replacement candidate does not belong to the requested subject."
            )
    @staticmethod
    def _close_memory(memory:MemoryRecordV1,effective_at:datetime,status:MemoryStatus)->MemoryRecordV1:
        MemoryLifecycleService._validate_effective_at(effective_at)
        if effective_at<memory.valid_from:
            raise MemoryLifecycleError(
                LifecycleErrorCode.TEMPORAL_CONFLICT,
                "effective_at cannot precede memory valid_from."
            )
        return memory.model_copy(
            update={
                "valid_to":effective_at,
                "status":status,
                "retrieval_eligible":False,
                "embedding_eligible":False
            }
        )
    @staticmethod
    def _validate_candidate_policy(candidate:ExtractedMemoryCandidate,policy:PolicyDecisionV1)->None:
        if not isinstance(candidate,ExtractedMemoryCandidate):
            raise MemoryLifecycleError(
                LifecycleErrorCode.INVALID_CANDIDATE,
                "Input must be an ExtractedMemoryCandidate."
            )
        if not isinstance(policy,PolicyDecisionV1):
            raise MemoryLifecycleError(
                LifecycleErrorCode.POLICY_NOT_ALLOWED,
                "Input must be a PolicyDecisionV1."
            )
        if candidate.subject_id!=policy.subject_id:
            raise MemoryLifecycleError(
                LifecycleErrorCode.SUBJECT_MISMATCH,
                "Candidate and policy decision subjects do not match."
            )