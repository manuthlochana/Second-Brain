import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_telegram_alert(message: str):
    """
    Sends a proactive message to the user via Telegram.
    Used by Scheduler and Proactive Triggers.
    """
    if not TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing. Skipping alert.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                print(f"❌ Telegram Send Failed: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")
