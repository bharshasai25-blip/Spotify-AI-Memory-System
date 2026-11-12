from __future__ import annotations
import json
import os
from datetime import datetime,timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend_memory_pipeline.ingestion.ingestion import ConsentState
from backend_memory_pipeline.policy_consent.policy_consent import ConsentStateRecordV1,MemoryControlAction,ConsentStateStore
class PostgreSQLConsentStateStore:
    def __init__(
        self,
        host: Optional[str]=None,
        port: Optional[int]=None,
        database: Optional[str]=None,
        user: Optional[str]=None,
        password: Optional[str]=None
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
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS consent_state(
                        subject_id TEXT PRIMARY KEY,
                        subject_scope TEXT NOT NULL,
                        state TEXT NOT NULL,
                        changed_at TIMESTAMPTZ NOT NULL,
                        last_action TEXT NOT NULL,
                        correlation_id TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        CHECK(state IN ('unknown','opted_in','opted_out','paused')),
                        CHECK(last_action IN ('opt_in','opt_out','pause','resume'))
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS consent_state_subject_idx
                    ON consent_state(subject_id)
                    """
                )
            conn.commit()
    def get(self,subject_id:str)->Optional[ConsentStateRecordV1]:
        if not subject_id:
            return None
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        subject_id,
                        subject_scope,
                        state,
                        changed_at,
                        last_action,
                        correlation_id,
                        metadata
                    FROM consent_state
                    WHERE subject_id=%s
                    """,
                    (subject_id,)
                )
                row=cursor.fetchone()
        if row is None:
            return None
        metadata=row["metadata"] or {}
        if isinstance(metadata,str):
            metadata=json.loads(metadata)
        return ConsentStateRecordV1(
            subject_id=row["subject_id"],
            subject_scope=row["subject_scope"],
            state=ConsentState(row["state"]),
            changed_at=row["changed_at"],
            last_action=MemoryControlAction(row["last_action"]),
            correlation_id=row["correlation_id"],
            metadata=metadata
        )
    def put(self,record:ConsentStateRecordV1)->None:
        now=datetime.now(timezone.utc)
        metadata=dict(record.metadata)
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO consent_state(
                        subject_id,
                        subject_scope,
                        state,
                        changed_at,
                        last_action,
                        correlation_id,
                        metadata,
                        created_at,
                        updated_at
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(subject_id)
                    DO UPDATE SET
                        subject_scope=EXCLUDED.subject_scope,
                        state=EXCLUDED.state,
                        changed_at=EXCLUDED.changed_at,
                        last_action=EXCLUDED.last_action,
                        correlation_id=EXCLUDED.correlation_id,
                        metadata=EXCLUDED.metadata,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (
                        record.subject_id,
                        record.subject_scope,
                        record.state.value,
                        record.changed_at,
                        record.last_action.value,
                        record.correlation_id,
                        Jsonb(metadata),
                        now,
                        now
                    )
                )
            conn.commit()
    def clear(self,subject_id:Optional[str]=None)->None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                if subject_id is None:
                    cursor.execute("DELETE FROM consent_state")
                else:
                    cursor.execute(
                        "DELETE FROM consent_state WHERE subject_id=%s",
                        (subject_id,)
                    )
            conn.commit()