"""Outbound notification service primitives."""

from typing import Any

from core import database
from services.notifications.base import (
    Channel,
    channel_class_for_kind,
    register_channel,
    registered_channels,
)
from services.notifications.models import ChannelResult, NotificationChannel, NotificationEvent


def notification_cfg() -> dict[str, Any]:
    cfg = database.CFG.get("notifications", {})
    return cfg if isinstance(cfg, dict) else {}


__all__ = [
    "Channel",
    "ChannelResult",
    "NotificationChannel",
    "NotificationEvent",
    "channel_class_for_kind",
    "notification_cfg",
    "register_channel",
    "registered_channels",
]
