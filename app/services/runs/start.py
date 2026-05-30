"""Shared run-start orchestration for browser and API routes."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from services.teams.scope import OwnerContext, owner_context_for_scope


class RunPreparationError(Exception):
    def __init__(self, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


class RunSpawnError(Exception):
    pass


class RunStartRejected(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class RunStartHandlers:
    resolves_exact_special_builtin_command: Callable[[str], bool]
    execute_builtin_command: Callable[..., tuple[list[dict[str, Any]], int]]
    history_safe_command_for_storage: Callable[[str], str]
    brokered_synthetic_run: Callable[..., str]
    prepare_command_input: Callable[..., Any]
    resolve_builtin_command: Callable[[str], object]
    filter_builtin_command_events: Callable[..., list[dict[str, Any]]]
    prepare_real_command: Callable[..., Any]
    runtime_missing_command_message: Callable[[str], str]
    start_real_command_process: Callable[..., Any]
    publish_run_event: Callable[[str, str, dict[str, Any]], Any]
    brokered_real_run_worker: Callable[..., Any]
    workspace_notice_lines: Callable[[Any], list[str]]
    workspace_artifacts_from_validation: Callable[[Any, str], list[dict[str, Any]]]


@dataclass(frozen=True)
class BrokeredRunStartResult:
    run_id: str
    cmd_type: str
    status: str
    exit_code: int | None = None


def status_for_exit_code(exit_code: object) -> str:
    if not isinstance(exit_code, (int, str, bytes, bytearray)):
        return "complete"
    try:
        return "succeeded" if int(exit_code) == 0 else "failed"
    except (TypeError, ValueError):
        return "complete"


def start_brokered_run(
    *,
    original_command: str,
    session_id: str,
    client_ip: str,
    handlers: RunStartHandlers,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    team_id: str = "",
    team_role: str = "",
    workspace_cwd: str = "",
    link_project_id: str = "",
    thread_name_prefix: str = "run-broker",
) -> BrokeredRunStartResult:
    owner_context: OwnerContext = owner_context_for_scope(session_id, team_id=team_id)
    if handlers.resolves_exact_special_builtin_command(original_command):
        if link_project_id:
            raise RunStartRejected(
                "project_link_not_supported",
                "Project links only support external command runs.",
                status_code=409,
            )
        builtin_kwargs: dict[str, Any] = {"tab_id": owner_tab_id, "owner_context": owner_context}
        if team_id:
            builtin_kwargs.update({"team_id": team_id, "team_role": team_role})
        events, exit_code = handlers.execute_builtin_command(original_command, session_id, **builtin_kwargs)
        synthetic_kwargs: dict[str, str] = {"owner_tab_id": owner_tab_id}
        if team_id:
            synthetic_kwargs["team_id"] = team_id
        run_id = handlers.brokered_synthetic_run(
            handlers.history_safe_command_for_storage(original_command),
            session_id,
            client_ip,
            events,
            exit_code,
            **synthetic_kwargs,
        )
        return BrokeredRunStartResult(
            run_id=run_id,
            cmd_type="builtin",
            status=status_for_exit_code(exit_code),
            exit_code=exit_code,
        )

    prepared_input = handlers.prepare_command_input(original_command, session_id, client_ip)
    if handlers.resolve_builtin_command(prepared_input.execution_command):
        if link_project_id:
            raise RunStartRejected(
                "project_link_not_supported",
                "Project links only support external command runs.",
                status_code=409,
            )
        builtin_kwargs = {"tab_id": owner_tab_id, "owner_context": owner_context}
        if team_id:
            builtin_kwargs.update({"team_id": team_id, "team_role": team_role})
        events, exit_code = handlers.execute_builtin_command(prepared_input.execution_command, session_id, **builtin_kwargs)
        synthetic_kwargs = {"owner_tab_id": owner_tab_id}
        if team_id:
            synthetic_kwargs["team_id"] = team_id
        run_id = handlers.brokered_synthetic_run(
            handlers.history_safe_command_for_storage(original_command),
            session_id,
            client_ip,
            handlers.filter_builtin_command_events(
                events,
                prepared_input.variable_notice,
                prepared_input.postfilter,
            ),
            exit_code,
            **synthetic_kwargs,
        )
        return BrokeredRunStartResult(
            run_id=run_id,
            cmd_type="builtin",
            status=status_for_exit_code(exit_code),
            exit_code=exit_code,
        )

    if team_id:
        prepared_real = handlers.prepare_real_command(
            original_command,
            prepared_input.execution_command,
            session_id,
            client_ip,
            workspace_cwd,
            team_id=team_id,
            owner_context=owner_context,
        )
    else:
        prepared_real = handlers.prepare_real_command(
            original_command,
            prepared_input.execution_command,
            session_id,
            client_ip,
            workspace_cwd,
        )
    if prepared_real.missing_runtime:
        if link_project_id:
            raise RunStartRejected(
                "project_link_not_supported",
                "Project links only support completed external command runs.",
                status_code=409,
            )
        synthetic_kwargs = {"cmd_type": "missing", "owner_tab_id": owner_tab_id}
        if team_id:
            synthetic_kwargs["team_id"] = team_id
        run_id = handlers.brokered_synthetic_run(
            original_command,
            session_id,
            client_ip,
            [{"type": "output", "text": handlers.runtime_missing_command_message(prepared_real.missing_runtime)}],
            127,
            **synthetic_kwargs,
        )
        return BrokeredRunStartResult(
            run_id=run_id,
            cmd_type="missing",
            status="failed",
            exit_code=127,
        )

    start_kwargs: dict[str, Any] = {}
    if owner_client_id:
        start_kwargs["owner_client_id"] = owner_client_id
    if owner_tab_id:
        start_kwargs["owner_tab_id"] = owner_tab_id
    if team_id:
        start_kwargs["team_id"] = team_id
        start_kwargs["owner_context"] = owner_context
    started = handlers.start_real_command_process(
        original_command,
        session_id,
        client_ip,
        prepared_real,
        **start_kwargs,
    )
    handlers.publish_run_event(
        started.run_id,
        "started",
        {"run_id": started.run_id, "started": started.run_started},
    )
    threading.Thread(
        target=handlers.brokered_real_run_worker,
        kwargs={
            "run_id": started.run_id,
            "proc": started.proc,
            "session_id": session_id,
            "team_id": team_id,
            "client_ip": client_ip,
            "original_command": original_command,
            "run_started": started.run_started,
            "capture": started.capture,
            "signal_classifier": started.signal_classifier,
            "postfilter": prepared_input.postfilter,
            "workspace_path_filter": started.workspace_path_filter,
            "variable_notice": prepared_input.variable_notice,
            "rewrite_notice": prepared_real.rewrite_notice,
            "workspace_notices": handlers.workspace_notice_lines(prepared_real.validation),
            "workspace_artifacts": handlers.workspace_artifacts_from_validation(prepared_real.validation, session_id),
            "owner_tab_id": owner_tab_id,
            "link_project_id": link_project_id,
        },
        name=f"{thread_name_prefix}-{started.run_id[:8]}",
        daemon=True,
    ).start()
    return BrokeredRunStartResult(run_id=started.run_id, cmd_type="real", status="running")
