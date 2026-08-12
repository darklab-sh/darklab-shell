# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalized configuration boundary for the optional ZAP connector."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from config import resolve_effective_cfg


class ZapConnectorUnavailable(RuntimeError):
    """Raised when a configured ZAP connector can't be used safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ZapConnectorSettings:
    enabled: bool
    base_url: str
    api_key_secret_id: str
    tls_verify: bool
    allowed_target_cidrs: tuple[str, ...]
    scope_policy_url: str
    scope_policy_token_secret_id: str
    scope_policy_id: str
    egress_proxy_host: str
    egress_proxy_port: int
    max_concurrent_jobs: int
    job_timeout_seconds: int
    max_report_bytes: int


def zap_connector_settings(cfg: Mapping[str, Any] | None = None) -> ZapConnectorSettings:
    """Return the normalized, non-secret ZAP connector settings."""
    raw = resolve_effective_cfg(cfg).get("zap_connector")
    active = raw if isinstance(raw, Mapping) else {}
    raw_cidrs = active.get("allowed_target_cidrs")
    cidrs = raw_cidrs if isinstance(raw_cidrs, (list, tuple)) else []
    base_url = str(active.get("base_url") or "").strip().rstrip("/")
    if base_url and urlsplit(base_url).scheme not in {"http", "https"}:
        raise ZapConnectorUnavailable(
            "zap_base_url_invalid", "The configured ZAP origin must use HTTP or HTTPS",
        )
    settings = ZapConnectorSettings(
        enabled=bool(active.get("enabled", False)),
        base_url=base_url,
        api_key_secret_id=str(active.get("api_key_secret_id") or "").strip(),
        tls_verify=bool(active.get("tls_verify", True)),
        allowed_target_cidrs=tuple(str(value) for value in cidrs),
        scope_policy_url=str(active.get("scope_policy_url") or "").strip(),
        scope_policy_token_secret_id=str(
            active.get("scope_policy_token_secret_id") or ""
        ).strip(),
        scope_policy_id=str(active.get("scope_policy_id") or "").strip(),
        egress_proxy_host=str(active.get("egress_proxy_host") or "").strip().lower(),
        egress_proxy_port=int(active.get("egress_proxy_port") or 0),
        max_concurrent_jobs=int(active.get("max_concurrent_jobs") or 1),
        job_timeout_seconds=int(active.get("job_timeout_seconds") or 1800),
        max_report_bytes=int(active.get("max_report_bytes") or 10485760),
    )
    if settings.enabled:
        try:
            policy = urlsplit(settings.scope_policy_url)
            policy_port = policy.port
        except ValueError:
            policy = urlsplit("")
            policy_port = None
        if (
            policy.scheme != "https"
            or policy.path != "/v1/zap-scope/review"
            or not policy.hostname
            or policy.username is not None
            or policy.password is not None
            or policy.query
            or policy.fragment
            or (policy_port is None and policy.netloc.endswith(":"))
            or not settings.scope_policy_token_secret_id
            or not settings.scope_policy_id
            or not settings.egress_proxy_host
            or not 1 <= settings.egress_proxy_port <= 65535
        ):
            raise ZapConnectorUnavailable(
                "zap_scope_policy_invalid",
                "ZAP scanner-side scope enforcement is not configured safely",
            )
    return settings


def resolve_zap_api_key(settings: ZapConnectorSettings, *, environ: Mapping[str, str] | None = None) -> str:
    """Resolve the API key only at the connector call boundary."""
    if not settings.enabled:
        raise ZapConnectorUnavailable("zap_connector_disabled", "ZAP connector is disabled")
    source = os.environ if environ is None else environ
    api_key = str(source.get(settings.api_key_secret_id) or "")
    if not api_key:
        raise ZapConnectorUnavailable(
            "zap_api_key_unavailable",
            "The configured ZAP API key is unavailable",
        )
    return api_key


def resolve_zap_scope_policy_token(
    settings: ZapConnectorSettings,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the scanner-side scope-policy token only at its call boundary."""
    if not settings.enabled:
        raise ZapConnectorUnavailable("zap_connector_disabled", "ZAP connector is disabled")
    source = os.environ if environ is None else environ
    token = str(source.get(settings.scope_policy_token_secret_id) or "")
    if not token:
        raise ZapConnectorUnavailable(
            "zap_scope_policy_token_unavailable",
            "The configured ZAP scope-policy token is unavailable",
        )
    return token
