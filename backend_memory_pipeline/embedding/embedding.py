from datetime import datetime,timezone
from enum import Enum
from typing import Any,Optional,Protocol
import hashlib
import math
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel,ConfigDict,Field,model_validator
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
class EmbeddingOperation(str,Enum):
    CREATE="create"
    UPDATE="update"
    DELETE="delete"
    SKIP="skip"
class EmbeddingErrorCode(str,Enum):
    INVALID_MEMORY="INVALID_MEMORY"
    EMBEDDING_NOT_ELIGIBLE="EMBEDDING_NOT_ELIGIBLE"
    MEMORY_DELETED="MEMORY_DELETED"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    INVALID_PROVIDER="INVALID_PROVIDER"
    DIMENSION_MISMATCH="DIMENSION_MISMATCH"
    EMBEDDING_NOT_FOUND="EMBEDDING_NOT_FOUND"
    EMBEDDING_CONFLICT="EMBEDDING_CONFLICT"
class EmbeddingError(Exception):
    def __init__(self,code:EmbeddingErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class EmbeddingRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    approved_text_fields:list[str]=Field(min_length=1)
    model_name:str=Field(min_length=1,max_length=256)
    model_version:str=Field(min_length=1,max_length=128)
    dimensions:int=Field(gt=0,le=8192)
    requested_at:datetime
    correlation_id:str=Field(min_length=1,max_length=128)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_request(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware.")
        if not self.approved_text_fields:
            raise ValueError("approved_text_fields cannot be empty.")
        return self
class EmbeddingRecordV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    embedding_id:str=Field(min_length=1,max_length=256)
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    vector:list[float]=Field(min_length=1)
    dimensions:int=Field(gt=0,le=8192)
    model_name:str=Field(min_length=1,max_length=256)
    model_version:str=Field(min_length=1,max_length=128)
    approved_text_fields:list[str]=Field(min_length=1)
    content_hash:str=Field(min_length=1,max_length=128)
    memory_status:MemoryStatus
    retrieval_eligible:bool
    embedding_eligible:bool
    source_event_ids:list[str]=Field(default_factory=list,min_length=1)
    source_session_ids:list[str]=Field(default_factory=list)
    recorded_at:datetime
    created_at:datetime
    deleted:bool=False
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_record(self):
        if self.dimensions!=len(self.vector):
            raise ValueError("dimensions must match vector length.")
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware.")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware.")
        if self.memory_status in {MemoryStatus.DELETED,MemoryStatus.PENDING_DELETION}:
            if not self.deleted and not self.retrieval_eligible and not self.embedding_eligible:
                return self
        return self
class EmbeddingWriteResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    operation:EmbeddingOperation
    embedding_id:str
    memory_id:str
    subject_id:str
    changed:bool
    dimensions:int
    model_name:str
    model_version:str
    content_hash:str
    embedding_record:Optional[EmbeddingRecordV1]=None
    metadata:dict[str,Any]=Field(default_factory=dict)
class EmbeddingProvider(Protocol):
    def embed(self,text:str,model_name:str,model_version:str,dimensions:int)->list[float]:
        ...
class DeterministicEmbeddingProvider:
    def embed(self,text:str,model_name:str,model_version:str,dimensions:int)->list[float]:
        if not text.strip():
            raise EmbeddingError(EmbeddingErrorCode.INVALID_PROVIDER,"Embedding text cannot be empty.")
        seed=f"{model_name}:{model_version}:{text}".encode("utf-8")
        values=[]
        counter=0
        while len(values)<dimensions:
            digest=hashlib.sha256(seed+counter.to_bytes(4,"big")).digest()
            for index in range(0,len(digest),4):
                if len(values)>=dimensions:
                    break
                integer=int.from_bytes(digest[index:index+4],"big")
                value=(integer/4294967295.0)*2.0-1.0
                values.append(value)
            counter+=1
        norm=math.sqrt(sum(value*value for value in values))
        if norm==0:
            return [0.0]*dimensions
        return [value/norm for value in values]
class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed(self,text: str,model_name: str,
        model_version: str,dimensions: int) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError(
                EmbeddingErrorCode.INVALID_PROVIDER,"Embedding text cannot be empty.")
        if model_name != self.model_name:
            raise EmbeddingError(EmbeddingErrorCode.INVALID_PROVIDER,
                f"Provider is configured for model '{self.model_name}', "
                f"but received '{model_name}'.")
        vector = self.model.encode(text,normalize_embeddings=True)
        vector = vector.tolist()
        if len(vector) != dimensions:
            raise EmbeddingError(EmbeddingErrorCode.DIMENSION_MISMATCH,
                "SentenceTransformer returned an unexpected vector dimension.")
        return vector    
class EmbeddingStore(Protocol):
    def get(self,memory_id:str)->Optional[EmbeddingRecordV1]:
        ...
    def upsert(self,record:EmbeddingRecordV1)->bool:
        ...
    def delete(self,memory_id:str,subject_id:str)->bool:
        ...
class InMemoryEmbeddingStore:
    def __init__(self):
        self._records:dict[str,EmbeddingRecordV1]={}
    def get(self,memory_id:str)->Optional[EmbeddingRecordV1]:
        return self._records.get(memory_id)
    def upsert(self,record:EmbeddingRecordV1)->bool:
        existing=self._records.get(record.memory_id)
        changed=existing is None or existing.model_dump()!=record.model_dump()
        if changed:
            self._records[record.memory_id]=record
        return changed
    def delete(self,memory_id:str,subject_id:str)->bool:
        existing=self._records.get(memory_id)
        if existing is None:
            return False
        if existing.subject_id!=subject_id:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "Embedding does not belong to the requested subject."
            )
        del self._records[memory_id]
        return True
    def all(self)->list[EmbeddingRecordV1]:
        return list(self._records.values())
class EmbeddingService:
    def __init__(
        self,
        store:Optional[EmbeddingStore]=None,
        provider:Optional[EmbeddingProvider]=None
    ):
        self.store=store or InMemoryEmbeddingStore()
        self.provider=provider or DeterministicEmbeddingProvider()
    def upsert_memory_embedding(
        self,
        memory:MemoryRecordV1,
        model_name:str="all-MiniLM-L6-v2",
        model_version:str="v1",
        dimensions:int=384,
        approved_text_fields:Optional[list[str]]=None,
        correlation_id:str="embedding-correlation"
    )->EmbeddingWriteResultV1:
        self._validate_memory(memory)
        if memory.status in {MemoryStatus.DELETED,MemoryStatus.PENDING_DELETION}:
            raise EmbeddingError(
                EmbeddingErrorCode.MEMORY_DELETED,
                "Deleted or pending-deletion memory cannot receive a new embedding."
            )
        if not memory.embedding_eligible:
            raise EmbeddingError(
                EmbeddingErrorCode.EMBEDDING_NOT_ELIGIBLE,
                "Memory is not eligible for embedding."
            )
        approved_text_fields=approved_text_fields or ["normalized_fact"]
        text=self._build_approved_text(memory,approved_text_fields)
        content_hash=self._content_hash(text,model_name,model_version,approved_text_fields)
        existing=self.store.get(memory.memory_id)
        if existing is not None:
            if existing.subject_id!=memory.subject_id or existing.subject_scope!=memory.subject_scope:
                raise EmbeddingError(
                    EmbeddingErrorCode.SUBJECT_MISMATCH,
                    "Existing embedding belongs to another subject."
                )
            if (
                existing.content_hash==content_hash
                and existing.model_name==model_name
                and existing.model_version==model_version
                and existing.dimensions==dimensions
                and existing.embedding_eligible==memory.embedding_eligible
                and existing.memory_status==memory.status
            ):
                return EmbeddingWriteResultV1(
                    operation=EmbeddingOperation.UPDATE,
                    embedding_id=existing.embedding_id,
                    memory_id=memory.memory_id,
                    subject_id=memory.subject_id,
                    changed=False,
                    dimensions=existing.dimensions,
                    model_name=existing.model_name,
                    model_version=existing.model_version,
                    content_hash=existing.content_hash,
                    embedding_record=existing,
                    metadata={"idempotent":True}
                )
        vector=self.provider.embed(
            text=text,
            model_name=model_name,
            model_version=model_version,
            dimensions=dimensions
        )
        if len(vector)!=dimensions:
            raise EmbeddingError(
                EmbeddingErrorCode.DIMENSION_MISMATCH,
                "Embedding provider returned an unexpected vector dimension."
            )
        embedding_id=existing.embedding_id if existing is not None else f"embedding:{memory.memory_id}"
        record=EmbeddingRecordV1(
            embedding_id=embedding_id,
            memory_id=memory.memory_id,
            subject_id=memory.subject_id,
            subject_scope=memory.subject_scope,
            vector=vector,
            dimensions=dimensions,
            model_name=model_name,
            model_version=model_version,
            approved_text_fields=approved_text_fields,
            content_hash=content_hash,
            memory_status=memory.status,
            retrieval_eligible=memory.retrieval_eligible,
            embedding_eligible=memory.embedding_eligible,
            source_event_ids=list(memory.source_event_ids),
            source_session_ids=list(memory.source_session_ids),
            recorded_at=memory.recorded_at,
            created_at=memory.created_at,
            deleted=False,
            metadata={
                **memory.metadata,
                "correlation_id":correlation_id
            }
        )
        changed=self.store.upsert(record)
        operation=EmbeddingOperation.CREATE if existing is None else EmbeddingOperation.UPDATE
        return EmbeddingWriteResultV1(
            operation=operation,
            embedding_id=record.embedding_id,
            memory_id=record.memory_id,
            subject_id=record.subject_id,
            changed=changed,
            dimensions=record.dimensions,
            model_name=record.model_name,
            model_version=record.model_version,
            content_hash=record.content_hash,
            embedding_record=record,
            metadata={
                "approved_text_fields":record.approved_text_fields,
                "memory_status":record.memory_status.value
            }
        )
    '''
    def delete_memory_embedding(self,memory_id:str,subject_id:str)->EmbeddingWriteResultV1:
        existing=self.store.get(memory_id)
        if existing is None:
           return EmbeddingWriteResultV1(
              operation=EmbeddingOperation.DELETE,
              embedding_id=f"embedding:{memory_id}",
              memory_id=memory_id,
              subject_id=subject_id,
              changed=False,
              dimensions=0,
              model_name="",
              model_version="",
              content_hash="",
              embedding_record=None,
              metadata={
                "deletion_propagation":True,
                "idempotent":True,
                "already_absent":True})
            
        
        if existing.subject_id!=subject_id or existing.subject_scope!=subject_id:
           raise EmbeddingError(
              EmbeddingErrorCode.SUBJECT_MISMATCH,
              "Embedding does not belong to the requested subject.")
        
        changed=self.store.delete(memory_id,subject_id)
        return EmbeddingWriteResultV1(
            operation=EmbeddingOperation.DELETE,
            embedding_id=existing.embedding_id,
            memory_id=memory_id,
            subject_id=subject_id,
            changed=changed,
            dimensions=existing.dimensions,
            model_name=existing.model_name,
            model_version=existing.model_version,
            content_hash=existing.content_hash,
            embedding_record=None,
            metadata={"deletion_propagation":True})
    '''
    
    def delete_memory_embedding(self,memory_id:str,subject_id:str)->EmbeddingWriteResultV1:
        existing=self.store.get(memory_id)
        if existing is None:
            raise EmbeddingError(
                EmbeddingErrorCode.EMBEDDING_NOT_FOUND,
                f"Embedding for memory {memory_id} was not found."
            )
        if existing.subject_id!=subject_id or existing.subject_scope!=subject_id:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "Embedding does not belong to the requested subject."
            )
        changed=self.store.delete(memory_id,subject_id)
        return EmbeddingWriteResultV1(
            operation=EmbeddingOperation.DELETE,
            embedding_id=existing.embedding_id,
            memory_id=memory_id,
            subject_id=subject_id,
            changed=changed,
            dimensions=existing.dimensions,
            model_name=existing.model_name,
            model_version=existing.model_version,
            content_hash=existing.content_hash,
            embedding_record=None,
            metadata={"deletion_propagation":True})
        
    def get_memory_embedding(self,memory_id:str,subject_id:str)->EmbeddingRecordV1:
        record=self.store.get(memory_id)
        if record is None:
            raise EmbeddingError(
                EmbeddingErrorCode.EMBEDDING_NOT_FOUND,
                f"Embedding for memory {memory_id} was not found."
            )
        if record.subject_id!=subject_id or record.subject_scope!=subject_id:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "Embedding does not belong to the requested subject."
            )
        return record
    @staticmethod
    def _build_approved_text(memory:MemoryRecordV1,approved_text_fields:list[str])->str:
        supported_fields={
            "normalized_fact":memory.normalized_fact
        }
        values=[]
        for field_name in approved_text_fields:
            if field_name not in supported_fields:
                raise EmbeddingError(
                    EmbeddingErrorCode.INVALID_MEMORY,
                    f"Unsupported approved embedding field: {field_name}"
                )
            value=supported_fields[field_name]
            if value is not None and str(value).strip():
                values.append(str(value).strip())
        text=" ".join(values).strip()
        if not text:
            raise EmbeddingError(
                EmbeddingErrorCode.INVALID_MEMORY,
                "Approved embedding fields produced empty text."
            )
        return text
    @staticmethod
    def _content_hash(text:str,model_name:str,model_version:str,approved_text_fields:list[str])->str:
        payload=f"{model_name}|{model_version}|{'|'.join(approved_text_fields)}|{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    @staticmethod
    def _validate_memory(memory:MemoryRecordV1)->None:
        if not isinstance(memory,MemoryRecordV1):
            raise EmbeddingError(
                EmbeddingErrorCode.INVALID_MEMORY,
                "Input must be a MemoryRecordV1."
            )
        if not memory.subject_id.strip() or not memory.subject_scope.strip():
            raise EmbeddingError(
                EmbeddingErrorCode.INVALID_MEMORY,
                "Memory subject identity and scope are required."
            )
        if memory.subject_id!=memory.subject_scope:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "Memory subject scope must match subject identity."
            )