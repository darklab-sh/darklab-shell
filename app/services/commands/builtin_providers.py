# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed provider list for app-owned helper commands."""

from __future__ import annotations

from services.commands import (
    builtins_client,
    builtins_discovery,
    builtins_intel,
    builtins_misc,
    builtins_notify,
    builtins_project,
    builtins_runtime_specs,
    builtins_schedule,
    builtins_secrets,
    builtins_session,
    builtins_shortcuts,
    builtins_system,
    builtins_team,
    builtins_watch,
    builtins_wordlist,
    builtins_workspace,
)
from services.commands.builtin_registry import (
    BuiltinCommandProvider,
    BuiltinCommandRegistry,
)


BUILTIN_COMMAND_PROVIDERS: tuple[BuiltinCommandProvider, ...] = (
    builtins_client.builtin_command_specs,
    builtins_discovery.builtin_command_specs,
    builtins_intel.builtin_command_specs,
    builtins_misc.builtin_command_specs,
    builtins_notify.builtin_command_specs,
    builtins_project.builtin_command_specs,
    builtins_runtime_specs.builtin_command_specs,
    builtins_schedule.builtin_command_specs,
    builtins_secrets.builtin_command_specs,
    builtins_session.builtin_command_specs,
    builtins_shortcuts.builtin_command_specs,
    builtins_system.builtin_command_specs,
    builtins_team.builtin_command_specs,
    builtins_watch.builtin_command_specs,
    builtins_wordlist.builtin_command_specs,
    builtins_workspace.builtin_command_specs,
)


def build_builtin_registry() -> BuiltinCommandRegistry:
    registry = BuiltinCommandRegistry(
        workspace_alias_validator=(builtins_workspace.resolves_workspace_alias_command),
        fork_bomb_matcher=lambda command: builtins_misc.FORK_BOMB_RE.fullmatch(command.strip()) is not None,
    )
    for provider in BUILTIN_COMMAND_PROVIDERS:
        registry.register_provider(provider)
    return registry.freeze()
