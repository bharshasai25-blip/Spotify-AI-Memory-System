from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

class PostgreSQLConversationRepository:
    """Persist chat transcripts separately from governed long-term memories."""
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, database: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
        self.database = database or os.getenv("POSTGRES_DB", "spotify_memory")
        self.user = user or os.getenv("POSTGRES_USER", "spotify_memory")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "spotify_memory_password")
        self._ensure_table()
    def _connect(self):
        return psycopg.connect(host=self.host, port=self.port, dbname=self.database, user=self.user, password=self.password, row_factory=dict_row)
    def _ensure_table(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""CREATE TABLE IF NOT EXISTS conversation_messages(
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL
                )""")
                cursor.execute("CREATE INDEX IF NOT EXISTS conversation_messages_owner_idx ON conversation_messages(subject_id, conversation_id, created_at)")
            connection.commit()
    def list_messages(self, subject_id: str, conversation_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT message_id, conversation_id, subject_id, role, content, metadata, created_at
                    FROM conversation_messages WHERE subject_id=%s AND conversation_id=%s
                    ORDER BY created_at DESC, message_id DESC LIMIT %s""", (subject_id, conversation_id, max(1, min(limit, 5000))))
                rows = cursor.fetchall()
        rows.reverse()
        return [{**row, "metadata": dict(row["metadata"] or {}), "created_at": row["created_at"].isoformat()} for row in rows]
    def append_message(self, subject_id: str, conversation_id: str, role: str, content: str, metadata: Optional[dict] = None) -> dict[str, Any]:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        if not content or not content.strip():
            raise ValueError("content cannot be empty")
        row = {"message_id": str(uuid4()), "conversation_id": conversation_id, "subject_id": subject_id, "role": role, "content": content.strip(), "metadata": dict(metadata or {}), "created_at": datetime.now(timezone.utc)}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO conversation_messages(message_id,conversation_id,subject_id,role,content,metadata,created_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)""", (row["message_id"], row["conversation_id"], row["subject_id"], row["role"], row["content"], Jsonb(row["metadata"]), row["created_at"]))
            connection.commit()
        row["created_at"] = row["created_at"].isoformat()
        return row
