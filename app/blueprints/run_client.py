"""Client-owned run persistence route for the run blueprint."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import run as run_routes


@run_routes.run_bp.route("/run/client", methods=["POST"])
def save_client_side_run():
    """Persist browser-owned built-in command output as a normal history run."""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    command = data.get("command", "")
    if not isinstance(command, str):
        return jsonify({"error": "Command must be a string"}), 400
    command = command.strip()
    if not command:
        return jsonify({"error": "No command provided"}), 400
    if not run_routes._client_side_run_command_allowed(command):
        return jsonify({"error": "Client-side run persistence is limited to browser-owned built-ins"}), 403

    try:
        exit_code = int(data.get("exit_code", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "exit_code must be an integer"}), 400

    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = run_routes._require_team_capability(owner_scope, run_routes.Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    client_ip = run_routes.get_client_ip()
    raw_lines = data.get("lines", [])
    if not isinstance(raw_lines, list):
        run_routes.log.warning("CLIENT_RUN_OUTPUT_INVALID", extra={
            "session": run_routes.get_log_session_id(session_id),
            "ip": client_ip,
            "cmd": command,
            "payload_type": type(raw_lines).__name__,
        })
    active_cfg = run_routes.resolve_effective_cfg()
    lines, preview_truncated, output_line_count = run_routes._normalize_client_side_run_lines(raw_lines, command)
    if isinstance(raw_lines, list) and preview_truncated:
        run_routes.log.warning("CLIENT_RUN_OUTPUT_TRUNCATED", extra={
            "session": run_routes.get_log_session_id(session_id),
            "ip": client_ip,
            "cmd": command,
            "raw_line_count": len(raw_lines),
            "stored_line_count": len(lines),
            "limit": active_cfg["max_output_lines"],
        })
    run_id = str(run_routes.uuid.uuid4())
    started = datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    output_search_text = run_routes._extract_output_search_text(lines)
    stored_output_search_text = run_routes.maybe_store_text_body(
        "run_search",
        run_id,
        output_search_text,
        run_routes.inline_threshold_bytes(active_cfg.get("runs_search_text_inline_max_bytes")),
    )

    run_routes.log.info("RUN_START", extra={
        "run_id": run_id, "session": run_routes.get_log_session_id(session_id), "ip": client_ip,
        "pid": 0, "cmd": command, "cmd_type": "client-builtin",
    })
    run_routes.app_metrics.record_run_started(command, run_routes.RUN_KIND_BUILTIN, active=False)
    run_routes.app_metrics.record_completed_run_values(
        command,
        run_routes.RUN_KIND_BUILTIN,
        exit_code,
        0.0,
        output_bytes=sum(len(str(line.get("text", ""))) for line in lines),
        truncated=bool(preview_truncated),
    )

    def _persist_client_run(conn):
        run_routes.insert_run_row(
            conn,
            run_id=run_id,
            session_id=session_id,
            team_id=owner_scope.team_id,
            run_kind=run_routes.RUN_KIND_BUILTIN,
            owner_tab_id=run_routes._active_run_owner_value(data.get("tab_id", "")),
            command=command,
            started=started.isoformat(),
            finished=finished.isoformat(),
            exit_code=exit_code,
            output_preview=json.dumps(lines),
            preview_truncated=int(preview_truncated),
            output_line_count=output_line_count,
            full_output_available=False,
            full_output_truncated=False,
            output_search_text=stored_output_search_text,
        )
        run_routes.replace_run_output_summary(conn, run_id, lines)
        recorded_entities: list = []
        scan_observation_count = 0
        try:
            recorded_entities = run_routes.run_finalize_savepoint(
                conn,
                "atlas_entities",
                lambda: run_routes.materialize_run_entities(
                    conn,
                    session_id,
                    run_id,
                    lines,
                    team_id=owner_scope.team_id,
                    seen_at=finished.isoformat(),
                    command=command,
                ),
            )
            scan_observation_count = run_routes.scan_target_observation_count(conn, run_id)
        except Exception:
            run_routes.app_metrics.record_run_finalize_error("entity_materialize")
            run_routes.log.error("ATLAS_ENTITY_CAPTURE_ERROR", exc_info=True, extra={
                "run_id": run_id,
                "session": run_routes.get_log_session_id(session_id),
                "cmd": command,
            })
        run_routes._log_atlas_entities_captured(
            session_id,
            owner_scope.team_id,
            run_id,
            recorded_entities,
            scan_observation_count,
        )
        return recorded_entities, scan_observation_count

    run_routes.run_persistence_transaction(_persist_client_run)

    elapsed = round((finished - started).total_seconds(), 1)
    run_routes.log.info("RUN_END", extra={
        "run_id": run_id, "session": run_routes.get_log_session_id(session_id), "ip": client_ip,
        "exit_code": exit_code, "elapsed": elapsed, "cmd": command,
        "cmd_type": "client-builtin",
        "output_line_count": output_line_count,
        "full_output_truncated": False,
        "full_output_available": False,
        "artifact_count": 0,
    })
    return jsonify({"ok": True, "run_id": run_id, "output_line_count": output_line_count})
