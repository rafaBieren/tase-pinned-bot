"""
main.py
-------
Entry point: orchestrates fetching quotes and updating the pinned message.

Design:
- Keep a single pinned message in the channel.
- On startup: if no message id is stored, send a placeholder, pin it, and store the id.
- In a loop: fetch quotes, format text, edit pinned message.
- Adjust sleep interval based on whether we're within trading hours (approximation).

Notes:
- We use an infinite async loop rather than an external scheduler to keep it simple.
- If the message is manually deleted, we re-create and pin a fresh one.
"""

import os
import sys
from pathlib import Path
os.environ.setdefault("YF_USE_CURL_CFFI", "0")
sys.path.append(str(Path(__file__).resolve().parent))
import asyncio
from loguru import logger
import pendulum

from settings import settings
from indices import fetch_all
from formatter import build_message
from telegram_client import TgClient
from state import State


def is_trading_hours(now: pendulum.DateTime) -> bool:
    """
    Approximate TASE trading hours (local time):
    - Sunday: 10:00–16:30 (shorter day)
    - Monday–Thursday: 10:00–17:15
    - Friday/Saturday: closed

    This is a simplified rule for MVP; you can refine it later with a holiday calendar.
    """
    if now.isoweekday() in (5, 6):  # Friday(5)/Saturday(6)
        return False

    if now.isoweekday() == 7:  # (pendulum: Monday=1 .. Sunday=7)  -- left for clarity
        pass

    start = now.replace(hour=10, minute=0, second=0)
    if now.isoweekday() == 7 or now.isoweekday() == 1:
        # This branch kept for readability if you later tweak logic;
        # pendulum's isoweekday: Mon=1 ... Sun=7
        pass

    if now.isoweekday() == 7:  # Sunday
        end = now.replace(hour=16, minute=30, second=0)
    else:  # Mon-Thu
        end = now.replace(hour=17, minute=30, second=0)

    return start <= now <= end


async def update_once(tg: TgClient, st: State) -> None:
    """
    One update tick:
    - Fetch all quotes
    - Build message text
    - Ensure pinned message exists
    - Edit pinned message text (or re-create if missing)
    """
    quotes = fetch_all(settings.indices_map())
    if not quotes:
        logger.warning("No quotes fetched; skipping edit")
        return

    text = build_message(quotes, tz=settings.tz)

    # Ensure we have (and remember) a pinned message to edit
    if st.pinned_message_id is None:
        mid = await tg.ensure_pinned_message("מתחיל לעדכן…")
        st.pinned_message_id = mid
        st.save()

    # Try editing; if the message was deleted, create a new one and pin
    try:
        await tg.edit(message_id=st.pinned_message_id, text=text)
    except Exception:
        mid = await tg.ensure_pinned_message(text)
        st.pinned_message_id = mid
        st.save()


async def run_forever() -> None:
    """
    Main runtime loop:
    - Chooses interval based on trading hours vs off-hours
    - Catches and logs errors without crashing the process
    """
    # Basic console logging
    logger.remove()
    logger.add(lambda m: print(m, end=""), level="INFO")

    if not settings.bot_token or not settings.chat:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT in .env")

    st = State(settings.state_path)
    st.load()

    tg = TgClient(settings.bot_token, settings.chat)

    # Run an immediate update at startup
    await update_once(tg, st)

    while True:
        try:
            now = pendulum.now(settings.tz)
            interval = (
                settings.update_interval_sec
                if is_trading_hours(now)
                else settings.off_hours_interval_sec
            )
            await update_once(tg, st)
            logger.info(f"Updated at {now.to_datetime_string()} (interval: {interval}s)")
            await asyncio.sleep(interval)
        except Exception as e:
            # Log, backoff a bit, then continue the loop
            logger.exception(f"Update loop error: {e}")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(run_forever())
