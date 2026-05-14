"""Encrypted secrets built-in command handlers."""

from __future__ import annotations

from collections import defaultdict

from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import load_commands_registry, split_command_argv
from services.secrets.storage import InvalidSecretName, delete_secret, list_secret_metadata, normalize_secret_name
from services.secrets.vault import MasterKeyError, SecretDecryptError


def _secret_usage() -> list[dict[str, str]]:
    return [
        output_line("Secret commands:", "builtin-section"),
        output_line("  secret set NAME", "builtin-help-row"),
        output_line("  secret list", "builtin-help-row"),
        output_line("  secret unset NAME", "builtin-help-row"),
        output_line("  secret show-consumers", "builtin-help-row"),
        output_line("Values are entered through the browser prompt and are never shown in the transcript.", "builtin-note"),
    ]


def _secret_consumer_map() -> dict[str, list[str]]:
    registry = load_commands_registry()
    consumers: dict[str, list[str]] = defaultdict(list)
    for command in registry.get("commands", []):
        root = str(command.get("root") or "").strip()
        if not root:
            continue
        for item in command.get("requires_secrets") or []:
            env = str(item.get("env") or "").strip().upper()
            fallback_envs = [
                str(fallback or "").strip().upper()
                for fallback in item.get("fallback_envs", []) or []
                if str(fallback or "").strip()
            ]
            requirement = "optional" if bool(item.get("optional", False)) else "required"
            for env_name in [env, *fallback_envs]:
                if env_name:
                    consumers[env_name].append(f"{root} ({requirement})")
    return {env: sorted(set(roots)) for env, roots in consumers.items()}


def run_builtin_secret(command: str, session_id: str) -> list[dict[str, str]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"

    if subcommand in {"help", "-h", "--help"}:
        return _secret_usage()

    if subcommand == "list":
        try:
            rows = list_secret_metadata(session_id)
        except (MasterKeyError, SecretDecryptError) as exc:
            return [output_line(f"secret: {exc}")]
        if not rows:
            return [output_line("No secrets stored for this session.", "builtin-note")]
        lines = [output_line("Stored secrets:", "builtin-section")]
        for row in rows:
            envs = ", ".join(row.get("consumer_envs") or [])
            lines.append(output_line(format_native_record(str(row.get("name") or ""), envs, 22), "builtin-kv"))
        return lines

    if subcommand == "set":
        if len(parts) != 3:
            return [
                output_line("Usage: secret set NAME"),
                output_line("Do not put the value on the command line. The browser prompt collects it safely.", "builtin-note"),
            ]
        try:
            name = normalize_secret_name(parts[2])
        except InvalidSecretName as exc:
            return [output_line(f"secret: {exc}")]
        return [
            output_line(f"Ready to store {name}.", "builtin-success"),
            output_line("Open the Options > Secrets panel to enter or replace the value.", "builtin-note"),
        ]

    if subcommand in {"unset", "delete", "rm"}:
        if len(parts) != 3:
            return [output_line("Usage: secret unset NAME")]
        try:
            name = normalize_secret_name(parts[2])
            removed = delete_secret(session_id, name)
        except (InvalidSecretName, MasterKeyError, SecretDecryptError) as exc:
            return [output_line(f"secret: {exc}")]
        if removed:
            return [output_line(f"{name} removed.", "builtin-success")]
        return [output_line(f"{name} was not set.", "builtin-note")]

    if subcommand == "show-consumers":
        consumers = _secret_consumer_map()
        if not consumers:
            return [output_line("No command registry secret consumers are configured.", "builtin-note")]
        lines = [output_line("Command registry secret consumers:", "builtin-section")]
        for env, roots in sorted(consumers.items()):
            lines.append(output_line(format_native_record(env, ", ".join(roots), 22), "builtin-kv"))
        return lines

    return [
        output_line(f"secret: unknown subcommand '{subcommand}'"),
        *_secret_usage(),
    ]
