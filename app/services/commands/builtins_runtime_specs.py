# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Registry specifications for runtime, history, and status helpers."""

from __future__ import annotations

from services.commands import builtins_runtime
from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    build_builtin_command_spec,
)
from services.commands.registry import command_root, split_command_argv


_BUILTIN_AUTOCOMPLETE = {
    "history": {
        "root": "history",
        "description": "built-in: list command history from this session",
        "autocomplete": {"arguments": []},
    },
    "jobs": {
        "root": "jobs",
        "description": "built-in: alias for runs",
        "autocomplete": {
            "flags": [
                {"value": "-v", "description": "Show full IDs, started timestamps, and metadata source"},
                {"value": "--verbose", "description": "Show full IDs, started timestamps, and metadata source"},
                {"value": "--json", "description": "Print active-run metadata as JSON"},
            ]
        },
    },
    "last": {
        "root": "last",
        "description": "built-in: show recent completed runs with timestamps and exit codes",
        "autocomplete": {"arguments": []},
    },
    "limits": {
        "root": "limits",
        "description": "built-in: show configured runtime, history, and retention limits",
        "autocomplete": {"arguments": []},
    },
    "ps": {
        "root": "ps",
        "description": "built-in: show the current shell process view",
        "autocomplete": {
            "flags": [
                {"value": "aux", "description": "All processes with user and memory info"},
                {"value": "-ef", "description": "All processes, full format"},
            ]
        },
    },
    "retention": {
        "root": "retention",
        "description": "built-in: show retention and persisted-output settings",
        "autocomplete": {"arguments": []},
    },
    "runs": {
        "root": "runs",
        "description": "built-in: show active runs; use -v for details or --json for automation",
        "autocomplete": {
            "flags": [
                {"value": "-v", "description": "Show full IDs, started timestamps, and metadata source"},
                {"value": "--verbose", "description": "Show full IDs, started timestamps, and metadata source"},
                {"value": "--json", "description": "Print active-run metadata as JSON"},
            ]
        },
    },
    "stats": {
        "root": "stats",
        "description": "built-in: show session activity totals and command breakdowns",
        "autocomplete": {"arguments": []},
    },
    "status": {
        "root": "status",
        "description": "built-in: show the current session summary, limits, and backend health",
        "autocomplete": {"arguments": []},
    },
}


def builtin_command_specs() -> tuple[BuiltinCommandSpec, ...]:
    def runs_handler(command, context):
        return builtins_runtime.run_builtin_runs(
            command,
            context.session_id,
            split_command_argv,
            builtins_runtime.active_runs_for_session,
        )

    return (
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["history"],
            handler_key="history",
            handler=lambda _command, context: builtins_runtime.run_builtin_history(context.session_id),
            name="history",
            description="List command history from this session.",
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["jobs"],
            handler_key="jobs",
            handler=runs_handler,
            name="jobs",
            description="Alias for `runs`.",
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["last"],
            handler_key="last",
            handler=lambda _command, context: builtins_runtime.run_builtin_last(context.session_id),
            name="last",
            description=("Show recent completed runs with timestamps and exit codes."),
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["limits"],
            handler_key="limits",
            handler=lambda _command, _context: builtins_runtime.run_builtin_limits(),
            name="limits",
            description="Show configured runtime, history, and retention limits.",
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["ps"],
            handler_key="ps",
            handler=lambda command, context: builtins_runtime.run_builtin_ps(
                context.session_id,
                command,
                builtins_runtime.active_runs_for_session,
            ),
            name="ps",
            description=("Show the current shell process view plus recent session commands."),
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["retention"],
            handler_key="retention",
            handler=lambda _command, _context: builtins_runtime.run_builtin_retention(),
            name="retention",
            description="Show retention and persisted-output settings.",
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["runs"],
            handler_key="runs",
            handler=runs_handler,
            name="runs [-v|--json]",
            description="Show app-native active run metadata for this session.",
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["stats"],
            handler_key="stats",
            handler=lambda _command, context: builtins_runtime.run_builtin_stats(
                context.session_id,
                command_root,
                lambda: set(context.command_registry.roots()),
                builtins_runtime.active_runs_for_session,
            ),
            name="stats",
            description=("Show session activity totals and command-root breakdowns."),
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["status"],
            handler_key="status",
            handler=lambda _command, context: builtins_runtime.run_builtin_status(
                context.session_id,
                builtins_runtime.active_runs_for_session,
                builtins_runtime.redis_client,
            ),
            name="status",
            description=("Show the current session summary, limits, and backend health."),
        ),
    )
