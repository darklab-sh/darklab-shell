"""Session persistence helpers owned by the service layer."""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from urllib.parse import urlsplit, urlunsplit

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.notifications.channels_store import migrate_notification_channels_session
from services.projects.migration import migrate_project_workspace_session
from services.secrets.storage import migrate_session_secrets

log = logging.getLogger("shell")

SESSION_PREFERENCE_KEYS = {
    "pref_active_project_id",
    "pref_project_auto_link_external_runs",
    "pref_project_auto_link_run_entities",
    "pref_theme_name",
    "pref_timestamps",
    "pref_line_numbers",
    "pref_welcome_intro",
    "pref_share_redaction_default",
    "pref_run_notify",
    "pref_command_outcome_summaries",
    "pref_hud_clock",
    "pref_prompt_username",
    "pref_compare_view_mode",
    "pref_compare_context",
    "pref_options_modal_last_tab",
    "pref_tour_seen_version",
    "pref_atlas_saved_views",
    "pref_constellation_full_day",
}

RECENT_VALUE_LIMIT = 10
RECENT_VALUE_KINDS = ("domain", "ip", "url", "port_set")

_PROMPT_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_COMPARE_VIEW_MODES = {"auto", "side_by_side", "unified", "changes_only", "findings_only"}
_COMPARE_CONTEXT_MODES = {"3", "10", "all"}
_OPTIONS_MODAL_TABS = {"preferences", "secrets", "teams", "notifications"}
_ATLAS_SAVED_VIEW_TABS = {"findings", "ip", "domain", "hash", "cve", "url"}
_ATLAS_SAVED_VIEW_FILTER_VALUES = {"hide", "all", "only"}
_ATLAS_SAVED_VIEW_ID_RE = re.compile(r"^atv_[0-9a-f]{16,32}$")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def normalize_session_preferences(raw: Any) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    prefs: dict[str, object] = {}
    for key, value in raw.items():
        if key not in SESSION_PREFERENCE_KEYS:
            continue
        if key == "pref_tour_seen_version":
            try:
                tour_seen_version = int(value)
            except (TypeError, ValueError):
                continue
            if tour_seen_version < 1:
                continue
            prefs[key] = tour_seen_version
            continue
        if key == "pref_atlas_saved_views":
            prefs[key] = normalize_atlas_saved_views(value)
            continue
        if not isinstance(value, str):
            value = str(value or "")
        value = value.strip()
        if not value:
            continue
        if key == "pref_active_project_id" and not re.fullmatch(r"prj_[0-9a-f]{16}", value):
            continue
        if key in {
            "pref_project_auto_link_external_runs",
            "pref_project_auto_link_run_entities",
            "pref_command_outcome_summaries",
        }:
            value = "off" if value.lower() in {"0", "false", "no", "off"} else "on"
        if key == "pref_constellation_full_day":
            value = "on" if value.lower() in {"1", "true", "yes", "on"} else "off"
        if key == "pref_prompt_username" and not _PROMPT_USERNAME_RE.fullmatch(value):
            continue
        if key == "pref_compare_view_mode":
            value = value.lower()
            if value not in _COMPARE_VIEW_MODES:
                continue
        if key == "pref_compare_context":
            value = value.lower()
            if value not in _COMPARE_CONTEXT_MODES:
                continue
        if key == "pref_options_modal_last_tab":
            value = value.lower()
            if value not in _OPTIONS_MODAL_TABS:
                continue
        prefs[key] = value
    return prefs


def normalize_atlas_saved_views(value: Any) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    views: list[dict[str, object]] = []
    seen_ids = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        item_data: dict[str, object] = dict(item)
        view_id = str(item_data.get("id") or "").strip().lower()
        name = str(item_data.get("name") or "").strip()[:60]
        tab = str(item_data.get("tab") or "findings").strip().lower()
        raw_filters = item_data.get("filters")
        filters: dict[str, object] = dict(raw_filters) if isinstance(raw_filters, dict) else {}
        if not name or not _ATLAS_SAVED_VIEW_ID_RE.fullmatch(view_id) or view_id in seen_ids:
            continue
        if tab not in _ATLAS_SAVED_VIEW_TABS:
            tab = "findings"
        orphan_filter = str(filters.get("orphan_filter") or "hide").strip().lower()
        suppression_filter = str(filters.get("suppression_filter") or "hide").strip().lower()
        if orphan_filter not in _ATLAS_SAVED_VIEW_FILTER_VALUES:
            orphan_filter = "hide"
        if suppression_filter not in _ATLAS_SAVED_VIEW_FILTER_VALUES:
            suppression_filter = "hide"
        finding_status = str(filters.get("finding_status") or "").strip().lower()
        if finding_status not in {"", "new", "reviewed", "important", "false_positive", "needs_followup"}:
            finding_status = ""

        def _saved_view_list(key: str) -> list[str]:
            raw_values = filters.get(key)
            raw_items = raw_values if isinstance(raw_values, list) else [raw_values]
            values = []
            seen_values = set()
            for raw_item in raw_items:
                normalized = str(raw_item or "").strip().lower()
                if not normalized or normalized in seen_values:
                    continue
                seen_values.add(normalized)
                values.append(normalized[:120])
                if len(values) >= 12:
                    break
            return values

        views.append({
            "id": view_id,
            "name": name,
            "tab": tab,
            "filters": {
                "query": str(filters.get("query") or "").strip()[:500],
                "orphan_filter": orphan_filter,
                "suppression_filter": suppression_filter,
                "finding_status": finding_status,
                "project_id": str(filters.get("project_id") or "").strip()[:80],
                "project_name": str(filters.get("project_name") or "").strip()[:120],
                "run_id": str(filters.get("run_id") or "").strip()[:120],
                "run_label": str(filters.get("run_label") or "").strip()[:240],
                "sort": str(filters.get("sort") or "").strip()[:80],
                "signals": _saved_view_list("signals"),
                "kinds": _saved_view_list("kinds"),
                "exclude_kinds": _saved_view_list("exclude_kinds"),
                "roles": _saved_view_list("roles"),
                "entities": _saved_view_list("entities"),
                "entity_types": _saved_view_list("entity_types"),
            },
            "updated_at": str(item_data.get("updated_at") or "")[:40],
        })
        seen_ids.add(view_id)
        if len(views) >= 30:
            break
    return views


def decode_preferences(value: Any, *, session_id: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        log.warning("SESSION_PREFERENCES_INVALID", extra={
            "session": get_log_session_id(session_id),
            "session_kind": "token" if str(session_id or "").startswith("tok_") else "anonymous",
            "error_type": type(exc).__name__,
            "json_pos": getattr(exc, "pos", None),
        })
        return {}
    except TypeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def load_session_preferences_from_conn(conn: Any, session_id: str) -> dict[str, object]:
    row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return {}
    return normalize_session_preferences(decode_preferences(row["preferences"], session_id=session_id))


def save_session_preferences_to_conn(conn: Any, session_id: str, preferences: dict[str, object], updated: str) -> None:
    conn.execute(
        "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET preferences = excluded.preferences, updated = excluded.updated",
        (session_id, dialect_for_backend(get_db_backend()).json_param(preferences), updated),
    )


def create_session_token(
    session_token: str,
    created: str,
    *,
    audit_fields: dict[str, Any],
    audit_details: dict[str, Any],
    audit_target_id: str,
) -> None:
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO session_tokens (token, created) VALUES (?, ?) ON CONFLICT(token) DO NOTHING",
            (session_token, created),
        )
        record_event(
            AuditEventType.SESSION_TOKEN_GENERATE,
            target_id=audit_target_id,
            details=audit_details,
            conn=conn,
            **audit_fields,
        )
        conn.commit()


def session_token_created(token: str) -> str | None:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT created FROM session_tokens WHERE token = ?",
            (token,),
        ).fetchone()
    return str(row["created"]) if row else None


def session_token_exists(token: str) -> bool:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_tokens WHERE token = ?",
            (token,),
        ).fetchone()
    return row is not None


def revoke_session_token(
    token: str,
    *,
    audit_fields: dict[str, Any],
    audit_details: dict[str, Any],
    audit_target_id: str,
) -> int:
    with get_db_connect()() as conn:
        result = conn.execute(
            "DELETE FROM session_tokens WHERE token = ?",
            (token,),
        )
        if result.rowcount:
            record_event(
                AuditEventType.SESSION_TOKEN_REVOKE,
                target_id=audit_target_id,
                details=audit_details,
                conn=conn,
                **audit_fields,
            )
            conn.commit()
        return int(result.rowcount or 0)


def _normalize_recent_domain(value: Any) -> str:
    text = str(value or "").strip().lower().rstrip(".")
    if not text or len(text) > 253:
        return ""
    if "/" in text or ":" in text or "@" in text:
        return ""
    if "." not in text:
        return ""
    if _IPV4_RE.fullmatch(text):
        return ""
    labels = text.split(".")
    if len(labels) < 2:
        return ""
    if all(label.isdigit() for label in labels):
        return ""
    for label in labels:
        if len(label) < 1 or len(label) > 63 or not _DOMAIN_LABEL_RE.fullmatch(label):
            return ""
    return text


def _normalize_recent_ip(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text)).lower()
    except ValueError:
        return ""


def _normalize_recent_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or re.search(r"\s", text):
        return ""
    try:
        parsed = urlsplit(text)
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""
        if not parsed.hostname or parsed.username or parsed.password:
            return ""
        port = parsed.port
    except ValueError:
        return ""
    host = parsed.hostname.lower().rstrip(".")
    netloc = f"[{host}]" if ":" in host else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    path = parsed.path or ""
    return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def _normalize_recent_port_set(value: Any) -> str:
    parts = str(value or "").strip().split(",")
    if not parts:
        return ""
    normalized = []
    for part in parts:
        match = re.fullmatch(r"\s*(\d{1,5})(?:\s*-\s*(\d{1,5}))?\s*", part)
        if not match:
            return ""
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        if start < 1 or start > 65535 or end < 1 or end > 65535 or start > end:
            return ""
        value_text = str(start) if start == end else f"{start}-{end}"
        if value_text not in normalized:
            normalized.append(value_text)
    return ",".join(normalized)


def normalize_recent_value(kind: Any, value: Any) -> tuple[str, str]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind == "domain":
        return "domain", _normalize_recent_domain(value)
    if normalized_kind == "ip":
        return "ip", _normalize_recent_ip(value)
    if normalized_kind == "url":
        return "url", _normalize_recent_url(value)
    if normalized_kind == "port_set":
        return "port_set", _normalize_recent_port_set(value)
    return "", ""


def normalize_recent_value_entries(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    entries = []
    seen = set()
    per_kind_counts = {kind: 0 for kind in RECENT_VALUE_KINDS}
    for item in values:
        if not isinstance(item, dict):
            continue
        kind, value = normalize_recent_value(item.get("kind"), item.get("value"))
        if not kind or not value:
            continue
        key = (kind, value)
        if key in seen or per_kind_counts[kind] >= RECENT_VALUE_LIMIT:
            continue
        seen.add(key)
        per_kind_counts[kind] += 1
        entries.append({"kind": kind, "value": value})
    return entries


def _recent_values_response(rows: list[Any]) -> dict[str, list[str]]:
    values = {kind: [] for kind in RECENT_VALUE_KINDS}
    for row in rows:
        kind = str(row["kind"] or "")
        value = str(row["value"] or "")
        if kind in values and value:
            values[kind].append(value)
    return values


def list_recent_values_for_conn(
        conn: Any,
        session_id: str,
        team_id: str = "",
        kinds: Sequence[str] | None = None
    ) -> dict[str, list[str]]:
    normalized_kinds = [kind for kind in (kinds or RECENT_VALUE_KINDS) if kind in RECENT_VALUE_KINDS]
    if not normalized_kinds:
        return {kind: [] for kind in RECENT_VALUE_KINDS}
    rows = conn.execute(
        "SELECT kind, value FROM recent_values "
        "WHERE session_id = ? AND team_id = ? "
        "ORDER BY kind ASC, last_used DESC, value ASC",
        (session_id, team_id),
    ).fetchall()
    kind_set = set(normalized_kinds)
    values = _recent_values_response([row for row in rows if row["kind"] in kind_set])
    return {
        kind: values[kind][:RECENT_VALUE_LIMIT]
        for kind in RECENT_VALUE_KINDS
    }


def list_recent_values(session_id: str, team_id: str = "", kinds: Sequence[str] | None = None) -> dict[str, list[str]]:
    with get_db_connect()() as conn:
        return list_recent_values_for_conn(conn, session_id, team_id, kinds)


def prune_recent_values(conn: Any, session_id: str, team_id: str, kind: str) -> None:
    conn.execute(
        "DELETE FROM recent_values "
        "WHERE session_id = ? AND team_id = ? "
        "AND kind = ? "
        "AND value NOT IN ("
        "    SELECT value FROM recent_values "
        "    WHERE session_id = ? AND team_id = ? AND kind = ? "
        "    ORDER BY last_used DESC, value ASC "
        "    LIMIT ?"
        ")",
        (session_id, team_id, kind, session_id, team_id, kind, RECENT_VALUE_LIMIT),
    )


def upsert_recent_values_for_conn(conn: Any, session_id: str, team_id: str, values: Any) -> int:
    entries = normalize_recent_value_entries(values)
    if not entries:
        return 0
    base_time = datetime.now(timezone.utc)
    touched_kinds = set()
    for index, entry in enumerate(entries):
        last_used = (base_time - timedelta(microseconds=index)).strftime("%Y-%m-%d %H:%M:%S.%f")
        conn.execute(
            "INSERT INTO recent_values (session_id, team_id, kind, value, last_used, use_count) "
            "VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(session_id, team_id, kind, value) DO UPDATE SET "
            "last_used = excluded.last_used, "
            "use_count = recent_values.use_count + 1",
            (session_id, team_id, entry["kind"], entry["value"], last_used),
        )
        touched_kinds.add(entry["kind"])
    for kind in touched_kinds:
        prune_recent_values(conn, session_id, team_id, kind)
    return len(entries)


def save_recent_values(session_id: str, team_id: str, values: Any) -> tuple[int, dict[str, list[str]]]:
    with get_db_connect()() as conn:
        saved = upsert_recent_values_for_conn(conn, session_id, team_id, values)
        response_values = list_recent_values_for_conn(conn, session_id, team_id)
        conn.commit()
    return saved, response_values


def migrate_recent_values_for_conn(conn: Any, from_session_id: str, to_session_id: str) -> int:
    rows = conn.execute(
        "SELECT team_id, kind, value, last_used, use_count FROM recent_values "
        "WHERE session_id = ? "
        "ORDER BY team_id ASC, kind ASC, last_used DESC, value ASC",
        (from_session_id,),
    ).fetchall()
    migrated = 0
    touched_scopes = set()
    for row in rows:
        kind, value = normalize_recent_value(row["kind"], row["value"])
        if not kind or not value:
            continue
        conn.execute(
            "INSERT INTO recent_values (session_id, team_id, kind, value, last_used, use_count) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, team_id, kind, value) DO UPDATE SET "
            "last_used = CASE "
            "  WHEN excluded.last_used > recent_values.last_used THEN excluded.last_used "
            "  ELSE recent_values.last_used "
            "END, "
            "use_count = recent_values.use_count + excluded.use_count",
            (to_session_id, str(row["team_id"] or ""), kind, value, row["last_used"], int(row["use_count"] or 1)),
        )
        migrated += 1
        touched_scopes.add((str(row["team_id"] or ""), kind))
    conn.execute(
        "DELETE FROM recent_values WHERE session_id = ?",
        (from_session_id,),
    )
    for team_id, kind in touched_scopes:
        prune_recent_values(conn, to_session_id, team_id, kind)
    return migrated


def migrate_session_records(
    from_session_id: str,
    to_session_id: str,
    *,
    migrated_workspace_file_paths: Any = (),
    extra_counts: dict[str, int] | None = None,
    audit_fields: dict[str, Any],
    audit_details: dict[str, Any],
    audit_target_id: str,
) -> dict[str, int]:
    with get_db_connect()() as conn:
        runs_result = conn.execute(
            "UPDATE runs SET session_id = ? WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        snaps_result = conn.execute(
            "UPDATE snapshots SET session_id = ? WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        dialect = dialect_for_backend(get_db_backend())
        stars_insert = conn.execute(
            "INSERT INTO starred_commands (session_id, command) "  # nosec B608
            "SELECT ?, command FROM starred_commands WHERE session_id = ? "
            + dialect.insert_or_ignore_clause(("session_id", "command")),
            (to_session_id, from_session_id),
        )
        prefs_insert = conn.execute(
            "INSERT INTO session_preferences (session_id, preferences, updated) "  # nosec B608
            "SELECT ?, preferences, updated FROM session_preferences WHERE session_id = ? "
            + dialect.insert_or_ignore_clause(("session_id",)),
            (to_session_id, from_session_id),
        )
        vars_insert = conn.execute(
            "INSERT INTO session_variables (session_id, name, value, updated) "  # nosec B608
            "SELECT ?, name, value, updated FROM session_variables WHERE session_id = ? "
            + dialect.insert_or_ignore_clause(("session_id", "name")),
            (to_session_id, from_session_id),
        )
        workflows_result = conn.execute(
            "UPDATE user_workflows SET session_id = ? WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        project_migration = migrate_project_workspace_session(
            conn,
            from_session_id,
            to_session_id,
            migrated_workspace_file_paths=migrated_workspace_file_paths,
        )
        migrated_secrets = migrate_session_secrets(conn, from_session_id, to_session_id)
        notification_migration = migrate_notification_channels_session(conn, from_session_id, to_session_id)
        migrated_recent_values = migrate_recent_values_for_conn(conn, from_session_id, to_session_id)
        conn.execute("DELETE FROM starred_commands WHERE session_id = ?", (from_session_id,))
        conn.execute("DELETE FROM session_preferences WHERE session_id = ?", (from_session_id,))
        conn.execute("DELETE FROM session_variables WHERE session_id = ?", (from_session_id,))
        conn.execute("DELETE FROM user_workflows WHERE session_id = ?", (from_session_id,))
        counts = {
            "migrated_runs": int(runs_result.rowcount or 0),
            "migrated_snapshots": int(snaps_result.rowcount or 0),
            "migrated_stars": int(stars_insert.rowcount or 0),
            "migrated_preferences": int(prefs_insert.rowcount or 0),
            "migrated_variables": int(vars_insert.rowcount or 0),
            "migrated_workflows": int(workflows_result.rowcount or 0),
            **project_migration,
            **notification_migration,
            "migrated_recent_values": migrated_recent_values,
            "migrated_secrets": migrated_secrets,
        }
        if extra_counts:
            counts.update({key: int(value or 0) for key, value in extra_counts.items()})
        record_event(
            AuditEventType.SESSION_MIGRATE,
            target_id=audit_target_id,
            details={**audit_details, "migration_counts": counts},
            conn=conn,
            **audit_fields,
        )
        conn.commit()
        return counts


def get_preferences(session_id: str) -> dict[str, Any]:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT preferences, updated FROM session_preferences WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return {"preferences": {}, "updated": None}
    return {
        "preferences": normalize_session_preferences(decode_preferences(row["preferences"], session_id=session_id)),
        "updated": row["updated"],
    }


def save_preferences(session_id: str, raw_preferences: dict[str, object], updated: str) -> dict[str, object]:
    prefs = normalize_session_preferences(raw_preferences)
    with get_db_connect()() as conn:
        if "pref_atlas_saved_views" not in raw_preferences:
            existing_views = load_session_preferences_from_conn(conn, session_id).get("pref_atlas_saved_views")
            if existing_views:
                prefs["pref_atlas_saved_views"] = existing_views
        save_session_preferences_to_conn(conn, session_id, prefs, updated)
        conn.commit()
    return prefs


def mark_tour_seen(session_id: str, tour_version: int, updated: str) -> dict[str, object]:
    with get_db_connect()() as conn:
        prefs = load_session_preferences_from_conn(conn, session_id)
        prefs["pref_tour_seen_version"] = tour_version
        save_session_preferences_to_conn(conn, session_id, prefs, updated)
        conn.commit()
    return prefs


def session_counts(session_id: str) -> dict[str, int]:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        workflow_row = conn.execute(
            "SELECT COUNT(*) AS n FROM user_workflows WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        recent_value_row = conn.execute(
            "SELECT COUNT(*) AS n FROM recent_values WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return {
        "count": int(row["n"] if row else 0),
        "workflow_count": int(workflow_row["n"] if workflow_row else 0),
        "recent_value_count": int(recent_value_row["n"] if recent_value_row else 0),
    }


def list_starred_commands(session_id: str) -> list[str]:
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT command FROM starred_commands WHERE session_id = ? ORDER BY command",
            (session_id,),
        ).fetchall()
    return [str(row["command"]) for row in rows]


def add_starred_command(session_id: str, command: str) -> int:
    with get_db_connect()() as conn:
        result = conn.execute(
            "INSERT INTO starred_commands (session_id, command) VALUES (?, ?) "
            "ON CONFLICT(session_id, command) DO NOTHING",
            (session_id, command),
        )
        conn.commit()
    return int(result.rowcount or 0)


def remove_starred_commands(session_id: str, command: str = "") -> int:
    with get_db_connect()() as conn:
        if command:
            result = conn.execute(
                "DELETE FROM starred_commands WHERE session_id = ? AND command = ?",
                (session_id, command),
            )
        else:
            result = conn.execute(
                "DELETE FROM starred_commands WHERE session_id = ?",
                (session_id,),
            )
        conn.commit()
    return int(result.rowcount or 0)
