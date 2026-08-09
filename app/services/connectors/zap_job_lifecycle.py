# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Guarded transitions for durable external ZAP jobs."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
import re
from typing import Any

from services.connectors.zap_jobs import (
    ZapJobError,
    _connection_scope,
    _decode_row,
    _json,
    _utc_now,
    zap_job_for_owner,
)
from services.connectors.zap_remote_progress import ReviewedZapRemoteProgress


_TERMINAL_STATUSES = frozenset({"ready", "imported", "canceled", "failed", "expired"})
_TRANSITIONS = {
    "queued": frozenset({"submitting", "canceled", "failed", "expired"}),
    "submitting": frozenset({"running", "cancel_requested", "failed", "expired"}),
    "running": frozenset({"cancel_requested", "downloading", "failed", "expired"}),
    "cancel_requested": frozenset({"canceled", "downloading", "failed", "expired"}),
    "downloading": frozenset({"ready", "failed", "expired"}),
    "ready": frozenset({"imported"}),
}
_REMOTE_PLAN_ID_RE = re.compile(r"(?:0|[1-9][0-9]{0,9})")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def transition_zap_job(
    job_id: str,
    expected_statuses: Collection[str],
    status: str,
    *,
    remote_plan_id: str = "",
    error_code: str = "",
    error_detail: str = "",
    report_bytes: int = 0,
    report_sha256: str = "",
    import_source_id: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Apply one legal compare-and-set lifecycle transition."""
    expected = tuple(dict.fromkeys(str(value) for value in expected_statuses))
    if not expected or any(status not in _TRANSITIONS.get(value, ()) for value in expected):
        raise ZapJobError("zap_job_transition_invalid", "The ZAP job transition is invalid")
    remote_id = str(remote_plan_id or "").strip()
    if remote_id and not _REMOTE_PLAN_ID_RE.fullmatch(remote_id):
        raise ZapJobError("zap_job_remote_id_invalid", "The ZAP plan id is invalid")
    if (status == "running") != bool(remote_id):
        raise ZapJobError(
            "zap_job_remote_id_invalid",
            "Only a running ZAP job may receive its required remote plan id",
        )
    digest = str(report_sha256 or "").strip().lower()
    if digest and not _SHA256_RE.fullmatch(digest):
        raise ZapJobError("zap_job_report_invalid", "The ZAP report digest is invalid")
    size = int(report_bytes)
    if size < 0 or size > 52428800:
        raise ZapJobError("zap_job_report_invalid", "The ZAP report size is invalid")
    if (status == "ready") != bool(size and digest):
        raise ZapJobError(
            "zap_job_report_invalid",
            "Only a ready ZAP job may receive its required report identity",
        )
    source_id = str(import_source_id or "").strip()
    if (status == "imported") != bool(source_id):
        raise ZapJobError(
            "zap_job_import_invalid",
            "Only an imported ZAP job may receive its required import source id",
        )
    instant = _utc_now(now).isoformat()
    assignments = ["status = ?", "updated_at = ?"]
    params: list[object] = [status, instant]
    if remote_id:
        assignments.extend(["remote_plan_id = ?", "submitted_at = ?"])
        params.extend([remote_id, instant])
    if status in _TERMINAL_STATUSES:
        assignments.append("finished_at = ?")
        params.append(instant)
    if error_code or error_detail:
        assignments.extend(["error_code = ?", "error_detail = ?"])
        params.extend([
            str(error_code or "zap_job_failed")[:80],
            " ".join(str(error_detail or "").split())[:1000],
        ])
    if status == "ready":
        assignments.extend(["report_bytes = ?", "report_sha256 = ?"])
        params.extend([size, digest])
    if status == "imported":
        assignments.append("import_source_id = ?")
        params.append(source_id[:96])
    placeholders = ", ".join("?" for _ in expected)
    params.extend([job_id, *expected])
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            f"UPDATE zap_connector_jobs SET {', '.join(assignments)} "  # nosec B608
            f"WHERE id = ? AND status IN ({placeholders})",
            tuple(params),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            if owns_conn:
                active_conn.rollback()
            raise ZapJobError(
                "zap_job_transition_conflict",
                "The ZAP job changed before this operation completed",
            )
        if owns_conn:
            active_conn.commit()
        row = active_conn.execute(
            "SELECT * FROM zap_connector_jobs WHERE id = ?", (job_id,),
        ).fetchone()
        return _decode_row(row)


def record_zap_job_progress(
    job_id: str,
    progress: ReviewedZapRemoteProgress,
    *,
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    instant = _utc_now(now).isoformat()
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            "UPDATE zap_connector_jobs SET progress_json = ?, updated_at = ? "
            "WHERE id = ? AND remote_plan_id = ? "
            "AND status IN ('running', 'cancel_requested')",
            (_json(progress.to_dict()), instant, job_id, progress.remote_plan_id),
        )
        if int(getattr(cursor, "rowcount", 0) or 0) != 1:
            if owns_conn:
                active_conn.rollback()
            raise ZapJobError(
                "zap_job_progress_conflict",
                "The ZAP job no longer accepts this progress response",
            )
        if owns_conn:
            active_conn.commit()
        row = active_conn.execute(
            "SELECT * FROM zap_connector_jobs WHERE id = ?", (job_id,),
        ).fetchone()
        return _decode_row(row)


def request_zap_job_cancel(
    session_id: str,
    job_id: str,
    *,
    team_id: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Record cancel intent without confusing it with remote confirmation."""
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        current = zap_job_for_owner(session_id, job_id, team_id=team_id, conn=active_conn)
        if current is None:
            raise ZapJobError("zap_job_not_found", "ZAP job not found")
        status = str(current["status"])
        if status in {"cancel_requested", "canceled"}:
            return current
        target = "canceled" if status == "queued" else "cancel_requested"
        updated = transition_zap_job(
            job_id,
            (status,),
            target,
            now=now,
            conn=active_conn,
        )
        if owns_conn:
            active_conn.commit()
        return updated


def expire_zap_jobs(*, now: datetime | None = None, conn=None) -> int:
    """Expire active jobs whose fixed deadline has passed."""
    instant = _utc_now(now).isoformat()
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        cursor = active_conn.execute(
            "UPDATE zap_connector_jobs SET status = 'expired', finished_at = ?, updated_at = ?, "
            "error_code = 'zap_job_expired', error_detail = 'ZAP job lifetime expired' "
            "WHERE status IN ('queued', 'submitting', 'running', 'cancel_requested', 'downloading') "
            "AND expires_at <= ?",
            (instant, instant, instant),
        )
        if owns_conn:
            active_conn.commit()
        return int(getattr(cursor, "rowcount", 0) or 0)
