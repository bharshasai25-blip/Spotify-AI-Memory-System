from __future__ import annotations
import os
from datetime import datetime,timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from backend_memory_pipeline.memory_extraction.memory_extraction import BehavioralState,BehavioralStateStore

class PostgreSQLBehavioralStateStore:
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
                    CREATE TABLE IF NOT EXISTS behavioral_state(
                        subject_id TEXT NOT NULL,
                        content_key TEXT NOT NULL,
                        saved BOOLEAN NOT NULL DEFAULT FALSE,
                        followed BOOLEAN NOT NULL DEFAULT FALSE,
                        save_count INTEGER NOT NULL DEFAULT 0,
                        follow_count INTEGER NOT NULL DEFAULT 0,
                        playback_count INTEGER NOT NULL DEFAULT 0,
                        skip_count INTEGER NOT NULL DEFAULT 0,
                        source_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                        last_event_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY(subject_id,content_key),
                        CHECK(save_count>=0),
                        CHECK(follow_count>=0),
                        CHECK(playback_count>=0),
                        CHECK(skip_count>=0)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS behavioral_state_subject_idx
                    ON behavioral_state(subject_id)
                    """
                )
            conn.commit()
    def get(self,subject_id: str,content_key: str)->Optional[BehavioralState]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        subject_id,
                        content_key,
                        saved,
                        followed,
                        save_count,
                        follow_count,
                        playback_count,
                        skip_count,
                        source_event_ids,
                        last_event_at
                    FROM behavioral_state
                    WHERE subject_id=%s AND content_key=%s
                    """,
                    (subject_id,content_key)
                )
                row=cursor.fetchone()
        if row is None:
            return None
        source_event_ids=row["source_event_ids"] or []
        if isinstance(source_event_ids,str):
            import json
            source_event_ids=json.loads(source_event_ids)
        return BehavioralState(
            subject_id=row["subject_id"],
            content_key=row["content_key"],
            saved=row["saved"],
            followed=row["followed"],
            save_count=row["save_count"],
            follow_count=row["follow_count"],
            playback_count=row["playback_count"],
            skip_count=row["skip_count"],
            source_event_ids=source_event_ids,
            last_event_at=row["last_event_at"]
        )
    def put(self,state: BehavioralState)->None:
        now=datetime.now(timezone.utc)
        source_event_ids=list(dict.fromkeys(state.source_event_ids))
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO behavioral_state(
                        subject_id,
                        content_key,
                        saved,
                        followed,
                        save_count,
                        follow_count,
                        playback_count,
                        skip_count,
                        source_event_ids,
                        last_event_at,
                        created_at,
                        updated_at
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(subject_id,content_key)
                    DO UPDATE SET
                        saved=EXCLUDED.saved,
                        followed=EXCLUDED.followed,
                        save_count=EXCLUDED.save_count,
                        follow_count=EXCLUDED.follow_count,
                        playback_count=EXCLUDED.playback_count,
                        skip_count=EXCLUDED.skip_count,
                        source_event_ids=EXCLUDED.source_event_ids,
                        last_event_at=EXCLUDED.last_event_at,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (
                        state.subject_id,
                        state.content_key,
                        state.saved,
                        state.followed,
                        state.save_count,
                        state.follow_count,
                        state.playback_count,
                        state.skip_count,
                        Jsonb(source_event_ids),
                        state.last_event_at,
                        now,
                        now
                    )
                )
            conn.commit()

