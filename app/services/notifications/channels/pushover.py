# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Pushover notification channel."""

from __future__ import annotations

from typing import Any

from services.notifications.base import Channel
from services.notifications.channels._format import format_plain_text, notification_title
from services.notifications.channels._http import post_form
from services.notifications.models import ChannelResult
from services.notifications.secrets import first_secret_ref, get_channel_secret

PUSHOVER_MESSAGE_URL = "https://api.pushover.net/1/messages.json"
PUSHOVER_APP_TOKEN_SECRET_KEYS = ("app_token", "token")
PUSHOVER_USER_KEY_SECRET_KEYS = ("user_key", "user")


def _secret_name(secrets: dict[str, Any], keys: tuple[str, ...]) -> str:
    return first_secret_ref(secrets, keys)


def _optional_config(config: dict[str, Any], key: str) -> str:
    return str(config.get(key) or "").strip()


class PushoverChannel(Channel):
    """Send notifications through Pushover's message endpoint."""

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not _secret_name(self.channel.secrets, PUSHOVER_APP_TOKEN_SECRET_KEYS):
            errors.append("Pushover app token secret is required")
        if not _secret_name(self.channel.secrets, PUSHOVER_USER_KEY_SECRET_KEYS):
            errors.append("Pushover user key secret is required")
        priority = str(config.get("priority") or "").strip()
        if priority:
            try:
                int(priority)
            except ValueError:
                errors.append("Pushover priority must be an integer")
        return errors

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        app_token_secret = _secret_name(self.channel.secrets, PUSHOVER_APP_TOKEN_SECRET_KEYS)
        user_key_secret = _secret_name(self.channel.secrets, PUSHOVER_USER_KEY_SECRET_KEYS)
        if not app_token_secret or not user_key_secret:
            return ChannelResult.terminal("Pushover app token and user key secrets are unavailable")
        app_token = get_channel_secret(self.channel.secret_owner_token, app_token_secret)
        user_key = get_channel_secret(self.channel.secret_owner_token, user_key_secret)
        if not app_token or not user_key:
            return ChannelResult.terminal("Pushover app token and user key secrets are unavailable")

        fields = {
            "token": app_token,
            "user": user_key,
            "title": notification_title(payload),
            "message": format_plain_text(payload),
            "priority": _optional_config(self.channel.config, "priority"),
            "sound": _optional_config(self.channel.config, "sound"),
            "device": _optional_config(self.channel.config, "device"),
        }
        return post_form(
            PUSHOVER_MESSAGE_URL,
            fields,
            self.channel.config,
            label="pushover",
            test_send=str(payload.get("trigger") or "") == "test",
        )
