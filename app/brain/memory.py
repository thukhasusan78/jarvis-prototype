import os
import time
import json
from datetime import datetime # 🔥 ဒါလေးထည့်
import pytz
from upstash_redis import Redis
from supabase import create_client, Client
from app.brain.prompts import get_system_prompt

# .env Loading
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
REDIS_URL = os.environ.get("REDIS_URL")
REDIS_TOKEN = os.environ.get("REDIS_TOKEN")

class MemorySystem:
    def __init__(self):
        # 1. Redis Connection (Short-term)
        try:
            self.redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)
            print("[Memory] ✅ Redis Cloud Active.")
        except:
            print("[Memory] ⚠️ Redis Connection Failed.")
            self.redis = None

        # 2. Supabase Connection (Long-term)
        try:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("[Memory] ✅ Supabase Neural Net Active.")
        except:
            print("[Memory] ⚠️ Supabase Connection Failed.")
            self.supabase = None

    # --- HISTORY (Redis) ---
    def update_chat_history(self, role, text):
        if not self.redis: return
        try:
            msg = f"{role}: {text}"
            self.redis.rpush("jarvis_chat_buffer", msg)
            self.redis.ltrim("jarvis_chat_buffer", -20, -1)
            self.redis.expire("jarvis_chat_buffer", 3600)
        except: pass

    def get_chat_history(self):
        if not self.redis: return []
        try:
            raw = self.redis.lrange("jarvis_chat_buffer", 0, -1)
            return [msg.decode('utf-8') if isinstance(msg, bytes) else msg for msg in raw]
        except: return []

    # --- DATABASE FETCHING (The Full Read) ---
    
    def get_user_profile(self):
        """Users Table: သခင်ရဲ့ အချက်အလက်အကုန် (Biometrics + Prefs)"""
        if not self.supabase: return {}
        try:
            res = self.supabase.table("users").select("*").eq("role", "master").execute()
            return res.data[0] if res.data else {}
        except: return {}

    def get_active_directives(self):
        """Directives Table: လိုက်နာရမယ့် Protocol များ"""
        if not self.supabase: return []
        try:
            # Active ဖြစ်နေတဲ့ Protocol တွေကိုပဲ ယူမယ်
            res = self.supabase.table("directives").select("protocol_name, description").eq("is_active", True).execute()
            return res.data if res.data else []
        except: return []

    def get_core_memories(self):
        """Memories Table: အရေးကြီး မှတ်ဉာဏ်များ"""
        if not self.supabase: return []
        try:
            # Importance Level 7 နှင့်အထက် အရေးကြီးတာတွေကိုပဲ ဆွဲမယ် (Token မပွအောင်)
            res = self.supabase.table("memories").select("category, content").gte("importance_level", 7).execute()
            return res.data if res.data else []
        except: return []

    # --- THE FINAL PROMPT CONSTRUCTION ---
    def build_system_instruction(self):
        """
        Database တစ်ခုလုံးကို ပေါင်းစပ်ပြီး JARVIS ၏ 'စိတ်' ကို ဖန်တီးခြင်း
        """
        base_prompt = get_system_prompt()
        
        # 1. Fetch ALL Data
        user = self.get_user_profile()
        directives = self.get_active_directives()
        memories = self.get_core_memories()

        # 2. Format User Data (Detailed)
        bio_json = user.get('biometrics', {})
        pref_json = user.get('preferences', {})
        
        user_context = f"""
        [USER PROFILE - ACCESS LEVEL 10]
        - Name: {user.get('name', 'Sir')}
        - Bio: {user.get('bio', 'N/A')}
        - Biometrics: Height {bio_json.get('height')}, Weight {bio_json.get('weight')}
        - Relationship: {pref_json.get('relationship_status')}
        - Favorites: {', '.join(pref_json.get('favorite_movies', []))}
        """

        # 3. Format Directives (Protocols)
        protocol_str = "\n".join([f"- {d['protocol_name']}: {d['description']}" for d in directives])
        
        # 4. Format Memories (Past Knowledge)
        memory_str = "\n".join([f"- [{m['category'].upper()}] {m['content']}" for m in memories])

        # 5. Assemble the Ultimate Context
        # 🔥 TIME CORRECTION (ဒီအပိုင်းကို ကူးထည့်ပါ)
        try:
            tz_MM = pytz.timezone('Asia/Yangon') 
            now = datetime.now(tz_MM)
            current_time = now.strftime("%I:%M %p") # e.g., 01:15 AM
            current_date = now.strftime("%Y-%m-%d")
        except:
            # Error တက်ရင် စက်ထဲက အချိန်အတိုင်းပဲ ယူမယ်
            current_time = datetime.now().strftime("%I:%M %p")
            current_date = datetime.now().strftime("%Y-%m-%d")

        full_context = f"""
        {base_prompt}

        {user_context}

        [ACTIVE PROTOCOLS]
        {protocol_str}

        [CORE MEMORY BANK]
        {memory_str}

        [REAL-TIME SYSTEM DATA]
        - Location: Myanmar (Yangon Time)
        - Date: {current_date}
        - Current Time: {current_time} 
        
        (Note: Always answer based on this Myanmar time.)
        """
    
        return full_context

        # ... (အပေါ်က Code တွေ အကုန်ဒီအတိုင်းထားပါ)

    # 🔥 NEW FUNCTION: SAVE MEMORY 🔥
    def save_core_memory(self, content):
        """အရေးကြီးတာ မှတ်ခိုင်းရင် Database ထဲ ရေးထည့်မယ်"""
        if not self.supabase: return False
        try:
            data = {
                "category": "user_defined", # User ကိုယ်တိုင်မှတ်ခိုင်းတာ
                "content": content,
                "importance_level": 10      # အရေးကြီးဆုံးလို့ သတ်မှတ်မယ်
            }
            self.supabase.table("memories").insert(data).execute()
            print(f"[Memory] 💾 Saved to Database: {content}")
            return True
        except Exception as e:
            print(f"[Save Error] {e}")
            return False