"""
URL routes for the users app.
The root urls.py will `include('users.urls')` under /api/, so the final paths
become /api/auth/register/ and /api/users/me/.
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import RegisterView, MeView
from .admin_views import (
    StatsView,
    UserListCreateView,
    UserDetailView,
    ActivityView,
    AdminLessonListView,
)

urlpatterns = [
    # JWT auth — these come from djangorestframework-simplejwt:
    #   POST /api/auth/login/    {username, password}        -> {access, refresh}
    #   POST /api/auth/refresh/  {refresh}                   -> {access}
    path("auth/login/",    TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/",  TokenRefreshView.as_view(),    name="token_refresh"),
    path("auth/register/", RegisterView.as_view(),        name="register"),

    # Current user
    path("users/me/", MeView.as_view(), name="me"),

    # Admin
    path("admin/stats/",          StatsView.as_view(),          name="admin-stats"),
    path("admin/users/",          UserListCreateView.as_view(), name="admin-user-list"),
    path("admin/users/<int:pk>/", UserDetailView.as_view(),     name="admin-user-detail"),
    path("admin/activity/",       ActivityView.as_view(),       name="admin-activity"),
    path("admin/lessons/",        AdminLessonListView.as_view(), name="admin-lesson-list"),
]
