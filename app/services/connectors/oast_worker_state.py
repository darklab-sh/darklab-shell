# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded database reads and counters for the private OAST worker."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import re
from typing import Any

from services.connectors.oast_correlations import (
    _connection_scope,
    _decode_row,
    _utc_now,
)


_CORRELATION_ID_RE = re.compile(r"ocr_[0-9a-f]{32}")
_MAX_CANDIDATES = 256


def oast_correlations_for_worker(
    *,
    limit: int = 50,
    conn=None,
) -> list[dict[str, Any]]:
    """Return bounded live work, prioritizing active polling over registration."""
    bounded_limit = max(1, min(int(limit), 100))
    with _connection_scope(conn) as active_conn:
        rows = active_conn.execute(
            "SELECT * FROM oast_correlations WHERE status IN ('reserved', 'active') "
            "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at, id "
            "LIMIT ?",
            (bounded_limit,),
        ).fetchall()
        return [_decode_row(row) for row in rows]


def oast_correlations_by_ids(
    correlation_ids: Sequence[object],
    *,
    conn=None,
) -> dict[str, dict[str, Any]]:
    """Return durable rows for a bounded set of private spool candidates."""
    candidates = tuple(
        value
        for value in dict.fromkeys(
            str(item or "").strip().lower() for item in correlation_ids
        )
        if _CORRELATION_ID_RE.fullmatch(value)
    )[:_MAX_CANDIDATES]
    if not candidates:
        return {}
    placeholders = ", ".join("?" for _ in candidates)
    with _connection_scope(conn) as active_conn:
        rows = active_conn.execute(
            f"SELECT * FROM oast_correlations WHERE id IN ({placeholders})",  # nosec B608
            candidates,
        ).fetchall()
        return {
            str(row["id"]): _decode_row(row)
            for row in rows
        }


def record_oast_provider_rejections(
    correlation_id: str,
    count: int,
    *,
    now: datetime | None = None,
    conn=None,
) -> int:
    """Add bounded provider-side rejects to one active correlation counter."""
    increment = max(0, min(int(count), _MAX_CANDIDATES))
    if not increment:
        return 0
    instant = _utc_now(now).isoformat()
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            "UPDATE oast_correlations SET rejected_count = CASE "
            "WHEN rejected_count > ? THEN 10000 ELSE rejected_count + ? END, "
            "updated_at = ? WHERE id = ? AND status = 'active'",
            (10000 - increment, increment, instant, correlation_id),
        )
        if owns_conn:
            active_conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)


__all__ = [
    "oast_correlations_by_ids",
    "oast_correlations_for_worker",
    "record_oast_provider_rejections",
]
