# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Non-secret configuration boundary for the optional private OAST connector."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from config import resolve_effective_cfg


class OastConnectorUnavailable(RuntimeError):
    """Raised when the private OAST connector isn't available for explicit use."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OastConnectorSettings:
    enabled: bool
    base_url: str
    token_secret_id: str
    allowed_domain: str
    tls_verify: bool
    callback_retention_seconds: int
    privacy_acknowledged: bool


def oast_connector_settings(
    cfg: Mapping[str, Any] | None = None,
) -> OastConnectorSettings:
    """Return the normalized connector settings without resolving its token."""
    raw = resolve_effective_cfg(cfg).get("oast_connector")
    active = raw if isinstance(raw, Mapping) else {}
    return OastConnectorSettings(
        enabled=bool(active.get("enabled", False)),
        base_url=str(active.get("base_url") or "").strip().rstrip("/"),
        token_secret_id=str(active.get("token_secret_id") or "").strip(),
        allowed_domain=str(active.get("allowed_domain") or "").strip().lower().rstrip("."),
        tls_verify=bool(active.get("tls_verify", True)),
        callback_retention_seconds=int(active.get("callback_retention_seconds") or 604800),
        privacy_acknowledged=bool(active.get("privacy_acknowledged", False)),
    )


def resolve_oast_token(
    settings: OastConnectorSettings,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the private token only at a future explicit connector call boundary."""
    if not settings.enabled:
        raise OastConnectorUnavailable(
            "oast_connector_disabled",
            "Private OAST connector is disabled",
        )
    if not settings.privacy_acknowledged:
        raise OastConnectorUnavailable(
            "oast_privacy_acknowledgement_required",
            "Private OAST use requires the operator privacy acknowledgement",
        )
    source = os.environ if environ is None else environ
    token = str(source.get(settings.token_secret_id) or "")
    if not token:
        raise OastConnectorUnavailable(
            "oast_token_unavailable",
            "The configured private OAST token is unavailable",
        )
    return token
