# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Built-in command handlers for common shell commands that should be useful in
the app without spawning a real process.
"""

from __future__ import annotations

import random
import subprocess
from collections.abc import Sequence

import core.process as process_state
from core.process import active_runs_for_session
from services.commands import (
    builtin_providers,
    builtins_discovery,
    builtins_misc,
    builtins_runtime,
    builtins_wordlist,
    builtins_workspace,
)
from services.commands.builtin_registry import BuiltinExecutionContext
from services.commands.builtins_runtime import (
    run_builtin_ps as _run_builtin_ps_impl,
    run_builtin_runs as _run_builtin_runs_impl,
    run_builtin_stats as _run_builtin_stats_impl,
    run_builtin_status as _run_builtin_status_impl,
)
from services.commands.builtins_shortcuts import (
    get_current_shortcuts as _get_current_shortcuts,
)
from services.commands.registry import (
    command_root,
    load_all_faq,
    load_ascii_art,
    load_commands_registry,
    resolve_runtime_command,
    runtime_missing_command_name,
    split_command_argv,
)
from services.commands.wordlists import load_wordlist_catalog
from services.teams.scope import OwnerContext


def _sync_builtin_module_hooks() -> None:
    """Keep the aggregate module as the patch point for split built-in handlers."""
    builtins_discovery.load_all_faq = load_all_faq
    builtins_discovery.load_commands_registry = load_commands_registry
    builtins_discovery.resolve_runtime_command = resolve_runtime_command
    builtins_discovery.runtime_missing_command_name = runtime_missing_command_name
    builtins_discovery.subprocess = subprocess
    builtins_misc.load_ascii_art = load_ascii_art
    builtins_misc.random = random
    builtins_runtime.active_runs_for_session = active_runs_for_session
    builtins_runtime.redis_client = process_state.redis_client
    builtins_wordlist.load_wordlist_catalog = load_wordlist_catalog


def _active_documented_builtin_commands() -> list[dict[str, object]]:
    return _BUILTIN_REGISTRY.documented_commands()


def _active_builtin_command_roots() -> set[str]:
    return set(_BUILTIN_REGISTRY.roots())


def _split_command(command: str) -> list[str]:
    # Built-in command routing keys off the first token only so "history --help"
    # resolves to the same built-in implementation as plain "history".
    return split_command_argv(command)


def _resolve_special_builtin_command(command: str) -> str | None:
    resolution = _BUILTIN_REGISTRY.resolve_exact(command)
    return resolution.handler_key if resolution is not None else None


def _resolve_workspace_alias_command(parts: Sequence[str]) -> str | None:
    if not builtins_workspace.resolves_workspace_alias_command(parts):
        return None
    return parts[0].lower()


def resolve_builtin_command(command: str) -> str | None:
    resolution = _BUILTIN_REGISTRY.resolve(command)
    return resolution.handler_key if resolution is not None else None


def resolves_exact_special_builtin_command(command: str) -> bool:
    return _resolve_special_builtin_command(command) is not None


def get_special_command_keys() -> list[str]:
    """Return the normalized exact-match keys for special built-in commands.

    The JS client uses this list to exempt these commands from the client-side
    shell-operator validation check before they reach the server.
    """
    return list(_BUILTIN_REGISTRY.exact_aliases())


def get_builtin_command_roots() -> list[str]:
    """Return the command roots routed by the backend built-in command layer."""
    return list(_BUILTIN_REGISTRY.roots(include_exact_alias_roots=True))


def get_registered_builtin_command_roots() -> tuple[str, ...]:
    """Return every configured helper root for feature-independent storage use."""
    return _BUILTIN_REGISTRY.registered_roots(include_exact_alias_roots=True)


def get_builtin_autocomplete_context(cfg=None) -> dict[str, dict[str, object]]:
    """Return complete app-owned autocomplete metadata from helper specs."""
    return _BUILTIN_REGISTRY.autocomplete_context(cfg=cfg)


def get_builtin_command_catalog(cfg=None) -> list[dict[str, object]]:
    """Return rich discovery metadata for registered app-owned helpers."""
    return _BUILTIN_REGISTRY.catalog(cfg=cfg)


def get_builtin_command_catalog_entry(
    root: str,
    subcommand: str | None = None,
    cfg=None,
) -> dict[str, object] | None:
    """Return one rich app-owned helper catalog entry."""
    return _BUILTIN_REGISTRY.catalog_entry(root, subcommand, cfg=cfg)


def get_current_shortcuts(is_mac: bool | None = None) -> dict:
    return _get_current_shortcuts(is_mac=is_mac)


def _run_builtin_runs(command: str, session_id: str) -> list[dict[str, object]]:
    return _run_builtin_runs_impl(command, session_id, _split_command, active_runs_for_session)


def _run_builtin_ps(session_id: str, command: str) -> list[dict[str, object]]:
    return _run_builtin_ps_impl(session_id, command, active_runs_for_session)


def _run_builtin_status(session_id: str) -> list[dict[str, object]]:
    return _run_builtin_status_impl(session_id, active_runs_for_session, process_state.redis_client)


def _run_builtin_stats(session_id: str) -> list[dict[str, object]]:
    return _run_builtin_stats_impl(
        session_id,
        command_root,
        _active_builtin_command_roots,
        active_runs_for_session,
    )


def _documented_builtin_rows() -> list[tuple[str, str]]:
    return builtins_discovery.documented_builtin_rows(_active_documented_builtin_commands)


def _run_builtin_help() -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_help()


def _run_builtin_commands(command: str) -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_commands(
        command,
        _split_command,
        _active_documented_builtin_commands,
        load_commands_registry,
        get_builtin_command_catalog,
        get_builtin_command_catalog_entry,
    )


def _run_builtin_client_side_command(name: str) -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_client_side_command(name)


def _run_builtin_faq() -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_faq()


def _run_builtin_man(command: str) -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_man(
        command,
        _split_command,
        _active_builtin_command_roots,
        _documented_builtin_rows,
    )


def _run_builtin_type(command: str) -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_type(command, _split_command, _active_builtin_command_roots)


def _run_builtin_which(command: str) -> list[dict[str, object]]:
    return builtins_discovery.run_builtin_which(command, _split_command, _active_builtin_command_roots)


_BUILTIN_REGISTRY = builtin_providers.build_builtin_registry()


def execute_builtin_command(
    command: str,
    session_id: str,
    *,
    tab_id: str = "",
    team_id: str = "",
    team_role: str = "",
    owner_context: OwnerContext | None = None,
) -> tuple[list[dict[str, object]], int]:
    # Built-in commands still return the same line-event plus exit-code shape as
    # real runs so the frontend path is identical.
    _sync_builtin_module_hooks()
    return _BUILTIN_REGISTRY.execute(
        command,
        BuiltinExecutionContext(
            session_id=session_id,
            tab_id=tab_id,
            team_id=team_id,
            team_role=team_role,
            supplied_owner_context=owner_context,
        ),
    )
