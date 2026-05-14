"""YAML loading, normalization, and overlay merging for command registry files."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
import os
import re
import yaml


SECRET_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def dedupe_preserve_order(values):
    return list(dict.fromkeys(values))


def load_yaml_mapping(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError:
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
        if item.get("requires_workspace"):
            normalized["requires_workspace"] = True
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
    result: list[dict[str, object]] = []
    by_env: dict[str, dict[str, object]] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        env = str(item.get("env") or "").strip().upper()
        if not SECRET_ENV_RE.fullmatch(env):
            continue
        optional = bool(item.get("optional", False))
        if env in by_env:
            # If any declaration requires the secret, keep the merged entry required.
            by_env[env]["optional"] = bool(by_env[env].get("optional")) and optional
            continue
        normalized: dict[str, object] = {"env": env, "optional": optional}
        by_env[env] = normalized
        result.append(normalized)
    return result


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
    return entry


def load_commands_registry_file(
    path: str,
    normalize_autocomplete: Callable[[str, object], dict],
) -> dict:
    loaded = load_yaml_mapping(path)
    commands = []
    pipe_helpers = []
    for raw_entry in loaded.get("commands", []) or []:
        entry = normalize_commands_registry_entry(raw_entry, normalize_autocomplete)
        if entry:
            commands.append(entry)
    for raw_entry in loaded.get("pipe_helpers", []) or []:
        entry = normalize_commands_registry_entry(raw_entry, normalize_autocomplete, pipe_helper=True)
        if entry:
            pipe_helpers.append(entry)
    return {
        "version": int(loaded.get("version") or 1),
        "commands": commands,
        "pipe_helpers": pipe_helpers,
    }


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
                (
                    tuple(item.get("flags", []) or []),
                    item.get("position"),
                    tuple(item.get("unless_any", []) or []),
                    tuple(item.get("unless_any_regex", []) or []),
                )
                for item in runtime_adaptations.setdefault("inject_flags", [])
                if isinstance(item, dict)
            }
            for inject in overlay_runtime.get("inject_flags", []) or []:
                key = (
                    tuple(inject.get("flags", []) or []),
                    inject.get("position"),
                    tuple(inject.get("unless_any", []) or []),
                    tuple(inject.get("unless_any_regex", []) or []),
                )
                if key not in existing_inject:
                    runtime_adaptations.setdefault("inject_flags", []).append(deepcopy(inject))
                    existing_inject.add(key)
        if overlay_runtime.get("environment"):
            existing_env = {
                (item.get("name"), item.get("value"), item.get("managed_directory_flag"))
                for item in runtime_adaptations.setdefault("environment", [])
                if isinstance(item, dict)
            }
            for env_item in overlay_runtime.get("environment", []) or []:
                key = (env_item.get("name"), env_item.get("value"), env_item.get("managed_directory_flag"))
                if key not in existing_env:
                    runtime_adaptations.setdefault("environment", []).append(deepcopy(env_item))
                    existing_env.add(key)
        if overlay_entry.get("interactive"):
            interactive = merged.setdefault("interactive", {})
            interactive.update(deepcopy(overlay_entry["interactive"]))
        if overlay_entry.get("requires_secrets"):
            existing_secrets = {
                item.get("env"): item
                for item in merged.setdefault("requires_secrets", [])
                if isinstance(item, dict) and item.get("env")
            }
            for secret in overlay_entry.get("requires_secrets", []) or []:
                env = secret.get("env") if isinstance(secret, dict) else None
                if not env:
                    continue
                if env in existing_secrets:
                    existing_secrets[env]["optional"] = bool(existing_secrets[env].get("optional")) and bool(
                        secret.get("optional")
                    )
                    continue
                copied = deepcopy(secret)
                merged.setdefault("requires_secrets", []).append(copied)
                existing_secrets[env] = copied

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
    return merged


def load_commands_registry(
    path: str,
    normalize_autocomplete: Callable[[str, object], dict],
    empty_autocomplete_entry: Callable[[], dict],
    merge_autocomplete_context: Callable[[dict, dict], dict],
) -> dict:
    base = load_commands_registry_file(path, normalize_autocomplete)
    root, ext = os.path.splitext(path)
    local = load_commands_registry_file(f"{root}.local{ext}", normalize_autocomplete)
    return merge_commands_registry(base, local, empty_autocomplete_entry, merge_autocomplete_context)
