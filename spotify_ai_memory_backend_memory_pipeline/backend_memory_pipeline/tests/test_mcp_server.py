import pytest
from unittest.mock import Mock
from backend_memory_pipeline.mcp.server import create_mcp_server
from backend_memory_pipeline.mcp.auth import SpotifyMemoryTokenVerifier
from backend_memory_pipeline.orchestration.orchestration import (MemoryQueryOrchestrator,MemoryWriteOrchestrator,MemoryControlOrchestrator)
from backend_memory_pipeline.mcp.server import (create_mcp_server,get_mcp_server)

@pytest.fixture
def query_orchestrator():
    return Mock(spec=MemoryQueryOrchestrator)
@pytest.fixture
def write_orchestrator():
    return Mock(spec=MemoryWriteOrchestrator)
@pytest.fixture
def control_orchestrator():
    return Mock(spec=MemoryControlOrchestrator)
@pytest.fixture
def mcp_server(query_orchestrator,write_orchestrator,control_orchestrator):
    return create_mcp_server(
        query_orchestrator=query_orchestrator,
        write_orchestrator=write_orchestrator,
        control_orchestrator=control_orchestrator,
    )
@pytest.mark.anyio
async def test_mcp_server_can_be_created(mcp_server):
    assert mcp_server is not None
@pytest.mark.anyio
async def test_mcp_server_has_correct_name(mcp_server):
    assert mcp_server.name=="spotify-ai-memory"
@pytest.mark.anyio
async def test_mcp_server_has_description(mcp_server):
    assert mcp_server.description=="Authenticated MCP interface for the Spotify AI Memory System."
@pytest.mark.anyio
async def test_mcp_server_has_instructions(mcp_server):
    assert mcp_server.instructions=="Use the memory tools only for authenticated, subject-scoped memory operations."
@pytest.mark.anyio
async def test_mcp_server_uses_spotify_memory_token_verifier(mcp_server):
    assert isinstance(mcp_server._token_verifier,SpotifyMemoryTokenVerifier)
@pytest.mark.anyio
async def test_mcp_server_has_auth_settings(mcp_server):
    assert mcp_server.settings.auth is not None
    assert str(mcp_server.settings.auth.issuer_url)=="http://localhost:8000"
    assert str(mcp_server.settings.auth.resource_server_url)=="http://localhost:8000"
    assert mcp_server.settings.auth.required_scopes==["memory"]
@pytest.mark.anyio
async def test_exactly_five_mcp_tools_are_registered(mcp_server):
    tools=await mcp_server.list_tools()
    tool_names={tool.name for tool in tools}
    assert tool_names=={
        "search_memory",
        "add_explicit_preference",
        "correct_memory",
        "delete_memory",
        "explain_memory_use",
    }
    assert len(tools)==5
@pytest.mark.anyio
async def test_search_memory_tool_is_registered(mcp_server):
    tools=await mcp_server.list_tools()
    tool=next(tool for tool in tools if tool.name=="search_memory")
    assert tool.name=="search_memory"
    assert tool.description=="Search the authenticated user's governed memories using the current intent."
    assert tool.input_schema["type"]=="object"
    assert "request" in tool.input_schema["properties"]
@pytest.mark.anyio
async def test_add_explicit_preference_tool_is_registered(mcp_server):
    tools=await mcp_server.list_tools()
    tool=next(tool for tool in tools if tool.name=="add_explicit_preference")
    assert tool.name=="add_explicit_preference"
    assert tool.description=="Store an explicit preference stated by the authenticated user."
    assert tool.input_schema["type"]=="object"
    assert "request" in tool.input_schema["properties"]
@pytest.mark.anyio
async def test_correct_memory_tool_is_registered(mcp_server):
    tools=await mcp_server.list_tools()
    tool=next(tool for tool in tools if tool.name=="correct_memory")
    assert tool.name=="correct_memory"
    assert tool.description=="Correct an existing memory owned by the authenticated user."
    assert tool.input_schema["type"]=="object"
    assert "request" in tool.input_schema["properties"]
@pytest.mark.anyio
async def test_delete_memory_tool_is_registered(mcp_server):
    tools=await mcp_server.list_tools()
    tool=next(tool for tool in tools if tool.name=="delete_memory")
    assert tool.name=="delete_memory"
    assert tool.description=="Delete an existing memory owned by the authenticated user."
    assert tool.input_schema["type"]=="object"
    assert "request" in tool.input_schema["properties"]
@pytest.mark.anyio
async def test_explain_memory_use_tool_is_registered(mcp_server):
    tools=await mcp_server.list_tools()
    tool=next(tool for tool in tools if tool.name=="explain_memory_use")
    assert tool.name=="explain_memory_use"
    assert tool.description=="Explain why a memory owned by the authenticated user was used."
    assert tool.input_schema["type"]=="object"
    assert "request" in tool.input_schema["properties"]
@pytest.mark.anyio
async def test_mcp_tools_have_unique_names(mcp_server):
    tools=await mcp_server.list_tools()
    names=[tool.name for tool in tools]
    assert len(names)==len(set(names))
def test_create_mcp_server_requires_query_orchestrator():
    with pytest.raises(TypeError):
        create_mcp_server(
            write_orchestrator=Mock(spec=MemoryWriteOrchestrator),
            control_orchestrator=Mock(spec=MemoryControlOrchestrator),
        )
def test_create_mcp_server_requires_write_orchestrator():
    with pytest.raises(TypeError):
        create_mcp_server(
            query_orchestrator=Mock(spec=MemoryQueryOrchestrator),
            control_orchestrator=Mock(spec=MemoryControlOrchestrator),
        )
def test_create_mcp_server_requires_control_orchestrator():
    with pytest.raises(TypeError):
        create_mcp_server(
            query_orchestrator=Mock(spec=MemoryQueryOrchestrator),
            write_orchestrator=Mock(spec=MemoryWriteOrchestrator),
        )
def test_get_mcp_server_returns_server():
    server=get_mcp_server()
    assert server is not None
    assert server.name=="spotify-ai-memory"
    
def test_get_mcp_server_is_cached():
    first=get_mcp_server()
    second=get_mcp_server()
    assert first is second        