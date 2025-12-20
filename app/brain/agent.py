import base64
import json
import asyncio
from google import genai
from google.genai import types
from app.core.config import Config
from app.brain.memory import MemorySystem
from app.core.key_manager import key_manager
# 🔥 Shared State Import (New Feature)
from app.core.shared_state import state 

# Setup (Global Client မသုံးတော့ဘူး)
memory = MemorySystem()

# --- 🔥 SUBCONSCIOUS LAYER (မသိစိတ်) ---
async def extract_and_save_memory(user_text: str):
    """
    User ပြောတဲ့ စကားထဲမှာ Fact/Preference ပါမပါ စစ်ပြီး
    ပါခဲ့ရင် Database ထဲ အလိုလို သိမ်းမယ့် Function
    """
    try:
        # 🔥 Key အသစ်တောင်းမယ်
        current_key = key_manager.get_next_key()
        client = genai.Client(api_key=current_key) 

        analysis_prompt = f"""
        Analyze this text: "{user_text}"
        
        Check if the user mentioned any:
        1. Personal Fact (Name, Age, Job, Health)
        2. Preference (Likes, Dislikes, Favorites)
        3. Plan/Goal (Project, Travel, Future)
        4. Important Relationship info
        
        Ignore casual greetings like "Hello", "How are you".
        
        OUTPUT ONLY JSON format:
        {{
            "found": true/false,
            "category": "preference/fact/plan",
            "content": "Extract the specific fact concisely"
        }}
        """

        response = client.models.generate_content(
            model=Config.MODEL_NAME,
            contents=analysis_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        result = json.loads(response.text)

        if result.get("found") is True:
            content = result.get("content")
            category = result.get("category")
            memory.save_core_memory(content) 
            print(f"[Brain] 🧠 Auto-Memory Stored: [{category}] {content}")
            return True

    except Exception as e:
        print(f"[Memory Analysis Error] {e}")
    
    return False

# --- 🔥 MAIN CONSCIOUS LAYER (အသိစိတ်) ---
async def ask_jarvis(text_input: str, image_data: str = None):
    try:
        # 🔥 Key အသစ်တောင်းမယ် (Main Brain အတွက်)
        current_key = key_manager.get_next_key()
        client = genai.Client(api_key=current_key) 

        # 1. User ပြောတာကို Short-term History ထဲထည့်မယ်
        memory.update_chat_history("user", text_input)

        # 2. Auto-Memory Analysis
        has_memorized = await extract_and_save_memory(text_input)
        
        # ပုံပါလာရင် System Log ထဲထည့်မယ်
        if image_data:
            memory.update_chat_history("system", "[User uploaded an image]")

        # 3. System Instruction တည်ဆောက်မယ်
        sys_instruct = memory.build_system_instruction()

        # 4. History ပြန်ခေါ်မယ်
        history_msgs = memory.get_chat_history()
        context_str = "\n".join(history_msgs)
        
        # 5. Gemini ဆီပို့ဖို့ ပြင်ဆင်မယ်
        contents_list = []
        
        # Vision Logic
        if image_data:
            print("[Brain] 👀 Vision Active.")
            if "base64," in image_data:
                image_data = image_data.split("base64,")[1]
            image_bytes = base64.b64decode(image_data)
            contents_list.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

        # 🔥 LOCATION CONTEXT INJECTION (NEW FEATURE) 🔥
        location_context = ""
        if state.current_gps:
            location_context = f"""
[SYSTEM DATA: User's Current GPS Location: {state.current_gps}]
(If user asks about location, navigation, or "Where am I?", use this GPS data. Do not ask for location again.)
"""

        # Final Prompt
        memory_notice = ""
        if has_memorized:
            memory_notice = "\n[SYSTEM NOTE: You just automatically saved a new fact from this input to your long-term memory. Acknowledge it naturally if relevant.]"

        final_prompt = f"""
        {location_context}
        
        PREVIOUS CHAT:
        {context_str}
        
        CURRENT INPUT:
        {text_input}
        {memory_notice}
        """
        contents_list.append(final_prompt)

        # 6. Response Generation
        response = client.models.generate_content(
            model=Config.MODEL_NAME,
            contents=contents_list,
            config=types.GenerateContentConfig(
                system_instruction=sys_instruct,
                temperature=0.7
            )
        )

        reply_text = response.text
        memory.update_chat_history("model", reply_text)

        return reply_text

    except Exception as e:
        print(f"[Brain Error] {e}")
        return "Sir, I am experiencing a cognitive glitch."