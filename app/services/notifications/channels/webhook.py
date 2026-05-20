"""Generic JSON webhook notification channel."""

from __future__ import annotations

from typing import Any

from services.notifications.base import Channel, register_channel
from services.notifications.channels._http import post_json
from services.notifications.models import CHANNEL_KIND_WEBHOOK, ChannelResult
from services.notifications.secrets import get_channel_secret

WEBHOOK_URL_SECRET_KEYS = ("url", "webhook_url")


def _webhook_url_secret_name(secrets: dict[str, Any]) -> str:
    for key in WEBHOOK_URL_SECRET_KEYS:
        value = str(secrets.get(key) or "").strip()
        if value:
            return value
    return ""


class WebhookChannel(Channel):
    """Send notification payloads to a vault-backed JSON webhook URL."""

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if not _webhook_url_secret_name(self.channel.secrets):
            errors.append("webhook URL secret is required")
        if "timeout_seconds" in config:
            raw_timeout = config.get("timeout_seconds")
            if raw_timeout is None:
                errors.append("timeout_seconds must be a number")
                return errors
            try:
                timeout = float(raw_timeout)
            except (TypeError, ValueError):
                errors.append("timeout_seconds must be a number")
            else:
                if timeout < 1 or timeout > 60:
                    errors.append("timeout_seconds must be between 1 and 60")
        return errors

    def _webhook_url(self) -> str | None:
        secret_name = _webhook_url_secret_name(self.channel.secrets)
        if not secret_name:
            return None
        return get_channel_secret(self.channel.session_token, secret_name)

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        return self._send_payload(payload, label="webhook")

    def _send_payload(self, payload: dict[str, Any], *, label: str) -> ChannelResult:
        url = self._webhook_url()
        if not url:
            return ChannelResult.terminal(f"{label} URL secret is unavailable")
        return post_json(url, payload, self.channel.config, label=label)


register_channel(CHANNEL_KIND_WEBHOOK, WebhookChannel)
