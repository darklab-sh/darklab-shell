# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Server-owned workflow execution orchestration."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from services.metrics_lazy import app_metrics
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.runs.output_store import load_run_output_events_for_run
from services.runs.output_model import LineEvent
from services.workflows.captures import WorkflowCaptureAccumulator
from services.workflows.collections import WorkflowCollectionAccumulator
from services.workflows.compiler import (
    WorkflowDefinitionError,
    render_step_command,
    render_step_display_command,
    workflow_private_values,
)
from services.workflows.fanout_child_lifecycle import (
    finalize_fanout_child_run,
    reset_launching_fanout_child_for_recovery,
)
from services.workflows.fanout_child_queries import fanout_child_for_run
from services.workflows.fanout_children import list_fanout_children
from services.workflows.fanout_launch import launch_fanout_batch
from services.workflows.execution_kinds import WORKFLOW_EXECUTION_KIND
from services.workflows.execution_authorization import (
    current_execution_role as _current_execution_role,
    execution_elapsed_seconds,
    execution_expired as _execution_expired,
    max_execution_runtime_seconds as _max_runtime_seconds,
)
from services.workflows import storage


log = logging.getLogger("shell")


class _WorkflowRunBindingError(RuntimeError):
    pass


def _record_execution_finished(execution_id: str, status: str) -> None:
    execution = storage.get_execution_by_id(execution_id) or {}
    duration_seconds = execution_elapsed_seconds(execution)
    app_metrics.record_workflow_execution_outcome(status, duration_seconds)
    log.info("WORKFLOW_EXECUTION_COMPLETED", extra={
        "execution_id": execution_id,
        "workflow_status": status,
        "duration_ms": int(duration_seconds * 1000),
    })


def _record_failed_step_and_execution(execution_id: str, step_id: str) -> None:
    if step_id:
        app_metrics.record_workflow_step_outcome("failed")
    _record_execution_finished(execution_id, "failed")


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


def _capture_results(
    capture: object | None,
) -> tuple[dict[str, str], dict[str, list[str]], str]:
    scalar = getattr(capture, "workflow_capture_accumulator", None)
    collection = getattr(capture, "workflow_collection_accumulator", None)
    captures: dict[str, str] = {}
    collections: dict[str, list[str]] = {}
    errors: list[str] = []
    if isinstance(scalar, WorkflowCaptureAccumulator):
        captures, error = scalar.result()
        if error:
            errors.append(error)
    if isinstance(collection, WorkflowCollectionAccumulator):
        collections, error = collection.result()
        if error:
            errors.append(error)
    return captures, collections, "; ".join(errors)


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


def _launch_current_fanout_batch(execution_id: str) -> dict[str, object] | None:
    execution = storage.get_execution_by_id(execution_id)
    if not execution:
        return None
    step_id = str(execution.get("current_step_id") or "")
    can_launch, current_role = _execution_can_launch(execution, step_id)
    if not can_launch:
        return None
    definition = execution.get("definition_snapshot")
    step = _definition_step(
        definition if isinstance(definition, Mapping) else {},
        step_id,
    )
    if not step or not isinstance(step.get("for_each"), Mapping):
        changed = storage.fail_execution(
            execution_id,
            "fanout_definition_error",
            "The current workflow fan-out step is invalid.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_FANOUT_DEFINITION_MISSING", extra={
            "execution_id": execution_id,
            "step_id": step_id,
        })
        return None
    try:
        result = launch_fanout_batch(execution, step, current_role)
    except WorkflowDefinitionError as exc:
        changed = storage.fail_execution(
            execution_id,
            "fanout_definition_error",
            str(exc),
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_FANOUT_LAUNCH_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "error_type": type(exc).__name__,
            "stage": "plan",
        })
        return None
    except Exception as exc:
        changed = storage.fail_execution(
            execution_id,
            "fanout_launch_failed",
            "The workflow fan-out batch could not be launched.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.error("WORKFLOW_FANOUT_LAUNCH_ERROR", exc_info=True, extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "error_type": type(exc).__name__,
            "stage": "batch",
        })
        return None
    raw_transition = result.pop("parent_transition", None)
    if isinstance(raw_transition, Mapping) and raw_transition:
        _log_step_transition(raw_transition)
        if not raw_transition.get("terminal"):
            launch_execution_step(str(raw_transition["execution_id"]))
    return result


def _continue_after_fanout_child(
    child: Mapping[str, object],
    finalized_child: Mapping[str, object],
) -> dict[str, object] | None:
    parent_transition = finalized_child.get("parent_transition")
    if not isinstance(parent_transition, Mapping) or not parent_transition:
        _launch_current_fanout_batch(str(child.get("execution_id") or ""))
        return None
    _log_step_transition(parent_transition)
    if not parent_transition.get("terminal"):
        launch_execution_step(str(parent_transition["execution_id"]))
    return dict(parent_transition)


def finalize_workflow_run(run_id: str, exit_code: int, capture: object | None) -> dict[str, object] | None:
    child = fanout_child_for_run(run_id)
    if child and str(child.get("execution_kind") or "") != WORKFLOW_EXECUTION_KIND:
        return None
    if child and str(child.get("status") or "") != "running":
        return None
    linked_execution = storage.execution_for_run(run_id)
    if linked_execution and _execution_expired(linked_execution):
        changed = (
            storage.fail_execution(
                str(linked_execution.get("id") or ""),
                "execution_timeout",
                "The workflow exceeded its maximum runtime.",
                step_id=str(child.get("step_id") or ""),
            )
            if child
            else storage.fail_execution_for_run(
                run_id,
                "execution_timeout",
                "The workflow exceeded its maximum runtime.",
            )
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
    if child:
        finalized_child = finalize_fanout_child_run(run_id, int(exit_code))
        if not finalized_child:
            return None
        return _continue_after_fanout_child(child, finalized_child)
    captures, collection_captures, capture_error = _capture_results(capture)
    state = storage.finalize_run_step(
        run_id,
        int(exit_code),
        captures=captures,
        collection_captures=collection_captures,
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
    if isinstance(step.get("for_each"), Mapping):
        return _launch_current_fanout_batch(execution_id)
    try:
        command = render_step_command(step, variables if isinstance(variables, Mapping) else {})
        display_command = render_step_display_command(
            step,
            definition if isinstance(definition, Mapping) else {},
            variables if isinstance(variables, Mapping) else {},
        )
        private_values = workflow_private_values(
            definition if isinstance(definition, Mapping) else {},
            variables if isinstance(variables, Mapping) else {},
        )
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
    collection_accumulator = WorkflowCollectionAccumulator(step.get("captures"))
    capture_holder: dict[str, object] = {}

    def attach_run(run_id: str, capture: object | None) -> None:
        if not storage.bind_step_run(execution_id, step_id, run_id):
            raise _WorkflowRunBindingError("workflow step run binding was already claimed")
        if capture is not None:
            def observe(event: LineEvent) -> None:
                accumulator.observe(event)
                collection_accumulator.observe(event)

            setattr(capture, "_event_observer", observe)
            setattr(capture, "workflow_capture_accumulator", accumulator)
            setattr(capture, "workflow_collection_accumulator", collection_accumulator)
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
            display_command=display_command,
            private_values=private_values,
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
    collection_accumulator = WorkflowCollectionAccumulator(step_definition.get("captures"))
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
        collection_accumulator.observe(event)
    captures, capture_error = accumulator.result()
    collection_captures, collection_error = collection_accumulator.result()
    capture_error = "; ".join(error for error in (capture_error, collection_error) if error)
    state = storage.finalize_run_step(
        str(run.get("id") or ""),
        int(str(run.get("exit_code") or 0)),
        captures=captures,
        collection_captures=collection_captures,
        capture_error=capture_error,
    )
    if state:
        _log_step_transition(state)
        if not state.get("terminal"):
            launch_execution_step(str(state["execution_id"]))
    return state


def _recover_fanout_step(
    execution: Mapping[str, object],
    step: Mapping[str, object],
) -> str:
    execution_id = str(execution.get("id") or "")
    step_id = str(step.get("step_id") or "")
    recovered = False
    missing_child = False
    children = list_fanout_children(execution_id, step_id)
    if any(
        (
            str(child.get("status") or "") == "launching"
            and bool(str(child.get("run_id") or ""))
        )
        or (
            str(child.get("status") or "") == "running"
            and not str(child.get("run_id") or "")
        )
        for child in children
    ):
        changed = storage.fail_execution(
            execution_id,
            "recovery_state_invalid",
            "The workflow fan-out step has an invalid child recovery state.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_RECOVERY_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "reason": "fanout_child_state_invalid",
        })
        return "failed"
    for child in children:
        child_status = str(child.get("status") or "")
        run_id = str(child.get("run_id") or "")
        if child_status == "launching" and not run_id:
            recovered = reset_launching_fanout_child_for_recovery(
                str(child.get("id") or "")
            ) or recovered
            continue
        if child_status != "running" or not run_id:
            continue
        completed_run = storage.completed_run_for_recovery(run_id)
        if completed_run:
            finalize_workflow_run(
                run_id,
                int(str(completed_run.get("exit_code") or 0)),
                None,
            )
            recovered = True
            continue
        if _run_is_still_active(execution, run_id):
            continue
        finalized = finalize_fanout_child_run(
            run_id,
            1,
            error_code="active_run_missing",
        )
        if finalized:
            _continue_after_fanout_child(child, finalized)
            recovered = True
            missing_child = True
            log.warning("WORKFLOW_FANOUT_RECOVERY_CHILD_MISSING", extra={
                "execution_id": execution_id,
                "step_id": step_id,
                "ordinal": int(str(child.get("ordinal") or 0)),
                "attempt": int(str(child.get("attempt") or 1)),
                "run_id": run_id,
            })

    current = storage.get_execution_by_id(execution_id)
    if not current or str(current.get("status") or "") not in storage.ACTIVE_EXECUTION_STATUSES:
        if missing_child and str((current or {}).get("status") or "") == "failed":
            return "failed"
        return "recovered" if recovered else "ignored"
    if str(current.get("current_step_id") or "") == step_id:
        launched = _launch_current_fanout_batch(execution_id)
        raw_launches = (launched or {}).get("launched")
        recovered = (
            bool(raw_launches)
            or str((launched or {}).get("status") or "") == "completed"
            or recovered
        )
        refreshed = storage.get_execution_by_id(execution_id)
        refreshed_status = str((refreshed or {}).get("status") or "")
        if refreshed_status == "failed" and (missing_child or not recovered):
            return "failed"
        if refreshed_status == "completed":
            return "recovered"
    return "recovered" if recovered else "left_running"


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
    definition = execution.get("definition_snapshot")
    step_definition = _definition_step(
        definition if isinstance(definition, Mapping) else {},
        step_id,
    )
    if step_definition and isinstance(step_definition.get("for_each"), Mapping):
        if step_status == "pending" and not run_id:
            launch_execution_step(execution_id)
            return "recovered"
        if step_status in {"launching", "running"} and not run_id:
            return _recover_fanout_step(execution, step)
        changed = storage.fail_execution(
            execution_id,
            "recovery_state_invalid",
            "The workflow fan-out parent has an invalid recovery state.",
            step_id=step_id,
        )
        if changed:
            _record_failed_step_and_execution(execution_id, step_id)
        log.warning("WORKFLOW_RECOVERY_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "reason": "fanout_parent_state_invalid",
        })
        return "failed"
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
