"""
Signals make Django call our code automatically when a model is saved.
We use this so that whenever a User is created, the matching profile row
(StudentProfile or TeacherProfile) is created too — no manual step needed.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, StudentProfile, TeacherProfile


@receiver(post_save, sender=User)
def create_role_profile(sender, instance: User, created: bool, **kwargs):
    # `created` is True only on insert, not on every update — so we don't
    # try to recreate the profile every time the user is edited.
    if not created:
        return

    if instance.role == User.Role.STUDENT:
        StudentProfile.objects.create(user=instance)
    elif instance.role == User.Role.TEACHER:
        TeacherProfile.objects.create(user=instance)
    # Admins don't need a profile row.
