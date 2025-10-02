import os
import asyncio

# Work around yfinance's optional curl_cffi transport causing attribute errors in some environments
# This MUST be set before any yfinance import (which happens in indices module)
os.environ["YF_USE_CURL_CFFI"] = "false"
os.environ["YF_DISABLE_CURL_CFFI"] = "true"

from telegram import Bot
from dotenv import load_dotenv
from telegram.error import InvalidToken, TimedOut, BadRequest, Forbidden
from telegram.request import HTTPXRequest

from settings import settings
from indices import fetch_all
from formatter import build_message

UPDATE_INTERVAL_SEC = 300
SEND_RETRY_DELAYS = [0, 2, 4]
FALLBACK_TEXT = "\u05dc\u05d0 \u05d4\u05e6\u05dc\u05d7\u05ea\u05d9 \u05dc\u05d4\u05d1\u05d9\u05d0 \u05db\u05e8\u05d2\u05e2 \u05e0\u05ea\u05d5\u05e0\u05d9\u05dd \u05dc\u05de\u05d3\u05d3\u05d9\u05dd. \u05e0\u05e1\u05d5 \u05e9\u05d5\u05d1 \u05de\u05d0\u05d5\u05d7\u05e8 \u05d9\u05d5\u05ea\u05e8."


async def main() -> None:
    """Send indices update message and refresh it every 5 minutes."""
    # Ensure .env values override any existing environment variables
    load_dotenv(override=True)

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT") or "").strip()

    if not token:
        print("!! Missing TELEGRAM_BOT_TOKEN in environment or .env")
        print("Please create a .env file with your bot token. See README.md for details.")
        return
    if not chat_id:
        print("!! Missing TELEGRAM_CHAT in environment or .env")
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

    message_id = None
    last_text = None

    while True:
        indices_map = settings.indices_map()
        quotes = fetch_all(indices_map)

        if not quotes:
            text = FALLBACK_TEXT
        else:
            text = build_message(quotes=quotes, tz=settings.tz)

        print(f"[INFO] Generated message with {len(quotes)} indices")
        print(f"[INFO] Message preview: {text[:100]}...")

        if message_id is None:
            send_success = False
            for attempt in range(len(SEND_RETRY_DELAYS)):
                try:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="MarkdownV2",
                        disable_web_page_preview=True,
                    )
                    message_id = msg.message_id
                    last_text = text
                    try:
                        await bot.pin_chat_message(
                            chat_id=chat_id,
                            message_id=message_id,
                            disable_notification=True,
                        )
                        print("[OK] Message pinned successfully.")
                    except Forbidden as exc:
                        print(f"[WARN] Bot lacks rights to pin message: {exc}")
                    except BadRequest as exc:
                        print(f"[WARN] Failed to pin message: {exc}")
                    except TimedOut:
                        print("[WARN] Pin request timed out; will retry on next cycle.")
                    send_success = True
                    print("[OK] Message sent successfully to Telegram!")
                    break
                except TimedOut:
                    if attempt < len(SEND_RETRY_DELAYS) - 1:
                        delay = SEND_RETRY_DELAYS[attempt + 1]
                        print(f"[WARN] Timeout, retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                        continue
                    print("[ERROR] Failed to send message after retries")
            if not send_success:
                return
        else:
            if text == last_text:
                print("[INFO] No changes detected; skipping edit.")
            else:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode="MarkdownV2",
                        disable_web_page_preview=True,
                    )
                    last_text = text
                    print("[OK] Message edited successfully.")
                except BadRequest as exc:
                    if "message is not modified" in str(exc).lower():
                        print("[INFO] Telegram reported message is not modified; skipping.")
                    else:
                        print(f"[ERROR] Failed to edit message: {exc}")
                except TimedOut:
                    print("[WARN] Edit timed out; will retry on next cycle.")

        await asyncio.sleep(UPDATE_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
