# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""YAML loading, normalization, and overlay merging for command registry files."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import logging
import os
import re
import yaml

from services.commands.registry_adaptations import (
    copy_environment_conditions,
    copy_inject_conditions,
    environment_merge_key,
    inject_merge_key,
)
from services.commands import registry_secret_specs


log = logging.getLogger("shell")
SECRET_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# ── Knowledge field schema ─────────────────────────────────────────────────────
# Phase 0 locked decisions — these constants are the contract that Phase 1
# normalization, merge, and catalog projection must implement.
#
# Merge strategy (locked):
#   - List fields  (.local overlays extend, dedupe after normalization)
#   - Scalar fields (.local overlays replace entirely)
# All knowledge fields are descriptive only; none affect allow/deny policy
# or runtime behaviour in any way.
KNOWLEDGE_LIST_FIELDS: frozenset[str] = frozenset({"notes", "gotchas", "safe_defaults", "common_flags"})
KNOWLEDGE_SCALAR_FIELDS: frozenset[str] = frozenset({"artifact_behavior"})
KNOWLEDGE_FIELDS: frozenset[str] = KNOWLEDGE_LIST_FIELDS | KNOWLEDGE_SCALAR_FIELDS
# Caps: max items per list field; max characters per item (list or scalar).
KNOWLEDGE_LIST_MAX_ITEMS: int = 5
KNOWLEDGE_TEXT_MAX_CHARS: int = 200

# Top-level fields explicitly consumed by normalize_commands_registry_entry.
# "knowledge" is listed here now so that Phase 1's addition of that key never
# trips the lint even before the normalizer wire-up lands.
# Anything not in this set is silently ignored during normalisation; the lint
# function check_unknown_command_fields() surfaces such keys in tests and
# startup validation passes without hard-failing on .local overlays.
_KNOWN_TOP_LEVEL_COMMAND_FIELDS: frozenset[str] = frozenset({
    "root", "description", "category", "policy", "help",
    "workspace_flags", "autocomplete", "runtime_adaptations",
    "requires_secrets", "interactive", "allow_grouping_flags",
    # Feature-gate aliases — all three map to the same normalized value.
    "feature_required", "requires_feature", "feature",
    # Knowledge fields (consumed after Phase 1 normalization lands).
    "knowledge",
})
# Pipe helpers have a narrower field set; any extra key is a likely typo.
_KNOWN_TOP_LEVEL_PIPE_HELPER_FIELDS: frozenset[str] = frozenset({
    "root", "autocomplete",
    "feature_required", "requires_feature", "feature",
})


def check_unknown_command_fields(entry: object, *, pipe_helper: bool = False) -> list[str]:
    """Return unknown top-level keys in a registry entry (for lint use only).

    Not called on the hot path.  Use in tests or a startup validation pass to
    surface typos in commands.yaml and .local overlays without hard-failing
    normalisation (silent-ignore is the runtime policy; this is the companion
    lint that makes the policy visible to authors).

    Returns a sorted list of unrecognised key names, or [] if the entry is
    clean.  Returns [] for non-dict input.
    """
    if not isinstance(entry, dict):
        return []
    known = _KNOWN_TOP_LEVEL_PIPE_HELPER_FIELDS if pipe_helper else _KNOWN_TOP_LEVEL_COMMAND_FIELDS
    unknown = [k for k in entry if k not in known]
    raw_knowledge = entry.get("knowledge")
    if not pipe_helper and isinstance(raw_knowledge, dict):
        unknown.extend(f"knowledge.{k}" for k in raw_knowledge if k not in KNOWLEDGE_FIELDS)
    return sorted(unknown)


def dedupe_preserve_order(values):
    return list(dict.fromkeys(values))


def load_yaml_mapping(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        log.warning("COMMAND_REGISTRY_YAML_LOAD_FAILED", extra={
            "path": path,
            "overlay": ".local" in os.path.basename(path),
            "error_type": type(exc).__name__,
            "error": str(exc)[:240],
        })
        return {}
    return data if isinstance(data, dict) else {}


def normalize_policy_list(items, *, lowercase: bool) -> list[str]:
    result = []
    seen = set()
    for item in items or []:
        value = str(item or "").strip()
        if not value:
            continue
        if lowercase:
            value = value.lower()
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_workspace_flags(items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        flag = str(item.get("flag") or "").strip()
        mode = str(item.get("mode") or "").strip().lower()
        value = str(item.get("value") or "").strip().lower()
        if not flag or mode not in {"read", "write", "read_write"}:
            continue
        if value not in {"required", "separate", "attached", "separate_or_attached"}:
            value = "required"
        subcommands = tuple(
            sorted(
                str(subcommand).strip().lower()
                for subcommand in item.get("subcommands", []) or []
                if str(subcommand).strip()
            )
        )
        key = (flag, mode, value, str(item.get("kind") or "").strip().lower(), subcommands)
        if key in seen:
            continue
        seen.add(key)
        normalized: dict[str, object] = {"flag": flag, "mode": mode, "value": value}
        if subcommands:
            normalized["subcommands"] = list(subcommands)
        kind = str(item.get("kind") or "").strip().lower()
        if kind == "directory":
            normalized["kind"] = kind
        output_format = str(item.get("format") or "").strip().lower()
        if output_format:
            normalized["format"] = output_format
        max_file_mb = item.get("max_file_mb")
        if isinstance(max_file_mb, int | float) and max_file_mb > 0:
            normalized["max_file_mb"] = max_file_mb
        result.append(normalized)
    return result


def normalize_allow_grouping_flags(raw_entry: dict) -> list[str]:
    result: list[str] = []
    seen = set()
    autocomplete = raw_entry.get("autocomplete")
    raw_flags = autocomplete.get("flags", []) if isinstance(autocomplete, dict) else []
    for raw_flag in raw_flags or []:
        if not isinstance(raw_flag, dict) or not raw_flag.get("allow_grouping") or raw_flag.get("takes_value"):
            continue
        value = str(raw_flag.get("value") or "").strip()
        if not re.fullmatch(r"-[A-Za-z]", value):
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_help_flag_token(token: object) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    if raw.startswith("--") or len(raw) > 2:
        return raw.lower()
    return raw


def normalize_help_spec(raw_spec: object) -> dict[str, object]:
    if not isinstance(raw_spec, dict):
        return {}
    raw_flags = raw_spec.get("flags", []) or []
    if not isinstance(raw_flags, list):
        raw_flags = [raw_flags]
    raw_subcommands = raw_spec.get("subcommands", []) or []
    if not isinstance(raw_subcommands, list):
        raw_subcommands = [raw_subcommands]
    flags = [
        token
        for token in (normalize_help_flag_token(item) for item in raw_flags)
        if token
    ]
    subcommands = [
        str(item or "").strip().lower()
        for item in raw_subcommands
        if str(item or "").strip()
    ]
    spec: dict[str, object] = {}
    if flags:
        spec["flags"] = dedupe_preserve_order(flags)
    if subcommands:
        spec["subcommands"] = dedupe_preserve_order(subcommands)
    return spec


def normalize_runtime_inject_flags(items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        raw_flags = item.get("flags") or item.get("tokens") or []
        flags = [
            str(flag).strip()
            for flag in raw_flags
            if str(flag).strip()
        ] if isinstance(raw_flags, list) else []
        if not flags:
            continue
        position = str(item.get("position") or "prepend").strip().lower()
        if position == "prefix":
            position = "command_prefix"
        if position not in {"prepend", "append", "command_prefix"}:
            position = "prepend"
        unless_any = [
            str(token).strip()
            for token in item.get("unless_any", []) or []
            if str(token).strip()
        ]
        unless_any_regex = [
            str(pattern).strip()
            for pattern in item.get("unless_any_regex", []) or []
            if str(pattern).strip()
        ]
        normalized: dict[str, object] = {
            "flags": flags,
            "position": position,
            "unless_any": unless_any,
            "unless_any_regex": unless_any_regex,
        }
        notice = str(item.get("notice") or item.get("output_notice") or "").strip()
        if notice:
            normalized["notice"] = notice
        copy_inject_conditions(item, normalized)
        result.append(normalized)
    return result


def normalize_runtime_managed_workspace_directory(item) -> dict[str, object]:
    if not isinstance(item, dict):
        return {}
    flag = str(item.get("flag") or "").strip()
    directory = str(item.get("directory") or item.get("path") or "").strip().strip("/")
    if not flag or not directory:
        return {}
    subcommands = [
        str(subcommand).strip().lower()
        for subcommand in item.get("subcommands", []) or []
        if str(subcommand).strip()
    ]
    skip_if_any = [
        str(token).strip()
        for token in item.get("skip_if_any", []) or []
        if str(token).strip()
    ]
    result: dict[str, object] = {
        "flag": flag,
        "directory": directory,
        "subcommands": dedupe_preserve_order(subcommands),
        "skip_if_any": dedupe_preserve_order(skip_if_any),
        "reject_alternate": bool(item.get("reject_alternate", True)),
        "counts_as_workspace_write": bool(item.get("counts_as_workspace_write", True)),
    }
    reject_message = str(item.get("reject_message") or "").strip()
    if reject_message:
        result["reject_message"] = reject_message
    return result


def normalize_runtime_environment(items) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name or not value:
            continue
        normalized: dict[str, object] = {"name": name, "value": value}
        managed_flag = str(item.get("managed_directory_flag") or "").strip()
        if managed_flag:
            normalized["managed_directory_flag"] = managed_flag
        copy_environment_conditions(item, normalized)
        result.append(normalized)
    return result


def normalize_runtime_adaptations(raw_value) -> dict[str, object]:
    raw = raw_value if isinstance(raw_value, dict) else {}
    adaptations: dict[str, object] = {}
    inject_flags = normalize_runtime_inject_flags(raw.get("inject_flags"))
    if inject_flags:
        adaptations["inject_flags"] = inject_flags
    managed_directory = normalize_runtime_managed_workspace_directory(
        raw.get("managed_workspace_directory")
    )
    if managed_directory:
        adaptations["managed_workspace_directory"] = managed_directory
    environment = normalize_runtime_environment(raw.get("environment"))
    if environment:
        adaptations["environment"] = environment
    return adaptations


def normalize_required_secrets(items) -> list[dict[str, object]]:
    return registry_secret_specs.normalize_required_secrets(items, secret_env_re=SECRET_ENV_RE)


def coerce_positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return number if number > 0 else default


def normalize_interactive_spec(raw_spec: object) -> dict:
    if not isinstance(raw_spec, dict) or not raw_spec:
        return {}
    mode = str(raw_spec.get("mode") or "").strip().lower()
    trigger_flag = str(raw_spec.get("trigger_flag") or "").strip()
    if mode != "pty" or not trigger_flag:
        return {}
    transcript_mode = str(raw_spec.get("transcript_mode") or "final_frame").strip().lower()
    if transcript_mode not in {"final_frame", "scrollback_findings", "all_sanitized"}:
        transcript_mode = "final_frame"
    allow_input = bool(raw_spec.get("allow_input", True))
    input_safety = str(raw_spec.get("input_safety") or "").strip().lower()
    allowed_input_safety = {"no_input", "navigation_only", "scanner_controls"}
    if not input_safety and not allow_input:
        input_safety = "no_input"
    if input_safety not in allowed_input_safety:
        return {}
    if allow_input and input_safety == "no_input":
        return {}
    return {
        "mode": "pty",
        "trigger_flag": trigger_flag,
        "default_rows": coerce_positive_int(raw_spec.get("default_rows"), 24),
        "default_cols": coerce_positive_int(raw_spec.get("default_cols"), 100),
        "max_runtime_seconds": coerce_positive_int(raw_spec.get("max_runtime_seconds"), 900),
        "allow_input": allow_input,
        "requires_args": bool(raw_spec.get("requires_args", False)),
        "transcript_mode": transcript_mode,
        "input_safety": input_safety,
    }


def normalize_command_knowledge(raw_knowledge: object) -> dict[str, object]:
    """Normalize the optional ``knowledge`` sub-dict from a registry entry.

    Returns a sparse dict — fields are omitted when empty after normalization.
    All fields are descriptive only; none affect allow/deny policy or any
    runtime behaviour.  Normalization rules per Phase 0 locked decisions:
    - List fields: strip, truncate to KNOWLEDGE_TEXT_MAX_CHARS, drop empties,
      dedupe, cap at KNOWLEDGE_LIST_MAX_ITEMS items.
    - Scalar fields: strip, truncate to KNOWLEDGE_TEXT_MAX_CHARS.
    - Unknown sub-keys: silently ignored.
    """
    if not isinstance(raw_knowledge, dict):
        return {}

    result: dict[str, object] = {}

    for field in KNOWLEDGE_LIST_FIELDS:
        raw_items = raw_knowledge.get(field)
        if raw_items is None:
            continue
        items_raw: list[object] = raw_items if isinstance(raw_items, list) else [raw_items]
        items: list[str] = []
        seen: set[str] = set()
        for item in items_raw:
            text = str(item or "").strip()
            if not text:
                continue
            if len(text) > KNOWLEDGE_TEXT_MAX_CHARS:
                text = text[:KNOWLEDGE_TEXT_MAX_CHARS]
            if text in seen:
                continue
            seen.add(text)
            items.append(text)
            if len(items) >= KNOWLEDGE_LIST_MAX_ITEMS:
                break
        if items:
            result[field] = items

    for field in KNOWLEDGE_SCALAR_FIELDS:
        raw_value = raw_knowledge.get(field)
        if raw_value is None:
            continue
        text = str(raw_value).strip()
        if len(text) > KNOWLEDGE_TEXT_MAX_CHARS:
            text = text[:KNOWLEDGE_TEXT_MAX_CHARS]
        if text:
            result[field] = text

    return result


def normalize_commands_registry_entry(
    raw_entry,
    normalize_autocomplete: Callable[[str, object], dict],
    *,
    pipe_helper: bool = False,
) -> dict | None:
    if not isinstance(raw_entry, dict):
        return None
    root = str(raw_entry.get("root") or "").strip().lower()
    if not root:
        return None

    entry = {
        "root": root,
        "autocomplete": normalize_autocomplete(root, raw_entry.get("autocomplete")),
    }
    description = str(raw_entry.get("description") or "").strip()
    if description:
        entry["description"] = description
    feature_required = raw_entry.get("feature_required") or raw_entry.get("requires_feature") or raw_entry.get("feature")
    if feature_required:
        if isinstance(feature_required, (list, tuple, set)):
            entry["feature_required"] = [
                str(value).strip().lower() for value in feature_required if str(value).strip()
            ]
        else:
            entry["feature_required"] = str(feature_required).strip().lower()
    if pipe_helper:
        return entry

    raw_policy_value = raw_entry.get("policy")
    raw_policy = raw_policy_value if isinstance(raw_policy_value, dict) else {}
    entry["category"] = str(raw_entry.get("category") or "").strip()
    entry["policy"] = {
        "allow": normalize_policy_list(raw_policy.get("allow"), lowercase=True),
        "deny": normalize_policy_list(raw_policy.get("deny"), lowercase=False),
    }
    entry["workspace_flags"] = normalize_workspace_flags(raw_entry.get("workspace_flags"))
    entry["help"] = normalize_help_spec(raw_entry.get("help"))
    entry["allow_grouping_flags"] = normalize_allow_grouping_flags(raw_entry)
    entry["runtime_adaptations"] = normalize_runtime_adaptations(raw_entry.get("runtime_adaptations"))
    entry["requires_secrets"] = normalize_required_secrets(raw_entry.get("requires_secrets"))
    interactive = normalize_interactive_spec(raw_entry.get("interactive"))
    if interactive and entry["requires_secrets"]:
        raise ValueError(
            f"{root} cannot combine interactive PTY mode with requires_secrets until PTY secret injection is supported"
        )
    if interactive:
        entry["interactive"] = interactive
    knowledge = normalize_command_knowledge(raw_entry.get("knowledge"))
    if knowledge:
        entry["knowledge"] = knowledge
    return entry


def load_commands_registry_file(
    path: str,
    normalize_autocomplete: Callable[[str, object], dict],
) -> dict:
    loaded = load_yaml_mapping(path)
    return normalize_commands_registry_data(loaded, normalize_autocomplete)


def normalize_commands_registry_data(
    loaded: object,
    normalize_autocomplete: Callable[[str, object], dict],
) -> dict:
    """Normalize an in-memory registry mapping with the YAML registry schema."""
    data = loaded if isinstance(loaded, dict) else {}
    commands = []
    pipe_helpers = []
    for raw_entry in data.get("commands", []) or []:
        entry = normalize_commands_registry_entry(raw_entry, normalize_autocomplete)
        if entry:
            commands.append(entry)
    for raw_entry in data.get("pipe_helpers", []) or []:
        entry = normalize_commands_registry_entry(raw_entry, normalize_autocomplete, pipe_helper=True)
        if entry:
            pipe_helpers.append(entry)
    registry = {
        "version": int(data.get("version") or 1),
        "commands": commands,
        "pipe_helpers": pipe_helpers,
    }
    validate_commands_registry_semantics(registry, require_pipe_contracts=False)
    return registry


def validate_commands_registry_semantics(
    registry: dict,
    *,
    require_pipe_contracts: bool,
) -> None:
    """Reject ambiguous command roots and incomplete pipe-helper contracts."""
    roots_by_section: dict[str, set[str]] = {}
    for section in ("commands", "pipe_helpers"):
        roots: set[str] = set()
        for entry in registry.get(section, []) or []:
            root = str(entry.get("root") or "").strip().lower()
            if not root:
                continue
            if root in roots:
                raise ValueError(f"duplicate command registry root in {section}: {root}")
            roots.add(root)
            if (
                require_pipe_contracts
                and section == "pipe_helpers"
                and not bool((entry.get("autocomplete") or {}).get("pipe_command"))
            ):
                raise ValueError(f"pipe helper must declare autocomplete.pipe.enabled: {root}")
        roots_by_section[section] = roots

    overlaps = roots_by_section["commands"] & roots_by_section["pipe_helpers"]
    if overlaps:
        raise ValueError(
            "command registry roots cannot appear in commands and pipe_helpers: "
            + ", ".join(sorted(overlaps))
        )


def merge_command_registry_entries(
    base_entry: dict,
    overlay_entry: dict,
    empty_autocomplete_entry: Callable[[], dict],
    merge_autocomplete_context: Callable[[dict, dict], dict],
    *,
    pipe_helper: bool = False,
) -> dict:
    merged = deepcopy(base_entry)
    if not pipe_helper:
        if overlay_entry.get("category"):
            merged["category"] = overlay_entry["category"]
        policy = merged.setdefault("policy", {"allow": [], "deny": []})
        for allow in overlay_entry.get("policy", {}).get("allow", []) or []:
            if allow not in policy.setdefault("allow", []):
                policy["allow"].append(allow)
        for deny in overlay_entry.get("policy", {}).get("deny", []) or []:
            if deny not in policy.setdefault("deny", []):
                policy["deny"].append(deny)
        allow_grouping_flags = merged.setdefault("allow_grouping_flags", [])
        for flag in overlay_entry.get("allow_grouping_flags", []) or []:
            if flag not in allow_grouping_flags:
                allow_grouping_flags.append(flag)
        workspace_flags = merged.setdefault("workspace_flags", [])
        existing_workspace_flags = {
            (
                item.get("flag"),
                item.get("mode"),
                item.get("value"),
                item.get("kind"),
                tuple(item.get("subcommands", []) or []),
            )
            for item in workspace_flags if isinstance(item, dict)
        }
        for workspace_flag in overlay_entry.get("workspace_flags", []) or []:
            key = (
                workspace_flag.get("flag"),
                workspace_flag.get("mode"),
                workspace_flag.get("value"),
                workspace_flag.get("kind"),
                tuple(workspace_flag.get("subcommands", []) or []),
            )
            if key not in existing_workspace_flags:
                workspace_flags.append(deepcopy(workspace_flag))
                existing_workspace_flags.add(key)

        runtime_adaptations = merged.setdefault("runtime_adaptations", {})
        overlay_runtime = overlay_entry.get("runtime_adaptations") or {}
        if overlay_runtime.get("managed_workspace_directory"):
            runtime_adaptations["managed_workspace_directory"] = deepcopy(
                overlay_runtime["managed_workspace_directory"]
            )
        if overlay_runtime.get("inject_flags"):
            existing_inject = {
                inject_merge_key(item)
                for item in runtime_adaptations.setdefault("inject_flags", [])
                if isinstance(item, dict)
            }
            for inject in overlay_runtime.get("inject_flags", []) or []:
                key = inject_merge_key(inject)
                if key not in existing_inject:
                    runtime_adaptations.setdefault("inject_flags", []).append(deepcopy(inject))
                    existing_inject.add(key)
        if overlay_runtime.get("environment"):
            existing_env = {
                environment_merge_key(item)
                for item in runtime_adaptations.setdefault("environment", [])
                if isinstance(item, dict)
            }
            for env_item in overlay_runtime.get("environment", []) or []:
                key = environment_merge_key(env_item)
                if key not in existing_env:
                    runtime_adaptations.setdefault("environment", []).append(deepcopy(env_item))
                    existing_env.add(key)
        if overlay_entry.get("interactive"):
            interactive = merged.setdefault("interactive", {})
            interactive.update(deepcopy(overlay_entry["interactive"]))
        if overlay_entry.get("help"):
            help_spec = merged.setdefault("help", {})
            if isinstance(help_spec, dict):
                for key in ("flags", "subcommands"):
                    values = [
                        str(item)
                        for item in help_spec.setdefault(key, [])
                        if str(item).strip()
                    ]
                    seen_values = set(values)
                    for item in overlay_entry.get("help", {}).get(key, []) or []:
                        value = str(item)
                        if value in seen_values:
                            continue
                        values.append(value)
                        seen_values.add(value)
                    help_spec[key] = values
        if overlay_entry.get("requires_secrets"):
            existing_secrets = {
                (
                    item.get("env"),
                    item.get("inject_env") or item.get("env"),
                    tuple(item.get("subcommands", []) or []),
                ): item
                for item in merged.setdefault("requires_secrets", [])
                if isinstance(item, dict) and item.get("env")
            }
            for secret in overlay_entry.get("requires_secrets", []) or []:
                env = secret.get("env") if isinstance(secret, dict) else None
                inject_env = (secret.get("inject_env") or env) if isinstance(secret, dict) else None
                if not env:
                    continue
                key = (env, inject_env, tuple(secret.get("subcommands", []) or []))
                if key in existing_secrets:
                    existing_secrets[key]["optional"] = bool(existing_secrets[key].get("optional")) and bool(
                        secret.get("optional")
                    )
                    fallback_envs = list(secret.get("fallback_envs", []) or [])
                    if fallback_envs:
                        existing_fallbacks = existing_secrets[key].setdefault("fallback_envs", [])
                        if isinstance(existing_fallbacks, list):
                            for fallback_env in fallback_envs:
                                if fallback_env not in existing_fallbacks:
                                    existing_fallbacks.append(fallback_env)
                    continue
                copied = deepcopy(secret)
                merged.setdefault("requires_secrets", []).append(copied)
                existing_secrets[key] = copied
        overlay_knowledge = overlay_entry.get("knowledge")
        if isinstance(overlay_knowledge, dict) and overlay_knowledge:
            base_knowledge = merged.setdefault("knowledge", {})
            # Scalar fields: overlay replaces entirely (Phase 0 locked).
            for field in KNOWLEDGE_SCALAR_FIELDS:
                if field in overlay_knowledge:
                    base_knowledge[field] = overlay_knowledge[field]
            # List fields: overlay extends then dedupes (Phase 0 locked).
            for field in KNOWLEDGE_LIST_FIELDS:
                overlay_items = overlay_knowledge.get(field)
                if not isinstance(overlay_items, list):
                    continue
                existing: list[str] = list(base_knowledge.get(field) or [])
                seen: set[str] = set(existing)
                for item in overlay_items:
                    if isinstance(item, str) and item and item not in seen:
                        existing.append(item)
                        seen.add(item)
                    if len(existing) >= KNOWLEDGE_LIST_MAX_ITEMS:
                        break
                base_knowledge[field] = existing
            if not base_knowledge:
                merged.pop("knowledge", None)

    base_autocomplete = merged.get("autocomplete") or empty_autocomplete_entry()
    overlay_autocomplete = overlay_entry.get("autocomplete") or {}
    if overlay_autocomplete:
        merged["autocomplete"] = merge_autocomplete_context(
            {merged["root"]: base_autocomplete},
            {merged["root"]: overlay_autocomplete},
        )[merged["root"]]
    elif "autocomplete" not in merged:
        merged["autocomplete"] = {}
    return merged


def merge_commands_registry(
    base: dict,
    overlay: dict,
    empty_autocomplete_entry: Callable[[], dict],
    merge_autocomplete_context: Callable[[dict, dict], dict],
) -> dict:
    merged = {
        "version": int(base.get("version") or 1),
        "commands": deepcopy(base.get("commands") or []),
        "pipe_helpers": deepcopy(base.get("pipe_helpers") or []),
    }

    def merge_list(key: str, *, pipe_helper: bool = False) -> None:
        existing = {entry["root"]: index for index, entry in enumerate(merged[key])}
        for overlay_entry in overlay.get(key) or []:
            root = overlay_entry["root"]
            if root in existing:
                index = existing[root]
                merged[key][index] = merge_command_registry_entries(
                    merged[key][index],
                    overlay_entry,
                    empty_autocomplete_entry,
                    merge_autocomplete_context,
                    pipe_helper=pipe_helper,
                )
            else:
                existing[root] = len(merged[key])
                merged[key].append(deepcopy(overlay_entry))

    merge_list("commands")
    merge_list("pipe_helpers", pipe_helper=True)
    validate_commands_registry_semantics(merged, require_pipe_contracts=True)
    return merged


def load_commands_registry(
    path: str,
    normalize_autocomplete: Callable[[str, object], dict],
    empty_autocomplete_entry: Callable[[], dict],
    merge_autocomplete_context: Callable[[dict, dict], dict],
    *, local_path: str | None = None,
) -> dict:
    base = load_commands_registry_file(path, normalize_autocomplete)
    if local_path is None:
        root, ext = os.path.splitext(path)
        local_path = f"{root}.local{ext}"
    local = load_commands_registry_file(local_path, normalize_autocomplete)
    return merge_commands_registry(base, local, empty_autocomplete_entry, merge_autocomplete_context)
