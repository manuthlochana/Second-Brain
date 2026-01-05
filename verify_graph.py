import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "secret-key"

def test_graph():
    print("🚀 Testing Knowledge Graph Engine...")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # 1. Test Get Graph
    try:
        r = requests.get(f"{BASE_URL}/graph/data", headers=headers)
        if r.status_code == 200:
            data = r.json()
            nodes = data.get("nodes", [])
            links = data.get("links", [])
            print(f"✅ Graph Data: {len(nodes)} nodes, {len(links)} edges retrieved.")
            # print(json.dumps(data, indent=2))
        else:
            print(f"❌ Graph Data Failed: {r.status_code} - {r.text}")
            return
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return

    # 2. Test Inference Trigger
    r = requests.post(f"{BASE_URL}/graph/inference", headers=headers)
    if r.status_code == 200:
        print("✅ Inference Triggered successfully.")
    else:
         print(f"❌ Inference Trigger Failed: {r.status_code}")

if __name__ == "__main__":
    test_graph()
