"""Structured audit events for external intel provider lookups."""

from __future__ import annotations

import logging
from typing import Any

from core.helpers import get_log_session_id

log = logging.getLogger("shell")


def emit_intel_lookup(
    session_id: str,
    provider: str,
    entity_type: str,
    *,
    run_id: str = "",
    cache_hit: bool = False,
    http_status: int | str = "",
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "session": get_log_session_id(session_id),
        "provider": str(provider or "").strip().lower(),
        "entity_type": str(entity_type or "").strip().lower(),
        "cache_hit": bool(cache_hit),
    }
    if run_id:
        payload["run_id"] = run_id
    if http_status != "":
        payload["http_status"] = http_status
    payload.update(extra)
    payload.pop("api_key", None)
    payload.pop("response_body", None)
    log.info("INTEL_LOOKUP", extra=payload)
