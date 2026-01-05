import os
import logging
import asyncio
import httpx
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ChatAction

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("TELEGRAM_CHAT_ID") # Your specific ID for security
API_BASE_URL = "http://127.0.0.1:8000"
API_KEY = os.getenv("API_KEY", "secret-key")

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing!")

# --- Helpers ---

async def is_authorized(update: Update) -> bool:
    """Checks if the user is the authorized CEO."""
    user = update.effective_user
    if str(user.id) != str(ALLOWED_USER_ID):
        logger.warning(f"Unauthorized access attempt from {user.id} ({user.username})")
        await update.message.reply_text("⛔ Unauthorized Access.")
        return False
    return True

async def send_to_brain(text: str, source: str = "telegram") -> str:
    """Sends text to the FastAPI Brain and returns the response."""
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"user_input": text, "source": source}
    
    async with httpx.AsyncClient() as client:
        # Ingest endpoint is async (202 Accepted). 
        # We need a way to get the response.
        # Ideally, we should poll or use the same logic as verify_api to wait/listen?
        # Or, we update the API to return synchronous response for simpler integrations if needed.
        # But wait, the previous `process_brain_task` logic was background.
        # FOR THIS BOT: We'll modify logic to use a sync/direct endpoint or handle the WS flow.
        # SIMPLIFICATION: Since telegram bot is async, we can wait.
        # However, `agent_engine` is blocking. The backend runs it in thread.
        # Does the backend return the answer in the HTTP response?
        # Looking at previous main.py: /ingest/web returns `APIResponse` with status "accepted". 
        # It DOES NOT return the answer text immediately. The answer goes to WS.
        
        # Challenge: Telegram bot needs the answer.
        # Solution 1: We create a new endpoint /ingest/sync that blocks and returns the answer.
        # Solution 2: We simulate the logic here directly (import agent_engine).
        # Solution 3: We poll for status? No.
        
        # Best Approach for "Hybrid": Import `agent_engine` logic directly here if running on same server?
        # But we want separation.
        # Let's create a Synchronous endpoint in main.py or just use the agent directly here since it IS part of the backend codebase.
        # Using `agent_engine.run_agent(text)` directly is cleaner for a "local" bot running alongside the API.
        pass

# --- Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    await update.message.reply_text("👋 Jarvis Online. Ready for instructions.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    help_text = """
    📜 *Command List*:
    /start - Wake up Jarvis
    /status - Check system health
    /today - Daily Briefing
    /vault - Secure Notes
    """
    await update.message.reply_markdown(help_text)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for text messages."""
    if not await is_authorized(update): return
    
    text = update.message.text
    logger.info(f"Received: {text}")

    # UI Feedback
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    # Process directly via Agent Engine (since we're in the same backend env)
    # This avoids the Async/WS complexity for the bot.
    try:
        # Dynamic import to avoid circular dependency if any, or just import at top
        from agent_engine import run_agent
        
        # Use run_agent directly - this is blocking but fine for a simple bot instance
        # Ideally run in executor
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, run_agent, text)
        
        await update.message.reply_markdown(response)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.message.reply_text("⚠️ Critical System Failure.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_authorized(update): return
    await update.message.reply_text("🎤 Voice processing coming soon...")

async def proactive_push(context: ContextTypes.DEFAULT_TYPE):
    """Job to push scheduled messages."""
    job = context.job
    await context.bot.send_message(job.chat_id, text=job.data)

# --- Proactive Listener (Simulated) ---
# To make this bot "Proactive", it needs to listen to the Scheduler.
# Since the scheduler is a separate process hitting an API, the BOT needs to expose an API or check a queue?
# OR: We just run this Bot script, and IT starts a small web server?
# Better: We add `telegram_bot.py` logic INTO `main.py` allowing proper webhook integration?
# OR: Simple Polling bot that also has a tiny server?
# Simplest for "CEO Brain": Run this script. It uses `Application` which can run alongside a simple starlette/fastapi or we assume scheduler just hits the MAIN API, and MAIN API sends to Telegram?
# YES. `main.py` should be the sender. This script is just the "Receiver/UI".
# Actually, `python-telegram-bot` can send messages proactively if initialized with the token.
# So `main.py` or `scheduler.py` can import a `send_telegram(chat_id, text)` function.

# Let's keep `telegram_bot.py` as the "Listener" process.
# And `scheduler.py` will use a simple helper to send messages.

def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Text
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Voice
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("🤖 Telegram Bot Interface Started...")
    application.run_polling()

if __name__ == "__main__":
    main()
