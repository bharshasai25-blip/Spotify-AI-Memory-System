from datetime import datetime
from typing import Optional,Any
import json
import os
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import MemoryStore,MemoryRecordV1,MemoryStatus
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryType
from backend_memory_pipeline.policy_consent.policy_consent import RetentionClass
class PostgreSQLMemoryStore(MemoryStore):
    def __init__(
        self,
        host:Optional[str]=None,
        port:Optional[int]=None,
        database:Optional[str]=None,
        user:Optional[str]=None,
        password:Optional[str]=None
    ):
        self.host=host or os.getenv("POSTGRES_HOST","localhost")
        self.port=port or int(os.getenv("POSTGRES_PORT","5432"))
        self.database=database or os.getenv("POSTGRES_DB","spotify_memory")
        self.user=user or os.getenv("POSTGRES_USER","spotify_memory")
        self.password=password or os.getenv("POSTGRES_PASSWORD","spotify_memory_password")
        self._ensure_table()
    def _connect(self):
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            row_factory=dict_row
        )
    def _ensure_table(self)->None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories(
                        memory_id TEXT PRIMARY KEY,
                        schema_version TEXT NOT NULL DEFAULT '1.0',
                        subject_id TEXT NOT NULL,
                        subject_scope TEXT NOT NULL,
                        memory_type TEXT NOT NULL,
                        normalized_fact TEXT NOT NULL,
                        entities JSONB NOT NULL DEFAULT '[]'::jsonb,
                        confidence DOUBLE PRECISION NOT NULL,
                        source_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        source_session_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL,
                        valid_from TIMESTAMPTZ NOT NULL,
                        valid_to TIMESTAMPTZ,
                        status TEXT NOT NULL,
                        retention_class TEXT NOT NULL,
                        retrieval_eligible BOOLEAN NOT NULL DEFAULT TRUE,
                        embedding_eligible BOOLEAN NOT NULL DEFAULT TRUE,
                        correction_of_memory_id TEXT,
                        supersedes_memory_id TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        CONSTRAINT memories_subject_scope_check CHECK(subject_id=subject_scope),
                        CONSTRAINT memories_confidence_check CHECK(confidence>=0.0 AND confidence<=1.0)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS memories_active_equivalent_idx
                    ON memories(
                        subject_id,
                        memory_type,
                        lower(btrim(normalized_fact))
                    )
                    WHERE status='active'
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS memories_subject_idx
                    ON memories(subject_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS memories_subject_status_idx
                    ON memories(subject_id,status)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS memories_subject_type_idx
                    ON memories(subject_id,memory_type)
                    """
                )
            connection.commit()
    @staticmethod
    def _row_to_memory(row:Optional[dict])->Optional[MemoryRecordV1]:
        if row is None:
            return None
        return MemoryRecordV1(
            schema_version=row["schema_version"],
            memory_id=row["memory_id"],
            subject_id=row["subject_id"],
            subject_scope=row["subject_scope"],
            memory_type=MemoryType(row["memory_type"]),
            normalized_fact=row["normalized_fact"],
            entities=list(row["entities"] or []),
            confidence=float(row["confidence"]),
            source_event_ids=list(row["source_event_ids"] or []),
            source_session_ids=list(row["source_session_ids"] or []),
            created_at=row["created_at"],
            recorded_at=row["recorded_at"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            status=MemoryStatus(row["status"]),
            retention_class=RetentionClass(row["retention_class"]),
            retrieval_eligible=bool(row["retrieval_eligible"]),
            embedding_eligible=bool(row["embedding_eligible"]),
            correction_of_memory_id=row["correction_of_memory_id"],
            supersedes_memory_id=row["supersedes_memory_id"],
            metadata=dict(row["metadata"] or {})
        )
    def get(self,memory_id:str)->Optional[MemoryRecordV1]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        schema_version,
                        memory_id,
                        subject_id,
                        subject_scope,
                        memory_type,
                        normalized_fact,
                        entities,
                        confidence,
                        source_event_ids,
                        source_session_ids,
                        created_at,
                        recorded_at,
                        valid_from,
                        valid_to,
                        status,
                        retention_class,
                        retrieval_eligible,
                        embedding_eligible,
                        correction_of_memory_id,
                        supersedes_memory_id,
                        metadata
                    FROM memories
                    WHERE memory_id=%s
                    """,
                    (memory_id,)
                )
                row=cursor.fetchone()
        return self._row_to_memory(row)
    def put(self,memory:MemoryRecordV1)->None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO memories(
                        memory_id,
                        schema_version,
                        subject_id,
                        subject_scope,
                        memory_type,
                        normalized_fact,
                        entities,
                        confidence,
                        source_event_ids,
                        source_session_ids,
                        created_at,
                        recorded_at,
                        valid_from,
                        valid_to,
                        status,
                        retention_class,
                        retrieval_eligible,
                        embedding_eligible,
                        correction_of_memory_id,
                        supersedes_memory_id,
                        metadata
                    )
                    VALUES(
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT(memory_id)
                    DO UPDATE SET
                        schema_version=EXCLUDED.schema_version,
                        subject_id=EXCLUDED.subject_id,
                        subject_scope=EXCLUDED.subject_scope,
                        memory_type=EXCLUDED.memory_type,
                        normalized_fact=EXCLUDED.normalized_fact,
                        entities=EXCLUDED.entities,
                        confidence=EXCLUDED.confidence,
                        source_event_ids=EXCLUDED.source_event_ids,
                        source_session_ids=EXCLUDED.source_session_ids,
                        created_at=EXCLUDED.created_at,
                        recorded_at=EXCLUDED.recorded_at,
                        valid_from=EXCLUDED.valid_from,
                        valid_to=EXCLUDED.valid_to,
                        status=EXCLUDED.status,
                        retention_class=EXCLUDED.retention_class,
                        retrieval_eligible=EXCLUDED.retrieval_eligible,
                        embedding_eligible=EXCLUDED.embedding_eligible,
                        correction_of_memory_id=EXCLUDED.correction_of_memory_id,
                        supersedes_memory_id=EXCLUDED.supersedes_memory_id,
                        metadata=EXCLUDED.metadata
                    """,
                    (
                        memory.memory_id,
                        memory.schema_version,
                        memory.subject_id,
                        memory.subject_scope,
                        memory.memory_type.value,
                        memory.normalized_fact,
                        Jsonb(memory.entities),
                        memory.confidence,
                        Jsonb(memory.source_event_ids),
                        Jsonb(memory.source_session_ids),
                        memory.created_at,
                        memory.recorded_at,
                        memory.valid_from,
                        memory.valid_to,
                        memory.status.value,
                        memory.retention_class.value,
                        memory.retrieval_eligible,
                        memory.embedding_eligible,
                        memory.correction_of_memory_id,
                        memory.supersedes_memory_id,
                        Jsonb(memory.metadata)
                    )
                )
            connection.commit()
    def delete(self,memory_id:str)->None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM memories WHERE memory_id=%s",
                    (memory_id,)
                )
            connection.commit()
    def find_equivalent(
        self,
        subject_id:str,
        memory_type:MemoryType,
        normalized_fact:str
    )->Optional[MemoryRecordV1]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        schema_version,
                        memory_id,
                        subject_id,
                        subject_scope,
                        memory_type,
                        normalized_fact,
                        entities,
                        confidence,
                        source_event_ids,
                        source_session_ids,
                        created_at,
                        recorded_at,
                        valid_from,
                        valid_to,
                        status,
                        retention_class,
                        retrieval_eligible,
                        embedding_eligible,
                        correction_of_memory_id,
                        supersedes_memory_id,
                        metadata
                    FROM memories
                    WHERE subject_id=%s
                    AND memory_type=%s
                    AND status='active'
                    AND lower(btrim(normalized_fact))=lower(btrim(%s))
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (
                        subject_id,
                        memory_type.value,
                        normalized_fact
                    )
                )
                row=cursor.fetchone()
        return self._row_to_memory(row)
    def list_by_subject(self,subject_id:str)->list[MemoryRecordV1]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        schema_version,
                        memory_id,
                        subject_id,
                        subject_scope,
                        memory_type,
                        normalized_fact,
                        entities,
                        confidence,
                        source_event_ids,
                        source_session_ids,
                        created_at,
                        recorded_at,
                        valid_from,
                        valid_to,
                        status,
                        retention_class,
                        retrieval_eligible,
                        embedding_eligible,
                        correction_of_memory_id,
                        supersedes_memory_id,
                        metadata
                    FROM memories
                    WHERE subject_id=%s
                    ORDER BY created_at DESC
                    """,
                    (subject_id,)
                )
                rows=cursor.fetchall()
        return [
            memory
            for row in rows
            if (memory:=self._row_to_memory(row)) is not None
        ]