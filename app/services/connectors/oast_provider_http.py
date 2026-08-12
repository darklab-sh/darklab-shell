# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fixed, bounded HTTP boundary for the private OAST provider."""

from __future__ import annotations

from collections.abc import Mapping
import json
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from services.connectors.oast_config import OastConnectorSettings
from services.connectors.oast_provider_contracts import OastProviderTransportError


_ALLOWED_ENDPOINTS = frozenset({"/register", "/poll", "/deregister"})
_MAX_POLL_BYTES = 1048576
_MAX_TOKEN_CHARS = 4096
_TIMEOUT_SECONDS = 30


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def _open_oast_request(
    request: Request,
    *,
    settings: OastConnectorSettings,
    timeout: int,
):
    handlers: list[Any] = [_RejectRedirects()]
    if urlsplit(settings.base_url).scheme == "https":
        context = ssl.create_default_context()
        if not settings.tls_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        handlers.append(HTTPSHandler(context=context))
    return build_opener(*handlers).open(request, timeout=timeout)  # nosec B310


def _review_token(token: str) -> str:
    value = str(token or "")
    if not value or len(value) > _MAX_TOKEN_CHARS or "\r" in value or "\n" in value:
        raise OastProviderTransportError(
            "oast_provider_token_invalid",
            "The private OAST provider token is invalid",
        )
    return value


def request_oast_provider_bytes(
    settings: OastConnectorSettings,
    token: str,
    endpoint: str,
    *,
    method: str,
    body: Mapping[str, str] | None = None,
    query: Mapping[str, str] | None = None,
    max_bytes: int,
) -> bytes:
    """Call one fixed provider endpoint and return a size-limited body."""
    if not settings.enabled or not settings.base_url:
        raise OastProviderTransportError(
            "oast_connector_disabled",
            "Private OAST connector is disabled",
        )
    if endpoint not in _ALLOWED_ENDPOINTS:
        raise OastProviderTransportError(
            "oast_provider_endpoint_invalid",
            "The private OAST provider endpoint is not allowed",
        )
    encoded_query = urlencode(dict(query or {}))
    url = f"{settings.base_url}{endpoint}" + (
        f"?{encoded_query}" if encoded_query else ""
    )
    payload = None
    headers = {
        "Accept": "application/json",
        "Authorization": _review_token(token),
        "User-Agent": "darklab_shell-oast-connector/1",
    }
    if body is not None:
        payload = json.dumps(
            dict(body), ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=payload, headers=headers, method=method)
    limit = max(1, min(int(max_bytes), _MAX_POLL_BYTES))
    try:
        with _open_oast_request(
            request,
            settings=settings,
            timeout=_TIMEOUT_SECONDS,
        ) as response:
            if urlsplit(str(response.geturl())) != urlsplit(url):
                raise OastProviderTransportError(
                    "oast_provider_redirected",
                    "The private OAST provider returned an unexpected URL",
                )
            raw_status = getattr(response, "status", None)
            status = int(response.getcode() if raw_status is None else raw_status)
            if not 200 <= status < 300:
                raise OastProviderTransportError(
                    "oast_provider_http_error",
                    f"The private OAST provider returned HTTP {status}",
                )
            response_bytes = response.read(limit + 1)
    except HTTPError as exc:
        raise OastProviderTransportError(
            "oast_provider_http_error",
            f"The private OAST provider returned HTTP {int(exc.code)}",
        ) from None
    except (TimeoutError, socket.timeout, ssl.SSLError, URLError, OSError):
        raise OastProviderTransportError(
            "oast_provider_unavailable",
            "The private OAST provider is unavailable",
        ) from None
    if len(response_bytes) > limit:
        raise OastProviderTransportError(
            "oast_provider_response_too_large",
            "The private OAST provider response exceeds the size limit",
        )
    return response_bytes


__all__ = ["request_oast_provider_bytes"]
