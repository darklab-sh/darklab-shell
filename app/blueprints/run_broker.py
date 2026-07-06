"""Brokered run HTTP routes for the run blueprint."""

from __future__ import annotations

from flask import Response, jsonify, request

from blueprints import run as run_routes


@run_routes.run_bp.route("/runs", methods=["POST"])
@run_routes.limiter.limit(lambda: (
    f"{run_routes.CFG['rate_limit_per_minute']} per minute; "
    f"{run_routes.CFG['rate_limit_per_second']} per second"
))
def start_brokered_run():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    session_id = run_routes.get_session_id()
    original_command = data.get("command", "")
    client_ip = run_routes.get_client_ip()
    owner_client_id = run_routes._active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = run_routes._active_run_owner_value(data.get("tab_id", ""))
    workspace_cwd = run_routes._workspace_cwd_value(data.get("workspace_cwd", ""))
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400
    team_id = ""
    team_role = ""
    if run_routes.requested_team_id(request):
        try:
            owner_scope = run_routes.current_request_scope(session_id, request)
        except run_routes.RequestScopeError as exc:
            payload, status = run_routes.scope_error_payload(exc)
            return jsonify(payload), status
        capability_response = run_routes._require_team_capability(owner_scope, run_routes.Capability.RUN_COMMANDS)
        if capability_response:
            return capability_response
        team_id = owner_scope.team_id
        team_role = str((owner_scope.member or {}).get("role") or "")

    if not run_routes.broker_available():
        reason = run_routes.broker_unavailable_reason()
        log_method = (
            run_routes.log.info
            if reason == "Run broker is disabled by configuration."
            else run_routes.log.warning
        )
        log_method("RUN_BROKER_UNAVAILABLE", extra={
            "session": run_routes.get_log_session_id(session_id),
            "ip": client_ip,
            "reason": reason,
            "broker_mode": run_routes.broker_mode(),
            "team_requested": bool(team_id or run_routes.requested_team_id(request)),
            "command_root": run_routes.command_root(original_command) or "",
        })
        return jsonify({"error": reason}), 503

    try:
        started = run_routes._start_brokered_run_service(
            original_command=original_command,
            session_id=session_id,
            team_id=team_id,
            team_role=team_role,
            client_ip=client_ip,
            handlers=run_routes._run_start_handlers(),
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
            workspace_cwd=workspace_cwd,
            thread_name_prefix="run-broker",
        )
    except run_routes._RunPreparationError as exc:
        return run_routes._preparation_error_response(exc)
    except run_routes._RunSpawnError as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"run_id": started.run_id, "stream": f"/runs/{started.run_id}/stream"}), 202


@run_routes.run_bp.route("/runs/<run_id>/events")
def get_brokered_run_events(run_id):
    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    visibility = run_routes._run_session_visibility(run_id, session_id, owner_scope.team_id)
    if not visibility["allowed"]:
        return run_routes._run_visibility_error_response(visibility)
    after_id = str(request.args.get("after", "0-0") or "0-0")
    try:
        limit = max(1, min(int(request.args.get("limit", 100) or 100), 500))
    except (TypeError, ValueError):
        limit = 100
    events = run_routes.get_run_events(run_id, after_id=after_id, limit=limit)
    return jsonify({
        "run_id": run_id,
        "events": [event.as_payload() for event in events],
    })


@run_routes.run_bp.route("/runs/<run_id>/stream")
def stream_brokered_run(run_id):
    session_id = run_routes.get_session_id()
    try:
        owner_scope = run_routes.current_request_scope(session_id, request)
    except run_routes.RequestScopeError as exc:
        payload, status = run_routes.scope_error_payload(exc)
        return jsonify(payload), status
    visibility = run_routes._run_session_visibility(run_id, session_id, owner_scope.team_id)
    if not visibility["allowed"]:
        run_routes.log.warning("RUN_BROKER_STREAM_MISS", extra={
            "run_id": run_id,
            "session": run_routes.get_log_session_id(session_id),
            "ip": run_routes.get_client_ip(),
            "broker_mode": run_routes.broker_mode(),
            "active_match": bool(visibility["active_match"]),
            "db_match": bool(visibility["db_match"]),
            "active_count": int(visibility["active_count"]),
            "after_id": str(request.args.get("after", "0-0") or "0-0"),
            "owner_client_id_present": bool(run_routes._active_run_owner_value(request.headers.get("X-Client-ID", ""))),
            "owner_tab_id_present": bool(run_routes._active_run_owner_value(request.args.get("tab_id", ""))),
            "scope_mismatch": bool(visibility.get("scope_mismatch")),
            "actual_team_id": str(visibility.get("actual_team_id", "") or ""),
        })
        return run_routes._run_visibility_error_response(visibility)
    after_id = str(request.args.get("after", "0-0") or "0-0")
    owner_client_id = run_routes._active_run_owner_value(request.headers.get("X-Client-ID", ""))
    owner_tab_id = run_routes._active_run_owner_value(request.args.get("tab_id", ""))

    def generate():
        last_touch_monotonic = None
        for item in run_routes.stream_run_events(run_id, after_id=after_id):
            if owner_client_id:
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
