# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""HTTP profile and URL scope review for generated ZAP plans."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from services.connectors.zap_plan_contracts import ZapPlanError
from services.connectors.zap_scope import ReviewedZapTarget

MAX_TARGETS = 8
MAX_SCOPE_EXCLUSIONS = 50
_MAX_PATH_LENGTH = 1000
_ROLE_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")


def _path_in_scope(path: str, prefixes: Sequence[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def _normalized_path_prefix(value: object) -> str:
    path = str(value or "").strip()
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or len(path) > _MAX_PATH_LENGTH
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or ".." in PurePosixPath(path).parts
    ):
        raise ZapPlanError(
            "zap_scope_exclusion_invalid",
            "ZAP scope exclusions must be bounded URL path prefixes",
        )
    return path


def _profile_list(profile: Mapping[str, Any], key: str) -> list[str]:
    raw = profile.get(key, [])
    if not isinstance(raw, (list, tuple)):
        raise ZapPlanError("zap_http_profile_invalid", "The selected HTTP profile is invalid")
    return [str(value) for value in raw]


def canonical_target_url(target: ReviewedZapTarget) -> str:
    parsed = urlsplit(target.url)
    rendered_host = f"[{target.host}]" if ":" in target.host else target.host
    port = parsed.port
    if port is not None and not (
        (parsed.scheme == "http" and port == 80)
        or (parsed.scheme == "https" and port == 443)
    ):
        rendered_host = f"{rendered_host}:{port}"
    return urlunsplit((parsed.scheme, rendered_host, parsed.path or "/", "", ""))


def _same_origin(left: str, right: str) -> bool:
    left_url = urlsplit(left)
    right_url = urlsplit(right)
    return (
        left_url.scheme == right_url.scheme
        and left_url.hostname == right_url.hostname
        and left_url.port == right_url.port
    )


def _target_matches_root(target: str, root: str) -> bool:
    if not _same_origin(target, root):
        return False
    return _path_in_scope(
        urlsplit(target).path or "/",
        [urlsplit(root).path or "/"],
    )


def scope_pattern(origin: str, path: str) -> str:
    if path == "/":
        return rf"^{re.escape(origin)}/(?:.*)?$"
    return rf"^{re.escape(origin + path.rstrip('/'))}(?:/.*)?(?:\?.*)?$"


def _has_protected_material(profile: Mapping[str, Any]) -> bool:
    counts = profile.get("reference_counts")
    protected_count = False
    if counts is not None and not isinstance(counts, Mapping):
        raise ZapPlanError("zap_http_profile_invalid", "The selected HTTP profile is invalid")
    if isinstance(counts, Mapping):
        for key in ("secret_refs", "file_refs", "headers", "capture_rules"):
            value = counts.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ZapPlanError(
                    "zap_http_profile_invalid",
                    "The selected HTTP profile is invalid",
                )
            protected_count = protected_count or value > 0
    return protected_count or any((
        profile.get("credential_use"),
        profile.get("headers"),
        profile.get("secret_refs"),
        profile.get("file_refs"),
        profile.get("proxy_url"),
        profile.get("proxy_configured"),
        profile.get("login_workflow_id"),
        profile.get("token_capture_rules"),
        profile.get("capture_rule_count"),
    ))


def reviewed_rate_limit(profile: Mapping[str, Any]) -> int:
    """Return the current profile rate after rejecting malformed values."""
    value = profile.get("rate_limit_per_second", 10)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1000:
        raise ZapPlanError("zap_http_profile_invalid", "The selected HTTP profile is invalid")
    return value


def review_zap_plan_scope(
    profile: Mapping[str, Any],
    targets: Sequence[str],
    extra_exclusions: Sequence[object],
) -> tuple[str, list[str], list[str]]:
    """Review selected URLs against one current, non-secret HTTP profile."""
    if not profile.get("enabled"):
        raise ZapPlanError("zap_http_profile_disabled", "The selected HTTP profile is disabled")
    role = str(profile.get("role") or "anonymous").strip().lower()
    if not _ROLE_RE.fullmatch(role):
        raise ZapPlanError("zap_http_profile_invalid", "The selected HTTP profile role is invalid")
    if role != "anonymous" or _has_protected_material(profile):
        raise ZapPlanError(
            "zap_http_profile_unsupported",
            "This HTTP profile needs connector material that is not yet supported",
        )

    allowed_hosts = {value.casefold() for value in _profile_list(profile, "allowed_hosts")}
    roots = _profile_list(profile, "scope_roots")
    includes = _profile_list(profile, "include_paths")
    saved_exclusions = _profile_list(profile, "exclude_paths")
    exclusions = list(dict.fromkeys(
        [_normalized_path_prefix(value) for value in saved_exclusions]
        + [_normalized_path_prefix(value) for value in extra_exclusions]
    ))
    if len(exclusions) > MAX_SCOPE_EXCLUSIONS:
        raise ZapPlanError(
            "zap_scope_exclusion_limit",
            "ZAP plans accept at most 50 scope exclusions",
        )
    for target in targets:
        parsed = urlsplit(target)
        path = parsed.path or "/"
        if (
            str(parsed.hostname or "").casefold() not in allowed_hosts
            or not any(_target_matches_root(target, root) for root in roots)
            or (includes and not _path_in_scope(path, includes))
            or (exclusions and _path_in_scope(path, exclusions))
        ):
            raise ZapPlanError(
                "zap_http_profile_scope_mismatch",
                "A selected ZAP target is outside the HTTP profile scope",
            )
    return role, includes, exclusions
