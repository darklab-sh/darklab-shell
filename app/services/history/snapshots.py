# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""History snapshot persistence helpers."""

from __future__ import annotations

from typing import Any

from core.database import delete_snapshot_metadata
from core.database_access import get_db_connect
from services.audit.models import AuditEventType, AuditTargetType
from services.audit.recorder import record_event


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
