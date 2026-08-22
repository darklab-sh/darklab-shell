# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe human-readable formatting for Project HTTP profiles."""

from __future__ import annotations

from typing import Any

from ..client import DarklabCliError
from ..formatting import print_collection, print_payload, print_table

HTTP_PROFILE_PUBLIC_FIELDS = (
    "id",
    "name",
    "role",
    "base_url",
    "enabled",
    "revision",
    "protected_references_visible",
    "reference_counts",
)


def print_http_profiles(payload: dict[str, Any], output_format: str) -> int:
    return print_collection(
        payload,
        "profiles",
        output_format,
        fields=HTTP_PROFILE_PUBLIC_FIELDS,
    )


def print_http_profile(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return print_payload(payload, output_format)
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        raise DarklabCliError("invalid HTTP profile response")
    print_table([profile], HTTP_PROFILE_PUBLIC_FIELDS)
    return 0


def print_http_profile_deleted(
    payload: dict[str, Any], output_format: str, profile_id: str
) -> int:
    if output_format == "json":
        return print_payload(payload, output_format)
    if not payload.get("ok") or not payload.get("removed"):
        raise DarklabCliError("invalid HTTP profile deletion response")
    print(f"Deleted HTTP profile {profile_id}.")
    return 0


__all__ = ["print_http_profile", "print_http_profile_deleted", "print_http_profiles"]
