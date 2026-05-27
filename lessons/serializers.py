from rest_framework import serializers
from django.utils import timezone

from .models import AvailabilitySlot, Lesson


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    """
    Used for both reading slots (student view, teacher view) and creating
    them (teacher view). The teacher is set automatically from request.user
    in the view's perform_create — never trusted from the payload.
    """
    teacher_name = serializers.CharField(source="teacher.username", read_only=True)

    class Meta:
        model = AvailabilitySlot
        fields = ("id", "teacher", "teacher_name", "start_time", "end_time", "is_booked")
        read_only_fields = ("id", "teacher", "is_booked")

    def validate(self, attrs):
        # `attrs` is the partially-validated dict. On PATCH some keys may
        # be missing, so fall back to the existing instance.
        start = attrs.get("start_time") or getattr(self.instance, "start_time", None)
        end   = attrs.get("end_time")   or getattr(self.instance, "end_time",   None)

        if start and end and end <= start:
            raise serializers.ValidationError("end_time must be after start_time.")
        if start and start < timezone.now():
            raise serializers.ValidationError("Cannot create a slot in the past.")
        return attrs


class BulkSlotItemSerializer(serializers.Serializer):
    """One {start_time, end_time} pair inside the bulk-create payload."""
    start_time = serializers.DateTimeField()
    end_time   = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError("end_time must be after start_time.")
        if attrs["start_time"] < timezone.now():
            raise serializers.ValidationError("Cannot create a slot in the past.")
        return attrs


class BulkSlotCreateSerializer(serializers.Serializer):
    """
    Input for POST /api/teacher/slots/bulk/. The frontend expands the
    recurrence (days of week × date range × times) into a flat array of
    slots in the user's local timezone, so the backend just does the
    insert. Slots that collide with an existing teacher+start_time row
    are silently skipped — re-running the same recurrence is safe.
    """
    slots = BulkSlotItemSerializer(many=True, allow_empty=False)


class LessonSerializer(serializers.ModelSerializer):
    """
    Read serializer for lessons. Privacy: a student sees only `teacher_name`,
    never the teacher's email or any contact field.
    """
    student_name = serializers.CharField(source="student.username", read_only=True)
    teacher_name = serializers.CharField(source="teacher.username", read_only=True)

    class Meta:
        model = Lesson
        fields = (
            "id",
            "student", "student_name",
            "teacher", "teacher_name",
            "slot", "scheduled_at",
            "status", "cancellation_charged",
            "created_at", "updated_at",
        )
        read_only_fields = fields  # entire model is read-only via this serializer


class BookLessonSerializer(serializers.Serializer):
    """
    Input for POST /api/lessons/. Student sends just the slot id; everything
    else (student, teacher, scheduled_at, status) is derived server-side.

    Using a plain Serializer (not ModelSerializer) here because the booking
    flow has side effects — we mutate the slot too — so it's cleaner to
    keep the actual creation in the view, where transactions live.
    """
    slot = serializers.PrimaryKeyRelatedField(queryset=AvailabilitySlot.objects.all())

    def validate_slot(self, slot: AvailabilitySlot):
        if slot.is_booked:
            raise serializers.ValidationError("This slot is already booked.")
        if slot.start_time < timezone.now():
            raise serializers.ValidationError("Cannot book a slot in the past.")
        return slot
