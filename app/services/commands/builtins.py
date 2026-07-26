# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Built-in command handlers for common shell commands that should be useful in
the app without spawning a real process.
"""

from __future__ import annotations

import random
import re
import subprocess
from collections import defaultdict
from collections.abc import Callable, Sequence

from services.commands.registry import (
    command_root,
    load_all_faq,
    load_ascii_art,
    load_builtin_autocomplete_registry,
    load_commands_registry,
    resolve_runtime_command,
    runtime_missing_command_name,
    split_command_argv,
)
from services.commands.builtin_registry import (
    BuiltinCommandRegistry,
    BuiltinCommandSpec,
    BuiltinExecutionContext,
    BuiltinExecutionOwner,
    BuiltinHandler,
    BuiltinMatchStrategy,
)
from services.commands.features import feature_enabled
from services.commands.builtins_catalog import (
    _BUILTIN_COMMANDS,
    _DOCUMENTED_BUILTIN_COMMANDS,
    _FORK_BOMB_RE,
    _SPECIAL_BUILTIN_COMMANDS,
    _WORKSPACE_ALIAS_ROOTS,
    _WORKSPACE_BUILTIN_ROOTS,
)
from services.commands import builtins_discovery, builtins_misc, builtins_wordlist
from services.commands.builtins_intel import run_builtin_intel as _run_builtin_intel
from services.commands.builtins_misc import (
    run_builtin_banner as _run_builtin_banner,
    run_builtin_clear as _run_builtin_clear,
    run_builtin_coffee as _run_builtin_coffee,
    run_builtin_fork_bomb as _run_builtin_fork_bomb,
    run_builtin_fortune as _run_builtin_fortune,
    run_builtin_groups as _run_builtin_groups,
    run_builtin_poweroff as _run_builtin_poweroff,
    run_builtin_reboot as _run_builtin_reboot,
    run_builtin_rm_root as _run_builtin_rm_root,
    run_builtin_su as _run_builtin_su,
    run_builtin_sudo as _run_builtin_sudo,
    run_builtin_xyzzy as _run_builtin_xyzzy,
)
from services.commands.builtins_notify import run_builtin_notify as _run_builtin_notify
from services.commands.builtins_project import run_builtin_project as _run_builtin_project
from services.commands.builtins_runtime import (
    run_builtin_history as _run_builtin_history,
    run_builtin_last as _run_builtin_last,
    run_builtin_limits as _run_builtin_limits,
    run_builtin_ps as _run_builtin_ps_impl,
    run_builtin_retention as _run_builtin_retention,
    run_builtin_runs as _run_builtin_runs_impl,
    run_builtin_stats as _run_builtin_stats_impl,
    run_builtin_status as _run_builtin_status_impl,
)
from services.commands.builtins_schedule import run_builtin_schedule as _run_builtin_schedule
from services.commands.builtins_session import (
    run_builtin_session_token as _run_builtin_session_token,
    run_builtin_var as _run_builtin_var,
)
from services.commands.builtins_secrets import run_builtin_secret as _run_builtin_secret
from services.commands.builtins_watch import run_builtin_watch as _run_builtin_watch
from services.commands.builtins_shortcuts import (
    get_current_shortcuts as _get_current_shortcuts,
    run_builtin_shortcuts as _run_builtin_shortcuts,
)
from services.commands.builtins_system import (
    run_builtin_date as _run_builtin_date,
    run_builtin_df as _run_builtin_df,
    run_builtin_env as _run_builtin_env,
    run_builtin_free as _run_builtin_free,
    run_builtin_hostname as _run_builtin_hostname,
    run_builtin_id as _run_builtin_id,
    run_builtin_ip_addr as _run_builtin_ip_addr,
    run_builtin_pwd as _run_builtin_pwd,
    run_builtin_route as _run_builtin_route,
    run_builtin_tty as _run_builtin_tty,
    run_builtin_uname as _run_builtin_uname,
    run_builtin_uptime as _run_builtin_uptime,
    run_builtin_version as _run_builtin_version,
    run_builtin_who as _run_builtin_who,
    run_builtin_whoami as _run_builtin_whoami,
)
from services.commands.builtins_team import run_builtin_team as _run_builtin_team
from services.commands.builtins_workspace import (
    parse_workspace_list_command as _parse_workspace_list_command,
    run_builtin_diff as _run_builtin_diff,
    run_builtin_workspace as _run_builtin_workspace,
    run_builtin_workspace_alias as _run_builtin_workspace_alias,
)
from services.commands.builtins_wordlist import run_builtin_wordlist as _run_builtin_wordlist
from services.commands.wordlists import load_wordlist_catalog
from services.teams.scope import OwnerContext
import core.process as process_state
from core.process import active_runs_for_session


_BACKSPACE_RE = re.compile(r".\x08")


def _sync_builtin_module_hooks() -> None:
    """Keep the aggregate module as the patch point for split built-in handlers."""
    builtins_discovery.load_all_faq = load_all_faq
    builtins_discovery.resolve_runtime_command = resolve_runtime_command
    builtins_discovery.runtime_missing_command_name = runtime_missing_command_name
    builtins_discovery.subprocess = subprocess
    builtins_misc.random = random
    builtins_wordlist.load_wordlist_catalog = load_wordlist_catalog


def _active_documented_builtin_commands() -> list[dict[str, object]]:
    commands: list[dict[str, object]] = []
    for entry in _DOCUMENTED_BUILTIN_COMMANDS:
        handler_key = str(entry.get("root") or "").strip()
        if not handler_key:
            handler_key = _SPECIAL_BUILTIN_COMMANDS.get(
                " ".join(str(entry.get("exact") or "").strip().lower().split()),
                "",
            )
        spec = _BUILTIN_REGISTRY.spec_for_key(handler_key)
        if spec is None:
            continue
        if not all(feature_enabled(feature) for feature in spec.feature_required):
            continue
        commands.append(dict(entry))
    return commands


def _active_builtin_command_roots() -> set[str]:
    return set(_BUILTIN_REGISTRY.roots())


def _split_command(command: str) -> list[str]:
    # Built-in command routing keys off the first token only so "history --help"
    # resolves to the same built-in implementation as plain "history".
    return split_command_argv(command)


def _resolve_special_builtin_command(command: str) -> str | None:
    resolution = _BUILTIN_REGISTRY.resolve_exact(command)
    return resolution.handler_key if resolution is not None else None


def _safe_workspace_alias_path(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw or raw.startswith("/") or "\\" in raw or "\x00" in raw:
        return False
    parts = raw.split("/")
    return all(part and part not in {".", ".."} and not part.startswith(".") for part in parts)


def _resolve_workspace_alias_command(parts: Sequence[str]) -> str | None:
    if not parts:
        return None
    root = parts[0].lower()
    if root in {"ls", "ll"}:
        _long, _recursive, target, usage_error = _parse_workspace_list_command(list(parts))
        if usage_error:
            return None
        return root if not target or _safe_workspace_alias_path(target) else None
    if root in {"cat", "rm", "touch"}:
        return root if len(parts) == 2 and _safe_workspace_alias_path(parts[1]) else None
    if root in {"cp", "mv"}:
        return root if len(parts) == 3 and all(_safe_workspace_alias_path(part) for part in parts[1:]) else None
    return None


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


def _builtin_handlers() -> dict[str, BuiltinHandler]:
    def workspace_alias(
        cmd: str,
        context: BuiltinExecutionContext,
    ) -> list[dict[str, object]]:
        return _run_builtin_workspace_alias(
            cmd,
            context.session_id,
            owner_context=context.owner_context,
            team_role=context.team_role,
            tab_id=context.tab_id,
        )

    return {
        "banner":    lambda cmd, context: _run_builtin_banner(load_ascii_art),
        "cat":       workspace_alias,
        "cp":        workspace_alias,
        "cd":        workspace_alias,
        "clear":     lambda cmd, context: _run_builtin_clear(),
        "commands":  lambda cmd, context: _run_builtin_commands(cmd),
        "config":    lambda cmd, context: _run_builtin_client_side_command("config"),
        "date":      lambda cmd, context: _run_builtin_date(),
        "diff":      lambda cmd, context: _run_builtin_diff(
            _split_command(cmd),
            context.owner_context,
            context.effective_cfg,
            tab_id=context.tab_id,
        ),
        "env":       lambda cmd, context: _run_builtin_env(context.session_id),
        "exit":      lambda cmd, context: _run_builtin_client_side_command("exit"),
        "faq":       lambda cmd, context: _run_builtin_faq(),
        "fortune":   lambda cmd, context: _run_builtin_fortune(),
        "groups":    lambda cmd, context: _run_builtin_groups(),
        "grep":      workspace_alias,
        "head":      workspace_alias,
        "help":      lambda cmd, context: _run_builtin_help(),
        "history":   lambda cmd, context: _run_builtin_history(context.session_id),
        "hostname":  lambda cmd, context: _run_builtin_hostname(),
        "id":        lambda cmd, context: _run_builtin_id(),
        "ip_addr":   lambda cmd, context: _run_builtin_ip_addr(),
        "intel":     lambda cmd, context: _run_builtin_intel(
            cmd,
            context.session_id,
            team_id=context.team_id,
        ),
        "jobs":      lambda cmd, context: _run_builtin_runs(cmd, context.session_id),
        "last":      lambda cmd, context: _run_builtin_last(context.session_id),
        "limits":    lambda cmd, context: _run_builtin_limits(),
        "ll":        workspace_alias,
        "ls":        workspace_alias,
        "mkdir":     workspace_alias,
        "mv":        workspace_alias,
        "man":       lambda cmd, context: _run_builtin_man(cmd),
        "notify":    lambda cmd, context: _run_builtin_notify(
            cmd,
            context.session_id,
            team_id=context.team_id,
            team_role=context.team_role,
        ),
        "providers": lambda cmd, context: _run_builtin_secret(
            "secret show-consumers",
            context.session_id,
            team_id=context.team_id,
            team_role=context.team_role,
        ),
        "ps":        lambda cmd, context: _run_builtin_ps(context.session_id, cmd),
        "pwd":       lambda cmd, context: _run_builtin_pwd(),
        "project":   lambda cmd, context: _run_builtin_project(
            cmd,
            context.session_id,
            tab_id=context.tab_id,
        ),
        "quit":      lambda cmd, context: _run_builtin_client_side_command("quit"),
        "poweroff":  lambda cmd, context: _run_builtin_poweroff(),
        "reboot":    lambda cmd, context: _run_builtin_reboot(),
        "retention": lambda cmd, context: _run_builtin_retention(),
        "rm":        workspace_alias,
        "rm_root":   lambda cmd, context: _run_builtin_rm_root(),
        "route":     lambda cmd, context: _run_builtin_route(),
        "runs":      lambda cmd, context: _run_builtin_runs(cmd, context.session_id),
        "schedule":  lambda cmd, context: _run_builtin_schedule(cmd, context.session_id),
        "secret":    lambda cmd, context: _run_builtin_secret(
            cmd,
            context.session_id,
            team_id=context.team_id,
            team_role=context.team_role,
        ),
        "session-token": lambda cmd, context: _run_builtin_session_token(
            cmd,
            context.session_id,
        ),
        "shortcuts": lambda cmd, context: _run_builtin_shortcuts(),
        "sort":      workspace_alias,
        "stats":     lambda cmd, context: _run_builtin_stats(context.session_id),
        "status":    lambda cmd, context: _run_builtin_status(context.session_id),
        "tail":      workspace_alias,
        "touch":     workspace_alias,
        "team":      lambda cmd, context: _run_builtin_team(
            cmd,
            context.session_id,
            team_id=context.team_id,
            team_role=context.team_role,
        ),
        "sudo":      lambda cmd, context: _run_builtin_sudo(cmd),
        "su_shell":  lambda cmd, context: _run_builtin_su(cmd),
        "theme":     lambda cmd, context: _run_builtin_client_side_command("theme"),
        "tour":      lambda cmd, context: _run_builtin_client_side_command("tour"),
        "tty":       lambda cmd, context: _run_builtin_tty(),
        "type":      lambda cmd, context: _run_builtin_type(cmd),
        "uname":     lambda cmd, context: _run_builtin_uname(cmd, _split_command),
        "uptime":    lambda cmd, context: _run_builtin_uptime(),
        "uniq":      workspace_alias,
        "var":       lambda cmd, context: _run_builtin_var(cmd, context.session_id),
        "version":   lambda cmd, context: _run_builtin_version(),
        "watch":     lambda cmd, context: _run_builtin_watch(cmd, context.session_id),
        "file":      lambda cmd, context: _run_builtin_workspace(
            cmd,
            context.session_id,
            owner_context=context.owner_context,
            team_role=context.team_role,
            tab_id=context.tab_id,
        ),
        "wc":        workspace_alias,
        "which":     lambda cmd, context: _run_builtin_which(cmd),
        "who":       lambda cmd, context: _run_builtin_who(context.session_id),
        "whoami":    lambda cmd, context: _run_builtin_whoami(),
        "wordlist":  lambda cmd, context: _run_builtin_wordlist(cmd),
        "workflow":  lambda cmd, context: _run_builtin_client_side_command("workflow"),
        "xyzzy":     lambda cmd, context: _run_builtin_xyzzy(),
        "coffee":    lambda cmd, context: _run_builtin_coffee(),
        "fork_bomb": lambda cmd, context: _run_builtin_fork_bomb(),
        "df":        lambda cmd, context: _run_builtin_df(cmd),
        "free":      lambda cmd, context: _run_builtin_free(cmd),
    }


def _builtin_execution_owner(handler_key: str) -> tuple[
    BuiltinExecutionOwner,
    tuple[str, ...],
    bool,
]:
    if handler_key in {"config", "exit", "quit", "theme", "tour", "workflow"}:
        return BuiltinExecutionOwner.BROWSER, (), True
    if handler_key == "secret":
        return BuiltinExecutionOwner.MIXED, ("set",), False
    if handler_key == "session-token":
        return BuiltinExecutionOwner.MIXED, ("*",), False
    if handler_key in _WORKSPACE_BUILTIN_ROOTS:
        return BuiltinExecutionOwner.MIXED, ("*",), False
    return BuiltinExecutionOwner.SERVER, (), False


def _build_builtin_registry() -> BuiltinCommandRegistry:
    registry = BuiltinCommandRegistry(
        workspace_alias_validator=lambda parts: _resolve_workspace_alias_command(parts) is not None,
        fork_bomb_matcher=lambda command: _FORK_BOMB_RE.fullmatch(command.strip()) is not None,
    )
    documented_by_root = {
        str(entry.get("root") or "").strip(): entry
        for entry in _DOCUMENTED_BUILTIN_COMMANDS
        if entry.get("root")
    }
    documented_by_exact = {
        " ".join(str(entry.get("exact") or "").strip().lower().split()): entry
        for entry in _DOCUMENTED_BUILTIN_COMMANDS
        if entry.get("exact")
    }
    autocomplete_entries = {
        str(entry.get("root") or "").strip().lower(): entry
        for entry in load_builtin_autocomplete_registry().get("commands", [])
        if isinstance(entry, dict) and entry.get("root")
    }
    aliases_by_handler: defaultdict[str, list[str]] = defaultdict(list)
    for alias, handler_key in _SPECIAL_BUILTIN_COMMANDS.items():
        aliases_by_handler[handler_key].append(alias)

    for handler_key, handler in _builtin_handlers().items():
        documented = documented_by_root.get(handler_key)
        if documented is None:
            documented = next(
                (
                    documented_by_exact[alias]
                    for alias in aliases_by_handler.get(handler_key, [])
                    if alias in documented_by_exact
                ),
                None,
            )
        execution_owner, browser_subcommands, fallback_stub = _builtin_execution_owner(
            handler_key
        )
        match_strategy = BuiltinMatchStrategy.ROOT
        if handler_key in _WORKSPACE_ALIAS_ROOTS:
            match_strategy = BuiltinMatchStrategy.WORKSPACE_ALIAS
        elif handler_key == "fork_bomb":
            match_strategy = BuiltinMatchStrategy.FORK_BOMB
        autocomplete_root = "ip" if handler_key == "ip_addr" else (
            handler_key if handler_key in autocomplete_entries else ""
        )
        raw_autocomplete = autocomplete_entries.get(
            autocomplete_root,
            {},
        ).get("autocomplete")
        autocomplete = raw_autocomplete if isinstance(raw_autocomplete, dict) else {}
        registry.register(BuiltinCommandSpec(
            handler_key=handler_key,
            handler=handler,
            name=str(documented.get("name") or handler_key) if documented else handler_key,
            description=str(documented.get("description") or "") if documented else "",
            root=handler_key if handler_key in _BUILTIN_COMMANDS else "",
            autocomplete_root=autocomplete_root,
            autocomplete_description=str(
                autocomplete_entries.get(autocomplete_root, {}).get("description") or ""
            ),
            exact_aliases=tuple(aliases_by_handler.get(handler_key, [])),
            feature_required=("workspace",) if handler_key in _WORKSPACE_BUILTIN_ROOTS else (
                ("tour",) if handler_key == "tour" else ()
            ),
            execution_owner=execution_owner,
            browser_owned_subcommands=browser_subcommands,
            browser_fallback_stub=fallback_stub,
            match_strategy=match_strategy,
            autocomplete=autocomplete,
            user_facing=documented is not None,
        ))
    return registry.freeze()


_BUILTIN_REGISTRY = _build_builtin_registry()


def _legacy_builtin_handler(spec: BuiltinCommandSpec) -> Callable[[str, str], object]:
    return lambda command, session_id: spec.handler(
        command,
        BuiltinExecutionContext(session_id=session_id),
    )


_BUILTIN_COMMAND_DISPATCH = {
    spec.handler_key: _legacy_builtin_handler(spec)
    for spec in _BUILTIN_REGISTRY.specs()
}


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
