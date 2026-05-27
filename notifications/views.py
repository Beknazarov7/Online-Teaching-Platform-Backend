"""
Telegram-link API endpoints.

Two operations:
    POST   /api/me/telegram/link/    — create a fresh one-time code
    DELETE /api/me/telegram/link/    — remove the linked telegram_id

Linking itself happens in the bot: the user types /start <code>, the bot
finds the matching TelegramLinkCode row and writes user.telegram_id.
"""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TelegramLinkCode
from .serializers import TelegramLinkCodeSerializer


class TelegramLinkView(APIView):
    """
    POST   -> issue a new code (invalidates any previous one for this user)
    DELETE -> unlink (clear telegram_id and any pending codes)
    """
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        # One active code per user — kill old ones to keep the table clean
        # and avoid users having multiple working codes at once.
        TelegramLinkCode.objects.filter(user=request.user).delete()
        code = TelegramLinkCode.objects.create(user=request.user)
        return Response(
            TelegramLinkCodeSerializer(code).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        user = request.user
        user.telegram_id = None
        user.save(update_fields=["telegram_id"])
        TelegramLinkCode.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
