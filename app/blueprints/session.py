"""
Session token routes: session token generation and session history migration.
"""

import json
import logging
import ipaddress
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

from flask import Blueprint, jsonify, request

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from services.commands.registry import load_tour
from core.helpers import get_client_ip, get_log_session_id, get_session_id, is_valid_anonymous_session_id
from services.notifications.channels_store import migrate_notification_channels_session
from services.projects.migration import migrate_project_workspace_session
from services.secrets.storage import migrate_session_secrets
from services.session.variables import list_session_variables
from services.workflows.user_workflows import (
    UserWorkflowError,
    create_user_workflow,
    delete_user_workflow,
    get_user_workflow,
    list_user_workflows,
    update_user_workflow,
)
from services.workspace.files import InvalidWorkspacePath, migrate_session_workspace, workspace_usage

log = logging.getLogger("shell")

session_bp = Blueprint("session", __name__)

_SESSION_PREFERENCE_KEYS = {
    "pref_active_project_id",
    "pref_project_auto_link_external_runs",
    "pref_project_auto_link_run_entities",
    "pref_theme_name",
    "pref_timestamps",
    "pref_line_numbers",
    "pref_welcome_intro",
    "pref_share_redaction_default",
    "pref_run_notify",
    "pref_hud_clock",
    "pref_prompt_username",
    "pref_compare_view_mode",
    "pref_compare_context",
    "pref_options_modal_last_tab",
    "pref_tour_seen_version",
    "pref_atlas_saved_views",
    "pref_constellation_full_day",
}

_PROMPT_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_COMPARE_VIEW_MODES = {"auto", "side_by_side", "unified", "changes_only", "findings_only"}
_COMPARE_CONTEXT_MODES = {"3", "10", "all"}
_OPTIONS_MODAL_TABS = {"preferences", "secrets", "notifications"}
_ATLAS_SAVED_VIEW_TABS = {"findings", "ip", "domain", "hash", "cve", "url"}
_ATLAS_SAVED_VIEW_FILTER_VALUES = {"hide", "all", "only"}
_ATLAS_SAVED_VIEW_ID_RE = re.compile(r"^atv_[0-9a-f]{16,32}$")

_RECENT_VALUE_LIMIT = 10
_RECENT_VALUE_KINDS = ("domain", "ip", "url", "port_set")
_DOMAIN_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _session_kind(session_id):
    return "token" if str(session_id or "").startswith("tok_") else "anonymous"


def _command_root(command):
    return str(command or "").strip().split(maxsplit=1)[0].lower()


def _normalize_session_preferences(raw):
    if not isinstance(raw, dict):
        return {}
    prefs = {}
    for key, value in raw.items():
        if key not in _SESSION_PREFERENCE_KEYS:
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
            prefs[key] = _normalize_atlas_saved_views(value)
            continue
        if not isinstance(value, str):
            value = str(value or "")
        value = value.strip()
        if not value:
            continue
        if key == "pref_active_project_id" and not re.fullmatch(r"prj_[0-9a-f]{16}", value):
            continue
        if key in {"pref_project_auto_link_external_runs", "pref_project_auto_link_run_entities"}:
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


def _normalize_atlas_saved_views(value):
    if not isinstance(value, list):
        return []
    views = []
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

        def _saved_view_list(key):
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


def _load_session_preferences(conn, session_id):
    row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return {}
    return _normalize_session_preferences(_decode_preferences(row["preferences"], session_id=session_id))


def _decode_preferences(value, *, session_id=""):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        log.warning("SESSION_PREFERENCES_INVALID", extra={
            "session": str(session_id or ""),
            "error": str(exc),
        })
        return {}
    except TypeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _save_session_preferences(conn, session_id, preferences, updated):
    conn.execute(
        "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET preferences = excluded.preferences, updated = excluded.updated",
        (session_id, dialect_for_backend(DB_BACKEND).json_param(preferences), updated),
    )


def _current_tour_version():
    tour = load_tour()
    version = tour.get("version", 0)
    try:
        return int(version)
    except (TypeError, ValueError):
        return 0


def _normalize_recent_domain(value):
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


def _normalize_recent_ip(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text)).lower()
    except ValueError:
        return ""


def _normalize_recent_url(value):
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


def _normalize_recent_port_set(value):
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


def _normalize_recent_value(kind, value):
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


def _normalize_recent_value_entries(values):
    if not isinstance(values, list):
        return []
    entries = []
    seen = set()
    per_kind_counts = {kind: 0 for kind in _RECENT_VALUE_KINDS}
    for item in values:
        if not isinstance(item, dict):
            continue
        kind, value = _normalize_recent_value(item.get("kind"), item.get("value"))
        if not kind or not value:
            continue
        key = (kind, value)
        if key in seen or per_kind_counts[kind] >= _RECENT_VALUE_LIMIT:
            continue
        seen.add(key)
        per_kind_counts[kind] += 1
        entries.append({"kind": kind, "value": value})
    return entries


def _recent_values_response(rows):
    values = {kind: [] for kind in _RECENT_VALUE_KINDS}
    for row in rows:
        kind = str(row["kind"] or "")
        value = str(row["value"] or "")
        if kind in values and value:
            values[kind].append(value)
    return values


def _list_recent_values(conn, session_id, kinds=None):
    normalized_kinds = [kind for kind in (kinds or _RECENT_VALUE_KINDS) if kind in _RECENT_VALUE_KINDS]
    if not normalized_kinds:
        return {kind: [] for kind in _RECENT_VALUE_KINDS}
    rows = conn.execute(
        "SELECT kind, value FROM recent_values "
        "WHERE session_id = ? "
        "ORDER BY kind ASC, last_used DESC, value ASC",
        (session_id,),
    ).fetchall()
    kind_set = set(normalized_kinds)
    values = _recent_values_response([row for row in rows if row["kind"] in kind_set])
    return {
        kind: values[kind][:_RECENT_VALUE_LIMIT]
        for kind in _RECENT_VALUE_KINDS
    }


def _prune_recent_values(conn, session_id, kind):
    conn.execute(
        "DELETE FROM recent_values "
        "WHERE session_id = ? "
        "AND kind = ? "
        "AND value NOT IN ("
        "    SELECT value FROM recent_values "
        "    WHERE session_id = ? AND kind = ? "
        "    ORDER BY last_used DESC, value ASC "
        "    LIMIT ?"
        ")",
        (session_id, kind, session_id, kind, _RECENT_VALUE_LIMIT),
    )


def _upsert_recent_values(conn, session_id, values):
    entries = _normalize_recent_value_entries(values)
    if not entries:
        return 0
    base_time = datetime.now(timezone.utc)
    touched_kinds = set()
    for index, entry in enumerate(entries):
        last_used = (base_time - timedelta(microseconds=index)).strftime("%Y-%m-%d %H:%M:%S.%f")
        conn.execute(
            "INSERT INTO recent_values (session_id, kind, value, last_used, use_count) "
            "VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(session_id, kind, value) DO UPDATE SET "
            "last_used = excluded.last_used, "
            "use_count = recent_values.use_count + 1",
            (session_id, entry["kind"], entry["value"], last_used),
        )
        touched_kinds.add(entry["kind"])
    for kind in touched_kinds:
        _prune_recent_values(conn, session_id, kind)
    return len(entries)


def _migrate_recent_values(conn, from_session_id, to_session_id):
    rows = conn.execute(
        "SELECT kind, value, last_used, use_count FROM recent_values "
        "WHERE session_id = ? "
        "ORDER BY kind ASC, last_used DESC, value ASC",
        (from_session_id,),
    ).fetchall()
    migrated = 0
    touched_kinds = set()
    for row in rows:
        kind, value = _normalize_recent_value(row["kind"], row["value"])
        if not kind or not value:
            continue
        conn.execute(
            "INSERT INTO recent_values (session_id, kind, value, last_used, use_count) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id, kind, value) DO UPDATE SET "
            "last_used = CASE "
            "  WHEN excluded.last_used > recent_values.last_used THEN excluded.last_used "
            "  ELSE recent_values.last_used "
            "END, "
            "use_count = recent_values.use_count + excluded.use_count",
            (to_session_id, kind, value, row["last_used"], int(row["use_count"] or 1)),
        )
        migrated += 1
        touched_kinds.add(kind)
    conn.execute(
        "DELETE FROM recent_values WHERE session_id = ?",
        (from_session_id,),
    )
    for kind in touched_kinds:
        _prune_recent_values(conn, to_session_id, kind)
    return migrated


@session_bp.route("/session/token/generate")
def session_token_generate():
    """Generate a new session token, persist it, and return it.

    The token uses a cryptographically random 32-hex-character suffix with a
    ``tok_`` prefix so it is visually distinct from UUID session IDs in logs
    and the database.  The caller is responsible for storing the token in
    ``localStorage`` as ``session_token`` and sending it as ``X-Session-ID``
    on subsequent requests.
    """
    session_token = "tok_" + secrets.token_hex(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO session_tokens (token, created) VALUES (?, ?) ON CONFLICT(token) DO NOTHING",
            (session_token, created),
        )
        conn.commit()
    log.info("SESSION_TOKEN_GENERATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(get_session_id()),
        "session_kind": _session_kind(get_session_id()),
    })
    return jsonify({"session_token": session_token})


@session_bp.route("/session/token/info")
def session_token_info():
    """Return the current session token and its creation date.

    Returns ``{"token": "tok_...", "created": "YYYY-MM-DD HH:MM:SS"}`` when the
    caller is using a named session token, or ``{"token": null, "created": null}``
    for anonymous UUID sessions.  The ``created`` field may be ``null`` for tokens
    that pre-date the ``created`` column (edge case in older deployments).
    """
    session_id = get_session_id()
    if not session_id.startswith("tok_"):
        return jsonify({"token": None, "created": None})
    with db_connect() as conn:
        row = conn.execute(
            "SELECT created FROM session_tokens WHERE token = ?", (session_id,)
        ).fetchone()
    # get_session_id() already rejects revoked tokens; this row-absent check
    # guards the narrow TOCTOU window between that validation and this query.
    if not row:
        return jsonify({"token": None, "created": None})
    return jsonify({"token": session_id, "created": row["created"]})


@session_bp.route("/session/token/revoke", methods=["POST"])
def session_token_revoke():
    """Permanently delete a session token from the server.

    Accepts ``{"token": "tok_..."}`` in the request body.  The token must carry a
    ``tok_`` prefix and must exist in ``session_tokens``; any other value returns a
    4xx error.  On success the token is deleted and can no longer be used as a
    named session identity.  Associated run history, snapshots, starred commands,
    and saved session preferences remain in the database under the now-orphaned
    session ID; they are not deleted and are not migrated.

    Possession of the token value is the only authorization check — there is no
    higher-level ownership model.  If the caller is revoking their own current
    active token (``X-Session-ID == token``) the client is responsible for
    switching to an anonymous session after this call succeeds.
    """
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    current_session_id = get_session_id()
    if not token:
        log.warning("SESSION_TOKEN_REVOKE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "missing_token",
        })
        return jsonify({"error": "token is required"}), 400
    if not token.startswith("tok_"):
        log.warning("SESSION_TOKEN_REVOKE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "not_tok_token",
        })
        return jsonify({"error": "only tok_ tokens can be revoked"}), 400
    with db_connect() as conn:
        result = conn.execute(
            "DELETE FROM session_tokens WHERE token = ?", (token,)
        )
        conn.commit()
    if result.rowcount == 0:
        log.warning("SESSION_TOKEN_REVOKE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "not_found",
        })
        return jsonify({"error": "token not found"}), 404
    log.info("SESSION_TOKEN_REVOKED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(current_session_id),
        "session_kind": _session_kind(current_session_id),
        "revoked_current": token == current_session_id,
    })
    return jsonify({"ok": True})


@session_bp.route("/session/token/verify", methods=["POST"])
def session_token_verify():
    """Check whether a tok_ session token was issued by this server.

    UUID-format tokens are anonymous sessions never stored in ``session_tokens``
    and are treated as always-valid.  Only ``tok_`` prefixed tokens are checked
    against the table.

    Returns ``{"ok": true, "exists": true/false}``.
    """
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token is required"}), 400
    if not token.startswith("tok_"):
        if not is_valid_anonymous_session_id(token):
            return jsonify({"error": "invalid anonymous session id"}), 400
        # Anonymous UUID sessions — no server-side issuance record needed.
        return jsonify({"ok": True, "exists": True})
    with db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_tokens WHERE token = ?", (token,)
        ).fetchone()
    return jsonify({"ok": True, "exists": row is not None})


def _requested_recent_value_kinds():
    raw_kinds = []
    for value in request.args.getlist("kind"):
        raw_kinds.extend(str(value or "").split(","))
    if not raw_kinds:
        return list(_RECENT_VALUE_KINDS), ""
    kinds = []
    for raw_kind in raw_kinds:
        kind = raw_kind.strip().lower()
        if not kind:
            continue
        if kind not in _RECENT_VALUE_KINDS:
            return [], f"unsupported recent value kind: {kind}"
        if kind not in kinds:
            kinds.append(kind)
    return kinds or list(_RECENT_VALUE_KINDS), ""


@session_bp.route("/session/recent-values")
def session_recent_values_list():
    """Return recently used typed values for autocomplete in this session."""
    kinds, error = _requested_recent_value_kinds()
    if error:
        return jsonify({"error": error}), 400
    session_id = get_session_id()
    with db_connect() as conn:
        values = _list_recent_values(conn, session_id, kinds)
    return jsonify({"values": values})


@session_bp.route("/session/recent-values", methods=["POST"])
def session_recent_values_save():
    """Persist recently used typed values for autocomplete in this session."""
    data = request.get_json(silent=True) or {}
    raw_values = data.get("values")
    if not isinstance(raw_values, list):
        return jsonify({"error": "values must be a list"}), 400
    session_id = get_session_id()
    with db_connect() as conn:
        saved = _upsert_recent_values(conn, session_id, raw_values)
        values = _list_recent_values(conn, session_id)
        conn.commit()
    total_count = sum(len(items) for items in values.values())
    log.debug("SESSION_RECENT_VALUES_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "saved": saved,
        "count": total_count,
    })
    return jsonify({"ok": True, "values": values, "saved": saved})


@session_bp.route("/session/migrate", methods=["POST"])
def session_migrate():
    """Migrate all runs and snapshots from one session ID to another.

    Security: ``from_session_id`` in the request body must match the caller's
    ``X-Session-ID`` header.  This prevents a client from migrating a session
    it does not own.  ``to_session_id`` must be a server-issued token when it
    carries a ``tok_`` prefix — migrating to an unissued token is rejected so a
    typo cannot silently strand run history on an unreachable identity.
    """
    data = request.get_json(silent=True) or {}
    from_session_id = str(data.get("from_session_id") or "").strip()
    to_session_id = str(data.get("to_session_id") or "").strip()

    if not from_session_id or not to_session_id:
        return jsonify({"error": "from_session_id and to_session_id are required"}), 400

    if from_session_id == to_session_id:
        return jsonify({"error": "from_session_id and to_session_id must be different"}), 400

    current_session_id = get_session_id()
    if from_session_id != current_session_id:
        log.warning("SESSION_MIGRATE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": "from_session_id does not match X-Session-ID",
            "from_session_kind": _session_kind(from_session_id),
            "to_session_kind": _session_kind(to_session_id),
        })
        return jsonify({"error": "from_session_id must match your current session"}), 403

    # Reject migration to a tok_ token that was never issued by this server.
    if to_session_id.startswith("tok_"):
        with db_connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM session_tokens WHERE token = ?", (to_session_id,)
            ).fetchone()
        if not row:
            log.warning("SESSION_MIGRATE_DENIED", extra={
                "ip": get_client_ip(),
                "session": get_log_session_id(current_session_id),
                "reason": "unknown_destination_token",
                "from_session_kind": _session_kind(from_session_id),
                "to_session_kind": _session_kind(to_session_id),
            })
            return jsonify({"error": "destination token is not a known issued token"}), 400

    try:
        workspace_migration = migrate_session_workspace(from_session_id, to_session_id)
    except InvalidWorkspacePath as exc:
        log.warning("SESSION_MIGRATE_WORKSPACE_DENIED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(current_session_id),
            "reason": str(exc),
            "from_session_kind": _session_kind(from_session_id),
            "to_session_kind": _session_kind(to_session_id),
        })
        return jsonify({"error": str(exc)}), 400

    with db_connect() as conn:
        runs_result = conn.execute(
            "UPDATE runs SET session_id = ? WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        snaps_result = conn.execute(
            "UPDATE snapshots SET session_id = ? WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        dialect = dialect_for_backend(DB_BACKEND)
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
            migrated_workspace_file_paths=getattr(workspace_migration, "migrated_file_paths", ()),
        )
        migrated_secrets = migrate_session_secrets(conn, from_session_id, to_session_id)
        notification_migration = migrate_notification_channels_session(conn, from_session_id, to_session_id)
        migrated_recent_values = _migrate_recent_values(conn, from_session_id, to_session_id)
        conn.execute(
            "DELETE FROM starred_commands WHERE session_id = ?",
            (from_session_id,),
        )
        conn.execute(
            "DELETE FROM session_preferences WHERE session_id = ?",
            (from_session_id,),
        )
        conn.execute(
            "DELETE FROM session_variables WHERE session_id = ?",
            (from_session_id,),
        )
        conn.execute(
            "DELETE FROM user_workflows WHERE session_id = ?",
            (from_session_id,),
        )
        conn.commit()

    migrated_runs = runs_result.rowcount
    migrated_snapshots = snaps_result.rowcount
        # Use the INSERT rowcount, not the DELETE rowcount — duplicate rows are ignored.
    # counts rows actually written; DELETE counts all source rows including any
    # that were skipped because the destination already had the same command.
    migrated_stars = stars_insert.rowcount
    migrated_preferences = prefs_insert.rowcount
    migrated_variables = vars_insert.rowcount
    migrated_workflows = workflows_result.rowcount

    log.info("SESSION_MIGRATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(current_session_id),
        "from_session_kind": _session_kind(from_session_id),
        "to_session_kind": _session_kind(to_session_id),
        "migrated_runs": migrated_runs,
        "migrated_snapshots": migrated_snapshots,
        "migrated_stars": migrated_stars,
        "migrated_preferences": migrated_preferences,
        "migrated_variables": migrated_variables,
        "migrated_workflows": migrated_workflows,
        **project_migration,
        **notification_migration,
        "migrated_recent_values": migrated_recent_values,
        "migrated_secrets": migrated_secrets,
        "migrated_workspace_files": workspace_migration.migrated_files,
        "skipped_workspace_files": workspace_migration.skipped_files,
        "migrated_workspace_directories": workspace_migration.migrated_directories,
        "skipped_workspace_directories": workspace_migration.skipped_directories,
    })
    return jsonify({
        "ok": True,
        "migrated_runs": migrated_runs,
        "migrated_snapshots": migrated_snapshots,
        "migrated_stars": migrated_stars,
        "migrated_preferences": migrated_preferences,
        "migrated_variables": migrated_variables,
        "migrated_workflows": migrated_workflows,
        **project_migration,
        **notification_migration,
        "migrated_recent_values": migrated_recent_values,
        "migrated_secrets": migrated_secrets,
        "migrated_workspace_files": workspace_migration.migrated_files,
        "skipped_workspace_files": workspace_migration.skipped_files,
        "migrated_workspace_directories": workspace_migration.migrated_directories,
        "skipped_workspace_directories": workspace_migration.skipped_directories,
    })


@session_bp.route("/session/preferences")
def session_preferences_get():
    """Return the saved preference snapshot for the current session."""
    session_id = get_session_id()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT preferences, updated FROM session_preferences WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return jsonify({"preferences": {}, "updated": None})
    prefs = _normalize_session_preferences(_decode_preferences(row["preferences"], session_id=session_id))
    return jsonify({"preferences": prefs, "updated": row["updated"]})


@session_bp.route("/session/preferences", methods=["POST"])
def session_preferences_save():
    """Persist the current session's full preference snapshot."""
    raw_data = request.get_json(silent=True)
    data: dict[str, object] = dict(raw_data) if isinstance(raw_data, dict) else {}
    raw_preferences_value = data.get("preferences")
    raw_preferences: dict[str, object] = (
        dict(raw_preferences_value) if isinstance(raw_preferences_value, dict) else {}
    )
    prefs = _normalize_session_preferences(raw_preferences)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    session_id = get_session_id()
    with db_connect() as conn:
        if "pref_atlas_saved_views" not in raw_preferences:
            existing_views = _load_session_preferences(conn, session_id).get("pref_atlas_saved_views")
            if existing_views:
                prefs["pref_atlas_saved_views"] = existing_views
        _save_session_preferences(conn, session_id, prefs, updated)
        conn.commit()
    log.info("SESSION_PREFERENCES_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "key_count": len(prefs),
    })
    return jsonify({"ok": True, "preferences": prefs, "updated": updated})


@session_bp.route("/session/tour-seen", methods=["POST"])
def session_tour_seen():
    """Record that the current session opened the current tour version."""
    tour_version = _current_tour_version()
    if tour_version < 1:
        return jsonify({"error": "tour is not available"}), 404
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    session_id = get_session_id()
    with db_connect() as conn:
        prefs = _load_session_preferences(conn, session_id)
        prefs["pref_tour_seen_version"] = tour_version
        _save_session_preferences(conn, session_id, prefs, updated)
        conn.commit()
    log.info("SESSION_TOUR_SEEN", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "tour_version": tour_version,
    })
    return jsonify({
        "ok": True,
        "tour_version": tour_version,
        "preferences": prefs,
        "updated": updated,
    })


@session_bp.route("/session/variables")
def session_variables_list():
    """Return command-variable names and values for the current session."""
    session_id = get_session_id()
    variables = list_session_variables(session_id)
    log.debug("SESSION_VARIABLES_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": len(variables),
    })
    return jsonify({
        "variables": [
            {"name": name, "value": value}
            for name, value in variables.items()
        ],
    })


@session_bp.route("/session/workflows")
def session_workflows_list():
    """Return user-created workflows for the current session."""
    session_id = get_session_id()
    workflows = list_user_workflows(session_id)
    log.debug("USER_WORKFLOWS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": len(workflows),
    })
    return jsonify({"items": workflows})


@session_bp.route("/session/workflows", methods=["POST"])
def session_workflows_create():
    """Create a user workflow for the current session."""
    session_id = get_session_id()
    try:
        workflow = create_user_workflow(session_id, request.get_json(silent=True) or {})
    except UserWorkflowError as exc:
        return jsonify({"error": str(exc)}), 400
    log.info("USER_WORKFLOW_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "workflow_id": workflow["id"] if workflow else "",
    })
    return jsonify({"ok": True, "workflow": workflow}), 201


@session_bp.route("/session/workflows/<workflow_id>", methods=["GET"])
def session_workflows_get(workflow_id):
    """Return one user workflow for the current session."""
    session_id = get_session_id()
    workflow = get_user_workflow(session_id, workflow_id)
    if not workflow:
        return jsonify({"error": "workflow not found"}), 404
    return jsonify({"workflow": workflow})


@session_bp.route("/session/workflows/<workflow_id>", methods=["PUT"])
def session_workflows_update(workflow_id):
    """Update a user workflow for the current session."""
    session_id = get_session_id()
    try:
        workflow = update_user_workflow(session_id, workflow_id, request.get_json(silent=True) or {})
    except UserWorkflowError as exc:
        return jsonify({"error": str(exc)}), 400
    if not workflow:
        return jsonify({"error": "workflow not found"}), 404
    log.info("USER_WORKFLOW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "workflow_id": workflow_id,
    })
    return jsonify({"ok": True, "workflow": workflow})


@session_bp.route("/session/workflows/<workflow_id>", methods=["DELETE"])
def session_workflows_delete(workflow_id):
    """Delete a user workflow for the current session."""
    session_id = get_session_id()
    if not delete_user_workflow(session_id, workflow_id):
        return jsonify({"error": "workflow not found"}), 404
    log.info("USER_WORKFLOW_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "workflow_id": workflow_id,
    })
    return jsonify({"ok": True})


@session_bp.route("/session/run-count")
def session_run_count():
    """Return the total run count for the current session, uncapped.

    The pre-migration confirmation prompt needs the true row count so the user
    is not shown the `history_panel_limit` cap that `/history` applies to its
    page of runs. The actual migration UPDATE on `/session/migrate` is already
    uncapped; this endpoint just keeps the confirmation honest.
    """
    session_id = get_session_id()
    with db_connect() as conn:
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
    count = int(row["n"] if row else 0)
    workflow_count = int(workflow_row["n"] if workflow_row else 0)
    recent_value_count = int(recent_value_row["n"] if recent_value_row else 0)
    workspace_files = 0
    try:
        workspace_files = workspace_usage(session_id).file_count
    except Exception as exc:
        log.warning("SESSION_ROUTE_FAILED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "route": "session_run_count",
            "error": str(exc),
        })
        workspace_files = 0
    log.debug("SESSION_RUN_COUNT_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": count,
        "workspace_files": workspace_files,
        "workflow_count": workflow_count,
        "recent_value_count": recent_value_count,
    })
    return jsonify({
        "count": count,
        "workspace_files": workspace_files,
        "workflow_count": workflow_count,
        "recent_value_count": recent_value_count,
    })


@session_bp.route("/session/starred")
def session_starred_list():
    """Return the starred command list for the current session."""
    session_id = get_session_id()
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT command FROM starred_commands WHERE session_id = ? ORDER BY command",
            (session_id,),
        ).fetchall()
    log.debug("STARRED_COMMANDS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": len(rows),
    })
    return jsonify({"commands": [row["command"] for row in rows]})


@session_bp.route("/session/starred", methods=["POST"])
def session_starred_add():
    """Add a command to the starred list for the current session."""
    data = request.get_json(silent=True) or {}
    command = str(data.get("command") or "").strip()
    if not command:
        return jsonify({"error": "command is required"}), 400
    session_id = get_session_id()
    with db_connect() as conn:
        result = conn.execute(
            "INSERT INTO starred_commands (session_id, command) VALUES (?, ?) "
            "ON CONFLICT(session_id, command) DO NOTHING",
            (session_id, command),
        )
        conn.commit()
    log.info("STARRED_COMMAND_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "command_root": _command_root(command),
        "changed": bool(result.rowcount),
    })
    return jsonify({"ok": True})


@session_bp.route("/session/starred", methods=["DELETE"])
def session_starred_remove():
    """Remove one command (body: {"command": "..."}) or all commands (no body) from the starred list."""
    data = request.get_json(silent=True) or {}
    command = str(data.get("command") or "").strip()
    session_id = get_session_id()
    with db_connect() as conn:
        if command:
            result = conn.execute(
                "DELETE FROM starred_commands WHERE session_id = ? AND command = ?",
                (session_id, command),
            )
            event = "STARRED_COMMAND_REMOVED"
        else:
            result = conn.execute(
                "DELETE FROM starred_commands WHERE session_id = ?",
                (session_id,),
            )
            event = "STARRED_COMMANDS_CLEARED"
        conn.commit()
    extra = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": result.rowcount,
    }
    if command:
        extra["command_root"] = _command_root(command)
    log.info(event, extra=extra)
    return jsonify({"ok": True})
