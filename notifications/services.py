"""
Notification dispatcher.

Used by both Celery tasks (lesson reminders) and views (link confirmations)
to actually push a Telegram message to a user. We hit the Telegram Bot
HTTP API directly with `requests` instead of going through aiogram —
sending a single message doesn't need an event loop, and Celery workers
are sync, so this avoids `asyncio.run` gymnastics.

The bot module under notifications.bot uses aiogram for *receiving*
messages (long-polling); that's a different concern.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_message(user, text: str, *, parse_mode: str = "HTML") -> bool:
    """
    Send `text` to the user's linked Telegram chat. No-op (returns False)
    if the user hasn't linked yet or the bot token isn't configured.

    Returns True on a successful 200 from the Telegram API.
    """
    chat_id = getattr(user, "telegram_id", None)
    if not chat_id:
        logger.info("Skipping Telegram send: user %s has no telegram_id", user.id)
        return False

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set; cannot send to %s", user.id)
        return False

    try:
        resp = requests.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("Telegram send failed (network) for user %s: %s", user.id, exc)
        return False

    if resp.status_code != 200:
        logger.error(
            "Telegram send failed for user %s: %s %s",
            user.id, resp.status_code, resp.text,
        )
        return False

    return True
