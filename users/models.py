from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model. Extends Django's AbstractUser so we still get
    `username`, `password`, `email`, `is_staff`, `is_superuser`, etc. for free,
    but we add a `role` field and a `telegram_id` for bot integration.

    We set this as AUTH_USER_MODEL in settings.py so every part of Django
    (auth backends, admin, JWT) uses this model instead of the default.
    """

    class Role(models.TextChoices):
        # TextChoices keeps the values readable in the DB and gives us
        # User.Role.STUDENT etc. in code.
        STUDENT = "student", "Student"
        TEACHER = "teacher", "Teacher"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    # Telegram chat id — filled in once the user links their account to the bot.
    # Nullable because new accounts haven't linked yet.
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class StudentProfile(models.Model):
    """
    One-to-one extension of User for students.
    Created automatically via signal when a User with role=STUDENT is saved.
    """

    class Level(models.TextChoices):
        A1 = "A1", "A1 — Beginner"
        A2 = "A2", "A2 — Elementary"
        B1 = "B1", "B1 — Intermediate"
        B2 = "B2", "B2 — Upper-Intermediate"
        C1 = "C1", "C1 — Advanced"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,         # delete the profile if the user is deleted
        related_name="student_profile",   # access via user.student_profile
    )
    level = models.CharField(max_length=2, choices=Level.choices, default=Level.A1)
    total_lessons = models.PositiveIntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)

    @property
    def rank(self) -> str:
        """
        Computed (not stored) — rank is always derived from total_lessons,
        so we can never get out of sync. See gamification table in the spec.
        """
        n = self.total_lessons
        if n <= 5:
            return "Starter"
        if n <= 15:
            return "Learner"
        if n <= 30:
            return "Speaker"
        if n <= 50:
            return "Confident"
        return "Fluent"

    def __str__(self):
        return f"StudentProfile<{self.user.username}>"


class TeacherProfile(models.Model):
    """
    One-to-one extension of User for teachers. For Phase 1 we only need a bio;
    availability lives in the lessons app.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"TeacherProfile<{self.user.username}>"
