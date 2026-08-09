# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Guarded activation, closure, expiry, and cleanup for OAST reservations."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from services.connectors.oast_correlations import (
    OastCorrelationError,
    _connection_scope,
    _decode_row,
    _owner_predicate,
    _utc_now,
)


_RUN_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


def activate_oast_correlation(
    session_id: str,
    correlation_id: str,
    run_id: str,
    *,
    team_id: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Bind a reserved callback to the exact run created for its action."""
    selected_run_id = str(run_id or "").strip().lower()
    if not _RUN_ID_RE.fullmatch(selected_run_id):
        raise OastCorrelationError(
            "oast_correlation_run_invalid", "The OAST source run id is invalid"
        )
    instant = _utc_now(now).isoformat()
    owner_sql, owner_params = _owner_predicate(
        str(session_id or ""), str(team_id or "")
    )
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        current = active_conn.execute(
            "SELECT check_id FROM oast_correlations WHERE id = ? AND " + owner_sql,  # nosec B608
            (correlation_id, *owner_params),
        ).fetchone()
        if current is None:
            raise OastCorrelationError(
                "oast_correlation_not_found", "OAST correlation not found"
            )
        duplicate = active_conn.execute(
            "SELECT 1 FROM oast_correlations WHERE run_id = ? AND check_id = ? "
            "AND id != ? LIMIT 1",
            (selected_run_id, current["check_id"], correlation_id),
        ).fetchone()
        if duplicate:
            raise OastCorrelationError(
                "oast_correlation_run_conflict",
                "The run already has an OAST correlation for this check",
            )
        cursor = active_conn.execute(
            "UPDATE oast_correlations SET status = 'active', run_id = ?, "  # nosec B608
            "activated_at = ?, updated_at = ? WHERE id = ? AND "
            + owner_sql
            + " AND status = 'reserved' AND active_until > ?",
            (
                selected_run_id,
                instant,
                instant,
                correlation_id,
                *owner_params,
                instant,
            ),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            if owns_conn:
                active_conn.rollback()
            raise OastCorrelationError(
                "oast_correlation_activation_conflict",
                "The OAST correlation is no longer available for this run",
            )
        if owns_conn:
            active_conn.commit()
        row = active_conn.execute(
            "SELECT * FROM oast_correlations WHERE id = ?", (correlation_id,)
        ).fetchone()
        return _decode_row(row)


def close_oast_correlation(
    session_id: str,
    correlation_id: str,
    *,
    team_id: str = "",
    failed: bool = False,
    error_code: str = "",
    error_detail: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Close active work, or fail a reservation that never reached its run."""
    status = "failed" if failed else "closed"
    expected = ("reserved", "active") if failed else ("active",)
    instant = _utc_now(now).isoformat()
    owner_sql, owner_params = _owner_predicate(
        str(session_id or ""), str(team_id or "")
    )
    placeholders = ", ".join("?" for _ in expected)
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            "UPDATE oast_correlations SET status = ?, closed_at = ?, updated_at = ?, "  # nosec B608
            "error_code = ?, error_detail = ? WHERE id = ? AND "
            + owner_sql
            + f" AND status IN ({placeholders})",
            (
                status,
                instant,
                instant,
                str(error_code or ("oast_correlation_failed" if failed else ""))[:80],
                " ".join(str(error_detail or "").split())[:1000],
                correlation_id,
                *owner_params,
                *expected,
            ),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            if owns_conn:
                active_conn.rollback()
            raise OastCorrelationError(
                "oast_correlation_close_conflict",
                "The OAST correlation no longer accepts this close result",
            )
        if owns_conn:
            active_conn.commit()
        row = active_conn.execute(
            "SELECT * FROM oast_correlations WHERE id = ?", (correlation_id,)
        ).fetchone()
        return _decode_row(row)


def expire_oast_correlations(*, now: datetime | None = None, conn=None) -> int:
    """Expire reserved or active callbacks after their fixed correlation window."""
    instant = _utc_now(now).isoformat()
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            "UPDATE oast_correlations SET status = 'expired', closed_at = ?, "
            "updated_at = ?, error_code = 'oast_correlation_expired', "
            "error_detail = 'OAST correlation window expired' "
            "WHERE status IN ('reserved', 'active') AND active_until <= ?",
            (instant, instant, instant),
        )
        if owns_conn:
            active_conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)


def purge_oast_correlations(*, now: datetime | None = None, conn=None) -> int:
    """Delete terminal correlation state after its visible retention deadline."""
    instant = _utc_now(now).isoformat()
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            "DELETE FROM oast_correlations WHERE "
            "status IN ('closed', 'failed', 'expired') AND purge_at <= ?",
            (instant,),
        )
        if owns_conn:
            active_conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)
