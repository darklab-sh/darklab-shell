"""
Project run comparison helpers.
"""

from __future__ import annotations

import services.runs.comparison as run_comparison
from core.database_access import get_db_connect
from services.projects.contracts import (
    MAX_ENTITY_ID_LEN,
    MAX_LABEL_LEN,
    ProjectWorkspaceError,
)
from services.projects.utils import trim_text as _trim_text

MAX_PROJECT_COMPARE_ITEMS_PER_SIDE = run_comparison.MAX_COMPARE_ITEMS_PER_SIDE


def _project_linked_run_ids(conn, session_id, project_id):
    rows = conn.execute(
        "SELECT l.entity_id AS run_id "
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
        "ORDER BY l.created DESC",
        (project_id, session_id),
    ).fetchall()
    return [row["run_id"] for row in rows]


def _project_labeled_run_id(conn, session_id, project_id, label, excluded_run_ids=None):
    excluded = [str(run_id) for run_id in (excluded_run_ids or []) if run_id]
    params = [project_id, session_id, label]
    excluded_sql = ""
    if excluded:
        placeholders = ",".join("?" for _ in excluded)
        excluded_sql = f"AND r.id NOT IN ({placeholders}) "
        params.extend(excluded)
    row = conn.execute(
        "SELECT r.id "  # nosec
        "FROM project_links l "
        "JOIN runs r ON r.id = l.entity_id "
        "JOIN entity_labels el ON el.entity_type = 'run' AND el.entity_id = r.id "
        "WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ? "
        "AND el.session_id = r.session_id AND el.label = ? "
        f"{excluded_sql}"
        "ORDER BY r.started DESC, l.created DESC LIMIT 1",
        params,
    ).fetchone()
    return row["id"] if row else ""


def _run_compare_summary(row):
    if not row:
        return {}
    return {
        "id": row["id"],
        "command": row["command"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "output_line_count": int(row["output_line_count"] or 0),
        "preview_truncated": bool(row["preview_truncated"]),
        "full_output_available": bool(row["full_output_available"]),
        "full_output_truncated": bool(row["full_output_truncated"]),
    }


def compare_project_runs(session_id, project_id, filters=None):
    filters = filters if isinstance(filters, dict) else {}
    with get_db_connect()() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        linked_run_ids = _project_linked_run_ids(conn, session_id, project_id)
        left_run_id = _trim_text(filters.get("left_run_id"), MAX_ENTITY_ID_LEN)
        right_run_id = _trim_text(filters.get("right_run_id"), MAX_ENTITY_ID_LEN)
        baseline_label = _trim_text(filters.get("baseline_label"), MAX_LABEL_LEN)
        if not left_run_id and len(linked_run_ids) >= 1:
            left_run_id = linked_run_ids[0]
        if not right_run_id and baseline_label:
            right_run_id = _project_labeled_run_id(
                conn,
                session_id,
                project_id,
                baseline_label,
                excluded_run_ids=[left_run_id],
            )
            if not right_run_id:
                raise ProjectWorkspaceError("no linked project run matches the baseline label")
        if not right_run_id and len(linked_run_ids) >= 2:
            right_run_id = linked_run_ids[1]
        if not left_run_id or not right_run_id:
            raise ProjectWorkspaceError("project comparison needs two linked runs")
        if left_run_id == right_run_id:
            raise ProjectWorkspaceError("project comparison needs two different linked runs")
        linked = set(linked_run_ids)
        if left_run_id not in linked or right_run_id not in linked:
            raise ProjectWorkspaceError("comparison runs must both be linked to this project")
        run_rows = conn.execute(
            "SELECT id, command, started, finished, exit_code, output_line_count, "
            "preview_truncated, full_output_available, full_output_truncated "
            "FROM runs WHERE session_id = ? AND id IN (?, ?)",
            (session_id, left_run_id, right_run_id),
        ).fetchall()
        runs_by_id = {str(row["id"]): row for row in run_rows}
        if left_run_id not in runs_by_id or right_run_id not in runs_by_id:
            raise ProjectWorkspaceError("comparison runs must both be linked to this project")
        left_findings, left_finding_count, left_findings_truncated = run_comparison.run_finding_compare_items(
            conn, session_id, left_run_id, include_line_number=True
        )
        right_findings, right_finding_count, right_findings_truncated = run_comparison.run_finding_compare_items(
            conn, session_id, right_run_id, include_line_number=True
        )
        left_artifacts, left_artifact_count, left_artifacts_truncated = run_comparison.run_artifact_compare_items(
            conn, session_id, left_run_id
        )
        right_artifacts, right_artifact_count, right_artifacts_truncated = run_comparison.run_artifact_compare_items(
            conn, session_id, right_run_id
        )
    finding_diff = run_comparison.compare_items(left_findings, right_findings)
    artifact_diff = run_comparison.compare_items(left_artifacts, right_artifacts)
    response = {
        "left_run_id": left_run_id,
        "right_run_id": right_run_id,
        "left": {
            **_run_compare_summary(runs_by_id[left_run_id]),
            "persisted_finding_count": left_finding_count,
            "artifact_count": left_artifact_count,
        },
        "right": {
            **_run_compare_summary(runs_by_id[right_run_id]),
            "persisted_finding_count": right_finding_count,
            "artifact_count": right_artifact_count,
        },
        "baseline_label": baseline_label,
        "objects": {
            "findings": finding_diff,
            "artifacts": artifact_diff,
        },
    }
    if any((
        left_findings_truncated,
        right_findings_truncated,
        left_artifacts_truncated,
        right_artifacts_truncated,
    )):
        response["truncated"] = {
            "left": bool(left_findings_truncated or left_artifacts_truncated),
            "right": bool(right_findings_truncated or right_artifacts_truncated),
            "findings": {
                "left": bool(left_findings_truncated),
                "right": bool(right_findings_truncated),
            },
            "artifacts": {
                "left": bool(left_artifacts_truncated),
                "right": bool(right_artifacts_truncated),
            },
            "item_limit": run_comparison.compare_item_limit(),
        }
    return response
