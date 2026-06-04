"""Telegram Bot API notification channel."""

from __future__ import annotations

from typing import Any

from services.notifications.base import Channel
from services.notifications.channels._format import format_plain_text
from services.notifications.channels._http import post_json
from services.notifications.models import ChannelResult
from services.notifications.secrets import first_secret_ref, get_channel_secret

TELEGRAM_TOKEN_SECRET_KEYS = ("bot_token", "token")
TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _secret_name(secrets: dict[str, Any]) -> str:
    return first_secret_ref(secrets, TELEGRAM_TOKEN_SECRET_KEYS)


class TelegramChannel(Channel):
    """Send plain-text notifications through Telegram's sendMessage endpoint."""

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not _secret_name(self.channel.secrets):
            errors.append("Telegram bot token secret is required")
        if not str(config.get("chat_id") or "").strip():
            errors.append("Telegram chat_id is required")
        return errors

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        token_secret_name = _secret_name(self.channel.secrets)
        if not token_secret_name:
            return ChannelResult.terminal("Telegram bot token secret is unavailable")
        token = get_channel_secret(self.channel.secret_owner_token, token_secret_name)
        if not token:
            return ChannelResult.terminal("Telegram bot token secret is unavailable")
        chat_id = str(self.channel.config.get("chat_id") or "").strip()
        if not chat_id:
            return ChannelResult.terminal("Telegram chat_id is required")

        body = {
            "chat_id": chat_id,
            "text": format_plain_text(payload),
            "disable_web_page_preview": True,
        }
        return post_json(
            TELEGRAM_SEND_MESSAGE_URL.format(token=token),
            body,
            self.channel.config,
            label="telegram",
            test_send=str(payload.get("trigger") or "") == "test",
        )
