"""
Notifications app models.

Currently just `TelegramLinkCode` — a one-time code the web app generates
so a user can prove they own a Telegram account by sending the code to
the bot via /start <code>.

The Telegram chat id itself lives on `users.User.telegram_id` (set in
Phase 1). Codes here are short-lived; the bot deletes them after consuming.
"""
import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


CODE_TTL = timedelta(minutes=10)
CODE_LENGTH = 8


def _make_code() -> str:
    """Random URL-safe code; ambiguous characters (0/O, 1/I/l) excluded."""
    alphabet = "".join(c for c in (string.ascii_uppercase + string.digits)
                       if c not in "0O1IL")
    return "".join(secrets.choice(alphabet) for _ in range(CODE_LENGTH))


class TelegramLinkCode(models.Model):
    """
    A short, expiring code that the user types into the bot to prove
    ownership. We store the user FK so the bot, on /start <code>, can look
    up which user to link. There's at most one active code per user — the
    view deletes any existing rows before creating a new one.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_link_codes",
    )
    code = models.CharField(max_length=16, unique=True, default=_make_code)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def expires_at(self):
        return self.created_at + CODE_TTL

    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"LinkCode<{self.user.username} {self.code}>"
