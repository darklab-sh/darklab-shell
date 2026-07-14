# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Server-owned workflow execution orchestration."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone

from config import resolve_effective_cfg
from core.database_access import get_db_connect
from services.metrics_lazy import app_metrics
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.runs.output_store import load_run_output_events_for_run
from services.teams.capabilities import Capability, role_can
from services.teams.storage import get_member, get_team
from services.workflows.captures import WorkflowCaptureAccumulator
from services.workflows.compiler import WorkflowDefinitionError, render_step_command
from services.workflows import storage


log = logging.getLogger("shell")


class _WorkflowRunBindingError(RuntimeError):
    pass


def _max_runtime_seconds() -> int:
    return max(1, int(resolve_effective_cfg().get("workflow_execution_max_runtime_seconds") or 14400))


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _execution_expired(execution: Mapping[str, object], *, now: datetime | None = None) -> bool:
    created = _parse_timestamp(execution.get("created"))
    if created is None:
        return True
    current = now or datetime.now(timezone.utc)
    return (current - created).total_seconds() >= _max_runtime_seconds()


def execution_elapsed_seconds(
    execution: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> float:
    created = _parse_timestamp(execution.get("created"))
    if created is None:
        return 0.0
    finished = _parse_timestamp(execution.get("finished")) or now or datetime.now(timezone.utc)
    return max(0.0, (finished - created).total_seconds())


def _record_execution_finished(execution_id: str, status: str) -> None:
    execution = storage.get_execution_by_id(execution_id) or {}
    duration_seconds = execution_elapsed_seconds(execution)
    app_metrics.record_workflow_execution_outcome(status, duration_seconds)
    log.info("WORKFLOW_EXECUTION_COMPLETED", extra={
        "execution_id": execution_id,
        "status": status,
        "duration_ms": int(duration_seconds * 1000),
    })


def _record_failed_step_and_execution(execution_id: str, step_id: str) -> None:
    if step_id:
        app_metrics.record_workflow_step_outcome("failed")
    _record_execution_finished(execution_id, "failed")


def _current_execution_role(execution: Mapping[str, object]) -> tuple[str, str, str]:
    team_id = str(execution.get("team_id") or "")
    member_id = str(execution.get("actor_member_id") or "")
    session_id = str(execution.get("session_id") or "")
    with get_db_connect()() as conn:
        token_exists = not session_id.startswith("tok_") or bool(
            conn.execute(
                "SELECT 1 FROM session_tokens WHERE token = ?",
                (session_id,),
            ).fetchone()
        )
        team = get_team(conn, team_id) if team_id else None
        member = get_member(conn, member_id) if member_id else None
    if not token_exists:
        return "token_revoked", "The workflow initiator's session token is no longer active.", ""
    if not team_id:
        return "", "", ""
    if not team or str(team.get("status") or "") != "active":
        return "team_unavailable", "The workflow's team is no longer active.", ""
    if (
        not member
        or str(member.get("team_id") or "") != team_id
        or str(member.get("status") or "") != "active"
        or bool(member.get("removed_at"))
    ):
        return "member_revoked", "The workflow initiator is no longer an active team member.", ""
    role = str(member.get("role") or "")
    if not role_can(role, Capability.RUN_COMMANDS):
        return "permission_revoked", "The workflow initiator can no longer run team commands.", role
    return "", "", role


def _execution_can_launch(execution: Mapping[str, object], step_id: str) -> tuple[bool, str]:
    execution_id = str(execution.get("id") or "")
    if _execution_expired(execution):
        changed = storage.fail_execution(
            execution_id,
            "execution_timeout",
            "The workflow exceeded its maximum runtime.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_EXECUTION_TIMEOUT", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "max_runtime_seconds": _max_runtime_seconds(),
        })
        return False, ""
    failure_code, failure_detail, current_role = _current_execution_role(execution)
    if failure_code:
        changed = storage.fail_execution(execution_id, failure_code, failure_detail, step_id=step_id)
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_EXECUTION_PERMISSION_REVOKED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "team_id": str(execution.get("team_id") or ""),
            "actor_member_id": str(execution.get("actor_member_id") or ""),
            "reason": failure_code,
        })
        return False, ""
    return True, current_role


def _definition_step(definition: Mapping[str, object], step_id: str) -> dict[str, object] | None:
    raw_steps = definition.get("steps")
    for step in raw_steps if isinstance(raw_steps, list) else []:
        if isinstance(step, dict) and step.get("id") == step_id:
            return step
    return None


def _log_step_transition(state: Mapping[str, object]) -> None:
    duration_ms = int(str(state.get("duration_ms") or 0))
    log.info("WORKFLOW_STEP_COMPLETED", extra={
        "execution_id": str(state.get("execution_id") or ""),
        "step_id": str(state.get("step_id") or ""),
        "step_status": str(state.get("step_status") or ""),
        "exit_code": int(str(state.get("exit_code") or 0)),
        "duration_ms": duration_ms,
        "transition": str(state.get("destination") or ""),
        "transition_reason": str(state.get("transition_reason") or ""),
    })
    app_metrics.record_workflow_step_outcome(
        str(state.get("step_status") or "failed"),
        duration_ms / 1000.0,
    )
    if state.get("capture_failed"):
        capture_reason = str(state.get("capture_failure_reason") or "other")
        app_metrics.record_workflow_capture_failure(capture_reason)
        log.warning("WORKFLOW_CAPTURE_FAILED", extra={
            "execution_id": str(state.get("execution_id") or ""),
            "step_id": str(state.get("step_id") or ""),
            "reason": capture_reason,
        })
    elif (
        str(state.get("step_status") or "") == "failed"
        and state.get("terminal")
        and state.get("destination") == "stop"
    ):
        log.warning("WORKFLOW_STEP_FAILED", extra={
            "execution_id": str(state.get("execution_id") or ""),
            "step_id": str(state.get("step_id") or ""),
            "exit_code": int(str(state.get("exit_code") or 0)),
            "transition_reason": str(state.get("transition_reason") or ""),
        })
    if state.get("terminal"):
        status = "completed" if state.get("destination") == "complete" else "failed"
        _record_execution_finished(str(state.get("execution_id") or ""), status)


def finalize_workflow_run(run_id: str, exit_code: int, capture: object | None) -> dict[str, object] | None:
    linked_execution = storage.execution_for_run(run_id)
    if linked_execution and _execution_expired(linked_execution):
        changed = storage.fail_execution_for_run(
            run_id,
            "execution_timeout",
            "The workflow exceeded its maximum runtime.",
        )
        if changed:
            _record_failed_step_and_execution(
                str(linked_execution.get("id") or ""),
                str(linked_execution.get("current_step_id") or ""),
            )
        log.warning("WORKFLOW_EXECUTION_TIMEOUT", extra={
            "execution_id": str(linked_execution.get("id") or ""),
            "step_id": str(linked_execution.get("current_step_id") or ""),
            "max_runtime_seconds": _max_runtime_seconds(),
        })
        return {
            "execution_id": str(linked_execution.get("id") or ""),
            "step_id": str(linked_execution.get("current_step_id") or ""),
            "step_status": "failed",
            "destination": "stop",
            "transition_reason": "execution_timeout",
            "terminal": True,
        }
    accumulator = getattr(capture, "workflow_capture_accumulator", None)
    captures: dict[str, str] = {}
    capture_error = ""
    if isinstance(accumulator, WorkflowCaptureAccumulator):
        captures, capture_error = accumulator.result()
    state = storage.finalize_run_step(
        run_id,
        int(exit_code),
        captures=captures,
        capture_error=capture_error,
    )
    if not state:
        return None
    _log_step_transition(state)
    if state.get("terminal"):
        return state
    launch_execution_step(str(state["execution_id"]))
    return state


def launch_execution_step(execution_id: str) -> dict[str, object] | None:
    """Claim and launch the execution's current step through the normal broker."""
    from blueprints import run as run_routes  # noqa: PLC0415

    pending_execution = storage.get_execution_by_id(execution_id)
    if not pending_execution:
        return None
    step_id = str(pending_execution.get("current_step_id") or "")
    can_launch, current_role = _execution_can_launch(pending_execution, step_id)
    if not can_launch:
        return None
    pointer = storage.execution_launch_pointer(execution_id)
    if not pointer:
        return None
    _session_id, _team_id, step_id = pointer
    execution = storage.claim_step_for_launch(execution_id, step_id)
    if not execution:
        return None
    definition = execution.get("definition_snapshot")
    variables = execution.get("variables")
    step = _definition_step(definition if isinstance(definition, Mapping) else {}, step_id)
    if not step:
        changed = storage.fail_step_launch(
            execution_id,
            step_id,
            "definition_error",
            "The current workflow step is missing.",
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_STEP_DEFINITION_MISSING", extra={
            "execution_id": execution_id,
            "step_id": step_id,
        })
        return None
    try:
        command = render_step_command(step, variables if isinstance(variables, Mapping) else {})
    except WorkflowDefinitionError as exc:
        changed = storage.fail_step_launch(execution_id, step_id, "render_failed", str(exc))
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_STEP_RENDER_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "error_type": type(exc).__name__,
        })
        return None

    interactive_spec = run_routes.interactive_pty_spec_for_command(command)
    interactive_trigger = str((interactive_spec or {}).get("trigger_flag") or "").strip()
    if interactive_trigger and interactive_trigger in run_routes.split_command_argv(command)[1:]:
        changed = storage.fail_step_launch(
            execution_id,
            step_id,
            "interactive_pty_unsupported",
            "Interactive PTY commands cannot run as workflow steps.",
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_INTERACTIVE_STEP_REJECTED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
        })
        return None

    accumulator = WorkflowCaptureAccumulator(step.get("captures"))
    capture_holder: dict[str, object] = {}

    def attach_run(run_id: str, capture: object | None) -> None:
        if not storage.bind_step_run(execution_id, step_id, run_id):
            raise _WorkflowRunBindingError("workflow step run binding was already claimed")
        if capture is not None:
            setattr(capture, "_event_observer", accumulator.observe)
            setattr(capture, "workflow_capture_accumulator", accumulator)
            capture_holder["capture"] = capture

    try:
        if not run_routes.broker_available():
            raise RunStartRejected(
                "broker_unavailable",
                run_routes.broker_unavailable_reason(),
                status_code=503,
            )
        builtin_step = bool(
            run_routes.resolves_exact_special_builtin_command(command)
            or run_routes.resolve_builtin_command(command)
        )
        started = run_routes._start_brokered_run_service(
            original_command=command,
            session_id=str(execution.get("session_id") or ""),
            team_id=str(execution.get("team_id") or ""),
            team_role=current_role or str(execution.get("actor_role") or ""),
            client_ip="",
            handlers=run_routes._run_start_handlers(),
            owner_client_id=str(execution.get("owner_client_id") or ""),
            owner_tab_id=str(execution.get("owner_tab_id") or ""),
            workspace_cwd=str(execution.get("workspace_cwd") or ""),
            link_project_id="" if builtin_step else str(execution.get("project_id") or ""),
            thread_name_prefix="workflow-run",
            run_created_hook=attach_run,
        )
    except (RunPreparationError, RunStartRejected) as exc:
        changed = storage.fail_step_launch(execution_id, step_id, "launch_failed", str(exc))
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_STEP_LAUNCH_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "error_type": type(exc).__name__,
            "stage": "run_start",
        })
        return None
    except _WorkflowRunBindingError as exc:
        changed = storage.fail_step_launch(
            execution_id,
            step_id,
            "launch_failed",
            "The workflow run could not be bound to its step.",
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.error("WORKFLOW_STEP_LAUNCH_ERROR", exc_info=True, extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "error_type": type(exc).__name__,
            "stage": "bind_run",
        })
        return None
    except RunSpawnError as exc:
        changed = storage.fail_step_launch(execution_id, step_id, "launch_failed", str(exc))
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        if isinstance(exc.__cause__, _WorkflowRunBindingError):
            log.error("WORKFLOW_STEP_LAUNCH_ERROR", exc_info=True, extra={
                "execution_id": execution_id,
                "step_id": step_id,
                "error_type": type(exc.__cause__).__name__,
                "stage": "bind_run",
            })
        else:
            log.warning("WORKFLOW_STEP_LAUNCH_FAILED", extra={
                "execution_id": execution_id,
                "step_id": step_id,
                "error_type": type(exc).__name__,
                "stage": "run_start",
            })
        return None
    except Exception as exc:
        changed = storage.fail_step_launch(
            execution_id,
            step_id,
            "launch_failed",
            "The workflow step could not be launched.",
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.error("WORKFLOW_STEP_LAUNCH_ERROR", exc_info=True, extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "error_type": type(exc).__name__,
            "stage": "run_start",
        })
        return None

    log.info("WORKFLOW_STEP_STARTED", extra={
        "execution_id": execution_id,
        "step_id": step_id,
        "run_id": started.run_id,
        "cmd_type": started.cmd_type,
    })
    if started.exit_code is not None:
        finalize_workflow_run(started.run_id, started.exit_code, capture_holder.get("capture"))
    return {
        "execution_id": execution_id,
        "step_id": step_id,
        "run_id": started.run_id,
        "status": started.status,
        "stream": f"/runs/{started.run_id}/stream",
    }


def _run_is_still_active(execution: Mapping[str, object], run_id: str) -> bool:
    from core.process import pid_for_session, pid_for_team  # noqa: PLC0415

    team_id = str(execution.get("team_id") or "")
    if team_id:
        return pid_for_team(run_id, team_id) is not None
    return pid_for_session(run_id, str(execution.get("session_id") or "")) is not None


def _recover_completed_step(
    execution: Mapping[str, object],
    step: Mapping[str, object],
    run: Mapping[str, object],
) -> dict[str, object] | None:
    definition = execution.get("definition_snapshot")
    step_definition = _definition_step(
        definition if isinstance(definition, Mapping) else {},
        str(step.get("step_id") or ""),
    )
    if not step_definition:
        execution_id = str(execution.get("id") or "")
        step_id = str(step.get("step_id") or "")
        changed = storage.fail_execution(
            execution_id,
            "recovery_definition_error",
            "The current workflow step is missing from its saved definition.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_RECOVERY_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "reason": "recovery_definition_error",
        })
        return None
    accumulator = WorkflowCaptureAccumulator(step_definition.get("captures"))
    output = load_run_output_events_for_run(
        run,
        log_event="WORKFLOW_RECOVERY_OUTPUT_LOAD_FAILED",
        failure_log_extra={
            "execution_id": str(execution.get("id") or ""),
            "step_id": str(step.get("step_id") or ""),
            "stage": "load_completed_run_output",
        },
    )
    for event in output.events:
        accumulator.observe(event)
    captures, capture_error = accumulator.result()
    state = storage.finalize_run_step(
        str(run.get("id") or ""),
        int(str(run.get("exit_code") or 0)),
        captures=captures,
        capture_error=capture_error,
    )
    if state:
        _log_step_transition(state)
        if not state.get("terminal"):
            launch_execution_step(str(state["execution_id"]))
    return state


def recover_workflow_execution(execution_id: str) -> str:
    execution = storage.get_execution_by_id(execution_id)
    if not execution or str(execution.get("status") or "") not in storage.ACTIVE_EXECUTION_STATUSES:
        return "ignored"
    step_id = str(execution.get("current_step_id") or "")
    steps = execution.get("steps")
    step = next(
        (
            item for item in steps if isinstance(item, Mapping) and item.get("step_id") == step_id
        ),
        None,
    ) if isinstance(steps, list) else None
    if not step:
        changed = storage.fail_execution(
            execution_id,
            "recovery_step_missing",
            "The active workflow step could not be recovered.",
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_RECOVERY_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "reason": "recovery_step_missing",
        })
        return "failed"
    can_launch, _role = _execution_can_launch(execution, step_id)
    if not can_launch:
        return "failed"
    step_status = str(step.get("status") or "")
    run_id = str(step.get("run_id") or "")
    if step_status == "launching" and not run_id:
        storage.reset_launching_step_for_recovery(execution_id, step_id)
        step_status = "pending"
    if step_status == "pending":
        launch_execution_step(execution_id)
        return "recovered"
    if step_status == "running" and run_id:
        completed_run = storage.completed_run_for_recovery(run_id)
        if completed_run:
            _recover_completed_step(execution, step, completed_run)
            return "recovered"
        if _run_is_still_active(execution, run_id):
            return "left_running"
        changed = storage.fail_execution(
            execution_id,
            "active_run_missing",
            "The workflow's active run disappeared during recovery.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_RECOVERY_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "run_id": run_id,
            "reason": "active_run_missing",
        })
        return "failed"
    changed = storage.fail_execution(
        execution_id,
        "recovery_state_invalid",
        "The workflow's active step has an invalid recovery state.",
        step_id=step_id,
    )
    if changed:
        _record_failed_step_and_execution(execution_id, step_id)
    log.warning("WORKFLOW_RECOVERY_FAILED", extra={
        "execution_id": execution_id,
        "step_id": step_id,
        "reason": "recovery_state_invalid",
    })
    return "failed"


def recover_workflow_executions(*, limit: int = 100) -> dict[str, int]:
    """Reconcile durable workflow state after process startup."""
    result = {"recovered": 0, "left_running": 0, "failed": 0, "ignored": 0, "errors": 0}
    after_created = ""
    after_id = ""
    while True:
        page = storage.active_execution_page_for_recovery(
            limit=limit,
            after_created=after_created,
            after_id=after_id,
        )
        if not page:
            break
        for execution_id, created in page:
            try:
                outcome = recover_workflow_execution(execution_id)
            except Exception:
                result["errors"] += 1
                app_metrics.record_workflow_recovery_action("failed")
                log.error("WORKFLOW_RECOVERY_ERROR", exc_info=True, extra={
                    "execution_id": execution_id,
                    "stage": "recover_execution",
                    "pid": os.getpid(),
                    "recovery_owner": True,
                })
            else:
                if outcome in result:
                    result[outcome] += 1
                    app_metrics.record_workflow_recovery_action(outcome)
            after_created = created
            after_id = execution_id
        if len(page) < max(1, min(int(limit or 100), 500)):
            break
    log.info("WORKFLOW_RECOVERY_COMPLETED", extra={
        **result,
        "examined": sum(result.values()),
        "pid": os.getpid(),
        "recovery_owner": True,
    })
    return result
