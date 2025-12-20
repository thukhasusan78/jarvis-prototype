import asyncio
import json
import logging
import av
import time
import websockets
import base64
from fractions import Fraction
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from app.core.config import Config
from app.core.key_manager import key_manager
from app.brain.memory import MemorySystem
from app.mcp import mcp
from app.senses.hearing import Ear

logger = logging.getLogger("JARVIS_RTC")

# Initialize Ear System (Loads Model Once)
jarvis_ear = Ear(Config.OWNER_VOICE_PATH)

class GeminiAudioTrack(MediaStreamTrack):
    """
    Gemini Output Track with Optimized Buffer for Smoothness vs Latency
    """
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.q = asyncio.Queue()
        self.pts = 0
        self.out_sample_rate = 48000
        self.AUDIO_PTIME = 0.020  # 20ms Packet Time
        self.samples_per_frame = int(self.out_sample_rate * self.AUDIO_PTIME)
        
        # Resampler (24k -> 48k)
        self.resampler = av.AudioResampler(
            format='s16', layout='mono', rate=self.out_sample_rate
        )
        self.buffer = bytearray()

    async def recv(self):
        # 🔥 FIX: Buffer Size ကို တိုးလိုက်သည် (Stutter မဖြစ်အောင်)
        # 1 Frame = 20ms
        # 100 Frames = 2 Seconds (Max Latency Cap)
        
        if self.q.qsize() > 100: 
            dropped = 0
            # Queue အရမ်းကြပ်မှသာ 0.5s စာလောက် (25 frames) ချန်ပြီး ကျန်တာဖြတ်မယ်
            while self.q.qsize() > 25: 
                _ = self.q.get_nowait()
                dropped += 1
            if dropped > 0:
                logger.warning(f"⚡ [Latency] Cleaned up {dropped} frames. (Buffer Reset)")

        frame = await self.q.get()
        frame.pts = self.pts
        frame.time_base = Fraction(1, self.out_sample_rate)
        self.pts += frame.samples
        return frame

    def add_audio_chunk(self, pcm_data_24k):
        """Sync Method called by Gemini Listener"""
        if not pcm_data_24k: return

        try:
            samples = len(pcm_data_24k) // 2
            input_frame = av.AudioFrame(format='s16', layout='mono', samples=samples)
            input_frame.planes[0].update(pcm_data_24k)
            input_frame.sample_rate = 24000
            input_frame.time_base = Fraction(1, 24000)

            output_frames = self.resampler.resample(input_frame)
            
            for f in output_frames:
                self.buffer.extend(f.to_ndarray().tobytes())

            frame_size_bytes = self.samples_per_frame * 2 
            while len(self.buffer) >= frame_size_bytes:
                chunk = self.buffer[:frame_size_bytes]
                self.buffer = self.buffer[frame_size_bytes:]

                frame = av.AudioFrame(format='s16', layout='mono', samples=self.samples_per_frame)
                frame.planes[0].update(chunk)
                frame.sample_rate = 48000
                frame.time_base = Fraction(1, 48000)
                
                self.q.put_nowait(frame)
                
        except Exception as e:
            logger.error(f"Audio Processing Error: {e}")


class JarvisSession:
    def __init__(self):
        self.api_key = key_manager.get_next_key()
        self.url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}"
        self.memory = MemorySystem()
        self.gemini_ws = None
        self.audio_out_track = GeminiAudioTrack()
        
        # Input Resampler (48k -> 16k for Gemini)
        self.in_resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)

        # --- 🔥 SPEAKER ID GATEKEEPER STATE ---
        self.verification_state = "pending" # pending | verified | denied
        self.id_buffer = bytearray()        # Accumulate input for ID check
        self.gemini_output_buffer = []      # Hold Gemini response while checking
        self.last_input_time = time.time()
        self.is_verifying = False           # 🔥 New Flag to prevent overlapping checks

    async def connect_gemini(self):
        try:
            # Ping Interval helps keep connection stable
            self.gemini_ws = await websockets.connect(self.url, ping_interval=20, ping_timeout=10)
            logger.info("✅ Connected to Gemini Live API")
            await self.send_setup_msg()
            asyncio.create_task(self.gemini_listener())
        except Exception as e:
            logger.error(f"Gemini Connection Failed: {e}")

    async def send_setup_msg(self):
        sys_instruction = self.memory.build_system_instruction()
        
        # Inject MCP Tools
        tools = mcp.get_gemini_tools()
        logger.info(f"[Setup] Injecting {len(tools[0]['function_declarations'])} MCP Tools.")

        msg = {
            "setup": {
                "model": Config.LIVE_MODEL, 
                "tools": tools,
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": Config.TTS_VOICE 
                            }
                        }
                    }
                },
                "system_instruction": {
                    "parts": [{"text": sys_instruction}]
                }
            }
        }
        await self.gemini_ws.send(json.dumps(msg))
        logger.info("Sent Setup Message to Gemini")

    async def gemini_listener(self):
        """Listens for responses from Gemini"""
        try:
            async for raw_msg in self.gemini_ws:
                response = json.loads(raw_msg)

                # 1. Handle Audio Output (with Gatekeeper)
                if "serverContent" in response:
                    parts = response["serverContent"].get("modelTurn", {}).get("parts", [])
                    for part in parts:
                        if "inlineData" in part:
                            b64_data = part["inlineData"]["data"]
                            pcm_data = base64.b64decode(b64_data)
                            
                            # --- 🛑 GATEKEEPER LOGIC ---
                            if self.verification_state == "verified":
                                # Approved: Play immediately
                                self.audio_out_track.add_audio_chunk(pcm_data)
                            
                            elif self.verification_state == "denied":
                                # Rejected: Drop audio (Silence)
                                pass 
                            
                            else:
                                # Pending: Buffer it until ID check finishes
                                self.gemini_output_buffer.append(pcm_data)

                # 2. Handle Tool Call (MCP)
                if "toolCall" in response:
                    await self.handle_tool_call(response["toolCall"])

        except Exception as e:
            logger.error(f"Gemini Listener Error: {e}")

    async def handle_tool_call(self, tool_call_data):
        function_calls = tool_call_data.get("functionCalls", [])
        function_responses = []

        for call in function_calls:
            name = call["name"]
            args = call["args"]
            call_id = call["id"]

            logger.info(f"[Jarvis] 🧠 Brain requested tool: {name}")
            execution_result = await mcp.execute(name, args)
            
            function_responses.append({
                "name": name,
                "response": {"result": execution_result}, 
                "id": call_id
            })

        if function_responses:
            msg = {
                "toolResponse": {
                    "functionResponses": function_responses
                }
            }
            await self.gemini_ws.send(json.dumps(msg))

    # --- INPUT PROCESSING (Parallel & Non-Blocking) ---
    async def process_input_stream(self, track):
        """Reads WebRTC input, sends to Gemini, and checks Speaker ID in parallel"""
        while True:
            try:
                frame = await track.recv()
                
                # Resample 48k -> 16k
                resampled_frames = self.in_resampler.resample(frame)
                pcm_bytes = b"".join([f.to_ndarray().tobytes() for f in resampled_frames])
                
                if not pcm_bytes: continue

                # 1. Update Timestamp (Reset logic with 0.8s)
                now = time.time()
                silence_gap = now - self.last_input_time
                
                # 🔥 FIX: Reset if silence > 0.8s (Prevent piggybacking & allow retry after denial)
                if silence_gap > 0.8:
                    if self.verification_state != "pending":
                        # logger.info("🔄 Session Reset. Ready for new command.")
                        self.verification_state = "pending"
                        self.id_buffer.clear()
                        self.gemini_output_buffer.clear()
                        self.is_verifying = False

                self.last_input_time = now

                # 2. Send to Gemini IMMEDIATELY (Latency Priority)
                # This ensures Gemini starts processing while we check ID in background
                await self.send_audio_to_gemini(pcm_bytes)

                # 3. Parallel Speaker ID Check (Non-Blocking)
                if Config.ENABLE_SPEAKER_ID and self.verification_state == "pending":
                    self.id_buffer.extend(pcm_bytes)
                    
                    # Wait for enough audio (~0.5s) and ensure no check is running
                    if len(self.id_buffer) > 16000 and not self.is_verifying:
                        self.is_verifying = True
                        # 🔥 Run in Background Task (This fixes the 20s latency)
                        asyncio.create_task(self.run_verification_task())

            except Exception as e:
                logger.info(f"Input Stream Ended: {e}")
                break

    async def run_verification_task(self):
        """Background task to verify speaker without blocking audio stream"""
        try:
            # Make a copy of buffer to verify
            check_data = bytes(self.id_buffer)
            
            # Run CPU-heavy task in thread
            is_owner, conf = await asyncio.to_thread(jarvis_ear.identify_speaker, check_data)
            
            if is_owner:
                logger.info(f"✅ [Gatekeeper] Voice Verified ({conf:.2f}). Release Buffer.")
                self.verification_state = "verified"
                
                # Flush Buffered Output
                for chunk in self.gemini_output_buffer:
                    self.audio_out_track.add_audio_chunk(chunk)
                self.gemini_output_buffer.clear()
                
            else:
                # Access Denied
                logger.warning(f"❌ [Gatekeeper] Access Denied ({conf:.2f}). Dropping Audio.")
                self.verification_state = "denied"
                self.gemini_output_buffer.clear() # Dump buffered audio
        
        except Exception as e:
            logger.error(f"Verification Error: {e}")
        
        finally:
            self.is_verifying = False # Allow next check

    async def send_audio_to_gemini(self, pcm_bytes):
        if self.gemini_ws:
            try:
                b64_audio = base64.b64encode(pcm_bytes).decode('utf-8')
                msg = {
                    "realtime_input": {
                        "media_chunks": [{
                            "data": b64_audio,
                            "mime_type": "audio/pcm"
                        }]
                    }
                }
                await self.gemini_ws.send(json.dumps(msg))
            except Exception:
                pass

async def create_webrtc_session(pc: RTCPeerConnection, offer: RTCSessionDescription):
    session = JarvisSession()
    await session.connect_gemini()
    pc.addTrack(session.audio_out_track)

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            logger.info("🎤 Received Audio Track from User")
            asyncio.create_task(session.process_input_stream(track))