# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Attested scanner-side CIDR policy boundary for ZAP target traffic."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import secrets
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from services.connectors.zap_config import (
    ZapConnectorSettings,
    resolve_zap_scope_policy_token,
)


_MAX_HOSTS = 8
_MAX_ADDRESSES = 16
_MAX_RESPONSE_BYTES = 65536
_SCHEMA_VERSION = 1


class ZapScopePolicyError(RuntimeError):
    """Raised when scanner-side egress enforcement cannot be established."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReviewedZapScopePolicy:
    policy_id: str
    allowed_target_cidrs_sha256: str
    egress_proxy_host: str
    egress_proxy_port: int
    scanner_addresses: tuple[tuple[str, tuple[str, ...]], ...]


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def allowed_target_cidrs_sha256(settings: ZapConnectorSettings) -> str:
    """Return the stable digest used to bind app and proxy CIDR policies."""
    encoded = json.dumps(
        sorted(settings.allowed_target_cidrs),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review_hosts(hosts: Sequence[str]) -> tuple[str, ...]:
    supplied = tuple(str(host or "").strip().lower() for host in hosts)
    normalized = tuple(dict.fromkeys(supplied))
    if (
        not supplied
        or len(supplied) > _MAX_HOSTS
        or any(not host for host in supplied)
    ):
        raise ZapScopePolicyError(
            "zap_scope_policy_targets_invalid",
            "ZAP scope-policy review requires between one and eight target hosts",
        )
    return normalized


def _review_proxy(value: object, settings: ZapConnectorSettings) -> None:
    if not isinstance(value, Mapping):
        raise ZapScopePolicyError(
            "zap_scope_policy_response_invalid",
            "ZAP scope-policy service returned an invalid proxy binding",
        )
    if (
        str(value.get("host") or "").strip().lower() != settings.egress_proxy_host
        or value.get("port") != settings.egress_proxy_port
    ):
        raise ZapScopePolicyError(
            "zap_scope_policy_mismatch",
            "ZAP scope-policy service does not enforce the configured egress proxy",
        )


def review_zap_scope_policy_response(
    settings: ZapConnectorSettings,
    hosts: Sequence[str],
    payload: object,
    *,
    nonce: str,
) -> ReviewedZapScopePolicy:
    """Validate one fresh scanner-vantage policy attestation."""
    reviewed_hosts = _review_hosts(hosts)
    if not isinstance(payload, Mapping):
        raise ZapScopePolicyError(
            "zap_scope_policy_response_invalid",
            "ZAP scope-policy service returned an invalid response",
        )
    expected_digest = allowed_target_cidrs_sha256(settings)
    enforcement = payload.get("enforcement")
    if (
        payload.get("schema_version") != _SCHEMA_VERSION
        or str(payload.get("nonce") or "") != nonce
        or str(payload.get("policy_id") or "") != settings.scope_policy_id
        or str(payload.get("allowed_target_cidrs_sha256") or "") != expected_digest
        or not isinstance(enforcement, Mapping)
        or enforcement.get("mode") != "cidr_proxy"
        or enforcement.get("dns_recheck") != "per_connection"
    ):
        raise ZapScopePolicyError(
            "zap_scope_policy_mismatch",
            "ZAP scope-policy attestation does not match the configured network boundary",
        )
    _review_proxy(payload.get("egress_proxy"), settings)
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or len(raw_targets) != len(reviewed_hosts):
        raise ZapScopePolicyError(
            "zap_scope_policy_response_invalid",
            "ZAP scope-policy service returned an invalid target review",
        )
    networks = tuple(ipaddress.ip_network(cidr, strict=False) for cidr in settings.allowed_target_cidrs)
    scanner_addresses: list[tuple[str, tuple[str, ...]]] = []
    for expected_host, raw_target in zip(reviewed_hosts, raw_targets, strict=True):
        if not isinstance(raw_target, Mapping):
            raise ZapScopePolicyError(
                "zap_scope_policy_response_invalid",
                "ZAP scope-policy service returned an invalid target review",
            )
        host = str(raw_target.get("host") or "").strip().lower()
        raw_addresses = raw_target.get("resolved_addresses")
        if host != expected_host or not isinstance(raw_addresses, list):
            raise ZapScopePolicyError(
                "zap_scope_policy_response_invalid",
                "ZAP scope-policy service returned an unexpected target review",
            )
        addresses = tuple(dict.fromkeys(str(value or "").strip() for value in raw_addresses))
        if not addresses or len(addresses) > _MAX_ADDRESSES or any(not value for value in addresses):
            raise ZapScopePolicyError(
                "zap_scope_policy_response_invalid",
                "ZAP scope-policy service returned an invalid address set",
            )
        try:
            parsed = tuple(ipaddress.ip_address(value) for value in addresses)
        except ValueError as exc:
            raise ZapScopePolicyError(
                "zap_scope_policy_response_invalid",
                "ZAP scope-policy service returned an invalid address",
            ) from exc
        if any(not any(address in network for network in networks) for address in parsed):
            raise ZapScopePolicyError(
                "zap_scanner_target_out_of_scope",
                "ZAP scanner-side DNS resolved a target outside the allowed networks",
            )
        scanner_addresses.append((host, tuple(str(address) for address in parsed)))
    return ReviewedZapScopePolicy(
        policy_id=settings.scope_policy_id,
        allowed_target_cidrs_sha256=expected_digest,
        egress_proxy_host=settings.egress_proxy_host,
        egress_proxy_port=settings.egress_proxy_port,
        scanner_addresses=tuple(scanner_addresses),
    )


def review_zap_scope_policy(
    settings: ZapConnectorSettings,
    hosts: Sequence[str],
    *,
    token: str = "",
) -> ReviewedZapScopePolicy:
    """Request and verify one fresh scanner-side scope-policy attestation."""
    if not settings.enabled:
        raise ZapScopePolicyError("zap_connector_disabled", "ZAP connector is disabled")
    reviewed_hosts = _review_hosts(hosts)
    secret = token or resolve_zap_scope_policy_token(settings)
    if not secret or len(secret) > 4096 or "\r" in secret or "\n" in secret:
        raise ZapScopePolicyError(
            "zap_scope_policy_token_invalid",
            "The configured ZAP scope-policy token is invalid",
        )
    nonce = secrets.token_urlsafe(24)
    request_body = json.dumps({
        "schema_version": _SCHEMA_VERSION,
        "nonce": nonce,
        "policy_id": settings.scope_policy_id,
        "allowed_target_cidrs_sha256": allowed_target_cidrs_sha256(settings),
        "egress_proxy": {
            "host": settings.egress_proxy_host,
            "port": settings.egress_proxy_port,
        },
        "targets": [{"host": host} for host in reviewed_hosts],
    }, separators=(",", ":")).encode("utf-8")
    request = Request(
        settings.scope_policy_url,
        data=request_body,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "User-Agent": "darklab_shell-zap-scope-policy/1",
        },
        method="POST",
    )
    try:
        with build_opener(ProxyHandler({}), _RejectRedirects()).open(  # nosec B310
            request,
            timeout=max(3, min(15, settings.job_timeout_seconds)),
        ) as response:
            if str(response.geturl()) != settings.scope_policy_url:
                raise ZapScopePolicyError(
                    "zap_scope_policy_redirected",
                    "ZAP scope-policy service returned an unexpected URL",
                )
            status = int(response.getcode())
            if not 200 <= status < 300:
                raise ZapScopePolicyError(
                    "zap_scope_policy_http_error",
                    f"ZAP scope-policy service returned HTTP {status}",
                )
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except ZapScopePolicyError:
        raise
    except HTTPError as exc:
        raise ZapScopePolicyError(
            "zap_scope_policy_http_error",
            f"ZAP scope-policy service returned HTTP {int(exc.code)}",
        ) from None
    except (TimeoutError, socket.timeout, ssl.SSLError, URLError, OSError):
        raise ZapScopePolicyError(
            "zap_scope_policy_unavailable",
            "ZAP scope-policy service is unavailable",
        ) from None
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ZapScopePolicyError(
            "zap_scope_policy_response_too_large",
            "ZAP scope-policy response exceeds the size limit",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZapScopePolicyError(
            "zap_scope_policy_response_invalid",
            "ZAP scope-policy service returned invalid JSON",
        ) from exc
    return review_zap_scope_policy_response(settings, reviewed_hosts, payload, nonce=nonce)


__all__ = [
    "ReviewedZapScopePolicy",
    "ZapScopePolicyError",
    "allowed_target_cidrs_sha256",
    "review_zap_scope_policy",
    "review_zap_scope_policy_response",
]
