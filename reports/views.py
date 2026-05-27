"""
Reports & reviews — read endpoints from Phase 1, plus Phase 2 write logic.

The interesting part is `LessonReportListCreateView.perform_create`:
writing a report is what flips the lesson into COMPLETED and updates
the student's gamification stats. Doing it here means the lifecycle is
event-driven — there's no separate "complete this lesson" call.
"""
from django.db import transaction
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError

from lessons.models import Lesson
from users.models import User
from users.permissions import IsStudent, IsTeacher

from .models import LessonReport, Review
from .serializers import LessonReportSerializer, ReviewSerializer


class LessonReportListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/reports/  — students see reports for their lessons,
                          teachers see reports they wrote.
    POST /api/reports/  — teacher writes a report for a CONFIRMED lesson.
                          Side effects:
                              - lesson.status -> COMPLETED
                              - student.total_lessons += 1
                              - student.streak += 1
    """
    serializer_class = LessonReportSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        u = self.request.user
        if u.role == User.Role.TEACHER:
            return LessonReport.objects.filter(lesson__teacher=u)
        return LessonReport.objects.filter(lesson__student=u)

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.TEACHER:
            raise PermissionDenied("Only teachers can write lesson reports.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        lesson: Lesson = serializer.validated_data["lesson"]

        # Ownership: teachers can only report on lessons they taught.
        if lesson.teacher_id != self.request.user.id:
            raise PermissionDenied("You are not the teacher of this lesson.")

        # State check: a report only makes sense for a confirmed lesson
        # that actually happened.
        if lesson.status != Lesson.Status.CONFIRMED:
            raise ValidationError(
                f"Cannot report on a lesson in status '{lesson.status}'."
            )

        # The OneToOne on LessonReport.lesson would already prevent dupes
        # at the DB level, but checking up-front gives a nicer error.
        if hasattr(lesson, "report"):
            raise ValidationError("A report already exists for this lesson.")

        # All side effects in one transaction so a partial failure doesn't
        # leave the lesson half-completed.
        with transaction.atomic():
            serializer.save()

            lesson.status = Lesson.Status.COMPLETED
            lesson.save(update_fields=["status", "updated_at"])

            profile = getattr(lesson.student, "student_profile", None)
            if profile:
                profile.total_lessons += 1
                profile.streak += 1
                # `rank` is computed from total_lessons, no field to save.
                profile.save(update_fields=["total_lessons", "streak"])


class ReviewListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/reviews/  — student sees own reviews, teacher sees reviews
                          students left them.
    POST /api/reviews/  — student rates a COMPLETED lesson (1-5 stars).
    """
    serializer_class = ReviewSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        u = self.request.user
        if u.role == User.Role.TEACHER:
            return Review.objects.filter(lesson__teacher=u)
        return Review.objects.filter(lesson__student=u)

    def create(self, request, *args, **kwargs):
        if request.user.role != User.Role.STUDENT:
            raise PermissionDenied("Only students can leave reviews.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        lesson: Lesson = serializer.validated_data["lesson"]

        if lesson.student_id != self.request.user.id:
            raise PermissionDenied("You are not the student of this lesson.")

        if lesson.status != Lesson.Status.COMPLETED:
            raise ValidationError("You can only review a completed lesson.")

        if hasattr(lesson, "review"):
            raise ValidationError("You have already reviewed this lesson.")

        serializer.save()
