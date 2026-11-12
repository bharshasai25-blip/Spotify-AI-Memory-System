from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend_memory_pipeline.entity_resolution.entity_resolution import (
    CatalogEntityV1,
    CatalogRepository,
    EntityType,
    EntityResolutionError,
    EntityResolutionErrorCode,
    normalize_entity_text,
)


class PostgreSQLCatalogRepository(CatalogRepository):
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
        self.database = database or os.getenv("POSTGRES_DB", "spotify_memory")
        self.user = user or os.getenv("POSTGRES_USER", "spotify_memory")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "spotify_memory_password")
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

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entities(
                        canonical_entity_id TEXT PRIMARY KEY,
                        entity_type TEXT NOT NULL,
                        canonical_name TEXT NOT NULL,
                        normalized_name TEXT NOT NULL,
                        aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
                        owner_subject_id TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        CONSTRAINT entities_canonical_name_check
                            CHECK(length(btrim(canonical_name)) > 0)
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS entities_type_name_idx
                    ON entities(entity_type,normalized_name)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS entities_subject_idx
                    ON entities(owner_subject_id)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS entities_name_idx
                    ON entities(normalized_name)
                    """
                )

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS entity_external_mappings(
                        mapping_id TEXT PRIMARY KEY,
                        canonical_entity_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        external_id TEXT NOT NULL,
                        external_url TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        CONSTRAINT entity_external_mapping_entity_fk
                            FOREIGN KEY(canonical_entity_id)
                            REFERENCES entities(canonical_entity_id)
                            ON DELETE CASCADE,
                        CONSTRAINT entity_external_mapping_provider_id_unique
                            UNIQUE(provider,external_id)
                    )
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS entity_external_mapping_entity_idx
                    ON entity_external_mappings(canonical_entity_id)
                    """
                )

                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS entity_external_mapping_provider_idx
                    ON entity_external_mappings(provider)
                    """
                )

            conn.commit()

    @staticmethod
    def _row_to_entity(row: Optional[dict]) -> Optional[CatalogEntityV1]:
        if row is None:
            return None

        aliases = row["aliases"] or []
        if isinstance(aliases, str):
            aliases = json.loads(aliases)

        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return CatalogEntityV1(
            entity_id=row["canonical_entity_id"],
            entity_type=EntityType(row["entity_type"]),
            canonical_name=row["canonical_name"],
            aliases=list(aliases),
            normalized_name=row["normalized_name"],
            owner_subject_id=row["owner_subject_id"],
            metadata=dict(metadata)
        )

    def search(
        self,
        mention: str,
        entity_type: Optional[EntityType] = None
    ) -> Sequence[CatalogEntityV1]:
        normalized_mention = normalize_entity_text(mention)

        if not normalized_mention:
            return []

        with self._connect() as conn:
            with conn.cursor() as cursor:
                if entity_type is None:
                    cursor.execute(
                        """
                        SELECT
                            canonical_entity_id,
                            entity_type,
                            canonical_name,
                            normalized_name,
                            aliases,
                            owner_subject_id,
                            metadata
                        FROM entities
                        WHERE normalized_name=%s
                        OR EXISTS(
                            SELECT 1
                            FROM jsonb_array_elements_text(aliases) AS alias
                            WHERE lower(btrim(alias))=%s
                        )
                        ORDER BY canonical_name ASC
                        """,
                        (
                            normalized_mention,
                            normalized_mention
                        )
                    )
                else:
                    cursor.execute(
                        """
                        SELECT
                            canonical_entity_id,
                            entity_type,
                            canonical_name,
                            normalized_name,
                            aliases,
                            owner_subject_id,
                            metadata
                        FROM entities
                        WHERE entity_type=%s
                        AND (
                            normalized_name=%s
                            OR EXISTS(
                                SELECT 1
                                FROM jsonb_array_elements_text(aliases) AS alias
                                WHERE lower(btrim(alias))=%s
                            )
                        )
                        ORDER BY canonical_name ASC
                        """,
                        (
                            entity_type.value,
                            normalized_mention,
                            normalized_mention
                        )
                    )

                rows = cursor.fetchall()

        return [
            entity
            for row in rows
            if (entity := self._row_to_entity(row)) is not None
        ]

    def search_catalog(self, query: str, entity_type: Optional[EntityType] = None, limit: int = 50) -> list[CatalogEntityV1]:
        """Search the catalog by case-insensitive name/alias substring for the discovery UI."""
        cleaned = " ".join((query or "").strip().casefold().split())
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        if not cleaned:
            return []
        pattern = f"%{cleaned}%"
        with self._connect() as conn:
            with conn.cursor() as cursor:
                if entity_type is None:
                    cursor.execute("""SELECT canonical_entity_id,entity_type,canonical_name,normalized_name,aliases,owner_subject_id,metadata FROM entities WHERE lower(canonical_name) LIKE %s OR normalized_name LIKE %s OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(aliases) AS alias WHERE lower(alias) LIKE %s) ORDER BY canonical_name ASC LIMIT %s""", (pattern, pattern, pattern, limit))
                else:
                    cursor.execute("""SELECT canonical_entity_id,entity_type,canonical_name,normalized_name,aliases,owner_subject_id,metadata FROM entities WHERE entity_type=%s AND (lower(canonical_name) LIKE %s OR normalized_name LIKE %s OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(aliases) AS alias WHERE lower(alias) LIKE %s)) ORDER BY canonical_name ASC LIMIT %s""", (entity_type.value, pattern, pattern, pattern, limit))
                rows=cursor.fetchall()
        return [entity for row in rows if (entity := self._row_to_entity(row)) is not None]

    def get(
        self,
        canonical_entity_id: str
    ) -> Optional[CatalogEntityV1]:
        if not canonical_entity_id:
            return None

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        canonical_entity_id,
                        entity_type,
                        canonical_name,
                        normalized_name,
                        aliases,
                        owner_subject_id,
                        metadata
                    FROM entities
                    WHERE canonical_entity_id=%s
                    """,
                    (canonical_entity_id,)
                )
                row = cursor.fetchone()

        return self._row_to_entity(row)

    def put(self, entity: CatalogEntityV1) -> None:
        if not isinstance(entity, CatalogEntityV1):
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                "Input must be a CatalogEntityV1."
            )

        normalized_name = normalize_entity_text(entity.canonical_name)

        if not normalized_name:
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                "Canonical entity name cannot be empty."
            )

        aliases = list(
            dict.fromkeys(
                alias.strip()
                for alias in entity.aliases
                if alias and alias.strip()
            )
        )

        metadata = dict(entity.metadata)
        now = datetime.now(timezone.utc)

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO entities(
                        canonical_entity_id,
                        entity_type,
                        canonical_name,
                        normalized_name,
                        aliases,
                        owner_subject_id,
                        metadata,
                        created_at,
                        updated_at
                    )
                    VALUES(
                        %s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT(canonical_entity_id)
                    DO UPDATE SET
                        entity_type=EXCLUDED.entity_type,
                        canonical_name=EXCLUDED.canonical_name,
                        normalized_name=EXCLUDED.normalized_name,
                        aliases=EXCLUDED.aliases,
                        owner_subject_id=EXCLUDED.owner_subject_id,
                        metadata=EXCLUDED.metadata,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (
                        entity.entity_id,
                        entity.entity_type.value,
                        entity.canonical_name.strip(),
                        normalized_name,
                        Jsonb(aliases),
                        entity.owner_subject_id,
                        Jsonb(metadata),
                        now,
                        now
                    )
                )

            conn.commit()

    def delete(self, canonical_entity_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM entities
                    WHERE canonical_entity_id=%s
                    """,
                    (canonical_entity_id,)
                )

            conn.commit()

    def add_external_mapping(
        self,
        mapping_id: str,
        canonical_entity_id: str,
        provider: str,
        external_id: str,
        external_url: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> None:
        if not mapping_id:
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                "mapping_id is required."
            )

        if not canonical_entity_id:
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                "canonical_entity_id is required."
            )

        if not provider:
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                "provider is required."
            )

        if not external_id:
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                "external_id is required."
            )

        metadata = dict(metadata or {})
        now = datetime.now(timezone.utc)

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO entity_external_mappings(
                        mapping_id,
                        canonical_entity_id,
                        provider,
                        external_id,
                        external_url,
                        metadata,
                        created_at,
                        updated_at
                    )
                    VALUES(
                        %s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT(provider,external_id)
                    DO UPDATE SET
                        canonical_entity_id=EXCLUDED.canonical_entity_id,
                        external_url=EXCLUDED.external_url,
                        metadata=EXCLUDED.metadata,
                        updated_at=EXCLUDED.updated_at
                    """,
                    (
                        mapping_id,
                        canonical_entity_id,
                        provider.strip().casefold(),
                        external_id.strip(),
                        external_url,
                        Jsonb(metadata),
                        now,
                        now
                    )
                )

            conn.commit()

    def get_external_mapping(
        self,
        provider: str,
        external_id: str
    ) -> Optional[dict]:
        if not provider or not external_id:
            return None

        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mapping_id,
                        canonical_entity_id,
                        provider,
                        external_id,
                        external_url,
                        metadata,
                        created_at,
                        updated_at
                    FROM entity_external_mappings
                    WHERE provider=%s
                    AND external_id=%s
                    """,
                    (
                        provider.strip().casefold(),
                        external_id.strip()
                    )
                )
                row = cursor.fetchone()

        if row is None:
            return None

        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return {
            "mapping_id": row["mapping_id"],
            "canonical_entity_id": row["canonical_entity_id"],
            "provider": row["provider"],
            "external_id": row["external_id"],
            "external_url": row["external_url"],
            "metadata": dict(metadata),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }

    def list_external_mappings(
        self,
        canonical_entity_id: str
    ) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mapping_id,
                        canonical_entity_id,
                        provider,
                        external_id,
                        external_url,
                        metadata,
                        created_at,
                        updated_at
                    FROM entity_external_mappings
                    WHERE canonical_entity_id=%s
                    ORDER BY provider ASC
                    """,
                    (canonical_entity_id,)
                )
                rows = cursor.fetchall()

        mappings = []

        for row in rows:
            metadata = row["metadata"] or {}

            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            mappings.append(
                {
                    "mapping_id": row["mapping_id"],
                    "canonical_entity_id": row["canonical_entity_id"],
                    "provider": row["provider"],
                    "external_id": row["external_id"],
                    "external_url": row["external_url"],
                    "metadata": dict(metadata),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                }
            )

        return mappings