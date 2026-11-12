import asyncio
import threading
import time
import uuid
from uuid import uuid4
from datetime import datetime,timezone
import httpx2
from dotenv import load_dotenv
#from google import genai
from backend_memory_pipeline.agent.gemini_mcp_agent import GeminiMCPAgent
from backend_memory_pipeline.api.dependencies import (
    create_access_token,
    get_memory_write_orchestrator,
    get_memory_control_orchestrator,
    get_memory_query_orchestrator,
)
from backend_memory_pipeline.mcp.server import create_mcp_server
from backend_memory_pipeline.policy_consent.policy_consent import (
    ConsentControlRequestV1,
    MemoryControlAction,
)
import uvicorn
#from backend_memory_pipeline.mcp.auth import create_access_token
from backend_memory_pipeline.persistence.postgres.memory_repository import PostgreSQLMemoryStore
from backend_memory_pipeline.persistence.neo4j.graph_store import Neo4jGraphStore
from backend_memory_pipeline.persistence.qdrant.embedding_store import QdrantEmbeddingStore

load_dotenv()

SUBJECT_ID=f"gemini-five-tools-{uuid4().hex}"
SESSION_ID=f"five-tools-session-{uuid4().hex}"
SURFACE="chat"
LOCALE="en-US"
MCP_HOST="127.0.0.1"
MCP_PORT=8001
MCP_URL=f"http://{MCP_HOST}:{MCP_PORT}/mcp"

def now()->datetime:
    return datetime.now(timezone.utc)

def opt_in_subject()->None:
    orchestrator=get_memory_control_orchestrator()
    result=orchestrator.apply_consent_control(
        ConsentControlRequestV1(
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            action=MemoryControlAction.OPT_IN,
            timestamp=now(),
            correlation_id=f"five-tools-consent-{uuid.uuid4().hex}",
            metadata={
                "source":"gemini_mcp_agent_five_tools_test"
            },
        )
    )
    print(
        "Consent state:",
        result.consent_state.current_state.value,
        flush=True,
    )

def start_mcp_server():
    query_orchestrator=get_memory_query_orchestrator()
    write_orchestrator=get_memory_write_orchestrator()
    control_orchestrator=get_memory_control_orchestrator()
    server=create_mcp_server(
        query_orchestrator=query_orchestrator,
        write_orchestrator=write_orchestrator,
        control_orchestrator=control_orchestrator,
    )
    app=server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=False,
        host=MCP_HOST,
    )
    import uvicorn
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

'''
def wait_for_mcp_server():
    for _ in range(30):
        try:
            response=httpx2.get(
                f"http://{MCP_HOST}:{MCP_PORT}/mcp",
                timeout=2,
            )
            if response.status_code in {200,202,400,401,405}:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("MCP server did not start.")
'''    

def main():
    print(f"TEST SUBJECT: {SUBJECT_ID}")
    print(f"TEST SESSION: {SESSION_ID}")
    print("="*80)
    #opt_in_subject()
    uvicorn_server,mcp_thread=start_mcp_server()
    '''
    mcp_thread=threading.Thread(
        target=start_mcp_server,
        daemon=True,
    )
    mcp_thread.start()
    wait_for_mcp_server()
    '''
    print("MCP SERVER: READY")
    print("="*80)
    agent=GeminiMCPAgent(
        mcp_url=MCP_URL,
        model="gemini-3.5-flash-lite",
    )
    access_token=create_access_token(
        subject_id=SUBJECT_ID,
        username=f"{SUBJECT_ID}-user",
        expires_in_seconds=3600,
    )
    async def run_tests():
        opt_in_subject()
        print("\nTEST 1: ADD EXPLICIT PREFERENCE")
        print("-"*80)
        add_result=await agent.chat(
            query="Remember that I prefer classical music.",
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            requested_at=now(),
            session_id=SESSION_ID,
        )
        print("RESPONSE:")
        print(add_result.response_text)
        print("MEMORY RESULT:")
        print(add_result.memory_result)
        assert add_result.response_text
        assert add_result.memory_result is not None
        print("ADD EXPLICIT PREFERENCE: PASSED")
        print("\nTEST 2: SEARCH MEMORY")
        print("-"*80)
        search_result=await agent.chat(
            query="What type of music do I prefer?",
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            session_id=SESSION_ID,
            requested_at=now(),
        )
        print("RESPONSE:")
        print(search_result.response_text)
        print("MEMORY RESULT:")
        print(search_result.memory_result)
        assert search_result.memory_grounded is True
        assert search_result.memory_result is not None
        context_items=search_result.memory_result.get("context_items",[])
        assert context_items
        memory_id=context_items[0]["memory_id"]
        print(f"FOUND MEMORY ID: {memory_id}")
        print("SEARCH MEMORY: PASSED")
        print("\nTEST 3: EXPLAIN MEMORY USE")
        print("-"*80)
        explain_result=await agent.chat(
            query=("Why did you store and use my classical music preference? "
                   "Please explain why that memory was remembered."),
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            requested_at=now(),
            session_id=SESSION_ID,
        )
        print("RESPONSE:")
        print(explain_result.response_text)
        print("MEMORY RESULT:")
        print(explain_result.memory_result)
        assert explain_result.response_text
        assert explain_result.memory_result is not None
        print("EXPLAIN MEMORY USE: PASSED")
        print("\nTEST 4: CORRECT MEMORY")
        print("-"*80)
        correct_result=await agent.chat(
            query=("The classical music preference you remembered about me is no longer correct. Please correct that existing memory. My corrected preference is that I prefer jazz music."),
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            session_id=SESSION_ID,
            requested_at=now(),
        )
        print("RESPONSE:")
        print(correct_result.response_text)
        print("MEMORY RESULT:")
        print(correct_result.memory_result)
        replacement_memory_id=correct_result.memory_result["replacement_memory_id"]
        assert correct_result.response_text
        assert correct_result.memory_result is not None
        print("CORRECT MEMORY: PASSED")
        print("\nTEST 5: SEARCH CORRECTED MEMORY")
        print("-"*80)
        corrected_search=await agent.chat(
            query="What music do I prefer now?",
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            session_id=SESSION_ID,
            requested_at=now(),
        )
        print("RESPONSE:")
        print(corrected_search.response_text)
        print("MEMORY RESULT:")
        print(corrected_search.memory_result)
        assert corrected_search.memory_grounded is True
        assert corrected_search.memory_result is not None
        corrected_items=corrected_search.memory_result.get("context_items",[])
        assert corrected_items
        corrected_fact=corrected_items[0]["normalized_fact"].lower()
        assert "jazz" in corrected_fact
        print("CORRECTED MEMORY SEARCH: PASSED")
        print("\nTEST 6: DELETE MEMORY")
        print("-"*80)
        delete_result=await agent.chat(
            query="Please forget and delete the existing memory that says I prefer jazz music.",
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            requested_at=now(),
            session_id=SESSION_ID,
        )
        print("RESPONSE:")
        print(delete_result.response_text)
        print("MEMORY RESULT:")
        print(delete_result.memory_result)
        assert delete_result.response_text
        assert delete_result.memory_result is not None
        print("DELETE MEMORY: PASSED")
        '''
        print("\nTEST 7: VERIFY MEMORY IS GONE")
        print("-"*80)
        final_search=await agent.chat(
            query="What music preference did I ask you to remember?",
            subject_id=SUBJECT_ID,
            subject_scope=SUBJECT_ID,
            surface=SURFACE,
            locale=LOCALE,
            access_token=access_token,
            requested_at=now(),
            session_id=SESSION_ID,
        )
        print("RESPONSE:")
        print(final_search.response_text)
        print("MEMORY RESULT:")
        print(final_search.memory_result)
        context_items=(
            final_search.memory_result.get("context_items",[])
            if final_search.memory_result
            else []
        )
        jazz_items=[
            item for item in context_items
            if "jazz" in item.get("normalized_fact","").lower()
        ]
        assert not jazz_items
        print("DELETE VERIFICATION: PASSED")
        print("\n"+"="*80)
        print("ALL GEMINI MCP TOOL TESTS PASSED")
        print("="*80)
        '''
        print("\nTEST 7: VERIFY MEMORY IS GONE")
        print("-" * 80)
        # PostgreSQL verification
        postgres_store=PostgreSQLMemoryStore()
        postgres_memory=postgres_store.get(replacement_memory_id)
        postgres_deleted=postgres_memory is None
        print("POSTGRES:", "DELETED" if postgres_deleted else "STILL EXISTS")

        # Neo4j verification
        neo4j_store=Neo4jGraphStore(
          uri="bolt://localhost:7687",
          username="neo4j",
          password="password",
          database="neo4j",
        )
        neo4j_memory=neo4j_store.get_memory(replacement_memory_id)
        neo4j_deleted=neo4j_memory is None
        print("NEO4J:", "DELETED" if neo4j_deleted else "STILL EXISTS")

        # Qdrant verification
        qdrant_store=QdrantEmbeddingStore(
          url="http://localhost:6333",
          collection_name="spotify_memory_embeddings",
          dimensions=384,
        )
        qdrant_memory=qdrant_store.get(replacement_memory_id)
        qdrant_deleted=qdrant_memory is None
        print("QDRANT:", "DELETED" if qdrant_deleted else "STILL EXISTS")

        # Final verification
        if not postgres_deleted:
          raise AssertionError("PostgreSQL deletion verification failed.")
        if not neo4j_deleted:
          raise AssertionError("Neo4j deletion verification failed.")
        if not qdrant_deleted:
          raise AssertionError("Qdrant deletion verification failed.")
        print("=" * 80)
        print("ALL THREE STORES: DELETION VERIFIED")
        print("VERIFY MEMORY IS GONE: PASSED")

    try:    
        asyncio.run(run_tests())
    finally:
        uvicorn_server.should_exit=True
        mcp_thread.join(timeout=10)    

if __name__=="__main__":
    main()