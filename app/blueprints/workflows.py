# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable workflow execution HTTP routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from config import resolve_effective_cfg
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.commands.registry import load_all_workflows
from services.metrics_lazy import app_metrics
from services.projects.active import get_active_project
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload
from services.workflows.compiler import (
    WorkflowDefinitionError,
    compile_execution_definition,
    resolve_workflow_inputs,
)
from services.workflows.contracts import WorkflowActiveExecutionLimitExceeded
from services.workflows.executions import execution_elapsed_seconds, launch_execution_step
from services.workflows.events import replay_execution_events
from services.workflows.storage import (
    ACTIVE_EXECUTION_STATUSES,
    cancel_execution,
    create_execution,
    get_execution,
    list_executions,
    public_execution,
)
from services.workflows.user_workflows import get_user_workflow


log = logging.getLogger("shell")
workflows_bp = Blueprint("workflows", __name__)


def _scope_or_response(session_id: str):
    try:
        return current_request_scope(session_id, request), None
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, (jsonify(payload), status)


def _run_capability_response(scope):
    if not scope.is_team:
        return None
    role = str((scope.member or {}).get("role") or "")
    try:
        require_capability(role, Capability.RUN_COMMANDS)
    except TeamPermissionDenied:
        return jsonify({
            "error": "team_forbidden",
            "message": "Your team role cannot run shared workflows.",
        }), 403
    return None


def _catalog_workflow(session_id: str, workflow_id: str, *, team_id: str = ""):
    saved = get_user_workflow(session_id, workflow_id, team_id=team_id)
    if saved:
        return saved
    return next((item for item in load_all_workflows(resolve_effective_cfg()) if item.get("id") == workflow_id), None)


@workflows_bp.route("/workflow-executions", methods=["POST"])
def workflow_executions_create():
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    scope, error_response = _scope_or_response(session_id)
    if error_response:
        return error_response
    if scope is None:
        return jsonify({"error": "scope_unavailable"}), 500
    forbidden = _run_capability_response(scope)
    if forbidden:
        return forbidden
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        log.warning("WORKFLOW_EXECUTION_VALIDATION_FAILED", extra={
            "reason": "invalid_body",
            "session": get_log_session_id(session_id),
        })
        return jsonify({"error": "Request body must be a JSON object"}), 400
    workflow_id = str(data.get("workflow_id") or "").strip()
    workflow = _catalog_workflow(session_id, workflow_id, team_id=scope.team_id)
    if not workflow:
        return jsonify({"error": "workflow not found"}), 404
    provided = data.get("inputs") or {}
    if not isinstance(provided, dict):
        log.warning("WORKFLOW_EXECUTION_VALIDATION_FAILED", extra={
            "reason": "invalid_inputs",
            "workflow_id": workflow_id,
            "session": get_log_session_id(session_id),
        })
        return jsonify({"error": "workflow inputs must be an object"}), 400
    try:
        definition = compile_execution_definition(workflow)
        inputs = resolve_workflow_inputs(definition, provided)
    except WorkflowDefinitionError as exc:
        log.warning("WORKFLOW_EXECUTION_VALIDATION_FAILED", extra={
            "reason": "definition_or_input",
            "workflow_id": workflow_id,
            "error_type": type(exc).__name__,
            "session": get_log_session_id(session_id),
        })
        return jsonify({"error": str(exc)}), 400
    raw_steps = definition.get("steps")
    definition_steps = raw_steps if isinstance(raw_steps, list) else []
    if any(
        isinstance(step, dict) and (
            isinstance(step.get("for_each"), dict)
            or any(
                isinstance(capture, dict)
                and str(capture.get("kind") or capture.get("mode") or "").strip().lower()
                == "collection"
                for capture in step.get("captures") or []
            )
        )
        for step in definition_steps
    ):
        log.warning("WORKFLOW_EXECUTION_VALIDATION_FAILED", extra={
            "reason": "fanout_execution_unavailable",
            "workflow_id": workflow_id,
            "session": get_log_session_id(session_id),
        })
        return jsonify({
            "error": "workflow_fanout_execution_unavailable",
            "message": "This workflow's collection fan-out cannot start safely.",
        }), 400

    project = get_active_project(session_id, team_id=scope.team_id)
    member = scope.member or {}
    try:
        execution = create_execution(
            session_id=session_id,
            team_id=scope.team_id,
            workflow_id=workflow_id,
            workflow_source=str(workflow.get("source") or "config"),
            definition=definition,
            inputs=inputs,
            workspace_cwd=str(data.get("workspace_cwd") or "").strip()[:500],
            project_id=str((project or {}).get("id") or ""),
            actor_member_id=str(member.get("id") or ""),
            actor_role=str(member.get("role") or ""),
            owner_client_id=str(request.headers.get("X-Client-ID") or "").strip()[:128],
            owner_tab_id=str(data.get("tab_id") or "").strip()[:128],
            max_active=int(resolve_effective_cfg().get("workflow_active_execution_limit") or 3),
        )
    except WorkflowActiveExecutionLimitExceeded as exc:
        log.warning("WORKFLOW_EXECUTION_LIMIT_REACHED", extra={
            "limit": exc.limit,
            "team_id": scope.team_id,
            "session": get_log_session_id(session_id),
            "ip": get_client_ip(),
        })
        return jsonify({
            "error": "workflow_execution_limit",
            "message": str(exc),
            "limit": exc.limit,
        }), 429
    launch = launch_execution_step(str(execution["id"]))
    current = get_execution(session_id, str(execution["id"]), team_id=scope.team_id) or execution
    definition_steps = definition.get("steps")
    log.info("WORKFLOW_EXECUTION_STARTED", extra={
        "execution_id": str(execution["id"]),
        "workflow_id": workflow_id,
        "workflow_source": str(workflow.get("source") or "config"),
        "step_count": len(definition_steps) if isinstance(definition_steps, list) else 0,
        "team_id": scope.team_id,
        "session": get_log_session_id(session_id),
        "ip": get_client_ip(),
    })
    record_event(
        AuditEventType.WORKFLOW_EXECUTION_START,
        target_id=str(execution["id"]),
        project_id=str((project or {}).get("id") or ""),
        details={
            "action": "start",
            "source": str(workflow.get("source") or "config"),
            "status": str(current.get("status") or "queued"),
            "count": len(definition_steps) if isinstance(definition_steps, list) else 0,
        },
        **route_audit_fields(session_id, request, scope),
    )
    return jsonify({"execution": public_execution(current), "launch": launch}), 202


@workflows_bp.route("/workflow-executions")
def workflow_executions_list():
    session_id = get_session_id()
    scope, error_response = _scope_or_response(session_id)
    if error_response:
        return error_response
    if scope is None:
        return jsonify({"error": "scope_unavailable"}), 500
    try:
        limit = int(request.args.get("limit", 50) or 50)
    except (TypeError, ValueError):
        limit = 50
    workflow_id = str(request.args.get("workflow_id") or "").strip()[:200]
    return jsonify({
        "executions": [
            public_execution(execution)
            for execution in list_executions(
                session_id,
                team_id=scope.team_id,
                workflow_id=workflow_id,
                limit=limit,
            )
        ],
    })


@workflows_bp.route("/workflow-executions/<execution_id>")
def workflow_executions_get(execution_id: str):
    session_id = get_session_id()
    scope, error_response = _scope_or_response(session_id)
    if error_response:
        return error_response
    if scope is None:
        return jsonify({"error": "scope_unavailable"}), 500
    execution = get_execution(session_id, execution_id, team_id=scope.team_id)
    if not execution:
        return jsonify({"error": "workflow execution not found"}), 404
    return jsonify({"execution": public_execution(execution)})


@workflows_bp.route("/workflow-executions/<execution_id>/events")
def workflow_executions_events(execution_id: str):
    session_id = get_session_id()
    scope, error_response = _scope_or_response(session_id)
    if error_response:
        return error_response
    if scope is None:
        return jsonify({"error": "scope_unavailable"}), 500
    execution = get_execution(session_id, execution_id, team_id=scope.team_id)
    if not execution:
        return jsonify({"error": "workflow execution not found"}), 404
    try:
        after = int(request.args.get("after", 0) or 0)
        limit = int(request.args.get("limit", 100) or 100)
    except (TypeError, ValueError):
        return jsonify({"error": "after and limit must be integers"}), 400
    return jsonify(replay_execution_events(execution, after=after, limit=limit))


@workflows_bp.route("/workflow-executions/<execution_id>/cancel", methods=["POST"])
def workflow_executions_cancel(execution_id: str):
    from blueprints import run as run_routes  # noqa: PLC0415

    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    scope, error_response = _scope_or_response(session_id)
    if error_response:
        return error_response
    if scope is None:
        return jsonify({"error": "scope_unavailable"}), 500
    forbidden = _run_capability_response(scope)
    if forbidden:
        return forbidden
    before = get_execution(session_id, execution_id, team_id=scope.team_id)
    if not before:
        return jsonify({"error": "workflow execution not found"}), 404
    execution = cancel_execution(session_id, execution_id, team_id=scope.team_id)
    canceled_run_ids = (
        execution.pop("_canceled_run_ids", [])
        if isinstance(execution, dict)
        else []
    )
    for active_run_id in canceled_run_ids:
        pid = (
            run_routes.pid_for_team(active_run_id, scope.team_id)
            if scope.is_team
            else run_routes.pid_for_session(active_run_id, session_id)
        )
        if pid:
            try:
                run_routes._ensure_scanner_process_group_current(
                    active_run_id,
                    pid,
                    session_id,
                    team_id=scope.team_id,
                )
                run_routes._signal_process_group(pid)
            except (OSError, RuntimeError) as exc:
                log.warning("WORKFLOW_CANCEL_SIGNAL_FAILED", extra={
                    "execution_id": execution_id,
                    "run_id": active_run_id,
                    "error_type": type(exc).__name__,
                })
    active_run_id = str(canceled_run_ids[0]) if canceled_run_ids else ""
    if str(before.get("status") or "") in ACTIVE_EXECUTION_STATUSES:
        duration_seconds = execution_elapsed_seconds(execution or before)
        canceled_steps = sum(
            1
            for step in before.get("steps") or []
            if str(step.get("status") or "") in {"pending", "launching", "running"}
        )
        app_metrics.record_workflow_cancellation()
        app_metrics.record_workflow_execution_outcome("canceled", duration_seconds)
        app_metrics.record_workflow_step_outcome("canceled", count=canceled_steps)
        log.info("WORKFLOW_EXECUTION_CANCELED", extra={
            "execution_id": execution_id,
            "run_id": active_run_id,
            "step_count": canceled_steps,
            "duration_ms": int(duration_seconds * 1000),
            "team_id": scope.team_id,
            "session": get_log_session_id(session_id),
            "ip": get_client_ip(),
        })
        record_event(
            AuditEventType.WORKFLOW_EXECUTION_CANCEL,
            target_id=execution_id,
            project_id=str(before.get("project_id") or ""),
            details={"action": "cancel", "status": "canceled", "count": canceled_steps},
            **route_audit_fields(session_id, request, scope),
        )
    return jsonify({"execution": public_execution(execution)})
