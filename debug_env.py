from dotenv import load_dotenv
import os

print(f"CWD: {os.getcwd()}")
loaded = load_dotenv()
print(f"Loading .env result: {loaded}")
print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
print(f"NEO4J_URI: {os.getenv('NEO4J_URI')}")
