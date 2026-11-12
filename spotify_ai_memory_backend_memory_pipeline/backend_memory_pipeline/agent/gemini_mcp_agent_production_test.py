import asyncio
import threading
import time
import uuid
from datetime import datetime,timezone
import httpx2
from dotenv import load_dotenv
from backend_memory_pipeline.agent.gemini_mcp_agent import GeminiMCPAgent
from backend_memory_pipeline.api.dependencies import (
    create_access_token,
    get_memory_control_orchestrator,
    get_memory_write_orchestrator,
    get_memory_query_orchestrator,
)
from backend_memory_pipeline.mcp.server import create_mcp_server
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    MemoryControlAction,
)
import uvicorn
load_dotenv()
MCP_HOST="127.0.0.1"
MCP_PORT=8001
MCP_URL=f"http://{MCP_HOST}:{MCP_PORT}/mcp"
SUBJECT_ID=f"gemini-production-agent-{uuid.uuid4().hex}"
def now()->datetime:
    return datetime.now(timezone.utc)
def create_token()->str:
    return create_access_token(
        subject_id=SUBJECT_ID,
        username=f"{SUBJECT_ID}-user",
        expires_in_seconds=3600,
    )
def opt_in_subject()->None:
    orchestrator=get_memory_control_orchestrator()
    result=orchestrator.apply_consent_control(
        ConsentControlRequestV1(
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            action=MemoryControlAction.OPT_IN,
            timestamp=now(),
            correlation_id=f"production-agent-consent-{uuid.uuid4().hex}",
            metadata={
                "source":"gemini_mcp_agent_production_test"
            },
        )
    )
    print(
        "Consent state:",
        result.consent_state.current_state.value,
        flush=True,
    )
def seed_memory()->str:
    orchestrator=get_memory_write_orchestrator()
    result=orchestrator.add_explicit_preference(
        subject_id=SUBJECT_ID,
        subject_scope=SUBJECT_ID,
        session_id=f"production-agent-session-{uuid.uuid4().hex}",
        preference="I love jazz music.",
        surface="chat",
        locale="en-US",
        effective_at=now(),
        correlation_id=f"production-agent-seed-{uuid.uuid4().hex}",
        metadata={
            "source":"gemini_mcp_agent_production_test"
        },
    )
    memory_ids=[
        lifecycle_result.created_memory_id
        or lifecycle_result.memory_id
        for lifecycle_result in result.lifecycle_results
        if lifecycle_result.created_memory_id
        or lifecycle_result.memory_id
    ]
    if not memory_ids:
        raise RuntimeError("Failed to seed memory.")
    print(
        "Seeded memory:",
        memory_ids[0],
        flush=True,
    )
    return memory_ids[0]
def start_mcp_server():
    server=create_mcp_server(
        query_orchestrator=get_memory_query_orchestrator(),
        write_orchestrator=get_memory_write_orchestrator(),
        control_orchestrator=get_memory_control_orchestrator(),
    )
    app=server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=False,
        host=MCP_HOST,
    )
    config=uvicorn.Config(
        app,
        host=MCP_HOST,
        port=MCP_PORT,
        log_level="warning",
    )
    uvicorn_server=uvicorn.Server(config)
    thread=threading.Thread(
        target=uvicorn_server.run,
        daemon=True,
    )
    thread.start()
    deadline=time.time()+60
    while time.time()<deadline:
        if uvicorn_server.started:
            return uvicorn_server,thread
        time.sleep(0.1)
    raise RuntimeError("MCP server failed to start.")
async def run_test()->None:
    opt_in_subject()
    memory_id=seed_memory()
    print(
        "Memory created for production-agent test:",
        memory_id,
        flush=True,
    )
    uvicorn_server,thread=start_mcp_server()
    token=create_token()
    agent=GeminiMCPAgent(
        mcp_url=MCP_URL,
        model="gemini-3.5-flash-lite",
    )
    try:
        result=await agent.chat(
            query=(
                "What kind of music do I love? "
                "Use my saved memory if relevant."
            ),
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface="chat",
            locale="en-US",
            access_token=token,
            requested_at=now(),
            max_response_characters=12000,
        )
        print(
            "\nAGENT RESPONSE:",
            flush=True,
        )
        print(
            result.response_text,
            flush=True,
        )
        print(
            "\nMEMORY GROUNDED:",
            result.memory_grounded,
            flush=True,
        )
        print(
            "\nMEMORY RESULT:",
            result.memory_result,
            flush=True,
        )
        if not result.response_text:
            raise RuntimeError(
                "Production Gemini MCP agent returned an empty response."
            )
        if not result.memory_grounded:
            raise RuntimeError(
                "Production Gemini MCP agent did not use memory."
            )
        if not result.memory_result:
            raise RuntimeError(
                "Production Gemini MCP agent did not receive an MCP result."
            )
    finally:
        uvicorn_server.should_exit=True
        thread.join(timeout=10)
if __name__=="__main__":
    asyncio.run(run_test())