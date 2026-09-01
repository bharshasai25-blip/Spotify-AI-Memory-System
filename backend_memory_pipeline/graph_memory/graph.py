from enum import Enum
from typing import Any,Optional,Protocol
from pydantic import BaseModel,ConfigDict,Field
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryRecordV1,MemoryStatus
class GraphNodeType(str,Enum):
    SUBJECT="subject"
    MEMORY="memory"
    ENTITY="entity"
class GraphRelationshipType(str,Enum):
    SUBJECT_HAS_MEMORY="subject_has_memory"
    MEMORY_REFERENCES_ENTITY="memory_references_entity"
    MEMORY_SUPERSEDES="memory_supersedes"
    MEMORY_CORRECTS="memory_corrects"
class GraphOperation(str,Enum):
    UPSERT="upsert"
    UPDATE="update"
    CLOSE="close"
    DELETE="delete"
class GraphMemoryErrorCode(str,Enum):
    INVALID_MEMORY="INVALID_MEMORY"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    INVALID_ENTITY="INVALID_ENTITY"
    INVALID_RELATIONSHIP="INVALID_RELATIONSHIP"
    GRAPH_CONFLICT="GRAPH_CONFLICT"
    MEMORY_NOT_FOUND="MEMORY_NOT_FOUND"
class GraphMemoryError(Exception):
    def __init__(self,code:GraphMemoryErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class GraphNodeV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    node_id:str=Field(min_length=1,max_length=256)
    node_type:GraphNodeType
    subject_id:Optional[str]=None
    properties:dict[str,Any]=Field(default_factory=dict)
class GraphRelationshipV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    relationship_id:str=Field(min_length=1,max_length=256)
    relationship_type:GraphRelationshipType
    from_node_id:str=Field(min_length=1,max_length=256)
    to_node_id:str=Field(min_length=1,max_length=256)
    subject_id:str=Field(min_length=1,max_length=128)
    properties:dict[str,Any]=Field(default_factory=dict)
class GraphMemoryRecordV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    memory_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    subject_scope:str=Field(min_length=1,max_length=128)
    memory_type:str=Field(min_length=1,max_length=128)
    normalized_fact:str=Field(min_length=1,max_length=10000)
    confidence:float=Field(ge=0.0,le=1.0)
    source_event_ids:list[str]=Field(default_factory=list,min_length=1)
    source_session_ids:list[str]=Field(default_factory=list)
    created_at:Any
    recorded_at:Any
    valid_from:Any
    valid_to:Optional[Any]=None
    status:MemoryStatus
    retention_class:str=Field(min_length=1,max_length=64)
    retrieval_eligible:bool
    embedding_eligible:bool
    entities:list[dict[str,Any]]=Field(default_factory=list)
    correction_of_memory_id:Optional[str]=None
    supersedes_memory_id:Optional[str]=None
    metadata:dict[str,Any]=Field(default_factory=dict)
class GraphWriteResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    operation:GraphOperation
    memory_id:str
    subject_id:str
    changed:bool
    memory_node:GraphNodeV1
    relationships:list[GraphRelationshipV1]=Field(default_factory=list)
    graph_version:int
    provenance:dict[str,Any]=Field(default_factory=dict)
class GraphStore(Protocol):
    def get_memory(self,memory_id:str)->Optional[GraphMemoryRecordV1]:
        ...
    def upsert_memory(self,memory:GraphMemoryRecordV1)->bool:
        ...
    def delete_memory(self,memory_id:str)->None:
        ...
    def get_graph_version(self,memory_id:str)->int:
        ...
    def put_node(self,node:GraphNodeV1)->bool:
        ...
    def put_relationship(self,relationship:GraphRelationshipV1)->bool:
        ...
    def get_node(self,node_id:str)->Optional[GraphNodeV1]:
        ...
    def get_relationship(self,relationship_id:str)->Optional[GraphRelationshipV1]:
        ...
class InMemoryGraphStore:
    def __init__(self):
        self._memories:dict[str,GraphMemoryRecordV1]={}
        self._nodes:dict[str,GraphNodeV1]={}
        self._relationships:dict[str,GraphRelationshipV1]={}
        self._versions:dict[str,int]={}
    def get_memory(self,memory_id:str)->Optional[GraphMemoryRecordV1]:
        return self._memories.get(memory_id)
    def upsert_memory(self,memory:GraphMemoryRecordV1)->bool:
        existing=self._memories.get(memory.memory_id)
        changed=existing is None or existing.model_dump()!=memory.model_dump()
        if changed:
            self._versions[memory.memory_id]=self._versions.get(memory.memory_id,0)+1
            self._memories[memory.memory_id]=memory
        return changed
    def delete_memory(self,memory_id:str)->None:
        self._memories.pop(memory_id,None)
        self._versions[memory_id]=self._versions.get(memory_id,0)+1
        node_id=f"memory:{memory_id}"
        self._nodes.pop(node_id,None)
        relationship_ids=[
            relationship_id
            for relationship_id,relationship in self._relationships.items()
            if relationship.from_node_id==node_id or relationship.to_node_id==node_id
        ]
        for relationship_id in relationship_ids:
            self._relationships.pop(relationship_id,None)
    def get_graph_version(self,memory_id:str)->int:
        return self._versions.get(memory_id,0)
    def put_node(self,node:GraphNodeV1)->bool:
        existing=self._nodes.get(node.node_id)
        changed=existing is None or existing.model_dump()!=node.model_dump()
        if changed:
            self._nodes[node.node_id]=node
        return changed
    def put_relationship(self,relationship:GraphRelationshipV1)->bool:
        existing=self._relationships.get(relationship.relationship_id)
        changed=existing is None or existing.model_dump()!=relationship.model_dump()
        if changed:
            self._relationships[relationship.relationship_id]=relationship
        return changed
    def get_node(self,node_id:str)->Optional[GraphNodeV1]:
        return self._nodes.get(node_id)
    def get_relationship(self,relationship_id:str)->Optional[GraphRelationshipV1]:
        return self._relationships.get(relationship_id)
    def all_nodes(self)->list[GraphNodeV1]:
        return list(self._nodes.values())
    def all_relationships(self)->list[GraphRelationshipV1]:
        return list(self._relationships.values())
    def all_memories(self)->list[GraphMemoryRecordV1]:
        return list(self._memories.values())
class GraphMemoryService:
    def __init__(self,store:Optional[GraphStore]=None):
        self.store=store or InMemoryGraphStore()
    def upsert_memory(self,memory:MemoryRecordV1,expected_graph_version:Optional[int]=None)->GraphWriteResultV1:
        self._validate_memory(memory)
        existing=self.store.get_memory(memory.memory_id)
        if existing is not None:
            self._validate_existing_subject(existing,memory)
        current_version=self.store.get_graph_version(memory.memory_id)
        if expected_graph_version is not None and current_version!=expected_graph_version:
            raise GraphMemoryError(
                GraphMemoryErrorCode.GRAPH_CONFLICT,
                f"Expected graph version {expected_graph_version} but found {current_version}."
            )
        graph_record=self._to_graph_record(memory)
        changed=self.store.upsert_memory(graph_record)
        memory_node=self._build_memory_node(memory)
        self.store.put_node(memory_node)
        self._ensure_subject_node(memory)
        relationships=self._build_relationships(memory)
        for relationship in relationships:
            self.store.put_relationship(relationship)
        operation=GraphOperation.UPSERT if existing is None else GraphOperation.UPDATE
        return GraphWriteResultV1(
            operation=operation,
            memory_id=memory.memory_id,
            subject_id=memory.subject_id,
            changed=changed,
            memory_node=memory_node,
            relationships=relationships,
            graph_version=self.store.get_graph_version(memory.memory_id),
            provenance={
                "source_event_ids":memory.source_event_ids,
                "source_session_ids":memory.source_session_ids,
                "recorded_at":memory.recorded_at,
                "valid_from":memory.valid_from,
                "valid_to":memory.valid_to,
                "status":memory.status.value
            }
        )
    def close_memory(self,memory:MemoryRecordV1)->GraphWriteResultV1:
        self._validate_memory(memory)
        if memory.status not in {
            MemoryStatus.SUPERSEDED,
            MemoryStatus.EXPIRED,
            MemoryStatus.CORRECTED
        }:
            raise GraphMemoryError(
                GraphMemoryErrorCode.GRAPH_CONFLICT,
                "close_memory requires a closed lifecycle memory status."
            )
        if memory.valid_to is None:
            raise GraphMemoryError(
                GraphMemoryErrorCode.GRAPH_CONFLICT,
                "Closed graph memory requires valid_to."
            )
        result=self.upsert_memory(memory)
        result.operation=GraphOperation.CLOSE
        return result
    def delete_memory(self,memory:MemoryRecordV1)->GraphWriteResultV1:
        self._validate_memory(memory)
        existing=self.store.get_memory(memory.memory_id)
        if existing is None:
            raise GraphMemoryError(
                GraphMemoryErrorCode.MEMORY_NOT_FOUND,
                f"Memory {memory.memory_id} was not found."
            )
        self._validate_existing_subject(existing,memory)
        if memory.status==MemoryStatus.PENDING_DELETION:
            result=self.upsert_memory(memory)
            result.operation=GraphOperation.UPDATE
            return result
        if memory.status!=MemoryStatus.DELETED:
            raise GraphMemoryError(
                GraphMemoryErrorCode.GRAPH_CONFLICT,
                "Graph deletion requires a memory in DELETED state."
            )
        self.store.delete_memory(memory.memory_id)
        return GraphWriteResultV1(
            operation=GraphOperation.DELETE,
            memory_id=memory.memory_id,
            subject_id=memory.subject_id,
            changed=True,
            memory_node=self._build_deleted_memory_node(memory),
            relationships=[],
            graph_version=self.store.get_graph_version(memory.memory_id),
            provenance={
                "deleted":True,
                "source_event_ids":memory.source_event_ids,
                "source_session_ids":memory.source_session_ids,
                "recorded_at":memory.recorded_at
            }
        )
    def get_memory(self,memory_id:str,subject_id:str)->GraphMemoryRecordV1:
        memory=self.store.get_memory(memory_id)
        if memory is None:
            raise GraphMemoryError(
                GraphMemoryErrorCode.MEMORY_NOT_FOUND,
                f"Memory {memory_id} was not found."
            )
        if memory.subject_id!=subject_id or memory.subject_scope!=subject_id:
            raise GraphMemoryError(
                GraphMemoryErrorCode.SUBJECT_MISMATCH,
                "Memory does not belong to the requested subject."
            )
        return memory
    def _build_memory_node(self,memory:MemoryRecordV1)->GraphNodeV1:
        return GraphNodeV1(
            node_id=f"memory:{memory.memory_id}",
            node_type=GraphNodeType.MEMORY,
            subject_id=memory.subject_id,
            properties={
                "memory_id":memory.memory_id,
                "subject_id":memory.subject_id,
                "subject_scope":memory.subject_scope,
                "memory_type":memory.memory_type.value,
                "normalized_fact":memory.normalized_fact,
                "confidence":memory.confidence,
                "source_event_ids":memory.source_event_ids,
                "source_session_ids":memory.source_session_ids,
                "created_at":memory.created_at,
                "recorded_at":memory.recorded_at,
                "valid_from":memory.valid_from,
                "valid_to":memory.valid_to,
                "status":memory.status.value,
                "retention_class":memory.retention_class.value,
                "retrieval_eligible":memory.retrieval_eligible,
                "embedding_eligible":memory.embedding_eligible,
                "correction_of_memory_id":memory.correction_of_memory_id,
                "supersedes_memory_id":memory.supersedes_memory_id,
                "metadata":memory.metadata
            }
        )
    def _build_deleted_memory_node(self,memory:MemoryRecordV1)->GraphNodeV1:
        return GraphNodeV1(
            node_id=f"memory:{memory.memory_id}",
            node_type=GraphNodeType.MEMORY,
            subject_id=memory.subject_id,
            properties={
                "memory_id":memory.memory_id,
                "subject_id":memory.subject_id,
                "status":MemoryStatus.DELETED.value,
                "deleted":True
            }
        )
    def _ensure_subject_node(self,memory:MemoryRecordV1)->None:
        self.store.put_node(
            GraphNodeV1(
                node_id=f"subject:{memory.subject_id}",
                node_type=GraphNodeType.SUBJECT,
                subject_id=memory.subject_id,
                properties={
                    "subject_id":memory.subject_id,
                    "subject_scope":memory.subject_scope
                }
            )
        )
    def _build_relationships(self,memory:MemoryRecordV1)->list[GraphRelationshipV1]:
        relationships=[
            GraphRelationshipV1(
                relationship_id=f"subject_memory:{memory.subject_id}:{memory.memory_id}",
                relationship_type=GraphRelationshipType.SUBJECT_HAS_MEMORY,
                from_node_id=f"subject:{memory.subject_id}",
                to_node_id=f"memory:{memory.memory_id}",
                subject_id=memory.subject_id,
                properties={
                    "recorded_at":memory.recorded_at,
                    "valid_from":memory.valid_from,
                    "valid_to":memory.valid_to,
                    "status":memory.status.value
                }
            )
        ]
        seen_entity_relationships:set[str]=set()
        for entity in memory.entities:
            canonical_id=entity.get("canonical_id")
            entity_type=entity.get("entity_type")
            canonical_name=entity.get("canonical_name") or entity.get("mention")
            if canonical_id is None:
                continue
            if not isinstance(canonical_id,str) or not canonical_id.strip():
                raise GraphMemoryError(
                    GraphMemoryErrorCode.INVALID_ENTITY,
                    "Resolved entity canonical_id must be a non-empty string."
                )
            entity_node_id=f"entity:{canonical_id}"
            self.store.put_node(
                GraphNodeV1(
                    node_id=entity_node_id,
                    node_type=GraphNodeType.ENTITY,
                    subject_id=None,
                    properties={
                        "canonical_id":canonical_id,
                        "entity_type":entity_type,
                        "canonical_name":canonical_name
                    }
                )
            )
            relationship_key=f"{memory.memory_id}:{canonical_id}"
            if relationship_key not in seen_entity_relationships:
                relationships.append(
                    GraphRelationshipV1(
                        relationship_id=f"memory_entity:{memory.memory_id}:{canonical_id}",
                        relationship_type=GraphRelationshipType.MEMORY_REFERENCES_ENTITY,
                        from_node_id=f"memory:{memory.memory_id}",
                        to_node_id=entity_node_id,
                        subject_id=memory.subject_id,
                        properties={
                            "entity_type":entity_type,
                            "canonical_name":canonical_name,
                            "recorded_at":memory.recorded_at
                        }
                    )
                )
                seen_entity_relationships.add(relationship_key)
        if memory.supersedes_memory_id:
            relationships.append(
                GraphRelationshipV1(
                    relationship_id=f"memory_supersedes:{memory.memory_id}:{memory.supersedes_memory_id}",
                    relationship_type=GraphRelationshipType.MEMORY_SUPERSEDES,
                    from_node_id=f"memory:{memory.memory_id}",
                    to_node_id=f"memory:{memory.supersedes_memory_id}",
                    subject_id=memory.subject_id,
                    properties={
                        "recorded_at":memory.recorded_at,
                        "valid_from":memory.valid_from
                    }
                )
            )
        if memory.correction_of_memory_id:
            relationships.append(
                GraphRelationshipV1(
                    relationship_id=f"memory_corrects:{memory.memory_id}:{memory.correction_of_memory_id}",
                    relationship_type=GraphRelationshipType.MEMORY_CORRECTS,
                    from_node_id=f"memory:{memory.memory_id}",
                    to_node_id=f"memory:{memory.correction_of_memory_id}",
                    subject_id=memory.subject_id,
                    properties={
                        "recorded_at":memory.recorded_at,
                        "valid_from":memory.valid_from
                    }
                )
            )
        return relationships
    @staticmethod
    def _to_graph_record(memory:MemoryRecordV1)->GraphMemoryRecordV1:
        return GraphMemoryRecordV1(
            memory_id=memory.memory_id,
            subject_id=memory.subject_id,
            subject_scope=memory.subject_scope,
            memory_type=memory.memory_type.value,
            normalized_fact=memory.normalized_fact,
            confidence=memory.confidence,
            source_event_ids=list(memory.source_event_ids),
            source_session_ids=list(memory.source_session_ids),
            created_at=memory.created_at,
            recorded_at=memory.recorded_at,
            valid_from=memory.valid_from,
            valid_to=memory.valid_to,
            status=memory.status,
            retention_class=memory.retention_class.value,
            retrieval_eligible=memory.retrieval_eligible,
            embedding_eligible=memory.embedding_eligible,
            entities=list(memory.entities),
            correction_of_memory_id=memory.correction_of_memory_id,
            supersedes_memory_id=memory.supersedes_memory_id,
            metadata=dict(memory.metadata)
        )
    @staticmethod
    def _validate_memory(memory:MemoryRecordV1)->None:
        if not isinstance(memory,MemoryRecordV1):
            raise GraphMemoryError(
                GraphMemoryErrorCode.INVALID_MEMORY,
                "Input must be a MemoryRecordV1."
            )
        if not memory.subject_id.strip() or not memory.subject_scope.strip():
            raise GraphMemoryError(
                GraphMemoryErrorCode.INVALID_MEMORY,
                "Memory subject identity and scope are required."
            )
        if memory.subject_id!=memory.subject_scope:
            raise GraphMemoryError(
                GraphMemoryErrorCode.SUBJECT_MISMATCH,
                "Memory subject scope must match subject identity."
            )
    @staticmethod
    def _validate_existing_subject(existing:GraphMemoryRecordV1,incoming:MemoryRecordV1)->None:
        if existing.subject_id!=incoming.subject_id:
            raise GraphMemoryError(
                GraphMemoryErrorCode.SUBJECT_MISMATCH,
                "Existing graph memory belongs to another subject."
            )
        if existing.subject_scope!=incoming.subject_scope:
            raise GraphMemoryError(
                GraphMemoryErrorCode.SUBJECT_MISMATCH,
                "Existing graph memory scope does not match incoming scope."
            )