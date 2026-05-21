"""
Built-in command handlers for common shell commands that should be useful in
the app without spawning a real process.
"""

from __future__ import annotations

import random
import re
import subprocess

from services.commands.registry import (
    command_root,
    load_all_faq,
    load_ascii_art,
    load_commands_registry,
    resolve_runtime_command,
    runtime_missing_command_name,
    split_command_argv,
)
from services.commands.builtins_catalog import (
    _BUILTIN_COMMANDS,
    _DOCUMENTED_BUILTIN_COMMANDS,
    _FORK_BOMB_RE,
    _SPECIAL_BUILTIN_COMMANDS,
    _WORKSPACE_ALIAS_ROOTS,
    _WORKSPACE_BUILTIN_ROOTS,
)
from services.commands import builtins_discovery, builtins_misc, builtins_system, builtins_wordlist
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
from services.commands.builtins_workspace import (
    parse_workspace_list_command as _parse_workspace_list_command,
    run_builtin_workspace as _run_builtin_workspace,
    run_builtin_workspace_alias as _run_builtin_workspace_alias,
)
from services.commands.builtins_wordlist import run_builtin_wordlist as _run_builtin_wordlist
from services.commands.wordlists import load_wordlist_catalog
from config import CFG
from core.process import active_runs_for_session, redis_client


_BACKSPACE_RE = re.compile(r".\x08")


def _sync_builtin_module_hooks() -> None:
    """Keep the aggregate module as the patch point for split built-in handlers."""
    builtins_discovery.CFG = CFG
    builtins_discovery.load_all_faq = load_all_faq
    builtins_discovery.resolve_runtime_command = resolve_runtime_command
    builtins_discovery.runtime_missing_command_name = runtime_missing_command_name
    builtins_discovery.subprocess = subprocess
    builtins_misc.CFG = CFG
    builtins_misc.random = random
    builtins_system.CFG = CFG
    builtins_wordlist.load_wordlist_catalog = load_wordlist_catalog


def _workspace_feature_enabled() -> bool:
    return bool(CFG.get("workspace_enabled", False))


def _tour_feature_enabled() -> bool:
    return bool(CFG.get("tour_enabled", True))


def _active_documented_builtin_commands() -> list[dict[str, object]]:
    commands: list[dict[str, object]] = [dict(entry) for entry in _DOCUMENTED_BUILTIN_COMMANDS]
    if not _workspace_feature_enabled():
        commands = [
            entry for entry in commands
            if str(entry.get("root") or "") not in _WORKSPACE_BUILTIN_ROOTS
        ]
    if not _tour_feature_enabled():
        commands = [
            entry for entry in commands
            if str(entry.get("root") or "") != "tour"
        ]
    return commands


def _active_builtin_command_roots() -> set[str]:
    roots = set(_BUILTIN_COMMANDS)
    if not _workspace_feature_enabled():
        roots -= _WORKSPACE_BUILTIN_ROOTS
    if not _tour_feature_enabled():
        roots.discard("tour")
    return roots


def _split_command(command: str) -> list[str]:
    # Built-in command routing keys off the first token only so "history --help"
    # resolves to the same built-in implementation as plain "history".
    return split_command_argv(command)


def _resolve_special_builtin_command(command: str) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized in _SPECIAL_BUILTIN_COMMANDS:
        return _SPECIAL_BUILTIN_COMMANDS[normalized]
    if _FORK_BOMB_RE.fullmatch(command.strip()):
        return "fork_bomb"
    return None


def _safe_workspace_alias_path(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw or raw.startswith("/") or "\\" in raw or "\x00" in raw:
        return False
    parts = raw.split("/")
    return all(part and part not in {".", ".."} and not part.startswith(".") for part in parts)


def _resolve_workspace_alias_command(parts: list[str]) -> str | None:
    if not parts:
        return None
    root = parts[0].lower()
    if root in {"ls", "ll"}:
        _long, _recursive, target, usage_error = _parse_workspace_list_command(parts)
        if usage_error:
            return None
        return root if not target or _safe_workspace_alias_path(target) else None
    if root in {"cat", "rm"}:
        return root if len(parts) == 2 and _safe_workspace_alias_path(parts[1]) else None
    if root == "mv":
        return root if len(parts) == 3 and all(_safe_workspace_alias_path(part) for part in parts[1:]) else None
    return None


def resolve_builtin_command(command: str) -> str | None:
    special = _resolve_special_builtin_command(command)
    if special is not None:
        return special
    parts = _split_command(command)
    if not parts:
        return None
    root = parts[0].lower()
    active_roots = _active_builtin_command_roots()
    if root in _WORKSPACE_ALIAS_ROOTS:
        if root not in active_roots:
            return None
        return _resolve_workspace_alias_command(parts)
    return root if root in active_roots else None


def resolves_exact_special_builtin_command(command: str) -> bool:
    return _resolve_special_builtin_command(command) is not None


def get_special_command_keys() -> list[str]:
    """Return the normalized exact-match keys for special built-in commands.

    The JS client uses this list to exempt these commands from the client-side
    shell-operator validation check before they reach the server.
    """
    return list(_SPECIAL_BUILTIN_COMMANDS.keys())


def get_builtin_command_roots() -> list[str]:
    """Return the command roots routed by the backend built-in command layer."""
    exact_roots: set[str] = set()
    for key in _SPECIAL_BUILTIN_COMMANDS:
        root = command_root(key)
        if root:
            if not _workspace_feature_enabled() and root in _WORKSPACE_ALIAS_ROOTS:
                continue
            exact_roots.add(root)
    return sorted(root for root in (_active_builtin_command_roots() | exact_roots) if root)


def get_current_shortcuts(is_mac: bool | None = None) -> dict:
    return _get_current_shortcuts(is_mac=is_mac)


def _run_builtin_runs(command: str, session_id: str) -> list[dict[str, object]]:
    return _run_builtin_runs_impl(command, session_id, _split_command, active_runs_for_session)


def _run_builtin_ps(session_id: str, command: str) -> list[dict[str, object]]:
    return _run_builtin_ps_impl(session_id, command, active_runs_for_session)


def _run_builtin_status(session_id: str) -> list[dict[str, object]]:
    return _run_builtin_status_impl(session_id, active_runs_for_session, redis_client)


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


_BUILTIN_COMMAND_DISPATCH = {
    "banner":    lambda cmd, sid: _run_builtin_banner(load_ascii_art),
    "cat":       lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "cd":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "clear":     lambda cmd, sid: _run_builtin_clear(),
    "commands":  lambda cmd, sid: _run_builtin_commands(cmd),
    "config":    lambda cmd, sid: _run_builtin_client_side_command("config"),
    "date":      lambda cmd, sid: _run_builtin_date(),
    "env":       lambda cmd, sid: _run_builtin_env(sid),
    "exit":      lambda cmd, sid: _run_builtin_client_side_command("exit"),
    "faq":       lambda cmd, sid: _run_builtin_faq(),
    "fortune":   lambda cmd, sid: _run_builtin_fortune(),
    "groups":    lambda cmd, sid: _run_builtin_groups(),
    "grep":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "head":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "help":      lambda cmd, sid: _run_builtin_help(),
    "history":   lambda cmd, sid: _run_builtin_history(sid),
    "hostname":  lambda cmd, sid: _run_builtin_hostname(),
    "id":        lambda cmd, sid: _run_builtin_id(),
    "ip_addr":   lambda cmd, sid: _run_builtin_ip_addr(),
    "intel":     lambda cmd, sid: _run_builtin_intel(cmd, sid),
    "jobs":      lambda cmd, sid: _run_builtin_runs(cmd, sid),
    "last":      lambda cmd, sid: _run_builtin_last(sid),
    "limits":    lambda cmd, sid: _run_builtin_limits(),
    "ll":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "ls":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "mkdir":     lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "mv":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "man":       lambda cmd, sid: _run_builtin_man(cmd),
    "providers": lambda cmd, sid: _run_builtin_secret("secret show-consumers", sid),
    "ps":        lambda cmd, sid: _run_builtin_ps(sid, cmd),
    "pwd":       lambda cmd, sid: _run_builtin_pwd(),
    "project":   lambda cmd, sid: _run_builtin_project(cmd, sid),
    "quit":      lambda cmd, sid: _run_builtin_client_side_command("quit"),
    "poweroff":  lambda cmd, sid: _run_builtin_poweroff(),
    "reboot":    lambda cmd, sid: _run_builtin_reboot(),
    "retention": lambda cmd, sid: _run_builtin_retention(),
    "rm":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "rm_root":   lambda cmd, sid: _run_builtin_rm_root(),
    "route":     lambda cmd, sid: _run_builtin_route(),
    "runs":      lambda cmd, sid: _run_builtin_runs(cmd, sid),
    "schedule":  lambda cmd, sid: _run_builtin_schedule(cmd, sid),
    "secret":    lambda cmd, sid: _run_builtin_secret(cmd, sid),
    "session-token": lambda cmd, sid: _run_builtin_session_token(cmd, sid),
    "shortcuts": lambda cmd, sid: _run_builtin_shortcuts(),
    "sort":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "stats":     lambda cmd, sid: _run_builtin_stats(sid),
    "status":    lambda cmd, sid: _run_builtin_status(sid),
    "tail":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "sudo":      lambda cmd, sid: _run_builtin_sudo(cmd),
    "su_shell":  lambda cmd, sid: _run_builtin_su(cmd),
    "theme":     lambda cmd, sid: _run_builtin_client_side_command("theme"),
    "tour":      lambda cmd, sid: _run_builtin_client_side_command("tour"),
    "tty":       lambda cmd, sid: _run_builtin_tty(),
    "type":      lambda cmd, sid: _run_builtin_type(cmd),
    "uname":     lambda cmd, sid: _run_builtin_uname(cmd, _split_command),
    "uptime":    lambda cmd, sid: _run_builtin_uptime(),
    "uniq":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "var":       lambda cmd, sid: _run_builtin_var(cmd, sid),
    "version":   lambda cmd, sid: _run_builtin_version(),
    "watch":     lambda cmd, sid: _run_builtin_watch(cmd, sid),
    "file":      lambda cmd, sid: _run_builtin_workspace(cmd, sid),
    "wc":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "which":     lambda cmd, sid: _run_builtin_which(cmd),
    "who":       lambda cmd, sid: _run_builtin_who(sid),
    "whoami":    lambda cmd, sid: _run_builtin_whoami(),
    "wordlist":  lambda cmd, sid: _run_builtin_wordlist(cmd),
    "workflow":  lambda cmd, sid: _run_builtin_client_side_command("workflow"),
    "xyzzy":     lambda cmd, sid: _run_builtin_xyzzy(),
    "coffee":    lambda cmd, sid: _run_builtin_coffee(),
    "fork_bomb": lambda cmd, sid: _run_builtin_fork_bomb(),
    "df":        lambda cmd, sid: _run_builtin_df(cmd),
    "free":      lambda cmd, sid: _run_builtin_free(cmd),
}


def execute_builtin_command(command: str, session_id: str, *, tab_id: str = "") -> tuple[list[dict[str, object]], int]:
    # Built-in commands still return the same [{text, class}, ...], exit_code shape
    # as real runs so the frontend path is identical.
    _sync_builtin_module_hooks()
    root = resolve_builtin_command(command)
    handler = _BUILTIN_COMMAND_DISPATCH.get(root) if root is not None else None
    if handler is None:
        return [{"type": "output", "text": f"Unsupported built-in command: {command.strip()}"}], 1
    if root == "project":
        result = _run_builtin_project(command, session_id, tab_id=tab_id)
        return result, 0
    result = handler(command, session_id)
    if isinstance(result, tuple):
        return result
    return result, 0
