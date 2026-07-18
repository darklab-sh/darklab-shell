# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Channel registry and base delivery contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from services.notifications.models import CHANNEL_KINDS, ChannelResult, NotificationChannel


class Channel(ABC):
    """Base class for one notification delivery destination."""

    def __init__(self, channel: NotificationChannel):
        self.channel = channel

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        return []

    @abstractmethod
    def send(self, payload: dict[str, Any]) -> ChannelResult:
        """Deliver one payload to this channel."""


_CHANNEL_REGISTRY: dict[str, type[Channel]] = {}


def register_channel(kind: str, channel_cls: type[Channel]) -> None:
    normalized = str(kind or "").strip().lower()
    if normalized not in CHANNEL_KINDS:
        supported = ", ".join(sorted(CHANNEL_KINDS))
        raise ValueError(f"unsupported notification channel kind {kind!r}; expected one of: {supported}")
    if not issubclass(channel_cls, Channel):
        raise TypeError("channel classes must inherit services.notifications.base.Channel")
    _CHANNEL_REGISTRY[normalized] = channel_cls


def channel_class_for_kind(kind: str) -> type[Channel] | None:
    return _CHANNEL_REGISTRY.get(str(kind or "").strip().lower())


def registered_channels() -> dict[str, type[Channel]]:
    return dict(_CHANNEL_REGISTRY)


def _reset_channel_registry_for_tests() -> None:
    _CHANNEL_REGISTRY.clear()
