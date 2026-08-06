# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Data contracts for shared run-start orchestration."""

from dataclasses import dataclass
from typing import Any, Callable


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
