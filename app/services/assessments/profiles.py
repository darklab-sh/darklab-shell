# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Versioned assessment-profile catalog loading and validation."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from typing import Any

import yaml

import config as app_config
import config_paths
from services.projects.contracts import ProjectWorkspaceError


ASSESSMENT_PROFILE_CATALOG_VERSION = 1
ASSESSMENT_PROFILE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ASSESSMENT_PROFILE_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}$")
ASSESSMENT_COMPATIBLE_VERSION_RE = re.compile(r"^[0-9A-Za-z*<>=., _+\-]{1,64}$")
ASSESSMENT_TARGET_TYPES = frozenset({"domain", "ip", "port", "url"})
ASSESSMENT_EVIDENCE_TYPES = frozenset({
    "run",
    "workflow_execution",
    "finding",
    "atlas_entity",
    "run_artifact",
    "workspace_artifact",
    "screenshot",
})
ASSESSMENT_POLICY_LEVELS = frozenset({"safe", "standard", "intrusive", "destructive"})
ASSESSMENT_TARGET_MATCHES = frozenset({"exact", "host_or_descendant", "project_scope"})
ASSESSMENT_COMPLETION_CONDITIONS = frozenset({
    "available",
    "finding_present",
    "succeeded",
})
ASSESSMENT_STRUCTURED_OUTPUT_KINDS = frozenset({
    "artifacts",
    "dns_records",
    "entities",
    "findings",
    "http_responses",
    "ports",
    "screenshots",
    "services",
    "tls",
})
ASSESSMENT_PROFILE_MAX_PROFILES = 25
ASSESSMENT_PROFILE_MAX_CHECKS = 100
ASSESSMENT_PROFILE_MAX_RULES = 10
ASSESSMENT_PROFILE_MAX_LIST_ITEMS = 32
ASSESSMENT_PROFILE_LABEL_MAX_LEN = 120
ASSESSMENT_PROFILE_PURPOSE_MAX_LEN = 1000
ASSESSMENT_PROFILE_GUIDANCE_MAX_LEN = 2000
ASSESSMENT_PROFILE_ACTION_MAX_LEN = 200

_PROFILE_FIELDS = frozenset({"key", "version", "label", "purpose", "target_types", "checks"})
_CHECK_FIELDS = frozenset({
    "key",
    "version",
    "category",
    "label",
    "purpose",
    "target_types",
    "evidence_rules",
    "policy_level",
    "recommended_action",
    "completion_guidance",
})
_EVIDENCE_RULE_FIELDS = frozenset({
    "key",
    "version",
    "evidence_types",
    "command_roots",
    "workflow_actions",
    "structured_output_kinds",
    "target_match",
    "completion",
    "compatible_versions",
    "negative_evidence",
})

log = logging.getLogger(__name__)


class AssessmentProfileCatalogError(ProjectWorkspaceError):
    """Raised when an assessment-profile catalog is invalid."""


@dataclass(frozen=True)
class AssessmentProfileCatalog:
    source_path: str
    local_path: str
    local_profile_keys: tuple[str, ...]
    profiles: tuple[dict[str, Any], ...]


_CATALOG_CACHE: dict[tuple[str, str], dict[str, object]] = {}


def default_assessment_profiles_path() -> Path:
    return config_paths.config_asset_paths(
        "assessment_profiles.yaml",
        shipped_conf_dir=app_config.APP_CONF_DIR or None,
        local_conf_dir=app_config.APP_LOCAL_CONF_DIR or None,
    ).shipped


def configured_assessment_profile_paths() -> config_paths.ConfigAssetPaths:
    return config_paths.config_asset_paths(
        "assessment_profiles.yaml",
        shipped_conf_dir=app_config.APP_CONF_DIR or None,
        local_conf_dir=app_config.APP_LOCAL_CONF_DIR or None,
    )


def _catalog_signature(path: Path) -> tuple[str, int | None, int | None]:
    normalized = os.path.abspath(path)
    try:
        stat = os.stat(normalized)
    except OSError:
        return normalized, None, None
    return normalized, stat.st_mtime_ns, stat.st_size


def _catalog_error(message: str) -> AssessmentProfileCatalogError:
    return AssessmentProfileCatalogError(f"assessment profile catalog {message}")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _catalog_error(f"{label} must be an object")
    return value


def _reject_unknown_fields(value: dict[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(str(field) for field in value if field not in allowed)
    if unknown:
        raise _catalog_error(f"{label} has unknown fields: {', '.join(unknown)}")


def _required_text(value: object, label: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _catalog_error(f"{label} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise _catalog_error(f"{label} exceeds {max_length} characters")
    return normalized


def _stable_key(value: object, label: str) -> str:
    normalized = _required_text(value, label, 64).lower()
    if not ASSESSMENT_PROFILE_KEY_RE.fullmatch(normalized):
        raise _catalog_error(
            f"{label} must use lowercase letters, numbers, underscores, or hyphens"
        )
    return normalized


def _version(value: object, label: str) -> str:
    normalized = _required_text(value, label, 20)
    if not ASSESSMENT_PROFILE_VERSION_RE.fullmatch(normalized):
        raise _catalog_error(f"{label} must be a numeric dotted version")
    return normalized


def _string_list(
    value: object,
    label: str,
    *,
    allowed: frozenset[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise _catalog_error(f"{label} must be a list")
    if len(value) > ASSESSMENT_PROFILE_MAX_LIST_ITEMS:
        raise _catalog_error(f"{label} exceeds the item cap")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _required_text(item, label, 128).lower()
        if allowed is not None and normalized not in allowed:
            raise _catalog_error(f"{label} contains unsupported value: {normalized}")
        if normalized in seen:
            raise _catalog_error(f"{label} contains duplicate value: {normalized}")
        seen.add(normalized)
        result.append(normalized)
    if not result and not allow_empty:
        raise _catalog_error(f"{label} must not be empty")
    return result


def _known_action_references() -> tuple[frozenset[str], frozenset[str]]:
    # Import lazily so catalog validation does not make command/workflow loading
    # part of module import or app-factory setup.
    from services.commands.registry import load_all_workflows, load_commands_registry  # noqa: PLC0415

    registry = load_commands_registry()
    command_roots = frozenset(
        str(entry.get("root") or "").strip().lower()
        for entry in registry.get("commands", [])
        if isinstance(entry, dict) and str(entry.get("root") or "").strip()
    )
    workflow_ids = frozenset(
        str(entry.get("id") or "").strip()
        for entry in load_all_workflows(app_config.CFG)
        if str(entry.get("id") or "").strip()
    )
    return command_roots, workflow_ids


def _recommended_action(
    value: object,
    *,
    known_command_roots: frozenset[str],
    known_workflow_ids: frozenset[str],
) -> str:
    action = _required_text(value, "recommended_action", ASSESSMENT_PROFILE_ACTION_MAX_LEN)
    kind, separator, identifier = action.partition(":")
    if not separator or not identifier:
        raise _catalog_error("recommended_action must use command:<root> or workflow:<id>")
    if kind == "command" and identifier in known_command_roots:
        return action
    if kind == "workflow" and identifier in known_workflow_ids:
        return action
    raise _catalog_error(f"recommended_action references unknown {kind or 'action'}: {identifier}")


def _normalize_evidence_rule(
    value: object,
    *,
    known_command_roots: frozenset[str],
    known_workflow_ids: frozenset[str],
) -> dict[str, Any]:
    rule = _mapping(value, "evidence rule")
    _reject_unknown_fields(rule, _EVIDENCE_RULE_FIELDS, "evidence rule")
    command_roots = _string_list(
        rule.get("command_roots", []),
        "evidence rule command_roots",
        allow_empty=True,
    )
    unknown_commands = sorted(set(command_roots) - known_command_roots)
    if unknown_commands:
        raise _catalog_error(
            f"evidence rule command_roots contains unknown commands: {', '.join(unknown_commands)}"
        )
    workflow_actions = _string_list(
        rule.get("workflow_actions", []),
        "evidence rule workflow_actions",
        allow_empty=True,
    )
    unknown_workflows = sorted(set(workflow_actions) - known_workflow_ids)
    if unknown_workflows:
        raise _catalog_error(
            f"evidence rule workflow_actions contains unknown workflows: {', '.join(unknown_workflows)}"
        )
    compatible_versions = _string_list(
        rule.get("compatible_versions", ["*"]),
        "evidence rule compatible_versions",
    )
    if any(not ASSESSMENT_COMPATIBLE_VERSION_RE.fullmatch(item) for item in compatible_versions):
        raise _catalog_error("evidence rule compatible_versions contains an invalid constraint")
    negative_evidence = rule.get("negative_evidence", False)
    if not isinstance(negative_evidence, bool):
        raise _catalog_error("evidence rule negative_evidence must be true or false")
    return {
        "key": _stable_key(rule.get("key"), "evidence rule key"),
        "version": _version(rule.get("version"), "evidence rule version"),
        "evidence_types": _string_list(
            rule.get("evidence_types"),
            "evidence rule evidence_types",
            allowed=ASSESSMENT_EVIDENCE_TYPES,
        ),
        "command_roots": command_roots,
        "workflow_actions": workflow_actions,
        "structured_output_kinds": _string_list(
            rule.get("structured_output_kinds", []),
            "evidence rule structured_output_kinds",
            allowed=ASSESSMENT_STRUCTURED_OUTPUT_KINDS,
            allow_empty=True,
        ),
        "target_match": _required_text(rule.get("target_match"), "evidence rule target_match", 32).lower(),
        "completion": _required_text(rule.get("completion"), "evidence rule completion", 32).lower(),
        "compatible_versions": compatible_versions,
        "negative_evidence": negative_evidence,
    }


def _validate_evidence_rule_choices(rule: dict[str, Any]) -> None:
    if rule["target_match"] not in ASSESSMENT_TARGET_MATCHES:
        raise _catalog_error(f"evidence rule target_match is unsupported: {rule['target_match']}")
    if rule["completion"] not in ASSESSMENT_COMPLETION_CONDITIONS:
        raise _catalog_error(f"evidence rule completion is unsupported: {rule['completion']}")
    if not any((rule["command_roots"], rule["workflow_actions"], rule["structured_output_kinds"])):
        if set(rule["evidence_types"]) <= {"run", "workflow_execution"}:
            raise _catalog_error("run evidence rules must declare a command, workflow, or output matcher")


def _normalize_check(
    value: object,
    *,
    profile_target_types: set[str],
    known_command_roots: frozenset[str],
    known_workflow_ids: frozenset[str],
) -> dict[str, Any]:
    check = _mapping(value, "profile check")
    _reject_unknown_fields(check, _CHECK_FIELDS, "profile check")
    target_types = _string_list(
        check.get("target_types"),
        "profile check target_types",
        allowed=ASSESSMENT_TARGET_TYPES,
    )
    if not set(target_types).issubset(profile_target_types):
        raise _catalog_error("profile check target_types must be included in the profile target_types")
    raw_rules = check.get("evidence_rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise _catalog_error("profile check evidence_rules must be a non-empty list")
    if len(raw_rules) > ASSESSMENT_PROFILE_MAX_RULES:
        raise _catalog_error("profile check exceeds the evidence-rule cap")
    rules = []
    seen_rule_keys: set[str] = set()
    for raw_rule in raw_rules:
        rule = _normalize_evidence_rule(
            raw_rule,
            known_command_roots=known_command_roots,
            known_workflow_ids=known_workflow_ids,
        )
        _validate_evidence_rule_choices(rule)
        if rule["key"] in seen_rule_keys:
            raise _catalog_error(f"duplicate evidence rule key: {rule['key']}")
        seen_rule_keys.add(rule["key"])
        rules.append(rule)
    policy_level = _required_text(check.get("policy_level"), "policy_level", 32).lower()
    if policy_level not in ASSESSMENT_POLICY_LEVELS:
        raise _catalog_error(f"unsupported policy_level: {policy_level}")
    return {
        "key": _stable_key(check.get("key"), "profile check key"),
        "version": _version(check.get("version"), "profile check version"),
        "category": _stable_key(check.get("category"), "profile check category"),
        "label": _required_text(check.get("label"), "profile check label", ASSESSMENT_PROFILE_LABEL_MAX_LEN),
        "purpose": _required_text(
            check.get("purpose"), "profile check purpose", ASSESSMENT_PROFILE_PURPOSE_MAX_LEN
        ),
        "target_types": target_types,
        "evidence_rules": rules,
        "policy_level": policy_level,
        "recommended_action": _recommended_action(
            check.get("recommended_action"),
            known_command_roots=known_command_roots,
            known_workflow_ids=known_workflow_ids,
        ),
        "completion_guidance": _required_text(
            check.get("completion_guidance"),
            "profile check completion_guidance",
            ASSESSMENT_PROFILE_GUIDANCE_MAX_LEN,
        ),
    }


def _normalize_profile(
    value: object,
    *,
    known_command_roots: frozenset[str],
    known_workflow_ids: frozenset[str],
) -> dict[str, Any]:
    profile = _mapping(value, "profile")
    _reject_unknown_fields(profile, _PROFILE_FIELDS, "profile")
    target_types = _string_list(
        profile.get("target_types"),
        "profile target_types",
        allowed=ASSESSMENT_TARGET_TYPES,
    )
    raw_checks = profile.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise _catalog_error("profile checks must be a non-empty list")
    if len(raw_checks) > ASSESSMENT_PROFILE_MAX_CHECKS:
        raise _catalog_error("profile exceeds the check cap")
    checks = []
    seen_check_keys: set[str] = set()
    for raw_check in raw_checks:
        check = _normalize_check(
            raw_check,
            profile_target_types=set(target_types),
            known_command_roots=known_command_roots,
            known_workflow_ids=known_workflow_ids,
        )
        if check["key"] in seen_check_keys:
            raise _catalog_error(f"duplicate profile check key: {check['key']}")
        seen_check_keys.add(check["key"])
        checks.append(check)
    return {
        "key": _stable_key(profile.get("key"), "profile key"),
        "version": _version(profile.get("version"), "profile version"),
        "label": _required_text(profile.get("label"), "profile label", ASSESSMENT_PROFILE_LABEL_MAX_LEN),
        "purpose": _required_text(profile.get("purpose"), "profile purpose", ASSESSMENT_PROFILE_PURPOSE_MAX_LEN),
        "target_types": target_types,
        "checks": checks,
    }


def normalize_assessment_profile_catalog(
    data: object,
    *,
    source_path: str = "",
    local_path: str = "",
    known_command_roots: Iterable[str] | None = None,
    known_workflow_ids: Iterable[str] | None = None,
    allow_empty: bool = False,
) -> AssessmentProfileCatalog:
    root = _mapping(data, "root")
    _reject_unknown_fields(root, frozenset({"version", "profiles"}), "root")
    catalog_version = root.get("version")
    if (
        not isinstance(catalog_version, int)
        or isinstance(catalog_version, bool)
        or catalog_version != ASSESSMENT_PROFILE_CATALOG_VERSION
    ):
        raise _catalog_error(f"version must be {ASSESSMENT_PROFILE_CATALOG_VERSION}")
    raw_profiles = root.get("profiles")
    if not isinstance(raw_profiles, list):
        raise _catalog_error("profiles must be a list")
    if len(raw_profiles) > ASSESSMENT_PROFILE_MAX_PROFILES:
        raise _catalog_error("exceeds the profile cap")
    if not raw_profiles and not allow_empty:
        raise _catalog_error("must define at least one profile")
    if known_command_roots is None or known_workflow_ids is None:
        default_commands, default_workflows = _known_action_references()
        known_command_roots = default_commands if known_command_roots is None else known_command_roots
        known_workflow_ids = default_workflows if known_workflow_ids is None else known_workflow_ids
    command_roots = frozenset(str(value).strip().lower() for value in known_command_roots)
    workflow_ids = frozenset(str(value).strip() for value in known_workflow_ids)
    profiles = []
    seen_profile_keys: set[str] = set()
    for raw_profile in raw_profiles:
        profile = _normalize_profile(
            raw_profile,
            known_command_roots=command_roots,
            known_workflow_ids=workflow_ids,
        )
        if profile["key"] in seen_profile_keys:
            raise _catalog_error(f"duplicate profile key: {profile['key']}")
        seen_profile_keys.add(profile["key"])
        profiles.append(profile)
    return AssessmentProfileCatalog(
        source_path=source_path,
        local_path=local_path,
        local_profile_keys=tuple(),
        profiles=tuple(profiles),
    )


def _load_yaml(path: Path, *, required: bool) -> object | None:
    try:
        with path.open(encoding="utf-8") as source:
            return yaml.safe_load(source)
    except FileNotFoundError:
        if not required:
            return None
        raise _catalog_error(f"is missing: {path}") from None
    except yaml.YAMLError as exc:
        raise _catalog_error(f"contains invalid YAML ({type(exc).__name__})") from None


def _merge_catalogs(
    shipped: AssessmentProfileCatalog,
    local: AssessmentProfileCatalog,
    *,
    local_path: Path,
) -> AssessmentProfileCatalog:
    profiles_by_key = {str(profile["key"]): profile for profile in shipped.profiles}
    order = [str(profile["key"]) for profile in shipped.profiles]
    local_keys = []
    for profile in local.profiles:
        key = str(profile["key"])
        if key not in profiles_by_key:
            order.append(key)
        profiles_by_key[key] = profile
        local_keys.append(key)
    return AssessmentProfileCatalog(
        source_path=shipped.source_path,
        local_path=str(local_path),
        local_profile_keys=tuple(local_keys),
        profiles=tuple(profiles_by_key[key] for key in order),
    )


def clear_assessment_profile_catalog_cache() -> None:
    _CATALOG_CACHE.clear()


def load_assessment_profile_catalog(
    *,
    shipped_path: str | os.PathLike[str] | None = None,
    local_path: str | os.PathLike[str] | None = None,
    known_command_roots: Iterable[str] | None = None,
    known_workflow_ids: Iterable[str] | None = None,
) -> AssessmentProfileCatalog:
    configured_paths = configured_assessment_profile_paths()
    shipped = Path(shipped_path) if shipped_path is not None else configured_paths.shipped
    local = Path(local_path) if local_path is not None else (
        configured_paths.local if shipped_path is None else config_paths.local_overlay_path_for(shipped)
    )
    if known_command_roots is None or known_workflow_ids is None:
        default_commands, default_workflows = _known_action_references()
        known_command_roots = default_commands if known_command_roots is None else known_command_roots
        known_workflow_ids = default_workflows if known_workflow_ids is None else known_workflow_ids
    command_roots = frozenset(str(value).strip().lower() for value in known_command_roots)
    workflow_ids = frozenset(str(value).strip() for value in known_workflow_ids)
    cache_key = os.path.abspath(shipped), os.path.abspath(local)
    signature = (
        _catalog_signature(shipped),
        _catalog_signature(local),
        tuple(sorted(command_roots)),
        tuple(sorted(workflow_ids)),
    )
    cache = _CATALOG_CACHE.setdefault(cache_key, {"signature": None, "catalog": None})
    cached = cache.get("catalog")
    if cache.get("signature") == signature and isinstance(cached, AssessmentProfileCatalog):
        return cached

    try:
        shipped_data = _load_yaml(shipped, required=True)
        shipped_catalog = normalize_assessment_profile_catalog(
            shipped_data,
            source_path=str(shipped),
            known_command_roots=command_roots,
            known_workflow_ids=workflow_ids,
        )
    except AssessmentProfileCatalogError as exc:
        if not isinstance(cached, AssessmentProfileCatalog):
            raise
        log.warning(
            "ASSESSMENT_PROFILE_CATALOG_RELOAD_REJECTED",
            extra={"source": "shipped", "path": str(shipped), "error": str(exc)[:240]},
        )
        cache.update({"signature": signature, "catalog": cached})
        return cached

    try:
        local_data = _load_yaml(local, required=False)
    except AssessmentProfileCatalogError as exc:
        fallback = cached if isinstance(cached, AssessmentProfileCatalog) else shipped_catalog
        log.warning(
            "ASSESSMENT_PROFILE_LOCAL_CATALOG_REJECTED",
            extra={"path": str(local), "error": str(exc)[:240]},
        )
        cache.update({"signature": signature, "catalog": fallback})
        return fallback
    if local_data is None:
        catalog = shipped_catalog
    else:
        try:
            local_catalog = normalize_assessment_profile_catalog(
                local_data,
                source_path=str(shipped),
                local_path=str(local),
                known_command_roots=command_roots,
                known_workflow_ids=workflow_ids,
                allow_empty=True,
            )
            catalog = _merge_catalogs(shipped_catalog, local_catalog, local_path=local)
        except AssessmentProfileCatalogError as exc:
            fallback = cached if isinstance(cached, AssessmentProfileCatalog) else shipped_catalog
            log.warning(
                "ASSESSMENT_PROFILE_LOCAL_CATALOG_REJECTED",
                extra={"path": str(local), "error": str(exc)[:240]},
            )
            cache.update({"signature": signature, "catalog": fallback})
            return fallback

    cache.update({"signature": signature, "catalog": catalog})
    return catalog


def list_assessment_profiles(
    *,
    shipped_path: str | os.PathLike[str] | None = None,
    local_path: str | os.PathLike[str] | None = None,
    known_command_roots: Iterable[str] | None = None,
    known_workflow_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    catalog = load_assessment_profile_catalog(
        shipped_path=shipped_path,
        local_path=local_path,
        known_command_roots=known_command_roots,
        known_workflow_ids=known_workflow_ids,
    )
    return [deepcopy(profile) for profile in catalog.profiles]


def get_assessment_profile(
    profile_key: str,
    *,
    shipped_path: str | os.PathLike[str] | None = None,
    local_path: str | os.PathLike[str] | None = None,
    known_command_roots: Iterable[str] | None = None,
    known_workflow_ids: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    normalized_key = str(profile_key or "").strip().lower()
    catalog = load_assessment_profile_catalog(
        shipped_path=shipped_path,
        local_path=local_path,
        known_command_roots=known_command_roots,
        known_workflow_ids=known_workflow_ids,
    )
    for profile in catalog.profiles:
        if profile["key"] == normalized_key:
            return deepcopy(profile)
    return None
