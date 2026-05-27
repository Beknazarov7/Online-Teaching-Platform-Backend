from django.contrib import admin

from .models import LessonReport, Review


@admin.register(LessonReport)
class LessonReportAdmin(admin.ModelAdmin):
    list_display = ("lesson", "topic", "created_at")
    search_fields = ("topic", "text", "lesson__student__username")
    raw_id_fields = ("lesson",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("lesson", "rating", "created_at")
    list_filter = ("rating",)
    raw_id_fields = ("lesson",)
