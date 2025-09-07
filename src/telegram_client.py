"""
telegram_client.py
------------------
Thin wrapper around python-telegram-bot's Bot for:
- Sending an initial message (and pinning it)
- Editing the pinned message text

We keep this minimal to make it easy to swap libraries or add more methods later.
"""

from telegram import Bot, constants
from telegram.error import BadRequest, Forbidden
from loguru import logger


class TgClient:
    """Convenience wrapper for Telegram operations used by our bot."""

    def __init__(self, token: str, chat: str):
        self.bot = Bot(token=token)
        self.chat = chat  # channel username (@YourChannel) or numeric id (-100...)

    async def ensure_pinned_message(self, initial_text: str) -> int:
        """
        Send a new message and attempt to pin it.
        Returns the message_id.

        Note: pin may fail if the bot lacks permissions or another pinned message exists.
        In that case, we merely log a warning and proceed.
        """
        try:
            msg = await self.bot.send_message(
                chat_id=self.chat,
                text=initial_text,
                parse_mode=constants.ParseMode.HTML,
                disable_web_page_preview=True,
            )
            try:
                await self.bot.pin_chat_message(
                    chat_id=self.chat,
                    message_id=msg.message_id,
                    disable_notification=True,
                )
            except BadRequest as e:
                logger.warning(f"Pin failed (maybe already pinned or missing rights): {e}")

            return msg.message_id

        except Forbidden as e:
            logger.error(f"Bot is not admin or cannot post to {self.chat}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Failed to send initial pinned message: {e}")
            raise

    async def edit(self, message_id: int, text: str) -> int:
        """
        Edit an existing message by id.
        Raises if the message does not exist or cannot be edited.
        """
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
            logger.warning(f"Edit failed: {e}")
            raise
