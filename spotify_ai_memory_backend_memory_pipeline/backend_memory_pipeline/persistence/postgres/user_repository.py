from datetime import datetime,timezone
from typing import Optional,Any
import json
import os
import secrets
import psycopg
from psycopg.rows import dict_row
class PostgreSQLUserRepository:
    def __init__(
        self,
        api_user_class:Any,
        host:Optional[str]=None,
        port:Optional[int]=None,
        database:Optional[str]=None,
        user:Optional[str]=None,
        password:Optional[str]=None
    ):
        self.api_user_class=api_user_class
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
                    CREATE TABLE IF NOT EXISTS users(
                        username TEXT PRIMARY KEY,
                        subject_id TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
            connection.commit()
    def _row_to_user(self,row:Optional[dict])->Optional[Any]:
        if row is None:
            return None
        return self.api_user_class(
            username=row["username"],
            subject_id=row["subject_id"],
            password_hash=row["password_hash"],
            metadata=dict(row["metadata"] or {})
        )
    def get_by_username(self,username:str)->Optional[Any]:
        normalized_username=username.strip().lower()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT username,subject_id,password_hash,metadata
                    FROM users
                    WHERE username=%s
                    """,
                    (normalized_username,)
                )
                row=cursor.fetchone()
        return self._row_to_user(row)
    def get_by_subject_id(self,subject_id:str)->Optional[Any]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT username,subject_id,password_hash,metadata
                    FROM users
                    WHERE subject_id=%s
                    """,
                    (subject_id,)
                )
                row=cursor.fetchone()
        return self._row_to_user(row)
    def create_user(
        self,
        username:str,
        password_hash:str,
        subject_id:Optional[str]=None,
        metadata:Optional[dict[str,object]]=None
    )->Any:
        normalized_username=username.strip().lower()
        if not normalized_username:
            raise ValueError("username cannot be empty.")
        new_subject_id=subject_id or f"USER_{secrets.token_hex(12).upper()}"
        metadata_value=dict(metadata or {})
        now=datetime.now(timezone.utc)
        try:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users(
                            username,
                            subject_id,
                            password_hash,
                            metadata,
                            created_at,
                            updated_at
                        )
                        VALUES(%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            normalized_username,
                            new_subject_id,
                            password_hash,
                            json.dumps(metadata_value),
                            now,
                            now
                        )
                    )
                connection.commit()
        except psycopg.errors.UniqueViolation as exc:
            raise ValueError("username already exists.") from exc
        return self.get_by_username(normalized_username)

