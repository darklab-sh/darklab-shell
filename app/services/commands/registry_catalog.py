"""Command registry catalog and secret-consumer shaping."""

from __future__ import annotations

from typing import Callable, cast

from services.commands import registry_loader
from services.commands.features import suggestion_enabled_for_features
from services.commands.registry_validation import command_root


def _dedupe_preserve_order(values):
    return registry_loader.dedupe_preserve_order(values)


def required_secrets_for_command(
    command: str,
    registry: dict,
    *,
    is_help_invocation: Callable[[str, str | None, dict | None], bool],
) -> list[dict[str, object]]:
    """Return normalized secret declarations for a command root."""
    root = command_root(command)
    if not root:
        return []
    if is_help_invocation(command, root, registry):
        return []
    for entry in registry.get("commands", []) or []:
        if str(entry.get("root") or "").strip().lower() == root:
            return [dict(item) for item in entry.get("requires_secrets") or [] if isinstance(item, dict)]
    return []


def interactive_pty_specs_from_registry(registry: dict) -> list[dict[str, object]]:
    """Return command-registry entries that opt into interactive PTY mode."""
    specs: list[dict[str, object]] = []
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        interactive = entry.get("interactive")
        if not root or not isinstance(interactive, dict) or interactive.get("mode") != "pty":
            continue
        trigger_flag = str(interactive.get("trigger_flag") or "").strip()
        if not trigger_flag:
            continue
        specs.append({
            "root": root,
            "trigger_flag": trigger_flag,
            "default_rows": registry_loader.coerce_positive_int(interactive.get("default_rows"), 24),
            "default_cols": registry_loader.coerce_positive_int(interactive.get("default_cols"), 100),
            "max_runtime_seconds": registry_loader.coerce_positive_int(interactive.get("max_runtime_seconds"), 900),
            "allow_input": bool(interactive.get("allow_input", True)),
            "requires_args": bool(interactive.get("requires_args", False)),
            "transcript_mode": str(interactive.get("transcript_mode") or "final_frame"),
            "input_safety": str(interactive.get("input_safety") or "no_input"),
        })
    return specs


def interactive_pty_spec_for_command(command: str, registry: dict) -> dict[str, object] | None:
    """Return the interactive PTY registry spec matching a command root."""
    root = command_root(command)
    if not root:
        return None
    for spec in interactive_pty_specs_from_registry(registry):
        if spec.get("root") == root:
            return spec
    return None


def _catalog_suggestions(items: object, cfg=None) -> list[dict[str, object]]:
    suggestions: list[dict[str, object]] = []
    seen = set()
    if not isinstance(items, list):
        return suggestions
    for item in items:
        if not isinstance(item, dict) or not suggestion_enabled_for_features(item, cfg):
            continue
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        if value.lower() in seen:
            continue
        seen.add(value.lower())
        suggestion: dict[str, object] = {
            "value": value,
            "description": str(item.get("description") or "").strip(),
        }
        if item.get("takes_value"):
            suggestion["takes_value"] = True
        suggestions.append(suggestion)
    return suggestions


def _catalog_autocomplete_spec(spec: object, cfg=None) -> dict[str, object]:
    autocomplete = cast(dict[str, object], spec) if isinstance(spec, dict) else {}
    raw_expects_value = autocomplete.get("expects_value")
    expects_value = {
        str(item)
        for item in raw_expects_value
        if str(item)
    } if isinstance(raw_expects_value, (list, tuple, set)) else set()
    raw_arg_hints = autocomplete.get("arg_hints")
    arg_hints = cast(dict[str, object], raw_arg_hints) if isinstance(raw_arg_hints, dict) else {}
    flags: list[dict[str, object]] = []
    for item in _catalog_suggestions(autocomplete.get("flags"), cfg):
        flag = dict(item)
        value = str(flag.get("value") or "")
        if value in expects_value or item.get("takes_value"):
            flag["takes_value"] = True
            hints = _catalog_suggestions(arg_hints.get(value), cfg)
            if hints:
                flag["value_hints"] = hints
        flags.append(flag)

    positional_hints = _catalog_suggestions(arg_hints.get("__positional__"), cfg)
    examples = _catalog_suggestions(autocomplete.get("examples"), cfg)
    subcommands: list[dict[str, object]] = []
    raw_subcommands = autocomplete.get("subcommands")
    if isinstance(raw_subcommands, dict):
        for name, sub_spec in raw_subcommands.items():
            sub_name = str(name or "").strip()
            if not sub_name:
                continue
            sub_catalog = _catalog_autocomplete_spec(sub_spec, cfg)
            if isinstance(sub_spec, dict):
                description = str(sub_spec.get("description") or "").strip()
                if description:
                    sub_catalog["description"] = description
            sub_catalog["name"] = sub_name
            subcommands.append(sub_catalog)

    return {
        "flags": flags,
        "arguments": positional_hints,
        "examples": examples,
        "subcommands": subcommands,
    }


def _catalog_workspace_flags(items: object) -> list[dict[str, object]]:
    flags: list[dict[str, object]] = []
    if not isinstance(items, list):
        return flags
    for item in items:
        if not isinstance(item, dict):
            continue
        flag = str(item.get("flag") or "").strip()
        if not flag:
            continue
        entry: dict[str, object] = {
            "flag": flag,
            "mode": str(item.get("mode") or "").strip(),
            "value": str(item.get("value") or "").strip(),
        }
        kind = str(item.get("kind") or "").strip()
        if kind:
            entry["kind"] = kind
        subcommands = [
            str(subcommand).strip()
            for subcommand in item.get("subcommands", []) or []
            if str(subcommand).strip()
        ]
        if subcommands:
            entry["subcommands"] = subcommands
        flags.append(entry)
    return flags


def _catalog_runtime_notes(runtime_adaptations: object) -> list[str]:
    runtime = runtime_adaptations if isinstance(runtime_adaptations, dict) else {}
    notes: list[str] = []
    for inject in runtime.get("inject_flags", []) or []:
        if not isinstance(inject, dict):
            continue
        flags = " ".join(str(flag) for flag in inject.get("flags", []) or [] if str(flag).strip())
        if flags:
            notes.append(f"Adds `{flags}` automatically when needed.")
    managed = runtime.get("managed_workspace_directory")
    if isinstance(managed, dict) and managed.get("directory"):
        notes.append(
            f"Uses a managed `{managed['directory']}` directory in the session workspace."
        )
    environment = runtime.get("environment")
    if isinstance(environment, list) and environment:
        notes.append("Uses session-scoped runtime state for tool configuration.")
    return _dedupe_preserve_order(notes)


def _catalog_interactive_notes(interactive_spec: object) -> list[str]:
    interactive = interactive_spec if isinstance(interactive_spec, dict) else {}
    if interactive.get("mode") != "pty":
        return []
    trigger = str(interactive.get("trigger_flag") or "").strip()
    if not trigger:
        return []
    return [f"Use `{trigger}` to open the interactive terminal view for this command."]


def _catalog_required_secrets(items: object) -> list[dict[str, object]]:
    secrets = []
    if not isinstance(items, list):
        return secrets
    for item in items:
        if not isinstance(item, dict):
            continue
        env = str(item.get("env") or "").strip().upper()
        if not env:
            continue
        entry: dict[str, object] = {
            "env": env,
            "optional": bool(item.get("optional", False)),
        }
        inject_env = str(item.get("inject_env") or "").strip().upper()
        if inject_env and inject_env != env:
            entry["inject_env"] = inject_env
        fallback_envs = [
            str(fallback or "").strip().upper()
            for fallback in item.get("fallback_envs", []) or []
            if str(fallback or "").strip()
        ]
        if fallback_envs:
            entry["fallback_envs"] = fallback_envs
        secrets.append(entry)
    return secrets


def command_secret_consumers(registry: dict) -> list[dict[str, object]]:
    """Return metadata-only secret consumers declared by command registry entries."""
    consumers: list[dict[str, object]] = []
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if not root:
            continue
        for secret in _catalog_required_secrets(entry.get("requires_secrets")):
            consumer = dict(secret)
            consumer["source"] = "command_registry"
            consumer["consumer"] = root
            consumers.append(consumer)
    return consumers


def command_catalog_from_registry(registry: dict, cfg=None) -> list[dict[str, object]]:
    """Return user-facing command reference data from the external command registry."""
    catalog = []
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if not root:
            continue
        raw_policy_value = entry.get("policy")
        policy = raw_policy_value if isinstance(raw_policy_value, dict) else {}
        allowed = [
            str(item).strip()
            for item in policy.get("allow", []) or []
            if str(item).strip()
        ]
        if not allowed:
            continue
        autocomplete = _catalog_autocomplete_spec(entry.get("autocomplete"), cfg)
        catalog.append({
            "root": root,
            "category": str(entry.get("category") or "Allowed commands").strip(),
            "description": str(entry.get("description") or "").strip(),
            "allow": allowed,
            "deny": [
                str(item).strip()
                for item in policy.get("deny", []) or []
                if str(item).strip()
            ],
            "examples": autocomplete["examples"],
            "flags": autocomplete["flags"],
            "arguments": autocomplete["arguments"],
            "subcommands": autocomplete["subcommands"],
            "workspace_flags": _catalog_workspace_flags(entry.get("workspace_flags")),
            "requires_secrets": _catalog_required_secrets(entry.get("requires_secrets")),
            "runtime_notes": _dedupe_preserve_order([
                *_catalog_runtime_notes(entry.get("runtime_adaptations")),
                *_catalog_interactive_notes(entry.get("interactive")),
            ]),
            "knowledge": entry.get("knowledge") or {},
            "feature_required": entry.get("feature_required"),
        })
    return catalog


def pipe_catalog_from_registry(registry: dict) -> list[dict[str, object]]:
    """Return user-facing catalog data for app-native pipe helpers."""
    catalog: list[dict[str, object]] = []
    for entry in registry.get("pipe_helpers", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if not root:
            continue
        autocomplete = entry.get("autocomplete") or {}
        if not isinstance(autocomplete, dict):
            autocomplete = {}
        if not autocomplete.get("pipe_command"):
            continue
        description = str(autocomplete.get("pipe_description") or "").strip()
        raw_flags = autocomplete.get("flags")
        flags: list[dict[str, str]] = []
        for flag in (raw_flags if isinstance(raw_flags, list) else []):
            if not isinstance(flag, dict):
                continue
            value = str(flag.get("value") or "").strip()
            flag_description = str(flag.get("description") or "").strip()
            if value:
                flags.append({"value": value, "description": flag_description})
        raw_arg_hints = autocomplete.get("arg_hints")
        arg_hints = cast(dict[str, object], raw_arg_hints) if isinstance(raw_arg_hints, dict) else {}
        arguments = _catalog_suggestions(arg_hints.get("__positional__"))
        pipe_entry: dict[str, object] = {
            "root": root,
            "description": description,
            "flags": flags,
        }
        if arguments:
            pipe_entry["arguments"] = arguments
        feature_required = entry.get("feature_required")
        if feature_required:
            pipe_entry["feature_required"] = feature_required
        catalog.append(pipe_entry)
    return catalog


def command_catalog_entry(root: str, subcommand: str | None, registry: dict, cfg=None) -> dict[str, object] | None:
    """Return catalog details for one command root, optionally scoped to a subcommand."""
    wanted_root = str(root or "").strip().lower()
    wanted_subcommand = str(subcommand or "").strip().lower()
    if not wanted_root:
        return None
    for entry in command_catalog_from_registry(registry, cfg):
        if str(entry.get("root") or "").lower() != wanted_root:
            continue
        if not wanted_subcommand:
            return entry
        raw_subcommands = entry.get("subcommands")
        subcommands = raw_subcommands if isinstance(raw_subcommands, list) else []
        for sub in subcommands:
            if not isinstance(sub, dict):
                continue
            if str(sub.get("name") or "").strip().lower() != wanted_subcommand:
                continue
            scoped = dict(entry)
            scoped["subcommand"] = wanted_subcommand
            scoped["description"] = str(sub.get("description") or scoped.get("description") or "")
            scoped["examples"] = sub.get("examples") or entry.get("examples") or []
            scoped["flags"] = sub.get("flags") or []
            scoped["arguments"] = sub.get("arguments") or []
            scoped["subcommands"] = []
            return scoped
        return None
    return None
