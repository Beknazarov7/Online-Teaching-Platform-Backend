"""
Views are the request handlers. We use DRF generic views to keep things short:
- generics.CreateAPIView         -> POST only (registration)
- generics.RetrieveUpdateAPIView -> GET/PUT/PATCH (the "me" endpoint)
"""
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/  { username, email, password }
    Public — any visitor can create a student account.
    """
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)
    queryset = User.objects.all()


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/users/me/   -> current user's profile (with nested student/teacher profile)
    PATCH /api/users/me/   -> update own email or telegram_id (role is read-only)

    The user is identified from the JWT, never from a URL param, so a
    logged-in user can only ever see their own record.
    """
    serializer_class = UserSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user


class ChangePasswordSerializer(serializers.Serializer):
    """Validates the change-password payload — current + new (min 8)."""
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, min_length=8)


class ChangePasswordView(APIView):
    """
    POST /api/users/me/change-password/  { current_password, new_password }

    Verifies the current password before setting the new one. The existing
    JWT stays valid — token rotation on password change is intentionally not
    enforced (Django doesn't sign JWTs against the password hash).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(ser.validated_data["current_password"]):
            return Response(
                {"current_password": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(ser.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated."})
