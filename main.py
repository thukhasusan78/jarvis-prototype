import json
import logging
import os
import time
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import uvicorn
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from app.core.config import Config
from app.core.shared_state import state
from app.senses.rtc_handler import create_webrtc_session

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JARVIS_SERVER")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
pcs = set()

@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/offer")
async def offer(request: Request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    # STUN Server for AWS/External Access
    ice_config = RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
    )
    pc = RTCPeerConnection(configuration=ice_config)
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState in ["failed", "closed"]:
            await pc.close()
            pcs.discard(pc)

    await create_webrtc_session(pc, offer)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

# --- 🔥 FIX IS HERE (Websocket Logic) ---
@app.websocket("/ws/data")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("[WebSocket] 🟢 Client Connected via /ws/data")
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if "gps" in msg:
                gps_data = msg["gps"]
                lat = gps_data.get("lat")
                lng = gps_data.get("lng")
                acc = gps_data.get("accuracy", 0)
                ts = gps_data.get("timestamp", 0)
                
                # 1. Update Basic State
                state.current_gps = f"{lat},{lng}"
                
                # 2. 🔥 CRITICAL FIX: Save lat/lng into metadata too!
                state.gps_metadata = {
                    "lat": lat,   # <--- Added this
                    "lng": lng,   # <--- Added this
                    "accuracy": acc,
                    "client_ts": ts,
                    "server_ts": time.time()
                }
                
                # Debug log for verification
                if acc < 100:
                    # Only log accurate updates to keep terminal clean
                    pass 

    except Exception as e:
        logger.warning(f"[WebSocket] 🔴 Client Disconnected: {e}")

if __name__ == "__main__":
    print("\n[JARVIS] 🚀 SYSTEM ONLINE. Listening on Port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)