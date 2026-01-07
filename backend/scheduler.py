import os
import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import httpx
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

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

import telegram_utils # Import our Telegram helper

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
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{API_URL}/proactive/trigger", headers=headers)
                if resp.status_code == 200:
                    logger.info("   ✅ Trigger Successful")
                    await telegram_utils.send_telegram_alert(f"⚡ *Brain Triggered*: {reason}")
                else:
                    logger.error(f"   ❌ Trigger Failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"   ❌ Connection Error: {e}")

    async def run_pulse_async(self):
        """
        The 1-Minute Heartbeat.
        Checks for tasks due soon.
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

    async def check_user_engagement(self):
        """
        PROACTIVE LONELINESS CHECK.
        If user hasn't interacted in 6+ hours, send a social check-in message.
        """
        logger.info("💭 Checking user engagement...")
        
        def get_last_interaction():
            with get_db_session() as session:
                # Get user profile stats
                profile = session.execute(select(database.UserProfile).limit(1)).scalar_one_or_none()
                if not profile:
                    return None
                
                stats = profile.stats or {}
                last_interaction_str = stats.get('last_interaction')
                
                if not last_interaction_str:
                    # Check audit log as fallback
                    latest_log = session.execute(
                        select(database.AuditLog).order_by(desc(database.AuditLog.created_at)).limit(1)
                    ).scalar_one_or_none()
                    
                    if latest_log:
                        return latest_log.created_at
                    return None
                
                # Parse ISO format
                from dateutil import parser
                return parser.parse(last_interaction_str)
        
        try:
            last_interaction = await asyncio.to_thread(get_last_interaction)
            
            if not last_interaction:
                logger.info("   No interaction history found yet")
                return
            
            # Check if it's been 6+ hours
            now = datetime.now()
            hours_since = (now - last_interaction.replace(tzinfo=None)).total_seconds() / 3600
            
            logger.info(f"   Last interaction: {hours_since:.1f} hours ago")
            
            if hours_since >= 6:
                # Generate proactive message
                message = await self.generate_checkin_message()
                
                # Send via Telegram
                await telegram_utils.send_telegram_alert(message)
                logger.info(f"   ✅ Sent proactive check-in")
            else:
                logger.debug(f"   User active recently ({hours_since:.1f}h ago)")
                
        except Exception as e:
            logger.error(f"Error in engagement check: {e}")
    
    async def generate_checkin_message(self) -> str:
        """
        Uses LLM to generate contextual social check-in based on user's recent topics.
        """
        def get_recent_context():
            with get_db_session() as session:
                # Get recent notes
                recent_notes = session.execute(
                    select(database.Note).order_by(desc(database.Note.created_at)).limit(3)
                ).scalars().all()
                
                return [note.content for note in recent_notes]
        
        try:
            recent_context = await asyncio.to_thread(get_recent_context)
            
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return "Machan, quiet day today. Everything okay? 👋"
            
            llm = ChatGoogleGenerativeAI(model="gemini-flash-latest", temperature=0.8, google_api_key=api_key)
            
            template = """
You are Jarvis, a smart friend checking in on Manuth who hasn't spoken to you in 6+ hours.

Recent context from memory:
{context}

Generate a SHORT, CASUAL, FRIENDLY check-in message (1-2 sentences max).
- Reference recent topics naturally if relevant
- Use casual Sri Lankan English ("Machan", etc.)
- Don't be clingy or annoying
- Show you care but keep it light

Examples:
- "Machan, quiet day today. Everything okay with the girlfriend? 👋"
- "All good? Haven't heard from you in a bit."
- "Hope you're doing alright! Let me know if you need anything."
"""
            
            prompt = PromptTemplate(template=template, input_variables=["context"])
            chain = prompt | llm
            
            context_str = "\n".join(recent_context) if recent_context else "No recent context"
            response = chain.invoke({"context": context_str})
            
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate check-in message: {e}")
            return "Hey Machan! Just checking in. All good? 👋"

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
        
        # 2. Engagement Check: Every hour
        self.scheduler.add_job(
            self.check_user_engagement,
            IntervalTrigger(hours=1),
            id='engagement_check',
            replace_existing=True
        )
        
        # 3. Daily Reflection: 2:00 AM
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
