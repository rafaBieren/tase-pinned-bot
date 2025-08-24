"""
telegram_client.py
------------------
Thin wrapper around python-telegram-bot's Bot for:
- Sending an initial message (and pinning it)
- Editing the pinned message text

We keep this minimal to make it easy to swap libraries or add more methods later.
"""

from telegram import Bot, constants
from telegram.error import BadRequest, Forbidden, TimedOut
from telegram.request import HTTPXRequest    # <- הוספה
from loguru import logger

class TgClient:
    def __init__(self, token: str, chat: str):
        # הוסף בקשת HTTP עם timeouts נדיבים יותר
        request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
        self.bot = Bot(token=token, request=request)
        self.chat = chat

    async def ensure_pinned_message(self, initial_text: str) -> int:
        """
        Send a new message and attempt to pin it.
        Returns the message_id even if pin fails/times out.
        """
        try:
            msg = await self.bot.send_message(
                chat_id=self.chat,
                text=initial_text,
                parse_mode=constants.ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Forbidden as e:
            logger.error(f"Bot is not admin or cannot post to {self.chat}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Failed to send initial pinned message: {e}")
            raise

        # נסה להצמיד, אבל אל תקריס אם נכשל/timeout
        try:
            await self.bot.pin_chat_message(
                chat_id=self.chat,
                message_id=msg.message_id,
                disable_notification=True,
            )
        except (BadRequest, TimedOut) as e:
            logger.warning(f"Pin failed/timeout (continuing without pin): {e}")
        except Exception as e:
            logger.warning(f"Pin failed with unexpected error (continuing): {e}")

        return msg.message_id

    async def edit(self, message_id: int, text: str) -> int:
        """Edit existing message; ignore 'message is not modified' noise."""
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat,
                message_id=message_id,
                text=text,
                parse_mode=constants.ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return message_id
        except BadRequest as e:
            # אם אין שינוי בתוכן — לא דרמה, אל תזרוק חריגה
            if "message is not modified" in str(e).lower():
                logger.debug("Skipped edit: content unchanged")
                return message_id
            logger.warning(f"Edit failed: {e}")
            raise
