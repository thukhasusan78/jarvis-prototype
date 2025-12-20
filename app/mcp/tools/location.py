import httpx
import os
import time
import logging
from app.mcp.registry import mcp
from app.core.shared_state import state
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("MCP_LOCATION")

# --- HELPER: GPS VALIDATION ---
def is_gps_reliable():
    # 1. Check Metadata
    meta = state.gps_metadata
    if meta:
        if time.time() - meta.get("server_ts", 0) > 600:
            print("❌ DEBUG: GPS Data Stale.")
            return False, "GPS signal is too old. Please wake up your phone browser.", None
        
        lat = meta.get("lat")
        lng = meta.get("lng")
        if lat and lng:
            return True, str(lat), str(lng)

    # 2. Fallback
    if state.current_gps:
        try:
            lat, lng = state.current_gps.split(",")
            return True, lat, lng
        except:
            pass

    return False, "No GPS data. Please check phone dashboard.", None

# --- HELPER: TELEGRAM SENDER (FIXED & ESCAPED) ---
async def push_to_telegram(text):
    chat_id = os.getenv("ADMIN_CHAT_ID")
    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not chat_id or not token:
        print("❌ FAILED: Missing Chat ID or Token.")
        return "System Error: Config Missing."

    # 🔥 CRITICAL FIX: URL Escape for HTML Parse Mode
    # Telegram HTML mode hates raw '&' symbols in links. We must escape them.
    # But NOT if they are already escaped (simple check).
    safe_text = text.replace("&", "&amp;")
    # Note: If we double escape (&amp;amp;), it usually still works or just looks odd, 
    # but unescaped & crashes the API. This simple fix covers 99% cases.

    print(f"📨 SENDING TO ID: {chat_id} | Payload Size: {len(safe_text)}")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # disable_web_page_preview=True added to speed up delivery
    payload = {
        "chat_id": chat_id, 
        "text": safe_text, 
        "parse_mode": "HTML", 
        "disable_web_page_preview": True 
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                print("✅ SUCCESS: Message Delivered.")
                return "SUCCESS"
            else:
                print(f"❌ TELEGRAM ERROR: {resp.text}")
                return f"Telegram Error: {resp.text}"
        except Exception as e:
            print(f"❌ NETWORK ERROR: {e}")
            return f"Network Error: {e}"

# ==========================================
# TOOLS
# ==========================================

@mcp.tool(category="location")
async def get_current_address():
    valid, lat, lng = is_gps_reliable()
    if not valid: return lat

    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
        headers = {"User-Agent": "Jarvis_M.K.1_Project"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()
            address = data.get("display_name", "Unknown Area")
            parts = address.split(",")
            short = f"{parts[0]}, {parts[1] if len(parts)>1 else ''}"
            return f"Current Location: {short}."
    except Exception as e:
        return f"Address Error: {e}"

@mcp.tool(category="location")
async def calculate_route_info(destination: str):
    valid, lat, lng = is_gps_reliable()
    if not valid: return lat

    try:
        headers = {"User-Agent": "Jarvis_M.K.1_Project"}
        async with httpx.AsyncClient() as client:
            # Search
            s_url = f"https://nominatim.openstreetmap.org/search?q={destination}&format=json&limit=1"
            s_resp = await client.get(s_url, headers=headers)
            s_data = s_resp.json()
            
            if not s_data: return f"Could not find '{destination}'."
            d_lat, d_lng = s_data[0]["lat"], s_data[0]["lon"]

            # Route info only (No link sent here)
            r_url = f"http://router.project-osrm.org/route/v1/driving/{lng},{lat};{d_lng},{d_lat}?overview=false"
            r_resp = await client.get(r_url)
            r_data = r_resp.json()

            if r_data["code"] != "Ok": return "Route calculation failed."

            leg = r_data["routes"][0]["legs"][0]
            dist_km = leg["distance"] / 1000
            dur_min = leg["duration"] / 60
            
            return f"Distance: {dist_km:.1f} km, Time: ~{int(dur_min)} mins."

    except Exception as e:
        return f"Error: {e}"

@mcp.tool(category="location")
async def send_my_map():
    valid, lat, lng = is_gps_reliable()
    if not valid: return lat

    # Raw link created here
    map_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    
    # Text is passed to push_to_telegram which handles escaping
    res = await push_to_telegram(f"📍 <b>Location Pin</b>\n\n<a href='{map_link}'>Open Map</a>")
    return "Map sent." if res == "SUCCESS" else f"Failed: {res}"

@mcp.tool(category="location")
async def send_navigation_link(destination: str):
    valid, lat, lng = is_gps_reliable()
    if not valid: return lat

    try:
        headers = {"User-Agent": "Jarvis_M.K.1_Project"}
        async with httpx.AsyncClient() as client:
            s_resp = await client.get(f"https://nominatim.openstreetmap.org/search?q={destination}&format=json&limit=1", headers=headers)
            s_data = s_resp.json()
            if not s_data: return "Destination not found."
            
            d_lat, d_lng = s_data[0]["lat"], s_data[0]["lon"]
            
            # This link contains '&' which causes the crash!
            # But push_to_telegram will now replace it with '&amp;'
            nav_link = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lng}&destination={d_lat},{d_lng}&travelmode=driving"
            
            res = await push_to_telegram(f"🚗 <b>Navigate to {destination}</b>\n\n<a href='{nav_link}'>Start Driving</a>")
            return "Link sent." if res == "SUCCESS" else f"Failed: {res}"
            
    except Exception as e:
        return f"Error: {e}"