import os
import numpy as np
import logging
from pathlib import Path
from resemblyzer import VoiceEncoder, preprocess_wav

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("ENROLLMENT")

def enroll_voices(samples_folder="owner_samples", output_file="owner_voice.npy"):
    """
    Folder ထဲရှိသမျှ အသံဖိုင်များကို ဖတ်ပြီး Multi-Embedding Matrix ထုတ်ပေးခြင်း။
    (Average မလုပ်ပါ၊ တစ်ခုချင်းစီ သီးသန့်မှတ်ပါသည်)
    """
    folder_path = Path(samples_folder)
    
    # 1. Folder စစ်ခြင်း
    if not folder_path.exists():
        logger.warning(f"⚠️ Folder '{samples_folder}' မရှိပါ။ အသစ်ဆောက်ပေးနေသည်...")
        folder_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"👉 '{samples_folder}' folder ထဲတွင် အသံဖိုင်များ (.wav, .mp3) အကုန်ထည့်ပြီး ပြန် Run ပါ။")
        return

    # 2. Encoder Load လုပ်ခြင်း
    logger.info("⏳ Loading Neural Net (Resemblyzer)...")
    encoder = VoiceEncoder()
    
    embeddings = []
    files_processed = 0
    supported_extensions = {".wav", ".mp3", ".m4a", ".flac"}
    
    logger.info("🎤 Processing audio files individually...")
    
    # 3. ဖိုင်တစ်ခုချင်းစီကို Loop ပတ်ပြီး Embedding ထုတ်ခြင်း
    for file_path in folder_path.iterdir():
        if file_path.suffix.lower() in supported_extensions:
            try:
                # Preprocess & Embed
                wav = preprocess_wav(file_path)
                embed = encoder.embed_utterance(wav)
                embeddings.append(embed) # List ထဲထည့် (မပေါင်းပါ)
                
                logger.info(f"✅ Processed: {file_path.name}")
                files_processed += 1
            except Exception as e:
                logger.error(f"❌ Failed to process {file_path.name}: {e}")

    # 4. Save to .npy as a Matrix (N x 256)
    if files_processed > 0:
        embeddings_matrix = np.array(embeddings)
        np.save(output_file, embeddings_matrix)
        
        logger.info(f"\n🎉 SUCCESS! {files_processed} voice styles enrolled.")
        logger.info(f"💾 Saved to: {output_file}")
        logger.info(f"📊 Data Shape: {embeddings_matrix.shape} (Voices x Features)")
        logger.info("👉 System will now check against ALL these styles simultaneously.")
    else:
        logger.warning("⚠️ No valid audio files found. Please add files to 'owner_samples' folder.")

if __name__ == "__main__":
    enroll_voices()