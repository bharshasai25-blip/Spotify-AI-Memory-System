from enum import Enum
from typing import Any,Optional
from pydantic import BaseModel,ConfigDict,Field
from backend_memory_pipeline.ingestion.ingestion import ConsentState,EventType,InteractionEventV1
class ValidationStatus(str,Enum):
    VALID="valid"
    REJECTED="rejected"
class EventValidationErrorCode(str,Enum):
    INVALID_EVENT="INVALID_EVENT"
    UNSUPPORTED_SCHEMA_VERSION="UNSUPPORTED_SCHEMA_VERSION"
    INVALID_SUBJECT_SCOPE="INVALID_SUBJECT_SCOPE"
    INVALID_TIMESTAMP="INVALID_TIMESTAMP"
    INVALID_EVENT_TYPE="INVALID_EVENT_TYPE"
    INVALID_CONSENT_STATE="INVALID_CONSENT_STATE"
    INVALID_SOURCE="INVALID_SOURCE"
    INVALID_TEXT="INVALID_TEXT"
    INVALID_ENTITY="INVALID_ENTITY"
    UNSUPPORTED_CLAIM="UNSUPPORTED_CLAIM"
    PROHIBITED_CONTENT="PROHIBITED_CONTENT"
    INVALID_METADATA="INVALID_METADATA"
class EventValidationError(Exception):
    def __init__(self,code:EventValidationErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class EventValidationResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    status:ValidationStatus
    event_id:str
    subject_id:str
    event_type:EventType
    errors:list[str]=Field(default_factory=list)
    warnings:list[str]=Field(default_factory=list)
    safe_for_extraction:bool=False
class EventValidator:
    SUPPORTED_SCHEMA_VERSIONS=frozenset({"1.0"})
    SUPPORTED_EVENT_TYPES=frozenset(EventType)
    SUPPORTED_CONSENT_STATES=frozenset(ConsentState)
    def validate(self,event:InteractionEventV1)->EventValidationResult:
        errors=[]
        warnings=[]
        if not isinstance(event,InteractionEventV1):
            raise EventValidationError(EventValidationErrorCode.INVALID_EVENT,"Input must be an InteractionEventV1.")
        if event.schema_version not in self.SUPPORTED_SCHEMA_VERSIONS:
            errors.append("Unsupported schema version.")
        if not event.subject_id.strip():
            errors.append("Subject identity is required.")
        if not event.subject_scope.strip():
            errors.append("Subject scope is required.")
        if event.subject_scope!=event.subject_id:
            errors.append("Subject scope does not match event subject.")
        if event.timestamp.tzinfo is None or event.timestamp.utcoffset() is None:
            errors.append("Event timestamp must be timezone-aware.")
        if event.event_type not in self.SUPPORTED_EVENT_TYPES:
            errors.append("Unsupported event type.")
        if event.consent_state not in self.SUPPORTED_CONSENT_STATES:
            errors.append("Invalid consent state.")
        if not event.source.strip():
            errors.append("Source is required.")
        if event.event_type==EventType.AI_INTERACTION:
            if event.text is None or not event.text.strip():
                errors.append("AI interaction requires non-empty text.")
        if event.event_type==EventType.PLAYBACK:
            playback_action=event.metadata.get("playback_action")
            if playback_action not in {"play","pause"}:
                errors.append("playback_action must be play or pause for playback events.")        
        if event.text is not None:
            if len(event.text)>50000:
                errors.append("Event text exceeds maximum supported length.")
        if event.entity is not None:
            if not isinstance(event.entity,dict):
                errors.append("Entity payload must be an object.")
            else:
                entity_errors=self._validate_entity(event.entity)
                errors.extend(entity_errors)
        if not isinstance(event.context_entities,dict):
            errors.append("context_entities must be an object.")
        if not isinstance(event.metadata,dict):
            errors.append("metadata must be an object.")
        self._validate_metadata(event.metadata,errors,warnings)
        if errors:
            return EventValidationResult(
                status=ValidationStatus.REJECTED,
                event_id=event.event_id,
                subject_id=event.subject_id,
                event_type=event.event_type,
                errors=errors,
                warnings=warnings,
                safe_for_extraction=False
            )
        return EventValidationResult(
            status=ValidationStatus.VALID,
            event_id=event.event_id,
            subject_id=event.subject_id,
            event_type=event.event_type,
            errors=[],
            warnings=warnings,
            safe_for_extraction=True
        )
    def validate_or_raise(self,event:InteractionEventV1)->EventValidationResult:
        result=self.validate(event)
        if result.status==ValidationStatus.REJECTED:
            raise EventValidationError(EventValidationErrorCode.INVALID_EVENT,"; ".join(result.errors))
        return result
    def _validate_entity(self,entity:dict[str,Any])->list[str]:
        errors=[]
        allowed_fields={"entity_id","entity_type","name","canonical_id","source","confidence"}
        unknown=set(entity)-allowed_fields
        if unknown:
            errors.append(f"Unsupported entity fields: {sorted(unknown)}.")
        if "entity_type" in entity and not isinstance(entity["entity_type"],str):
            errors.append("entity_type must be a string.")
        if "confidence" in entity:
            confidence=entity["confidence"]
            if not isinstance(confidence,(int,float)) or not 0<=confidence<=1:
                errors.append("Entity confidence must be between 0 and 1.")
        return errors
    def _validate_metadata(self,metadata:dict[str,Any],errors:list[str],warnings:list[str])->None:
        forbidden_keys={"password","token","secret","api_key","access_token","refresh_token"}
        found=forbidden_keys.intersection(metadata.keys())
        if found:
            errors.append(f"Sensitive credential fields are not allowed in event metadata: {sorted(found)}.")
        if len(metadata)>100:
            warnings.append("Metadata contains a large number of fields.")
class EventValidationService:
    def __init__(self,validator:Optional[EventValidator]=None):
        self.validator=validator or EventValidator()
    def validate(self,event:InteractionEventV1)->EventValidationResult:
        return self.validator.validate(event)
    def validate_or_raise(self,event:InteractionEventV1)->EventValidationResult:
        return self.validator.validate_or_raise(event)