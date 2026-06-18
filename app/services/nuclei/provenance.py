"""Nuclei template-source provenance helpers."""

from __future__ import annotations

import logging
import os
from pathlib import PurePosixPath
import shlex
from typing import Any


log = logging.getLogger("shell")


def _managed_template_dir() -> str:
    configured = os.environ.get("NUCLEI_TEMPLATES_DIR")
    if configured:
        return str(PurePosixPath(configured))
    return str(PurePosixPath(os.sep, "tmp", "nuclei-templates"))


MANAGED_TEMPLATE_DIR = _managed_template_dir()
PROVENANCE_SCHEMA_VERSION = 1
_TEMPLATE_FLAGS = {"-t", "-templates", "-template", "-w", "-workflow", "-headless"}
_UPDATE_DIR_FLAGS = {"-ud", "-update-directory"}
_UPDATE_TEMPLATE_FLAGS = {"-update-templates", "-ut"}
_KNOWN_PIN_FILES = {"templates-version.txt", ".templates-version", "templates.sha256", "templates.lock"}
_MANAGED_TEMPLATE_TOP_LEVELS = {
    "cloud",
    "code",
    "cves",
    "dns",
    "file",
    "headless",
    "helpers",
    "http",
    "javascript",
    "network",
    "ssl",
    "workflows",
}


def tokenize_command(command: str) -> list[str]:
    try:
        return shlex.split(str(command or ""))
    except ValueError:
        log.warning("NUCLEI_PROVENANCE_TOKENIZE_FALLBACK", extra={
            "command_root": "nuclei",
            "command_length": len(str(command or "")),
        })
        return str(command or "").split()


def nuclei_template_provenance(command: str | list[str]) -> dict[str, Any]:
    tokens = command if isinstance(command, list) else tokenize_command(str(command or ""))
    if not tokens or str(tokens[0]).lower() != "nuclei":
        return {}

    update_dir = _flag_value(tokens, _UPDATE_DIR_FLAGS) or MANAGED_TEMPLATE_DIR
    template_values = _flag_values(tokens, _TEMPLATE_FLAGS)
    explicit_templates = [value for value in template_values if value]
    source_kind = _source_kind(update_dir, explicit_templates, tokens)
    managed_label = f"Managed {MANAGED_TEMPLATE_DIR} cache"
    source_label = {
        "managed_cache": managed_label,
        "pinned_clone": "Pinned nuclei-templates clone",
        "workspace_templates": "Session workspace templates",
        "operator_updated": "Operator-updated template set",
        "custom_update_directory": "Custom template directory",
    }.get(source_kind, "Nuclei templates")

    provenance: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "tool": "nuclei",
        "source_kind": source_kind,
        "source_label": source_label,
        "update_directory": _safe_path(update_dir),
    }
    if explicit_templates:
        provenance["template_paths"] = [_safe_path(value) for value in explicit_templates[:12]]
        provenance["template_path_count"] = len(explicit_templates)
    if _has_update_templates_flag(tokens):
        provenance["operator_updated"] = True
    pin_hint = _pin_hint(explicit_templates)
    if pin_hint:
        provenance["pin_hint"] = pin_hint
    log.debug("NUCLEI_TEMPLATE_PROVENANCE_CLASSIFIED", extra={
        "source_kind": source_kind,
        "template_path_count": len(explicit_templates),
        "operator_updated": _has_update_templates_flag(tokens),
        "has_custom_update_directory": update_dir != MANAGED_TEMPLATE_DIR,
    })
    return provenance


def nuclei_line_template_id(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped.startswith("["):
        return ""
    closing = stripped.find("]")
    if closing <= 1:
        return ""
    return stripped[1:closing].strip()[:160]


def nuclei_source_detail(command: str, *, line_text: str = "", row: dict[str, Any] | None = None) -> dict[str, Any]:
    provenance = nuclei_template_provenance(command)
    detail: dict[str, Any] = {"adapter": "nuclei"}
    template_id = ""
    row_template_path = ""
    if isinstance(row, dict):
        template_id = str(row.get("template-id") or row.get("template_id") or "").strip()
        row_template_path = str(row.get("template-path") or row.get("template_path") or "").strip()
    if not template_id:
        template_id = nuclei_line_template_id(line_text)
    if not provenance and isinstance(row, dict):
        row_paths = [row_template_path] if row_template_path else []
        source_kind = _source_kind(MANAGED_TEMPLATE_DIR, row_paths, [])
        provenance = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "tool": "nuclei",
            "source_kind": source_kind,
            "source_label": {
                "managed_cache": f"Managed {MANAGED_TEMPLATE_DIR} cache",
                "pinned_clone": "Pinned nuclei-templates clone",
                "workspace_templates": "Session workspace templates",
            }.get(source_kind, "Nuclei templates"),
            "update_directory": MANAGED_TEMPLATE_DIR,
        }
        if row_template_path:
            provenance["template_paths"] = [_safe_path(row_template_path)]
            provenance["template_path_count"] = 1
    if template_id:
        detail["template_id"] = template_id[:160]
    if row_template_path:
        detail["template_path"] = _safe_path(row_template_path)
    if provenance:
        detail["template_provenance"] = provenance
    return detail


def _flag_value(tokens: list[str], flags: set[str]) -> str:
    values = _flag_values(tokens, flags)
    return values[-1] if values else ""


def _flag_values(tokens: list[str], flags: set[str]) -> list[str]:
    values: list[str] = []
    lowered = {flag.lower() for flag in flags}
    index = 1
    while index < len(tokens):
        token = str(tokens[index] or "")
        lower = token.lower()
        attached = next((flag for flag in lowered if lower.startswith(f"{flag}=")), "")
        if attached:
            values.append(token.split("=", 1)[1])
            index += 1
            continue
        if lower in lowered and index + 1 < len(tokens):
            values.append(str(tokens[index + 1] or ""))
            index += 2
            continue
        index += 1
    return values


def _has_update_templates_flag(tokens: list[str]) -> bool:
    flags = {flag.lower() for flag in _UPDATE_TEMPLATE_FLAGS}
    return any(str(token or "").lower() in flags for token in tokens[1:])


def _source_kind(update_dir: str, template_paths: list[str], tokens: list[str]) -> str:
    normalized_update_dir = _normalize_path(update_dir)
    normalized_templates = [_normalize_path(value) for value in template_paths]
    if any(_is_workspace_path(value) for value in normalized_templates):
        return "workspace_templates"
    if any(_looks_pinned(value) for value in normalized_templates):
        return "pinned_clone"
    if _has_update_templates_flag(tokens):
        return "operator_updated"
    if normalized_update_dir == MANAGED_TEMPLATE_DIR:
        return "managed_cache"
    return "custom_update_directory"


def _safe_path(value: str) -> str:
    text = str(value or "").strip()
    return text[:240]


def _normalize_path(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(PurePosixPath(text))
    except (TypeError, ValueError):
        return text


def _is_workspace_path(value: str) -> bool:
    raw_text = str(value or "").strip()
    normalized = _normalize_path(value)
    if not normalized:
        return False
    if _is_workspace_absolute_path(normalized):
        return True
    if normalized.startswith("/") or normalized.startswith(".."):
        return False
    if raw_text.startswith("./"):
        return True
    first_part = normalized.split("/", 1)[0].lower()
    return first_part not in _MANAGED_TEMPLATE_TOP_LEVELS


def _is_workspace_absolute_path(value: str) -> bool:
    normalized = _normalize_path(value)
    workspace_roots = {
        _normalize_path(os.environ.get("WORKSPACE_ROOT", "")),
        str(PurePosixPath(os.sep, "tmp", "darklab_shell-workspaces")),
        str(PurePosixPath(os.sep, "workspaces")),
    }
    return any(root and (normalized == root or normalized.startswith(f"{root}/")) for root in workspace_roots)


def _looks_pinned(value: str) -> bool:
    normalized = _normalize_path(value).lower()
    if not normalized:
        return False
    name = normalized.rsplit("/", 1)[-1]
    return (
        "nuclei-templates" in normalized
        and (
            any(part.startswith(("v", "release-", "tag-")) for part in normalized.split("/"))
            or name in _KNOWN_PIN_FILES
        )
    )


def _pin_hint(paths: list[str]) -> str:
    for value in paths:
        normalized = _normalize_path(value)
        if _looks_pinned(normalized):
            return normalized[:160]
    return ""
