"""
Reports app: post-lesson teacher reports + student reviews.

Both models reference the Lesson with a OneToOneField — there's exactly
one report per lesson and exactly one review per lesson, so trying to
create a second row for the same lesson raises an IntegrityError instead
of silently duplicating data.
"""
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from lessons.models import Lesson


class LessonReport(models.Model):
    """
    Filled in by the teacher after a lesson. The presence of a report is
    what flips the lesson into the COMPLETED state in Phase 2.
    """
    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="report",
    )
    topic = models.CharField(max_length=200)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report<lesson={self.lesson_id}>"


class Review(models.Model):
    """
    Filled in by the student after a completed lesson. Rating 1-5 stars.
    Validators enforce the range at the form / DRF layer; the field itself
    is a small int so the DB stays compact.
    """
    lesson = models.OneToOneField(
        Lesson,
        on_delete=models.CASCADE,
        related_name="review",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review<lesson={self.lesson_id} stars={self.rating}>"
