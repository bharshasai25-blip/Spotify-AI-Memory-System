from datetime import datetime
from typing import Any,Optional

from pydantic import BaseModel,ConfigDict,Field,field_validator


class MCPBaseModel(BaseModel):
    model_config=ConfigDict(
        extra="forbid"
    )


class SearchMemoryInput(MCPBaseModel):
    query:str=Field(
        min_length=1,
        max_length=10000
    )
    surface:str=Field(
        min_length=1,
        max_length=64
    )
    locale:str=Field(
        min_length=2,
        max_length=32
    )
    requested_at:datetime
    max_items:int=Field(
        default=5,
        ge=1,
        le=20
    )
    max_characters:int=Field(
        default=10000,
        ge=1,
        le=50000
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls,value:str)->str:
        if not value.strip():
            raise ValueError("query cannot be empty.")
        return value

    @field_validator("surface")
    @classmethod
    def validate_surface(cls,value:str)->str:
        if not value.strip():
            raise ValueError("surface cannot be empty.")
        return value

    @field_validator("locale")
    @classmethod
    def validate_locale(cls,value:str)->str:
        if not value.strip():
            raise ValueError("locale cannot be empty.")
        return value

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls,value:datetime)->datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "requested_at must be timezone-aware."
            )
        return value


class SearchMemoryOutput(MCPBaseModel):
    schema_version:str="1.0"
    decision:str
    context_items:list[dict[str,Any]]
    memory_grounded:bool
    correlation_id:str


class AddExplicitPreferenceInput(MCPBaseModel):
    preference:str=Field(
        min_length=1,
        max_length=10000
    )
    session_id:str=Field(
        min_length=1,
        max_length=128
    )
    surface:str=Field(
        min_length=1,
        max_length=64
    )
    locale:str=Field(
        min_length=2,
        max_length=32
    )
    effective_at:datetime
    entity:Optional[dict[str,Any]]=None
    context_entities:Optional[dict[str,Any]]=None
    metadata:dict[str,Any]=Field(
        default_factory=dict
    )

    @field_validator("preference")
    @classmethod
    def validate_preference(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "preference cannot be empty."
            )
        return value

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "session_id cannot be empty."
            )
        return value

    @field_validator("surface")
    @classmethod
    def validate_surface(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "surface cannot be empty."
            )
        return value

    @field_validator("locale")
    @classmethod
    def validate_locale(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "locale cannot be empty."
            )
        return value

    @field_validator("effective_at")
    @classmethod
    def validate_effective_at(cls,value:datetime)->datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "effective_at must be timezone-aware."
            )
        return value


class AddExplicitPreferenceOutput(MCPBaseModel):
    schema_version:str="1.0"
    accepted:bool
    memory_ids:list[str]
    correlation_id:str


class CorrectMemoryInput(MCPBaseModel):
    memory_id:str=Field(
        min_length=1,
        max_length=128
    )
    corrected_statement:str=Field(
        min_length=1,
        max_length=10000
    )
    session_id:str=Field(
        min_length=1,
        max_length=128
    )
    reason:str=Field(
        min_length=1,
        max_length=2000
    )
    surface:str=Field(
        min_length=1,
        max_length=64
    )
    locale:str=Field(
        min_length=2,
        max_length=32
    )
    effective_at:datetime
    metadata:dict[str,Any]=Field(
        default_factory=dict
    )

    @field_validator(
        "memory_id",
        "corrected_statement",
        "session_id",
        "reason",
        "surface",
        "locale"
    )
    @classmethod
    def validate_non_empty(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "value cannot be empty."
            )
        return value

    @field_validator("effective_at")
    @classmethod
    def validate_effective_at(cls,value:datetime)->datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "effective_at must be timezone-aware."
            )
        return value


class CorrectMemoryOutput(MCPBaseModel):
    schema_version:str="1.0"
    corrected:bool
    target_memory_id:str
    replacement_memory_id:Optional[str]=None
    correlation_id:str


class DeleteMemoryInput(MCPBaseModel):
    memory_id:str=Field(
        min_length=1,
        max_length=128
    )
    reason:str=Field(
        min_length=1,
        max_length=2000
    )
    effective_at:datetime
    metadata:dict[str,Any]=Field(
        default_factory=dict
    )

    @field_validator("memory_id","reason")
    @classmethod
    def validate_non_empty(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "value cannot be empty."
            )
        return value

    @field_validator("effective_at")
    @classmethod
    def validate_effective_at(cls,value:datetime)->datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "effective_at must be timezone-aware."
            )
        return value


class DeleteMemoryOutput(MCPBaseModel):
    schema_version:str="1.0"
    deleted:bool
    memory_id:str
    correlation_id:str


class ExplainMemoryUseInput(MCPBaseModel):
    memory_id:str=Field(
        min_length=1,
        max_length=128
    )
    current_intent:Optional[str]=Field(
        default=None,
        max_length=10000
    )
    surface:str=Field(
        min_length=1,
        max_length=64
    )
    locale:str=Field(
        min_length=2,
        max_length=32
    )

    @field_validator("memory_id","surface","locale")
    @classmethod
    def validate_non_empty(cls,value:str)->str:
        if not value.strip():
            raise ValueError(
                "value cannot be empty."
            )
        return value

    @field_validator("current_intent")
    @classmethod
    def validate_current_intent(
        cls,
        value:Optional[str]
    )->Optional[str]:
        if value is not None and not value.strip():
            return None
        return value


class ExplainMemoryUseOutput(MCPBaseModel):
    schema_version:str="1.0"
    memory_id:str
    subject_id:str
    explanation:str
    relevance_reason:Optional[str]=None
    source:Optional[str]=None
    confidence:Optional[float]=Field(
        default=None,
        ge=0.0,
        le=1.0
    )
    timestamp:Optional[datetime]=None
    correlation_id:str