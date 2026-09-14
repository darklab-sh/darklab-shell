# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only operator inventory of work stopped by principal disablement."""

from collections.abc import Callable
from typing import Any

from services.storage.transactions import run_read

from .storage import get_principal


_WORK_QUERIES = (
    ("schedule", "schedules", "id", "label", "'paused'",
     "enabled = FALSE AND paused_reason = 'principal_disabled'", "Schedules", True),
    ("watcher", "watchers", "id", "label", "state",
     "state = 'paused' AND state_reason = 'principal_disabled'", "Watchers", True),
    ("notification_channel", "notification_channels", "id", "label", "'muted'",
     "muted = TRUE AND muted_reason = 'principal_disabled'", "Options → Notifications", True),
    ("project_digest", "project_digest_settings", "project_id",
     "(SELECT name FROM projects WHERE projects.id = project_digest_settings.project_id)", "'paused'",
     "enabled = FALSE AND paused_reason = 'principal_disabled'", "Project → Monitoring", True),
    ("workflow_execution", "workflow_executions", "id", "title", "status",
     "failure_code = 'principal_disabled'", "Workflows", False),
    ("notification_delivery", "notification_events", "id", "'Notification delivery'", "status",
     "status = 'dead' AND last_error = 'principal disabled'", "Options → Notifications", False),
    ("ai_assist", "ai_run_assists", "id", "'AI assistance'", "status",
     "error_code = 'principal_disabled'", "Run history", False),
    ("zap_job", "zap_connector_jobs", "id", "'ZAP assessment'", "status",
     "error_code = 'principal_disabled'", "Project → Assessment", False),
    ("oast_correlation", "oast_correlations", "id", "'OAST correlation'", "status",
     "error_code = 'principal_disabled'", "Project → Assessment", False),
)


def operator_suspended_work(principal_id: str, *, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """List current pauses and stopped jobs without reopening or resuming them."""
    def operation(conn: Any) -> dict[str, Any]:
        principal = get_principal(principal_id, conn=conn)
        items: list[dict[str, Any]] = []
        for kind, table, id_column, label, state, condition, review_in, resumable in _WORK_QUERIES:
            rows = conn.execute(
                f"SELECT {id_column} AS id, {label} AS label, {state} AS state, "  # nosec
                f"personal_workspace_id, team_id FROM {table} "  # nosec
                f"WHERE principal_id = ? AND {condition} ORDER BY {id_column}",  # nosec
                (principal.id,),
            ).fetchall()
            items.extend({
                "kind": kind, "id": str(row["id"]), "label": str(row["label"] or ""),
                "state": str(row["state"]), "team_id": str(row["team_id"] or ""),
                "personal_workspace_id": str(row["personal_workspace_id"] or ""),
                "reason": "principal_disabled", "review_in": review_in, "resumable": resumable,
            } for row in rows)
        return {
            "items": items, "count": len(items),
            "resumable_count": sum(item["resumable"] for item in items),
            "message": ("Review this work before resuming it. Enabling the principal does not resume work; "
                        "stopped jobs need a new request."),
        }

    return run_read(operation, connect=connect)
