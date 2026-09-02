import json
from datetime import date,datetime,time
from typing import Any,Optional
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from backend_memory_pipeline.graph_memory.graph import (
    GraphMemoryRecordV1,
    GraphNodeV1,
    GraphRelationshipV1,
    GraphStore,
    GraphNodeType,
    GraphRelationshipType,
)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryStatus
class Neo4jGraphStore(GraphStore):
    def __init__(self,uri:str="bolt://localhost:7687",username:str="neo4j",password:str="password",database:str="neo4j"):
        self.uri=uri
        self.username=username
        self.password=password
        self.database=database
        self.driver=GraphDatabase.driver(uri,auth=(username,password))
    def verify_connectivity(self)->None:
        self.driver.verify_connectivity()
    def close(self)->None:
        self.driver.close()
    def get_memory(self,memory_id:str)->Optional[GraphMemoryRecordV1]:
        query="""
        MATCH (m:Memory {memory_id:$memory_id})
        RETURN m
        """
        try:
            records,_,_=self.driver.execute_query(query,{"memory_id":memory_id},database_=self.database)
            if not records:
                return None
            return self._record_to_memory(records[0]["m"])
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j get_memory failed: {exc}") from exc
    def upsert_memory(self,memory:GraphMemoryRecordV1)->bool:
        node_id=f"memory:{memory.memory_id}"
        existing=self.get_memory(memory.memory_id)
        if existing is not None:
            if existing.model_dump()==memory.model_dump():
               return False
            query="""
            MATCH (m:Memory {node_id:$node_id})
            SET
               m.memory_id=$memory_id,
               m.subject_id=$subject_id,
               m.subject_scope=$subject_scope,
               m.memory_type=$memory_type,
               m.normalized_fact=$normalized_fact,
               m.confidence=$confidence,
               m.source_event_ids=$source_event_ids,
               m.source_session_ids=$source_session_ids,
               m.created_at=$created_at,
               m.recorded_at=$recorded_at,
               m.valid_from=$valid_from,
               m.valid_to=$valid_to,
               m.status=$status,
               m.retention_class=$retention_class,
               m.retrieval_eligible=$retrieval_eligible,
               m.embedding_eligible=$embedding_eligible,
               m.entities_json=$entities_json,
               m.correction_of_memory_id=$correction_of_memory_id,
               m.supersedes_memory_id=$supersedes_memory_id,
               m.metadata_json=$metadata_json,
               m.graph_version=coalesce(m.graph_version,0)+1
            RETURN m.graph_version AS graph_version
            """
            params=self._memory_parameters(memory)
            params["node_id"]=node_id
            try:
              records,_,_=self.driver.execute_query(query,params,database_=self.database)
              if not records:
                raise RuntimeError(
                    f"Neo4j memory {memory.memory_id} disappeared during upsert."
                )
              return True
            except Neo4jError as exc:
                raise RuntimeError(f"Neo4j upsert_memory failed: {exc}") from exc
        query="""
        CREATE (m:Memory {
           node_id:$node_id,
           memory_id:$memory_id,
           subject_id:$subject_id,
           subject_scope:$subject_scope,
           memory_type:$memory_type,
           normalized_fact:$normalized_fact,
           confidence:$confidence,
           source_event_ids:$source_event_ids,
           source_session_ids:$source_session_ids,
           created_at:$created_at,
           recorded_at:$recorded_at,
           valid_from:$valid_from,
           valid_to:$valid_to,
           status:$status,
           retention_class:$retention_class,
           retrieval_eligible:$retrieval_eligible,
           embedding_eligible:$embedding_eligible,
           entities_json:$entities_json,
           correction_of_memory_id:$correction_of_memory_id,
           supersedes_memory_id:$supersedes_memory_id,
           metadata_json:$metadata_json,
           graph_version:1})
           RETURN m.graph_version AS graph_version
           """
        params=self._memory_parameters(memory)
        params["node_id"]=node_id
        try:
            records,_,_=self.driver.execute_query(query,params,database_=self.database)
            if not records:
               raise RuntimeError(
                f"Neo4j memory {memory.memory_id} could not be created.")
            return True
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j upsert_memory failed: {exc}") from exc
    def delete_memory(self,memory_id:str)->None:
        query="""
        MATCH (m:Memory {memory_id:$memory_id})
        DETACH DELETE m
        """
        try:
            self.driver.execute_query(query,{"memory_id":memory_id},database_=self.database)
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j delete_memory failed: {exc}") from exc
    def get_graph_version(self,memory_id:str)->int:
        query="""
        MATCH (m:Memory {memory_id:$memory_id})
        RETURN coalesce(m.graph_version,0) AS graph_version
        """
        try:
            records,_,_=self.driver.execute_query(query,{"memory_id":memory_id},database_=self.database)
            if not records:
                return 0
            return int(records[0]["graph_version"])
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j get_graph_version failed: {exc}") from exc
    def put_node(self,node:GraphNodeV1)->bool:
        label=self._node_label(node.node_type)
        properties=self._serialize_node_properties(node.properties)
        properties["node_id"]=node.node_id
        if node.subject_id is not None:
            properties["subject_id"]=node.subject_id
        query=f"""
        MERGE (n:{label} {{node_id:$node_id}})
        WITH n
        SET n += $properties
        RETURN n
        """
        try:
            records,_,_=self.driver.execute_query(query,{"node_id":node.node_id,"properties":properties},database_=self.database)
            return bool(records)
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j put_node failed: {exc}") from exc
    def put_relationship(self,relationship:GraphRelationshipV1)->bool:
        relationship_type=self._relationship_type(relationship.relationship_type)
        properties=self._serialize_properties(relationship.properties)
        properties["relationship_id"]=relationship.relationship_id
        properties["subject_id"]=relationship.subject_id
        query=f"""
        MATCH (from_node {{node_id:$from_node_id}})
        MATCH (to_node {{node_id:$to_node_id}})
        MERGE (from_node)-[r:{relationship_type} {{relationship_id:$relationship_id}}]->(to_node)
        SET r += $properties
        RETURN r
        """
        try:
            records,_,_=self.driver.execute_query(
                query,
                {
                    "from_node_id":relationship.from_node_id,
                    "to_node_id":relationship.to_node_id,
                    "relationship_id":relationship.relationship_id,
                    "properties":properties,
                },
                database_=self.database,
            )
            if not records:
                raise RuntimeError(
                    f"Neo4j relationship endpoints were not found for {relationship.relationship_id}."
                )
            return bool(records)
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j put_relationship failed: {exc}") from exc
    def get_node(self,node_id:str)->Optional[GraphNodeV1]:
        query="""
        MATCH (n {node_id:$node_id})
        RETURN n
        """
        try:
            records,_,_=self.driver.execute_query(query,{"node_id":node_id},database_=self.database)
            if not records:
                return None
            node=records[0]["n"]
            labels=set(node.labels)
            if "Subject" in labels:
                node_type=GraphNodeType.SUBJECT
            elif "Memory" in labels:
                node_type=GraphNodeType.MEMORY
            elif "Entity" in labels:
                node_type=GraphNodeType.ENTITY
            else:
                raise RuntimeError(f"Unknown Neo4j node labels for {node_id}: {labels}")
            properties=self._deserialize_node_properties(dict(node))
            subject_id=properties.pop("subject_id",None)
            properties.pop("node_id",None)
            return GraphNodeV1(
                node_id=node_id,
                node_type=node_type,
                subject_id=subject_id,
                properties=properties,
            )
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j get_node failed: {exc}") from exc
    def get_relationship(self,relationship_id:str)->Optional[GraphRelationshipV1]:
        query="""
        MATCH (from_node)-[r {relationship_id:$relationship_id}]->(to_node)
        RETURN r,from_node.node_id AS from_node_id,to_node.node_id AS to_node_id
        """
        try:
            records,_,_=self.driver.execute_query(query,{"relationship_id":relationship_id},database_=self.database)
            if not records:
                return None
            record=records[0]
            relationship=record["r"]
            properties=self._deserialize_properties(dict(relationship))
            subject_id=properties.pop("subject_id",None)
            properties.pop("relationship_id",None)
            return GraphRelationshipV1(
                relationship_id=relationship_id,
                relationship_type=self._relationship_enum(relationship.type),
                from_node_id=record["from_node_id"],
                to_node_id=record["to_node_id"],
                subject_id=subject_id,
                properties=properties,
            )
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j get_relationship failed: {exc}") from exc
    def all_nodes(self)->list[GraphNodeV1]:
        query="""
        MATCH (n)
        RETURN n
        ORDER BY n.node_id
        """
        try:
            records,_,_=self.driver.execute_query(query,database_=self.database)
            result=[]
            for record in records:
                node=record["n"]
                labels=set(node.labels)
                if "Subject" in labels:
                    node_type=GraphNodeType.SUBJECT
                elif "Memory" in labels:
                    node_type=GraphNodeType.MEMORY
                elif "Entity" in labels:
                    node_type=GraphNodeType.ENTITY
                else:
                    continue
                properties=self._deserialize_node_properties(dict(node))
                node_id=properties.pop("node_id")
                subject_id=properties.pop("subject_id",None)
                result.append(
                    GraphNodeV1(
                        node_id=node_id,
                        node_type=node_type,
                        subject_id=subject_id,
                        properties=properties,
                    )
                )
            return result
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j all_nodes failed: {exc}") from exc
    def all_relationships(self)->list[GraphRelationshipV1]:
        query="""
        MATCH (from_node)-[r]->(to_node)
        WHERE r.relationship_id IS NOT NULL
        RETURN r,from_node.node_id AS from_node_id,to_node.node_id AS to_node_id
        ORDER BY r.relationship_id
        """
        try:
            records,_,_=self.driver.execute_query(query,database_=self.database)
            result=[]
            for record in records:
                relationship=record["r"]
                properties=self._deserialize_properties(dict(relationship))
                relationship_id=properties.pop("relationship_id")
                subject_id=properties.pop("subject_id")
                result.append(
                    GraphRelationshipV1(
                        relationship_id=relationship_id,
                        relationship_type=self._relationship_enum(relationship.type),
                        from_node_id=record["from_node_id"],
                        to_node_id=record["to_node_id"],
                        subject_id=subject_id,
                        properties=properties,
                    )
                )
            return result
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j all_relationships failed: {exc}") from exc
    def all_memories(self)->list[GraphMemoryRecordV1]:
        query="""
        MATCH (m:Memory)
        RETURN m
        ORDER BY m.memory_id
        """
        try:
            records,_,_=self.driver.execute_query(query,database_=self.database)
            return [self._record_to_memory(record["m"]) for record in records]
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j all_memories failed: {exc}") from exc
    def _record_to_memory(self,node:Any)->GraphMemoryRecordV1:
        properties=dict(node)
        return GraphMemoryRecordV1(
            memory_id=properties["memory_id"],
            subject_id=properties["subject_id"],
            subject_scope=properties["subject_scope"],
            memory_type=properties["memory_type"],
            normalized_fact=properties["normalized_fact"],
            confidence=float(properties["confidence"]),
            source_event_ids=list(properties.get("source_event_ids",[])),
            source_session_ids=list(properties.get("source_session_ids",[])),
            created_at=self._neo4j_to_python(properties.get("created_at")),
            recorded_at=self._neo4j_to_python(properties.get("recorded_at")),
            valid_from=self._neo4j_to_python(properties.get("valid_from")),
            valid_to=self._neo4j_to_python(properties.get("valid_to")),
            status=MemoryStatus(properties["status"]),
            retention_class=properties["retention_class"],
            retrieval_eligible=bool(properties["retrieval_eligible"]),
            embedding_eligible=bool(properties["embedding_eligible"]),
            entities=json.loads(properties.get("entities_json","[]")),
            correction_of_memory_id=properties.get("correction_of_memory_id"),
            supersedes_memory_id=properties.get("supersedes_memory_id"),
            metadata=json.loads(properties.get("metadata_json","{}")),
        )
    def _memory_parameters(self,memory:GraphMemoryRecordV1)->dict[str,Any]:
        return {
            "memory_id":memory.memory_id,
            "subject_id":memory.subject_id,
            "subject_scope":memory.subject_scope,
            "memory_type":memory.memory_type,
            "normalized_fact":memory.normalized_fact,
            "confidence":memory.confidence,
            "source_event_ids":list(memory.source_event_ids),
            "source_session_ids":list(memory.source_session_ids),
            "created_at":self._neo4j_value(memory.created_at),
            "recorded_at":self._neo4j_value(memory.recorded_at),
            "valid_from":self._neo4j_value(memory.valid_from),
            "valid_to":self._neo4j_value(memory.valid_to),
            "status":memory.status.value,
            "retention_class":memory.retention_class,
            "retrieval_eligible":memory.retrieval_eligible,
            "embedding_eligible":memory.embedding_eligible,
            "entities_json":json.dumps(memory.entities,default=str),
            "correction_of_memory_id":memory.correction_of_memory_id,
            "supersedes_memory_id":memory.supersedes_memory_id,
            "metadata_json":json.dumps(memory.metadata,default=str),
        }
    @staticmethod
    def _node_label(node_type:GraphNodeType)->str:
        mapping={
            GraphNodeType.SUBJECT:"Subject",
            GraphNodeType.MEMORY:"Memory",
            GraphNodeType.ENTITY:"Entity",
        }
        return mapping[node_type]
    @staticmethod
    def _relationship_type(relationship_type:GraphRelationshipType)->str:
        mapping={
            GraphRelationshipType.SUBJECT_HAS_MEMORY:"SUBJECT_HAS_MEMORY",
            GraphRelationshipType.MEMORY_REFERENCES_ENTITY:"MEMORY_REFERENCES_ENTITY",
            GraphRelationshipType.MEMORY_SUPERSEDES:"MEMORY_SUPERSEDES",
            GraphRelationshipType.MEMORY_CORRECTS:"MEMORY_CORRECTS",
        }
        return mapping[relationship_type]
    @staticmethod
    def _relationship_enum(relationship_type:str)->GraphRelationshipType:
        mapping={
            "SUBJECT_HAS_MEMORY":GraphRelationshipType.SUBJECT_HAS_MEMORY,
            "MEMORY_REFERENCES_ENTITY":GraphRelationshipType.MEMORY_REFERENCES_ENTITY,
            "MEMORY_SUPERSEDES":GraphRelationshipType.MEMORY_SUPERSEDES,
            "MEMORY_CORRECTS":GraphRelationshipType.MEMORY_CORRECTS,
        }
        if relationship_type not in mapping:
            raise RuntimeError(f"Unsupported Neo4j relationship type: {relationship_type}")
        return mapping[relationship_type]
    @classmethod
    def _serialize_node_properties(cls,properties:dict[str,Any])->dict[str,Any]:
        result={}
        for key,value in properties.items():
            if key=="metadata":
                result["metadata_json"]=json.dumps(value,default=str)
            elif key in {"created_at","recorded_at","valid_from","valid_to"}:
                result[key]=cls._neo4j_value(value)
            elif isinstance(value,list) and all(
                isinstance(item,(str,int,float,bool)) or item is None
                for item in value): 
                   result[key]=value   
            elif isinstance(value,dict):
                result[f"{key}_json"]=json.dumps(value,default=str)
            elif isinstance(value,list):
                result[f"{key}_json"]=json.dumps(value,default=str)    
            else:
                result[key]=value
        return result
    @classmethod
    def _deserialize_node_properties(cls,properties:dict[str,Any])->dict[str,Any]:
        result={}
        for key,value in properties.items():
            if key.endswith("_json"):
                base_key=key[:-5]
                try:
                    result[base_key]=json.loads(value)
                except (TypeError,json.JSONDecodeError):
                    result[base_key]=value
            else:
                result[key]=cls._neo4j_to_python(value)
        return result
    @classmethod
    def _serialize_properties(cls,properties:dict[str,Any])->dict[str,Any]:
        result={}
        for key,value in properties.items():
            if isinstance(value,(dict,list)):
                result[f"{key}_json"]=json.dumps(value,default=str)
            elif isinstance(value,(datetime,date,time)):
                result[key]=cls._neo4j_value(value)
            else:
                result[key]=value
        return result
    @classmethod
    def _deserialize_properties(cls,properties:dict[str,Any])->dict[str,Any]:
        result={}
        for key,value in properties.items():
            if key.endswith("_json"):
                base_key=key[:-5]
                try:
                    result[base_key]=json.loads(value)
                except (TypeError,json.JSONDecodeError):
                    result[base_key]=value
            else:
                result[key]=cls._neo4j_to_python(value)
        return result
    @staticmethod
    def _neo4j_value(value:Any)->Any:
        if value is None:
            return None
        if isinstance(value,(datetime,date,time)):
            return value
        return value
    @staticmethod
    def _neo4j_to_python(value:Any)->Any:
        return value