# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Config-backed evidence package preset catalog."""

from __future__ import annotations

from collections.abc import Mapping

from copy import deepcopy
from dataclasses import dataclass
import logging
from pathlib import Path
import os
import re
from typing import Any

import config as _config
from services.projects.contracts import (
    MAX_ENTITY_NOTE_BODY_LEN,
    MAX_LABEL_LEN,
    MAX_PACKAGE_DESCRIPTION_LEN,
    MAX_PACKAGE_NAME_LEN,
    ProjectWorkspaceError,
)
from services.projects.utils import trim_text as _trim_text


PACKAGE_PRESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
PACKAGE_PRESET_LABEL_MAX_LEN = 80
PACKAGE_PRESET_MAX_PRESETS = 50
PACKAGE_PRESET_MAX_DEFAULT_LABELS = 20
PACKAGE_PRESET_SELECTION_KEYS = ("runs", "transcripts", "findings", "artifacts", "targets")
PACKAGE_PRESET_POLICY_CHOICES = {
    "runs": frozenset({"all", "none"}),
    "transcripts": frozenset({"all", "none", "with_findings"}),
    "findings": frozenset({"all", "none", "non_false_positive"}),
    "artifacts": frozenset({"all", "none", "selectable"}),
    "targets": frozenset({"all", "none"}),
}
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PackagePresetCatalog:
    source_path: str
    presets: tuple[dict[str, object], ...]


_CATALOG_CACHE: dict[str, object] = {
    "signature": None,
    "catalog": None,
}


def _conf_dir() -> Path:
    return Path(_config.APP_CONF_DIR) if _config.APP_CONF_DIR else Path(__file__).resolve().parents[2] / "conf"


def _bundled_conf_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "conf"


def default_package_presets_path() -> Path:
    return _bundled_conf_dir() / "package_presets.yaml"


def configured_package_presets_path(cfg: Mapping[str, Any] | None = None) -> Path:
    active_cfg = cfg or _config.CFG
    raw_path = str(active_cfg.get("package_presets_file") or "package_presets.yaml").strip()
    path = Path(raw_path or "package_presets.yaml")
    return path if path.is_absolute() else _conf_dir() / path


def _catalog_signature(path: Path) -> tuple[str, int | None, int | None]:
    normalized = os.path.abspath(path)
    try:
        stat = os.stat(normalized)
    except OSError:
        return (normalized, None, None)
    return (normalized, stat.st_mtime_ns, stat.st_size)


def _load_yaml_catalog(path: Path) -> dict:
    return _config._load_yaml_config_optional(path)  # Reuse the app's YAML warning/fallback behavior.


def _normalize_policy(field: str, value: object) -> str:
    policy = str(value or "").strip().lower()
    if policy not in PACKAGE_PRESET_POLICY_CHOICES[field]:
        choices = ", ".join(sorted(PACKAGE_PRESET_POLICY_CHOICES[field]))
        raise ProjectWorkspaceError(f"package preset {field} policy must be one of: {choices}")
    return policy


def _normalize_default_labels(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ProjectWorkspaceError("package preset labels must be a list")
    labels = []
    seen = set()
    for raw_label in value:
        label = _trim_text(raw_label, MAX_LABEL_LEN)
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    if len(labels) > PACKAGE_PRESET_MAX_DEFAULT_LABELS:
        raise ProjectWorkspaceError("package preset labels exceed the per-package label cap")
    return labels


def normalize_package_preset_entry(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise ProjectWorkspaceError("package preset entries must be objects")

    preset_id = str(entry.get("id") or "").strip().lower()
    if not PACKAGE_PRESET_ID_RE.fullmatch(preset_id):
        raise ProjectWorkspaceError("package preset id must use lowercase letters, numbers, underscores, or hyphens")

    label = _trim_text(entry.get("label"), PACKAGE_PRESET_LABEL_MAX_LEN) or preset_id.replace("_", " ").title()
    description = _trim_text(entry.get("description"), MAX_PACKAGE_DESCRIPTION_LEN)
    redaction_mode = str(entry.get("redaction_mode") or "raw").strip().lower()
    if redaction_mode not in {"raw", "redacted"}:
        raise ProjectWorkspaceError("package preset redaction_mode must be raw or redacted")

    selection = entry.get("selection")
    if not isinstance(selection, dict):
        raise ProjectWorkspaceError("package preset selection must be an object")

    normalized_selection = {
        field: _normalize_policy(field, selection.get(field))
        for field in PACKAGE_PRESET_SELECTION_KEYS
    }

    return {
        "id": preset_id,
        "label": label,
        "description": description,
        "name_suffix": _trim_text(entry.get("name_suffix"), MAX_PACKAGE_NAME_LEN),
        "redaction_mode": redaction_mode,
        "include_artifacts": bool(entry.get("include_artifacts", False)),
        "include_private_notes": bool(entry.get("include_private_notes", False)),
        "labels": _normalize_default_labels(entry.get("labels")),
        "notes": _trim_text(entry.get("notes"), MAX_ENTITY_NOTE_BODY_LEN),
        "selection": normalized_selection,
    }


def normalize_package_preset_catalog(data: object, *, source_path: str = "") -> PackagePresetCatalog:
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("package preset catalog must be an object")
    raw_presets = data.get("presets")
    if not isinstance(raw_presets, list):
        raise ProjectWorkspaceError("package preset catalog must define a presets list")
    if len(raw_presets) > PACKAGE_PRESET_MAX_PRESETS:
        raise ProjectWorkspaceError("package preset catalog exceeds the configured preset cap")

    presets = []
    seen_ids = set()
    for raw_entry in raw_presets:
        preset = normalize_package_preset_entry(raw_entry)
        preset_id = str(preset["id"])
        if preset_id in seen_ids:
            raise ProjectWorkspaceError(f"duplicate package preset id: {preset_id}")
        seen_ids.add(preset_id)
        presets.append(preset)

    if not presets:
        raise ProjectWorkspaceError("package preset catalog must define at least one preset")
    return PackagePresetCatalog(source_path=source_path, presets=tuple(presets))


def clear_package_preset_catalog_cache() -> None:
    _CATALOG_CACHE["signature"] = None
    _CATALOG_CACHE["catalog"] = None


def load_package_preset_catalog(cfg: Mapping[str, Any] | None = None) -> PackagePresetCatalog:
    path = configured_package_presets_path(cfg)
    default_path = default_package_presets_path()
    signature = (
        _catalog_signature(path),
        _catalog_signature(default_path) if path != default_path else None,
    )
    cached = _CATALOG_CACHE.get("catalog")
    if _CATALOG_CACHE.get("signature") == signature and isinstance(cached, PackagePresetCatalog):
        return cached

    data = _load_yaml_catalog(path)
    try:
        catalog = normalize_package_preset_catalog(data, source_path=str(path))
    except ProjectWorkspaceError as exc:
        if path == default_path:
            raise
        log.warning(
            "PACKAGE_PRESETS_OVERRIDE_INVALID",
            extra={"path": str(path), "fallback_path": str(default_path), "error": str(exc)},
        )
        default_data = _load_yaml_catalog(default_path)
        catalog = normalize_package_preset_catalog(default_data, source_path=str(default_path))

    _CATALOG_CACHE["signature"] = signature
    _CATALOG_CACHE["catalog"] = catalog
    return catalog


def list_package_presets(cfg: Mapping[str, Any] | None = None) -> list[dict[str, object]]:
    return [deepcopy(preset) for preset in load_package_preset_catalog(cfg).presets]


def known_package_preset_ids(cfg: Mapping[str, Any] | None = None) -> set[str]:
    return {str(preset["id"]) for preset in load_package_preset_catalog(cfg).presets}
