class SharedState:
    def __init__(self):
        # Telegram Chat ID (Bot က ပြန်ပို့ဖို့)
        self.telegram_chat_id = None
        
        # Basic Location String ("lat,lng") - အရင် Tools တွေ အလုပ်ဆက်လုပ်နိုင်အောင် ထားထားခြင်း
        self.current_gps = None
        
        # 🔥 New Metadata Storage
        # ဒီထဲမှာ { 'accuracy': 15.5, 'timestamp': 17123456789 } ဆိုပြီး သိမ်းမယ်
        # Accuracy မကောင်းရင် (သို့) ကြာနေပြီဆိုရင် location tool က ငြင်းပယ်ဖို့အတွက် သုံးမယ်
        self.gps_metadata = {}

state = SharedState()