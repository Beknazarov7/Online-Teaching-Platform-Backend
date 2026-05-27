from django.urls import path

from .views import LessonReportListCreateView, ReviewListCreateView

urlpatterns = [
    path("reports/", LessonReportListCreateView.as_view(), name="report-list-create"),
    path("reviews/", ReviewListCreateView.as_view(),       name="review-list-create"),
]
