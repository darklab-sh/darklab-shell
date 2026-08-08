# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-scoped prior artifact paths protected from screenshot cleanup."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


PROTECTED_PATH_LOOKUP_MAX = 1_000


def load_protected_workspace_paths(
    conn: Any,
    paths: Sequence[str],
    *,
    run_id: str,
    session_id: str,
    team_id: str,
) -> set[str]:
    """Return candidate paths already referenced by an earlier owner run."""
    candidates = {str(path or "") for path in paths if path}
    if not candidates:
        return set()
    if team_id:
        count_row = conn.execute(
            "SELECT COUNT(DISTINCT a.workspace_path) AS count FROM run_file_artifacts a "
            "JOIN runs r ON r.id = a.run_id WHERE r.team_id = ? AND a.run_id <> ?",
            (team_id, run_id),
        ).fetchone()
        rows_query = (
            "SELECT DISTINCT a.workspace_path FROM run_file_artifacts a "
            "JOIN runs r ON r.id = a.run_id WHERE r.team_id = ? AND a.run_id <> ? LIMIT ?"
        )
        params = (team_id, run_id, PROTECTED_PATH_LOOKUP_MAX)
    else:
        count_row = conn.execute(
            "SELECT COUNT(DISTINCT a.workspace_path) AS count FROM run_file_artifacts a "
            "JOIN runs r ON r.id = a.run_id WHERE a.session_id = ? "
            "AND COALESCE(r.team_id, '') = '' AND a.run_id <> ?",
            (session_id, run_id),
        ).fetchone()
        rows_query = (
            "SELECT DISTINCT a.workspace_path FROM run_file_artifacts a "
            "JOIN runs r ON r.id = a.run_id WHERE a.session_id = ? "
            "AND COALESCE(r.team_id, '') = '' AND a.run_id <> ? LIMIT ?"
        )
        params = (session_id, run_id, PROTECTED_PATH_LOOKUP_MAX)
    if count_row and int(count_row["count"] or 0) > PROTECTED_PATH_LOOKUP_MAX:
        raise RuntimeError("protected artifact path lookup exceeded its bound")
    rows = conn.execute(rows_query, params).fetchall()
    return candidates.intersection(str(row["workspace_path"] or "") for row in rows)


__all__ = ["PROTECTED_PATH_LOOKUP_MAX", "load_protected_workspace_paths"]
