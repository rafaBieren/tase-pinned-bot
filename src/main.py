import os
import asyncio

# Work around yfinance's optional curl_cffi transport causing attribute errors in some environments
# This MUST be set before any yfinance import (which happens in indices module)
os.environ["YF_USE_CURL_CFFI"] = "false"
os.environ["YF_DISABLE_CURL_CFFI"] = "true"

from telegram import Bot
from dotenv import load_dotenv
from telegram.error import InvalidToken, TimedOut
from telegram.request import HTTPXRequest

from settings import settings
from indices import fetch_all
from formatter import build_message


async def main() -> None:
    """Send a single indices update message at startup and exit."""
    # Ensure .env values override any existing environment variables
    load_dotenv(override=True)

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT") or "").strip()

    if not token:
        print("❌ Missing TELEGRAM_BOT_TOKEN in environment or .env")
        print("Please create a .env file with your bot token. See README.md for details.")
        return
    if not chat_id:
        print("❌ Missing TELEGRAM_CHAT in environment or .env")
        print("Please create a .env file with your chat ID. See README.md for details.")
        return

    # Use more generous HTTP timeouts to avoid spurious startup failures
    request = HTTPXRequest(read_timeout=30.0, write_timeout=30.0, connect_timeout=10.0, pool_timeout=10.0)
    bot = Bot(token=token, request=request)

    # Validate token early with getMe for a clearer error
    try:
        await bot.get_me()
    except InvalidToken:
        raise SystemExit(
            "Invalid TELEGRAM_BOT_TOKEN (Unauthorized). Check the token with @BotFather and update .env."
        )
    except TimedOut:
        # Network is slow or blocked; proceed and let send attempt retries handle it
        pass

    # Build a message for the configured indices (skipping ones with missing data)
    indices_map = settings.indices_map()
    quotes = fetch_all(indices_map)

    # If everything failed (e.g., data source outage), send a friendly fallback text
    if not quotes:
        text = "לא הצלחתי להביא כרגע נתונים למדדים. נסו שוב מאוחר יותר."
    else:
        text = build_message(quotes=quotes, tz=settings.tz)

    print(f"📊 Generated message with {len(quotes)} indices")
    print(f"📝 Message preview: {text[:100]}...")

    # Try to send with simple backoff to tolerate transient Telegram timeouts
    delays = [0, 2, 4]
    for attempt in range(3):
        try:
            await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
            print("✅ Message sent successfully to Telegram!")
            break
        except TimedOut:
            if attempt < 2:
                print(f"⏳ Timeout, retrying in {delays[attempt + 1]} seconds...")
                await asyncio.sleep(delays[attempt + 1])
                continue
            print("❌ Failed to send message after retries")
            return


if __name__ == "__main__":
    asyncio.run(main())
