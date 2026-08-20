# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Launch one private fan-out item through the shared run service."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.runs.start_context import cleanup_started_run_material
from services.workflows.child_launch_spec import ChildLaunchSpec
from services.workflows.fanout_child_lifecycle import (
    bind_fanout_child_run,
    finalize_fanout_child_run,
)
from services.workflows.fanout_launch_state import fail_launching_fanout_child


log = logging.getLogger("shell")


class FanoutRunBindingError(RuntimeError):
    pass


def _integer(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _launch_failure_code(exc: Exception) -> str:
    if isinstance(exc, FanoutRunBindingError) or isinstance(exc.__cause__, FanoutRunBindingError):
        return "binding_failed"
    if isinstance(exc, RunStartRejected):
        code = str(exc.code or "").strip().lower()
        if code == "project_link_not_supported":
            return "scope_rejected"
        if code in {"broker_unavailable", "scope_rejected", "permission_denied"}:
            return code
        return "launch_rejected"
    if isinstance(exc, RunPreparationError):
        return "scope_rejected"
    if isinstance(exc, RunSpawnError):
        return "spawn_failed"
    return "launch_failed"


def launch_fanout_child(
    execution: Mapping[str, object],
    step_id: str,
    child: Mapping[str, object],
    current_role: str,
    launch_spec: ChildLaunchSpec,
) -> tuple[dict[str, object], dict[str, object]]:
    """Start one claimed child without deriving or persisting its private inputs."""
    from blueprints import run as run_routes  # noqa: PLC0415

    execution_id = str(execution.get("id") or "")
    execution_kind = str(execution.get("execution_kind") or "workflow")
    child_id = str(child.get("id") or "")
    ordinal = _integer(child.get("ordinal"), 0)
    command = launch_spec.execution_command
    interactive_spec = run_routes.interactive_pty_spec_for_command(command)
    interactive_trigger = str((interactive_spec or {}).get("trigger_flag") or "").strip()
    if interactive_trigger and interactive_trigger in run_routes.split_command_argv(command)[1:]:
        failed = fail_launching_fanout_child(child_id, "interactive_pty_unsupported") or {}
        return {}, failed

    def attach_run(run_id: str, _capture: object | None) -> None:
        if not bind_fanout_child_run(child_id, run_id):
            raise FanoutRunBindingError("workflow fan-out child binding was already claimed")

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
            display_command=launch_spec.display_command,
            session_id=str(execution.get("session_id") or ""),
            team_id=str(execution.get("team_id") or ""),
            team_role=current_role or str(execution.get("actor_role") or ""),
            client_ip="",
            handlers=run_routes._run_start_handlers(),
            owner_client_id=str(execution.get("owner_client_id") or ""),
            owner_tab_id=str(execution.get("owner_tab_id") or ""),
            workspace_cwd=str(execution.get("workspace_cwd") or ""),
            link_project_id="" if builtin_step else str(execution.get("project_id") or ""),
            thread_name_prefix=(
                "assessment-batch-run"
                if execution_kind == "assessment_batch"
                else "workflow-fanout-run"
            ),
            run_created_hook=attach_run,
            **launch_spec.broker_kwargs(),
        )
    except (RunPreparationError, RunStartRejected, RunSpawnError, FanoutRunBindingError) as exc:
        cleanup_started_run_material(launch_spec.run_cleanup_hook)
        error_code = _launch_failure_code(exc)
        failed = fail_launching_fanout_child(child_id, error_code) or {}
        log.warning("WORKFLOW_FANOUT_CHILD_LAUNCH_FAILED", extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "ordinal": ordinal,
            "attempt": _integer(child.get("attempt"), 1),
            "reason": error_code,
            "error_type": type(exc).__name__,
        })
        return {}, failed
    except Exception as exc:
        cleanup_started_run_material(launch_spec.run_cleanup_hook)
        failed = fail_launching_fanout_child(child_id, "launch_failed") or {}
        log.error("WORKFLOW_FANOUT_CHILD_LAUNCH_ERROR", exc_info=True, extra={
            "execution_id": execution_id,
            "step_id": step_id,
            "ordinal": ordinal,
            "attempt": _integer(child.get("attempt"), 1),
            "error_type": type(exc).__name__,
        })
        return {}, failed

    log.info("WORKFLOW_FANOUT_CHILD_STARTED", extra={
        "execution_id": execution_id,
        "step_id": step_id,
        "ordinal": ordinal,
        "attempt": _integer(child.get("attempt"), 1),
        "run_id": started.run_id,
        "cmd_type": started.cmd_type,
    })
    transition: dict[str, object] = {}
    if started.exit_code is not None:
        finalized = finalize_fanout_child_run(started.run_id, started.exit_code)
        raw_transition = (finalized or {}).get("parent_transition")
        if isinstance(raw_transition, Mapping):
            transition = dict(raw_transition)
    return {
        "run_id": started.run_id,
        "status": started.status,
        "stream": f"/runs/{started.run_id}/stream",
    }, {"parent_transition": transition}
