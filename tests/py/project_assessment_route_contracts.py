# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Registered-route inventory helpers for Project Assessment write contracts."""

from __future__ import annotations

from typing import Any


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _expected_capability(path: str, method: str) -> str:
    if method not in _WRITE_METHODS:
        return ""
    if "/assessments/" in path or path.endswith("/assessments"):
        if path.endswith("/zap-plan"):
            return ""
        if any(
            part in path
            for part in (
                "/recommended-action",
                "/zap-jobs",
                "/oast-correlations",
            )
        ):
            return "RUN_COMMANDS"
        return "MUTATE_PROJECTS"
    if "/http-profiles" in path:
        return "MANAGE_SECRETS"
    if "/findings/" in path or path.endswith("/findings"):
        if "/verification-actions/" in path:
            return "RUN_COMMANDS"
        return "TRIAGE_FINDINGS"
    return ""


def registered_assessment_mutations(
    app: Any,
    *,
    route_prefix: str,
) -> list[tuple[Any, str, Any, str]]:
    """Return registered Assessment-workspace mutations and expected capability names."""
    contracts: list[tuple[Any, str, Any, str]] = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(route_prefix):
            continue
        for method in sorted(_WRITE_METHODS.intersection(rule.methods or set())):
            capability = _expected_capability(rule.rule, method)
            if capability:
                contracts.append(
                    (rule, method, app.view_functions[rule.endpoint], capability)
                )
    return sorted(
        contracts,
        key=lambda item: (item[0].rule, item[1], item[0].endpoint),
    )
