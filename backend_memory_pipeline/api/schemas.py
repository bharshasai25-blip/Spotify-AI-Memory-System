from datetime import datetime
from typing import Any,Optional
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from backend_memory_pipeline.ingestion.ingestion import (
    EventType
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    MemoryControlAction as ConsentControlAction
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import (
    MemoryLifecycleAction
)
from backend_memory_pipeline.response_generation.response_generation import (
    GeneratedResponseV1
)
class APIErrorResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    code:str=Field(min_length=1,max_length=128)
    message:str=Field(min_length=1,max_length=1000)
    correlation_id:Optional[str]=Field(default=None,max_length=128)
    details:dict[str,Any]=Field(default_factory=dict)
class HealthResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    service:str=Field(min_length=1,max_length=128)
    version:str=Field(min_length=1,max_length=64)
    timestamp:datetime
    checks:dict[str,str]=Field(default_factory=dict)
class RegisterRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    username:str=Field(min_length=3,max_length=128)
    password:str=Field(min_length=8,max_length=256)
    metadata:dict[str,Any]=Field(default_factory=dict)
class RegisterResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    access_token:str=Field(min_length=1,max_length=4096)
    token_type:str="bearer"
    expires_in:int=Field(gt=0)
    subject_id:str=Field(min_length=1,max_length=128)
    username:str=Field(min_length=1,max_length=128)
    correlation_id:str=Field(min_length=1,max_length=128)

class LoginRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    username:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=1,max_length=256)
    metadata:dict[str,Any]=Field(default_factory=dict)
class LoginResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    access_token:str=Field(min_length=1,max_length=4096)
    token_type:str="bearer"
    expires_in:int=Field(gt=0)
    subject_id:str=Field(min_length=1,max_length=128)
    username:str=Field(min_length=1,max_length=128)
    correlation_id:str=Field(min_length=1,max_length=128)

class LogoutRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    metadata:dict[str,Any]=Field(default_factory=dict)
class LogoutResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    subject_id:str=Field(min_length=1,max_length=128)
    username:str=Field(min_length=1,max_length=128)
    token_revoked:bool
    correlation_id:str=Field(min_length=1,max_length=128)
    timestamp:datetime
    metadata:dict[str,Any]=Field(default_factory=dict)

class EventSubmissionRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    event_type:EventType
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    text:Optional[str]=None
    entity:Optional[dict[str,Any]]=None
    context_entities:dict[str,Any]=Field(default_factory=dict)
    metadata:dict[str,Any]=Field(default_factory=dict)
    idempotency_key:Optional[str]=Field(default=None,max_length=256)
    @field_validator("text")
    @classmethod
    def validate_text(cls,value:Optional[str])->Optional[str]:
        if value is not None and not value.strip():
            return None
        return value
    '''
    @model_validator(mode="after")
    def validate_event_type_requirements(self):
        if self.event_type==EventType.AI_INTERACTION:
            if self.text is None or not self.text.strip():
                raise ValueError(
                    "text is required for ai_interaction events."
                )
        if self.event_type==EventType.PLAYBACK:
            playback_action=self.metadata.get("playback_action")
            if playback_action not in {"play","pause"}:
                raise ValueError(
                    "playback_action must be play or pause for playback events."
                )
        return self '''    
class EventSubmissionResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    event_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    duplicate:bool
    correlation_id:str=Field(min_length=1,max_length=128)
    memory_write_status:Optional[str]=Field(default=None,max_length=64)
    metadata:dict[str,Any]=Field(default_factory=dict)

class ChatRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    query:str=Field(min_length=1,max_length=10000)
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    requested_at:datetime
    max_response_characters:int=Field(default=12000,ge=100,le=100000)
    include_memory_references:bool=True
    metadata:dict[str,Any]=Field(default_factory=dict)
    @field_validator("query")
    @classmethod
    def validate_query(cls,value:str)->str:
        if not value.strip():
            raise ValueError("query cannot be empty.")
        return value
class ChatResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    response:GeneratedResponseV1
    correlation_id:str=Field(min_length=1,max_length=128)
    trace_id:Optional[str]=Field(default=None,max_length=128)
    metadata:dict[str,Any]=Field(default_factory=dict)

class MemoryCorrectionRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    corrected_statement:str=Field(min_length=1,max_length=10000)
    reason:str=Field(min_length=1,max_length=5000)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @field_validator("corrected_statement")
    @classmethod
    def validate_corrected_statement(cls,value:str)->str:
        if not value.strip():
            raise ValueError("corrected_statement cannot be empty.")
        return value
    @field_validator("reason")
    @classmethod
    def validate_reason(cls,value:str)->str:
        if not value.strip():
            raise ValueError("reason cannot be empty.")
        return value  
class MemoryCorrectionResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    subject_id:str=Field(min_length=1,max_length=128)
    action:str=Field(min_length=1,max_length=64)
    target_memory_id:str=Field(min_length=1,max_length=128)
    corrected_memory_id:Optional[str]=Field(default=None,max_length=128)
    corrected_memory_status:str=Field(min_length=1,max_length=64)
    changed:bool
    effective_at:datetime
    correlation_id:str=Field(min_length=1,max_length=128)
    reason:str=Field(min_length=1,max_length=5000)
    metadata:dict[str,Any]=Field(default_factory=dict)

class MemoryDeletionRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    reason:str=Field(min_length=1,max_length=5000)
    metadata:dict[str,Any]=Field(default_factory=dict)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls,value:str)->str:
        if not value.strip():
            raise ValueError("reason cannot be empty.")
        return value
class MemoryDeletionResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    subject_id:str=Field(min_length=1,max_length=128)
    action:str=Field(min_length=1,max_length=64)
    memory_id:str=Field(min_length=1,max_length=128)
    memory_status:str=Field(min_length=1,max_length=64)
    changed:bool
    effective_at:datetime
    correlation_id:str=Field(min_length=1,max_length=128)
    reason:str=Field(min_length=1,max_length=5000)
    metadata:dict[str,Any]=Field(default_factory=dict)        
    
class MemoryConsentControlRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    action:ConsentControlAction
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_action(self):
        allowed={
            ConsentControlAction.OPT_IN,
            ConsentControlAction.OPT_OUT,
            ConsentControlAction.PAUSE,
            ConsentControlAction.RESUME
        }
        if self.action not in allowed:
            raise ValueError(
                "Only opt_in, opt_out, pause, and resume are valid consent control actions."
            )
        return self
class MemoryConsentControlResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    subject_id:str=Field(min_length=1,max_length=128)
    action:str=Field(min_length=1,max_length=64)
    previous_state:str=Field(min_length=1,max_length=32)
    current_state:str=Field(min_length=1,max_length=32)
    changed:bool
    correlation_id:str=Field(min_length=1,max_length=128)
    timestamp:datetime
    reason:str=Field(min_length=1,max_length=1000)
    metadata:dict[str,Any]=Field(default_factory=dict)
    
class MemoryLifecycleRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    action:MemoryLifecycleAction
    memory_id:Optional[str]=Field(default=None,max_length=128)
    target_memory_id:Optional[str]=Field(default=None,max_length=128)
    effective_at:Optional[datetime]=None
    reason:str=Field(min_length=1,max_length=5000)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_action_requirements(self):
        if self.action==MemoryLifecycleAction.CORRECT:
            if not self.target_memory_id:
                raise ValueError(
                    "target_memory_id is required for correct."
                )
        elif self.action==MemoryLifecycleAction.DELETE:
            if not self.memory_id:
                raise ValueError(
                    "memory_id is required for delete."
                )
        else:
            raise ValueError(
                "This endpoint currently supports only correct and delete actions."
            )
        if self.effective_at is not None:
            if (
                self.effective_at.tzinfo is None
                or self.effective_at.utcoffset() is None
            ):
                raise ValueError(
                    "effective_at must be timezone-aware."
                )
        return self
class MemoryLifecycleResponseV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    status:str=Field(min_length=1,max_length=32)
    subject_id:str=Field(min_length=1,max_length=128)
    action:str=Field(min_length=1,max_length=64)
    memory_id:Optional[str]=Field(default=None,max_length=128)
    created_memory_id:Optional[str]=Field(default=None,max_length=128)
    previous_memory_id:Optional[str]=Field(default=None,max_length=128)
    memory_status:str=Field(min_length=1,max_length=64)
    changed:bool
    effective_at:datetime
    correlation_id:str=Field(min_length=1,max_length=128)
    reason:str=Field(min_length=1,max_length=5000)
    metadata:dict[str,Any]=Field(default_factory=dict)

class MemorySearchRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    intent: str = Field(min_length=1, max_length=10000)
    surface: str = Field(min_length=1, max_length=64)
    locale: str = Field(min_length=2, max_length=32)
    requested_at: datetime
    top_k: int = Field(default=5, ge=1, le=50)
    candidate_limit: int = Field(default=50, ge=1, le=200)
    vector_weight: float = Field(default=0.55, ge=0.0, le=1.0)
    graph_weight: float = Field(default=0.45, ge=0.0, le=1.0)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("intent cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_request(self):
        if (
            self.requested_at.tzinfo is None
            or self.requested_at.utcoffset() is None
        ):
            raise ValueError(
                "requested_at must be timezone-aware."
            )

        if self.vector_weight + self.graph_weight <= 0:
            raise ValueError(
                "vector_weight and graph_weight cannot both be zero."
            )

        return self
class MemorySearchResponseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    decision: str
    subject_id: str
    query_intent: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    graph_candidate_count: int = Field(ge=0)
    vector_candidate_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    retrieval_version: str
    correlation_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)    