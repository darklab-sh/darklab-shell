# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable, owner-scoped lifecycle state for external ZAP jobs."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from typing import Any
import uuid

from core.database_access import get_db_connect
from services.connectors.zap_plan_contracts import ZapAutomationPlanSummary


_MAX_JSON_BYTES = 65536


class ZapJobError(RuntimeError):
    """Raised when a durable ZAP job operation fails closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@contextmanager
def _connection_scope(conn=None):
    if conn is not None:
        yield conn
        return
    with get_db_connect()() as owned:
        yield owned


def _utc_now(now: datetime | None = None) -> datetime:
    value = datetime.now(timezone.utc) if now is None else now
    if value.tzinfo is None:
        raise ZapJobError("zap_job_time_invalid", "ZAP job timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _json(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > _MAX_JSON_BYTES:
        raise ZapJobError("zap_job_state_too_large", "ZAP job state exceeds the storage limit")
    return encoded


def _decode_json(value: object) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return json.loads(str(value or "{}"))


def _decode_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["plan_summary"] = _decode_json(data.pop("plan_summary_json", {}))
    data["progress"] = _decode_json(data.pop("progress_json", {}))
    return data


def _owner_predicate(
    session_id: str,
    team_id: str,
    *,
    table_prefix: str = "",
) -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_prefix}." if table_prefix else ""
    if team_id:
        return f"{prefix}team_id = ?", (team_id,)
    return f"{prefix}team_id = '' AND {prefix}session_id = ?", (session_id,)


def create_zap_job(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    http_profile_id: str,
    http_profile_revision: int,
    summary: ZapAutomationPlanSummary,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Create one queued job after rechecking its current Project boundary."""
    owner_session = str(session_id or "").strip()
    owner_team = str(team_id or "").strip()
    if not owner_session and not owner_team:
        raise ZapJobError("zap_job_owner_invalid", "ZAP jobs require an owner")
    target_count = len(summary.targets)
    if not 1 <= target_count <= 8:
        raise ZapJobError("zap_job_target_limit", "ZAP jobs require between one and eight targets")
    if summary.policy_level not in {"safe", "intrusive"}:
        raise ZapJobError("zap_job_policy_invalid", "ZAP job policy must be safe or intrusive")
    if not 30 <= summary.job_timeout_seconds <= 86400:
        raise ZapJobError("zap_job_timeout_invalid", "The ZAP job lifetime is invalid")
    try:
        revision = int(http_profile_revision)
    except (TypeError, ValueError) as exc:
        raise ZapJobError("zap_job_profile_invalid", "ZAP jobs require a current HTTP profile") from exc
    if revision < 1:
        raise ZapJobError("zap_job_profile_invalid", "ZAP jobs require a current HTTP profile")

    instant = _utc_now(now)
    created_at = instant.isoformat()
    expires_at = (instant + timedelta(seconds=summary.job_timeout_seconds)).isoformat()
    owner_sql, owner_params = _owner_predicate(
        owner_session,
        owner_team,
        table_prefix="pa",
    )
    job_id = f"zpj_{uuid.uuid4().hex}"
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        current = active_conn.execute(
            "SELECT 1 FROM project_assessments pa "  # nosec B608
            "JOIN project_assessment_checks pc ON pc.assessment_id = pa.id "
            "JOIN project_http_profiles hp ON hp.project_id = pa.project_id "
            "WHERE pa.project_id = ? AND pa.id = ? AND pc.id = ? "
            "AND hp.id = ? AND hp.revision = ? AND hp.enabled = TRUE "
            "AND hp.team_id = pa.team_id "
            "AND (pa.team_id != '' OR hp.session_id = pa.session_id) "
            "AND pa.status = 'active' AND " + owner_sql,
            (
                project_id,
                assessment_id,
                check_id,
                http_profile_id,
                revision,
                *owner_params,
            ),
        ).fetchone()
        if not current:
            raise ZapJobError(
                "zap_job_scope_changed",
                "The Project, assessment check, or HTTP profile is no longer available",
            )
        active_conn.execute(
            "INSERT INTO zap_connector_jobs ("
            "id, session_id, team_id, project_id, assessment_id, check_id, "
            "http_profile_id, http_profile_revision, actor_member_id, actor_role, "
            "policy_level, target_count, plan_summary_json, report_filename, "
            "created_at, updated_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                owner_session,
                owner_team,
                project_id,
                assessment_id,
                check_id,
                http_profile_id,
                revision,
                str(actor_member_id or "")[:96],
                str(actor_role or "")[:32],
                summary.policy_level,
                target_count,
                _json(summary.to_dict()),
                str(summary.report_file or "")[:255],
                created_at,
                created_at,
                expires_at,
            ),
        )
        if owns_conn:
            active_conn.commit()
        row = active_conn.execute(
            "SELECT * FROM zap_connector_jobs WHERE id = ?", (job_id,),
        ).fetchone()
        return _decode_row(row)


def zap_job_for_owner(
    session_id: str,
    job_id: str,
    *,
    team_id: str = "",
    conn=None,
) -> dict[str, Any] | None:
    owner_sql, owner_params = _owner_predicate(str(session_id or ""), str(team_id or ""))
    with _connection_scope(conn) as active_conn:
        row = active_conn.execute(
            "SELECT * FROM zap_connector_jobs WHERE id = ? AND " + owner_sql,  # nosec B608
            (job_id, *owner_params),
        ).fetchone()
        return _decode_row(row) if row else None
