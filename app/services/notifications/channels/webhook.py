"""Generic JSON webhook notification channel."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from core import database
from services.notifications.base import Channel, register_channel
from services.notifications.models import CHANNEL_KIND_WEBHOOK, ChannelResult
from services.notifications.secrets import get_channel_secret

WEBHOOK_URL_SECRET_KEYS = ("url", "webhook_url")
DEFAULT_TIMEOUT_SECONDS = 8.0


def _notification_cfg() -> dict[str, Any]:
    cfg = database.CFG.get("notifications", {})
    return cfg if isinstance(cfg, dict) else {}


def _timeout_seconds(config: dict[str, Any]) -> float:
    raw = config.get("timeout_seconds", _notification_cfg().get("http_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(1.0, min(60.0, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _webhook_url_secret_name(secrets: dict[str, Any]) -> str:
    for key in WEBHOOK_URL_SECRET_KEYS:
        value = str(secrets.get(key) or "").strip()
        if value:
            return value
    return ""


def _validate_url(url: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "webhook URL must be an absolute http(s) URL"
    return None


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
        url = self._webhook_url()
        if not url:
            return ChannelResult.terminal("webhook URL secret is unavailable")
        url_error = _validate_url(url)
        if url_error:
            return ChannelResult.terminal(url_error)

        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "darklab_shell-notifications/1",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=_timeout_seconds(self.channel.config)) as response:  # nosec B310
                status = int(getattr(response, "status", response.getcode()))
        except HTTPError as exc:
            return _result_for_http_status(exc.code)
        except (TimeoutError, socket.timeout, URLError) as exc:
            return ChannelResult.retry(_network_error_message(exc))

        return _result_for_http_status(status)


def _network_error_message(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if reason:
        return f"webhook delivery failed: {reason}"
    return f"webhook delivery failed: {exc}"


def _result_for_http_status(status: int) -> ChannelResult:
    if 200 <= int(status) < 300:
        return ChannelResult.success()
    if 400 <= int(status) < 500:
        return ChannelResult.terminal(f"webhook returned HTTP {status}")
    return ChannelResult.retry(f"webhook returned HTTP {status}")


register_channel(CHANNEL_KIND_WEBHOOK, WebhookChannel)
