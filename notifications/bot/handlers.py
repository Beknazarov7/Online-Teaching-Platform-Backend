"""
aiogram handlers for the Telegram bot.

The bot only deals with INCOMING messages (commands the user types).
Outgoing reminders are sent from Celery via notifications.services —
that's a one-shot HTTP call to the Bot API, no event loop needed.

Django ORM is synchronous, so every DB call here is wrapped with
asgiref.sync.sync_to_async. That's the standard aiogram-on-Django pattern.
"""
from asgiref.sync import sync_to_async
from aiogram import Router, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message
from django.utils import timezone

from lessons.models import Lesson
from notifications.models import TelegramLinkCode
from users.models import User


router = Router()


# --- DB helpers (sync code wrapped for the async dispatcher) -------------

@sync_to_async
def link_user_by_code(code_str: str, telegram_id: int):
    """
    Try to consume a link code: returns the linked User on success,
    or a string error message on failure (expired / unknown / already
    used by another telegram account).
    """
    try:
        link = TelegramLinkCode.objects.select_related("user").get(code=code_str.upper())
    except TelegramLinkCode.DoesNotExist:
        return None, "Unknown code. Generate a fresh one from the web app."

    if link.is_expired():
        link.delete()
        return None, "That code has expired. Generate a new one from the web app."

    user = link.user
    # If this Telegram account is already linked to a *different* user,
    # bail — we don't want to silently steal another user's link.
    other = User.objects.filter(telegram_id=telegram_id).exclude(pk=user.pk).first()
    if other:
        return None, "This Telegram account is already linked to another user."

    user.telegram_id = telegram_id
    user.save(update_fields=["telegram_id"])
    link.delete()
    return user, None


@sync_to_async
def unlink_user(telegram_id: int):
    """Clear telegram_id on whichever user owns this chat."""
    user = User.objects.filter(telegram_id=telegram_id).first()
    if not user:
        return None
    user.telegram_id = None
    user.save(update_fields=["telegram_id"])
    return user


@sync_to_async
def upcoming_for(telegram_id: int):
    """Return list of upcoming PENDING/CONFIRMED lessons for the user."""
    user = User.objects.filter(telegram_id=telegram_id).first()
    if not user:
        return None
    now = timezone.now()
    qs = Lesson.objects.select_related("student", "teacher").filter(
        scheduled_at__gt=now,
        status__in=[Lesson.Status.PENDING, Lesson.Status.CONFIRMED],
    )
    if user.role == User.Role.TEACHER:
        qs = qs.filter(teacher=user)
    else:
        qs = qs.filter(student=user)
    # Materialise inside the sync_to_async wrapper — can't iterate a queryset
    # back in async context.
    return list(qs.order_by("scheduled_at")[:10]), user


# --- Handlers ------------------------------------------------------------

@router.message(CommandStart(deep_link=True))
async def on_start_with_code(message: Message, command: CommandObject):
    """/start <code>  — the link flow."""
    code = (command.args or "").strip()
    if not code:
        await message.answer(
            "Hi! To link your account, generate a code from your web profile "
            "and send <code>/start YOURCODE</code>.",
            parse_mode="HTML",
        )
        return

    user, err = await link_user_by_code(code, message.chat.id)
    if err:
        await message.answer(err)
        return

    await message.answer(
        f"Linked! You'll get reminders here for <b>{user.username}</b>.\n\n"
        "Try /upcoming to see your next lessons, or /help for the full list.",
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def on_start_plain(message: Message):
    """/start with no code."""
    await message.answer(
        "Hi! I send lesson reminders for the Online Teaching Platform.\n\n"
        "To connect your account, generate a code from your web profile and "
        "send <code>/start YOURCODE</code>.\n\n"
        "Type /help for what I can do.",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def on_help(message: Message):
    await message.answer(
        "<b>Commands</b>\n"
        "/start &lt;code&gt; — link your account\n"
        "/upcoming — your next 10 lessons\n"
        "/unlink — disconnect your account\n"
        "/help — show this message",
        parse_mode="HTML",
    )


@router.message(Command("upcoming"))
async def on_upcoming(message: Message):
    result = await upcoming_for(message.chat.id)
    if result is None:
        await message.answer("You're not linked yet. Send /start &lt;code&gt; to link.", parse_mode="HTML")
        return

    lessons, user = result
    if not lessons:
        await message.answer("No upcoming lessons.")
        return

    label = "student" if user.role == User.Role.STUDENT else "teacher"
    other = "teacher" if label == "student" else "student"

    lines = [f"<b>Your next lessons ({len(lessons)})</b>\n"]
    for l in lessons:
        partner = l.teacher.username if label == "student" else l.student.username
        when = l.scheduled_at.strftime("%a %d %b, %H:%M")
        lines.append(f"• {when} — with {partner} <i>({l.status})</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("unlink"))
async def on_unlink(message: Message):
    user = await unlink_user(message.chat.id)
    if user is None:
        await message.answer("You weren't linked. Nothing to do.")
        return
    await message.answer(f"Unlinked <b>{user.username}</b>. You won't get reminders here anymore.", parse_mode="HTML")


@router.message(F.text)
async def on_other(message: Message):
    """Catch-all for anything that isn't a known command."""
    await message.answer("I only respond to commands. Try /help.")
