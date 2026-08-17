# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared HTTP helpers for notification channels."""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from services.notifications import notification_cfg
from services.notifications.models import ChannelResult

log = logging.getLogger("shell")

DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_TEST_TIMEOUT_SECONDS = 4.0
_LOCALHOST_NAMES = {"localhost", "localhost.localdomain"}


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


def timeout_seconds(config: dict[str, Any], *, test_send: bool = False) -> float:
    cfg = notification_cfg()
    if test_send:
        raw = cfg.get("test_timeout_seconds", DEFAULT_TEST_TIMEOUT_SECONDS)
        default = DEFAULT_TEST_TIMEOUT_SECONDS
    else:
        raw = config.get("timeout_seconds", cfg.get("http_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        default = DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1.0, min(60.0, float(raw)))
    except (TypeError, ValueError):
        return default


def _private_host_allowlist() -> tuple[str, ...]:
    raw = notification_cfg().get("http_private_host_allowlist", ())
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list | tuple | set):
        values = list(raw)
    else:
        values = []
    return tuple(str(value).strip().lower() for value in values if str(value or "").strip())


def _host_is_allowlisted(hostname: str, ip_address: ipaddress._BaseAddress | None = None) -> bool:
    normalized_host = str(hostname or "").strip().lower().rstrip(".")
    for entry in _private_host_allowlist():
        if normalized_host and normalized_host == entry.rstrip("."):
            return True
        if ip_address is None:
            continue
        try:
            if ip_address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def _unsafe_address(ip_text: str) -> ipaddress._BaseAddress | None:
    try:
        address = ipaddress.ip_address(ip_text)
    except ValueError:
        return None
    return address if not address.is_global else None


def _safe_log_host(parsed_url) -> str:
    host = str(parsed_url.hostname or "").strip().lower().rstrip(".")
    if not host:
        return ""
    if parsed_url.port:
        return f"{host}:{parsed_url.port}"
    return host


def validate_http_url(url: str, label: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return f"{label} URL must be an absolute http(s) URL"
    hostname = str(parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        return f"{label} URL must include a hostname"
    if hostname in _LOCALHOST_NAMES or hostname.endswith(".localhost"):
        return f"{label} URL host is not allowed"
    literal_address = _unsafe_address(hostname)
    if literal_address is not None and not _host_is_allowlisted(hostname, literal_address):
        return f"{label} URL host is not allowed"
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        infos = []
    for info in infos:
        address_text = str(info[4][0])
        resolved_address = _unsafe_address(address_text)
        if resolved_address is not None and not _host_is_allowlisted(hostname, resolved_address):
            return f"{label} URL host is not allowed"
    return None


def post_json(
    url: str,
    payload: dict[str, Any],
    config: dict[str, Any],
    *,
    label: str,
    test_send: bool = False,
) -> ChannelResult:
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
        test_send=test_send,
    )


def post_form(
    url: str,
    payload: dict[str, Any],
    config: dict[str, Any],
    *,
    label: str,
    test_send: bool = False,
) -> ChannelResult:
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
        test_send=test_send,
    )


def _post(
    url: str,
    body: bytes,
    config: dict[str, Any],
    *,
    label: str,
    content_type: str,
    test_send: bool = False,
) -> ChannelResult:
    timeout = timeout_seconds(config, test_send=test_send)
    parsed_url = urlparse(url)
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
    log.debug(
        "NOTIFICATION_HTTP_REQUEST",
        extra={"label": label, "host": _safe_log_host(parsed_url), "timeout": timeout, "test_send": test_send},
    )
    try:
        with _open_http_request(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
    except HTTPError as exc:
        log.debug(
            "NOTIFICATION_HTTP_RESPONSE",
            extra={"label": label, "http_status": int(exc.code), "test_send": test_send},
        )
        return result_for_http_status(exc.code, label=label)
    except (TimeoutError, socket.timeout, URLError) as exc:
        log.warning(
            "NOTIFICATION_HTTP_NETWORK_ERROR",
            extra={"label": label, "host": _safe_log_host(parsed_url), "error": network_error_message(exc, label=label)},
        )
        return ChannelResult.retry(network_error_message(exc, label=label))
    log.debug(
        "NOTIFICATION_HTTP_RESPONSE",
        extra={"label": label, "http_status": status, "test_send": test_send},
    )
    return result_for_http_status(status, label=label)


def _open_http_request(request: Request, *, timeout: float):
    return urlopen(request, timeout=timeout)


def urlopen(request: Request, *, timeout: float):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)  # nosec


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
