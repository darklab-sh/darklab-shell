# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Primitive validation and privacy-safe profile catalog diagnostics."""

from __future__ import annotations

import re
from typing import Any

from services.projects.contracts import ProjectWorkspaceError


_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}$")
_MAX_LIST_ITEMS = 32
_ERROR_CODES = frozenset({
    "catalog_missing",
    "duplicate_value",
    "invalid_catalog",
    "invalid_yaml",
    "limit_exceeded",
    "unknown_action",
    "unknown_command",
    "unknown_field",
    "unknown_workflow",
    "unsupported_value",
})


class AssessmentProfileCatalogError(ProjectWorkspaceError):
    """Raised when an assessment-profile catalog is invalid."""

    def __init__(self, message: str, *, error_code: str = "invalid_catalog") -> None:
        super().__init__(message)
        self.error_code = error_code if error_code in _ERROR_CODES else "invalid_catalog"


def catalog_error(
    message: str,
    *,
    error_code: str = "invalid_catalog",
) -> AssessmentProfileCatalogError:
    return AssessmentProfileCatalogError(
        f"assessment profile catalog {message}",
        error_code=error_code,
    )


def mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise catalog_error(f"{label} must be an object")
    return value


def reject_unknown_fields(
    value: dict[str, Any],
    allowed: frozenset[str],
    label: str,
) -> None:
    unknown = sorted(str(field) for field in value if field not in allowed)
    if unknown:
        raise catalog_error(
            f"{label} has unknown fields: {', '.join(unknown)}",
            error_code="unknown_field",
        )


def required_text(value: object, label: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise catalog_error(f"{label} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise catalog_error(f"{label} exceeds {max_length} characters")
    return normalized


def stable_key(value: object, label: str) -> str:
    normalized = required_text(value, label, 64).lower()
    if not _KEY_RE.fullmatch(normalized):
        raise catalog_error(
            f"{label} must use lowercase letters, numbers, underscores, or hyphens"
        )
    return normalized


def version(value: object, label: str) -> str:
    normalized = required_text(value, label, 20)
    if not _VERSION_RE.fullmatch(normalized):
        raise catalog_error(f"{label} must be a numeric dotted version")
    return normalized


def string_list(
    value: object,
    label: str,
    *,
    allowed: frozenset[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise catalog_error(f"{label} must be a list")
    if len(value) > _MAX_LIST_ITEMS:
        raise catalog_error(f"{label} exceeds the item cap", error_code="limit_exceeded")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = required_text(item, label, 128).lower()
        if allowed is not None and normalized not in allowed:
            raise catalog_error(
                f"{label} contains unsupported value: {normalized}",
                error_code="unsupported_value",
            )
        if normalized in seen:
            raise catalog_error(
                f"{label} contains duplicate value: {normalized}",
                error_code="duplicate_value",
            )
        seen.add(normalized)
        result.append(normalized)
    if not result and not allow_empty:
        raise catalog_error(f"{label} must not be empty")
    return result


def catalog_rejection_fields(
    exc: AssessmentProfileCatalogError,
    *,
    source: str,
    path: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "path": path,
        "error_code": exc.error_code,
        "error_class": type(exc).__name__,
    }


__all__ = [
    "AssessmentProfileCatalogError",
    "catalog_error",
    "catalog_rejection_fields",
    "mapping",
    "reject_unknown_fields",
    "required_text",
    "stable_key",
    "string_list",
    "version",
]
