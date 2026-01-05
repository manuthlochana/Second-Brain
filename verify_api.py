import requests
import json
import uuid
import sys
import time

# Simple verification script for the FastAPI backend

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "secret-key"

def test_api():
    print("🚀 Testing CEO Brain API...")
    
    # 1. Test Root
    try:
        r = requests.get(f"{BASE_URL}/")
        if r.status_code == 200:
            print("✅ Root Endpoint: OK")
        else:
            print(f"❌ Root Endpoint Failed: {r.status_code}")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API. Is it running?")
        print("   Run: uvicorn backend.main:app --reload")
        return

    # 2. Test Ingest (Web)
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "user_input": "Test input from verification script",
        "source": "verification"
    }
    
    r = requests.post(f"{BASE_URL}/ingest/web", headers=headers, json=payload)
    
    if r.status_code == 202:
        data = r.json()
        print(f"✅ Ingest Accepted. Correlation ID: {data.get('correlation_id')}")
        print("   (Check server logs to see if background task ran)")
    else:
        print(f"❌ Ingest Failed: {r.status_code} - {r.text}")

    # 3. Test Auth Failure
    bad_headers = {"X-API-Key": "wrong-key"}
    r = requests.post(f"{BASE_URL}/ingest/web", headers=bad_headers, json=payload)
    if r.status_code == 403:
         print("✅ Security Check: OK (403 Forbidden received)")
    else:
         print(f"❌ Security Check Failed: Expected 403, got {r.status_code}")

if __name__ == "__main__":
    test_api()
