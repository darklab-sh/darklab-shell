# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Command loading, validation, and rewriting.

This module has no dependency on Flask — it contains pure helpers that can be
imported and tested in isolation.
"""

from copy import deepcopy
from dataclasses import dataclass, field
import ipaddress
import logging
import os
import re
from time import monotonic_ns
from typing import Any, Mapping
import yaml

import config as app_config
import config_paths
from services.commands import (
    registry_autocomplete,
    registry_cache,
    registry_catalog,
    registry_content,
    registry_faq,
    registry_loader,
    registry_runtime,
    registry_smoke,
    registry_targets,
    registry_validate,
    registry_workspace,
)
from services.commands.registry_faq import (
    FAQ_CATEGORY_ORDER as FAQ_CATEGORY_ORDER,  # noqa: F401 - compatibility seam
    FAQ_CATEGORY_OTHER as FAQ_CATEGORY_OTHER,  # noqa: F401 - compatibility seam
    _builtin_faq as _builtin_faq,  # noqa: F401 - compatibility seam
    _normalize_faq_category as _normalize_faq_category,  # noqa: F401 - compatibility seam
    render_faq_markup as render_faq_markup,  # noqa: F401 - compatibility seam
)
from services.commands.registry_content import TourPayload
from services.commands.features import feature_enabled
from services.commands.postfilters import parse_synthetic_postfilter as parse_synthetic_postfilter
from services.commands.registry_validation import (
    command_root as command_root,
    is_allowed_by_policy,
    is_denied,
    resolve_runtime_command as _resolve_runtime_command,
    runtime_missing_command_message as _runtime_missing_command_message,
    split_chained_commands as _split_chained_commands,
    split_command_argv,
)
from services.commands.raw_packets import nmap_raw_scan_restriction_reason
from services.teams.scope import OwnerContext

log = logging.getLogger("shell")
_HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CONF = app_config.APP_CONF_DIR or os.path.join(_HERE, "conf")
COMMANDS_REGISTRY_FILE = os.path.join(_CONF, "commands.yaml")
BUILTIN_AUTOCOMPLETE_FILE = os.path.join(os.path.dirname(__file__), "builtin_autocomplete.yaml")
FAQ_FILE              = os.path.join(_CONF, "faq.yaml")
WORKFLOWS_FILE        = os.path.join(_CONF, "workflows.yaml")
WELCOME_FILE          = os.path.join(_CONF, "welcome.yaml")
TOUR_FILE             = os.path.join(_CONF, "tour.yaml")
ASCII_FILE            = os.path.join(_CONF, "ascii.txt")
ASCII_MOBILE_FILE     = os.path.join(_CONF, "ascii_mobile.txt")
APP_HINTS_FILE        = os.path.join(_CONF, "app_hints.txt")
APP_HINTS_MOBILE_FILE = os.path.join(_CONF, "app_hints_mobile.txt")
AMASS_DEFAULT_WORKSPACE_DIR = "tools/amass"
WGET_DIRECTORY_PREFIX_FLAGS = registry_workspace.WGET_DIRECTORY_PREFIX_FLAGS
RESTRICTABLE_VALUE_TYPES = registry_targets.RESTRICTABLE_VALUE_TYPES
PROJECT_TARGET_VALUE_TYPES = registry_targets.PROJECT_TARGET_VALUE_TYPES
_COMMANDS_REGISTRY_CACHE: dict[str, Any] = {
    "signature": None,
    "registry": None,
}
_COMMANDS_POLICY_CACHE: dict[str, Any] = {
    "signature": None,
    "policy": None,
}
_COMMANDS_GROUPING_CACHE: dict[str, Any] = {
    "signature": None,
    "grouping": None,
}
_COMMANDS_REGISTRY_SIGNATURE_TTL_NS = 100_000_000
_COMMANDS_REGISTRY_SIGNATURE_CACHE: dict[str, tuple[int, tuple[tuple[str, int | None, int | None], ...]]] = {}


def _freeze_registry_value(value: Any) -> Any:
    return registry_cache.freeze_registry_value(value)


@dataclass(frozen=True)
class CommandValidationResult:
    allowed: bool
    reason: str = ""
    display_command: str = ""
    exec_command: str = ""
    workspace_reads: list[str] = field(default_factory=list)
    workspace_writes: list[str] = field(default_factory=list)
    workspace_exec_paths: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)


def _local_overlay_path(path):
    return os.fspath(config_paths.local_overlay_path_for(
        path, shipped_conf_dir=app_config.APP_CONF_DIR or _CONF,
        local_conf_dir=app_config.APP_LOCAL_CONF_DIR or None,
    ))


def _load_yaml_list(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def _load_yaml_list_with_local(path):
    items = _load_yaml_list(path)
    local_path = _local_overlay_path(path)
    if os.path.exists(local_path):
        try:
            items.extend(_load_yaml_list(local_path))
        except yaml.YAMLError as exc:
            log.warning("COMMAND_REGISTRY_LOCAL_OVERLAY_INVALID", extra={"path": local_path, "error": str(exc)})
    return items


def _dedupe_preserve_order(values):
    return registry_loader.dedupe_preserve_order(values)

def _empty_autocomplete_context_entry() -> dict:
    return {
        "flags": [],
        "expects_value": [],
        "arg_hints": {},
        "sequence_arg_hints": {},
        "close_after": {},
        "subcommands": {},
        "argument_limit": None,
        "pipe_command": False,
        "pipe_insert_value": "",
        "pipe_label": "",
        "pipe_description": "",
        "examples": [],
    }


def _normalize_policy_list(items, *, lowercase: bool) -> list[str]:
    return registry_loader.normalize_policy_list(items, lowercase=lowercase)


def _normalize_workspace_flags(items) -> list[dict[str, object]]:
    return registry_loader.normalize_workspace_flags(items)


def _normalize_allow_grouping_flags(raw_entry: dict) -> list[str]:
    return registry_loader.normalize_allow_grouping_flags(raw_entry)


def _normalize_runtime_inject_flags(items) -> list[dict[str, object]]:
    return registry_loader.normalize_runtime_inject_flags(items)


def _normalize_runtime_managed_workspace_directory(item) -> dict[str, object]:
    return registry_loader.normalize_runtime_managed_workspace_directory(item)


def _normalize_runtime_environment(items) -> list[dict[str, object]]:
    return registry_loader.normalize_runtime_environment(items)


def _normalize_runtime_adaptations(raw_value) -> dict[str, object]:
    return registry_loader.normalize_runtime_adaptations(raw_value)


def _normalize_registry_autocomplete(root: str, raw_spec) -> dict:
    if not isinstance(raw_spec, dict) or not raw_spec:
        return {}
    return _normalize_autocomplete_context({root: raw_spec}).get(root, {})


def _coerce_positive_int(value: object, default: int) -> int:
    return registry_loader.coerce_positive_int(value, default)

def _normalize_interactive_spec(raw_spec: object) -> dict:
    return registry_loader.normalize_interactive_spec(raw_spec)


def _normalize_commands_registry_entry(raw_entry, *, pipe_helper: bool = False) -> dict | None:
    return registry_loader.normalize_commands_registry_entry(
        raw_entry,
        _normalize_registry_autocomplete,
        pipe_helper=pipe_helper,
    )


def _load_commands_registry_file(path: str) -> dict:
    return registry_loader.load_commands_registry_file(path, _normalize_registry_autocomplete)


def _merge_command_registry_entries(base_entry: dict, overlay_entry: dict, *, pipe_helper: bool = False) -> dict:
    return registry_loader.merge_command_registry_entries(
        base_entry,
        overlay_entry,
        _empty_autocomplete_context_entry,
        _merge_autocomplete_context,
        pipe_helper=pipe_helper,
    )


def _merge_commands_registry(base: dict, overlay: dict) -> dict:
    return registry_loader.merge_commands_registry(
        base,
        overlay,
        _empty_autocomplete_context_entry,
        _merge_autocomplete_context,
    )


def _commands_registry_signature_uncached(path: str) -> tuple[tuple[str, int | None, int | None], ...]:
    candidates = (path, _local_overlay_path(path))
    signature = []
    for candidate in candidates:
        normalized = os.path.abspath(candidate)
        try:
            stat = os.stat(normalized)
        except OSError:
            signature.append((normalized, None, None))
            continue
        signature.append((normalized, stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def _commands_registry_signature(path: str) -> tuple[tuple[str, int | None, int | None], ...]:
    cache_key = "\0".join((os.path.abspath(path), os.path.abspath(_local_overlay_path(path))))
    now = monotonic_ns()
    cached = _COMMANDS_REGISTRY_SIGNATURE_CACHE.get(cache_key)
    if cached is not None:
        expires_at, signature = cached
        if now < expires_at:
            return signature
    signature = _commands_registry_signature_uncached(path)
    _COMMANDS_REGISTRY_SIGNATURE_CACHE[cache_key] = (now + _COMMANDS_REGISTRY_SIGNATURE_TTL_NS, signature)
    return signature


def load_commands_registry() -> dict:
    """Read commands.yaml plus optional commands.local.yaml overlays."""
    signature = _commands_registry_signature(COMMANDS_REGISTRY_FILE)
    if _COMMANDS_REGISTRY_CACHE["signature"] == signature and isinstance(_COMMANDS_REGISTRY_CACHE["registry"], dict):
        return _COMMANDS_REGISTRY_CACHE["registry"]

    registry = registry_loader.load_commands_registry(
        COMMANDS_REGISTRY_FILE,
        _normalize_registry_autocomplete,
        _empty_autocomplete_context_entry,
        _merge_autocomplete_context,
        local_path=_local_overlay_path(COMMANDS_REGISTRY_FILE),
    )
    frozen_registry = _freeze_registry_value(registry)
    _COMMANDS_REGISTRY_CACHE["signature"] = signature
    _COMMANDS_REGISTRY_CACHE["registry"] = frozen_registry
    return frozen_registry


_NATIVE_LOAD_COMMANDS_REGISTRY = load_commands_registry


def _commands_registry_loader_is_native() -> bool:
    return load_commands_registry is _NATIVE_LOAD_COMMANDS_REGISTRY


def clear_commands_registry_cache() -> None:
    """Clear cached command registry data for tests or live diagnostics."""
    _COMMANDS_REGISTRY_SIGNATURE_CACHE.clear()
    _COMMANDS_REGISTRY_CACHE["signature"] = None
    _COMMANDS_REGISTRY_CACHE["registry"] = None
    _COMMANDS_POLICY_CACHE["signature"] = None
    _COMMANDS_POLICY_CACHE["policy"] = None
    _COMMANDS_GROUPING_CACHE["signature"] = None
    _COMMANDS_GROUPING_CACHE["grouping"] = None


def required_secrets_for_command(command: str) -> list[dict[str, object]]:
    """Return normalized secret declarations for a command root."""
    return registry_catalog.required_secrets_for_command(
        command,
        load_commands_registry(),
        is_help_invocation=lambda cmd, root, registry: is_help_invocation(cmd, root=root, registry=registry),
    )


def interactive_pty_specs_from_registry(registry: dict | None = None) -> list[dict[str, object]]:
    """Return command-registry entries that opt into interactive PTY mode."""
    return registry_catalog.interactive_pty_specs_from_registry(registry or load_commands_registry())


def interactive_pty_spec_for_command(command: str, registry: dict | None = None) -> dict[str, object] | None:
    """Return the interactive PTY registry spec matching a command root."""
    return registry_catalog.interactive_pty_spec_for_command(command, registry or load_commands_registry())


def command_secret_consumers(registry: dict | None = None) -> list[dict[str, object]]:
    """Return metadata-only secret consumers declared by command registry entries."""
    return registry_catalog.command_secret_consumers(registry or load_commands_registry())


def command_catalog_from_registry(registry: dict | None = None, cfg=None) -> list[dict[str, object]]:
    """Return user-facing command reference data from the external command registry."""
    return registry_catalog.command_catalog_from_registry(registry or load_commands_registry(), cfg)


def pipe_catalog_from_registry(registry: dict | None = None) -> list[dict[str, object]]:
    """Return user-facing catalog data for app-native pipe helpers.

    Used by the Pipes section in command discovery and the command-registry
    modal.  Does not include allow/deny policy — pipe helpers are always
    available when the app is running.
    """
    return registry_catalog.pipe_catalog_from_registry(registry or load_commands_registry())


def command_catalog_entry(
    root: str,
    subcommand: str | None = None,
    registry: dict | None = None,
    cfg=None,
) -> dict[str, object] | None:
    """Return catalog details for one command root, optionally scoped to a subcommand."""
    return registry_catalog.command_catalog_entry(root, subcommand, registry or load_commands_registry(), cfg)


def load_builtin_autocomplete_registry():
    """Read app-owned built-in autocomplete grammar.

    This lives outside app/conf because built-in command grammar is not an
    operator-facing policy/config surface. It still uses the same registry
    shape and normalizer as external command autocomplete.
    """
    return _load_commands_registry_file(BUILTIN_AUTOCOMPLETE_FILE)


def load_command_policy():
    """Return allow/deny prefixes from commands.yaml."""
    signature = _commands_registry_signature(COMMANDS_REGISTRY_FILE)
    cached = _COMMANDS_POLICY_CACHE.get("policy")
    cache_enabled = _commands_registry_loader_is_native()
    if cache_enabled and _COMMANDS_POLICY_CACHE["signature"] == signature and isinstance(cached, tuple):
        cached_allow, cached_deny = cached
        allow_copy = list(cached_allow) if isinstance(cached_allow, list) else None
        deny_copy = list(cached_deny) if isinstance(cached_deny, list) else []
        return allow_copy, deny_copy

    registry = load_commands_registry()
    allow_prefixes: list[str] = []
    deny_prefixes: list[str] = []
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        raw_policy_value = entry.get("policy")
        policy = raw_policy_value if isinstance(raw_policy_value, dict) else {}
        allow_prefixes.extend(policy.get("allow") or [])
        deny_prefixes.extend(policy.get("deny") or [])

    allow_prefixes = _dedupe_preserve_order(allow_prefixes)
    deny_prefixes = _dedupe_preserve_order(deny_prefixes)
    policy = (allow_prefixes if allow_prefixes else None), deny_prefixes
    if cache_enabled:
        _COMMANDS_POLICY_CACHE["signature"] = signature
        _COMMANDS_POLICY_CACHE["policy"] = (
            list(policy[0]) if isinstance(policy[0], list) else None,
            list(policy[1]),
        )
    return policy


def load_allow_grouping_flags() -> dict[str, set[str]]:
    """Return short flags that may be grouped for allow-prefix matching."""
    signature = _commands_registry_signature(COMMANDS_REGISTRY_FILE)
    cached = _COMMANDS_GROUPING_CACHE.get("grouping")
    cache_enabled = _commands_registry_loader_is_native()
    if cache_enabled and _COMMANDS_GROUPING_CACHE["signature"] == signature and isinstance(cached, dict):
        return {
            str(root): set(flags)
            for root, flags in cached.items()
            if isinstance(flags, set)
        }

    registry = load_commands_registry()
    grouped: dict[str, set[str]] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if not root:
            continue
        flags = {
            str(flag)
            for flag in entry.get("allow_grouping_flags", []) or []
            if re.fullmatch(r"-[A-Za-z]", str(flag))
        }
        if flags:
            grouped.setdefault(root, set()).update(flags)
    if cache_enabled:
        _COMMANDS_GROUPING_CACHE["signature"] = signature
        _COMMANDS_GROUPING_CACHE["grouping"] = {
            root: set(flags)
            for root, flags in grouped.items()
        }
    return grouped


def autocomplete_context_from_commands_registry(registry: dict, cfg=None) -> dict:
    """Return the browser autocomplete context from a loaded command registry."""
    context = {}
    for section in ("commands", "pipe_helpers"):
        for entry in registry.get(section, []) or []:
            root = str(entry.get("root") or "").strip().lower()
            autocomplete = entry.get("autocomplete")
            if (
                root
                and isinstance(autocomplete, dict)
                and autocomplete
                and _suggestion_enabled_for_features(entry, cfg)
            ):
                spec = _attach_workspace_autocomplete_flags(
                    deepcopy(autocomplete),
                    entry.get("workspace_flags") or [],
                )
                if entry.get("description"):
                    spec["description"] = entry["description"]
                if entry.get("feature_required"):
                    spec["feature_required"] = entry["feature_required"]
                if entry.get("help"):
                    spec["help"] = deepcopy(entry["help"])
                required_secrets = [
                    dict(item)
                    for item in entry.get("requires_secrets") or []
                    if isinstance(item, dict)
                ]
                if required_secrets:
                    spec["requires_secrets"] = required_secrets
                context[root] = spec
    return _filter_autocomplete_context_by_features(context, app_config.CFG if cfg is None else cfg)


def _entry_for_command_root(root: str, registry: dict | None = None) -> dict | None:
    resolved_root = str(root or "").strip().lower()
    if not resolved_root:
        return None
    active_registry = registry or load_commands_registry()
    for entry in active_registry.get("commands", []) or []:
        if isinstance(entry, dict) and str(entry.get("root") or "").strip().lower() == resolved_root:
            return entry
    return None


def is_help_invocation_for_spec(command: str, help_spec: object, root: str | None = None) -> bool:
    """Return True when a command matches one command's help invocation metadata."""
    tokens = split_command_argv(command)
    resolved_root = str(root if root is not None else (tokens[0] if tokens else "")).strip().lower()
    if not resolved_root or not tokens or tokens[0].lower() != resolved_root:
        return False
    if not isinstance(help_spec, dict):
        return False

    flags = {
        registry_loader.normalize_help_flag_token(token)
        for token in help_spec.get("flags", []) or []
        if registry_loader.normalize_help_flag_token(token)
    }
    subcommands = {
        str(token or "").strip().lower()
        for token in help_spec.get("subcommands", []) or []
        if str(token or "").strip()
    }
    if flags and any(registry_loader.normalize_help_flag_token(token) in flags for token in tokens[1:]):
        return True
    return bool(len(tokens) > 1 and tokens[1].lower() in subcommands)


def is_help_invocation(command: str, root: str | None = None, registry: dict | None = None) -> bool:
    """Return True when a command matches registry-declared help invocation metadata."""
    tokens = split_command_argv(command)
    resolved_root = str(root if root is not None else (tokens[0] if tokens else "")).strip().lower()
    entry = _entry_for_command_root(resolved_root, registry)
    help_spec = entry.get("help") if isinstance(entry, dict) else None
    return is_help_invocation_for_spec(command, help_spec, root=resolved_root)


def _attach_workspace_autocomplete_flags(spec: dict, workspace_flags: list[dict[str, object]]) -> dict:
    """Mark value-taking autocomplete flags that should use live session files."""
    read_flags = [
        str(item.get("flag") or "")
        for item in workspace_flags
        if isinstance(item, dict)
        and item.get("mode") == "read"
        and item.get("kind") != "directory"
        and item.get("flag")
    ]
    if not read_flags:
        return spec

    def _relevant_flags(target_spec: dict, subcommand: str = "") -> list[str]:
        expects = {str(token) for token in target_spec.get("expects_value", []) or []}
        hints = {str(token) for token in (target_spec.get("arg_hints") or {})}
        relevant = []
        for item in workspace_flags:
            if not isinstance(item, dict) or item.get("mode") != "read" or item.get("kind") == "directory":
                continue
            flag = str(item.get("flag") or "")
            if not flag:
                continue
            raw_subcommands = item.get("subcommands")
            subcommands = (
                {str(value) for value in raw_subcommands}
                if isinstance(raw_subcommands, (list, tuple, set))
                else set()
            )
            if subcommand and subcommands and subcommand not in subcommands:
                continue
            if flag in expects or flag in hints:
                relevant.append(flag)
        return _dedupe_preserve_order(relevant)

    root_flags = _relevant_flags(spec)
    if root_flags:
        spec["workspace_file_flags"] = root_flags
    for subcommand, sub_spec in (spec.get("subcommands") or {}).items():
        if not isinstance(sub_spec, dict):
            continue
        sub_flags = _relevant_flags(sub_spec, str(subcommand))
        if sub_flags:
            sub_spec["workspace_file_flags"] = sub_flags
    return spec


def load_autocomplete_context_from_commands_registry(cfg=None) -> dict:
    """Read autocomplete metadata from commands.yaml and app-owned built-ins."""
    external = autocomplete_context_from_commands_registry(load_commands_registry(), cfg=cfg)
    builtins = autocomplete_context_from_commands_registry(load_builtin_autocomplete_registry(), cfg=cfg)
    return _merge_autocomplete_context(external, builtins)


def _feature_enabled(feature, cfg=None):
    return feature_enabled(feature, cfg)


def is_feature_required_enabled(feature_required: object, cfg=None) -> bool:
    """Return True if all features in *feature_required* are enabled on this instance.

    Accepts the normalized ``feature_required`` value from a catalog entry —
    ``None``, a single feature-name string, or a list of feature names.
    An entry with ``feature_required=None`` is always considered enabled.
    Unknown feature names default to enabled so future features do not
    accidentally suppress discovery on older app versions.
    """
    if not feature_required:
        return True
    features = list(feature_required) if isinstance(feature_required, (list, tuple)) else [feature_required]
    return all(_feature_enabled(f, cfg) for f in features)


def _faq_entry_enabled(item, cfg=None):
    return registry_faq._faq_entry_enabled(item, cfg)


def load_faq(cfg=None):
    """Read faq.yaml and return a list of {question, answer} dicts.
    Returns an empty list if the file doesn't exist or contains no valid entries."""
    return registry_faq.load_faq(FAQ_FILE, cfg, load_yaml_list_with_local=_load_yaml_list_with_local)


def load_all_faq(app_name="darklab_shell", project_readme=None, cfg=None):
    """Return the built-in FAQ entries followed by any custom faq.yaml entries."""
    return registry_faq.load_all_faq(
        FAQ_FILE,
        app_name,
        project_readme,
        cfg,
        load_yaml_list_with_local=_load_yaml_list_with_local,
    )


def _builtin_workflows():
    return registry_content.builtin_workflows()


def _workflow_tokens(value: str) -> set[str]:
    return registry_content.workflow_tokens(value)


def _render_workflow_text(value: str, inputs: dict[str, str]) -> str:
    return registry_content.render_workflow_text(value, inputs)


def normalize_workflow_entry(entry):
    """Return a normalized workflow entry or None when the payload is invalid."""
    return registry_content.normalize_workflow_entry(entry)


def _workflow_entry_enabled(entry, cfg=None):
    return _suggestion_enabled_for_features(entry, cfg)


def load_workflows():
    """Read workflows.yaml and return a list of workflow dicts."""
    return registry_content.load_workflows(WORKFLOWS_FILE, local_path=_local_overlay_path(WORKFLOWS_FILE))


def load_all_workflows(cfg=None):
    """Return the built-in workflows followed by any custom workflows.yaml entries."""
    return registry_content.load_all_workflows(
        WORKFLOWS_FILE,
        cfg,
        suggestion_enabled_for_features=_suggestion_enabled_for_features,
        local_path=_local_overlay_path(WORKFLOWS_FILE),
    )


def load_welcome():
    """Read welcome.yaml and return startup blocks for the welcome typeout.
    Returns an empty list if the file is missing or empty, disabling the welcome animation."""
    return registry_content.load_welcome(WELCOME_FILE, local_path=_local_overlay_path(WELCOME_FILE))


def load_tour(cfg=None, *, mobile: bool = False) -> TourPayload:
    """Read tour.yaml and return the visible onboarding tour chapters.

    Missing tour.yaml returns an empty disabled tour. Invalid files raise a
    ValueError so docs/tests catch stale or malformed chapter content.
    """
    return registry_content.load_tour(TOUR_FILE, cfg, mobile=mobile)


def load_ascii_art():
    """Read ascii.txt and return the welcome banner art as plain text.
    Returns an empty string if the file is missing or empty."""
    return registry_content.load_ascii_art(ASCII_FILE, local_path=_local_overlay_path(ASCII_FILE))


def load_ascii_mobile_art():
    """Read ascii_mobile.txt and return the compact mobile banner art."""
    return registry_content.load_ascii_art(ASCII_MOBILE_FILE, local_path=_local_overlay_path(ASCII_MOBILE_FILE))


def load_welcome_hints(cfg=None):
    """Read app_hints.txt and return enabled app-usage hints."""
    return registry_content.load_scoped_hints(APP_HINTS_FILE, cfg, local_path=_local_overlay_path(APP_HINTS_FILE))


def load_mobile_welcome_hints(cfg=None):
    """Read app_hints_mobile.txt and return enabled mobile-specific hints."""
    return registry_content.load_scoped_hints(
        APP_HINTS_MOBILE_FILE, cfg, local_path=_local_overlay_path(APP_HINTS_MOBILE_FILE)
    )


def _suggestion_interactive_enabled(item) -> bool:
    return registry_autocomplete._suggestion_interactive_enabled(item)


def _suggestion_required_features(item) -> list[str]:
    return registry_autocomplete._suggestion_required_features(item)


def _normalize_context_suggestion(item):
    return registry_autocomplete._normalize_context_suggestion(item)


def _normalize_smoke_metadata(raw_value):
    return registry_autocomplete._normalize_smoke_metadata(raw_value)


def _suggestion_enabled_for_features(item, cfg=None) -> bool:
    return registry_autocomplete._suggestion_enabled_for_features(item, cfg)


def _filter_autocomplete_context_by_features(context: dict, cfg=None) -> dict:
    return registry_autocomplete._filter_autocomplete_context_by_features(context, cfg)


def _normalize_single_autocomplete_spec(raw_spec: dict, *, include_pipe: bool = True) -> dict:
    return registry_autocomplete._normalize_single_autocomplete_spec(raw_spec, include_pipe=include_pipe)


def _normalize_autocomplete_context(data):
    return registry_autocomplete._normalize_autocomplete_context(data)


def _merge_autocomplete_context(base, overlay):
    return registry_autocomplete._merge_autocomplete_context(base, overlay)


def _spread_sensitive_smoke_commands(commands: list[str]) -> list[str]:
    return registry_smoke.spread_sensitive_smoke_commands(commands)


def load_container_smoke_test_commands():
    """Return the user-facing smoke-test corpus from registry examples and workflows."""
    return registry_smoke.load_container_smoke_test_commands(
        load_autocomplete_context=load_autocomplete_context_from_commands_registry,
        load_workflows=load_all_workflows,
        workflow_tokens=_workflow_tokens,
        render_workflow_text=_render_workflow_text,
        is_help_invocation_for_spec=is_help_invocation_for_spec,
        suggestion_enabled_for_features=_suggestion_enabled_for_features,
    )


def _feature_required_includes(item: dict, feature: str) -> bool:
    return registry_smoke.feature_required_includes(
        item,
        feature,
        suggestion_required_features=_suggestion_required_features,
    )


def load_container_smoke_test_interactive_commands():
    """Return interactive PTY examples for the dedicated smoke-test corpus."""
    return registry_smoke.load_container_smoke_test_interactive_commands(
        load_autocomplete_context=load_autocomplete_context_from_commands_registry,
        suggestion_enabled_for_features=_suggestion_enabled_for_features,
        suggestion_required_features=_suggestion_required_features,
    )


def _runtime_injection_blocked(tokens: list[str], inject: dict[str, object]) -> bool:
    return registry_runtime.runtime_injection_blocked(tokens, inject)


def _runtime_injection_token(
    token: str,
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> str:
    return registry_runtime.runtime_injection_token(
        token,
        session_id=session_id,
        cfg=cfg,
        owner_context=owner_context,
    )


def _runtime_injection_flags(
    inject: dict[str, object],
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> list[str]:
    return registry_runtime.runtime_injection_flags(
        inject,
        session_id=session_id,
        cfg=cfg,
        owner_context=owner_context,
    )


def _apply_runtime_inject_flags(
    command: str,
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> tuple[str, str | None]:
    return registry_runtime.apply_runtime_inject_flags(
        command,
        runtime_adaptations_by_root=_runtime_adaptations_by_root,
        session_id=session_id,
        cfg=cfg or app_config.CFG,
        owner_context=owner_context,
    )


def resolve_runtime_command(command_name: str) -> str | None:
    """Return the absolute path to command_name if installed on this instance."""
    return _resolve_runtime_command(command_name)


def runtime_missing_command_name(command: str) -> str | None:
    """Return the missing root command name for a command string, or None if installed/empty."""
    tokens = split_command_argv(command)
    root = tokens[0].strip().lower() if tokens else None
    if root == "env":
        for token in tokens[1:]:
            if "=" in token and not token.startswith("-"):
                continue
            root = token.strip().lower()
            break
        else:
            root = None
    if not root:
        return None
    return None if resolve_runtime_command(root) else root


def runtime_missing_command_message(command_name: str) -> str:
    """Return the standard instance-level message for missing runtime commands."""
    return _runtime_missing_command_message(command_name)


def split_chained_commands(command: str) -> list[str]:
    """Split a command string on any shell chaining/piping/redirection operator."""
    return _split_chained_commands(command)


def _is_allowed_by_policy(command_tokens: list[str], allowed: list[str], allow_grouping: dict[str, set[str]]) -> bool:
    return is_allowed_by_policy(command_tokens, allowed, allow_grouping)


def _is_denied(command: str, deny_entries: list[str], *, exempt_flags: set[str] | None = None) -> bool:
    return is_denied(command, deny_entries, exempt_flags=exempt_flags)


def _nmap_raw_scan_restriction_reason(command: str) -> str:
    return nmap_raw_scan_restriction_reason(command)


def _workspace_flag_specs_by_root() -> dict[str, list[dict[str, object]]]:
    return registry_workspace.workspace_flag_specs_by_root(load_commands_registry)


def _runtime_adaptations_by_root() -> dict[str, dict[str, object]]:
    return registry_workspace.runtime_adaptations_by_root(load_commands_registry)


def _workspace_flag_applies_to_command(spec: dict[str, object], tokens: list[str]) -> bool:
    return registry_workspace.workspace_flag_applies_to_command(spec, tokens)


def _managed_workspace_directory_applies(spec: dict[str, object], tokens: list[str]) -> bool:
    return registry_workspace.managed_workspace_directory_applies(spec, tokens)


def _managed_workspace_directory_for_root(root: str) -> dict[str, object]:
    return registry_workspace.managed_workspace_directory_for_root(
        root,
        runtime_adaptations_by_root=_runtime_adaptations_by_root,
    )


def _workspace_flag_matches_token(token: str, spec: dict[str, object]) -> bool:
    return registry_workspace.workspace_flag_matches_token(token, spec)


def _wget_has_directory_prefix(tokens: list[str]) -> bool:
    return registry_workspace.wget_has_directory_prefix(tokens)


def _workspace_flag_value(tokens: list[str], index: int, spec: dict[str, object]) -> tuple[str | None, int | None, str | None]:
    return registry_workspace.workspace_flag_value(tokens, index, spec)


def _normalize_workspace_command_path(value: str, cwd: str = "") -> str:
    return registry_workspace.normalize_workspace_command_path(value, cwd)


def _invalid_workspace_file_path_reason(value: str, detail: str = "") -> str:
    return registry_workspace.invalid_workspace_file_path_reason(value, detail)


def _absolute_workspace_flag_path_error(value: str) -> str:
    return registry_workspace.absolute_workspace_flag_path_error(value)


def _workspace_owner_context(session_id: str, owner_context: OwnerContext | None = None) -> OwnerContext:
    return registry_workspace.workspace_owner_context(session_id, owner_context)


def _workspace_flag_absolute_passthrough(value: str, mode: str) -> bool:
    return registry_workspace.workspace_flag_absolute_passthrough(value, mode)


def _wget_default_directory_prefix(
    session_id: str,
    cfg: Mapping[str, Any],
    workspace_cwd: str,
    *,
    owner_context: OwnerContext | None = None,
) -> tuple[str, str]:
    return registry_workspace.wget_default_directory_prefix(
        session_id,
        cfg,
        workspace_cwd,
        owner_context=owner_context,
    )


def _restricted_command_networks(cfg: Mapping[str, Any] | None = None) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    active_cfg = cfg or app_config.CFG
    raw_values = active_cfg.get("restricted_command_input_cidrs") or []
    if isinstance(raw_values, str):
        raw_values = [raw_values]
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw_value in raw_values if isinstance(raw_values, list) else []:
        value = str(raw_value or "").strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _value_type_is_restrictable(value_type: str) -> bool:
    return registry_targets.value_type_is_restrictable(value_type)


def _dict_value(data: dict[str, object], key: str) -> dict:
    return registry_targets._dict_value(data, key)


def _list_value(data: dict[str, object], key: str) -> list:
    return registry_targets._list_value(data, key)


def _autocomplete_value_type_from_hint(spec: dict[str, object], trigger: str) -> str:
    return registry_targets.autocomplete_value_type_from_hint(spec, trigger)


def _autocomplete_flag_value_types(spec: dict[str, object]) -> dict[str, str]:
    return registry_targets.autocomplete_flag_value_types(spec)


def _autocomplete_positional_value_types(spec: dict[str, object]) -> list[str]:
    return registry_targets.autocomplete_positional_value_types(spec)


def _autocomplete_positional_project_target_value_types(spec: dict[str, object]) -> list[str]:
    return registry_targets.autocomplete_positional_project_target_value_types(spec)


def _autocomplete_value_flag_types(spec: dict[str, object]) -> dict[str, str]:
    return registry_targets.autocomplete_value_flag_types(spec)


def _autocomplete_hint_marks_target_list_file(hint: dict) -> bool:
    return registry_targets._autocomplete_hint_marks_target_list_file(hint)


def _autocomplete_project_target_flag_specs(spec: dict[str, object]) -> dict[str, dict[str, object]]:
    return registry_targets._autocomplete_project_target_flag_specs(spec)


def command_project_target_inputs(command: str, cfg: Mapping[str, Any] | None = None) -> list[dict[str, str]]:
    """Return registry-typed command inputs that can become project targets."""
    return registry_targets.command_project_target_inputs(
        command,
        cfg,
        load_autocomplete_context=load_autocomplete_context_from_commands_registry,
    )


def _autocomplete_spec_needs_normalization(spec: dict[str, object]) -> bool:
    return registry_targets.autocomplete_spec_needs_normalization(spec)


def _autocomplete_spec_for_tokens(tokens: list[str], cfg: Mapping[str, Any] | None = None) -> tuple[dict[str, object], int]:
    return registry_targets.autocomplete_spec_for_tokens(
        tokens,
        cfg,
        load_autocomplete_context=load_autocomplete_context_from_commands_registry,
    )


def _flag_value_from_token(tokens: list[str], index: int, flag: str) -> tuple[str | None, int | None]:
    return registry_targets.flag_value_from_token(tokens, index, flag)


def _candidate_host_tokens(value: str) -> list[str]:
    return registry_targets.candidate_host_tokens(value)


def _restricted_value_match(value: str, networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> str | None:
    return registry_targets.restricted_value_match(value, networks)


def _restricted_input_reason(value: str) -> str:
    return registry_targets.restricted_input_reason(value)


def _restricted_inline_input_reason(command: str, cfg: Mapping[str, Any] | None = None) -> str:
    networks = _restricted_command_networks(cfg)
    return registry_targets.restricted_inline_input_reason(
        command,
        cfg,
        networks=networks,
        load_autocomplete_context=load_autocomplete_context_from_commands_registry,
    )


def _workspace_read_file_restriction_reason(
    command: str,
    session_id: str,
    cfg: Mapping[str, Any] | None = None,
    *,
    workspace_cwd: str = "",
    owner_context: OwnerContext | None = None,
) -> str:
    networks = _restricted_command_networks(cfg)
    return registry_workspace.workspace_read_file_restriction_reason(
        command,
        session_id,
        cfg,
        workspace_cwd=workspace_cwd,
        owner_context=owner_context,
        networks=networks,
        load_commands_registry=load_commands_registry,
        load_autocomplete_context=load_autocomplete_context_from_commands_registry,
    )


def _reserved_interactive_deny_matches(command: str, deny_entries: list[str]) -> bool:
    command_tokens = split_command_argv(command)
    if "--interactive" not in command_tokens:
        return False
    return is_denied(
        command,
        [entry for entry in deny_entries if "--interactive" in split_command_argv(entry)],
    )


def _trufflehog_git_uri_restriction_reason(command: str) -> str:
    tokens = split_command_argv(command)
    if len(tokens) < 3 or tokens[0].lower() != "trufflehog" or tokens[1].lower() != "git":
        return ""
    value_flags = {
        "--branch",
        "--exclude-globs",
        "--exclude-paths",
        "--include-paths",
        "--max-depth",
        "--since-commit",
    }
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token in value_flags:
            index += 2
            continue
        if any(token.startswith(f"{flag}=") for flag in value_flags):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if token.lower().startswith("https://"):
            return ""
        return "trufflehog git scans must use an HTTPS repository URL."
    return ""


def _puredns_resolver_restriction_reason(command: str) -> str:
    tokens = split_command_argv(command)
    if len(tokens) < 2 or tokens[0].lower() != "puredns" or tokens[1].lower() != "bruteforce":
        return ""
    if any(token in {"-r", "--resolvers"} or token.startswith("--resolvers=") for token in tokens[2:]):
        return ""
    return "puredns bruteforce requires --resolvers with a session resolver file."


def _rewrite_workspace_file_flags(
    command: str,
    session_id: str,
    cfg: Mapping[str, Any] | None = None,
    *,
    workspace_cwd: str = "",
    owner_context: OwnerContext | None = None,
) -> tuple[str, set[str], list[str], list[str], list[str], str]:
    return registry_workspace.rewrite_workspace_file_flags(
        command,
        session_id,
        cfg,
        workspace_cwd=workspace_cwd,
        owner_context=owner_context,
        load_commands_registry=load_commands_registry,
        runtime_adaptations_by_root=_runtime_adaptations_by_root,
    )


def _runtime_environment_value(template: str, tokens: list[str], env_spec: dict[str, object]) -> str:
    return registry_runtime.runtime_environment_value(template, tokens, env_spec)


def _apply_workspace_runtime_environment(command: str, cfg: Mapping[str, Any] | None = None) -> str:
    return registry_runtime.apply_workspace_runtime_environment(
        command,
        runtime_adaptations_by_root=_runtime_adaptations_by_root,
        cfg=cfg or app_config.CFG,
    )


def validate_command(
    command: str,
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    workspace_cwd: str = "",
    extra_allowed_prefixes: list[str] | None = None,
    owner_context: OwnerContext | None = None,
) -> CommandValidationResult:
    """Validate a command and return the display command plus execution command.

    Workspace-aware file/directory flags are still denied by default. When
    workspace storage is enabled, declared workspace flags are validated and
    rewritten to the active owner workspace before deny-prefix checks run.
    """
    return registry_validate.validate_command(
        command,
        result_cls=CommandValidationResult,
        load_command_policy=load_command_policy,
        load_allow_grouping_flags=load_allow_grouping_flags,
        restricted_inline_input_reason=_restricted_inline_input_reason,
        reserved_interactive_deny_matches=_reserved_interactive_deny_matches,
        trufflehog_git_uri_restriction_reason=_trufflehog_git_uri_restriction_reason,
        puredns_resolver_restriction_reason=_puredns_resolver_restriction_reason,
        rewrite_workspace_file_flags=_rewrite_workspace_file_flags,
        workspace_read_file_restriction_reason=_workspace_read_file_restriction_reason,
        apply_workspace_runtime_environment=_apply_workspace_runtime_environment,
        session_id=session_id,
        cfg=cfg,
        workspace_cwd=workspace_cwd,
        extra_allowed_prefixes=extra_allowed_prefixes,
        owner_context=owner_context,
    )


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Return (allowed, reason) for legacy callers."""
    result = validate_command(command)
    return result.allowed, result.reason


def rewrite_command(
    command: str,
    *,
    session_id: str = "",
    cfg: Mapping[str, Any] | None = None,
    owner_context: OwnerContext | None = None,
) -> tuple[str, str | None]:
    """Rewrite commands that need a TTY or specific flags into a safe non-interactive equivalent.
    Returns (rewritten_command, notice_message_or_None)."""
    return _apply_runtime_inject_flags(command, session_id=session_id, cfg=cfg, owner_context=owner_context)
