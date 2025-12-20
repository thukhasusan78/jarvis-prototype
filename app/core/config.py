import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Basic Settings ---
    GEMINI_KEYS_LIST = os.getenv("GEMINI_KEYS_LIST", "").split(",")
    # Key Rotation logic ကို key_manager မှာထားတဲ့အတွက် ဒီမှာ list ပဲယူမယ်
    
    # --- Brain ---
    MODEL_NAME = "gemini-2.5-flash" # Or 2.5 as you used

    LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

    TTS_VOICE = "Enceladus" # Or Enceladus
    
    # --- Audio Specs ---
    # WebRTC standard is 48kHz, but Models usually want 16kHz
    WEBRTC_RATE = 48000
    MODEL_RATE = 16000
    CHANNELS = 1
    chunk = 1280 # Processing Chunk Size

    # --- Feature Flags ---
    ENABLE_WAKEWORD = True
    ENABLE_SPEAKER_ID = True # အသံခွဲခြားစနစ်
    
    # --- Paths ---
    BASE_DIR = os.getcwd()
    OWNER_VOICE_PATH = os.path.join(BASE_DIR, "owner_voice.npy") # အစ်ကို့အသံ မှတ်ထားမယ့်ဖိုင်

    if not GEMINI_KEYS_LIST:
        raise ValueError("API Key မရှိပါ။ .env ဖိုင်ကို စစ်ဆေးပါ။")
