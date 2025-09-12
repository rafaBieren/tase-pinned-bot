import os
import asyncio

from telegram import Bot
from dotenv import load_dotenv
from telegram.error import InvalidToken, TimedOut
from telegram.request import HTTPXRequest

from ta125_update import send_ta125_update


async def main() -> None:
    """Send a single TA-125 update message at startup and exit."""
    # Ensure .env values override any existing environment variables
    load_dotenv(override=True)

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT") or "").strip()

    if not token:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN in environment or .env")
    if not chat_id:
        raise SystemExit("Missing TELEGRAM_CHAT in environment or .env")

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

    await send_ta125_update(chat_id=chat_id, bot=bot)


if __name__ == "__main__":
    asyncio.run(main())
