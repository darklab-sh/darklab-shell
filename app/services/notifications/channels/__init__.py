# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Built-in outbound notification channel registrations."""

from services.notifications.base import register_channel
from services.notifications.channels.discord import DiscordChannel
from services.notifications.channels.email import EmailChannel
from services.notifications.channels.pushover import PushoverChannel
from services.notifications.channels.slack import SlackChannel
from services.notifications.channels.telegram import TelegramChannel
from services.notifications.channels.webhook import WebhookChannel
from services.notifications.models import (
    CHANNEL_KIND_DISCORD,
    CHANNEL_KIND_EMAIL,
    CHANNEL_KIND_PUSHOVER,
    CHANNEL_KIND_SLACK,
    CHANNEL_KIND_TELEGRAM,
    CHANNEL_KIND_WEBHOOK,
)


def register_builtin_channels() -> None:
    """Register all built-in notification channel implementations."""
    register_channel(CHANNEL_KIND_WEBHOOK, WebhookChannel)
    register_channel(CHANNEL_KIND_SLACK, SlackChannel)
    register_channel(CHANNEL_KIND_DISCORD, DiscordChannel)
    register_channel(CHANNEL_KIND_TELEGRAM, TelegramChannel)
    register_channel(CHANNEL_KIND_PUSHOVER, PushoverChannel)
    register_channel(CHANNEL_KIND_EMAIL, EmailChannel)


register_builtin_channels()


__all__ = [
    "DiscordChannel",
    "EmailChannel",
    "PushoverChannel",
    "SlackChannel",
    "TelegramChannel",
    "WebhookChannel",
    "register_builtin_channels",
]
