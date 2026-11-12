import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL="http://127.0.0.1:8000"


def main():
    username="livechatuser"
    password="testpassword123"

    print("Registering user...")

    register_response=requests.post(
        f"{BASE_URL}/v1/auth/register",
        json={
            "username":username,
            "password":password
        },
        timeout=30
    )

    print("Register status:",register_response.status_code)

    if register_response.status_code not in (200,409):
        print("Register response:",register_response.text)
        return

    print("Logging in...")

    login_response=requests.post(
        f"{BASE_URL}/v1/auth/login",
        json={
            "username":username,
            "password":password
        },
        timeout=30
    )

    print("Login status:",login_response.status_code)

    if login_response.status_code!=200:
        print("Login response:",login_response.text)
        return

    login_body=login_response.json()

    access_token=login_body["access_token"]
    subject_id=login_body["subject_id"]

    print("Authenticated subject:",subject_id)

    print("\nSending chat request...")

    chat_response=requests.post(
        f"{BASE_URL}/v1/chat",
        headers={
            "Authorization":f"Bearer {access_token}"
        },
        json={
            "query":"What music do I prefer?",
            "surface":"chat",
            "locale":"en-IN",
            "requested_at":"2026-09-13T17:00:00+05:30",
            "max_response_characters":12000,
            "include_memory_references":True,
            "metadata":{
                "source":"live_chat_api_test"
            }
        },
        timeout=300
    )

    print("\n========== CHAT API RESULT ==========")
    print("Status:",chat_response.status_code)
    print("Response:")
    print(chat_response.text)
    print("=====================================")


if __name__=="__main__":
    main()