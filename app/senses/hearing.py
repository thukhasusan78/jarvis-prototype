import numpy as np
import logging
import os
from pathlib import Path
from resemblyzer import VoiceEncoder, preprocess_wav

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JARVIS_HEARING")

class Ear:
    def __init__(self, owner_voice_path: str = None):
        logger.info("[Hearing] 👂 Loading Neural Net (Resemblyzer)...")
        self.encoder = VoiceEncoder(verbose=0) 
        self.owner_embeds = None 
        # Threshold ကို 0.65 - 0.7 လောက်ထားပါ
        # Tone မျိုးစုံရှိလို့ အရင်ကထက် ပိုတိကျသွားပါပြီ
        self.SIMILARITY_THRESHOLD = 0.4  
        
        if owner_voice_path:
            self.load_owner_voice(owner_voice_path)

    def load_owner_voice(self, path_str):
        path = Path(path_str)
        if not path.exists():
            return

        try:
            if path.suffix == ".npy":
                data = np.load(path)
                # Matrix (N, 256) ဖြစ်မဖြစ် စစ်ပြီး Load ပါ
                if data.ndim == 1:
                    self.owner_embeds = np.expand_dims(data, axis=0)
                else:
                    self.owner_embeds = data
                
                logger.info(f"[Hearing] ✅ Loaded {self.owner_embeds.shape[0]} Voice Styles.")
            else:
                wav = preprocess_wav(path)
                embed = self.encoder.embed_utterance(wav)
                self.owner_embeds = np.expand_dims(embed, axis=0)
                
        except Exception as e:
            logger.error(f"[Hearing] Load Error: {e}")

    def identify_speaker(self, pcm_data):
        """
        Input: Raw PCM bytes
        Returns: (is_owner: bool, confidence: float)
        """
        if self.owner_embeds is None:
            return True, 1.0 

        try:
            # PCM -> Float32 Normalization
            audio_np = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            if len(audio_np) < 3200: return False, 0.0 # Ignore Noise

            # Embed Current Input
            current_embed = self.encoder.embed_utterance(audio_np)
            
            # 🔥 KEYRING LOGIC: Check against ALL enrolled styles
            # np.inner returns an array of scores (e.g., [0.4, 0.85, 0.3])
            all_scores = np.inner(self.owner_embeds, current_embed)
            
            # 🔥 MAX LOGIC: Take the HIGHEST score
            # (Average မယူပါ၊ အများဆုံးတူတာ တစ်ခုရှိရင် လက်ခံသည်)
            best_score = float(np.max(all_scores))
            
            is_owner = best_score > self.SIMILARITY_THRESHOLD
            return is_owner, best_score
            
        except Exception as e:
            logger.warning(f"[Hearing] ID Error: {e}")
            return False, 0.0

if __name__ == "__main__":
    ear = Ear("owner_voice.npy")