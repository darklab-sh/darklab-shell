"""Interactive PTY route group for the run blueprint."""

from __future__ import annotations

from flask import Response, jsonify, request

from blueprints import run as run_routes
from services.teams.capabilities import Capability


@run_routes.run_bp.route("/pty/runs", methods=["POST"])
@run_routes.limiter.limit(lambda: (
    f"{run_routes.CFG['rate_limit_per_minute']} per minute; "
    f"{run_routes.CFG['rate_limit_per_second']} per second"
))
def start_interactive_pty_run():
    if not run_routes.pty_enabled():
        return jsonify({"error": "Interactive PTY mode is disabled on this instance"}), 403
    if not run_routes.pty_broker_available():
        return jsonify({"error": run_routes.pty_broker_unavailable_reason()}), 503

    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    original_command = data.get("command", "")
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400

    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = run_routes._require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    client_ip = run_routes.get_client_ip()
    workspace_cwd = run_routes._workspace_cwd_value(data.get("workspace_cwd", ""))
    try:
        argv, execution_command, pty_spec = run_routes._prepare_interactive_pty_command(
            original_command,
            session_id,
            client_ip,
            workspace_cwd,
            owner_context=owner_scope.context,
        )
    except run_routes._RunPreparationError as exc:
        return run_routes._preparation_error_response(exc)

    pty_limit = run_routes._interactive_pty_concurrency_limit()
    active_pty_count = run_routes._active_interactive_pty_count(session_id)
    if active_pty_count >= pty_limit:
        run_routes.app_metrics.record_rate_limit_rejection(
            request.endpoint or "start_interactive_pty_run",
            scope="pty_input",
        )
        return jsonify({
            "error": (
                "Interactive PTY limit reached for this session "
                f"({active_pty_count}/{pty_limit} active). Close or kill an active PTY before starting another."
            ),
        }), 429

    try:
        run = run_routes.start_pty_run(
            session_id=session_id,
            team_id=owner_scope.team_id,
            client_ip=client_ip,
            command=original_command,
            argv=argv,
            rows=data.get("rows"),
            cols=data.get("cols"),
            default_rows=pty_spec.get("default_rows"),
            default_cols=pty_spec.get("default_cols"),
            owner_client_id=run_routes._active_run_owner_value(request.headers.get("X-Client-ID", "")),
            owner_tab_id=run_routes._active_run_owner_value(data.get("tab_id", "")),
            allow_input=(
                bool(pty_spec.get("allow_input", True))
                and str(pty_spec.get("input_safety") or "") != "no_input"
            ),
            max_runtime_seconds=run_routes._coerce_positive_int(
                pty_spec.get("max_runtime_seconds"),
                run_routes._coerce_positive_int(
                    run_routes.CFG.get("interactive_pty_max_runtime_seconds", 900),
                    900,
                ),
            ),
            completion_callback=lambda completed_run, finished_iso, exit_code, synthesized_lines: (
                run_routes._persist_completed_pty_run(
                    completed_run,
                    execution_command,
                    finished_iso,
                    exit_code,
                    synthesized_lines,
                    transcript_mode=pty_spec.get("transcript_mode"),
                )
            ),
        )
    except run_routes.PtyDependencyError as exc:
        run_routes.log.error("PTY_DEPENDENCY_ERROR", extra={
            "ip": client_ip, "session": run_routes.get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        run_routes.log.error("PTY_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": run_routes.get_log_session_id(session_id), "cmd": original_command,
        })
        return jsonify({"error": str(exc)}), 500
    return jsonify({
        "run_id": run.run_id,
        "stream": f"/pty/runs/{run.run_id}/stream",
        "command": execution_command,
        "interactive": True,
        "rows": run.rows,
        "cols": run.cols,
    }), 202


@run_routes.run_bp.route("/pty/runs/<run_id>/stream")
def stream_interactive_pty_run(run_id):
    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    belongs_to_run = (
        run_routes.pty_run_belongs_to_scope(run_id, session_id, owner_scope.team_id)
        if owner_scope.is_team
        else run_routes.pty_run_belongs_to_session(run_id, session_id)
    )
    if not belongs_to_run:
        return jsonify({"error": "Run not found"}), 404
    after_id = request.args.get("after", "0-0") or "0-0"
    owner_client_id = run_routes._active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = run_routes._active_run_owner_value(request.args.get("tab_id", ""))
    can_control = run_routes._scope_has_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if owner_client_id and can_control:
        if owner_scope.is_team:
            run_routes.claim_pty_stream_owner(
                run_id,
                session_id,
                owner_client_id,
                owner_tab_id,
                team_id=owner_scope.team_id,
            )
        else:
            run_routes.claim_pty_stream_owner(run_id, session_id, owner_client_id, owner_tab_id)

    def generate():
        last_touch_monotonic = None
        for item in run_routes.stream_pty_events(run_id, session_id, after=after_id, team_id=owner_scope.team_id):
            if owner_client_id and can_control:
                last_touch_monotonic = run_routes._maybe_touch_active_run_owner(
                    run_id,
                    owner_client_id,
                    owner_tab_id,
                    last_touch_monotonic=last_touch_monotonic,
                )
            yield item

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


def _pty_snapshot_error_response(message: str):
    text = message or "PTY snapshot is not available"
    headers = {}
    if text == "Run not found":
        status = 404
    elif text in {"Run is closed", "PTY run is no longer active"}:
        status = 410
    elif "snapshot is not available" in text:
        status = 503
        headers["Retry-After"] = "1"
    else:
        status = 409
    return jsonify({"error": text}), status, headers


@run_routes.run_bp.route("/pty/runs/<run_id>/snapshot")
def snapshot_interactive_pty_run(run_id):
    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    if owner_scope.is_team:
        ok, message, snapshot = run_routes.pty_run_snapshot(run_id, session_id, team_id=owner_scope.team_id)
    else:
        ok, message, snapshot = run_routes.pty_run_snapshot(run_id, session_id)
    if not ok:
        return _pty_snapshot_error_response(message)
    return jsonify(snapshot)


@run_routes.run_bp.route("/pty/runs/<run_id>/input", methods=["POST"])
@run_routes.limiter.limit(run_routes._interactive_pty_input_limit)
def send_interactive_pty_input(run_id):
    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = run_routes._require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    ok, message = run_routes.write_pty_input(
        run_id,
        session_id,
        data.get("data", ""),
        run_routes._active_run_owner_value(request.headers.get("X-Client-ID", "")),
        run_routes._active_run_owner_value(data.get("tab_id", "")),
        team_id=owner_scope.team_id,
    )
    if not ok:
        status = 404 if message == "Run not found" else 409 if "no longer active" in message else 400
        return jsonify({"error": message or "Input rejected"}), status
    return jsonify({"ok": True})


@run_routes.run_bp.route("/pty/runs/<run_id>/resize", methods=["POST"])
@run_routes.limiter.limit(run_routes._interactive_pty_resize_limit)
def resize_interactive_pty_run(run_id):
    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    capability_response = run_routes._require_team_capability(owner_scope, Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    ok, message, rows, cols = run_routes.resize_pty(
        run_id,
        session_id,
        data.get("rows"),
        data.get("cols"),
        team_id=owner_scope.team_id,
    )
    if not ok:
        status = 404 if message == "Run not found" else 409 if "no longer active" in message else 400
        return jsonify({"error": message or "Resize rejected"}), status
    return jsonify({"ok": True, "rows": rows, "cols": cols})
