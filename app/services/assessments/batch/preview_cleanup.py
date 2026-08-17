# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded expiry cleanup for server-owned assessment-batch previews."""

from __future__ import annotations

from typing import Any

from services.projects.scope import shared_owner_where


def delete_expired_batch_previews_on_conn(
    conn: Any,
    session_id: str,
    team_id: str,
    expires_before: str,
) -> int:
    """Delete expired snapshots for one owner before storing another preview."""
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    cursor = conn.execute(
        "DELETE FROM assessment_batch_previews AS p WHERE "
        + owner_sql  # nosec
        + " AND p.expires_at <= ?",
        (*owner_params, expires_before),
    )
    return max(0, int(cursor.rowcount or 0))


__all__ = ["delete_expired_batch_previews_on_conn"]
