from __future__ import annotations
from typing import Protocol
from backend_memory_pipeline.entity_resolution.entity_resolution import CatalogEntityV1

class CatalogEnrichmentService(Protocol):
    def enrich(
        self,
        entity_type: str,
        query: str,
    ) -> CatalogEntityV1:
        ...