# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Catalog stubs for commands whose user-facing execution belongs to the browser."""

from __future__ import annotations

from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    BuiltinExecutionOwner,
    build_builtin_command_spec,
)
from services.commands.builtins_discovery import run_builtin_client_side_command


_BUILTIN_AUTOCOMPLETE = {
    "config": {
        "root": "config",
        "description": "built-in: show or update user options",
        "autocomplete": {
            "subcommands": [
                {"value": "list", "description": "Show all current user config", "closes": True},
                {"value": "get", "description": "Show one user config value", "takes_value": True, "insert": "get "},
                {"value": "set", "description": "Set one user config value", "takes_value": True, "insert": "set "},
            ]
        },
    },
    "exit": {"root": "exit", "description": "built-in: close the current tab", "autocomplete": {"arguments": []}},
    "quit": {"root": "quit", "description": "built-in: close the current tab", "autocomplete": {"arguments": []}},
    "theme": {
        "root": "theme",
        "description": "built-in: show or apply the active shell theme",
        "autocomplete": {
            "subcommands": [
                {"value": "list", "description": "Show available themes", "closes": True},
                {"value": "current", "description": "Show the active theme", "closes": True},
                {"value": "set", "description": "Apply a theme", "takes_value": True, "insert": "set "},
            ]
        },
    },
    "tour": {
        "root": "tour",
        "description": "built-in: print the onboarding tour inside the terminal",
        "feature_required": "tour",
        "autocomplete": {"subcommands": [{"value": "help", "description": "Show tour command usage", "closes": True}]},
    },
    "workflow": {
        "root": "workflow",
        "description": "built-in: list, inspect, and run guided workflows",
        "autocomplete": {
            "subcommands": [
                {"value": "list", "description": "List workflows", "closes": True},
                {
                    "value": "show",
                    "description": "Show workflow steps",
                    "takes_value": True,
                    "insert": "show ",
                    "value_hint": {"value": "<workflow>", "hint_only": True, "description": "Workflow name"},
                },
                {
                    "value": "run",
                    "description": "Run a workflow",
                    "takes_value": True,
                    "insert": "run ",
                    "value_hint": {"value": "<workflow>", "hint_only": True, "description": "Workflow name"},
                },
            ]
        },
    },
}


def _browser_spec(
    root: str,
    *,
    name: str,
    description: str,
) -> BuiltinCommandSpec:
    return build_builtin_command_spec(
        _BUILTIN_AUTOCOMPLETE[root],
        handler_key=root,
        handler=lambda _command, _context: run_builtin_client_side_command(root),
        name=name,
        description=description,
        execution_owner=BuiltinExecutionOwner.BROWSER,
        browser_fallback_stub=True,
    )


def builtin_command_specs() -> tuple[BuiltinCommandSpec, ...]:
    return (
        _browser_spec(
            "config",
            name="config",
            description="Show or update user options from the terminal.",
        ),
        _browser_spec(
            "exit",
            name="exit",
            description="Close the current tab.",
        ),
        _browser_spec(
            "quit",
            name="quit",
            description="Alias for `exit`.",
        ),
        _browser_spec(
            "theme",
            name="theme",
            description="Show or apply the active shell theme from the terminal.",
        ),
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["tour"],
            handler_key="tour",
            handler=lambda _command, _context: run_builtin_client_side_command("tour"),
            name="tour",
            description="Print the onboarding tour inside the terminal.",
            execution_owner=BuiltinExecutionOwner.BROWSER,
            browser_fallback_stub=True,
        ),
        _browser_spec(
            "workflow",
            name="workflow",
            description="List, inspect, and run guided workflows from the terminal.",
        ),
    )
