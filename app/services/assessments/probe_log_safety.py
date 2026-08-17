# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded identifier normalization for Project probe records."""

from __future__ import annotations

import re
from collections.abc import Mapping

from services.assessments.base_action_catalog import base_action


_ID_RE = re.compile(r"([a-z]{2,8})_[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_CODE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_CLASS_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}\Z")


def safe_probe_id(value: object, prefix: str) -> str:
    candidate = str(value or "").strip()
    match = _ID_RE.fullmatch(candidate)
    return candidate if match and match.group(1) == prefix else ""


def safe_probe_action(value: object) -> str:
    candidate = str(value or "").strip().casefold()
    if not candidate:
        return ""
    return candidate if base_action(candidate) is not None else "unknown"


def safe_probe_code(value: object, fallback: str = "unknown") -> str:
    candidate = str(value or "").strip().casefold()
    return candidate if _CODE_RE.fullmatch(candidate) else fallback


def safe_probe_error_class(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if _CLASS_RE.fullmatch(candidate) else "Exception"


def safe_probe_cleanup_fields(
    context: Mapping[str, object] | None,
    error_class: str = "",
) -> dict[str, object]:
    source = context or {}
    return {
        "project_id": safe_probe_id(source.get("project_id"), "prj"),
        "entity_id": safe_probe_id(source.get("entity_id"), "ent"),
        "action_id": safe_probe_action(source.get("action_id")),
        "profile_id": safe_probe_id(source.get("profile_id"), "hpr"),
        "cleanup_stage": "protected_material",
        "error_class": safe_probe_error_class(error_class) if error_class else "",
    }


__all__ = [
    "safe_probe_action",
    "safe_probe_code",
    "safe_probe_cleanup_fields",
    "safe_probe_error_class",
    "safe_probe_id",
]
