from datetime import datetime,timezone
from enum import Enum
from typing import Any,Optional,Protocol
import math
from httpcore import request
from openai import embeddings
from openai import embeddings
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel,ConfigDict,Field,model_validator
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
from backend_memory_pipeline.graph_memory.graph import InMemoryGraphStore,GraphMemoryRecordV1,GraphRelationshipType
from backend_memory_pipeline.embedding.embedding import EmbeddingRecordV1,InMemoryEmbeddingStore,DeterministicEmbeddingProvider,SentenceTransformerEmbeddingProvider
class RetrievalDecision(str,Enum):
    RETRIEVED="retrieved"
    NO_RESULTS="no_results"
    FALLBACK="fallback"
class RetrievalErrorCode(str,Enum):
    INVALID_REQUEST="INVALID_REQUEST"
    INVALID_QUERY="INVALID_QUERY"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    MEMORY_NOT_FOUND="MEMORY_NOT_FOUND"
    INELIGIBLE_MEMORY="INELIGIBLE_MEMORY"
    EMBEDDING_NOT_FOUND="EMBEDDING_NOT_FOUND"
    INVALID_EMBEDDING="INVALID_EMBEDDING"
    RETRIEVAL_CONFLICT="RETRIEVAL_CONFLICT"
class RetrievalError(Exception):
    def __init__(self,code:RetrievalErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class RetrievalRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    intent:str=Field(min_length=1,max_length=5000)
    surface:str=Field(min_length=1,max_length=64)
    locale:str=Field(min_length=2,max_length=32)
    requested_at:datetime
    top_k:int=Field(default=5,ge=1,le=50)
    candidate_limit:int=Field(default=50,ge=1,le=200)
    vector_weight:float=Field(default=0.55,ge=0.0,le=1.0)
    graph_weight:float=Field(default=0.45,ge=0.0,le=1.0)
    min_score:float=Field(default=0.0,ge=0.0,le=1.0)
    metadata:dict[str,Any]=Field(default_factory=dict)
    @model_validator(mode="after")
    def validate_request(self):
        if self.subject_id!=self.subject_scope:
            raise ValueError("subject_scope must match subject_id.")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware.")
        if self.vector_weight+self.graph_weight<=0:
            raise ValueError("vector_weight and graph_weight cannot both be zero.")
        return self
class RetrievalCandidateV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    memory_type:str=Field(min_length=1,max_length=128)
    normalized_fact:str=Field(min_length=1,max_length=10000)
    status:MemoryStatus
    confidence:float=Field(ge=0.0,le=1.0)
    vector_score:float=Field(ge=0.0,le=1.0)
    graph_score:float=Field(ge=0.0,le=1.0)
    explicitness_score:float=Field(ge=0.0,le=1.0)
    recency_score:float=Field(ge=0.0,le=1.0)
    repetition_score:float=Field(ge=0.0,le=1.0)
    surface_score:float=Field(ge=0.0,le=1.0)
    negative_feedback_score:float=Field(ge=0.0,le=1.0)
    final_score:float=Field(ge=0.0,le=1.0)
    source_event_ids:list[str]=Field(default_factory=list)
    source_session_ids:list[str]=Field(default_factory=list)
    relevance_reason:str=Field(min_length=1,max_length=2000)
    provenance:dict[str,Any]=Field(default_factory=dict)
class RetrievalResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    decision:RetrievalDecision
    subject_id:str
    query_intent:str
    candidates:list[RetrievalCandidateV1]=Field(default_factory=list)
    candidate_count:int=Field(ge=0)
    graph_candidate_count:int=Field(ge=0)
    vector_candidate_count:int=Field(ge=0)
    returned_count:int=Field(ge=0)
    retrieval_version:str="1.0"
    provenance:dict[str,Any]=Field(default_factory=dict)
class QueryEmbeddingProvider(Protocol):
    def embed_query(self,text:str,model_name:str,model_version:str,dimensions:int)->list[float]:
        ...
class DeterministicQueryEmbeddingProvider:
    def __init__(self):
        self._provider=DeterministicEmbeddingProvider()
    def embed_query(self,text:str,model_name:str,model_version:str,dimensions:int)->list[float]:
        return self._provider.embed(text,model_name,model_version,dimensions)
class SentenceTransformerQueryEmbeddingProvider:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_query(self,text: str,model_name: str,model_version: str,dimensions: int) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise RetrievalError(RetrievalErrorCode.INVALID_QUERY,"Retrieval intent cannot be empty.")
        if model_name != self.model_name:
            raise RetrievalError(RetrievalErrorCode.INVALID_EMBEDDING,
                f"Query provider is configured for model "
                f"'{self.model_name}', but received '{model_name}'.")
        vector = self.model.encode(text,normalize_embeddings=True).tolist()
        if len(vector) != dimensions:
            raise RetrievalError(RetrievalErrorCode.INVALID_EMBEDDING,"SentenceTransformer returned an unexpected query vector dimension.")
        return vector    
class RetrievalStore(Protocol):
    def graph_memories(self,subject_id:str)->list[GraphMemoryRecordV1]:
        ...
    def graph_relationships(self,subject_id:str)->list[Any]:
        ...
    def embeddings(self,subject_id:str)->list[EmbeddingRecordV1]:
        ...
class InMemoryRetrievalStore:
    def __init__(self,graph_store:InMemoryGraphStore,embedding_store:InMemoryEmbeddingStore):
        self.graph_store=graph_store
        self.embedding_store=embedding_store
    def graph_memories(self,subject_id:str)->list[GraphMemoryRecordV1]:
        return [
            memory
            for memory in self.graph_store.all_memories()
            if memory.subject_id==subject_id
            and memory.subject_scope==subject_id
        ]
    def graph_relationships(self,subject_id:str)->list[Any]:
        return [
            relationship
            for relationship in self.graph_store.all_relationships()
            if relationship.subject_id==subject_id
        ]
    def embeddings(self,subject_id:str)->list[EmbeddingRecordV1]:
        return [
            embedding
            for embedding in self.embedding_store.all()
            if embedding.subject_id==subject_id
            and embedding.subject_scope==subject_id
        ]
class RetrievalService:
    def __init__(self,retrieval_store:RetrievalStore,
        query_provider:Optional[QueryEmbeddingProvider]=None,
        retrieval_version:str="1.0"):

        self.store=retrieval_store
        #self.query_provider = (query_provider or SentenceTransformerQueryEmbeddingProvider())
        self.query_provider=query_provider or DeterministicQueryEmbeddingProvider()
        self.retrieval_version=retrieval_version
    def retrieve(self,request:RetrievalRequestV1)->RetrievalResultV1:
        self._validate_request(request)
        graph_memories=self.store.graph_memories(request.subject_id)
        relationships=self.store.graph_relationships(request.subject_id)
        embeddings=self.store.embeddings(request.subject_id)
        graph_memories=self._filter_eligible_memories(graph_memories,request)
        embeddings=self._filter_eligible_embeddings(embeddings,request)
        print("\n===== RETRIEVAL DEBUG =====")
        print("REQUEST SUBJECT:", request.subject_id)
        print("REQUESTED AT:", request.requested_at)
        print("GRAPH MEMORIES AFTER FILTER:", len(graph_memories))
        print("EMBEDDINGS AFTER FILTER:", len(embeddings))   
        print("RETRIEVAL DEBUG graph_memories:", graph_memories)
        print("RETRIEVAL DEBUG embeddings:", embeddings)
        print("RETRIEVAL DEBUG requested_at:", request.requested_at)
        print("RETRIEVAL DEBUG subject_id:", request.subject_id)
        if graph_memories:
           print("GRAPH MEMORY ID:", graph_memories[0].memory_id)
           print("GRAPH MEMORY VALID FROM:", graph_memories[0].valid_from)
           print("GRAPH MEMORY STATUS:", graph_memories[0].status)
           print("GRAPH MEMORY RETRIEVAL ELIGIBLE:",
           graph_memories[0].retrieval_eligible)

        if embeddings:
           print("EMBEDDING MEMORY ID:", embeddings[0].memory_id)
           print("EMBEDDING STATUS:", embeddings[0].memory_status)
           print("EMBEDDING RETRIEVAL ELIGIBLE:",
           embeddings[0].retrieval_eligible)
           print("EMBEDDING ELIGIBLE:",
           embeddings[0].embedding_eligible)

        query_dimensions=self._resolve_query_dimensions(embeddings)
        query_vector=self.query_provider.embed_query(request.intent,
        self._resolve_model_name(embeddings),
        self._resolve_model_version(embeddings),query_dimensions)

        vector_scores=self._vector_scores(query_vector,embeddings)
        print("VECTOR SCORES:", vector_scores)
        print("RETRIEVAL DEBUG vector_scores:", vector_scores)
        graph_scores=self._graph_scores(request,graph_memories,relationships)
        print("GRAPH SCORES:", graph_scores)
        print("RETRIEVAL DEBUG graph_scores:", graph_scores)
        memory_map={memory.memory_id:memory for memory in graph_memories}
        embedding_map={embedding.memory_id:embedding for embedding in embeddings}
        candidate_ids=set(vector_scores)|set(graph_scores)
        print("CANDIDATE IDS:", candidate_ids)
        print("RETRIEVAL DEBUG candidate_ids:", candidate_ids)
        ranked=[]
        for memory_id in candidate_ids:
            print("RETRIEVAL DEBUG processing memory_id:", memory_id)
            memory=memory_map.get(memory_id)
            if memory is None:
                continue
            embedding=embedding_map.get(memory_id)
            vector_score=vector_scores.get(memory_id,0.0)
            graph_score=graph_scores.get(memory_id,0.0)
            explicitness=self._explicitness_score(memory)
            recency=self._recency_score(memory,request.requested_at)
            repetition=self._repetition_score(memory)
            surface=self._surface_score(memory,request.surface)
            negative_feedback=self._negative_feedback_score(memory)
            final_score=self._final_score(
                vector_score=vector_score,
                graph_score=graph_score,
                explicitness=explicitness,
                confidence=memory.confidence,
                recency=recency,
                repetition=repetition,
                surface=surface,
                negative_feedback=negative_feedback,
                vector_weight=request.vector_weight,
                graph_weight=request.graph_weight
            )
            print("RETRIEVAL DEBUG scores:",
                {"memory_id": memory_id,
                "vector_score": vector_score,
                "graph_score": graph_score,
                "explicitness": explicitness,
                "confidence": memory.confidence,
                "recency": recency,
                "repetition": repetition,
                "surface": surface,
                "negative_feedback": negative_feedback,
                "final_score": final_score,
                "min_score": request.min_score,})
            
            if final_score<request.min_score:
                continue
            reason=self._relevance_reason(
                memory=memory,
                vector_score=vector_score,
                graph_score=graph_score,
                explicitness=explicitness,
                recency=recency,
                repetition=repetition,
                surface=surface,
                negative_feedback=negative_feedback
            )
            ranked.append(
                RetrievalCandidateV1(
                    memory_id=memory.memory_id,
                    subject_id=memory.subject_id,
                    memory_type=memory.memory_type,
                    normalized_fact=memory.normalized_fact,
                    status=memory.status,
                    confidence=memory.confidence,
                    vector_score=vector_score,
                    graph_score=graph_score,
                    explicitness_score=explicitness,
                    recency_score=recency,
                    repetition_score=repetition,
                    surface_score=surface,
                    negative_feedback_score=negative_feedback,
                    final_score=final_score,
                    source_event_ids=list(memory.source_event_ids),
                    source_session_ids=list(memory.source_session_ids),
                    relevance_reason=reason,
                    provenance={
                        "recorded_at":memory.recorded_at,
                        "valid_from":memory.valid_from,
                        "valid_to":memory.valid_to,
                        "embedding_id":embedding.embedding_id if embedding is not None else None,
                        "retrieval_version":self.retrieval_version
                    }
                )
            )
        ranked.sort(
            key=lambda candidate:(
                -candidate.final_score,
                -candidate.confidence,
                -candidate.recency_score,
                candidate.memory_id
            )
        )
        ranked=self._apply_diversity_limit(ranked,request.top_k)
        print("RANKED AFTER DIVERSITY:", len(ranked))
        print("RANKED:", ranked)
        print("===========================\n")
        if not ranked:
            return RetrievalResultV1(
                decision=RetrievalDecision.NO_RESULTS,
                subject_id=request.subject_id,
                query_intent=request.intent,
                candidates=[],
                candidate_count=len(candidate_ids),
                graph_candidate_count=len(graph_scores),
                vector_candidate_count=len(vector_scores),
                returned_count=0,
                retrieval_version=self.retrieval_version,
                provenance={
                    "fallback":"no_memory",
                    "surface":request.surface
                }
            )
        return RetrievalResultV1(
            decision=RetrievalDecision.RETRIEVED,
            subject_id=request.subject_id,
            query_intent=request.intent,
            candidates=ranked,
            candidate_count=len(candidate_ids),
            graph_candidate_count=len(graph_scores),
            vector_candidate_count=len(vector_scores),
            returned_count=len(ranked),
            retrieval_version=self.retrieval_version,
            provenance={
                "surface":request.surface,
                "top_k":request.top_k,
                "candidate_limit":request.candidate_limit
            }
        )
    @staticmethod
    def _validate_request(request:RetrievalRequestV1)->None:
        if not isinstance(request,RetrievalRequestV1):
            raise RetrievalError(
                RetrievalErrorCode.INVALID_REQUEST,
                "Input must be a RetrievalRequestV1."
            )
        if not request.intent.strip():
            raise RetrievalError(
                RetrievalErrorCode.INVALID_QUERY,
                "Retrieval intent cannot be empty."
            )
    @staticmethod
    def _filter_eligible_memories(
        memories:list[GraphMemoryRecordV1],
        request:RetrievalRequestV1
    )->list[GraphMemoryRecordV1]:
        eligible=[]
        for memory in memories:
            if memory.subject_id!=request.subject_id or memory.subject_scope!=request.subject_id:
                continue
            if memory.status!=MemoryStatus.ACTIVE:
                continue
            if not memory.retrieval_eligible:
                continue
            if memory.valid_from>request.requested_at:
                continue
            if memory.valid_to is not None and memory.valid_to<=request.requested_at:
                continue
            eligible.append(memory)
        return eligible[:request.candidate_limit]
    @staticmethod
    def _filter_eligible_embeddings(
        embeddings:list[EmbeddingRecordV1],
        request:RetrievalRequestV1
    )->list[EmbeddingRecordV1]:
        eligible=[]
        for embedding in embeddings:
            if embedding.subject_id!=request.subject_id or embedding.subject_scope!=request.subject_id:
                continue
            if not embedding.embedding_eligible:
                continue
            if not embedding.retrieval_eligible:
                continue
            if embedding.memory_status!=MemoryStatus.ACTIVE:
                continue
            eligible.append(embedding)
        return eligible[:request.candidate_limit]
    @staticmethod
    def _resolve_query_dimensions(embeddings:list[EmbeddingRecordV1])->int:
        if not embeddings:
            return 384
        dimensions=embeddings[0].dimensions
        if any(embedding.dimensions!=dimensions for embedding in embeddings):
            raise RetrievalError(
                RetrievalErrorCode.INVALID_EMBEDDING,
                "Embedding dimension mismatch detected in retrieval store."
            )
        return dimensions
    @staticmethod
    def _resolve_model_name(embeddings:list[EmbeddingRecordV1])->str:
        return embeddings[0].model_name if embeddings else "all-MiniLM-L6-v2"
    @staticmethod
    def _resolve_model_version(embeddings:list[EmbeddingRecordV1])->str:
        return embeddings[0].model_version if embeddings else "test-v1"
    @staticmethod
    def _vector_scores(
        query_vector:list[float],
        embeddings:list[EmbeddingRecordV1]
    )->dict[str,float]:
        scores={}
        for embedding in embeddings:
            score=RetrievalService._cosine_similarity(
                query_vector,
                embedding.vector
            )
            scores[embedding.memory_id]=max(0.0,min(1.0,(score+1.0)/2.0))
        return scores
    @staticmethod
    def _graph_scores(
        request:RetrievalRequestV1,
        memories:list[GraphMemoryRecordV1],
        relationships:list[Any]
    )->dict[str,float]:
        #print("GRAPH SCORES:", graph_scores)
        relationship_by_memory:dict[str,int]={}
        entity_match_by_memory:dict[str,int]={}
        intent_tokens=set(RetrievalService._tokens(request.intent))
        for relationship in relationships:
            if relationship.relationship_type==GraphRelationshipType.SUBJECT_HAS_MEMORY:
                memory_id=relationship.to_node_id.replace("memory:","",1)
                relationship_by_memory[memory_id]=relationship_by_memory.get(memory_id,0)+1
        scores={}
        for memory in memories:
            tokens=set(RetrievalService._tokens(memory.normalized_fact))
            lexical_overlap=len(tokens&intent_tokens)
            token_score=min(1.0,lexical_overlap/max(1,len(intent_tokens)))
            relation_score=1.0 if relationship_by_memory.get(memory.memory_id,0)>0 else 0.0
            score=min(1.0,0.7*token_score+0.3*relation_score)
            scores[memory.memory_id]=score
        return scores
    @staticmethod
    def _explicitness_score(memory:GraphMemoryRecordV1)->float:
        if memory.memory_type=="explicit_preference":
            return 1.0
        if memory.memory_type=="exclusion":
            return 0.95
        if memory.memory_type=="episode":
            return 0.65
        if memory.memory_type=="candidate_preference":
            return 0.45
        return 0.25
    @staticmethod
    def _recency_score(memory:GraphMemoryRecordV1,requested_at:datetime)->float:
        age=max(0.0,(requested_at-memory.recorded_at).total_seconds())
        days=age/86400.0
        return math.exp(-days/30.0)
    @staticmethod
    def _repetition_score(memory:GraphMemoryRecordV1)->float:
        evidence_count=max(
            len(memory.source_event_ids),
            len(memory.source_session_ids)
        )
        return min(1.0,evidence_count/5.0)
    @staticmethod
    def _surface_score(memory:GraphMemoryRecordV1,surface:str)->float:
        supported_surfaces=memory.metadata.get("supported_surfaces")
        if not supported_surfaces:
            return 0.5
        if isinstance(supported_surfaces,list) and surface in supported_surfaces:
            return 1.0
        return 0.0
    @staticmethod
    def _negative_feedback_score(memory:GraphMemoryRecordV1)->float:
        value=memory.metadata.get("negative_feedback_score",0.0)
        try:
            return max(0.0,min(1.0,float(value)))
        except (TypeError,ValueError):
            return 0.0
    @staticmethod
    def _final_score(
        vector_score:float,
        graph_score:float,
        explicitness:float,
        confidence:float,
        recency:float,
        repetition:float,
        surface:float,
        negative_feedback:float,
        vector_weight:float,
        graph_weight:float
    )->float:
        base_weight=vector_weight+graph_weight
        hybrid=((vector_score*vector_weight)+(graph_score*graph_weight))/base_weight
        score=(
            0.45*hybrid+
            0.15*explicitness+
            0.15*confidence+
            0.10*recency+
            0.05*repetition+
            0.05*surface+
            0.05*(1.0-negative_feedback)
        )
        return max(0.0,min(1.0,score))
    @staticmethod
    def _relevance_reason(
        memory:GraphMemoryRecordV1,
        vector_score:float,
        graph_score:float,
        explicitness:float,
        recency:float,
        repetition:float,
        surface:float,
        negative_feedback:float
    )->str:
        reasons=[]
        if vector_score>=0.65:
            reasons.append("strong semantic similarity")
        if graph_score>=0.65:
            reasons.append("strong graph relevance")
        if explicitness>=0.9:
            reasons.append("explicit user preference or exclusion")
        elif repetition>=0.6:
            reasons.append("repeated evidence")
        if recency>=0.7:
            reasons.append("recent memory")
        if surface>=0.9:
            reasons.append("surface-compatible memory")
        if negative_feedback>0:
            reasons.append("negative feedback reduced the score")
        if not reasons:
            reasons.append("hybrid relevance score")
        return "; ".join(reasons)
    @staticmethod
    def _apply_diversity_limit(
        candidates:list[RetrievalCandidateV1],
        top_k:int
    )->list[RetrievalCandidateV1]:
        selected=[]
        seen_types:set[str]=set()
        for candidate in candidates:
            if len(selected)>=top_k:
                break
            if candidate.memory_type not in seen_types or len(selected)<max(1,top_k//2):
                selected.append(candidate)
                seen_types.add(candidate.memory_type)
        return selected
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
    def _cosine_similarity(a:list[float],b:list[float])->float:
        if len(a)!=len(b) or not a or not b:
            raise RetrievalError(
                RetrievalErrorCode.INVALID_EMBEDDING,
                "Embedding vectors must have equal non-zero dimensions."
            )
        dot=sum(x*y for x,y in zip(a,b))
        norm_a=math.sqrt(sum(x*x for x in a))
        norm_b=math.sqrt(sum(y*y for y in b))
        if norm_a==0 or norm_b==0:
            raise RetrievalError(
                RetrievalErrorCode.INVALID_EMBEDDING,
                "Embedding vectors cannot have zero magnitude."
            )
        return dot/(norm_a*norm_b)