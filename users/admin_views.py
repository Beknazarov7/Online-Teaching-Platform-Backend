"""
Admin-only API endpoints.

Mounted under /api/admin/. All require IsAdminRole, which accepts both
`role == ADMIN` and Django superusers — so the existing `createsuperuser`
account works as an admin in the React UI without re-roling them.

Endpoints:
    GET    /api/admin/stats/                   — dashboard counters
    GET    /api/admin/users/?role=student      — list users
    POST   /api/admin/users/                   — create user with any role
    GET    /api/admin/users/<id>/              — retrieve
    PATCH  /api/admin/users/<id>/              — edit (is_active, role, email)
    DELETE /api/admin/users/<id>/              — delete (hard)
    GET    /api/admin/activity/                — recent platform activity
"""
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from lessons.models import Lesson
from lessons.serializers import LessonSerializer
from reports.models import LessonReport, Review

from .models import User
from .permissions import IsAdminRole
from .serializers import UserSerializer


# --- Stats --------------------------------------------------------------

class StatsView(APIView):
    """Dashboard counters with month-over-month deltas."""
    permission_classes = (permissions.IsAuthenticated, IsAdminRole)

    def get(self, request):
        now = timezone.now()
        month_ago = now - timedelta(days=30)
        prev_month = now - timedelta(days=60)

        students = User.objects.filter(role=User.Role.STUDENT).count()
        students_prev = User.objects.filter(
            role=User.Role.STUDENT, date_joined__lt=month_ago
        ).count()

        teachers = User.objects.filter(role=User.Role.TEACHER).count()
        teachers_prev = User.objects.filter(
            role=User.Role.TEACHER, date_joined__lt=month_ago
        ).count()

        lessons_completed = Lesson.objects.filter(status=Lesson.Status.COMPLETED).count()
        lessons_this_month = Lesson.objects.filter(
            status=Lesson.Status.COMPLETED, updated_at__gte=month_ago,
        ).count()

        return Response({
            "students":          {"value": students, "delta_pct": _pct(students_prev, students)},
            "teachers":          {"value": teachers, "delta_pct": _pct(teachers_prev, teachers)},
            "lessons_completed": {"value": lessons_completed, "this_month": lessons_this_month},
        })


def _pct(prev: int, curr: int) -> int:
    """Percent change rounded to whole number; safe when prev=0."""
    if prev == 0:
        return 100 if curr > 0 else 0
    return round((curr - prev) / prev * 100)


# --- User CRUD ----------------------------------------------------------

class AdminUserSerializer(serializers.ModelSerializer):
    """Trimmed serializer for the admin tables — no nested profiles."""
    class Meta:
        model = User
        fields = (
            "id", "username", "email", "role",
            "is_active", "is_superuser",
            "date_joined", "last_login",
        )
        read_only_fields = ("id", "is_superuser", "date_joined", "last_login")


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """Admin can create a user with any role (unlike public registration)."""
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password", "role")

    def create(self, validated_data):
        # create_user hashes the password; the post_save signal will create
        # the matching profile based on the role.
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            role=validated_data.get("role", User.Role.STUDENT),
        )


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = (permissions.IsAuthenticated, IsAdminRole)

    def get_serializer_class(self):
        return AdminUserCreateSerializer if self.request.method == "POST" else AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.all().order_by("-date_joined")
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
        return qs

    def create(self, request, *args, **kwargs):
        # Run through the create serializer, then return the read-shape so
        # the table row can be inserted client-side without a refetch.
        in_ser = self.get_serializer(data=request.data)
        in_ser.is_valid(raise_exception=True)
        user = in_ser.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (permissions.IsAuthenticated, IsAdminRole)
    serializer_class = AdminUserSerializer
    queryset = User.objects.all()

    def perform_destroy(self, instance):
        # Don't let an admin nuke themselves and lose access to the panel.
        if instance.id == self.request.user.id:
            raise serializers.ValidationError("You cannot delete your own account.")
        instance.delete()


# --- Activity feed ------------------------------------------------------

class ActivityView(APIView):
    """
    Heterogeneous feed: new registrations, completed lessons, reviews,
    cancellations. We pull a recent slice from each table and merge them
    in Python — fine for an admin dashboard's small page size.
    """
    permission_classes = (permissions.IsAuthenticated, IsAdminRole)

    def get(self, request):
        limit = int(request.query_params.get("limit", 20))
        per_kind = max(5, limit)

        items = []

        for u in User.objects.order_by("-date_joined")[:per_kind]:
            items.append({
                "kind": "registration",
                "at": u.date_joined,
                "title": "New registration",
                "subtitle": f"{u.get_role_display()}: {u.username}",
            })

        completed = (Lesson.objects
                     .filter(status=Lesson.Status.COMPLETED)
                     .select_related("student", "teacher")
                     .order_by("-updated_at")[:per_kind])
        for l in completed:
            items.append({
                "kind": "lesson_completed",
                "at": l.updated_at,
                "title": "Lesson completed",
                "subtitle": f"{l.teacher.username} → {l.student.username}",
            })

        for r in Review.objects.select_related("lesson__teacher").order_by("-created_at")[:per_kind]:
            items.append({
                "kind": "review",
                "at": r.created_at,
                "title": f"New review · {r.rating}★",
                "subtitle": (r.comment[:80] + "…") if r.comment and len(r.comment) > 80 else (r.comment or f"For {r.lesson.teacher.username}"),
            })

        cancelled = (Lesson.objects
                     .filter(status=Lesson.Status.CANCELLED)
                     .select_related("student", "teacher")
                     .order_by("-updated_at")[:per_kind])
        for l in cancelled:
            items.append({
                "kind": "lesson_cancelled",
                "at": l.updated_at,
                "title": "Lesson cancelled",
                "subtitle": f"{l.teacher.username} · {l.student.username}",
            })

        items.sort(key=lambda x: x["at"], reverse=True)
        return Response(items[:limit])


# --- Schedule (all lessons across the platform) -------------------------

class AdminLessonListView(generics.ListAPIView):
    """
    Platform-wide list of lessons for the admin Schedule page.

    Query params (all optional):
        ?status=pending|confirmed|completed|cancelled|declined
        ?teacher=<user_id>
        ?student=<user_id>
        ?date_from=YYYY-MM-DD        inclusive lower bound on scheduled_at
        ?date_to=YYYY-MM-DD          inclusive upper bound (treats date as end-of-day)
    """
    permission_classes = (permissions.IsAuthenticated, IsAdminRole)
    serializer_class = LessonSerializer

    def get_queryset(self):
        qs = Lesson.objects.select_related("student", "teacher").order_by("scheduled_at")

        params = self.request.query_params
        status_v = params.get("status")
        if status_v:
            qs = qs.filter(status=status_v)
        teacher_id = params.get("teacher")
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        student_id = params.get("student")
        if student_id:
            qs = qs.filter(student_id=student_id)

        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(scheduled_at__date__gte=date_from)
        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(scheduled_at__date__lte=date_to)

        return qs


# --- Progress / analytics ----------------------------------------------

class AdminProgressView(APIView):
    """
    Platform-wide analytics for the admin Progress page.

    All metrics are computed in a single request — the dataset is small
    enough that grouping/aggregating in Postgres is faster than splitting
    this across multiple round trips.

    Response shape:
        {
            "totals": {
                "lessons": int,
                "completed": int,
                "cancelled": int,
                "completion_rate": int,   # percent
                "avg_rating": float | None,
                "active_students": int,    # students with >=1 lesson in last 30d
            },
            "by_status": { "<status>": count, ... },
            "daily": [ { "date": "YYYY-MM-DD", "completed": int, "cancelled": int, "other": int }, ... ],   # last 30 days
            "top_teachers": [ { "id", "username", "completed", "avg_rating" }, ... ],
            "top_students": [ { "id", "username", "completed", "streak" }, ... ],
            "recent_reviews": [ { "rating", "comment", "student", "teacher", "at" }, ... ],
        }
    """
    permission_classes = (permissions.IsAuthenticated, IsAdminRole)

    def get(self, request):
        now = timezone.now()
        month_ago = now - timedelta(days=30)

        # --- Totals ---
        lessons_total   = Lesson.objects.count()
        completed_total = Lesson.objects.filter(status=Lesson.Status.COMPLETED).count()
        cancelled_total = Lesson.objects.filter(status=Lesson.Status.CANCELLED).count()
        # Completion rate is over lessons that have reached a terminal state —
        # excluding pending/confirmed avoids dragging the number down with
        # bookings that simply haven't happened yet.
        terminal = completed_total + cancelled_total + Lesson.objects.filter(
            status=Lesson.Status.DECLINED
        ).count()
        completion_rate = round(completed_total / terminal * 100) if terminal else 0

        avg_rating = Review.objects.aggregate(v=Avg("rating"))["v"]
        avg_rating = round(avg_rating, 2) if avg_rating is not None else None

        active_students = (
            Lesson.objects
            .filter(scheduled_at__gte=month_ago)
            .values("student_id").distinct().count()
        )

        # --- By status ---
        by_status_rows = (
            Lesson.objects.values("status").annotate(n=Count("id"))
        )
        by_status = {row["status"]: row["n"] for row in by_status_rows}

        # --- Daily series (last 30 days) ---
        daily_rows = (
            Lesson.objects
            .filter(scheduled_at__gte=month_ago)
            .annotate(d=TruncDate("scheduled_at"))
            .values("d", "status")
            .annotate(n=Count("id"))
        )
        daily_map = {}
        for row in daily_rows:
            key = row["d"].isoformat()
            bucket = daily_map.setdefault(key, {"date": key, "completed": 0, "cancelled": 0, "other": 0})
            if row["status"] == Lesson.Status.COMPLETED:
                bucket["completed"] += row["n"]
            elif row["status"] == Lesson.Status.CANCELLED:
                bucket["cancelled"] += row["n"]
            else:
                bucket["other"] += row["n"]
        # Fill in zero-days so the chart x-axis is continuous.
        daily = []
        for i in range(29, -1, -1):
            d = (now - timedelta(days=i)).date().isoformat()
            daily.append(daily_map.get(d, {"date": d, "completed": 0, "cancelled": 0, "other": 0}))

        # --- Top teachers ---
        teacher_rows = (
            User.objects
            .filter(role=User.Role.TEACHER)
            .annotate(
                completed=Count(
                    "teacher_lessons",
                    filter=Q(teacher_lessons__status=Lesson.Status.COMPLETED),
                ),
                avg_rating=Avg("teacher_lessons__review__rating"),
            )
            .filter(completed__gt=0)
            .order_by("-completed", "-avg_rating")[:5]
        )
        top_teachers = [
            {
                "id": t.id,
                "username": t.username,
                "completed": t.completed,
                "avg_rating": round(t.avg_rating, 2) if t.avg_rating else None,
            }
            for t in teacher_rows
        ]

        # --- Top students ---
        student_rows = (
            User.objects
            .filter(role=User.Role.STUDENT)
            .select_related("student_profile")
            .annotate(
                completed=Count(
                    "student_lessons",
                    filter=Q(student_lessons__status=Lesson.Status.COMPLETED),
                ),
            )
            .filter(completed__gt=0)
            .order_by("-completed")[:5]
        )
        top_students = [
            {
                "id": s.id,
                "username": s.username,
                "completed": s.completed,
                "streak": getattr(getattr(s, "student_profile", None), "streak", 0),
            }
            for s in student_rows
        ]

        # --- Recent reviews ---
        review_rows = (
            Review.objects
            .select_related("lesson__student", "lesson__teacher")
            .order_by("-created_at")[:5]
        )
        recent_reviews = [
            {
                "rating": r.rating,
                "comment": r.comment or "",
                "student": r.lesson.student.username,
                "teacher": r.lesson.teacher.username,
                "at": r.created_at,
            }
            for r in review_rows
        ]

        return Response({
            "totals": {
                "lessons":         lessons_total,
                "completed":       completed_total,
                "cancelled":       cancelled_total,
                "completion_rate": completion_rate,
                "avg_rating":      avg_rating,
                "active_students": active_students,
            },
            "by_status":      by_status,
            "daily":          daily,
            "top_teachers":   top_teachers,
            "top_students":   top_students,
            "recent_reviews": recent_reviews,
        })
