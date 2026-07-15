# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Outbound notification service primitives."""

from collections.abc import Mapping
from typing import Any

from config import resolve_effective_cfg
from services.notifications.base import (
    Channel,
    channel_class_for_kind,
    register_channel,
    registered_channels,
)
from services.notifications.models import ChannelResult, NotificationChannel, NotificationEvent


def notification_cfg() -> Mapping[str, Any]:
    cfg = resolve_effective_cfg().get("notifications", {})
    return cfg if isinstance(cfg, Mapping) else {}


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
