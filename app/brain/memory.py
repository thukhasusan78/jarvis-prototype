import os
import time
import json
from datetime import datetime
import pytz
from upstash_redis import Redis
from supabase import create_client, Client
from app.brain.prompts import get_chat_agent_prompt

# .env Loading
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
REDIS_URL = os.environ.get("REDIS_URL")
REDIS_TOKEN = os.environ.get("REDIS_TOKEN")

class MemorySystem:
    def __init__(self):
        # 1. Redis Connection
        try:
            self.redis = Redis(url=REDIS_URL, token=REDIS_TOKEN)
            self.redis.set("ping", "pong")
            print("[Memory] ✅ Redis Cloud Active.")
        except Exception as e:
            print(f"[Memory] ⚠️ Redis Connection Failed: {e}")
            self.redis = None

        # 2. Supabase Connection
        try:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            self.supabase.table("users").select("role").limit(1).execute()
            print("[Memory] ✅ Supabase Neural Net Active (Ping Success).")
        except Exception as e:
            print(f"[Memory] ⚠️ Supabase Connection Failed: {e}")
            self.supabase = None

    # --- HISTORY (Redis) ---
    def update_chat_history(self, role, text):
        if not self.redis: return
        try:
            msg = f"{role}: {text}"
            self.redis.rpush("jarvis_chat_buffer", msg)
            self.redis.ltrim("jarvis_chat_buffer", -30, -1) 
        except: pass

    def get_chat_history(self):
        if not self.redis: return []
        try:
            raw = self.redis.lrange("jarvis_chat_buffer", 0, -1)
            return [msg.decode('utf-8') if isinstance(msg, bytes) else msg for msg in raw]
        except: return []

    # --- DATABASE FETCHING ---
    def get_user_profile(self):
        if not self.supabase: return {}
        try:
            res = self.supabase.table("users").select("*").eq("role", "master").execute()
            return res.data[0] if res.data else {}
        except: return {}

    def get_active_directives(self):
        if not self.supabase: return []
        try:
            res = self.supabase.table("directives").select("protocol_name, description").eq("is_active", True).execute()
            return res.data if res.data else []
        except: return []

    def get_core_memories(self):
        if not self.supabase: return []
        try:
            res = self.supabase.table("memories").select("category, content").gte("importance_level", 7).execute()
            return res.data if res.data else []
        except: return []

    # --- VECTOR SEARCH (NEW FEATURE) ---
    def search_similar_memories(self, embedding_vector, threshold=0.85):
        """
        Database ထဲမှာ အဓိပ္ပါယ်ဆင်တူတဲ့ Memory ရှိမရှိ Vector နဲ့ ရှာမယ်။
        threshold 0.85 ဆိုတာ ၈၅% လောက် အဓိပ္ပါယ်တူမှ ဖော်ပြမယ်လို့ ဆိုလိုတာပါ။
        """
        if not self.supabase: return []
        try:
            params = {
                "query_embedding": embedding_vector,
                "match_threshold": threshold,
                "match_count": 1 # အတူဆုံး တစ်ခုရှိရင် တော်ပြီ (Duplicate စစ်ဖို့မို့လို့)
            }
            # Supabase RPC (Remote Procedure Call) to verify
            res = self.supabase.rpc("match_memories", params).execute()
            return res.data if res.data else []
        except Exception as e:
            print(f"[Vector Search Error] {e}")
            return []

    # --- CONTEXT BUILDER ---
    def build_system_instruction(self, selected_prompt_func=None):
        if selected_prompt_func:
            base_prompt = selected_prompt_func()
        else:
            base_prompt = get_chat_agent_prompt()
        
        user = self.get_user_profile()
        directives = self.get_active_directives()
        memories = self.get_core_memories()

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

        protocol_str = "\n".join([f"- {d['protocol_name']}: {d['description']}" for d in directives])
        memory_str = "\n".join([f"- [{m['category'].upper()}] {m['content']}" for m in memories])

        try:
            tz_MM = pytz.timezone('Asia/Yangon') 
            now = datetime.now(tz_MM)
            current_time = now.strftime("%I:%M %p")
            current_date = now.strftime("%Y-%m-%d")
        except:
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
        """
        return full_context

    # --- SAVE WITH VECTOR ---
    def save_core_memory(self, content, category="user_defined", tags=None, embedding=None):
        if not self.supabase: return False 
        try:
            safe_tags = []
            if isinstance(tags, list): safe_tags = [str(t) for t in tags if t]
            elif isinstance(tags, str): safe_tags = [t.strip() for t in tags.split(",") if t.strip()]

            data = {
                "category": category,
                "content": content,
                "importance_level": 10,
                "tags": safe_tags
            }
            
            # 🔥 Vector ပါလာရင် ထည့်သိမ်းမယ်
            if embedding:
                data["embedding"] = embedding

            self.supabase.table("memories").insert(data).execute()
            print(f"[Memory] 💾 Saved: {content} | Vector: {'✅' if embedding else '❌'}")
            return True
        except Exception as e:
            print(f"[Memory Save Error] {e}")
            return False