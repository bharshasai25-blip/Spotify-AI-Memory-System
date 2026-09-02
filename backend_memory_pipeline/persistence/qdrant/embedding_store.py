import json
from datetime import datetime
from typing import Any,Optional,Protocol
from uuid import NAMESPACE_URL,uuid5
from qdrant_client import QdrantClient
from qdrant_client.models import Distance,FieldCondition,Filter,MatchValue,PointStruct,ScoredPoint,VectorParams
from backend_memory_pipeline.embedding.embedding import EmbeddingRecordV1,EmbeddingStore,EmbeddingError,EmbeddingErrorCode
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryStatus
class VectorSearchResultV1:
    def __init__(self,record:EmbeddingRecordV1,score:float):
        self.record=record
        self.score=float(score)
class VectorSearchStore(Protocol):
    def search(
        self,
        query_vector:list[float],
        subject_id:str,
        subject_scope:str,
        limit:int=50
    )->list[VectorSearchResultV1]:
        ...
class QdrantEmbeddingStore:
    def __init__(
        self,
        url:str="http://localhost:6333",
        collection_name:str="spotify_memory_embeddings",
        dimensions:int=384
    ):
        self.url=url
        self.collection_name=collection_name
        self.dimensions=dimensions
        self.client=QdrantClient(url=self.url)
    def verify_connectivity(self)->None:
        try:
            self.client.get_collections()
        except Exception as exc:
            raise RuntimeError(f"Qdrant connectivity check failed: {exc}") from exc
    def ensure_collection(self,dimensions:Optional[int]=None)->None:
        dimensions=dimensions or self.dimensions
        try:
            collections=self.client.get_collections().collections
            existing_names={collection.name for collection in collections}
            if self.collection_name in existing_names:
                collection_info=self.client.get_collection(self.collection_name)
                existing_dimensions=collection_info.config.params.vectors.size
                if existing_dimensions!=dimensions:
                    raise EmbeddingError(
                        EmbeddingErrorCode.DIMENSION_MISMATCH,
                        f"Qdrant collection '{self.collection_name}' has dimension {existing_dimensions}, expected {dimensions}."
                    )
                self._ensure_payload_indexes()
                return
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=dimensions,
                    distance=Distance.COSINE
                )
            )
            self._ensure_payload_indexes()
        except EmbeddingError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Qdrant collection initialization failed: {exc}") from exc
    def _ensure_payload_indexes(self)->None:
        indexed_fields=[
            ("subject_id","keyword"),
            ("subject_scope","keyword"),
            ("memory_status","keyword"),
            ("retrieval_eligible","bool"),
            ("embedding_eligible","bool"),
            ("deleted","bool")
        ]
        for field_name,field_schema in indexed_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_schema
                )
            except Exception:
                pass
    def get(self,memory_id:str)->Optional[EmbeddingRecordV1]:
        point_id=self._point_id(memory_id)
        try:
            points=self.client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_payload=True,
                with_vectors=True
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant embedding retrieval failed: {exc}") from exc
        if not points:
            return None
        return self._point_to_record(points[0])
    def upsert(self,record:EmbeddingRecordV1)->bool:
        if record.dimensions!=self.dimensions:
            raise EmbeddingError(
                EmbeddingErrorCode.DIMENSION_MISMATCH,
                f"Embedding dimensions {record.dimensions} do not match Qdrant collection dimensions {self.dimensions}."
            )
        existing=self.get(record.memory_id)
        if existing is not None:
            if existing.subject_id!=record.subject_id or existing.subject_scope!=record.subject_scope:
                raise EmbeddingError(
                    EmbeddingErrorCode.SUBJECT_MISMATCH,
                    "Embedding does not belong to the requested subject."
                )
            if existing.model_dump()==record.model_dump():
                return False
        point=PointStruct(
            id=self._point_id(record.memory_id),
            vector=record.vector,
            payload=self._record_to_payload(record)
        )
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
                wait=True
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant embedding upsert failed: {exc}") from exc
        return True
    def delete(self,memory_id:str,subject_id:str)->bool:
        existing=self.get(memory_id)
        if existing is None:
            return False
        if existing.subject_id!=subject_id or existing.subject_scope!=subject_id:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "Embedding does not belong to the requested subject."
            )
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[self._point_id(memory_id)],
                wait=True
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant embedding deletion failed: {exc}") from exc
        return True
    def all(self)->list[EmbeddingRecordV1]:
        try:
            records,_=self.client.scroll(
                collection_name=self.collection_name,
                limit=10000,
                with_payload=True,
                with_vectors=True
            )
        except Exception as exc:
            raise RuntimeError(f"Qdrant embedding scan failed: {exc}") from exc
        return [self._point_to_record(point) for point in records]
    def search(
        self,
        query_vector:list[float],
        subject_id:str,
        subject_scope:str,
        limit:int=50
    )->list[VectorSearchResultV1]:
        if not query_vector:
            raise EmbeddingError(
                EmbeddingErrorCode.INVALID_PROVIDER,
                "Query vector cannot be empty."
            )
        if len(query_vector)!=self.dimensions:
            raise EmbeddingError(
                EmbeddingErrorCode.DIMENSION_MISMATCH,
                f"Query vector dimensions {len(query_vector)} do not match Qdrant collection dimensions {self.dimensions}."
            )
        if not subject_id or not subject_scope:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "subject_id and subject_scope are required for vector search."
            )
        if subject_id!=subject_scope:
            raise EmbeddingError(
                EmbeddingErrorCode.SUBJECT_MISMATCH,
                "subject_scope must match subject_id."
            )
        if limit<1:
            raise ValueError("limit must be at least 1.")
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="subject_id",
                    match=MatchValue(value=subject_id)
                ),
                FieldCondition(
                    key="subject_scope",
                    match=MatchValue(value=subject_scope)
                ),
                FieldCondition(
                    key="memory_status",
                    match=MatchValue(value=MemoryStatus.ACTIVE.value)
                ),
                FieldCondition(
                    key="retrieval_eligible",
                    match=MatchValue(value=True)
                ),
                FieldCondition(
                    key="embedding_eligible",
                    match=MatchValue(value=True)
                ),
                FieldCondition(
                    key="deleted",
                    match=MatchValue(value=False)
                )
            ]
        )
        try:
            points=self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=True
            ).points
        except Exception as exc:
            raise RuntimeError(f"Qdrant vector search failed: {exc}") from exc
        results=[]
        for point in points:
            record=self._point_to_record(point)
            if record.subject_id!=subject_id or record.subject_scope!=subject_scope:
                raise EmbeddingError(
                    EmbeddingErrorCode.SUBJECT_MISMATCH,
                    "Qdrant returned an embedding belonging to a different subject."
                )
            if record.memory_status!=MemoryStatus.ACTIVE:
                continue
            if not record.retrieval_eligible:
                continue
            if not record.embedding_eligible:
                continue
            if record.deleted:
                continue
            results.append(
                VectorSearchResultV1(
                    record=record,
                    score=max(0.0,min(1.0,float(point.score)))
                )
            )
        return results
    def close(self)->None:
        self.client.close()
    @staticmethod
    def _point_id(memory_id:str)->str:
        return str(uuid5(NAMESPACE_URL,f"spotify-memory-embedding:{memory_id}"))
    @staticmethod
    def _record_to_payload(record:EmbeddingRecordV1)->dict[str,Any]:
        return {
            "embedding_id":record.embedding_id,
            "memory_id":record.memory_id,
            "subject_id":record.subject_id,
            "subject_scope":record.subject_scope,
            "dimensions":record.dimensions,
            "model_name":record.model_name,
            "model_version":record.model_version,
            "approved_text_fields":list(record.approved_text_fields),
            "content_hash":record.content_hash,
            "memory_status":record.memory_status.value,
            "retrieval_eligible":record.retrieval_eligible,
            "embedding_eligible":record.embedding_eligible,
            "source_event_ids":list(record.source_event_ids),
            "source_session_ids":list(record.source_session_ids),
            "recorded_at":record.recorded_at.isoformat(),
            "created_at":record.created_at.isoformat(),
            "deleted":record.deleted,
            "metadata_json":json.dumps(record.metadata,default=str)
        }
    @staticmethod
    def _point_to_record(point:ScoredPoint)->EmbeddingRecordV1:
        payload=dict(point.payload or {})
        print("===== QDRANT PAYLOAD DEBUG =====")
        print(payload)
        vector=list(point.vector or [])
        metadata_json=payload.get("metadata_json","{}")
        try:
            metadata=json.loads(metadata_json)
        except (TypeError,json.JSONDecodeError):
            metadata={}
        return EmbeddingRecordV1(
            embedding_id=payload["embedding_id"],
            memory_id=payload["memory_id"],
            subject_id=payload["subject_id"],
            subject_scope=payload["subject_scope"],
            vector=[float(value) for value in vector],
            dimensions=int(payload["dimensions"]),
            model_name=payload["model_name"],
            model_version=payload["model_version"],
            approved_text_fields=list(payload["approved_text_fields"]),
            content_hash=payload["content_hash"],
            memory_status=MemoryStatus(payload["memory_status"]),
            retrieval_eligible=bool(payload["retrieval_eligible"]),
            embedding_eligible=bool(payload["embedding_eligible"]),
            source_event_ids=list(payload.get("source_event_ids",[])),
            source_session_ids=list(payload.get("source_session_ids",[])),
            recorded_at=datetime.fromisoformat(payload["recorded_at"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
            deleted=bool(payload.get("deleted",False)),
            metadata=metadata
        )