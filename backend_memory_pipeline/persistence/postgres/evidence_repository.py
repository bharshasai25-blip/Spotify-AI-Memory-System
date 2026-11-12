from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend_memory_pipeline.ingestion.ingestion import InteractionEventV1

class PostgreSQLEvidenceHistoryStore:
    def __init__(
        self,
        host: Optional[str]=None,
        port: Optional[int]=None,
        database: Optional[str]=None,
        user: Optional[str]=None,
        password: Optional[str]=None,
        max_events_per_subject: int=100
    ):
        self.host=host or os.getenv("POSTGRES_HOST","localhost")
        self.port=port or int(os.getenv("POSTGRES_PORT","5432"))
        self.database=database or os.getenv("POSTGRES_DB","spotify_memory")
        self.user=user or os.getenv("POSTGRES_USER","spotify_memory")
        self.password=password or os.getenv("POSTGRES_PASSWORD","spotify_memory_password")
        self.max_events_per_subject=max_events_per_subject
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
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_evidence(
                        event_id TEXT PRIMARY KEY,
                        source_event_id TEXT NOT NULL,
                        subject_id TEXT NOT NULL,
                        subject_scope TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL,
                        event_data JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS memory_evidence_subject_timestamp_idx
                    ON memory_evidence(subject_id,timestamp DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS memory_evidence_subject_event_type_idx
                    ON memory_evidence(subject_id,event_type)
                    """
                )
            conn.commit()
    def get(self,subject_id: str)->list[InteractionEventV1]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT event_data
                    FROM memory_evidence
                    WHERE subject_id=%s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (subject_id,self.max_events_per_subject)
                )
                rows=cursor.fetchall()
        events=[InteractionEventV1(**row["event_data"]) for row in rows]
        events.reverse()
        return events
    def append(self,event: InteractionEventV1)->None:
        event_data=event.model_dump(mode="json")
        created_at=datetime.now(timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO memory_evidence(
                        event_id,
                        source_event_id,
                        subject_id,
                        subject_scope,
                        session_id,
                        event_type,
                        timestamp,
                        event_data,
                        created_at
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(event_id) DO NOTHING
                    """,
                    (
                        event.event_id,
                        event.source_event_id,
                        event.subject_id,
                        event.subject_scope,
                        event.session_id,
                        event.event_type.value if hasattr(event.event_type,"value") else str(event.event_type),
                        event.timestamp,
                        Jsonb(event_data),
                        created_at
                    )
                )
            conn.commit()
    def clear(self,subject_id: Optional[str]=None)->None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                if subject_id is None:
                    cursor.execute("DELETE FROM memory_evidence")
                else:
                    cursor.execute(
                        "DELETE FROM memory_evidence WHERE subject_id=%s",
                        (subject_id,)
                    )
            conn.commit()
    def list_by_subject(self,subject_id: str)->list[InteractionEventV1]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT event_data
                    FROM memory_evidence
                    WHERE subject_id=%s
                    ORDER BY timestamp ASC
                    """,
                    (subject_id,)
                )
                rows=cursor.fetchall()
        return [InteractionEventV1(**row["event_data"]) for row in rows]
    def count_by_subject(self,subject_id: str)->int:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM memory_evidence
                    WHERE subject_id=%s
                    """,
                    (subject_id,)
                )
                row=cursor.fetchone()
        return int(row["count"])

