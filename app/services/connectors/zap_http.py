# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fixed, secret-safe HTTP boundary for the external ZAP API."""

from __future__ import annotations

from collections.abc import Mapping
import json
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from services.connectors.zap_config import ZapConnectorSettings


_ALLOWED_ENDPOINTS = frozenset({
    "/JSON/automation/action/runPlan/",
    "/JSON/automation/action/stopPlan/",
    "/JSON/automation/view/planProgress/",
    "/OTHER/core/other/fileDownload/",
    "/OTHER/core/other/fileUpload/",
})
_MAX_API_KEY_CHARS = 4096
_MAX_JSON_BYTES = 65536
_TIMEOUT_SECONDS = 30


class ZapTransportError(RuntimeError):
    """Raised when the ZAP transport rejects or cannot complete a request."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _open_zap_request(
    request: Request,
    *,
    settings: ZapConnectorSettings,
    timeout: int,
):
    handlers: list[Any] = [_RejectRedirects()]
    if urlsplit(settings.base_url).scheme == "https":
        context = ssl.create_default_context()
        if not settings.tls_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        handlers.append(HTTPSHandler(context=context))
    return build_opener(*handlers).open(request, timeout=timeout)  # nosec


def _request_url(
    settings: ZapConnectorSettings,
    endpoint: str,
    query: Mapping[str, str] | None,
) -> str:
    if not settings.enabled or not settings.base_url:
        raise ZapTransportError("zap_connector_disabled", "ZAP connector is disabled")
    if endpoint not in _ALLOWED_ENDPOINTS:
        raise ZapTransportError("zap_endpoint_invalid", "The ZAP API endpoint is not allowed")
    encoded = urlencode(dict(query or {}))
    return f"{settings.base_url}{endpoint}" + (f"?{encoded}" if encoded else "")


def _review_api_key(api_key: str) -> str:
    value = str(api_key or "")
    if (
        not value
        or len(value) > _MAX_API_KEY_CHARS
        or "\r" in value
        or "\n" in value
    ):
        raise ZapTransportError("zap_api_key_invalid", "The ZAP API key is invalid")
    return value


def zap_request_bytes(
    settings: ZapConnectorSettings,
    api_key: str,
    endpoint: str,
    *,
    query: Mapping[str, str] | None = None,
    form: Mapping[str, str] | None = None,
    max_bytes: int = _MAX_JSON_BYTES,
) -> bytes:
    """Call one fixed ZAP endpoint without redirects or secret-bearing URLs."""
    url = _request_url(settings, endpoint, query)
    body = urlencode(dict(form)).encode("utf-8") if form is not None else None
    headers = {
        "Accept": "application/json",
        "User-Agent": "darklab_shell-zap-connector/1",
        "X-ZAP-API-Key": _review_api_key(api_key),
    }
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    limit = max(1, min(int(max_bytes), 52428800))
    timeout = max(3, min(_TIMEOUT_SECONDS, settings.job_timeout_seconds))
    try:
        with _open_zap_request(request, settings=settings, timeout=timeout) as response:
            if urlsplit(str(response.geturl())) != urlsplit(url):
                raise ZapTransportError(
                    "zap_response_redirected",
                    "ZAP returned a response from an unexpected URL",
                )
            raw_status = getattr(response, "status", None)
            status = int(response.getcode() if raw_status is None else raw_status)
            if not 200 <= status < 300:
                raise ZapTransportError(
                    "zap_http_error",
                    f"ZAP returned HTTP {status}",
                )
            payload = response.read(limit + 1)
    except HTTPError as exc:
        raise ZapTransportError(
            "zap_http_error",
            f"ZAP returned HTTP {int(exc.code)}",
        ) from None
    except (TimeoutError, socket.timeout, ssl.SSLError, URLError, OSError):
        raise ZapTransportError(
            "zap_transport_unavailable",
            "The ZAP service is unavailable",
        ) from None
    if len(payload) > limit:
        raise ZapTransportError(
            "zap_response_too_large",
            "The ZAP response exceeds the configured size limit",
        )
    return payload


def zap_json_request(
    settings: ZapConnectorSettings,
    api_key: str,
    endpoint: str,
    *,
    query: Mapping[str, str] | None = None,
    form: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    payload = zap_request_bytes(
        settings,
        api_key,
        endpoint,
        query=query,
        form=form,
        max_bytes=_MAX_JSON_BYTES,
    )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZapTransportError(
            "zap_response_invalid",
            "ZAP returned an invalid JSON response",
        ) from exc
    if not isinstance(value, Mapping):
        raise ZapTransportError(
            "zap_response_invalid",
            "ZAP returned an invalid JSON response",
        )
    if isinstance(value.get("code"), str) and isinstance(value.get("message"), str):
        raise ZapTransportError("zap_remote_rejected", "ZAP rejected the request")
    return value


__all__ = ["ZapTransportError", "zap_json_request", "zap_request_bytes"]
