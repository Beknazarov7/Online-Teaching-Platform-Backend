"""
Root URL configuration.

We mount every app under /api/ so the React frontend (Phase 3) and the
Telegram bot (Phase 4) hit the same base path. Django's /admin/ keeps
its own non-/api root so the admin role still gets the full UI.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # API — each include() pulls in that app's urls.py file.
    path("api/", include("users.urls")),
    path("api/", include("lessons.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("notifications.urls")),
]
