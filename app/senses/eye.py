import requests
import time

# Vision Service (DeepFace API) လိပ်စာ
VISION_API_URL = "http://127.0.0.1:8001/verify"

def verify_image_data(image_bytes):
    """
    Frontend မှ ပို့လိုက်သော ပုံကို Vision Service သို့ ပို့၍ စစ်ဆေးခြင်း။
    Retry Logic ပါဝင်သည်။
    """
    print("[Vision] Receiving image data... Connecting to Neural Net...")

    session_proxies = { "http": None, "https": None }
    
    # --- RETRY CONFIG ---
    max_retries = 3
    attempt = 0
    
    while attempt < max_retries:
        try:
            attempt += 1
            print(f"[Vision] Authentication Attempt {attempt}/{max_retries}...")

            files = {'file': ('capture.jpg', image_bytes, 'image/jpeg')}
            
            # Timeout ကို 60 seconds ထိ တိုးပေးလိုက်ပါ (Model Load ချိန်ပါ cover ဖြစ်အောင်)
            response = requests.post(
                VISION_API_URL, 
                files=files, 
                proxies=session_proxies,
                timeout=60 
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("match", False):
                    score = result.get("score", 0)
                    print(f"[Vision] ✅ IDENTITY CONFIRMED (Similarity: {score:.2f})")
                    return True
                else:
                    print(f"[Vision] ❌ Face detected but not matched.")
                    return False # လူမှားနေရင်တော့ ထပ်မစမ်းတော့ဘူး၊ တန်းငြင်းမယ်
            else:
                print(f"[Vision Error] API Status: {response.status_code}")

        except requests.exceptions.ReadTimeout:
            print("[Vision Warning] Server is slow (Model Loading...). Retrying...")
        except requests.exceptions.ConnectionError:
            print("[Vision Warning] Cannot connect to Vision Service. Is it running?")
        except Exception as e:
            print(f"[Vision Error] {e}")

        # မအောင်မြင်ရင် ခဏနားမယ်
        if attempt < max_retries:
            time.sleep(2)

    print("[Vision] Authentication Timed Out.")
    return False