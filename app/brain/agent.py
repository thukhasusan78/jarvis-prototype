import base64
import json
import asyncio
from google import genai
from google.genai import types
from app.core.config import Config
from app.brain.memory import MemorySystem
from app.core.key_manager import key_manager
from app.core.shared_state import state 

# 🔥 IMPORT PROMPTS
from app.brain.prompts import (
    get_router_prompt, 
    get_news_agent_prompt, 
    get_chat_agent_prompt
)

memory = MemorySystem()

# =======================================================
# ⚙️ HELPER: JSON CLEANER & EMBEDDING
# =======================================================
def clean_json_text(text: str) -> str:
    if not text: return "{}"
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    elif text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text.strip()

async def get_embedding(text: str):
    """စာသားကို နံပါတ် (Vector) ပြောင်းပေးသော စနစ် (Non-Blocking)"""
    try:
        current_key = key_manager.get_next_key()
        client = genai.Client(api_key=current_key)
        
        # 🔥 FIX 1: Run in Thread to prevent stuttering
        result = await asyncio.to_thread(
            client.models.embed_content,
            model="models/text-embedding-004",
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[Embedding Error] {e}")
        return None

# =======================================================
# ⚡ ROUTER LAYER
# =======================================================
async def route_request(text: str):
    try:
        current_key = key_manager.get_next_key()
        client = genai.Client(api_key=current_key)
        
        # 🔥 FIX 2: Run in Thread
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=f"User Input: '{text}'",
            config=types.GenerateContentConfig(
                system_instruction=get_router_prompt(),
                temperature=0.0
            )
        )
        
        decision = response.text.strip() if response.text else "CHAT_AGENT"
        print(f"[Router] 🤖 Route Selected: {decision}")
        return decision
    except:
        return "CHAT_AGENT"

# =======================================================
# 🧠 SUBCONSCIOUS LAYER (AI VALIDATOR UPGRADE)
# =======================================================
async def extract_and_save_memory(user_text: str):
    # print(f"[Brain DEBUG] 🧠 Scanning Memory for: '{user_text}'")
    
    try:
        current_key = key_manager.get_next_key()
        client = genai.Client(api_key=current_key) 

        # Step 1: Extract Fact
        analysis_prompt = f"""
        Analyze this text: "{user_text}"
        Check if the user mentioned any Personal Fact, Preference, Plan, or Relationship info.
        
        ⛔ NEGATIVE CONSTRAINTS (DO NOT SAVE):
        - Do NOT save questions.
        - Do NOT save commands.
        - Do NOT save casual chat.
        
        CORE INSTRUCTION:
        1. Extract the fact.
        2. Categorize it (preference/fact/plan).
        3. GENERATE 3 SMART TAGS (keywords) as a JSON Array.
        
        OUTPUT ONLY JSON format:
        {{ "found": true, "category": "fact", "content": "...", "tags": [...] }}
        """

        # 🔥 FIX 3: Run in Thread
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=Config.MODEL_NAME,
            contents=analysis_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        if not response.text: return False
        result = json.loads(clean_json_text(response.text))

        if result.get("found") is True:
            content = result.get("content")
            category = result.get("category")
            tags = result.get("tags")
            
            # --- 🔥 ADVANCED DUPLICATE CHECK (AI JUDGE) ---
            print(f"[Brain] 🧐 Checking for logic redundancy...")
            
            vector = await get_embedding(content)
            
            if vector:
                # 1. Search Broadly
                similar_memories = memory.search_similar_memories(vector, threshold=0.65)
                
                if similar_memories:
                    existing_facts = [m['content'] for m in similar_memories]
                    print(f"[Brain] Found similar memories: {existing_facts}")

                    # 2. Ask Gemini: "Does this new fact add value?"
                    validation_prompt = f"""
                    I need to decide whether to save a NEW memory to the database.
                    
                    NEW MEMORY: "{content}"
                    EXISTING RELATED MEMORIES: {json.dumps(existing_facts)}
                    
                    RULE:
                    - If the NEW memory is already implied or covered by EXISTING memories, return "redundant": true.
                    - Example: If existing is "Wife name is Sarah", and new is "I have a wife", it is REDUNDANT.
                    - If the NEW memory adds specific details not present before, return "redundant": false.
                    
                    OUTPUT JSON ONLY: {{ "redundant": true/false, "reason": "short explanation" }}
                    """
                    
                    # 🔥 FIX 4: Run in Thread
                    val_resp = await asyncio.to_thread(
                        client.models.generate_content,
                        model="gemini-2.5-flash",
                        contents=validation_prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    
                    val_result = json.loads(clean_json_text(val_resp.text))
                    
                    if val_result.get("redundant") is True:
                        print(f"[Brain] 🗑️ Skipped Redundant Info: {val_result.get('reason')}")
                        return False # Stop Saving
            
            # 3. If passed AI Check, SAVE IT
            if tags is None: tags = []
            elif isinstance(tags, str): tags = [t.strip() for t in tags.split(",")]
            
            memory.save_core_memory(content, category, tags, embedding=vector) 
            return True

    except Exception as e:
        print(f"[Memory Extraction Error] {e}")
    
    return False

# =======================================================
# 🗣️ MAIN CONSCIOUS LAYER
# =======================================================
async def ask_jarvis(text_input: str, image_data: str = None):
    try:
        current_key = key_manager.get_next_key()
        client = genai.Client(api_key=current_key) 

        memory.update_chat_history("user", text_input)

        # Parallel Execution
        agent_task = asyncio.create_task(route_request(text_input))
        
        # 🔥 FIX: Memory ကို မစောင့်တော့ပါ (Fire & Forget)
        # Background မှာ သူ့ဘာသာသူ အလုပ်လုပ်နေပါလိမ့်မယ်၊ Latency မထိခိုက်တော့ပါဘူး
        asyncio.create_task(extract_and_save_memory(text_input))
        
        # Router (Agent ရွေးတာ) တစ်ခုကိုပဲ စောင့်ပါမယ် (ဒါက အရမ်းမြန်ပါတယ်)
        agent_name = await agent_task
        
        # Memory ကို မစောင့်တဲ့အတွက် "မှတ်လိုက်ပါပြီ" ဆိုတဲ့ Notice ကို ပိတ်ထားလိုက်ပါမယ်
        has_memorized = False

        if agent_name == "NEWS_AGENT":
            selected_prompt = get_news_agent_prompt
        else:
            selected_prompt = get_chat_agent_prompt

        sys_instruct = memory.build_system_instruction(selected_prompt)

        contents_list = []
        if image_data:
            try:
                img_str = image_data.split("base64,")[1] if "base64," in image_data else image_data
                img_bytes = base64.b64decode(img_str)
                contents_list.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
            except: pass

        location_context = ""
        if state.current_gps:
            location_context = f"\n[SYSTEM DATA: GPS {state.current_gps}]"

        chat_hist = "\n".join(memory.get_chat_history())
        final_prompt = f"{location_context}\nPREVIOUS CHAT:\n{chat_hist}\nCURRENT INPUT:\n{text_input}"
        contents_list.append(final_prompt)

        # 🔥 FIX 5: Critical Fix for Latency/Stuttering
        response = await asyncio.to_thread(
            client.models.generate_content,
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