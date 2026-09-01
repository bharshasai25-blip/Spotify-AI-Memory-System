from fastapi import FastAPI
from backend_memory_pipeline.api.routes import (
    auth_router,
    health_router,
    events_router,
    chat_router,
    memory_control_router,
    memory_correction_router,
    memory_deletion_router,
    memory_search_router
)

app=FastAPI(
    title="Spotify AI Memory API",
    version="1.0.0",
    description="User-facing API for the governed Spotify AI memory system."
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(events_router)
app.include_router(chat_router)
app.include_router(memory_control_router)
app.include_router(memory_correction_router)
app.include_router(memory_deletion_router)
app.include_router(memory_search_router)