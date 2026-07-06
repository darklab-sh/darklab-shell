"""Audit-event retention and disabled-state startup warning."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Mapping

from config import resolve_effective_cfg
from core.database_access import get_db_connect

log = logging.getLogger("shell")

AUDIT_RETENTION_DEFAULT_DAYS = 90
AUDIT_RETENTION_CHECK_INTERVAL_SECONDS = 86400.0

_disabled_warning_emitted = False
_last_retention_check_monotonic = 0.0


def _cfg(cfg: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return resolve_effective_cfg(cfg)


def audit_log_enabled(cfg: Mapping[str, Any] | None = None) -> bool:
    return bool(_cfg(cfg).get("audit_log_enabled", True))


def audit_retention_days(cfg: Mapping[str, Any] | None = None) -> int:
    raw = _cfg(cfg).get("audit_retention_days")
    if raw in ("", None):
        return AUDIT_RETENTION_DEFAULT_DAYS
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return AUDIT_RETENTION_DEFAULT_DAYS


def audit_export_max_rows(cfg: Mapping[str, Any] | None = None) -> int:
    raw = _cfg(cfg).get("audit_export_max_rows")
    if raw in ("", None):
        return 10000
    try:
        parsed = max(1, int(raw))
    except (TypeError, ValueError):
        parsed = 10000
    return min(parsed, 200000)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _managed_connection(conn=None):
    if conn is not None:
        yield conn, False
        return
    with get_db_connect()() as opened:
        yield opened, True


def warn_if_disabled(cfg: Mapping[str, Any] | None = None) -> None:
    global _disabled_warning_emitted
    if _disabled_warning_emitted or audit_log_enabled(cfg):
        return
    log.warning(
        "AUDIT_LOG_DISABLED",
        extra={"audit_log_enabled": False, "effect": "audit recorder no-op; product writes continue"},
    )
    _disabled_warning_emitted = True


def prune_events(conn=None, *, now: str | None = None, cfg: Mapping[str, Any] | None = None) -> int:
    retention_days = audit_retention_days(cfg)
    if retention_days <= 0:
        return 0
    current = now or _utc_now()
    cutoff = (datetime.fromisoformat(current) - timedelta(days=retention_days)).isoformat()
    with _managed_connection(conn) as (active_conn, owns_conn):
        cur = active_conn.execute("DELETE FROM audit_events WHERE created < ?", (cutoff,))
        pruned = int(getattr(cur, "rowcount", 0) or 0)
        if owns_conn:
            active_conn.commit()
    if pruned:
        log.info("AUDIT_EVENTS_PRUNED", extra={"count": pruned, "retention_days": retention_days})
    return pruned


def maybe_prune_events(
    conn=None,
    *,
    now: str | None = None,
    monotonic_now: float | None = None,
    cfg: Mapping[str, Any] | None = None,
) -> int:
    global _last_retention_check_monotonic
    current_monotonic = time.monotonic() if monotonic_now is None else float(monotonic_now)
    elapsed = current_monotonic - _last_retention_check_monotonic
    if elapsed < AUDIT_RETENTION_CHECK_INTERVAL_SECONDS:
        return 0
    _last_retention_check_monotonic = current_monotonic
    return prune_events(conn=conn, now=now, cfg=cfg)
