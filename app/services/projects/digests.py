"""Project attack-surface digest settings storage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any

from config import CFG
from core import database
from core.database import db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.projects.contracts import ProjectWorkspaceError, ProjectWorkspaceNotFound
from services.projects.monitoring import get_project_monitoring_summary
from services.projects.scope import shared_owner_where
from services.notifications.dispatcher import enqueue as enqueue_notification
from services.notifications.models import TRIGGER_PROJECT_DIGEST
from services.notifications.payloads import build_project_digest_payload
from services.scheduler.models import OWNER_KIND_PROJECT_DIGEST
from services.scheduler.service import create_schedule, pause_schedule, update_schedule

DIGEST_CADENCE_PRESETS = frozenset({"hourly", "daily", "weekly"})
DEFAULT_DIGEST_CADENCE = "daily"
MAX_DIGEST_CHANNEL_IDS = 25
log = logging.getLogger("shell")
_CONFIG_WARNED_KEYS: set[str] = set()
_DIGEST_CADENCE_LOOKBACK_HOURS = {
    "hourly": 1,
    "daily": 24,
    "weekly": 24 * 7,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_param(value: Any) -> Any:
    return dialect_for_backend(database.DB_BACKEND).json_param(value)


def _loads_json_list(value: Any) -> list[str]:
    return [
        str(item)
        for item in dialect_for_backend(database.DB_BACKEND).decode_json_list(value)
        if str(item or "").strip()
    ]


def _normalize_cadence(value: Any) -> str:
    cadence = str(value or _configured_default_cadence()).strip().lower()
    if cadence not in DIGEST_CADENCE_PRESETS:
        raise ProjectWorkspaceError("choose a supported digest cadence")
    return cadence


def _warn_invalid_config_once(key: str, value: Any, fallback: Any) -> None:
    if key in _CONFIG_WARNED_KEYS:
        return
    _CONFIG_WARNED_KEYS.add(key)
    log.warning(
        "PROJECT_DIGEST_CONFIG_INVALID",
        extra={
            "key": key,
            "value": str(value or "")[:80],
            "fallback": str(fallback),
        },
    )


def _configured_default_cadence() -> str:
    raw_settings = CFG.get("project_digests")
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    cadence = str(settings.get("default_cadence_preset") or DEFAULT_DIGEST_CADENCE).strip().lower()
    if cadence in DIGEST_CADENCE_PRESETS:
        return cadence
    _warn_invalid_config_once("project_digests.default_cadence_preset", cadence, DEFAULT_DIGEST_CADENCE)
    return DEFAULT_DIGEST_CADENCE


def _configured_first_send_lookback_hours(cadence: str) -> int:
    fallback = _DIGEST_CADENCE_LOOKBACK_HOURS.get(cadence, 24)
    raw_settings = CFG.get("project_digests")
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    raw_value = settings.get("first_send_lookback_hours")
    try:
        configured = int(raw_value or fallback)
    except (TypeError, ValueError):
        _warn_invalid_config_once("project_digests.first_send_lookback_hours", raw_value, fallback)
        configured = fallback
    return max(1, min(configured, fallback))


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_channel_ids(value: Any) -> tuple[str, ...]:
    raw_items = value if isinstance(value, list | tuple) else []
    normalized: list[str] = []
    for item in raw_items:
        channel_id = str(item or "").strip()
        if not channel_id or channel_id in normalized:
            continue
        normalized.append(channel_id)
        if len(normalized) > MAX_DIGEST_CHANNEL_IDS:
            raise ProjectWorkspaceError("too many digest notification channels")
    return tuple(normalized)


def _bool_flag(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(value)


def _summary_log_fields(summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = summary or {}
    return {
        "changed_count": int(summary.get("changed_monitor_count") or 0),
        "recovered_count": int(summary.get("recovered_monitor_count") or 0),
        "failed_count": int(summary.get("failed_monitor_count") or 0),
        "highest_severity": str(summary.get("highest_severity") or ""),
    }


def _digest_log_context(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    fired_at: str = "",
    window_start: str = "",
    window_end: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "fired_at": fired_at,
        "window_start": window_start,
        "window_end": window_end,
    }
    payload.update(extra)
    return payload


def _mark_evaluated_skip(
    conn: Any,
    *,
    session_id: str,
    project_id: str,
    team_id: str = "",
    fired_at: str,
    reason: str,
    level: int = logging.INFO,
    window_start: str = "",
    window_end: str = "",
    summary: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    mark_digest_evaluated(conn, project_id=project_id, session_id=session_id, team_id=team_id, evaluated_at=fired_at)
    log.log(
        level,
        "PROJECT_DIGEST_SKIPPED",
        extra=_digest_log_context(
            session_id,
            project_id,
            team_id=team_id,
            fired_at=fired_at,
            window_start=window_start,
            window_end=window_end,
            reason=reason,
            **_summary_log_fields(summary),
            **extra,
        ),
    )
    result = {"reason": reason, "queued": 0}
    if window_start or window_end:
        result.update({"window_start": window_start, "window_end": window_end})
    return result


def _project_row(conn: Any, session_id: str, project_id: str, *, team_id: str = "") -> Any:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    return conn.execute(
        "SELECT id, session_id, team_id, status FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
        (*owner_params, project_id),
    ).fetchone()


def _settings_session_id(project: Any, session_id: str, team_id: str) -> str:
    if str(team_id or "").strip() and project is not None:
        return str(project["session_id"] or session_id or "").strip()
    return str(session_id or "").strip()


def _team_is_archived(conn: Any, team_id: str) -> bool:
    if not team_id:
        return False
    row = conn.execute("SELECT status FROM teams WHERE id = ?", (team_id,)).fetchone()
    return row is not None and str(row["status"] or "") == "archived"


def _validate_channel_ids(conn: Any, session_id: str, team_id: str, channel_ids: tuple[str, ...]) -> None:
    if not channel_ids:
        return
    placeholders = ",".join("?" for _ in channel_ids)
    if team_id:
        rows = conn.execute(
            f"SELECT id FROM notification_channels WHERE team_id = ? AND id IN ({placeholders})",  # nosec
            (team_id, *channel_ids),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM notification_channels "
            f"WHERE session_token = ? AND (team_id IS NULL OR team_id = '') AND id IN ({placeholders})",  # nosec
            (session_id, *channel_ids),
        ).fetchall()
    found = {str(row["id"]) for row in rows}
    missing = [channel_id for channel_id in channel_ids if channel_id not in found]
    if missing:
        raise ProjectWorkspaceError("digest notification channels must belong to the same owner scope")


def _schedule_for_digest(conn: Any, session_id: str, project_id: str, *, team_id: str = "") -> Any:
    return conn.execute(
        "SELECT id, enabled, next_run_at, paused_reason, last_error "
        "FROM schedules WHERE owner_kind = ? AND owner_id = ? AND session_token = ? AND team_id = ?",
        (OWNER_KIND_PROJECT_DIGEST, project_id, session_id, team_id),
    ).fetchone()


def _sync_digest_schedule(
    conn: Any,
    *,
    session_id: str,
    project_id: str,
    team_id: str,
    enabled: bool,
    cadence_preset: str,
) -> None:
    row = _schedule_for_digest(conn, session_id, project_id, team_id=team_id)
    if row is None and enabled:
        create_schedule(
            session_id,
            team_id=team_id,
            command_text=f"project digest {project_id}",
            cadence_preset=cadence_preset,
            label="Project digest",
            owner_kind=OWNER_KIND_PROJECT_DIGEST,
            owner_id=project_id,
            conn=conn,
        )
        return
    if row is None:
        return
    schedule_id = str(row["id"])
    if enabled:
        update_schedule(
            schedule_id,
            {
                "command_text": f"project digest {project_id}",
                "cadence_preset": cadence_preset,
                "enabled": True,
                "paused_reason": "",
            },
            conn=conn,
        )
    else:
        pause_schedule(schedule_id, "digest disabled", conn=conn)


def _row_to_settings(
        row: Any, *, default_project_id: str = "",
        default_session_id: str = "",
        default_team_id: str = ""
    ) -> dict[str, Any]:
    if row is None:
        return {
            "project_id": default_project_id,
            "session_id": default_session_id,
            "team_id": default_team_id,
            "enabled": False,
            "cadence_preset": _configured_default_cadence(),
            "channel_ids": [],
            "quiet_no_change": False,
            "last_evaluated_at": "",
            "last_sent_at": "",
            "created": "",
            "updated": "",
        }
    return {
        "project_id": str(row["project_id"]),
        "session_id": str(row["session_id"]),
        "team_id": str(row["team_id"] or ""),
        "enabled": bool(row["enabled"]),
        "cadence_preset": str(row["cadence_preset"] or DEFAULT_DIGEST_CADENCE),
        "channel_ids": _loads_json_list(row["channel_ids_json"]),
        "quiet_no_change": bool(row["quiet_no_change"]),
        "last_evaluated_at": str(row["last_evaluated_at"] or ""),
        "last_sent_at": str(row["last_sent_at"] or ""),
        "created": str(row["created"]),
        "updated": str(row["updated"]),
    }


def _attach_schedule_status(conn: Any, settings: dict[str, Any]) -> dict[str, Any]:
    row = _schedule_for_digest(
        conn,
        str(settings.get("session_id") or ""),
        str(settings.get("project_id") or ""),
        team_id=str(settings.get("team_id") or ""),
    )
    settings = dict(settings)
    settings["next_due_at"] = str(row["next_run_at"] or "") if row is not None else ""
    settings["schedule_enabled"] = bool(row["enabled"]) if row is not None else False
    settings["schedule_paused_reason"] = str(row["paused_reason"] or "") if row is not None else ""
    settings["schedule_last_error"] = str(row["last_error"] or "") if row is not None else ""
    fire = None
    if row is not None:
        fire = conn.execute(
            "SELECT status, reason, fired_at FROM schedule_fires "
            "WHERE schedule_id = ? ORDER BY fired_at DESC, id DESC LIMIT 1",
            (str(row["id"]),),
        ).fetchone()
    settings["schedule_last_fire_status"] = str(fire["status"] or "") if fire is not None else ""
    settings["schedule_last_fire_reason"] = str(fire["reason"] or "") if fire is not None else ""
    settings["schedule_last_fire_at"] = str(fire["fired_at"] or "") if fire is not None else ""
    return settings


def digest_event_identity(
    *,
    project_id: str,
    session_id: str,
    team_id: str = "",
    window_start: str = "",
    window_end: str = "",
) -> dict[str, str]:
    return {
        "project_id": str(project_id or "").strip(),
        "session_id": str(session_id or "").strip(),
        "team_id": str(team_id or "").strip(),
        "window_start": str(window_start or "").strip(),
        "window_end": str(window_end or "").strip(),
    }


def _digest_event_key(identity: dict[str, str]) -> str:
    raw = "\x1f".join([
        str(identity.get("project_id") or ""),
        str(identity.get("session_id") or ""),
        str(identity.get("team_id") or ""),
        str(identity.get("window_start") or ""),
        str(identity.get("window_end") or ""),
    ])
    return "project_digest:" + hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def get_digest_settings(session_id: str, project_id: str, *, team_id: str = "", conn: Any | None = None) -> dict[str, Any] | None:
    if conn is None:
        with db_connect() as opened:
            return get_digest_settings(session_id, project_id, team_id=team_id, conn=opened)

    project = _project_row(conn, session_id, project_id, team_id=team_id)
    if project is None:
        return None
    settings_session_id = _settings_session_id(project, session_id, team_id)
    row = conn.execute(
        "SELECT project_id, session_id, team_id, enabled, cadence_preset, channel_ids_json, "
        "quiet_no_change, last_evaluated_at, last_sent_at, created, updated "
        "FROM project_digest_settings WHERE project_id = ? AND session_id = ? AND team_id = ?",
        (project_id, settings_session_id, team_id),
    ).fetchone()
    settings = _row_to_settings(
        row,
        default_project_id=project_id,
        default_session_id=settings_session_id,
        default_team_id=team_id,
    )
    return _attach_schedule_status(conn, settings)


def save_digest_settings(
    session_id: str,
    project_id: str,
    payload: dict[str, Any],
    *,
    team_id: str = "",
    conn: Any | None = None,
) -> dict[str, Any]:
    if conn is None:
        with db_connect() as opened:
            settings = save_digest_settings(session_id, project_id, payload, team_id=team_id, conn=opened)
            opened.commit()
            return settings

    project = _project_row(conn, session_id, project_id, team_id=team_id)
    if project is None:
        raise ProjectWorkspaceNotFound("project not found")
    settings_session_id = _settings_session_id(project, session_id, team_id)
    enabled = _bool_flag(payload.get("enabled"), default=False)
    if enabled and str(project["status"] or "") == "archived":
        raise ProjectWorkspaceError("archived projects cannot enable digest notifications")
    if enabled and _team_is_archived(conn, team_id):
        raise ProjectWorkspaceError("archived teams cannot enable digest notifications")

    cadence = _normalize_cadence(payload.get("cadence_preset"))
    channel_ids = _normalize_channel_ids(payload.get("channel_ids"))
    if enabled and not channel_ids:
        raise ProjectWorkspaceError("choose at least one digest notification channel")
    _validate_channel_ids(conn, session_id, team_id, channel_ids)
    quiet_no_change = _bool_flag(payload.get("quiet_no_change"), default=False)
    now = _now()
    conn.execute(
        "INSERT INTO project_digest_settings "
        "(project_id, session_id, team_id, enabled, cadence_preset, channel_ids_json, quiet_no_change, "
        "last_evaluated_at, last_sent_at, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, '', '', ?, ?) "
        "ON CONFLICT(project_id, session_id, team_id) DO UPDATE SET "
        "enabled = excluded.enabled, cadence_preset = excluded.cadence_preset, "
        "channel_ids_json = excluded.channel_ids_json, quiet_no_change = excluded.quiet_no_change, "
        "updated = excluded.updated",
        (
            project_id,
            settings_session_id,
            team_id,
            int(enabled),
            cadence,
            _json_param(list(channel_ids)),
            int(quiet_no_change),
            now,
            now,
        ),
    )
    _sync_digest_schedule(
        conn,
        session_id=settings_session_id,
        project_id=project_id,
        team_id=team_id,
        enabled=enabled,
        cadence_preset=cadence,
    )
    settings = get_digest_settings(settings_session_id, project_id, team_id=team_id, conn=conn)
    if settings is None:
        raise ProjectWorkspaceNotFound("project not found")
    return settings


def mark_digest_evaluated(
    conn: Any,
    *,
    project_id: str,
    session_id: str,
    team_id: str = "",
    evaluated_at: str | None = None,
) -> dict[str, Any] | None:
    parsed = _parse_time(evaluated_at)
    stamp = parsed.isoformat() if parsed is not None else _now()
    conn.execute(
        "UPDATE project_digest_settings SET last_evaluated_at = ?, updated = ? "
        "WHERE project_id = ? AND session_id = ? AND team_id = ? "
        "AND (last_evaluated_at IS NULL OR last_evaluated_at = '' OR last_evaluated_at < ?)",
        (stamp, stamp, project_id, session_id, team_id, stamp),
    )
    return get_digest_settings(session_id, project_id, team_id=team_id, conn=conn)


def mark_digest_sent(
    conn: Any,
    *,
    project_id: str,
    session_id: str,
    team_id: str = "",
    sent_at: str | None = None,
) -> dict[str, Any] | None:
    parsed = _parse_time(sent_at)
    stamp = parsed.isoformat() if parsed is not None else _now()
    conn.execute(
        "UPDATE project_digest_settings SET last_sent_at = ?, updated = ? "
        "WHERE project_id = ? AND session_id = ? AND team_id = ? "
        "AND (last_sent_at IS NULL OR last_sent_at = '' OR last_sent_at < ?)",
        (stamp, stamp, project_id, session_id, team_id, stamp),
    )
    return get_digest_settings(session_id, project_id, team_id=team_id, conn=conn)


def _window_start(settings: dict[str, Any], fired_at: str) -> str:
    sent_at = _parse_time(settings.get("last_sent_at"))
    end = _parse_time(fired_at) or datetime.now(timezone.utc)
    if sent_at is not None:
        return sent_at.isoformat()
    cadence = str(settings.get("cadence_preset") or DEFAULT_DIGEST_CADENCE)
    return (end - timedelta(hours=_configured_first_send_lookback_hours(cadence))).isoformat()


def _summary_has_changes(summary: dict[str, Any]) -> bool:
    return any(
        int(summary.get(key) or 0) > 0
        for key in ("changed_monitor_count", "recovered_monitor_count", "failed_monitor_count")
    )


def evaluate_due_digest(
    conn: Any,
    *,
    session_id: str,
    project_id: str,
    team_id: str = "",
    fired_at: str,
) -> dict[str, Any]:
    settings = get_digest_settings(session_id, project_id, team_id=team_id, conn=conn)
    if settings is None:
        log.info(
            "PROJECT_DIGEST_SKIPPED",
            extra=_digest_log_context(
                session_id,
                project_id,
                team_id=team_id,
                fired_at=fired_at,
                reason="digest skipped: project not found",
            ),
        )
        return {"reason": "digest skipped: project not found", "queued": 0}
    if not settings["enabled"]:
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: disabled",
        )
    project = _project_row(conn, session_id, project_id, team_id=team_id)
    if project is None:
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: project unavailable",
            level=logging.WARNING,
        )
    if str(project["status"] or "") == "archived":
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: project archived",
        )
    if _team_is_archived(conn, team_id):
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: team archived",
        )
    channel_ids = [str(channel_id) for channel_id in settings.get("channel_ids") or [] if str(channel_id or "").strip()]
    if not channel_ids:
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: no configured channels",
            level=logging.WARNING,
        )

    window_start = _window_start(settings, fired_at)
    window_end = str(fired_at or _now())
    log.debug(
        "PROJECT_DIGEST_EVALUATION_STARTED",
        extra=_digest_log_context(
            session_id,
            project_id,
            team_id=team_id,
            fired_at=fired_at,
            window_start=window_start,
            window_end=window_end,
            cadence_preset=str(settings.get("cadence_preset") or ""),
            last_sent_at=str(settings.get("last_sent_at") or ""),
            last_evaluated_at=str(settings.get("last_evaluated_at") or ""),
            channel_count=len(channel_ids),
            quiet_no_change=bool(settings.get("quiet_no_change")),
        ),
    )
    try:
        summary_payload = get_project_monitoring_summary(
            session_id,
            project_id,
            team_id=team_id,
            window_start=window_start,
            window_end=window_end,
        )
    except Exception:
        log.error(
            "PROJECT_DIGEST_EVALUATION_FAILED",
            exc_info=True,
            extra=_digest_log_context(
                session_id,
                project_id,
                team_id=team_id,
                fired_at=fired_at,
                window_start=window_start,
                window_end=window_end,
                phase="summary",
                channel_count=len(channel_ids),
            ),
        )
        raise
    if summary_payload is None:
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: project unavailable",
            level=logging.WARNING,
            window_start=window_start,
            window_end=window_end,
        )
    window_summary = summary_payload.get("window_summary") or {}
    if not isinstance(window_summary, dict):
        window_summary = {}
    has_changes = _summary_has_changes(window_summary)
    quiet = bool(settings.get("quiet_no_change"))
    if not has_changes and not quiet:
        return _mark_evaluated_skip(
            conn,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            fired_at=fired_at,
            reason="digest skipped: no changes",
            window_start=window_start,
            window_end=window_end,
            summary=window_summary,
            channel_count=len(channel_ids),
            quiet_no_change=quiet,
        )

    identity = digest_event_identity(
        project_id=project_id,
        session_id=session_id,
        team_id=team_id,
        window_start=window_start,
        window_end=window_end,
    )
    try:
        event_ids = enqueue_notification(
            TRIGGER_PROJECT_DIGEST,
            build_project_digest_payload(
                project=summary_payload["project"],
                summary=window_summary,
                digest_identity=identity,
                quiet=not has_changes,
            ),
            session_id,
            conn=conn,
            channel_ids=channel_ids,
            require_trigger_match=False,
            team_id=team_id,
            run_id=_digest_event_key(identity),
        )
    except Exception:
        log.error(
            "PROJECT_DIGEST_EVALUATION_FAILED",
            exc_info=True,
            extra=_digest_log_context(
                session_id,
                project_id,
                team_id=team_id,
                fired_at=fired_at,
                window_start=window_start,
                window_end=window_end,
                phase="enqueue",
                channel_count=len(channel_ids),
                **_summary_log_fields(window_summary),
            ),
        )
        raise
    mark_digest_evaluated(conn, project_id=project_id, session_id=session_id, team_id=team_id, evaluated_at=fired_at)
    if not event_ids:
        log.warning(
            "PROJECT_DIGEST_CHANNELS_UNAVAILABLE",
            extra=_digest_log_context(
                session_id,
                project_id,
                team_id=team_id,
                fired_at=fired_at,
                window_start=window_start,
                window_end=window_end,
                channel_count=len(channel_ids),
                quiet_no_change=quiet,
                **_summary_log_fields(window_summary),
            ),
        )
    else:
        log.info(
            "PROJECT_DIGEST_QUEUED",
            extra=_digest_log_context(
                session_id,
                project_id,
                team_id=team_id,
                fired_at=fired_at,
                window_start=window_start,
                window_end=window_end,
                queued=len(event_ids),
                channel_count=len(channel_ids),
                quiet_no_change=quiet,
                **_summary_log_fields(window_summary),
            ),
        )
    return {
        "reason": "digest queued" if event_ids else "digest skipped: no eligible channels",
        "queued": len(event_ids),
        "event_ids": event_ids,
        "window_start": window_start,
        "window_end": window_end,
    }
