# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded remediation filtering for assessment finding-change reads."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend


DELTA_STATE_RANKS = {
    "regressed": 5,
    "new": 4,
    "persistent": 3,
    "not_observed": 2,
    "incomparable": 1,
}
_FILTER_CHUNK_SIZE = 500
_ROLLUP_SQL = (
    "WITH strongest AS (SELECT remediation_id, MAX(CASE delta_state "
    "WHEN 'regressed' THEN 5 WHEN 'new' THEN 4 WHEN 'persistent' THEN 3 "
    "WHEN 'not_observed' THEN 2 ELSE 1 END) AS state_rank "
    "FROM project_assessment_finding_deltas WHERE current_assessment_id = ? "
    "GROUP BY remediation_id) SELECT state_rank, COUNT(*) AS count "
    "FROM strongest GROUP BY state_rank"
)
_REMEDIATION_IDS_SQL = (
    "SELECT remediation_id, MAX(CASE delta_state WHEN 'regressed' THEN 5 "
    "WHEN 'new' THEN 4 WHEN 'persistent' THEN 3 WHEN 'not_observed' THEN 2 "
    "ELSE 1 END) AS state_rank "
    "FROM project_assessment_finding_deltas WHERE current_assessment_id = ? "
    "GROUP BY remediation_id ORDER BY state_rank DESC, remediation_id ASC LIMIT ?"
)


def _filtered_queries(remediation_ids: list[str] | None) -> list[tuple[str, str, tuple[Any, ...]]]:
    if remediation_ids is None:
        return [(_ROLLUP_SQL, _REMEDIATION_IDS_SQL, ())]
    dialect = dialect_for_backend(get_db_backend())
    queries = []
    for offset in range(0, len(remediation_ids), _FILTER_CHUNK_SIZE):
        chunk = remediation_ids[offset:offset + _FILTER_CHUNK_SIZE]
        in_sql, in_params = dialect.in_clause("remediation_id", chunk)
        queries.append((
            _ROLLUP_SQL.replace(
                "WHERE current_assessment_id = ? ",
                f"WHERE current_assessment_id = ? AND {in_sql} ",
            ),
            _REMEDIATION_IDS_SQL.replace(
                "WHERE current_assessment_id = ? ",
                f"WHERE current_assessment_id = ? AND {in_sql} ",
            ),
            tuple(in_params),
        ))
    return queries


def delta_rollup(
    conn: Any,
    assessment_id: str,
    *,
    remediation_ids: list[str] | None = None,
    item_limit: int,
) -> tuple[dict[str, int], list[str]]:
    """Count and rank exact remediation ids without exceeding bind limits."""
    state_by_rank = {value: key for key, value in DELTA_STATE_RANKS.items()}
    rollup = {state: 0 for state in DELTA_STATE_RANKS}
    if remediation_ids is not None and not remediation_ids:
        return rollup, []
    ranked_ids: list[tuple[int, str]] = []
    for rollup_sql, remediation_sql, filter_params in _filtered_queries(remediation_ids):
        params = (assessment_id, *filter_params)
        rows = conn.execute(rollup_sql, params).fetchall()  # nosec B608
        for row in rows:
            rank = int(row["state_rank"] or 0)
            state = state_by_rank.get(rank, "incomparable")
            rollup[state] += int(row["count"] or 0)
        id_rows = conn.execute(
            remediation_sql,
            (*params, max(1, int(item_limit))),
        ).fetchall()  # nosec B608
        ranked_ids.extend(
            (int(row["state_rank"] or 0), str(row["remediation_id"]))
            for row in id_rows
        )
    ranked_ids.sort(key=lambda item: (-item[0], item[1]))
    return rollup, [remediation_id for _, remediation_id in ranked_ids[:item_limit]]
