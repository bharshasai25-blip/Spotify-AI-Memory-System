from __future__ import annotations
import os
from datetime import datetime,timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row
class PostgreSQLIdempotencyStore:
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
                    CREATE TABLE IF NOT EXISTS idempotency_records(
                        idempotency_key TEXT PRIMARY KEY,
                        event_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idempotency_records_event_id_idx
                        ON idempotency_records(event_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_deletion_records(
                        memory_id TEXT PRIMARY KEY,
                        subject_id TEXT NOT NULL,
                        lifecycle_event_id TEXT NOT NULL,
                        deleted_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS memory_deletion_records_subject_id_idx
                        ON memory_deletion_records(subject_id)
                    """
                )
            conn.commit()
    def get_event_id(self,idempotency_key:str)->Optional[str]:
        if not idempotency_key:
            return None
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT event_id
                    FROM idempotency_records
                    WHERE idempotency_key=%s
                    """,
                    (idempotency_key,)
                )
                row=cursor.fetchone()
        return None if row is None else row["event_id"]
    def register(self,idempotency_key:str,event_id:str)->None:
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required.")
        if not event_id or not event_id.strip():
            raise ValueError("event_id is required.")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO idempotency_records(
                        idempotency_key,
                        event_id,
                        created_at
                    )
                    VALUES(%s,%s,%s)
                    ON CONFLICT(idempotency_key) DO NOTHING
                    """,
                    (
                        idempotency_key,
                        event_id,
                        datetime.now(timezone.utc)
                    )
                )
            conn.commit()
    def clear(self)->None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM idempotency_records")
            conn.commit()
    def get_deletion_record(
        self,
        memory_id:str,
        subject_id:str
    )->Optional[dict]:
        if not memory_id or not memory_id.strip():
           return None
        if not subject_id or not subject_id.strip():
           return None
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                       memory_id,
                       subject_id,
                       lifecycle_event_id,
                       deleted_at
                    FROM memory_deletion_records
                    WHERE memory_id=%s
                    AND subject_id=%s
                    """,
                    (memory_id,subject_id)
                )
                row=cursor.fetchone()
        return None if row is None else dict(row)

    def register_deletion(
        self,
        memory_id:str,
        subject_id:str,
        lifecycle_event_id:str,
        deleted_at:datetime
    )->None:
        if not memory_id or not memory_id.strip():
            raise ValueError("memory_id is required.")
        if not subject_id or not subject_id.strip():
            raise ValueError("subject_id is required.")
        if not lifecycle_event_id or not lifecycle_event_id.strip():
            raise ValueError("lifecycle_event_id is required.")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO memory_deletion_records(
                       memory_id,
                       subject_id,
                       lifecycle_event_id,
                       deleted_at
                    )
                    VALUES(%s,%s,%s,%s)
                    ON CONFLICT(memory_id) DO NOTHING
                    """,
                    (
                      memory_id,
                      subject_id,
                      lifecycle_event_id,
                      deleted_at
                    )
                )
            conn.commit()