from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend_memory_pipeline.api.routes import (
    auth_router,
    health_router,
    events_router,
    chat_router,
    memory_control_router,
    memory_correction_router,
    memory_deletion_router,
    memory_search_router,
    memory_preference_router,
    memory_explaination_router)
from dotenv import load_dotenv
load_dotenv()

app=FastAPI(
    title="Spotify AI Memory API",
    version="1.0.0",
    description="User-facing API for the governed Spotify AI memory system."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(events_router)
app.include_router(chat_router)
app.include_router(memory_control_router)
app.include_router(memory_correction_router)
app.include_router(memory_deletion_router)
app.include_router(memory_search_router)
app.include_router(memory_preference_router)
app.include_router(memory_explaination_router)