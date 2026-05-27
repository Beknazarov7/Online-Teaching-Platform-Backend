from rest_framework import serializers

from lessons.models import Lesson

from .models import LessonReport, Review


class LessonReportSerializer(serializers.ModelSerializer):
    """
    Used for both list (read) and create (POST). On write, only the teacher
    of the lesson is allowed to create a report — the view enforces that.
    """
    class Meta:
        model = LessonReport
        fields = ("id", "lesson", "topic", "text", "created_at")
        read_only_fields = ("id", "created_at")


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ("id", "lesson", "rating", "comment", "created_at")
        read_only_fields = ("id", "created_at")
