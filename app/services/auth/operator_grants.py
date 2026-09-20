# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Local operator grant lifecycle; grants confer no workspace permissions."""

from __future__ import annotations

import logging
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend
from services.audit.models import AuditEventType, AuditTargetType
from services.audit.recorder import record_event
from services.storage.transactions import run_read, run_transaction

from .contracts import PrincipalDisabled, PrincipalNotFound, timestamp

log = logging.getLogger("shell")


def _status(principal_id: str, data) -> dict[str, Any]:
    granted = data["granted_at"] is not None and data["revoked_at"] is None
    return {
        "principal_id": principal_id,
        "principal_status": str(data["status"]),
        "granted": granted,
        "eligible": granted and data["status"] == "active",
        "granted_at": str(data["granted_at"]) if data["granted_at"] else None,
        "revoked_at": str(data["revoked_at"]) if data["revoked_at"] else None,
    }


def list_grants(*, limit: int = 100, after: str = "", connect=None) -> dict[str, Any]:
    """Inspect current grants, including disabled principals, in bounded pages."""
    if not 1 <= limit <= 1000 or len(after) > 256:
        raise ValueError("limit must be 1–1000 and after must be a principal id")

    def operation(conn):
        rows = conn.execute(
            "SELECT p.id, p.status, g.granted_at, g.revoked_at "
            "FROM instance_operator_grants g JOIN principals p ON p.id = g.principal_id "
            "WHERE g.revoked_at IS NULL AND p.id > ? ORDER BY p.id LIMIT ?",
            (after, limit + 1),
        ).fetchall()
        return {
            "operators": [_status(str(row["id"]), row) for row in rows[:limit]],
            "next_after": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
        }

    return run_read(operation, connect=connect)


def lock_principal(conn: Any, principal_id: str) -> dict[str, Any]:
    """Serialize grant changes and session step-up against this principal."""
    backend = DatabaseBackend(getattr(conn, "database_backend", None) or get_db_backend())
    if backend == DatabaseBackend.SQLITE and not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    query = ("SELECT id, status FROM principals WHERE id = ? FOR UPDATE" if backend == DatabaseBackend.POSTGRES
             else "SELECT id, status FROM principals WHERE id = ?")
    row = conn.execute(query, (principal_id,)).fetchone()
    if row is None:
        raise PrincipalNotFound("principal not found")
    return dict(row)


def grant_status(principal_id: str, *, conn=None, connect=None) -> dict[str, Any]:
    def operation(active):
        row = active.execute(
            "SELECT p.status, g.granted_at, g.revoked_at FROM principals p "
            "LEFT JOIN instance_operator_grants g ON g.principal_id = p.id WHERE p.id = ?",
            (principal_id,),
        ).fetchone()
        if row is None:
            raise PrincipalNotFound("principal not found")
        return _status(principal_id, row)

    return operation(conn) if conn is not None else run_read(operation, connect=connect)


def has_grant(principal_id: str, *, conn=None) -> bool:
    try:
        return grant_status(principal_id, conn=conn)["eligible"]
    except PrincipalNotFound:
        return False


def set_grant(principal_id: str, *, granted: bool, connect=None) -> dict[str, Any]:
    def operation(conn):
        principal = lock_principal(conn, principal_id)
        if granted and principal["status"] != "active":
            raise PrincipalDisabled("an active principal is required")
        before = grant_status(principal_id, conn=conn)
        changed = before["granted"] != granted
        if changed:
            now = timestamp()
            if granted:
                conn.execute(
                    "INSERT INTO instance_operator_grants (principal_id, granted_at, revoked_at) VALUES (?, ?, NULL) "
                    "ON CONFLICT (principal_id) DO UPDATE SET granted_at = excluded.granted_at, revoked_at = NULL",
                    (principal_id, now),
                )
            else:
                conn.execute("UPDATE instance_operator_grants SET revoked_at = ? WHERE principal_id = ?",
                             (now, principal_id))
            record_event(
                AuditEventType.INSTANCE_OPERATOR_GRANT if granted else AuditEventType.INSTANCE_OPERATOR_REVOKE,
                target_type=AuditTargetType.PRINCIPAL, target_id=principal_id,
                actor_role="local_operator", details={"source": "local_operator", "result": "changed"}, conn=conn,
            )
        return {**grant_status(principal_id, conn=conn), "changed": changed}

    result = run_transaction(operation, connect=connect)
    if result["changed"]:
        log.info("INSTANCE_OPERATOR_GRANT_CHANGED", extra={
            "principal_id": principal_id, "source": "local_operator", "granted": granted,
        })
    return result
