from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

class PostgreSQLUserEntityActionRepository:
    """Persistent user-specific follow/save/preference list state."""
    def __init__(self, host=None, port=None, database=None, user=None, password=None):
        self.host=host or os.getenv('POSTGRES_HOST','localhost')
        self.port=port or int(os.getenv('POSTGRES_PORT','5432'))
        self.database=database or os.getenv('POSTGRES_DB','spotify_memory')
        self.user=user or os.getenv('POSTGRES_USER','spotify_memory')
        self.password=password or os.getenv('POSTGRES_PASSWORD','spotify_memory_password')
        self._ensure_table()
    def _connect(self):
        return psycopg.connect(host=self.host,port=self.port,dbname=self.database,user=self.user,password=self.password,row_factory=dict_row)
    def _ensure_table(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TABLE IF NOT EXISTS user_entity_actions (
                    subject_id TEXT NOT NULL,
                    canonical_entity_id TEXT NOT NULL REFERENCES entities(canonical_entity_id) ON DELETE CASCADE,
                    action_type TEXT NOT NULL CHECK (action_type IN ('follow','save','preference')),
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY(subject_id,canonical_entity_id,action_type)
                )''')
                cur.execute('CREATE INDEX IF NOT EXISTS user_entity_actions_subject_active_idx ON user_entity_actions(subject_id,active,action_type)')
            conn.commit()
    def set_action(self, subject_id: str, entity_id: str, action_type: str, active: bool, metadata: dict[str,Any] | None = None) -> dict[str,Any]:
        now=datetime.now(timezone.utc)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('''INSERT INTO user_entity_actions(subject_id,canonical_entity_id,action_type,active,metadata,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(subject_id,canonical_entity_id,action_type) DO UPDATE SET active=EXCLUDED.active,metadata=user_entity_actions.metadata || EXCLUDED.metadata,updated_at=EXCLUDED.updated_at
                    RETURNING subject_id,canonical_entity_id,action_type,active,metadata,created_at,updated_at''',
                    (subject_id,entity_id,action_type,bool(active),Jsonb(dict(metadata or {})),now,now))
                row=cur.fetchone()
            conn.commit()
        return self._serialize(row)
    def get_action_record(self, subject_id: str, entity_id: str, action_type: str) -> dict[str,Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT subject_id,canonical_entity_id,action_type,active,metadata,created_at,updated_at FROM user_entity_actions WHERE subject_id=%s AND canonical_entity_id=%s AND action_type=%s',(subject_id,entity_id,action_type))
                row=cur.fetchone()
        return self._serialize(row) if row else None
    def get_actions(self, subject_id: str) -> dict[str,dict[str,bool]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT canonical_entity_id,action_type,active FROM user_entity_actions WHERE subject_id=%s',(subject_id,))
                rows=cur.fetchall()
        result={}
        for row in rows:
            result.setdefault(row['canonical_entity_id'],{'follow':False,'save':False,'preference':False,'_has_preference_record':False})[row['action_type']]=bool(row['active'])
            if row['action_type']=='preference': result[row['canonical_entity_id']]['_has_preference_record']=True
        return result
    def list_active(self, subject_id: str, action_type: str | None = None) -> list[dict[str,Any]]:
        sql='SELECT subject_id,canonical_entity_id,action_type,active,metadata,created_at,updated_at FROM user_entity_actions WHERE subject_id=%s AND active=TRUE'
        params=[subject_id]
        if action_type:
            sql+=' AND action_type=%s'; params.append(action_type)
        sql+=' ORDER BY updated_at DESC'
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql,params); rows=cur.fetchall()
        return [self._serialize(row) for row in rows]
    @staticmethod
    def _serialize(row):
        if row is None: return None
        metadata=row.get('metadata') or {}
        return {'subject_id':row['subject_id'],'entity_id':row['canonical_entity_id'],'action_type':row['action_type'],'active':bool(row['active']),'metadata':dict(metadata) if isinstance(metadata,dict) else {},'created_at':row['created_at'].isoformat() if row.get('created_at') else None,'updated_at':row['updated_at'].isoformat() if row.get('updated_at') else None}
