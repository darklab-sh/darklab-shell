# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 run control routes."""

from __future__ import annotations

import subprocess
import time

from flask import Response, jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.ai.assists import AIAssistRouteError, enqueue_next_commands_assist, enqueue_summary_assist, list_run_assists
from services.projects.contracts import ProjectWorkspaceError
from services.projects.links import link_project_entity, unlink_project_entity


@api_routes.api_v1_bp.route("/runs")
@api_routes.require_api_auth
def api_active_runs():
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    runs = [
        api_routes._active_run_summary(active)
        for active in api_routes._active_runs_for_owner(session_id, owner_scope.team_id)
    ]
    return jsonify({"runs": runs, "total": len(runs)})


@api_routes.api_v1_bp.route("/runs", methods=["POST"])
@api_routes.require_api_auth
def api_runs_start():
    parsed_json = request.get_json(silent=True)
    data = parsed_json if parsed_json is not None else {}
    if not isinstance(data, dict):
        return api_routes._api_json_error("invalid_body", "Request body must be a JSON object.", 400)
    original_command = data.get("command", "")
    if not isinstance(original_command, str):
        return api_routes._api_json_error("invalid_command", "Command must be a string.", 400)
    original_command = original_command.strip()
    if not original_command:
        return api_routes._api_json_error("missing_command", "Command is required.", 400)
    interactive_spec = api_routes.interactive_pty_spec_for_command(original_command)
    interactive_trigger = str((interactive_spec or {}).get("trigger_flag") or "").strip()
    if interactive_trigger and interactive_trigger in api_routes.split_command_argv(original_command)[1:]:
        return api_routes._api_json_error(
            "interactive_pty_not_supported",
            "Interactive PTY runs are not supported by API v1.",
            409,
        )

    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    try:
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.RUN_COMMANDS)
        link_project_id = api_routes._requested_project_id(data, session_id, team_id=owner_scope.team_id)
    except api_routes.ApiAuthError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except api_routes.TeamPermissionDenied as exc:
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    if not api_routes.broker_available():
        api_routes.log.warning("API_BROKER_UNAVAILABLE", extra={
            "ip": get_client_ip(),
            "reason": api_routes.broker_unavailable_reason(),
        })
        response, status = api_routes._api_json_error("broker_unavailable", api_routes.broker_unavailable_reason(), 503)
        response.headers["Retry-After"] = "5"
        return response, status
    client_ip = get_client_ip()
    owner_tab_id = ""
    workspace_cwd = api_routes._workspace_cwd_value(data.get("workspace_cwd", ""))
    team_role = str((owner_scope.member or {}).get("role") or "") if owner_scope.is_team else ""

    try:
        started = api_routes._start_brokered_run_service(
            original_command=original_command,
            session_id=session_id,
            team_id=owner_scope.team_id,
            team_role=team_role,
            client_ip=client_ip,
            handlers=api_routes._api_run_start_handlers(),
            owner_tab_id=owner_tab_id,
            workspace_cwd=workspace_cwd,
            link_project_id=link_project_id,
            thread_name_prefix="api-run-broker",
        )
    except api_routes.RunStartRejected as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except api_routes._RunPreparationError as exc:
        return api_routes._api_json_error("command_rejected", str(exc), exc.status_code)
    except api_routes._RunSpawnError as exc:
        return api_routes._api_json_error("spawn_failed", str(exc), 500)
    api_routes.log.info("API_RUN_STARTED", extra={
        "ip": client_ip,
        "session": get_log_session_id(session_id),
        "run_id": started.run_id,
        "cmd": original_command,
        "cmd_type": started.cmd_type,
        "project_id": link_project_id,
    })
    return jsonify(api_routes._run_started_payload(started.run_id, status=started.status)), 202


@api_routes.api_v1_bp.route("/runs/<run_id>")
@api_routes.require_api_auth
def api_run_status(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    run = api_routes._run_status_from_active_or_row(run_id, session_id, owner_scope.team_id)
    if run is None:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    return jsonify({"run": run})


@api_routes.api_v1_bp.route("/runs/<run_id>/wait", methods=["POST"])
@api_routes.require_api_auth
def api_run_wait(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    timeout = api_routes._parse_float(request.args.get("timeout"), 30.0, minimum=0.0, maximum=3600.0)
    deadline = time.monotonic() + timeout
    poll_interval = 0.1
    while True:
        run = api_routes._run_status_from_active_or_row(run_id, session_id, owner_scope.team_id)
        if run is None:
            return api_routes._api_json_error("not_found", "Run not found.", 404)
        if str(run.get("status") or "") != "running":
            return jsonify({"run": run})
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return api_routes._api_json_error("wait_timeout", "Run is still running.", 408)
        time.sleep(min(poll_interval, remaining))


@api_routes.api_v1_bp.route("/runs/<run_id>/ai-assists")
@api_routes.require_api_auth
def api_run_ai_assists(run_id):
    owner_scope = api_routes._api_request_scope()
    try:
        assists = list_run_assists(api_routes._require_session_id(), run_id, team_id=owner_scope.team_id)
    except AIAssistRouteError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    return jsonify({"assists": assists})


@api_routes.api_v1_bp.route("/runs/<run_id>/ai-summary", methods=["POST"])
@api_routes.require_api_auth
def api_run_ai_summary(run_id):
    owner_scope = api_routes._api_request_scope()
    try:
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.RUN_COMMANDS)
        assist, status_code = enqueue_summary_assist(
            api_routes._require_session_id(),
            run_id,
            team_id=owner_scope.team_id,
            force=api_routes._parse_bool(api_routes._json_body().get("force")),
        )
    except AIAssistRouteError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except api_routes.TeamPermissionDenied as exc:
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    return jsonify({"assist": assist}), status_code


@api_routes.api_v1_bp.route("/runs/<run_id>/ai-next-commands", methods=["POST"])
@api_routes.require_api_auth
def api_run_ai_next_commands(run_id):
    owner_scope = api_routes._api_request_scope()
    try:
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.RUN_COMMANDS)
        assist, status_code = enqueue_next_commands_assist(
            api_routes._require_session_id(),
            run_id,
            team_id=owner_scope.team_id,
            force=api_routes._parse_bool(api_routes._json_body().get("force")),
        )
    except AIAssistRouteError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except api_routes.TeamPermissionDenied as exc:
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    return jsonify({"assist": assist}), status_code


@api_routes.api_v1_bp.route("/runs/<run_id>/projects/<project_id>", methods=["POST"])
@api_routes.require_api_auth
def api_run_project_link(run_id, project_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    try:
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MUTATE_PROJECTS)
        if api_routes._active_project_for_write(session_id, project_id, team_id=owner_scope.team_id) is None:
            return api_routes._api_json_error("not_found", "Project not found.", 404)
        link = link_project_entity(
            session_id,
            project_id,
            {"entity_type": "run", "entity_id": run_id, "source": "manual"},
            team_id=owner_scope.team_id,
        )
    except api_routes.ApiAuthError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except api_routes.TeamPermissionDenied as exc:
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    except ProjectWorkspaceError as exc:
        return api_routes._project_workspace_api_error(exc)
    if link is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    api_routes.log.info("API_PROJECT_RUN_LINKED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "project_id": project_id,
        "link_source": link.get("source") or "",
    })
    return jsonify({"ok": True, "link": link}), 201


@api_routes.api_v1_bp.route("/runs/<run_id>/projects/<project_id>", methods=["DELETE"])
@api_routes.require_api_auth
def api_run_project_unlink(run_id, project_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    try:
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.MUTATE_PROJECTS)
        if api_routes._active_project_for_write(session_id, project_id, team_id=owner_scope.team_id) is None:
            return api_routes._api_json_error("not_found", "Project not found.", 404)
        deleted = unlink_project_entity(
            session_id,
            project_id,
            {"entity_type": "run", "entity_id": run_id},
            team_id=owner_scope.team_id,
        )
    except api_routes.ApiAuthError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except api_routes.TeamPermissionDenied as exc:
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    except ProjectWorkspaceError as exc:
        return api_routes._project_workspace_api_error(exc)
    if deleted is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    if not deleted:
        return api_routes._api_json_error("not_found", "Project link not found.", 404)
    api_routes.log.info("API_PROJECT_RUN_UNLINKED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "project_id": project_id,
    })
    return jsonify({"ok": True})


@api_routes.api_v1_bp.route("/runs/<run_id>/stream")
@api_routes.require_api_auth
def api_run_stream(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    if api_routes._run_status_from_active_or_row(run_id, session_id, owner_scope.team_id) is None:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    after_id = api_routes._sse_after_id()
    api_routes.log.debug("API_RUN_STREAM_ATTACHED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "team_id": owner_scope.team_id,
        "after_id": after_id,
        "format": str(request.args.get("format") or "sse"),
    })
    stream_log_fields = {
        "ip": get_client_ip(),
        "route": str(request.path or ""),
        "method": str(request.method or ""),
    }
    if str(request.args.get("format") or "").lower() == "ndjson":
        return Response(
            api_routes._ndjson_from_sse_chunks(
                api_routes.stream_run_events(run_id, after_id=after_id),
                run_id=run_id,
                session_id=session_id,
                team_id=owner_scope.team_id,
                **stream_log_fields,
            ),
            mimetype="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
    return Response(
        api_routes._sse_chunks_with_error_logging(
            api_routes.stream_run_events(run_id, after_id=after_id),
            run_id=run_id,
            session_id=session_id,
            team_id=owner_scope.team_id,
            **stream_log_fields,
        ),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@api_routes.api_v1_bp.route("/runs/<run_id>/cancel", methods=["POST"])
@api_routes.require_api_auth
def api_run_cancel(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    try:
        api_routes._require_api_team_capability(owner_scope, api_routes.Capability.RUN_COMMANDS)
    except api_routes.TeamPermissionDenied as exc:
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    active_run = next(
        (
            run for run in api_routes.active_runs_for_session(session_id, team_id=owner_scope.team_id)
            if run.get("run_id") == run_id
        ),
        {},
    )
    if not active_run:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    pid = api_routes.pid_for_session(run_id, session_id)
    if not pid:
        return api_routes._api_json_error("not_found", "No active process found for run.", 404)
    try:
        api_routes._ensure_scanner_process_group_current(
            run_id,
            pid,
            session_id,
            team_id=owner_scope.team_id if owner_scope.is_team else "",
        )
        api_routes._signal_process_group(pid)
        api_routes.publish_run_event(run_id, "killed", {"api": True})
    except ProcessLookupError as exc:
        api_routes.publish_run_event(run_id, "killed", {"api": True})
        api_routes.log.warning("API_RUN_CANCEL_SIGNAL_FAILED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "error": str(exc),
        })
    except (subprocess.TimeoutExpired, OSError) as exc:
        api_routes.log.warning("API_RUN_CANCEL_SIGNAL_FAILED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "error": str(exc),
        })
        return api_routes._api_json_error("cancel_failed", "Failed to signal process.", 500)
    return jsonify({"killed": True, "id": run_id})
