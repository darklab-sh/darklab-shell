# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preference-aware terminal summaries for durable assessment batches."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from urllib.parse import urljoin

from config import resolve_effective_cfg
from core.database_access import get_db_connect
from core.helpers import get_log_session_id
from services.assessments.batch.parent_completion import (
    batch_progress_details_on_conn,
)
from services.notifications import dispatcher
from services.notifications.models import TRIGGER_RUN_COMPLETE, notification_app_name
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


log = logging.getLogger("shell")
ASSESSMENT_BATCH_NOTIFICATION_KIND = "assessment_batch"
_TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


def _batch_path(project_id: str, batch_id: str) -> str:
    return f"/projects/{project_id}/assessment-batches/{batch_id}"


def _absolute_or_relative_url(path: str) -> str:
    base_url = str(resolve_effective_cfg().get("app_public_base_url") or "").strip()
    if not base_url:
        return path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _summary_snapshot(batch_id: str) -> dict[str, object] | None:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT e.session_id, e.team_id, e.project_id, e.status, e.finished, "
            "b.assessment_id, b.source_execution_id FROM workflow_executions e "
            "JOIN assessment_batches b ON b.execution_id = e.id "
            "WHERE e.id = ? AND e.execution_kind = ?",
            (batch_id, ASSESSMENT_BATCH_EXECUTION_KIND),
        ).fetchone()
        if not row or str(row["status"] or "") not in _TERMINAL_STATUSES:
            return None
        counts = batch_progress_details_on_conn(conn, batch_id)
    return {
        "session_id": str(row["session_id"] or ""),
        "team_id": str(row["team_id"] or ""),
        "project_id": str(row["project_id"] or ""),
        "assessment_id": str(row["assessment_id"] or ""),
        "source_batch_id": str(row["source_execution_id"] or ""),
        "status": str(row["status"] or ""),
        "finished": str(row["finished"] or ""),
        "counts": counts,
    }


def enqueue_terminal_batch_summary(batch_id: str) -> list[str]:
    """Queue one idempotent summary through the existing run-complete preference."""
    normalized_batch_id = str(batch_id or "").strip()
    if not normalized_batch_id:
        return []
    snapshot: dict[str, object] | None = None
    try:
        snapshot = _summary_snapshot(normalized_batch_id)
        if snapshot is None:
            return []
        project_id = str(snapshot["project_id"])
        path = _batch_path(project_id, normalized_batch_id)
        raw_counts = snapshot["counts"]
        counts = raw_counts if isinstance(raw_counts, dict) else {}
        payload = {
            "trigger": TRIGGER_RUN_COMPLETE,
            "notification_kind": ASSESSMENT_BATCH_NOTIFICATION_KIND,
            "app_name": notification_app_name(),
            "occurred_at": str(snapshot["finished"])
            or datetime.now(timezone.utc).isoformat(),
            "batch_id": normalized_batch_id,
            "project_id": project_id,
            "assessment_id": str(snapshot["assessment_id"]),
            "source_batch_id": str(snapshot["source_batch_id"]),
            "status": str(snapshot["status"]),
            "assessment_batch_path": path,
            "assessment_batch_url": _absolute_or_relative_url(path),
            "summary_fields": {
                "status": str(snapshot["status"]),
                "succeeded": int(counts.get("succeeded") or 0),
                "failed": int(counts.get("failed") or 0),
                "unavailable": int(counts.get("unavailable") or 0),
                "canceled": int(counts.get("canceled") or 0),
                "could_not_cancel": int(counts.get("could_not_cancel") or 0),
                "batch_link": _absolute_or_relative_url(path),
            },
        }
        return dispatcher.enqueue(
            TRIGGER_RUN_COMPLETE,
            payload,
            str(snapshot["session_id"]),
            run_id=normalized_batch_id,
            team_id=str(snapshot["team_id"]),
        )
    except Exception:
        log.error(
            "ASSESSMENT_BATCH_NOTIFICATION_ERROR",
            exc_info=True,
            extra={
                "batch_id": normalized_batch_id,
                "session": get_log_session_id(
                    str((snapshot or {}).get("session_id") or "")
                ),
            },
        )
        return []


__all__ = [
    "ASSESSMENT_BATCH_NOTIFICATION_KIND",
    "enqueue_terminal_batch_summary",
]
