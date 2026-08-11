# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Public readiness projection for private OAST provider sessions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.connectors.oast_observability import log_oast_spool_unavailable
from services.connectors.oast_provider_spool import (
    OastProviderSessionSpoolError,
    oast_provider_session_is_staged,
)


_LIVE_STATUSES = frozenset({"reserved", "active"})


def assessment_oast_provider_ready(correlation: Mapping[str, Any]) -> bool:
    if str(correlation.get("status") or "") not in _LIVE_STATUSES:
        return False
    correlation_id = str(correlation.get("id") or "")
    try:
        return oast_provider_session_is_staged(correlation_id)
    except OastProviderSessionSpoolError as exc:
        log_oast_spool_unavailable(correlation_id, exc)
        return False


__all__ = ["assessment_oast_provider_ready"]
