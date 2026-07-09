"""History delete, export, and snapshot mutation helpers."""

from __future__ import annotations

from typing import Any

from core.database import delete_run_artifacts, delete_snapshot_metadata
from core.database_access import get_db_connect
from services.atlas.cleanup import atlas_run_cleanup_preview, delete_atlas_cleanup_preview
from services.audit.models import AuditEventType, AuditTargetType
from services.audit.recorder import record_event


def delete_history_run(
    *,
    session_id: str,
    owner_scope,
    run_id: str,
    prune_atlas: bool,
    prune_curated_atlas: bool,
    audit_fields: dict[str, Any],
) -> tuple[int, dict[str, int]]:
    scope_sql, scope_params = owner_scope.predicate()
    atlas_cleanup = {"entities": 0, "findings": 0}
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
        if cur.rowcount:
            record_event(
                AuditEventType.HISTORY_DELETE,
                target_id=run_id,
                details={"run_id": run_id, "deleted_count": int(cur.rowcount or 0), "source": "history"},
                conn=conn,
                **audit_fields,
            )
        conn.commit()
    return int(cur.rowcount or 0), atlas_cleanup


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


def clear_history_runs(*, owner_scope, audit_fields: dict[str, Any]) -> int:
    with get_db_connect()() as conn:
        scope_sql, scope_params = owner_scope.predicate()
        run_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM runs WHERE " + scope_sql,  # nosec
                scope_params,
            ).fetchall()
        ]
        delete_run_artifacts(conn, run_ids)
        cur = conn.execute("DELETE FROM runs WHERE " + scope_sql, scope_params)  # nosec
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


def save_snapshot(
    *,
    session_id: str,
    team_id: str,
    share_id: str,
    label: str,
    created: str,
    stored_content: str,
    audit_fields: dict[str, Any],
    audit_details: dict[str, Any],
    redaction_audit: bool,
) -> None:
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO snapshots (id, session_id, team_id, label, created, content) VALUES (?, ?, ?, ?, ?, ?)",
            (share_id, session_id, team_id, label, created, stored_content),
        )
        record_event(
            AuditEventType.SNAPSHOT_CREATE,
            target_id=share_id,
            details=audit_details,
            conn=conn,
            **audit_fields,
        )
        if redaction_audit:
            record_event(
                AuditEventType.REDACTION_USE,
                target_type=AuditTargetType.SNAPSHOT,
                target_id=share_id,
                details={
                    "snapshot_id": share_id,
                    "redaction_mode": "configured",
                    "source": "share",
                },
                conn=conn,
                **audit_fields,
            )
        conn.commit()


def bulk_delete_snapshots(
    *,
    session_id: str,
    snapshot_ids: list[str],
    result_factory,
    audit_fields: dict[str, Any],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts = {"deleted": 0, "not_found": 0, "rejected": 0}
    results = []
    deletable_ids = []
    with get_db_connect()() as conn:
        placeholders = ",".join("?" for _ in snapshot_ids)
        rows = conn.execute(
            f"SELECT id FROM snapshots WHERE session_id = ? AND id IN ({placeholders})",  # nosec
            [session_id, *snapshot_ids],
        ).fetchall()
        owned_ids = {str(row["id"]) for row in rows}
        for snapshot_id in snapshot_ids:
            if snapshot_id not in owned_ids:
                results.append(result_factory(counts, snapshot_id, "not_found", key="snapshot_id"))
                continue
            deletable_ids.append(snapshot_id)
            results.append(result_factory(counts, snapshot_id, "deleted", key="snapshot_id"))
        if deletable_ids:
            delete_snapshot_metadata(conn, deletable_ids)
            delete_placeholders = ",".join("?" for _ in deletable_ids)
            conn.execute(
                f"DELETE FROM snapshots WHERE session_id = ? AND id IN ({delete_placeholders})",  # nosec
                [session_id, *deletable_ids],
            )
            record_event(
                AuditEventType.SNAPSHOT_DELETE,
                target_id="",
                details={
                    "snapshot_ids": deletable_ids,
                    "deleted_count": len(deletable_ids),
                    "source": "share_bulk",
                },
                conn=conn,
                **audit_fields,
            )
        conn.commit()
    return counts, results


def snapshot_row(share_id: str):
    with get_db_connect()() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (share_id,)).fetchone()
    return dict(row) if row else None


def delete_snapshot(*, session_id: str, share_id: str, audit_fields: dict[str, Any]) -> int:
    with get_db_connect()() as conn:
        snapshot_rows = conn.execute(
            "SELECT id FROM snapshots WHERE id = ? AND session_id = ?",
            (share_id, session_id),
        ).fetchall()
        delete_snapshot_metadata(conn, [row["id"] for row in snapshot_rows])
        cur = conn.execute(
            "DELETE FROM snapshots WHERE id = ? AND session_id = ?",
            (share_id, session_id),
        )
        if cur.rowcount:
            record_event(
                AuditEventType.SNAPSHOT_DELETE,
                target_id=share_id,
                details={
                    "snapshot_id": share_id,
                    "deleted_count": int(cur.rowcount or 0),
                    "source": "share",
                },
                conn=conn,
                **audit_fields,
            )
        conn.commit()
    return int(cur.rowcount or 0)
