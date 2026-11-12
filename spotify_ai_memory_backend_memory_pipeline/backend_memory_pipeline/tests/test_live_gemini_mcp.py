import os
import asyncio
from datetime import datetime,timezone
from backend_memory_pipeline.api.dependencies import create_access_token
from backend_memory_pipeline.agent.gemini_mcp_agent import GeminiMCPAgent
from dotenv import load_dotenv

load_dotenv()


async def main():
    subject_id="TEST_USER_001"
    username="testuser"

    access_token=create_access_token(
        subject_id=subject_id,
        username=username,
        expires_in_seconds=3600
    )

    agent=GeminiMCPAgent(
        mcp_url="http://127.0.0.1:8001/mcp"
    )

    result=await agent.chat(
        query="What music do I prefer?",
        subject_id=subject_id,
        subject_scope=subject_id,
        surface="chat",
        locale="en-IN",
        access_token=access_token,
        requested_at=datetime.now(timezone.utc),
        max_response_characters=12000,
        session_id="test-session-001"
    )

    print("\n========== GEMINI MCP RESULT ==========")
    print("Response:")
    print(result.response_text)
    print("\nMemory grounded:")
    print(result.memory_grounded)
    print("\nMemory result:")
    print(result.memory_result)
    print("\nModel:")
    print(result.model_name)
    print("\nModel version:")
    print(result.model_version)
    print("========================================")


if __name__=="__main__":
    asyncio.run(main())