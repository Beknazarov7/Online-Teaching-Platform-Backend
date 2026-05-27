"""
Custom DRF permission classes — one per role.
DRF calls `has_permission(request, view)` on every protected request;
returning False causes a 403. Combine with IsAuthenticated by listing
both in `permission_classes` on the view.
"""
from rest_framework.permissions import BasePermission

from .models import User


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == User.Role.STUDENT)


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == User.Role.TEACHER)


class IsAdminRole(BasePermission):
    """
    Note: distinct from DRF's built-in IsAdminUser, which checks `is_staff`.
    This one checks our custom `role` field. Superusers also pass.
    """
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return u.role == User.Role.ADMIN or u.is_superuser
