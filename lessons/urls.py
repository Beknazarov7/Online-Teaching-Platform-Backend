from django.urls import path

from .views import (
    AvailableSlotListView,
    TeacherSlotListCreateView,
    TeacherSlotDetailView,
    TeacherSlotBulkCreateView,
    LessonListBookView,
    ConfirmLessonView,
    DeclineLessonView,
    CancelLessonView,
)

urlpatterns = [
    # Slot listing / management
    path("slots/",                  AvailableSlotListView.as_view(),     name="slot-list"),
    path("teacher/slots/",          TeacherSlotListCreateView.as_view(), name="teacher-slot-list-create"),
    path("teacher/slots/bulk/",     TeacherSlotBulkCreateView.as_view(), name="teacher-slot-bulk"),
    path("teacher/slots/<int:pk>/", TeacherSlotDetailView.as_view(),     name="teacher-slot-detail"),

    # Lessons
    path("lessons/",                       LessonListBookView.as_view(), name="lesson-list-book"),
    path("lessons/<int:pk>/confirm/",      ConfirmLessonView.as_view(),  name="lesson-confirm"),
    path("lessons/<int:pk>/decline/",      DeclineLessonView.as_view(),  name="lesson-decline"),
    path("lessons/<int:pk>/cancel/",       CancelLessonView.as_view(),   name="lesson-cancel"),
]
