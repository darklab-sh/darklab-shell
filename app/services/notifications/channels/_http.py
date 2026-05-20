"""Shared HTTP helpers for notification channels."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from core import database
from services.notifications.models import ChannelResult

DEFAULT_TIMEOUT_SECONDS = 8.0


def notification_cfg() -> dict[str, Any]:
    cfg = database.CFG.get("notifications", {})
    return cfg if isinstance(cfg, dict) else {}


def timeout_seconds(config: dict[str, Any]) -> float:
    raw = config.get("timeout_seconds", notification_cfg().get("http_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    try:
        return max(1.0, min(60.0, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def validate_http_url(url: str, label: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return f"{label} URL must be an absolute http(s) URL"
    return None


def post_json(url: str, payload: dict[str, Any], config: dict[str, Any], *, label: str) -> ChannelResult:
    url_error = validate_http_url(url, label)
    if url_error:
        return ChannelResult.terminal(url_error)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _post(
        url,
        body,
        config,
        label=label,
        content_type="application/json",
    )


def post_form(url: str, payload: dict[str, Any], config: dict[str, Any], *, label: str) -> ChannelResult:
    url_error = validate_http_url(url, label)
    if url_error:
        return ChannelResult.terminal(url_error)
    body = urlencode({key: value for key, value in payload.items() if value not in ("", None)}).encode("utf-8")
    return _post(
        url,
        body,
        config,
        label=label,
        content_type="application/x-www-form-urlencoded",
    )


def _post(url: str, body: bytes, config: dict[str, Any], *, label: str, content_type: str) -> ChannelResult:
    request = Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": content_type,
            "User-Agent": "darklab_shell-notifications/1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds(config)) as response:  # nosec B310
            status = int(getattr(response, "status", response.getcode()))
    except HTTPError as exc:
        return result_for_http_status(exc.code, label=label)
    except (TimeoutError, socket.timeout, URLError) as exc:
        return ChannelResult.retry(network_error_message(exc, label=label))
    return result_for_http_status(status, label=label)


def network_error_message(exc: BaseException, *, label: str) -> str:
    reason = getattr(exc, "reason", None)
    if reason:
        return f"{label} delivery failed: {reason}"
    return f"{label} delivery failed: {exc}"


def result_for_http_status(status: int, *, label: str) -> ChannelResult:
    if 200 <= int(status) < 300:
        return ChannelResult.success()
    if 400 <= int(status) < 500:
        return ChannelResult.terminal(f"{label} returned HTTP {status}")
    return ChannelResult.retry(f"{label} returned HTTP {status}")
