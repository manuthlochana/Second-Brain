import asyncio
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

# Import from backend modules
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.database import Task, Base
from backend.scheduler import ExecutiveScheduler

# Use the same DB URL as backend
# Assuming sqlite for local dev as established in main.py fallback logic or logs
DATABASE_URL = "sqlite:///./backend/brain.db" 

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def create_urgent_task():
    print("🕑 Creating urgent task for testing...")
    session = SessionLocal()
    
    due_soon = datetime.datetime.now() + datetime.timedelta(seconds=30)
    
    task = Task(
        id=uuid4(),
        title="Test Urgent Task Trigger",
        status="PENDING",
        due_date=due_soon
    )
    session.add(task)
    session.commit()
    print(f"✅ Created Task: '{task.title}' due at {task.due_date}")
    session.close()

async def run_scheduler_briefly():
    print("⏳ Running Scheduler for 70 seconds...")
    sched = ExecutiveScheduler()
    
    # Manually start scheduler non-blocking for this script
    sched.scheduler.add_job(sched.run_pulse_async, 'interval', seconds=10) # Speed up for test
    sched.scheduler.start()
    
    await asyncio.sleep(70)
    print("🛑 Stopping Scheduler test.")

if __name__ == "__main__":
    create_urgent_task()
    # We need to run the async scheduler loop
    try:
        asyncio.run(run_scheduler_briefly())
    except KeyboardInterrupt:
        pass
