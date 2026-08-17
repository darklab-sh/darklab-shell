# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sanitized assessment-batch ancestry for ordinary child runs."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend, sqlite_table_exists
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


_REQUIRED_TABLES = (
    "workflow_executions",
    "workflow_execution_children",
    "assessment_batches",
    "assessment_batch_items",
    "assessment_batch_item_checks",
)


def assessment_batch_provenance_by_run(
    conn: Any,
    run_ids: list[str],
    *,
    owner_scope: Any | None = None,
    session_id: str = "",
    team_id: str = "",
) -> dict[str, dict[str, Any]]:
    """Return bounded, owner-scoped batch ancestry for ordinary run ids."""
    normalized_ids = [str(run_id) for run_id in run_ids if str(run_id or "")]
    if not normalized_ids:
        return {}
    if getattr(conn, "database_backend", get_db_backend()) == DatabaseBackend.SQLITE and not all(
        sqlite_table_exists(conn, table_name) for table_name in _REQUIRED_TABLES
    ):
        return {}
    placeholders = ", ".join("?" for _run_id in normalized_ids)
    owner_sql = ""
    owner_params: tuple[Any, ...] = ()
    if owner_scope is not None:
        owner_clause, raw_owner_params = owner_scope.predicate(table_alias="e")
        owner_sql = " AND " + owner_clause
        owner_params = tuple(raw_owner_params)
    elif session_id or team_id:
        owner_clause, raw_owner_params = shared_owner_where(
            session_id,
            team_id=team_id,
            table_alias="e",
        )
        owner_sql = " AND " + owner_clause
        owner_params = tuple(raw_owner_params)
    rows = conn.execute(
        "SELECT child.run_id, child.execution_id AS batch_id, child.step_id, "  # nosec B608
        "child.attempt, child.status AS item_status, child.exit_code, "
        "item.item_index, batch.assessment_id, batch.source_execution_id, "
        "e.project_id, e.status AS batch_status, e.created, "
        "(SELECT COUNT(*) FROM assessment_batch_item_checks mapping "
        "WHERE mapping.batch_id = item.batch_id "
        "AND mapping.item_index = item.item_index) AS check_count "
        "FROM workflow_execution_children child "
        "JOIN workflow_executions e ON e.id = child.execution_id "
        "JOIN assessment_batches batch ON batch.execution_id = child.execution_id "
        "JOIN assessment_batch_items item ON item.batch_id = child.execution_id "
        "AND item.step_id = child.step_id AND item.child_ordinal = child.ordinal "
        f"WHERE e.execution_kind = ? AND child.run_id IN ({placeholders})" + owner_sql,
        (ASSESSMENT_BATCH_EXECUTION_KIND, *normalized_ids, *owner_params),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        run_id = str(row["run_id"] or "")
        result[run_id] = {
            "schema_version": 1,
            "batch_id": str(row["batch_id"] or ""),
            "assessment_id": str(row["assessment_id"] or ""),
            "project_id": str(row["project_id"] or ""),
            "status": str(row["batch_status"] or ""),
            "source_batch_id": str(row["source_execution_id"] or ""),
            "created": row["created"],
            "item": {
                "item_index": int(row["item_index"] or 0),
                "step_id": str(row["step_id"] or ""),
                "attempt": int(row["attempt"] or 0),
                "status": str(row["item_status"] or ""),
                "run_id": run_id,
                "exit_code": row["exit_code"],
                "check_count": int(row["check_count"] or 0),
            },
        }
    return result


def apply_assessment_batch_provenance(
    run: dict[str, Any],
    provenance: dict[str, Any] | None,
) -> None:
    """Attach the stable public batch ancestry fields used by run surfaces."""
    run["assessment_batch"] = provenance
    run["assessment_batch_id"] = str((provenance or {}).get("batch_id") or "")
    item = (provenance or {}).get("item")
    run["assessment_batch_item_index"] = (
        int(item.get("item_index") or 0) if isinstance(item, dict) else None
    )


def attach_assessment_batch_run_provenance(
    conn: Any,
    runs: list[dict[str, Any]],
    *,
    owner_scope: Any | None = None,
    session_id: str = "",
    team_id: str = "",
) -> None:
    """Attach public batch ancestry to an already owner-scoped run collection."""
    provenance_by_run = assessment_batch_provenance_by_run(
        conn,
        [str(run.get("id") or run.get("run_id") or "") for run in runs],
        owner_scope=owner_scope,
        session_id=session_id,
        team_id=team_id,
    )
    for run in runs:
        run_id = str(run.get("id") or run.get("run_id") or "")
        apply_assessment_batch_provenance(run, provenance_by_run.get(run_id))


def apply_assessment_batch_evidence_provenance(
    conn: Any,
    evidence_items: list[dict[str, Any]],
) -> None:
    """Attach ancestry only when the scoped evidence and batch cycle agree."""
    run_ids = [
        str(item.get("evidence_id") or "")
        for item in evidence_items
        if item.get("evidence_type") == "run" and item.get("evidence_id")
    ]
    provenance_by_run = assessment_batch_provenance_by_run(conn, run_ids)
    for item in evidence_items:
        provenance = provenance_by_run.get(str(item.get("evidence_id") or ""))
        if provenance and provenance["assessment_id"] == item.get("assessment_id"):
            apply_assessment_batch_provenance(item, provenance)


__all__ = [
    "apply_assessment_batch_evidence_provenance",
    "apply_assessment_batch_provenance",
    "assessment_batch_provenance_by_run",
    "attach_assessment_batch_run_provenance",
]
