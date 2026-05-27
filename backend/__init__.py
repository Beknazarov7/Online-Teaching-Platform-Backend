# Importing the celery_app here means it's loaded as soon as Django starts,
# so @shared_task decorators in any app are registered against this app
# rather than a fresh default one.
from .celery import app as celery_app

__all__ = ("celery_app",)
