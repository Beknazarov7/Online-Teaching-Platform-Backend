from rest_framework import serializers

from .models import TelegramLinkCode


class TelegramLinkCodeSerializer(serializers.ModelSerializer):
    """Returned to the frontend when the user requests a fresh link code."""
    bot_username = serializers.SerializerMethodField()
    expires_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = TelegramLinkCode
        fields = ("code", "expires_at", "bot_username")
        read_only_fields = fields

    def get_bot_username(self, obj):
        from django.conf import settings
        return getattr(settings, "TELEGRAM_BOT_USERNAME", "")
