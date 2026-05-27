"""
Serializers translate between Django model instances and JSON.
- "Read" usage: model -> dict -> JSON for the API response.
- "Write" usage: JSON -> validated dict -> .save() creates/updates the model.
"""
from rest_framework import serializers

from .models import User, StudentProfile, TeacherProfile


class StudentProfileSerializer(serializers.ModelSerializer):
    # Expose the computed rank as a read-only field. SerializerMethodField
    # calls get_rank(self, obj) under the hood.
    rank = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = ("level", "total_lessons", "streak", "rank")
        # total_lessons / streak are mutated by business logic (Phase 2),
        # not by direct API edits — so make them read-only here.
        read_only_fields = ("total_lessons", "streak")

    def get_rank(self, obj: StudentProfile) -> str:
        return obj.rank


class TeacherProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ("bio",)


class UserSerializer(serializers.ModelSerializer):
    """
    Returned by /api/users/me/. Nests whichever profile matches the role.
    Both nested profiles are read-only here; profile edits go through their
    own dedicated endpoints later if needed.
    """
    student_profile = StudentProfileSerializer(read_only=True)
    teacher_profile = TeacherProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "role", "telegram_id",
            "is_active", "is_superuser", "date_joined", "last_login",
            "student_profile", "teacher_profile",
        )
        read_only_fields = ("id", "role", "is_superuser", "date_joined", "last_login")


class RegisterSerializer(serializers.ModelSerializer):
    """
    Public sign-up serializer. Only allows the STUDENT role from this endpoint
    — teachers and admins are created via Django Admin to keep things safe.
    """
    # write_only means the password is accepted on input but never returned.
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data):
        # We must use create_user (not the ModelSerializer default .create)
        # so the password gets hashed instead of stored in plain text.
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            role=User.Role.STUDENT,
        )
        return user
