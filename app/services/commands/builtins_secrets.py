"""Encrypted secrets built-in command handlers."""

from __future__ import annotations

from typing import Any

from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import split_command_argv
from services.intel.registry import provider_status_catalog
from services.secrets.audit import emit_secret_event
from services.secrets.storage import InvalidSecretName, delete_secret, list_secret_metadata, normalize_secret_name
from services.secrets.vault import MasterKeyError, SecretDecryptError
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamPermissionDenied


def _secret_usage() -> list[dict[str, object]]:
    return [
        output_line("Secret commands:", "builtin-section"),
        output_line("  secret set NAME", "builtin-help-row"),
        output_line("  secret list", "builtin-help-row"),
        output_line("  secret unset NAME", "builtin-help-row"),
        output_line("  secret show-consumers", "builtin-help-row"),
        output_line("  providers", "builtin-help-row"),
        output_line("Values are entered through the browser prompt and are never shown in the transcript.", "builtin-note"),
    ]


def _provider_secret_names(provider: dict[str, Any]) -> list[str]:
    names = provider.get("secret_env_names")
    if not isinstance(names, list):
        aliases = provider.get("secret_env_aliases")
        alias_names = aliases if isinstance(aliases, list) else []
        names = [
            provider.get("secret_env"),
            *alias_names,
        ]
    return [
        str(name or "").strip().upper()
        for name in names
        if str(name or "").strip()
    ]


def _provider_display_secret_names(provider: dict[str, Any]) -> str:
    primary = str(provider.get("secret_env") or "").strip().upper()
    if primary:
        return primary
    return "No secret needed"


def _provider_secret_name_set(secret_scope_id: str) -> set[str]:
    names: set[str] = set()
    for row in list_secret_metadata(secret_scope_id):
        name = str(row.get("name") or "").strip().upper()
        if name:
            names.add(name)
        for env in row.get("consumer_envs") or []:
            env_name = str(env or "").strip().upper()
            if env_name:
                names.add(env_name)
    return names


def _provider_intel_subcommands(provider: dict[str, Any]) -> str:
    uses = [
        str(item or "").strip()
        for item in provider.get("uses") or []
        if str(item or "").strip()
    ]
    if uses:
        return ", ".join(uses)
    entity_types = [
        str(entity_type or "").strip().lower()
        for entity_type in provider.get("entity_types") or []
        if str(entity_type or "").strip()
    ]
    if not entity_types:
        return "No intel subcommands"
    return ", ".join(f"intel {entity_type}" for entity_type in entity_types)


def _provider_status(provider: dict[str, Any], stored_secret_names: set[str]) -> tuple[bool, str]:
    secret_names = _provider_secret_names(provider)
    if any(name in stored_secret_names for name in secret_names):
        return True, "configured"
    needs_secret = bool(provider.get("requires_secret") or secret_names)
    if not needs_secret or provider.get("optional_secret"):
        return True, "available"
    return False, "not configured"


def _format_provider_status_row(provider: dict[str, Any], status_label: str) -> str:
    label = str(provider.get("label") or provider.get("id") or "Provider").strip()
    detail = " · ".join([
        status_label,
        _provider_intel_subcommands(provider),
        _provider_display_secret_names(provider),
    ])
    return format_native_record(label, detail, 22)


def _run_secret_show_consumers(secret_scope_id: str) -> list[dict[str, object]]:
    try:
        stored_secret_names = _provider_secret_name_set(secret_scope_id)
    except (MasterKeyError, SecretDecryptError) as exc:
        return [output_line(f"secret: {exc}")]

    providers = provider_status_catalog()
    if not providers:
        return [output_line("No intel providers are registered.", "builtin-note")]

    provider_rows = []
    for provider in providers:
        configured, status_label = _provider_status(provider, stored_secret_names)
        provider_rows.append({
            "configured": configured,
            "label": str(provider.get("label") or provider.get("id") or ""),
            "line": _format_provider_status_row(provider, status_label),
        })

    usable_count = sum(1 for row in provider_rows if row["configured"])
    needs_count = max(0, len(provider_rows) - usable_count)
    lines = [
        output_line("Provider status:", "builtin-section"),
        output_line(f"{usable_count} usable · {needs_count} not configured", "builtin-note"),
    ]

    usable_rows = sorted(
        [row for row in provider_rows if row["configured"]],
        key=lambda row: str(row["label"]).lower(),
    )
    missing_rows = sorted(
        [row for row in provider_rows if not row["configured"]],
        key=lambda row: str(row["label"]).lower(),
    )

    if usable_rows:
        lines.append(output_line(""))
        lines.append(output_line("Usable providers:", "builtin-section"))
        for row in usable_rows:
            lines.append(output_line(str(row["line"]), "builtin-kv"))

    if missing_rows:
        lines.append(output_line(""))
        lines.append(output_line("Not configured:", "builtin-section"))
        for row in missing_rows:
            lines.append(output_line(str(row["line"]), "builtin-kv"))

    return lines


def run_builtin_secret(command: str, session_id: str, *, team_id: str = "", team_role: str = "") -> list[dict[str, object]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"
    secret_scope_id = team_id or session_id

    if subcommand in {"help", "-h", "--help"}:
        return _secret_usage()

    if subcommand == "list":
        try:
            rows = list_secret_metadata(secret_scope_id)
        except (MasterKeyError, SecretDecryptError) as exc:
            return [output_line(f"secret: {exc}")]
        if not rows:
            scope_label = "team" if team_id else "session"
            return [output_line(f"No secrets stored for this {scope_label}.", "builtin-note")]
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
        if team_id:
            try:
                require_capability(
                    team_role,
                    Capability.MANAGE_SECRETS,
                    team_id=team_id,
                    action="secret_unset",
                    surface="terminal_builtin",
                )
            except TeamPermissionDenied:
                return [output_line("secret: your team role cannot manage shared secrets.", "exit-fail")]
        try:
            name = normalize_secret_name(parts[2])
            removed = delete_secret(secret_scope_id, name)
        except (InvalidSecretName, MasterKeyError, SecretDecryptError) as exc:
            return [output_line(f"secret: {exc}")]
        if team_id:
            emit_secret_event(
                "SECRET_DELETED" if removed else "SECRET_DELETE_NOOP",
                session_id,
                name=name,
                team_id=team_id,
                actor_role=team_role,
                surface="terminal_builtin",
            )
        if removed:
            return [output_line(f"{name} removed.", "builtin-success")]
        return [output_line(f"{name} was not set.", "builtin-note")]

    if subcommand == "show-consumers":
        return _run_secret_show_consumers(secret_scope_id)

    return [
        output_line(f"secret: unknown subcommand '{subcommand}'"),
        *_secret_usage(),
    ]
