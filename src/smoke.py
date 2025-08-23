# src/smoke.py
import os, asyncio
from dotenv import load_dotenv
from telegram import Bot

# function to check if the environment variable is set
def must(var: str) -> str:
    v = os.getenv(var)
    if not v:
        raise RuntimeError(f"Missing {var} in .env")
    return v

# main function to send a message to the telegram chat
async def main():
    load_dotenv()
    token = must("TELEGRAM_BOT_TOKEN")
    chat = must("TELEGRAM_CHAT")
    bot = Bot(token=token)

    me = await bot.get_me()
    print("Bot OK:", me.username)

    # שליחת הודעת טסט לערוץ (מחק אחרי):
    msg = await bot.send_message(chat_id=chat, text="בוט מחובר ✅ (טסט חד־פעמי)")
    print("Sent message id:", msg.message_id)

if __name__ == "__main__":
    asyncio.run(main())
