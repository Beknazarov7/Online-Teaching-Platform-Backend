"""
Views are the request handlers. We use DRF generic views to keep things short:
- generics.CreateAPIView         -> POST only (registration)
- generics.RetrieveUpdateAPIView -> GET/PUT/PATCH (the "me" endpoint)
"""
from rest_framework import generics, permissions

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
