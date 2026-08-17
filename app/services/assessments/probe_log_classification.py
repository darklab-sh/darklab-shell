# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fixed severity and outcome decisions for Project probe records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.assessments.probe_contracts import ProbeError


_BROKER_DISABLED = "Run broker is disabled by configuration."
_EXPECTED_UNAVAILABLE = frozenset({"intrusive_actions_disabled", "unsupported_target_type"})


def classify_probe_error(exc: ProbeError) -> tuple[str, str, str]:
    """Return outcome, log method, and safe code for an expected rejection."""
    if exc.code == "broker_unavailable":
        disabled = str(exc) == _BROKER_DISABLED
        return (
            "unavailable",
            "info" if disabled else "warning",
            "broker_disabled" if disabled else "broker_dependency_unavailable",
        )
    outcome = "unavailable" if exc.status_code == 503 else "rejected"
    level = "warning" if exc.status_code in {403, 409, 429, 503} else "info"
    return outcome, level, exc.code


def classify_probe_result(result: Any, phase: str) -> tuple[str, str, str]:
    """Return outcome, log method, and availability code for a service result."""
    unavailable = isinstance(result, Mapping) and not result.get("launchable", True)
    if not unavailable:
        return "success", "info" if phase == "launch" else "debug", ""
    availability = result.get("availability")
    code = str(availability.get("code") or "") if isinstance(availability, Mapping) else ""
    return "unavailable", "info" if code in _EXPECTED_UNAVAILABLE else "warning", code


__all__ = ["classify_probe_error", "classify_probe_result"]
