"""
Phase 2: full scheduling logic.

Endpoint summary:
    GET    /api/slots/                    — student lists bookable slots
    GET    /api/teacher/slots/            — teacher lists their own slots
    POST   /api/teacher/slots/            — teacher creates a slot
    PATCH  /api/teacher/slots/<id>/       — teacher edits their slot (if unbooked)
    DELETE /api/teacher/slots/<id>/       — teacher deletes their slot (if unbooked)
    GET    /api/lessons/                  — list lessons involving the current user
    POST   /api/lessons/                  — student books a lesson
    POST   /api/lessons/<id>/confirm/     — teacher confirms a pending booking
    POST   /api/lessons/<id>/decline/     — teacher declines a pending booking
    POST   /api/lessons/<id>/cancel/      — student or teacher cancels (6h rule)
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User
from users.permissions import IsStudent, IsTeacher

from .models import AvailabilitySlot, Lesson
from .serializers import (
    AvailabilitySlotSerializer,
    BookLessonSerializer,
    BulkSlotCreateSerializer,
    LessonSerializer,
)
from .tasks import schedule_reminders_for


# How close to the lesson does cancellation become "charged"?
# Pulled out as a constant so the rule is easy to find and tweak.
CANCELLATION_GRACE = timedelta(hours=6)


# ---------------------------------------------------------------- Slots --
class AvailableSlotListView(generics.ListAPIView):
    """Student-facing list of bookable slots. Optional ?teacher=<id> filter."""
    serializer_class = AvailabilitySlotSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        qs = AvailabilitySlot.objects.filter(
            is_booked=False,
            start_time__gt=timezone.now(),  # hide past slots
        )
        teacher_id = self.request.query_params.get("teacher")
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        return qs


class TeacherSlotListCreateView(generics.ListCreateAPIView):
    """
    GET  -> list this teacher's own slots (booked or not)
    POST -> create a new slot
    """
    serializer_class = AvailabilitySlotSerializer
    permission_classes = (permissions.IsAuthenticated, IsTeacher)

    def get_queryset(self):
        return AvailabilitySlot.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        # The teacher is the logged-in user — never trust the payload.
        serializer.save(teacher=self.request.user)


class TeacherSlotDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET / PATCH / DELETE a single slot. The queryset is filtered to the
    current teacher's slots, so a teacher who guesses another teacher's
    slot id gets a 404 instead of being able to mutate it.
    """
    serializer_class = AvailabilitySlotSerializer
    permission_classes = (permissions.IsAuthenticated, IsTeacher)

    def get_queryset(self):
        return AvailabilitySlot.objects.filter(teacher=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.is_booked:
            # Once a student has booked, the slot's time is part of a
            # lesson agreement — don't allow silent edits.
            raise ValidationError("Cannot edit a slot that is already booked.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_booked:
            raise ValidationError("Cannot delete a slot that is already booked.")
        instance.delete()


class TeacherSlotBulkCreateView(APIView):
    """
    POST /api/teacher/slots/bulk/

    Take a flat list of {start_time, end_time} pairs and create them all.
    Slots that collide with an existing teacher+start_time row (the unique
    constraint) are skipped, not errored — that way running the same
    recurrence twice doesn't fail. Returns:
        {created: [...slots], skipped: int}
    """
    permission_classes = (permissions.IsAuthenticated, IsTeacher)

    def post(self, request):
        in_ser = BulkSlotCreateSerializer(data=request.data)
        in_ser.is_valid(raise_exception=True)

        created = []
        skipped = 0
        for item in in_ser.validated_data["slots"]:
            try:
                # Each insert in its own savepoint — IntegrityError on one
                # collision must not poison the whole outer transaction.
                with transaction.atomic():
                    slot = AvailabilitySlot.objects.create(
                        teacher=request.user,
                        start_time=item["start_time"],
                        end_time=item["end_time"],
                    )
                created.append(slot)
            except IntegrityError:
                skipped += 1

        out = AvailabilitySlotSerializer(created, many=True)
        return Response(
            {"created": out.data, "skipped": skipped},
            status=status.HTTP_201_CREATED,
        )


# -------------------------------------------------------------- Lessons --
class LessonListBookView(generics.ListCreateAPIView):
    """
    GET  -> lessons involving the current user
    POST -> student books a slot (creates a PENDING lesson)

    Two HTTP verbs share one URL because that's the standard REST pattern:
    GET /lessons/  =  list, POST /lessons/  =  create.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get_serializer_class(self):
        # The list response shape and the booking input shape are different,
        # so we swap serializers based on method.
        if self.request.method == "POST":
            return BookLessonSerializer
        return LessonSerializer

    def get_queryset(self):
        u = self.request.user
        if u.role == User.Role.TEACHER:
            return Lesson.objects.filter(teacher=u)
        return Lesson.objects.filter(student=u)

    def create(self, request, *args, **kwargs):
        # Only students book.
        if request.user.role != User.Role.STUDENT:
            raise PermissionDenied("Only students can book lessons.")

        in_serializer = self.get_serializer(data=request.data)
        in_serializer.is_valid(raise_exception=True)
        slot_id = in_serializer.validated_data["slot"].id

        # Race-condition safety: two students might POST at the same time.
        # `select_for_update` locks the row until the transaction commits,
        # so the second request waits and then sees is_booked=True and fails.
        with transaction.atomic():
            slot = (
                AvailabilitySlot.objects
                .select_for_update()
                .get(pk=slot_id)
            )
            if slot.is_booked:
                raise ValidationError("This slot was just booked by someone else.")

            # Don't let one student book two lessons at the same time.
            clash = Lesson.objects.filter(
                student=request.user,
                scheduled_at=slot.start_time,
            ).exclude(status__in=[Lesson.Status.CANCELLED, Lesson.Status.DECLINED])
            if clash.exists():
                raise ValidationError("You already have a lesson at that time.")

            lesson = Lesson.objects.create(
                student=request.user,
                teacher=slot.teacher,
                slot=slot,
                scheduled_at=slot.start_time,
                status=Lesson.Status.PENDING,
            )
            slot.is_booked = True
            slot.save(update_fields=["is_booked"])

        # Ping the teacher on Telegram (no-op if they haven't linked).
        from notifications.services import send_telegram_message
        when = lesson.scheduled_at.strftime("%a %d %b, %H:%M")
        send_telegram_message(
            lesson.teacher,
            f"📩 <b>New booking request</b>\n"
            f"<b>{lesson.student.username}</b> wants a lesson at {when} (UTC).\n"
            f"Confirm or decline from the web app.",
        )

        # Return the full lesson via the read serializer so the client gets
        # everything it needs in one round trip.
        out = LessonSerializer(lesson)
        return Response(out.data, status=status.HTTP_201_CREATED)


def _get_lesson_for_user(lesson_id: int, user, *, must_be_teacher: bool = False) -> Lesson:
    """
    Helper used by every action endpoint below. Centralises the "does this
    user have permission to act on this lesson?" check so we don't repeat
    the same six lines four times.
    """
    try:
        lesson = Lesson.objects.select_related("slot").get(pk=lesson_id)
    except Lesson.DoesNotExist:
        # Use 404 instead of 403 so we don't leak whether the id exists.
        raise ValidationError("Lesson not found.")

    if must_be_teacher:
        if lesson.teacher_id != user.id:
            raise PermissionDenied("Only the lesson's teacher can do this.")
    else:
        if user.id not in (lesson.student_id, lesson.teacher_id):
            raise PermissionDenied("You are not part of this lesson.")
    return lesson


class ConfirmLessonView(APIView):
    """POST /api/lessons/<id>/confirm/  — teacher accepts a PENDING booking."""
    permission_classes = (permissions.IsAuthenticated, IsTeacher)

    def post(self, request, pk):
        lesson = _get_lesson_for_user(pk, request.user, must_be_teacher=True)

        if lesson.status != Lesson.Status.PENDING:
            raise ValidationError(f"Cannot confirm a lesson in status '{lesson.status}'.")

        lesson.status = Lesson.Status.CONFIRMED
        lesson.save(update_fields=["status", "updated_at"])

        # Now that the time is locked in, queue the reminder tasks.
        schedule_reminders_for(lesson)

        from notifications.services import send_telegram_message
        when = lesson.scheduled_at.strftime("%a %d %b, %H:%M")
        send_telegram_message(
            lesson.student,
            f"✅ <b>Lesson confirmed</b>\n"
            f"<b>{lesson.teacher.username}</b> confirmed your lesson on {when} (UTC).",
        )

        return Response(LessonSerializer(lesson).data)


class DeclineLessonView(APIView):
    """POST /api/lessons/<id>/decline/  — teacher rejects, slot is freed."""
    permission_classes = (permissions.IsAuthenticated, IsTeacher)

    def post(self, request, pk):
        lesson = _get_lesson_for_user(pk, request.user, must_be_teacher=True)

        if lesson.status != Lesson.Status.PENDING:
            raise ValidationError(f"Cannot decline a lesson in status '{lesson.status}'.")

        with transaction.atomic():
            lesson.status = Lesson.Status.DECLINED
            lesson.save(update_fields=["status", "updated_at"])
            # Free the slot so another student can book it.
            if lesson.slot:
                lesson.slot.is_booked = False
                lesson.slot.save(update_fields=["is_booked"])

        from notifications.services import send_telegram_message
        when = lesson.scheduled_at.strftime("%a %d %b, %H:%M")
        send_telegram_message(
            lesson.student,
            f"❌ <b>Lesson declined</b>\n"
            f"<b>{lesson.teacher.username}</b> declined your booking for {when} (UTC). "
            f"The slot is open again — you can pick a different one.",
        )

        return Response(LessonSerializer(lesson).data)


class CancelLessonView(APIView):
    """
    POST /api/lessons/<id>/cancel/  — student or teacher cancels.

    The 6-hour rule:
      * cancelled > 6h before scheduled_at  -> free, slot freed up
      * cancelled <=6h before scheduled_at  -> charged, slot stays booked
                                              (the teacher's hour is "used")
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, pk):
        lesson = _get_lesson_for_user(pk, request.user)

        if lesson.status not in (Lesson.Status.PENDING, Lesson.Status.CONFIRMED):
            raise ValidationError(f"Cannot cancel a lesson in status '{lesson.status}'.")

        # The grace window: more than 6h away = free.
        is_free = (lesson.scheduled_at - timezone.now()) > CANCELLATION_GRACE

        with transaction.atomic():
            lesson.status = Lesson.Status.CANCELLED
            lesson.cancellation_charged = not is_free
            lesson.save(update_fields=["status", "cancellation_charged", "updated_at"])

            # Free the slot only on a free cancellation. A charged
            # cancellation consumes the teacher's hour even though the
            # lesson didn't physically happen.
            if is_free and lesson.slot:
                lesson.slot.is_booked = False
                lesson.slot.save(update_fields=["is_booked"])

            # A free cancellation breaks the student's streak; a charged one
            # does NOT (the lesson is "used", it just didn't take place).
            if is_free and lesson.student.role == User.Role.STUDENT:
                profile = getattr(lesson.student, "student_profile", None)
                if profile:
                    profile.streak = 0
                    profile.save(update_fields=["streak"])

        from notifications.services import send_telegram_message
        when = lesson.scheduled_at.strftime("%a %d %b, %H:%M")
        # Notify whichever side did NOT click cancel.
        other = lesson.teacher if request.user.id == lesson.student_id else lesson.student
        actor = lesson.student if request.user.id == lesson.student_id else lesson.teacher
        send_telegram_message(
            other,
            f"🚫 <b>Lesson cancelled</b>\n"
            f"<b>{actor.username}</b> cancelled the lesson on {when} (UTC).",
        )

        return Response(LessonSerializer(lesson).data)
