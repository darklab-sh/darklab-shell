"""Audit event recording with bounded, allowlisted detail payloads."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from config import CFG
from core import database
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.teams.storage import token_hash

from .models import DETAILS_VERSION, AuditEventType, AuditTargetType, RecordingMode, event_spec

log = logging.getLogger("shell")

MAX_DETAIL_STRING_CHARS = 2048
MAX_DETAIL_LIST_ITEMS = 50
MAX_DETAILS_BYTES = 32768
MAX_USER_AGENT_CHARS = 256


class AuditRecordError(RuntimeError):
    """Raised when a fail-closed audit event cannot be recorded safely."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_id() -> str:
    return f"aud_{uuid.uuid4().hex}"


def _cfg(cfg: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return cfg if cfg is not None else CFG


def audit_log_enabled(cfg: Mapping[str, Any] | None = None) -> bool:
    return bool(_cfg(cfg).get("audit_log_enabled", True))


def _safe_text(value: Any, *, limit: int = MAX_DETAIL_STRING_CHARS) -> str:
    return str(value or "").strip()[:limit]


def _session_hash(session_id: str) -> str:
    value = str(session_id or "").strip()
    return token_hash(value) if value else ""


def _safe_detail_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_DETAIL_STRING_CHARS]
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, child in list(value.items())[:MAX_DETAIL_LIST_ITEMS]:
            sanitized[str(key)[:128]] = _safe_detail_value(child, depth=depth + 1)
        if len(value) > MAX_DETAIL_LIST_ITEMS:
            sanitized["details_truncated"] = True
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [_safe_detail_value(item, depth=depth + 1) for item in list(value)[:MAX_DETAIL_LIST_ITEMS]]
        if len(value) > MAX_DETAIL_LIST_ITEMS:
            items.append("[truncated]")
        return items
    return str(value)[:MAX_DETAIL_STRING_CHARS]


def _json_size(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _sanitize_details(
    details: Mapping[str, Any] | None,
    *,
    event_type: str,
) -> dict[str, Any]:
    spec = event_spec(event_type)
    raw = dict(details or {})
    sanitized: dict[str, Any] = {}
    omitted = 0
    for key, value in raw.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            omitted += 1
            continue
        if normalized_key not in spec.allowed_detail_keys:
            if spec.recording_mode == RecordingMode.FAIL_CLOSED:
                raise AuditRecordError(f"detail key is not allowed for {event_type}: {normalized_key}")
            omitted += 1
            continue
        sanitized[normalized_key] = _safe_detail_value(value)
    if omitted:
        sanitized["omitted_detail_keys"] = int(sanitized.get("omitted_detail_keys") or 0) + omitted
    if _json_size(sanitized) > MAX_DETAILS_BYTES:
        return {
            "details_truncated": True,
            "omitted_detail_keys": int(sanitized.get("omitted_detail_keys") or 0),
        }
    return sanitized


def _json_param(value: Mapping[str, Any]) -> Any:
    return dialect_for_backend(database.DB_BACKEND).json_param(value)


@contextmanager
def _managed_connection(conn=None):
    if conn is not None:
        yield conn, False
        return
    with database.db_connect() as opened:
        yield opened, True


@contextmanager
def _best_effort_savepoint(conn, *, enabled: bool):
    if not enabled:
        yield
        return
    savepoint_name = f"audit_best_effort_{uuid.uuid4().hex}"
    conn.execute(f"SAVEPOINT {savepoint_name}")  # nosec
    try:
        yield
    except Exception:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")  # nosec
            conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")  # nosec
        except Exception:
            log.exception("AUDIT_EVENT_SAVEPOINT_ROLLBACK_FAILED")
        raise
    else:
        conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")  # nosec


def _fallback_log_payload(
    *,
    event_type: str,
    target_type: str,
    target_id: str,
    project_id: str,
    correlation_id: str,
    job_id: str,
    details: Mapping[str, Any],
    error: Exception,
    recording_mode: str,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "target_type": target_type,
        "target_id": target_id,
        "project_id": project_id,
        "correlation_id": correlation_id,
        "job_id": job_id,
        "recording_mode": recording_mode,
        "details": dict(details),
        "error": str(error)[:MAX_DETAIL_STRING_CHARS],
    }


def record_event(
    event_type: str | AuditEventType,
    *,
    target_type: str | AuditTargetType | None = None,
    target_id: str = "",
    session_id: str = "",
    team_id: str = "",
    actor_session_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
    project_id: str = "",
    request_id: str = "",
    correlation_id: str = "",
    job_id: str = "",
    client_ip: str = "",
    user_agent: str = "",
    details: Mapping[str, Any] | None = None,
    conn=None,
    cfg: Mapping[str, Any] | None = None,
    created: str | None = None,
) -> str | None:
    """Record an audit event.

    Fail-closed events raise when the event cannot be stored. Best-effort events
    emit a sanitized fallback log line and return ``None`` on recorder failure.
    """
    if not audit_log_enabled(cfg):
        return None
    normalized_event_type = (
        event_type.value if isinstance(event_type, AuditEventType) else str(event_type or "").strip()
    )
    spec = event_spec(normalized_event_type)
    normalized_target_type = (
        target_type.value if isinstance(target_type, AuditTargetType)
        else str(target_type or spec.target_type.value).strip()
    )
    sanitized_details = _sanitize_details(details, event_type=normalized_event_type)
    audit_id = _event_id()
    params = (
        audit_id,
        _session_hash(session_id),
        _safe_text(team_id),
        _session_hash(actor_session_id or session_id),
        _safe_text(get_log_session_id(actor_session_id or session_id)),
        _safe_text(actor_member_id),
        _safe_text(actor_role, limit=64),
        _safe_text(actor_display_name, limit=128),
        normalized_event_type,
        normalized_target_type,
        _safe_text(target_id, limit=128),
        _safe_text(project_id, limit=128),
        _safe_text(request_id, limit=128),
        _safe_text(correlation_id, limit=128),
        _safe_text(job_id, limit=128),
        DETAILS_VERSION,
        created or _now(),
        _safe_text(client_ip, limit=128),
        _safe_text(user_agent, limit=MAX_USER_AGENT_CHARS),
        _json_param(sanitized_details),
    )
    try:
        with _managed_connection(conn) as (active_conn, owns_conn):
            with _best_effort_savepoint(
                active_conn,
                enabled=not owns_conn and spec.recording_mode == RecordingMode.BEST_EFFORT,
            ):
                active_conn.execute(
                    """
                    INSERT INTO audit_events (
                        id, owner_session_hash, team_id, actor_session_hash, actor_session_label,
                        actor_member_id, actor_role, actor_display_name, event_type, target_type,
                        target_id, project_id, request_id, correlation_id, job_id, details_version,
                        created, client_ip, user_agent, details
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
            if owns_conn:
                active_conn.commit()
    except Exception as exc:
        if spec.recording_mode == RecordingMode.BEST_EFFORT:
            log.warning(
                "AUDIT_EVENT_RECORD_FAILED",
                extra=_fallback_log_payload(
                    event_type=normalized_event_type,
                    target_type=normalized_target_type,
                    target_id=_safe_text(target_id, limit=128),
                    project_id=_safe_text(project_id, limit=128),
                    correlation_id=_safe_text(correlation_id, limit=128),
                    job_id=_safe_text(job_id, limit=128),
                    details=sanitized_details,
                    error=exc,
                    recording_mode=spec.recording_mode.value,
                ),
            )
            return None
        log.warning(
            "AUDIT_EVENT_RECORD_BLOCKED",
            extra=_fallback_log_payload(
                event_type=normalized_event_type,
                target_type=normalized_target_type,
                target_id=_safe_text(target_id, limit=128),
                project_id=_safe_text(project_id, limit=128),
                correlation_id=_safe_text(correlation_id, limit=128),
                job_id=_safe_text(job_id, limit=128),
                details=sanitized_details,
                error=exc,
                recording_mode=spec.recording_mode.value,
            ),
        )
        raise AuditRecordError(f"failed to record audit event {normalized_event_type}") from exc
    return audit_id
