"""
Celery application bootstrap.

Celery runs *outside* the Django request/response cycle. It connects to a
broker (Redis here) where Django publishes "task messages", and worker
processes pull those messages and run the matching @shared_task function.

Typical local dev setup needs three terminals:
    1) `python manage.py runserver`              — the API
    2) `celery -A backend worker -l info`        — the worker that runs tasks
    3) `redis-server` (already running as a service)

We DON'T need celery-beat for Phase 2 because we schedule each reminder
explicitly via `apply_async(eta=...)` when a lesson is confirmed.
"""
import os
from celery import Celery

# Tell Celery which settings module to use BEFORE we instantiate the app —
# otherwise it can't read CELERY_* config.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

app = Celery("backend")

# Pull every CELERY_* setting from Django settings.py (the namespace= arg
# means we only have to write CELERY_BROKER_URL, not the prefix-less form).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py inside each installed app — that's how
# `lessons/tasks.py` gets picked up without us importing it explicitly.
app.autodiscover_tasks()
