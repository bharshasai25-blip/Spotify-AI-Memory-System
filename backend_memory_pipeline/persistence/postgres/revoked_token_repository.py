from __future__ import annotations
import os
from datetime import datetime,timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row

class PostgreSQLRevokedTokenStore:
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
                    CREATE TABLE IF NOT EXISTS revoked_tokens(
                        token_id TEXT PRIMARY KEY,
                        revoked_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            conn.commit()
    def revoke(self,token_id:str)->None:
        if not token_id or not token_id.strip():
            raise ValueError("token_id is required.")
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO revoked_tokens(token_id,revoked_at)
                    VALUES(%s,%s)
                    ON CONFLICT(token_id) DO NOTHING
                    """,
                    (token_id,datetime.now(timezone.utc))
                )
            conn.commit()
    def is_revoked(self,token_id:str)->bool:
        if not token_id:
            return False
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM revoked_tokens
                    WHERE token_id=%s
                    """,
                    (token_id,)
                )
                return cursor.fetchone() is not None
    def clear(self)->None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM revoked_tokens")
            conn.commit()