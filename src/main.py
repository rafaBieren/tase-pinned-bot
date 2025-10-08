import os
import asyncio
from typing import Optional

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
from tase_calendar import TradingDayInfo
from datetime import datetime
from zoneinfo import ZoneInfo


UPDATE_INTERVAL_SEC = 300
SEND_RETRY_DELAYS = [0, 2, 4]
FALLBACK_TEXT = "לא הצלחתי להביא כרגע נתונים למדדים. נסו שוב מאוחר יותר."
MESSAGE_ID_FILE = "message_id.txt"


def _get_tz() -> ZoneInfo:
    """Resolve timezone from settings with a fallback."""
    try:
        return ZoneInfo(settings.tz)
    except Exception:
        return ZoneInfo("Asia/Jerusalem")


def _read_message_id() -> Optional[int]:
    """Read message ID if it exists and belongs to the current trading day."""
    if not os.path.exists(MESSAGE_ID_FILE):
        return None

    with open(MESSAGE_ID_FILE, "r") as f:
        content = f.read().strip()

    parts = content.split(",")
    if len(parts) != 2:
        return None

    message_id_str, date_str = parts
    if not message_id_str.isdigit():
        return None

    try:
        stored_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    tz = _get_tz()
    today = datetime.now(tz).date()

    if stored_date == today:
        return int(message_id_str)

    return None


def _write_message_id(message_id: int) -> None:
    """Write message ID and current date to file."""
    tz = _get_tz()
    today_str = datetime.now(tz).date().isoformat()
    with open(MESSAGE_ID_FILE, "w") as f:
        f.write(f"{message_id},{today_str}")


async def main(run_once: bool = False, market_open: bool = True, day_info: Optional[TradingDayInfo] = None) -> None:
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

    message_id = _read_message_id()
    last_text = None

    while True:
        indices_map = settings.indices_map()
        quotes = fetch_all(indices_map)

        if not quotes:
            text = FALLBACK_TEXT
        else:
            text = build_message(
                quotes=quotes,
                tz=settings.tz,
                market_closed=not market_open,
                day_info=day_info
            )

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
                    _write_message_id(message_id)
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
            if run_once:
                break
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
                    if run_once:
                        break
                except BadRequest as exc:
                    if "message is not modified" in str(exc).lower():
                        print("[INFO] Telegram reported message is not modified; skipping.")
                    else:
                        print(f"[ERROR] Failed to edit message: {exc}")
                except TimedOut:
                    print("[WARN] Edit timed out; will retry on next cycle.")

        if run_once:
            return

        await asyncio.sleep(UPDATE_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
