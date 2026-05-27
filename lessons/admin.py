from django.contrib import admin

from .models import AvailabilitySlot, Lesson


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ("teacher", "start_time", "end_time", "is_booked")
    list_filter = ("is_booked", "teacher")
    search_fields = ("teacher__username",)
    date_hierarchy = "start_time"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = (
        "id", "student", "teacher", "scheduled_at",
        "status", "cancellation_charged",
    )
    list_filter = ("status", "cancellation_charged")
    search_fields = ("student__username", "teacher__username")
    date_hierarchy = "scheduled_at"
    # raw_id_fields swaps the FK dropdowns for a search popup — important
    # once the user table grows past a few hundred rows.
    raw_id_fields = ("student", "teacher", "slot")
