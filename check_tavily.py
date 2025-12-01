import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("TAVILY_API_KEY")
if key:
    print(f"✅ TAVILY_API_KEY found: {key[:5]}...")
else:
    print("❌ TAVILY_API_KEY not found.")
