import itertools
from app.core.config import Config

class KeyManager:
    def __init__(self):
        # .env ထဲမှာ KEY တွေကို ကော်မာ (,) ခံပြီး ရေးထားရမယ်
        # ဥပမာ: GEMINI_KEYS="key1,key2,key3,..."
        self.keys = Config.GEMINI_KEYS_LIST 
        self.key_cycle = itertools.cycle(self.keys) # သံသရာလည်နေအောင် လုပ်တာ

        # 🔥 ဒီစာကြောင်းလေး ထပ်ထည့်လိုက်ပါ (Debug လုပ်ဖို့)
        print(f"\n[SYSTEM] 🔑 Key Manager Loaded: {len(self.keys)} Keys ready to rotate.\n")

    def get_next_key(self):
        """နောက်ထပ် သုံးရမယ့် Key ကို ထုတ်ပေးမယ်"""
        new_key = next(self.key_cycle)
        # print(f"[System] 🔑 Switching to API Key: ...{new_key[-4:]}")
        return new_key

# Global Instance
key_manager = KeyManager()