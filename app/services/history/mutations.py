# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""History run deletion and export mutation helpers."""

from __future__ import annotations

from typing import Any

from core.database import delete_run_artifacts
from core.database_access import get_db_connect
from services.atlas.cleanup import atlas_run_cleanup_preview, delete_atlas_cleanup_preview
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.history.cleanup_logging import history_cleanup_log_fields
from services.history.snapshots import (
    bulk_delete_snapshots as bulk_delete_snapshots,
    delete_snapshot as delete_snapshot,
    save_snapshot as save_snapshot,
    snapshot_row as snapshot_row,
)


def delete_history_run(
    *,
    session_id: str,
    owner_scope,
    run_id: str,
    prune_atlas: bool,
    prune_curated_atlas: bool,
    audit_fields: dict[str, Any],
) -> tuple[int, dict[str, int], dict[str, int | bool]]:
    scope_sql, scope_params = owner_scope.predicate()
    atlas_cleanup = {"entities": 0, "findings": 0}
    cleanup_preview: dict[str, Any] | None = None
    with get_db_connect()() as conn:
        owned = conn.execute(
            "SELECT id, session_id, team_id FROM runs WHERE id = ? AND " + scope_sql,  # nosec
            (run_id, *scope_params),
        ).fetchone()
        if owned:
            cleanup_session_id = str(owned["session_id"] or session_id)
            cleanup_team_id = str(owned["team_id"] or getattr(owner_scope, "team_id", "") or "")
            cleanup_preview = atlas_run_cleanup_preview(
                conn, cleanup_session_id, [run_id], include_curated=prune_curated_atlas, team_id=cleanup_team_id
            ) if prune_atlas else None
            delete_run_artifacts(conn, [run_id])
            if cleanup_preview:
                atlas_cleanup = delete_atlas_cleanup_preview(
                    conn,
                    cleanup_session_id,
                    cleanup_preview,
                    team_id=cleanup_team_id,
                )
        cur = conn.execute("DELETE FROM runs WHERE id = ? AND " + scope_sql, (run_id, *scope_params))  # nosec
        cleanup_log_fields = history_cleanup_log_fields(
            cleanup_preview,
            atlas_cleanup,
            prune_atlas=prune_atlas,
            prune_curated_atlas=prune_curated_atlas,
        )
        if cur.rowcount:
            record_event(
                AuditEventType.HISTORY_DELETE,
                target_id=run_id,
                details={
                    "run_id": run_id,
                    "deleted_count": int(cur.rowcount or 0),
                    "source": "history",
                    **cleanup_log_fields,
                },
                conn=conn,
                **audit_fields,
            )
        conn.commit()
    return int(cur.rowcount or 0), atlas_cleanup, cleanup_log_fields


def history_run_cleanup_preview(session_id: str, run_id: str, owner_scope=None):
    with get_db_connect()() as conn:
        scope_sql, scope_params = ("session_id = ?", [session_id]) if owner_scope is None else owner_scope.predicate()
        owned = conn.execute(
            "SELECT session_id, team_id FROM runs WHERE id = ? AND " + scope_sql,  # nosec
            (run_id, *scope_params),
        ).fetchone()
        if not owned:
            return None
        cleanup_session_id = str(owned["session_id"] or session_id)
        cleanup_team_id = str(owned["team_id"] or getattr(owner_scope, "team_id", "") or "")
        return atlas_run_cleanup_preview(conn, cleanup_session_id, [run_id], team_id=cleanup_team_id)


def bulk_export_rows(owner_scope, run_ids: list[str], snapshot_ids: list[str]):
    with get_db_connect()() as conn:
        owned_runs = {}
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            scope_sql, scope_params = owner_scope.predicate(table_alias="runs")
            rows = conn.execute(
                f"SELECT runs.*, art.rel_path "  # nosec
                f"FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
                f"WHERE {scope_sql} AND runs.id IN ({placeholders})",
                [*scope_params, *run_ids],
            ).fetchall()
            owned_runs = {str(row["id"]): dict(row) for row in rows}
        owned_snapshots = {}
        if snapshot_ids:
            placeholders = ",".join("?" for _ in snapshot_ids)
            scope_sql, scope_params = owner_scope.predicate()
            rows = conn.execute(
                f"SELECT * FROM snapshots WHERE {scope_sql} AND id IN ({placeholders})",  # nosec
                [*scope_params, *snapshot_ids],
            ).fetchall()
            owned_snapshots = {str(row["id"]): dict(row) for row in rows}
    return owned_runs, owned_snapshots


def bulk_delete_runs(
    *,
    owner_scope,
    session_id: str,
    run_ids: list[str],
    active_ids: set[str],
    result_factory,
    audit_fields: dict[str, Any],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts = {"deleted": 0, "not_found": 0, "rejected": 0}
    results = []
    deletable_ids = []
    with get_db_connect()() as conn:
        placeholders = ",".join("?" for _ in run_ids)
        scope_sql, scope_params = owner_scope.predicate(table_alias="runs")
        rows = conn.execute(
            f"SELECT id, finished, exit_code FROM runs WHERE {scope_sql} AND id IN ({placeholders})",  # nosec
            [*scope_params, *run_ids],
        ).fetchall()
        owned_by_id = {str(row["id"]): row for row in rows}
        for run_id in run_ids:
            if run_id in active_ids:
                results.append(result_factory(counts, run_id, "rejected", reason="running"))
                continue
            row = owned_by_id.get(run_id)
            if row is None:
                results.append(result_factory(counts, run_id, "not_found"))
                continue
            if row["finished"] is None and row["exit_code"] is None:
                results.append(result_factory(counts, run_id, "rejected", reason="incomplete"))
                continue
            deletable_ids.append(run_id)
            results.append(result_factory(counts, run_id, "deleted"))
        if deletable_ids:
            delete_run_artifacts(conn, deletable_ids)
            delete_placeholders = ",".join("?" for _ in deletable_ids)
            delete_scope_sql, delete_scope_params = owner_scope.predicate()
            conn.execute(
                f"DELETE FROM runs WHERE {delete_scope_sql} AND id IN ({delete_placeholders})",  # nosec
                [*delete_scope_params, *deletable_ids],
            )
            record_event(
                AuditEventType.HISTORY_DELETE,
                target_id="",
                details={"run_ids": deletable_ids, "deleted_count": len(deletable_ids), "source": "history_bulk"},
                conn=conn,
                **audit_fields,
            )
        conn.commit()
    return counts, results


def clear_history_runs(
    *,
    owner_scope,
    audit_fields: dict[str, Any],
    run_ids: list[str] | None = None,
) -> int:
    with get_db_connect()() as conn:
        scope_sql, scope_params = owner_scope.predicate()
        selected_ids = run_ids
        if selected_ids is None:
            selected_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM runs WHERE " + scope_sql,  # nosec
                    scope_params,
                ).fetchall()
            ]
        if selected_ids:
            placeholders = ",".join("?" for _ in selected_ids)
            delete_run_artifacts(conn, selected_ids)
            cur = conn.execute(
                f"DELETE FROM runs WHERE {scope_sql} AND id IN ({placeholders})",  # nosec
                [*scope_params, *selected_ids],
            )
        else:
            cur = conn.execute("DELETE FROM runs WHERE 1 = 0")
        if cur.rowcount:
            record_event(
                AuditEventType.HISTORY_DELETE,
                target_id="",
                details={
                    "run_count": int(cur.rowcount or 0),
                    "deleted_count": int(cur.rowcount or 0),
                    "source": "history_clear",
                },
                conn=conn,
                **audit_fields,
            )
        conn.commit()
    return int(cur.rowcount or 0)
