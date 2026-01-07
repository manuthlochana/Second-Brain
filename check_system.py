
import os
import sys
import time
import requests
import psycopg2
from dotenv import load_dotenv

# Load env from the project root
load_dotenv()

def check_env_vars():
    print("\n🔍 Checking Environment Variables...")
    required_vars = ["DATABASE_URL", "SUPABASE_URL", "GOOGLE_API_KEY", "TELEGRAM_BOT_TOKEN"]
    missing = []
    for var in required_vars:
        val = os.getenv(var)
        if not val:
            missing.append(var)
        else:
            masked = val[:4] + "..." + val[-4:] if len(val) > 10 else "****"
            print(f"   ✅ {var} is set ({masked})")
    
    if missing:
        print(f"   ❌ Missing variables: {missing}")
        return False
    return True

def check_database():
    print("\n🔍 Checking Database Connection...")
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("   ❌ DATABASE_URL not found.")
        return False
        
    try:
        conn = psycopg2.connect(dsn)
        print("   ✅ Connection to Supabase PostgreSQL successful.")
        
        # Optional: Check table existence
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
        tables = [row[0] for row in cur.fetchall()]
        print(f"   📊 Tables found: {tables}")
        
        required_tables = ['entities', 'notes', 'tasks', 'user_profiles']
        missing_tables = [t for t in required_tables if t not in tables]
        
        if missing_tables:
            print(f"   ⚠️  Missing core tables: {missing_tables} (Migrations might be needed)")
        else:
            print("   ✅ Core tables present.")
            
        conn.close()
        return True
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
        return False

def check_backend():
    print("\n🔍 Checking Backend API...")
    try:
        response = requests.get("http://localhost:8000/docs", timeout=5)
        if response.status_code == 200:
            print("   ✅ Backend API is reachable (http://localhost:8000/docs).")
            return True
        else:
            print(f"   ⚠️  Backend returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("   ❌ Could not connect to Backend API (Is it running?).")
        return False

def check_frontend():
    print("\n🔍 Checking Frontend Dashboard...")
    try:
        response = requests.get("http://localhost:3000", timeout=5)
        if response.status_code == 200:
            print("   ✅ Frontend Dashboard is reachable (http://localhost:3000).")
            return True
        else:
            print(f"   ⚠️  Frontend returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        try:
             # Try port 3001 just in case
            response = requests.get("http://localhost:3001", timeout=5)
            if response.status_code == 200:
                print("   ✅ Frontend Dashboard is reachable (http://localhost:3001).")
                return True
        except:
            pass
        print("   ❌ Could not connect to Frontend Dashboard (Is it running?).")
        return False

def main():
    print("🚀 Starting System Verification...")
    
    env_ok = check_env_vars()
    db_ok = check_database()
    backend_ok = check_backend()
    frontend_ok = check_frontend()
    
    print("\n📊 Verification Summary")
    print("-" * 30)
    print(f"Environment: {'✅ OK' if env_ok else '❌ FAIL'}")
    print(f"Database:    {'✅ OK' if db_ok else '❌ FAIL'}")
    print(f"Backend:     {'✅ OK' if backend_ok else '❌ FAIL'}")
    print(f"Frontend:    {'✅ OK' if frontend_ok else '❌ FAIL'}")
    print("-" * 30)
    
    if env_ok and db_ok and backend_ok and frontend_ok:
        print("🎉 System appears to be fully functional!")
    else:
        print("⚠️  System has issues. Please review the logs above.")

if __name__ == "__main__":
    main()
