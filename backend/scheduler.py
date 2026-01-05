import os
import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import httpx
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from dotenv import load_dotenv

import database
from contextlib import contextmanager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SCHEDULER - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("SCHEDULER")

API_URL = "http://127.0.0.1:8000"
API_KEY = os.getenv("API_KEY", "secret-key")

@contextmanager
def get_db_session():
    """Yields a DB session."""
    db_gen = database.get_db()
    db = next(db_gen)
    try:
        yield db
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
        except Exception:
            pass

import telegram_utils # Import our new helper

class ExecutiveScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def trigger_brain(self, reason: str, context: str = ""):
        """
        Hits the backend API to trigger the reasoning core.
        """
        logger.info(f"⚡ Triggering Brain: {reason}")
        headers = {
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        }
        # In a real scenario, context would be passed. The endpoint simplified takes user_input often.
        # But we added /proactive/trigger which accepts nothing, just a signal? 
        # Actually /proactive/trigger calls process_brain_task with hardcoded text.
        # Ideally we update main.py to accept custom prompt in proactive trigger or just generic check.
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{API_URL}/proactive/trigger", headers=headers)
                if resp.status_code == 200:
                    logger.info("   ✅ Trigger Successful")
                    # Also notify Telegram proactively
                    await telegram_utils.send_telegram_alert(f"⚡ *Brain Triggered*: {reason}")
                else:
                    logger.error(f"   ❌ Trigger Failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"   ❌ Connection Error: {e}")

    def run_pulse(self):
        """
        The 1-Minute Heartbeat.
        Checks for tasks due soon using direct DB access.
        """
        # Note: APScheduler runs this in a thread/executor usually if sync, or async if async def.
        # We make it synchronous DB access but wrapped? Or just DB access.
        # DB access is blocking. Should ideally be async or run in executor.
        # For simplicity in this stack using sync sqlalchemy:
        
        now = datetime.now()
        window = now + timedelta(minutes=5)
        
        logger.debug("❤️ Pulse Check...")
        
        with get_db_session() as session:
            # Query for PENDING tasks due between now and window
            tasks = session.execute(
                select(database.Task).where(
                    and_(
                        database.Task.status == 'PENDING',
                        database.Task.due_date <= window,
                        database.Task.due_date >= now - timedelta(minutes=1) # Don't re-alert too old?
                    )
                )
            ).scalars().all()
            
            if tasks:
                task_titles = [t.title for t in tasks]
                logger.info(f"   ⏰ Found urgent tasks: {task_titles}")
                # We need to trigger the brain. Since this function is not async def here (or is it?),
                # we can use asyncio.run or ensure the scheduler runs async jobs? 
                # APScheduler AsyncIOScheduler expects `async def` for awaitable jobs.
                # But DB access is sync.
                # Strategy: We will separate DB check (Sync) and Trigger (Async)?
                # No, better: Make this `async def` and use `await asyncio.to_thread` for DB.
                pass 

    async def run_pulse_async(self):
        """
        Async wrapper for the pulse.
        """
        now = datetime.now()
        window = now + timedelta(minutes=5)
        
        # Run DB query in thread to not block loop
        def check_db():
            with get_db_session() as session:
                return session.execute(
                    select(database.Task).where(
                        and_(
                            database.Task.status == 'PENDING',
                            database.Task.due_date <= window
                        )
                    )
                ).scalars().all()

        try:
            urgent_tasks = await asyncio.to_thread(check_db)
            
            if urgent_tasks:
                count = len(urgent_tasks)
                logger.info(f"❤️ Pulse: Found {count} urgent tasks.")
                await self.trigger_brain(f"Pulse Alert: {count} tasks due.")
            else:
                logger.debug("❤️ Pulse: No urgent tasks.")
                
        except Exception as e:
            logger.error(f"Error in Pulse: {e}")

    async def run_daily_reflection(self):
        """
        2 AM Reflection. Triggers Graph Inference.
        """
        logger.info("🌙 Starting Daily Reflection...")
        headers = {"X-API-Key": API_KEY}
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{API_URL}/graph/inference", headers=headers)
                logger.info("   ✅ Reflection Triggered.")
        except Exception as e:
            logger.error(f"   ❌ Reflection Failed: {e}")

    async def start_scheduler(self):
        logger.info("⏳ Starting Executive Scheduler...")
        
        # 1. Pulse: Every 60 seconds
        self.scheduler.add_job(
            self.run_pulse_async, 
            IntervalTrigger(seconds=60), 
            id='pulse', 
            replace_existing=True
        )
        
        # 2. Daily Reflection: 2:00 AM
        self.scheduler.add_job(
            self.run_daily_reflection, 
            CronTrigger(hour=2, minute=0), 
            id='daily_reflection',
            replace_existing=True
        )
        
        self.scheduler.start()
        
        # Keep alive
        try:
            while True:
                await asyncio.sleep(1000)
        except (KeyboardInterrupt, SystemExit):
            pass

if __name__ == "__main__":
    scheduler = ExecutiveScheduler()
    try:
        asyncio.run(scheduler.start_scheduler())
    except (KeyboardInterrupt, SystemExit):
        pass
