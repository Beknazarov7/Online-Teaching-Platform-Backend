"""
Long-poll the Telegram Bot API and dispatch incoming updates to the
aiogram handlers.

Usage:
    python manage.py runbot

Runs in the foreground and blocks. Stop with Ctrl+C. Re-run after a code
change (no auto-reload — it's a separate process from runserver).
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notifications.bot.handlers import router

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Telegram bot (long-polling mode)."

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise CommandError(
                "TELEGRAM_BOT_TOKEN is not set. Add it to backend/.env "
                "(get one from @BotFather on Telegram)."
            )

        self.stdout.write(self.style.SUCCESS("Starting Telegram bot (long-poll)…"))
        try:
            asyncio.run(_run(token))
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write(self.style.WARNING("Bot stopped."))


async def _run(token: str):
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    # drop_pending_updates=True so a long downtime doesn't replay every old message.
    await dp.start_polling(bot, drop_pending_updates=True)
