from datetime import datetime,timezone
from fastapi import APIRouter
from backend_memory_pipeline.api.schemas import HealthResponseV1
router=APIRouter(
    prefix="/v1",
    tags=["health"]
)
@router.get(
    "/health",
    response_model=HealthResponseV1
)
def health_check()->HealthResponseV1:
    return HealthResponseV1(
        status="healthy",
        service="spotify-ai-memory-api",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
        checks={
            "api":"healthy"
        }
    )