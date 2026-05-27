from django.urls import path

from .views import TelegramLinkView

urlpatterns = [
    path("me/telegram/link/", TelegramLinkView.as_view(), name="telegram-link"),
]
