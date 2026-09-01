from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any,Mapping,Optional,Protocol
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
class IngestionErrorCode(str,Enum):
    INVALID_SCHEMA="INVALID_SCHEMA"
    MISSING_REQUIRED_FIELD="MISSING_REQUIRED_FIELD"
    INVALID_FIELD="INVALID_FIELD"
    INVALID_TIMESTAMP="INVALID_TIMESTAMP"
    INVALID_EVENT_TYPE="INVALID_EVENT_TYPE"
    INVALID_CONSENT_STATE="INVALID_CONSENT_STATE"
    INVALID_SOURCE="INVALID_SOURCE"
    INVALID_IDEMPOTENCY_KEY="INVALID_IDEMPOTENCY_KEY"
    INVALID_SUBJECT_SCOPE="INVALID_SUBJECT_SCOPE"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    INVALID_SESSION="INVALID_SESSION"
    DUPLICATE_EVENT="DUPLICATE_EVENT"
class IngestionError(Exception):
    def __init__(self,code:IngestionErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class EventType(str,Enum):
    AI_INTERACTION="ai_interaction"
    PLAYBACK="playback"
    SAVE="save"
    FOLLOW="follow"
    SKIP="skip"
    EXPLICIT_PREFERENCE="explicit_preference"
class ConsentState(str,Enum):
    OPTED_IN="opted_in"
    OPTED_OUT="opted_out"
    PAUSED="paused"
    UNKNOWN="unknown"
    NOT_APPLICABLE="not_applicable"
class SessionRecordV1(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
    schema_version:str="1.0"
    session_id:str=Field(min_length=1,max_length=128)
    user_id:str=Field(min_length=1,max_length=128)
    session_start:datetime
    session_end:datetime
    session_duration_seconds:int=Field(ge=0)
    primary_domain:Optional[str]=None
    session_context:Optional[str]=None
    device_type:Optional[str]=None
    platform:Optional[str]=None
    @model_validator(mode="after")
    def validate_temporal_consistency(self):
        if self.session_start.tzinfo is None or self.session_start.utcoffset() is None:
            raise ValueError("session_start must be timezone-aware.")
        if self.session_end.tzinfo is None or self.session_end.utcoffset() is None:
            raise ValueError("session_end must be timezone-aware.")
        if self.session_end<=self.session_start:
            raise ValueError("session_end must be after session_start.")
        actual=(self.session_end-self.session_start).total_seconds()
        if abs(actual-self.session_duration_seconds)>1:
            raise ValueError("session_duration_seconds does not match session interval.")
        return self
class MemoryControlAction(str,Enum):
    OPT_IN="opt_in"
    OPT_OUT="opt_out"
    PAUSE="pause"
    RESUME="resume"
    #CORRECT="correct"
    #DELETE="delete"
#class MemoryLifecycleAction(str,Enum):
    #EXPIRE="expire"
    #SUPERSEDE="supersede"
    #RETAIN="retain"
class InteractionEventV1(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
    schema_version:str="1.0"
    event_id:str=Field(min_length=1,max_length=128)
    source_event_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    session_id:str=Field(min_length=1,max_length=128)
    event_type:EventType
    source:str=Field(min_length=1,max_length=64)
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    timestamp:datetime
    consent_state:ConsentState
    idempotency_key:str=Field(min_length=1,max_length=256)
    correlation_id:str=Field(min_length=1,max_length=128)
    text:Optional[str]=None
    entity:Optional[dict[str,Any]]=None
    context_entities:dict[str,Any]=Field(default_factory=dict)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_event(self):
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware.")
        if not self.source.strip():
            raise ValueError("source is required.")
        if not self.locale.strip():
            raise ValueError("locale is required.")
        if self.event_type==EventType.AI_INTERACTION:
            if self.text is None or not self.text.strip():
                raise ValueError("text is required for ai_interaction events.")
        if self.event_type==EventType.PLAYBACK:
           playback_action=self.metadata.get("playback_action")
           if playback_action not in {"play","pause"}:
                raise ValueError("playback_action must be play or pause for playback events.")    
        return self
    @field_validator("text")
    @classmethod
    def validate_text(cls,value):
        if value is not None and not value.strip():
            raise ValueError("text cannot be empty when supplied.")
        return value
@dataclass(frozen=True)
class IngestionEnvelopeV1:
    event:InteractionEventV1
    session:Optional[SessionRecordV1]=None
@dataclass(frozen=True)
class IngestionResult:
    status:str
    event:InteractionEventV1
    session:Optional[SessionRecordV1]
    duplicate:bool
class IdempotencyStore(Protocol):
    def get_event_id(self,idempotency_key:str)->Optional[str]:
        ...
    def register(self,idempotency_key:str,event_id:str)->None:
        ...
class InMemoryIdempotencyStore:
    def __init__(self):
        self._records:dict[str,str]={}
    def get_event_id(self,idempotency_key:str)->Optional[str]:
        return self._records.get(idempotency_key)
    def register(self,idempotency_key:str,event_id:str)->None:
        self._records[idempotency_key]=event_id
class IngestionService:
    def __init__(self,idempotency_store:Optional[IdempotencyStore]=None):
        self.idempotency_store=idempotency_store or InMemoryIdempotencyStore()
    def ingest(self,envelope:IngestionEnvelopeV1,authorized_subject_id:Optional[str]=None)->IngestionResult:
        self._validate_envelope(envelope)
        if authorized_subject_id is not None and authorized_subject_id!=envelope.event.subject_id:
            raise IngestionError(IngestionErrorCode.SUBJECT_MISMATCH,"Authenticated subject does not match event subject.")
        existing_event_id=self.idempotency_store.get_event_id(envelope.event.idempotency_key)
        if existing_event_id is not None:
            if existing_event_id==envelope.event.event_id:
                return IngestionResult(status="duplicate",event=envelope.event,session=envelope.session,duplicate=True)
            raise IngestionError(IngestionErrorCode.DUPLICATE_EVENT,"Idempotency key is already associated with another event.")
        self.idempotency_store.register(envelope.event.idempotency_key,envelope.event.event_id)
        return IngestionResult(status="accepted",event=envelope.event,session=envelope.session,duplicate=False)
    def ingest_mapping(self,data:Mapping[str,Any],authorized_subject_id:Optional[str]=None)->IngestionResult:
        if not isinstance(data,Mapping):
            raise IngestionError(IngestionErrorCode.INVALID_SCHEMA,"Ingestion input must be a mapping.")
        raw=dict(data)
        session_data=raw.pop("session",None)
        raw.setdefault("event_id",str(uuid4()))
        raw.setdefault("source_event_id",raw["event_id"])
        raw.setdefault("correlation_id",str(uuid4()))
        try:
            event=InteractionEventV1.model_validate(raw)
            session=SessionRecordV1.model_validate(session_data) if session_data is not None else None
        except Exception as exc:
            raise IngestionError(IngestionErrorCode.INVALID_SCHEMA,str(exc)) from exc
        envelope=IngestionEnvelopeV1(event=event,session=session)
        return self.ingest(envelope,authorized_subject_id=authorized_subject_id)
    @staticmethod
    def _validate_envelope(envelope:IngestionEnvelopeV1)->None:
        if not isinstance(envelope,IngestionEnvelopeV1):
            raise IngestionError(IngestionErrorCode.INVALID_SCHEMA,"Input must be an IngestionEnvelopeV1.")
        event=envelope.event
        if not event.subject_id.strip():
            raise IngestionError(IngestionErrorCode.MISSING_REQUIRED_FIELD,"subject_id is required.")
        if not event.subject_scope.strip():
            raise IngestionError(IngestionErrorCode.INVALID_SUBJECT_SCOPE,"subject_scope is required.")
        if not event.source_event_id.strip():
            raise IngestionError(IngestionErrorCode.MISSING_REQUIRED_FIELD,"source_event_id is required.")
        if not event.idempotency_key.strip():
            raise IngestionError(IngestionErrorCode.INVALID_IDEMPOTENCY_KEY,"idempotency_key is required.")
        if not event.source.strip():
            raise IngestionError(IngestionErrorCode.INVALID_SOURCE,"source is required.")
        if envelope.session is not None:
            session=envelope.session
            if session.session_id!=event.session_id:
                raise IngestionError(IngestionErrorCode.INVALID_SESSION,"Event session_id does not match session record.")
            if session.user_id!=event.subject_id:
                raise IngestionError(IngestionErrorCode.INVALID_SESSION,"Session user_id does not match event subject_id.")
            if event.timestamp<session.session_start or event.timestamp>session.session_end:
                raise IngestionError(IngestionErrorCode.INVALID_TIMESTAMP,"Event timestamp falls outside the session interval.")
    @staticmethod
    def new_event_id()->str:
        return str(uuid4())
    @staticmethod
    def new_source_event_id()->str:
        return str(uuid4())
    @staticmethod
    def new_correlation_id()->str:
        return str(uuid4())
    @staticmethod
    def new_idempotency_key()->str:
        return str(uuid4())
class MemoryControlEventV1(BaseModel):
    model_config=ConfigDict(extra="forbid",validate_assignment=True)
    schema_version:str="1.0"
    control_event_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    action:MemoryControlAction
    #memory_id:Optional[str]=Field(default=None,max_length=128)
    source_event_id:str=Field(min_length=1,max_length=128)
    idempotency_key:str=Field(min_length=1,max_length=256)
    timestamp:datetime
    correlation_id:str=Field(min_length=1,max_length=128)
    source:str=Field(min_length=1,max_length=64)
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_control_event(self):
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware.")
        if self.subject_id != self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        return self
        '''
        if self.action in {MemoryControlAction.CORRECT,MemoryControlAction.DELETE} and not self.memory_id:
            raise ValueError("memory_id is required for correct and delete actions.")
        return self
        ''' 