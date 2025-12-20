import os
import httpx
import logging
from app.mcp.registry import mcp
from app.core.shared_state import state

logger = logging.getLogger("MCP_TELEGRAM")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

def get_chat_id():
    """
    Prioritize ADMIN_CHAT_ID from .env
    If not found, use the temporary ID from current session (state)
    """
    # 1. .env ထဲက ID ကို အရင်ယူမယ် (Permanent ID)
    env_id = os.getenv("ADMIN_CHAT_ID")
    if env_id:
        return env_id
        
    # 2. မရှိမှ လက်ရှိ Session ID ကို ယူမယ်
    return state.telegram_chat_id

@mcp.tool(category="telegram")
async def send_text(message: str):
    """
    Sends a text message (or links) to the user via Telegram.
    Args:
        message: The text content or URL to send.
    """
    chat_id = get_chat_id()
    if not chat_id: 
        return "Error: I don't know your Telegram Chat ID yet. Please text me on Telegram first."

    async with httpx.AsyncClient() as client:
        try:
            url = f"{BASE_URL}/sendMessage"
            
            # 🔥 UPDATE: Added parse_mode for Hyperlinks
            payload = {
                "chat_id": chat_id, 
                "text": message,
                "parse_mode": "HTML",             # <--- UI Link Masking (Link ဖုံးဖို့ ဒါလိုပါတယ်)
                "disable_web_page_preview": True  # <--- Link Preview ပိတ်ထားမယ် (စာသားသန့်သန့်လေးဖြစ်အောင်)
            }
            
            await client.post(url, json=payload)
            return "Message sent successfully."
        except Exception as e:
            return f"Failed to send: {e}"

@mcp.tool(category="telegram")
async def send_location(lat: float = None, lng: float = None):
    """
    Sends the STATIC Live Location pin to Telegram.
    """
    chat_id = get_chat_id()
    
    if lat is None or lng is None:
        if state.current_gps:
            try:
                lat_str, lng_str = state.current_gps.split(",")
                lat, lng = float(lat_str), float(lng_str)
            except:
                return "Error: Invalid GPS data format."
        else:
            return "Error: No GPS location available."

    async with httpx.AsyncClient() as client:
        try:
            url = f"{BASE_URL}/sendLocation"
            payload = {"chat_id": chat_id, "latitude": lat, "longitude": lng}
            await client.post(url, json=payload)
            return f"Location map sent."
        except Exception as e:
            return f"Failed to send location: {e}"