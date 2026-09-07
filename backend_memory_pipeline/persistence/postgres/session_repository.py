from datetime import datetime
from typing import Optional
import os
import psycopg
from psycopg.rows import dict_row
from backend_memory_pipeline.session_management.session_management import SessionStateV1,SessionStatus,SessionStore
class PostgreSQLSessionStore(SessionStore):
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
                    CREATE TABLE IF NOT EXISTS sessions(
                        session_id TEXT PRIMARY KEY,
                        subject_id TEXT NOT NULL,
                        session_start TIMESTAMPTZ NOT NULL,
                        last_activity_at TIMESTAMPTZ NOT NULL,
                        session_end TIMESTAMPTZ,
                        primary_domain TEXT,
                        session_context TEXT,
                        device_type TEXT,
                        platform TEXT,
                        synthetic BOOLEAN NOT NULL DEFAULT FALSE,
                        status TEXT NOT NULL,
                        schema_version TEXT NOT NULL DEFAULT '1.0'
                    )
                    """
                )
            connection.commit()
    @staticmethod
    def _row_to_session(row:Optional[dict])->Optional[SessionStateV1]:
        if row is None:
            return None
        return SessionStateV1(
            schema_version=row["schema_version"],
            session_id=row["session_id"],
            subject_id=row["subject_id"],
            session_start=row["session_start"],
            last_activity_at=row["last_activity_at"],
            session_end=row["session_end"],
            primary_domain=row["primary_domain"],
            session_context=row["session_context"],
            device_type=row["device_type"],
            platform=row["platform"],
            synthetic=row["synthetic"],
            status=SessionStatus(row["status"])
        )
    def get(self,session_id:str)->Optional[SessionStateV1]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        schema_version,
                        session_id,
                        subject_id,
                        session_start,
                        last_activity_at,
                        session_end,
                        primary_domain,
                        session_context,
                        device_type,
                        platform,
                        synthetic,
                        status
                    FROM sessions
                    WHERE session_id=%s
                    """,
                    (session_id,)
                )
                row=cursor.fetchone()
        return self._row_to_session(row)
    def save(self,session:SessionStateV1)->None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sessions(
                        schema_version,
                        session_id,
                        subject_id,
                        session_start,
                        last_activity_at,
                        session_end,
                        primary_domain,
                        session_context,
                        device_type,
                        platform,
                        synthetic,
                        status
                    )
                    VALUES(
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT(session_id)
                    DO UPDATE SET
                        schema_version=EXCLUDED.schema_version,
                        subject_id=EXCLUDED.subject_id,
                        session_start=EXCLUDED.session_start,
                        last_activity_at=EXCLUDED.last_activity_at,
                        session_end=EXCLUDED.session_end,
                        primary_domain=EXCLUDED.primary_domain,
                        session_context=EXCLUDED.session_context,
                        device_type=EXCLUDED.device_type,
                        platform=EXCLUDED.platform,
                        synthetic=EXCLUDED.synthetic,
                        status=EXCLUDED.status
                    """,
                    (
                        session.schema_version,
                        session.session_id,
                        session.subject_id,
                        session.session_start,
                        session.last_activity_at,
                        session.session_end,
                        session.primary_domain,
                        session.session_context,
                        session.device_type,
                        session.platform,
                        session.synthetic,
                        session.status.value
                    )
                )
            connection.commit()
    def delete(self,session_id:str)->None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sessions WHERE session_id=%s",
                    (session_id,)
                )
            connection.commit()
    def list_by_subject(self,subject_id:str)->list[SessionStateV1]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        schema_version,
                        session_id,
                        subject_id,
                        session_start,
                        last_activity_at,
                        session_end,
                        primary_domain,
                        session_context,
                        device_type,
                        platform,
                        synthetic,
                        status
                    FROM sessions
                    WHERE subject_id=%s
                    ORDER BY session_start DESC
                    """,
                    (subject_id,)
                )
                rows=cursor.fetchall()
        return [
            session
            for row in rows
            if (session:=self._row_to_session(row)) is not None
        ]
    def list_all(self)->list[SessionStateV1]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        schema_version,
                        session_id,
                        subject_id,
                        session_start,
                        last_activity_at,
                        session_end,
                        primary_domain,
                        session_context,
                        device_type,
                        platform,
                        synthetic,
                        status
                    FROM sessions
                    ORDER BY session_start DESC
                    """
                )
                rows=cursor.fetchall()
        return [
            session
            for row in rows
            if (session:=self._row_to_session(row)) is not None
        ]