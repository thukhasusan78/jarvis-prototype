import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from app.brain.agent import ask_jarvis 
# 🔥 Global State ကို Import လုပ်မယ် (GPS Update ဖို့)
from app.core.shared_state import state

# .env Load
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Chat ID ကို Log ထုတ်ကြည့်မယ် (Admin Check ဖို့)
    print(f"\n🔥🔥🔥 YOUR TELEGRAM ID: {user.id} 🔥🔥🔥\n")
    
    # Global State မှာ Chat ID သိမ်းထားမယ် (Bot ကပြန်ပို့ဖို့)
    state.telegram_chat_id = str(update.effective_chat.id)
    
    await update.message.reply_text(f"Systems Online. ID: {user.id} Configured.")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User က Location ပို့လိုက်ရင် ဒီ Function အလုပ်လုပ်မယ်
    """
    user_loc = update.message.location
    lat = user_loc.latitude
    lng = user_loc.longitude
    
    # 1. Update Global State
    state.current_gps = f"{lat},{lng}"
    state.telegram_chat_id = str(update.effective_chat.id)

    print(f"📍 GPS Updated via Telegram: {state.current_gps}")
    
    await update.message.reply_text("✅ GPS Updated! You can now ask for routes/directions.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Chat ID မရှိသေးရင် သိမ်းမယ်
    if not state.telegram_chat_id:
        state.telegram_chat_id = str(update.effective_chat.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # Brain ကို လှမ်းမေးမယ်
        response = await ask_jarvis(user_text)
        await update.message.reply_text(response)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text("Sir, I encountered a processing error.")

if __name__ == '__main__':
    if not TOKEN:
        print("Error: .env ထဲမှာ Token မရှိပါ")
        exit()

    print("🤖 JARVIS Telegram Protocol Started...")
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler('start', start))
    # 🔥 Location Handler အသစ်ထည့်ထားသည်
    app.add_handler(MessageHandler(filters.LOCATION, handle_location)) 
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    app.run_polling()