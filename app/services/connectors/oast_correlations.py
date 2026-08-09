# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable, owner-scoped reservations for explicit private OAST actions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
import secrets
from typing import Any
import uuid

from core.database_access import get_db_connect
from services.connectors.oast_config import OastConnectorSettings


_ACTIVE_STATUSES = ("reserved", "active")
_CORRELATION_ID_RE = re.compile(r"ocr_[0-9a-f]{32}")
_CALLBACK_LABEL_RE = re.compile(r"[a-z0-9]{33}")
_CALLBACK_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_ACTION_KEY_RE = re.compile(r"oast_[a-z0-9_]{1,80}")
_MIN_WINDOW_SECONDS = 60
_MAX_WINDOW_SECONDS = 3600
_MAX_ACTIVE_PER_OWNER = 32
_MAX_ACTIVE_PER_CHECK = 4


class OastCorrelationError(RuntimeError):
    """Raised when an OAST reservation or lifecycle operation fails closed."""

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
        raise OastCorrelationError(
            "oast_correlation_time_invalid",
            "OAST correlation timestamps must include a timezone",
        )
    return value.astimezone(timezone.utc)


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


def _decode_row(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["callback_domain"] = (
        f"{data['callback_label']}.{data['allowed_domain']}"
    )
    return data


def new_oast_correlation_id() -> str:
    return f"ocr_{uuid.uuid4().hex}"


def new_oast_callback_label() -> str:
    """Return an Interactsh-default 20-character id plus 13-character nonce."""
    return "".join(secrets.choice(_CALLBACK_ALPHABET) for _ in range(33))


def _validate_settings(settings: OastConnectorSettings) -> None:
    if not settings.enabled or not settings.privacy_acknowledged:
        raise OastCorrelationError(
            "oast_correlation_disabled",
            "Private OAST correlation is not enabled and acknowledged",
        )
    if not settings.base_url or not settings.allowed_domain:
        raise OastCorrelationError(
            "oast_correlation_config_invalid",
            "Private OAST correlation settings are incomplete",
        )


def reserve_oast_correlation(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    action_key: str,
    settings: OastConnectorSettings,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    window_seconds: int = 900,
    correlation_id: str = "",
    callback_label: str = "",
    now: datetime | None = None,
    conn=None,
) -> dict[str, Any]:
    """Reserve one private callback identity without contacting its provider."""
    _validate_settings(settings)
    owner_session = str(session_id or "").strip()
    owner_team = str(team_id or "").strip()
    if not owner_session and not owner_team:
        raise OastCorrelationError(
            "oast_correlation_owner_invalid", "OAST correlations require an owner"
        )
    selected_action = str(action_key or "").strip()
    if not _ACTION_KEY_RE.fullmatch(selected_action):
        raise OastCorrelationError(
            "oast_correlation_action_invalid",
            "The reviewed OAST action is invalid",
        )
    try:
        active_seconds = int(window_seconds)
        retention_seconds = int(settings.callback_retention_seconds)
    except (TypeError, ValueError) as exc:
        raise OastCorrelationError(
            "oast_correlation_window_invalid",
            "The OAST correlation window is invalid",
        ) from exc
    if (
        not _MIN_WINDOW_SECONDS <= active_seconds <= _MAX_WINDOW_SECONDS
        or active_seconds > retention_seconds
    ):
        raise OastCorrelationError(
            "oast_correlation_window_invalid",
            "The OAST correlation window is outside its retention boundary",
        )

    instant = _utc_now(now)
    created_at = instant.isoformat()
    active_until = (instant + timedelta(seconds=active_seconds)).isoformat()
    purge_at = (instant + timedelta(seconds=retention_seconds)).isoformat()
    selected_id = str(correlation_id or "").strip() or new_oast_correlation_id()
    selected_label = str(callback_label or "").strip() or new_oast_callback_label()
    if not _CORRELATION_ID_RE.fullmatch(selected_id):
        raise OastCorrelationError(
            "oast_correlation_id_invalid", "The OAST correlation id is invalid"
        )
    if not _CALLBACK_LABEL_RE.fullmatch(selected_label):
        raise OastCorrelationError(
            "oast_callback_label_invalid", "The private OAST callback label is invalid"
        )

    owner_sql, owner_params = _owner_predicate(
        owner_session,
        owner_team,
        table_prefix="pa",
    )
    owns_conn = conn is None
    with _connection_scope(conn) as active_conn:
        scope = active_conn.execute(
            "SELECT pc.target_entity_id, pc.policy_level, pc.recommended_action_key "
            "FROM project_assessments pa "
            "JOIN project_assessment_checks pc ON pc.assessment_id = pa.id "
            "JOIN project_links target_link ON target_link.project_id = pa.project_id "
            "AND target_link.entity_id = pc.target_entity_id "
            "AND target_link.entity_type = pc.target_type "
            "WHERE pa.project_id = ? AND pa.id = ? AND pc.id = ? "
            "AND pa.status = 'active' AND pc.applicability = 'applicable' "
            "AND target_link.review_state = 'confirmed' AND " + owner_sql,  # nosec B608
            (project_id, assessment_id, check_id, *owner_params),
        ).fetchone()
        if (
            scope is None
            or str(scope["policy_level"] or "") != "intrusive"
            or str(scope["recommended_action_key"] or "") != selected_action
        ):
            raise OastCorrelationError(
                "oast_correlation_scope_changed",
                "The Project, assessment check, target, or reviewed action changed",
            )
        owner_count = active_conn.execute(
            "SELECT COUNT(*) AS count FROM oast_correlations WHERE "  # nosec B608
            + _owner_predicate(owner_session, owner_team)[0]
            + " AND status IN ('reserved', 'active') AND active_until > ?",
            (*_owner_predicate(owner_session, owner_team)[1], created_at),
        ).fetchone()
        check_count = active_conn.execute(
            "SELECT COUNT(*) AS count FROM oast_correlations WHERE assessment_id = ? "
            "AND check_id = ? AND status IN ('reserved', 'active') AND active_until > ?",
            (assessment_id, check_id, created_at),
        ).fetchone()
        if int(owner_count["count"] if owner_count else 0) >= _MAX_ACTIVE_PER_OWNER:
            raise OastCorrelationError(
                "oast_correlation_owner_limit",
                "The owner has too many active OAST correlations",
            )
        if int(check_count["count"] if check_count else 0) >= _MAX_ACTIVE_PER_CHECK:
            raise OastCorrelationError(
                "oast_correlation_check_limit",
                "The assessment check has too many active OAST correlations",
            )
        active_conn.execute(
            "INSERT INTO oast_correlations ("
            "id, session_id, team_id, project_id, assessment_id, check_id, "
            "target_entity_id, action_key, callback_label, allowed_domain, "
            "service_origin_sha256, actor_member_id, actor_role, created_at, "
            "updated_at, active_until, purge_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                selected_id,
                owner_session,
                owner_team,
                project_id,
                assessment_id,
                check_id,
                str(scope["target_entity_id"]),
                selected_action,
                selected_label,
                settings.allowed_domain,
                sha256(settings.base_url.encode("utf-8")).hexdigest(),
                str(actor_member_id or "")[:96],
                str(actor_role or "")[:32],
                created_at,
                created_at,
                active_until,
                purge_at,
            ),
        )
        if owns_conn:
            active_conn.commit()
        row = active_conn.execute(
            "SELECT * FROM oast_correlations WHERE id = ?", (selected_id,)
        ).fetchone()
        return _decode_row(row)


def oast_correlation_for_owner(
    session_id: str,
    correlation_id: str,
    *,
    team_id: str = "",
    conn=None,
) -> dict[str, Any] | None:
    owner_sql, owner_params = _owner_predicate(
        str(session_id or ""), str(team_id or "")
    )
    with _connection_scope(conn) as active_conn:
        row = active_conn.execute(
            "SELECT * FROM oast_correlations WHERE id = ? AND " + owner_sql,  # nosec B608
            (correlation_id, *owner_params),
        ).fetchone()
        return _decode_row(row) if row else None


def oast_correlations_for_owner_check(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str = "",
    limit: int = 10,
    conn=None,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 25))
    owner_sql, owner_params = _owner_predicate(
        str(session_id or ""), str(team_id or "")
    )
    with _connection_scope(conn) as active_conn:
        rows = active_conn.execute(
            "SELECT * FROM oast_correlations WHERE project_id = ? "  # nosec B608
            "AND assessment_id = ? AND check_id = ? AND "
            + owner_sql
            + " ORDER BY created_at DESC, id DESC LIMIT ?",
            (project_id, assessment_id, check_id, *owner_params, bounded_limit),
        ).fetchall()
        return [_decode_row(row) for row in rows]
