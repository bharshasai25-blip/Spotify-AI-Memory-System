from functools import lru_cache
from backend_memory_pipeline.api.dependencies import (get_memory_query_orchestrator,
    get_memory_write_orchestrator,get_memory_control_orchestrator,)
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from backend_memory_pipeline.mcp.auth import SpotifyMemoryTokenVerifier
from backend_memory_pipeline.mcp.schemas import (
    SearchMemoryInput,
    SearchMemoryOutput,
    AddExplicitPreferenceInput,
    AddExplicitPreferenceOutput,
    CorrectMemoryInput,
    CorrectMemoryOutput,
    DeleteMemoryInput,
    DeleteMemoryOutput,
    ExplainMemoryUseInput,
    ExplainMemoryUseOutput,
)
from backend_memory_pipeline.mcp.tools import (
    search_memory,
    add_explicit_preference,
    correct_memory,
    delete_memory,
    explain_memory_use,
)
from backend_memory_pipeline.orchestration.orchestration import (
    MemoryWriteOrchestrator,
    MemoryQueryOrchestrator,
    MemoryControlOrchestrator,
)
def create_mcp_server(
    query_orchestrator:MemoryQueryOrchestrator,
    write_orchestrator:MemoryWriteOrchestrator,
    control_orchestrator:MemoryControlOrchestrator,
)->MCPServer:
    server=MCPServer(
        name="spotify-ai-memory",
        description="Authenticated MCP interface for the Spotify AI Memory System.",
        instructions="Use the memory tools only for authenticated, subject-scoped memory operations.",
        token_verifier=SpotifyMemoryTokenVerifier(),
        auth=AuthSettings(
            issuer_url="http://localhost:8000",
            resource_server_url="http://localhost:8000",
            required_scopes=["memory"],
        ),
    )
    @server.tool(
        name="search_memory",
        description="Search the authenticated user's governed memories using the current intent.",
        structured_output=True,
    )
    async def search_memory_tool(
        request:SearchMemoryInput,
    )->SearchMemoryOutput:
        return search_memory(
            request=request,
            orchestrator=query_orchestrator,
        )
    @server.tool(
        name="add_explicit_preference",
        description="Store an explicit preference stated by the authenticated user.",
        structured_output=True,
    )
    async def add_explicit_preference_tool(
        request:AddExplicitPreferenceInput,
    )->AddExplicitPreferenceOutput:
        return add_explicit_preference(
            request=request,
            orchestrator=write_orchestrator,
        )
    @server.tool(
        name="correct_memory",
        description="Correct an existing memory owned by the authenticated user.",
        structured_output=True,
    )
    async def correct_memory_tool(
        request:CorrectMemoryInput,
    )->CorrectMemoryOutput:
        return correct_memory(
            request=request,
            orchestrator=control_orchestrator,
        )
    @server.tool(
        name="delete_memory",
        description="Delete an existing memory owned by the authenticated user.",
        structured_output=True,
    )
    async def delete_memory_tool(
        request:DeleteMemoryInput,
    )->DeleteMemoryOutput:
        return delete_memory(
            request=request,
            orchestrator=control_orchestrator,
        )
    @server.tool(
        name="explain_memory_use",
        description="Explain why a memory owned by the authenticated user was used.",
        structured_output=True,
    )
    async def explain_memory_use_tool(
        request:ExplainMemoryUseInput,
    )->ExplainMemoryUseOutput:
        return explain_memory_use(
            request=request,
            orchestrator=query_orchestrator,
        )
    return server

@lru_cache(maxsize=1)
def get_mcp_server()->MCPServer:
    return create_mcp_server(
        query_orchestrator=get_memory_query_orchestrator(),
        write_orchestrator=get_memory_write_orchestrator(),
        control_orchestrator=get_memory_control_orchestrator(),
    )