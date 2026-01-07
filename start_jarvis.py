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
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARNING": "\033[93m", "RESET": "\033[0m"}
    print(f"{colors.get(type, '')}[{type}] {msg}{colors['RESET']}")

def check_env():
    log("Checking Environment...", "INFO")
    required = ["DATABASE_URL", "GOOGLE_API_KEY", "TELEGRAM_BOT_TOKEN"]
    missing = [key for key in required if not os.getenv(key)]
    
    if missing:
        log(f"Missing ENV vars: {missing}", "WARNING")
        log("System will continue but some features may be limited.", "WARNING")
    else:
        log("Environment OK.", "SUCCESS")

def kill_zombie_processes():
    """Kill any processes using ports 8000 or 3000"""
    log("Checking for zombie processes on ports 8000 and 3000...", "INFO")
    
    ports = [8000, 3000]
    for port in ports:
        try:
            # Use lsof to find processes using the port
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        log(f"Killing zombie process {pid} on port {port}", "WARNING")
                        os.kill(int(pid), signal.SIGKILL)
                        time.sleep(0.5)
                    except ProcessLookupError:
                        pass  # Process already dead
                    except Exception as e:
                        log(f"Failed to kill process {pid}: {e}", "ERROR")
        except FileNotFoundError:
            # lsof not available (Windows?), skip
            log("lsof not available, skipping zombie process check", "WARNING")
            break
        except Exception as e:
            log(f"Error checking port {port}: {e}", "WARNING")
    
    log("Zombie process cleanup complete.", "SUCCESS")

def is_port_available(port):
    """Check if a port is available"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

def run_migrations():
    log("Running Database Migrations...", "INFO")
    try:
        # Assumes generic Alembic setup
        subprocess.run(["alembic", "upgrade", "head"], cwd="./backend", check=True, timeout=30)
        log("Migrations Applied.", "SUCCESS")
    except subprocess.TimeoutExpired:
        log("Migration Timeout (Non-Fatal) - Will retry on next start.", "WARNING")
    except subprocess.CalledProcessError as e:
        log(f"Migration Failed (Non-Fatal): {e}", "WARNING")
        log("⚠️ System will attempt to start, but database features may be unstable.", "INFO")
    except FileNotFoundError:
        log("Alembic not found - skipping migrations", "WARNING")
    except Exception as e:
        log(f"Migration Error: {e}", "WARNING")

def start_processes():
    processes = []
    
    # 1. Backend API
    log("🚀 Launching Backend API (FastAPI)...", "INFO")
    try:
        api = subprocess.Popen(
            ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"], 
            cwd="./backend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        processes.append(("Backend API", api))
        time.sleep(2)  # Give it time to start
        
        if api.poll() is not None:
            log("Backend API failed to start!", "ERROR")
            stderr = api.stderr.read().decode() if api.stderr else "No error output"
            log(f"Error: {stderr[:200]}", "ERROR")
            sys.exit(1)
    except FileNotFoundError:
        log("uvicorn not found! Install with: pip install uvicorn", "ERROR")
        sys.exit(1)
    
    # 2. Scheduler
    log("⏳ Launching Executive Scheduler...", "INFO")
    try:
        sched = subprocess.Popen([sys.executable, "scheduler.py"], cwd="./backend")
        processes.append(("Scheduler", sched))
    except FileNotFoundError:
        log("scheduler.py not found - skipping", "WARNING")
    
    # 3. Telegram Bot
    log("🤖 Launching Telegram Bot...", "INFO")
    try:
        bot = subprocess.Popen([sys.executable, "telegram_bot.py"], cwd="./backend")
        processes.append(("Telegram Bot", bot))
    except FileNotFoundError:
        log("telegram_bot.py not found - skipping", "WARNING")
    
    # 4. Frontend
    log("💻 Launching Next.js Dashboard...", "INFO")
    try:
        fe = subprocess.Popen(
            ["npm", "run", "dev"], 
            cwd="./frontend",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        processes.append(("Frontend", fe))
    except FileNotFoundError:
        log("npm not found! Install Node.js first", "ERROR")
        # Don't exit - backend is more critical
    
    return processes

PROCS = []

def cleanup(signum, frame):
    log("\n🛑 Shutting down Jarvis...", "INFO")
    for name, p in PROCS:
        try:
            log(f"Stopping {name}...", "INFO")
            p.terminate()
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            log(f"Force killing {name}...", "WARNING")
            p.kill()
        except Exception as e:
            log(f"Error stopping {name}: {e}", "WARNING")
    
    log("Shutdown complete.", "SUCCESS")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    print(r"""
       __   ___  ____  _    _  _____  
      |  | / _ \|    \ |  | |/ ____| 
      |  |/ /_\ \    / |  | (  (___  
  /\__|  /  _  \    \ \/  / \___  \ 
  \______/_/   \_\____\_/  |_____/  
   
    CEO Brain - Autonomous System v1.0
    """)
    
    # Clean up zombies first
    kill_zombie_processes()
    
    # Verify ports are available
    if not is_port_available(8000):
        log("Port 8000 still in use after cleanup! Manual intervention needed.", "ERROR")
        sys.exit(1)
    
    check_env()
    run_migrations()
    
    PROCS = start_processes()
    
    time.sleep(5)  # Heat up
    log("✅ SYSTEM LIVE. Access Dashboard at http://localhost:3000", "SUCCESS")
    log("Press Ctrl+C to shut down gracefully.", "INFO")
    
    try:
        webbrowser.open("http://localhost:3000")
    except Exception as e:
        log(f"Could not open browser: {e}", "WARNING")
    
    # Keep alive and monitor processes
    try:
        while True:
            time.sleep(5)
            # Check if critical process (Backend) died
            for name, proc in PROCS:
                if name == "Backend API" and proc.poll() is not None:
                    log("❌ CRITICAL: Backend API died unexpectedly!", "ERROR")
                    cleanup(None, None)
    except KeyboardInterrupt:
        cleanup(None, None)
