"""
Lesson-related models.
Phase 1 only defines the schema — the booking/cancellation logic itself
lives in views and Celery tasks (Phase 2). The models still need the right
fields, choices, and constraints so we don't have to migrate again later.
"""
from django.conf import settings
from django.db import models


class AvailabilitySlot(models.Model):
    """
    A single hour the teacher offers. The booking flow only ever consumes
    slots where is_booked=False, and flips the flag when a Lesson is created.
    """
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,            # always reference the user model via settings,
        on_delete=models.CASCADE,            # not by importing User directly — keeps the
        related_name="availability_slots",   # apps loosely coupled.
        # The role of this user is enforced in serializer/admin validation,
        # not in the DB schema (Postgres has no enum-on-FK constraint).
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_booked = models.BooleanField(default=False)

    class Meta:
        # Two teachers can have a slot at the same start_time, but the same
        # teacher can't double-book themselves. Enforced at the DB level.
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "start_time"],
                name="unique_teacher_start",
            ),
        ]
        ordering = ("start_time",)

    def __str__(self):
        return f"{self.teacher.username} @ {self.start_time:%Y-%m-%d %H:%M}"


class Lesson(models.Model):
    """
    A booking. Goes through a small state machine:
        PENDING -> CONFIRMED -> COMPLETED
                |-> CANCELLED (from any pre-completion state)
                |-> DECLINED  (teacher rejected the request)
    A lesson is only counted toward total_lessons / streak when it reaches
    COMPLETED (or CANCELLED with cancellation_charged=True per the 6h rule).
    """

    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        DECLINED  = "declined",  "Declined"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_lessons",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_lessons",
    )
    # The slot is consumed when the booking is created. We keep the FK so we
    # can free the slot back up on cancellation. SET_NULL lets us delete an
    # orphan slot without losing the lesson record.
    slot = models.OneToOneField(
        AvailabilitySlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson",
    )
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    # True when the cancellation happened inside the 6-hour window — the
    # lesson is "used up" and the student is charged for it.
    cancellation_charged = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-scheduled_at",)

    def __str__(self):
        return f"Lesson<{self.student.username}<->{self.teacher.username} {self.status}>"
