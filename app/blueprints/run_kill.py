# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Run kill route for the run blueprint."""

from __future__ import annotations

import subprocess

from flask import jsonify, request

from blueprints import run as run_routes


@run_routes.run_bp.route("/kill", methods=["POST"])
def kill_command():
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    run_id = data.get("run_id", "")
    killer_tab_id = run_routes._active_run_owner_value(data.get("tab_id", ""))
    client_ip = run_routes.get_client_ip()
    if not isinstance(run_id, str):
        return jsonify({"error": "run_id must be a string"}), 400
    session_id = run_routes.get_session_id()
    if session_id or run_routes.requested_team_id(request):
        try:
            owner_scope = run_routes.current_request_scope(session_id, request)
        except run_routes.RequestScopeError as exc:
            payload, status = run_routes.scope_error_payload(exc)
            return jsonify(payload), status
    else:
        owner_scope = run_routes.RequestScope(run_routes.OwnerContext(scope="personal", owner_id="", actor_session_id=""))
    capability_response = run_routes._require_team_capability(owner_scope, run_routes.Capability.RUN_COMMANDS)
    if capability_response:
        return capability_response
    kill_audit = {
        "session": run_routes.get_log_session_id(session_id),
        **run_routes._team_audit_fields(owner_scope),
    }
    killer_client_id = run_routes._active_run_owner_value(request.headers.get("X-Client-ID", ""))
    active_runs = (
        run_routes.active_runs_for_team(owner_scope.team_id)
        if owner_scope.is_team
        else run_routes.active_runs_for_session(session_id, team_id="")
    )
    active_run = next(
        (run for run in active_runs if run.get("run_id") == run_id),
        {},
    )
    run_type = str(active_run.get("run_type", "command") or "command").lower()
    pid = (
        run_routes.pid_for_team(run_id, owner_scope.team_id)
        if owner_scope.is_team
        else run_routes.pid_for_session(run_id, session_id)
    )
    if not pid:
        run_routes.log.debug("KILL_MISS", extra={
            "ip": client_ip,
            "run_id": run_id,
            **kill_audit,
        })
        return jsonify({"error": "No such process"}), 404
    killed_payload = {
        "killer_client_id": killer_client_id,
        "killer_tab_id": killer_tab_id,
    }
    pgid = pid
    try:
        # Subprocesses call os.setsid() during child setup, which makes PGID
        # == PID at creation time. Use the stored PID directly as the
        # PGID rather than calling os.getpgid() -- if the subprocess has
        # already exited and its PID was reused (e.g. by a new Gunicorn
        # worker), os.getpgid() would return the wrong PGID and we would
        # accidentally send SIGTERM to a gunicorn worker process group.
        # Using the original PID as the PGID is safe: if the process group
        # no longer exists the signal fails with ESRCH instead of hitting
        # an unrelated process.
        run_routes._ensure_scanner_process_group_current(
            run_id,
            pgid,
            session_id,
            team_id=owner_scope.team_id if owner_scope.is_team else "",
        )
        run_routes._signal_process_group(pgid)
        if run_type == "pty":
            if owner_scope.is_team:
                run_routes.notify_pty_killed_event(run_id, session_id, killed_payload, team_id=owner_scope.team_id)
            else:
                run_routes.notify_pty_killed_event(run_id, session_id, killed_payload)
        else:
            run_routes.publish_run_event(run_id, "killed", killed_payload)
        run_routes.log.info("RUN_KILL", extra={
            "run_id": run_id,
            "ip": client_ip,
            **kill_audit,
            "pid": pid,
            "pgid": pgid,
        })
    except ProcessLookupError as exc:
        if run_type == "pty":
            if owner_scope.is_team:
                run_routes.notify_pty_killed_event(run_id, session_id, killed_payload, team_id=owner_scope.team_id)
            else:
                run_routes.notify_pty_killed_event(run_id, session_id, killed_payload)
        else:
            run_routes.publish_run_event(run_id, "killed", killed_payload)
        run_routes.log.warning("KILL_FAILED", extra={
            "run_id": run_id,
            "ip": client_ip,
            **kill_audit,
            "pid": pid,
            "pgid": pgid,
            "error": str(exc),
        })
    except (subprocess.TimeoutExpired, OSError) as exc:
        run_routes.log.warning("KILL_FAILED", extra={
            "run_id": run_id,
            "ip": client_ip,
            **kill_audit,
            "pid": pid,
            "pgid": pgid,
            "error": str(exc),
        })
        return jsonify({"error": "Failed to signal process"}), 500
    return jsonify({"killed": True})
