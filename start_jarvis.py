import os
import sys
import time
import subprocess
import signal
import webbrowser
from dotenv import load_dotenv

# Load Env
load_dotenv()
API_KEY = os.getenv("API_KEY")

def log(msg, type="INFO"):
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "RESET": "\033[0m"}
    print(f"{colors.get(type, '')}[{type}] {msg}{colors['RESET']}")

def check_env():
    log("Checking Environment...", "INFO")
    required = ["DATABASE_URL", "GOOGLE_API_KEY", "TELEGRAM_BOT_TOKEN"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        log(f"Missing ENV vars: {missing}", "ERROR")
        sys.exit(1)
    log("Environment OK.", "SUCCESS")

def run_migrations():
    log("Running Database Migrations...", "INFO")
    try:
        # Assumes generic Alembic setup
        subprocess.run(["alembic", "upgrade", "head"], cwd="./backend", check=True)
        log("Migrations Applied.", "SUCCESS")
    except subprocess.CalledProcessError as e:
        log(f"Migration Failed (Non-Fatal): {e}", "ERROR")
        log("⚠️ System will attempt to start, but database features may be unstable.", "INFO")
    except Exception as e:
        log(f"Migration Error: {e}", "ERROR")

def start_processes():
    processes = []
    
    # 1. Backend API
    log("🚀 Launching Backend API (FastAPI)...", "INFO")
    api = subprocess.Popen(["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"], cwd="./backend")
    processes.append(api)
    
    # 2. Scheduler
    log("⏳ Launching Executive Scheduler...", "INFO")
    sched = subprocess.Popen([sys.executable, "scheduler.py"], cwd="./backend")
    processes.append(sched)
    
    # 3. Telegram Bot
    log("🤖 Launching Telegram Bot...", "INFO")
    bot = subprocess.Popen([sys.executable, "telegram_bot.py"], cwd="./backend")
    processes.append(bot)
    
    # 4. Frontend
    log("💻 Launching Next.js Dashboard...", "INFO")
    fe = subprocess.Popen(["npm", "run", "dev"], cwd="./frontend")
    processes.append(fe)
    
    return processes

def cleanup(signum, frame):
    log("\n🛑 Shutting down Jarvis...", "INFO")
    for p in PROCS:
        p.terminate()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    print(r"""
       __   ___  ____ _    _  _____  
      |  | / _ \|    \ |  | |/ ____| 
      |  |/ /_\ \    / |  | (  (___  
  /\__|  /  _  \    \ \/  / \___  \ 
  \______/_/   \_\____\_/  |_____/  
   
    CEO Brain - Autonomous System v1.0
    """)
    
    check_env()
    run_migrations()
    
    PROCS = start_processes()
    
    time.sleep(5) # Heat up
    log("✅ SYSTEM LIVE. Access Dashboard at http://localhost:3000", "SUCCESS")
    webbrowser.open("http://localhost:3000")
    
    # Keep alive
    while True:
        time.sleep(1)
