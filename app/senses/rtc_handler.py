import asyncio
import json
import logging
import av
import base64
import time
import websockets
import numpy as np
from fractions import Fraction
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from app.core.config import Config
from app.core.key_manager import key_manager
from app.brain.memory import MemorySystem
from app.mcp.registry import mcp

logger = logging.getLogger("JARVIS_RTC")

class GeminiAudioTrack(MediaStreamTrack):
    """
    🔥 VIBER-STYLE ADAPTIVE STREAM TRACK
    - Instant Start with "Priming" (Silence Runway)
    - Long Soft-Wait (0.75s) to prevent cut-offs on bad networks
    - Continuous PTS Timing
    """
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.raw_queue = asyncio.Queue()
        self.frame_queue = asyncio.Queue()
        
        self.out_sample_rate = 48000
        self.AUDIO_PTIME = 0.020  # 20ms
        self.SAMPLES_PER_FRAME = int(self.out_sample_rate * self.AUDIO_PTIME) # 960 samples
        
        self.pts = 0
        
        # --- 🚀 ADAPTIVE SETTINGS ---
        self.is_priming = True         # အစပိုင်း Silence ခင်းမယ့် Mode
        self.priming_frames_left = 3   # ရှေ့ဆုံးကနေ Silence 5 Frames (100ms) အရင်လွှတ်မယ်
        
        self.resampler = av.AudioResampler(format='s16', layout='mono', rate=self.out_sample_rate)
        self.silence_frame = self._create_silence_frame()
        
        # Start Background Worker
        asyncio.create_task(self._audio_transformer())

    def _create_silence_frame(self):
        frame = av.AudioFrame(format='s16', layout='mono', samples=self.SAMPLES_PER_FRAME)
        data = np.zeros(self.SAMPLES_PER_FRAME, dtype=np.int16)
        frame.planes[0].update(data.tobytes())
        frame.sample_rate = self.out_sample_rate
        frame.time_base = Fraction(1, self.out_sample_rate)
        return frame

    def _get_silence_frame(self):
        """Returns a copy of the silence frame with correct timestamp"""
        f = av.AudioFrame(format='s16', layout='mono', samples=self.SAMPLES_PER_FRAME)
        # Use to_ndarray().tobytes() to avoid AttributeError
        f.planes[0].update(self.silence_frame.to_ndarray().tobytes())
        f.sample_rate = self.out_sample_rate
        f.time_base = Fraction(1, self.out_sample_rate)
        return f

    def add_audio_chunk(self, b64_data):
        if b64_data:
            try:
                pcm_bytes = base64.b64decode(b64_data)
                self.raw_queue.put_nowait(pcm_bytes)
            except Exception as e:
                logger.error(f"Decode Error: {e}")

    async def _audio_transformer(self):
        """Worker: Raw -> Resample -> Slice -> Queue"""
        buffer = bytearray()
        
        while True:
            try:
                pcm_data = await self.raw_queue.get()
                
                if len(pcm_data) % 2 != 0: continue

                input_frame = av.AudioFrame(format='s16', layout='mono', samples=len(pcm_data)//2)
                input_frame.planes[0].update(pcm_data)
                input_frame.sample_rate = 24000
                input_frame.time_base = Fraction(1, 24000)

                output_frames = self.resampler.resample(input_frame)
                
                for f in output_frames:
                    buffer.extend(f.to_ndarray().tobytes())

                FRAME_SIZE_BYTES = self.SAMPLES_PER_FRAME * 2
                
                while len(buffer) >= FRAME_SIZE_BYTES:
                    chunk = buffer[:FRAME_SIZE_BYTES]
                    buffer = buffer[FRAME_SIZE_BYTES:]
                    
                    frame = av.AudioFrame(format='s16', layout='mono', samples=self.SAMPLES_PER_FRAME)
                    frame.planes[0].update(chunk)
                    frame.sample_rate = self.out_sample_rate
                    frame.time_base = Fraction(1, self.out_sample_rate)
                    
                    await self.frame_queue.put(frame)
                    
            except Exception as e:
                logger.error(f"Transformer Error: {e}")

    async def recv(self):
        """
        WebRTC Consumer with Viber-like Adaptive Logic
        """
        frame = None
        
        # 1. 🛫 Priming Phase (The Runway)
        # အစမှာ Real Audio မစောင့်ဘဲ Silence အရင်လွှတ်ပြီး လမ်းခင်းပေးလိုက်တယ် (Instant Start)
        if self.is_priming:
            if self.priming_frames_left > 0:
                self.priming_frames_left -= 1
                frame = self._get_silence_frame()
                # Update PTS and return immediately
                frame.pts = self.pts
                frame.time_base = Fraction(1, self.out_sample_rate)
                self.pts += self.SAMPLES_PER_FRAME
                return frame
            else:
                self.is_priming = False
                # Priming ပြီးတာနဲ့ အောက်က Real Logic ကို ဆက်သွားမယ်

        # 2. 📡 Real Audio Phase (with Long Soft-Wait)
        try:
            # ဆရာ့ request အတိုင်း 0.75s (750ms) စောင့်ပေးမယ်
            # Data မလာရင်တောင် ချက်ချင်းမဖြတ်ဘူး၊ လာမလားဆိုပြီး သည်းခံစောင့်မယ်
            frame = await asyncio.wait_for(self.frame_queue.get(), timeout=0.80)
            
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            # 3. 🛡️ Adaptive Silence (Network Drop)
            # 0.75s စောင့်လို့မှ မလာရင်တော့ Silence ထည့်မယ်
            # Priming ကို Reset မလုပ်ဘူး (Continuous Conversation မို့လို့)
            frame = self._get_silence_frame()

        # Apply Timestamp
        frame.pts = self.pts
        frame.time_base = Fraction(1, self.out_sample_rate)
        self.pts += self.SAMPLES_PER_FRAME
        return frame


class JarvisSession:
    def __init__(self):
        self.api_key = key_manager.get_next_key()
        self.url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={self.api_key}"
        self.memory = MemorySystem()
        self.gemini_ws = None
        self.audio_out_track = GeminiAudioTrack()

    async def connect_gemini(self):
        try:
            self.gemini_ws = await websockets.connect(self.url, ping_interval=20, ping_timeout=10)
            logger.info(f"✅ Gemini Connected")
            await self.send_setup_msg()
            asyncio.create_task(self.gemini_listener())
        except Exception as e:
            logger.error(f"Gemini Connection Failed: {e}")

    async def send_setup_msg(self):
        sys_instruction = self.memory.build_system_instruction()
        tools = mcp.get_gemini_tools()

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

    async def gemini_listener(self):
        try:
            async for raw_msg in self.gemini_ws:
                response = json.loads(raw_msg)
                if "serverContent" in response:
                    parts = response["serverContent"].get("modelTurn", {}).get("parts", [])
                    for part in parts:
                        if "inlineData" in part:
                            self.audio_out_track.add_audio_chunk(part["inlineData"]["data"])
                            
                if "toolCall" in response:
                    asyncio.create_task(self.handle_tool_call(response["toolCall"]))
        except Exception as e:
            logger.error(f"Gemini Listener Error: {e}")

    async def handle_tool_call(self, tool_call_data):
        function_calls = tool_call_data.get("functionCalls", [])
        function_responses = []
        for call in function_calls:
            name = call["name"]
            args = call["args"]
            call_id = call["id"]
            logger.info(f"[Tool] 🛠️ Executing: {name}")
            result = await mcp.execute(name, args)
            function_responses.append({
                "name": name, "response": {"result": result}, "id": call_id
            })

        if function_responses:
            await self.gemini_ws.send(json.dumps({
                "toolResponse": {"functionResponses": function_responses}
            }))

    async def send_audio_to_gemini(self, pcm_bytes):
        if self.gemini_ws:
            try:
                msg = {
                    "realtime_input": {
                        "media_chunks": [{
                            "data": base64.b64encode(pcm_bytes).decode('utf-8'),
                            "mime_type": "audio/pcm"
                        }]
                    }
                }
                await self.gemini_ws.send(json.dumps(msg))
            except: pass

async def create_webrtc_session(pc: RTCPeerConnection, offer: RTCSessionDescription):
    session = JarvisSession()
    await session.connect_gemini()
    pc.addTrack(session.audio_out_track)

    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            logger.info("🎤 User Audio Connected.")
            # 🔥 INPUT ENABLED
            asyncio.create_task(process_input_stream(track, session))

async def process_input_stream(track, session):
    """
    Reads WebRTC input (Opus/48k) -> Resamples to 16k -> Sends to Gemini
    """
    resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
    
    while True:
        try:
            frame = await track.recv()
            resampled_frames = resampler.resample(frame)
            pcm_bytes = b"".join([f.to_ndarray().tobytes() for f in resampled_frames])
            await session.send_audio_to_gemini(pcm_bytes)
        except Exception as e:
            # logger.error(f"Input Error: {e}")
            break