"""
Background tasks for lessons.

In Phase 2 these tasks just LOG the reminder — there's no Telegram bot yet.
In Phase 4 we'll replace the log line with an actual Telegram message,
but the surrounding scheduling code stays the same. That separation is the
whole point of using a task queue: the *when* and the *what* are decoupled.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


# `bind=True` gives us `self` inside the task — handy for retries later.
@shared_task(bind=True)
def send_lesson_reminder(self, lesson_id: int, label: str):
    """
    Fired by Celery at the scheduled ETA. Looks up the lesson and emits a
    log line. We import inside the function (not at module top) to avoid
    Django app-loading order issues at worker startup.
    """
    from .models import Lesson

    try:
        lesson = Lesson.objects.select_related("student", "teacher").get(pk=lesson_id)
    except Lesson.DoesNotExist:
        # The lesson was deleted between scheduling and firing — nothing to do.
        logger.warning("Reminder %s: lesson %s no longer exists", label, lesson_id)
        return

    # If the lesson got cancelled/declined after we queued the reminder,
    # just skip — we don't want to send "your lesson is in 1h" for a
    # lesson that no longer exists.
    if lesson.status not in (Lesson.Status.CONFIRMED,):
        logger.info(
            "Reminder %s skipped: lesson %s is in status %s",
            label, lesson_id, lesson.status,
        )
        return

    logger.info(
        "[REMINDER %s] lesson=%s student=%s teacher=%s scheduled_at=%s",
        label, lesson_id, lesson.student.username,
        lesson.teacher.username, lesson.scheduled_at,
    )

    # Push Telegram messages to both sides if they've linked their accounts.
    # send_telegram_message no-ops cleanly when telegram_id isn't set, so
    # we don't have to guard here.
    from notifications.services import send_telegram_message

    when = lesson.scheduled_at.strftime("%a %d %b, %H:%M")
    headline = "Your lesson is in 24 hours" if label == "24h" else "Your lesson starts in 1 hour"

    student_msg = (
        f"⏰ <b>{headline}</b>\n"
        f"With <b>{lesson.teacher.username}</b> at {when} (UTC)."
    )
    teacher_msg = (
        f"⏰ <b>{headline}</b>\n"
        f"With <b>{lesson.student.username}</b> at {when} (UTC)."
    )
    send_telegram_message(lesson.student, student_msg)
    send_telegram_message(lesson.teacher, teacher_msg)


def schedule_reminders_for(lesson) -> None:
    """
    Helper called from the confirm view. Queues two reminders — 24h and 1h
    before scheduled_at. If either ETA is already in the past (e.g. the
    lesson is < 1h away when confirmed), Celery fires the task immediately,
    which is the behavior we want.
    """
    eta_24h = lesson.scheduled_at - timedelta(hours=24)
    eta_1h  = lesson.scheduled_at - timedelta(hours=1)
    now = timezone.now()

    # Only schedule a reminder if there's at least *some* time left —
    # firing a "your lesson is in 24h" task for a lesson that already
    # happened is just noise.
    if eta_24h > now:
        send_lesson_reminder.apply_async(args=[lesson.id, "24h"], eta=eta_24h)
    if eta_1h > now:
        send_lesson_reminder.apply_async(args=[lesson.id, "1h"],  eta=eta_1h)
