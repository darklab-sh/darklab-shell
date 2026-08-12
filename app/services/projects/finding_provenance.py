# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded origin and validation-method contracts for saved findings."""

from __future__ import annotations


FINDING_ORIGINS = frozenset({"run", "import", "manual"})
FINDING_VALIDATION_METHODS = frozenset({
    "captured_observation",
    "active_confirmation",
    "version_inference",
    "imported_assertion",
    "manual_assessment",
})

_DEFAULT_VALIDATION_METHOD_BY_ORIGIN = {
    "run": "captured_observation",
    "import": "imported_assertion",
    "manual": "manual_assessment",
}


def normalize_finding_origin(value: object, *, default: str = "run") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in FINDING_ORIGINS:
        return normalized
    return default if default in FINDING_ORIGINS else "run"


def normalize_finding_validation_method(value: object, *, origin: object = "run") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in FINDING_VALIDATION_METHODS:
        return normalized
    normalized_origin = normalize_finding_origin(origin)
    return _DEFAULT_VALIDATION_METHOD_BY_ORIGIN[normalized_origin]
