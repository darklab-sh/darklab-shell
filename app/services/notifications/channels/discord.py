"""Discord incoming-webhook notification channel."""

from __future__ import annotations

from typing import Any

from services.notifications.base import register_channel
from services.notifications.channels._format import format_discord_payload
from services.notifications.channels.webhook import WebhookChannel
from services.notifications.models import CHANNEL_KIND_DISCORD, ChannelResult


class DiscordChannel(WebhookChannel):
    """Send notifications to Discord using an incoming webhook URL."""

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        return self._send_payload(format_discord_payload(payload), label="discord")


register_channel(CHANNEL_KIND_DISCORD, DiscordChannel)
