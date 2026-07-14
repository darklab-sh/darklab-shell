"""Owner-scoped database queries for run comparisons."""

from __future__ import annotations

import time

import services.runs.comparison as run_comparison
from core.database_access import get_db_connect
from services.metrics_lazy import app_metrics
from services.workflows.storage import apply_workflow_provenance, workflow_provenance_by_run


def compare_run_rows(owner_scope, left_id: str, right_id: str):
    query_started = time.perf_counter()
    with get_db_connect()() as conn:
        scope_sql, scope_params = owner_scope.predicate(table_alias="runs")
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE " + scope_sql + " AND runs.id IN (?, ?)",  # nosec B608
            (*scope_params, left_id, right_id),
        ).fetchall()
        provenance_by_run = workflow_provenance_by_run(
            conn,
            [left_id, right_id],
            owner_scope=owner_scope,
        )
    app_metrics.record_db_query("history_compare_run_rows", time.perf_counter() - query_started)
    by_id = {str(row["id"]): dict(row) for row in rows}
    for run_id, run in by_id.items():
        provenance = provenance_by_run.get(run_id)
        if provenance:
            apply_workflow_provenance(run, provenance)
    return by_id.get(left_id), by_id.get(right_id)


def compare_candidate_rows(owner_scope, run_id: str):
    with get_db_connect()() as conn:
        scope_sql, scope_params = owner_scope.predicate(table_alias="runs")
        source_row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.id = ? AND " + scope_sql + " "  # nosec B608
            "AND runs.run_kind = 'external' AND runs.finished IS NOT NULL",
            (run_id, *scope_params),
        ).fetchone()
        if not source_row:
            return None, []
        source = dict(source_row)
        source_started = str(source.get("started") or "")
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE " + scope_sql + " AND runs.id != ? AND runs.started < ? "  # nosec B608
            "AND runs.run_kind = 'external' AND runs.finished IS NOT NULL "
            "ORDER BY runs.started DESC "
            "LIMIT 200",
            (*scope_params, run_id, source_started),
        ).fetchall()
    return source, rows


def compare_persisted_objects(owner_scope, left_id: str, right_id: str):
    query_started = time.perf_counter()
    with get_db_connect()() as conn:
        left_findings, left_finding_count, left_findings_truncated = (
            run_comparison.run_finding_compare_items(
                conn,
                owner_scope,
                left_id,
                include_line_number=True,
                include_created=True,
            )
        )
        right_findings, right_finding_count, right_findings_truncated = (
            run_comparison.run_finding_compare_items(
                conn,
                owner_scope,
                right_id,
                include_line_number=True,
                include_created=True,
            )
        )
        left_artifacts, left_artifact_count, left_artifacts_truncated = (
            run_comparison.run_artifact_compare_items(
                conn,
                owner_scope,
                left_id,
                include_display_name=True,
                include_created=True,
            )
        )
        right_artifacts, right_artifact_count, right_artifacts_truncated = (
            run_comparison.run_artifact_compare_items(
                conn,
                owner_scope,
                right_id,
                include_display_name=True,
                include_created=True,
            )
        )
    app_metrics.record_db_query("history_compare_objects", time.perf_counter() - query_started)
    project_truncated = {}
    if any((
        left_findings_truncated,
        right_findings_truncated,
        left_artifacts_truncated,
        right_artifacts_truncated,
    )):
        project_truncated = {
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
    return {
        "finding_objects": run_comparison.compare_finding_items(left_findings, right_findings),
        "artifact_objects": run_comparison.compare_items(left_artifacts, right_artifacts),
        "left_persisted_finding_count": left_finding_count,
        "right_persisted_finding_count": right_finding_count,
        "left_artifact_count": left_artifact_count,
        "right_artifact_count": right_artifact_count,
        "project_truncated": project_truncated,
    }
