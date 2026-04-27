"""
Session token routes: session token generation and session history migration.
"""

import json
import logging
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from database import db_connect
from helpers import get_client_ip, get_log_session_id, get_session_id
from workspace import InvalidWorkspacePath, migrate_session_workspace, workspace_usage

log = logging.getLogger("shell")

session_bp = Blueprint("session", __name__)

_SESSION_PREFERENCE_KEYS = {
    "pref_theme_name",
    "pref_timestamps",
    "pref_line_numbers",
    "pref_welcome_intro",
    "pref_share_redaction_default",
    "pref_run_notify",
    "pref_hud_clock",
}


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
        if not isinstance(value, str):
            value = str(value or "")
        value = value.strip()
        if not value:
            continue
        prefs[key] = value
    return prefs


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
            "INSERT OR IGNORE INTO session_tokens (token, created) VALUES (?, ?)",
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
        # Anonymous UUID sessions — no server-side issuance record needed.
        return jsonify({"ok": True, "exists": True})
    with db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_tokens WHERE token = ?", (token,)
        ).fetchone()
    return jsonify({"ok": True, "exists": row is not None})


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
        stars_insert = conn.execute(
            "INSERT OR IGNORE INTO starred_commands (session_id, command) "
            "SELECT ?, command FROM starred_commands WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        prefs_insert = conn.execute(
            "INSERT OR IGNORE INTO session_preferences (session_id, preferences, updated) "
            "SELECT ?, preferences, updated FROM session_preferences WHERE session_id = ?",
            (to_session_id, from_session_id),
        )
        conn.execute(
            "DELETE FROM starred_commands WHERE session_id = ?",
            (from_session_id,),
        )
        conn.execute(
            "DELETE FROM session_preferences WHERE session_id = ?",
            (from_session_id,),
        )
        conn.commit()

    migrated_runs = runs_result.rowcount
    migrated_snapshots = snaps_result.rowcount
    # Use the INSERT rowcount, not the DELETE rowcount — INSERT OR IGNORE only
    # counts rows actually written; DELETE counts all source rows including any
    # that were skipped because the destination already had the same command.
    migrated_stars = stars_insert.rowcount
    migrated_preferences = prefs_insert.rowcount

    log.info("SESSION_MIGRATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(current_session_id),
        "from_session_kind": _session_kind(from_session_id),
        "to_session_kind": _session_kind(to_session_id),
        "migrated_runs": migrated_runs,
        "migrated_snapshots": migrated_snapshots,
        "migrated_stars": migrated_stars,
        "migrated_preferences": migrated_preferences,
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
    try:
        prefs = _normalize_session_preferences(json.loads(row["preferences"] or "{}"))
    except json.JSONDecodeError:
        log.warning("SESSION_PREFERENCES_INVALID", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "session_kind": _session_kind(session_id),
        })
        prefs = {}
    return jsonify({"preferences": prefs, "updated": row["updated"]})


@session_bp.route("/session/preferences", methods=["POST"])
def session_preferences_save():
    """Persist the current session's full preference snapshot."""
    data = request.get_json(silent=True) or {}
    prefs = _normalize_session_preferences(data.get("preferences"))
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    session_id = get_session_id()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET preferences = excluded.preferences, updated = excluded.updated",
            (session_id, json.dumps(prefs, sort_keys=True), updated),
        )
        conn.commit()
    log.info("SESSION_PREFERENCES_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "key_count": len(prefs),
    })
    return jsonify({"ok": True, "preferences": prefs, "updated": updated})


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
    count = int(row["n"] if row else 0)
    workspace_files = 0
    try:
        workspace_files = workspace_usage(session_id).file_count
    except Exception:
        workspace_files = 0
    log.debug("SESSION_RUN_COUNT_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "session_kind": _session_kind(session_id),
        "count": count,
        "workspace_files": workspace_files,
    })
    return jsonify({"count": count, "workspace_files": workspace_files})


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
            "INSERT OR IGNORE INTO starred_commands (session_id, command) VALUES (?, ?)",
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
