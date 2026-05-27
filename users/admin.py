"""
Django admin gives us a free CRUD interface at /admin/.
Per the project plan, the admin panel for managing users, teachers, and
students is "90% done via this" — so wiring it up properly now means we
get most of the admin role's functionality with almost no UI code.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, StudentProfile, TeacherProfile


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Extend Django's default UserAdmin so password hashing in the change form
    # keeps working. We only add our extra fields to the existing layout.
    list_display = ("username", "email", "role", "telegram_id", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Platform", {"fields": ("role", "telegram_id")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Platform", {"fields": ("role", "telegram_id", "email")}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "total_lessons", "streak", "rank")
    search_fields = ("user__username", "user__email")
    list_filter = ("level",)


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("user",)
    search_fields = ("user__username", "user__email")
