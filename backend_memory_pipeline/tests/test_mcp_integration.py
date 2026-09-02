
import os
import json
import threading
import time
import asyncio
from datetime import datetime,timezone
import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
os.environ.setdefault("API_AUTH_SECRET","test-secret-for-mcp-integration-1234567890")
from backend_memory_pipeline.api.dependencies import (
    create_access_token,
    get_memory_query_orchestrator,
    get_memory_write_orchestrator,
    get_memory_control_orchestrator,
)
from backend_memory_pipeline.mcp.server import create_mcp_server
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    MemoryControlAction,
)
MCP_HOST="127.0.0.1"
MCP_PORT=8001
MCP_URL=f"http://{MCP_HOST}:{MCP_PORT}/mcp"
def _now()->datetime:
    return datetime.now(timezone.utc)
def _create_authenticated_client(token:str)->httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"Authorization":f"Bearer {token}"}
    )
def _call_result(result):
    if getattr(result,"isError",False):
        raise AssertionError(f"MCP tool call failed: {result}")
    return result
def _structured_content(result):
    structured=getattr(result,"structuredContent",None)
    if isinstance(structured,dict):
        return structured
    if isinstance(structured,str):
        try:
            return json.loads(structured)
        except json.JSONDecodeError:
            return structured
    content=getattr(result,"content",None)
    if content:
        for item in content:
            data=getattr(item,"data",None)
            if isinstance(data,dict):
                return data
            text=getattr(item,"text",None)
            if text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
    return None
def _create_token(subject_id:str)->str:
    return create_access_token(
        subject_id=subject_id,
        username=f"{subject_id}-user",
        expires_in_seconds=3600,
    )
def _opt_in_subject(subject_id:str)->str:
    orchestrator=get_memory_control_orchestrator()
    token=_create_token(subject_id)
    result=orchestrator.apply_consent_control(
        ConsentControlRequestV1(
            subject_id=subject_id,
            subject_scope=subject_id,
            action=MemoryControlAction.OPT_IN,
            timestamp=_now(),
            correlation_id=f"integration-{subject_id}",
            metadata={"source":"mcp_integration_test"},
        )
    )
    assert result.consent_state is not None
    assert result.consent_state.current_state.value=="opted_in"
    return token
def _start_mcp_server():
    server=create_mcp_server(
        query_orchestrator=get_memory_query_orchestrator(),
        write_orchestrator=get_memory_write_orchestrator(),
        control_orchestrator=get_memory_control_orchestrator(),
    )
    app=server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=False,
        host=MCP_HOST,
    )
    config=uvicorn.Config(
        app,
        host=MCP_HOST,
        port=MCP_PORT,
        log_level="error",
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
    raise RuntimeError(
        "MCP test server failed to start within 60 seconds."
    )
@pytest.fixture(scope="module")
def mcp_server():
    uvicorn_server,thread=_start_mcp_server()
    yield uvicorn_server
    uvicorn_server.should_exit=True
    thread.join(timeout=10)
'''    
@pytest.fixture(scope="module")
def reset_memory_state():
    write_orchestrator=get_memory_write_orchestrator()
    query_orchestrator=get_memory_query_orchestrator()
    write_orchestrator.policy_consent._consent_states.clear()
    write_orchestrator.evidence_history._events.clear()
    write_orchestrator.lifecycle.memory_store._memories.clear()
    query_orchestrator.retrieval.store.graph_store._memories.clear()
    query_orchestrator.retrieval.store.embedding_store._embeddings.clear()
    yield
'''    
def test_mcp_tool_discovery(mcp_server):
    async def run():
        token=_create_token("mcp-discovery-user")
        async with _create_authenticated_client(token) as client:
            async with streamable_http_client(
                MCP_URL,
                http_client=client,
            ) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result=await session.list_tools()
                    tool_names={tool.name for tool in result.tools}
                    expected={
                        "search_memory",
                        "add_explicit_preference",
                        "correct_memory",
                        "delete_memory",
                        "explain_memory_use",
                    }
                    assert expected.issubset(tool_names)
                    assert len(tool_names)==5
    asyncio.run(run())
def test_mcp_memory_lifecycle(mcp_server):
    async def run():
        subject_id="mcp-e2e-user"
        token=_opt_in_subject(subject_id)
        async with _create_authenticated_client(token) as client:
            async with streamable_http_client(
                MCP_URL,
                http_client=client,
            ) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    add_result=await session.call_tool(
                        "add_explicit_preference",
                        {"request":{
                            "preference":"I love alternative rock music.",
                            "session_id":"mcp-session-1",
                            "surface":"chat",
                            "locale":"en-US",
                            "effective_at":_now().isoformat(),
                            "metadata":{"test":"mcp_lifecycle"},
                        }},
                    )
                    add_result=_call_result(add_result)
                    add_output=_structured_content(add_result)
                    assert add_output is not None
                    assert add_output["accepted"] is True
                    assert len(add_output["memory_ids"])>=1
                    memory_id=add_output["memory_ids"][0]
                    search_result=await session.call_tool(
                        "search_memory",
                        {"request":{
                            "query":"What kind of music do I love?",
                            "surface":"chat",
                            "locale":"en-US",
                            "requested_at":_now().isoformat(),
                            "max_items":10,
                            "max_characters":10000,
                        }},
                    )
                    search_result=_call_result(search_result)
                    search_output=_structured_content(search_result)
                    assert search_output is not None
                    assert search_output["memory_grounded"] is True
                    assert any(
                        item["memory_id"]==memory_id
                        for item in search_output["context_items"]
                    )
                    explain_result=await session.call_tool(
                        "explain_memory_use",
                        {"request":{
                            "memory_id":memory_id,
                            "current_intent":"What kind of music do I love?",
                            "surface":"chat",
                            "locale":"en-US",
                        }},
                    )
                    explain_result=_call_result(explain_result)
                    explain_output=_structured_content(explain_result)
                    assert explain_output is not None
                    assert explain_output["memory_id"]==memory_id
                    assert explain_output["subject_id"]==subject_id
                    assert explain_output["source"]=="mcp"
                    correction_result=await session.call_tool(
                        "correct_memory",
                        {"request":{
                            "memory_id":memory_id,
                            "corrected_statement":"I actually prefer jazz music.",
                            "session_id":"mcp-session-2",
                            "reason":"The previous preference was incorrect.",
                            "surface":"chat",
                            "locale":"en-US",
                            "effective_at":_now().isoformat(),
                            "metadata":{"test":"mcp_correction"},
                        }},
                    )
                    correction_result=_call_result(correction_result)
                    correction_output=_structured_content(correction_result)
                    assert correction_output is not None
                    assert correction_output["corrected"] is True
                    assert correction_output["target_memory_id"]==memory_id
                    replacement_memory_id=correction_output["replacement_memory_id"]
                    assert replacement_memory_id
                    assert replacement_memory_id!=memory_id
                    search_after_correction=await session.call_tool(
                        "search_memory",
                        {"request":{
                            "query":"What kind of music do I prefer?",
                            "surface":"chat",
                            "locale":"en-US",
                            "requested_at":_now().isoformat(),
                            "max_items":10,
                            "max_characters":10000,
                        }},
                    )
                    search_after_correction=_call_result(
                        search_after_correction
                    )
                    search_after_correction_output=_structured_content(
                        search_after_correction
                    )
                    assert search_after_correction_output is not None
                    normalized_facts=[
                        item["normalized_fact"].lower()
                        for item in search_after_correction_output["context_items"]
                    ]
                    assert any(
                        "jazz" in fact
                        for fact in normalized_facts
                    )
                    delete_result=await session.call_tool(
                        "delete_memory",
                        {"request":{
                            "memory_id":replacement_memory_id,
                            "reason":"User requested deletion during MCP integration test.",
                            "effective_at":_now().isoformat(),
                            "metadata":{"test":"mcp_deletion"},
                        }},
                    )
                    delete_result=_call_result(delete_result)
                    delete_output=_structured_content(delete_result)
                    assert delete_output is not None
                    assert delete_output["deleted"] is True
                    assert delete_output["memory_id"]==replacement_memory_id
                    search_after_delete=await session.call_tool(
                        "search_memory",
                        {"request":{
                            "query":"What music do I prefer?",
                            "surface":"chat",
                            "locale":"en-US",
                            "requested_at":_now().isoformat(),
                            "max_items":10,
                            "max_characters":10000,
                        }},
                    )
                    search_after_delete=_call_result(
                        search_after_delete
                    )
                    search_after_delete_output=_structured_content(
                        search_after_delete
                    )
                    assert search_after_delete_output is not None
                    assert all(
                        item["memory_id"]!=replacement_memory_id
                        for item in search_after_delete_output["context_items"]
                    )
    asyncio.run(run())
def test_mcp_cross_subject_isolation(mcp_server):
    async def run():
        subject_a="mcp-subject-a"
        subject_b="mcp-subject-b"
        token_a=_opt_in_subject(subject_a)
        token_b=_opt_in_subject(subject_b)
        async with _create_authenticated_client(token_a) as client_a:
            async with streamable_http_client(
                MCP_URL,
                http_client=client_a,
            ) as streams_a:
                async with ClientSession(*streams_a) as session_a:
                    await session_a.initialize()
                    add_result=await session_a.call_tool(
                        "add_explicit_preference",
                        {"request":{
                            "preference":"I love progressive metal.",
                            "session_id":"subject-a-session",
                            "surface":"chat",
                            "locale":"en-US",
                            "effective_at":_now().isoformat(),
                            "metadata":{"test":"cross_subject"},
                        }},
                    )
                    add_result=_call_result(add_result)
                    add_output=_structured_content(add_result)
                    assert add_output is not None
                    assert add_output["accepted"] is True
                    async with _create_authenticated_client(token_b) as client_b:
                        async with streamable_http_client(
                            MCP_URL,
                            http_client=client_b,
                        ) as streams_b:
                            async with ClientSession(*streams_b) as session_b:
                                await session_b.initialize()
                                search_result=await session_b.call_tool(
                                    "search_memory",
                                    {"request":{
                                        "query":"What kind of music does the user love?",
                                        "surface":"chat",
                                        "locale":"en-US",
                                        "requested_at":_now().isoformat(),
                                        "max_items":10,
                                        "max_characters":10000,
                                    }},
                                )
                                search_result=_call_result(search_result)
                                search_output=_structured_content(search_result)
                                assert search_output is not None
                                assert search_output["memory_grounded"] is False
                                assert search_output["context_items"]==[]
    asyncio.run(run())
def test_mcp_rejects_invalid_token(mcp_server):
    async def run():
        invalid_token="this-is-not-a-valid-jwt"
        async with _create_authenticated_client(invalid_token) as client:
            async with streamable_http_client(
                MCP_URL,
                http_client=client,
            ) as streams:
                async with ClientSession(*streams) as session:
                    with pytest.raises(Exception):
                        await session.initialize()
    asyncio.run(run())


'''                    
@pytest.mark.anyio
async def test_real_mcp_revoked_token_is_rejected():
    from backend_memory_pipeline.api.dependencies import (
        revoke_token,
        is_token_revoked,
        decode_access_token,
    )
    subject_id="mcp-revoked-user"
    token=create_access_token(
        subject_id=subject_id,
        username=f"{subject_id}@example.com",
    )
    authenticated_subject=decode_access_token(token)
    revoke_token(authenticated_subject.token_id)
    assert is_token_revoked(authenticated_subject.token_id) is True
    client=httpx2.AsyncClient(
        headers={
            "Authorization":f"Bearer {token}",
        }
    )
    async with client:
        with pytest.raises(Exception):
            async with streamable_http_client(
                MCP_URL,
                http_client=client,
            ) as (read_stream,write_stream):
                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:
                    await session.initialize()
''' 
'''    
@pytest.mark.anyio
async def test_debug_mcp_preference_result_shape():
    subject_id="mcp-debug-user"
    token=await _opt_in_subject(subject_id)
    client=_create_authenticated_client(token)
    async with client:
        async with streamable_http_client(
            MCP_URL,
            http_client=client,
        ) as (read_stream,write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:
                await session.initialize()
                result=await session.call_tool(
                    "add_explicit_preference",
                    {"request":{
                        "preference":"I prefer jazz music.",
                        "session_id":"mcp-debug-session",
                        "surface":"chat",
                        "locale":"en-US",
                        "effective_at":_now().isoformat()}})
                print("\nRESULT TYPE:",type(result))
                print("RESULT:",repr(result))
                print("STRUCTURED CONTENT TYPE:",type(getattr(result,"structuredContent",None)))
                print("STRUCTURED CONTENT:",repr(getattr(result,"structuredContent",None)))
                print("CONTENT TYPE:",type(getattr(result,"content",None)))
                print("CONTENT:",repr(getattr(result,"content",None)))
                assert not getattr(result,"isError",False) 
'''                              