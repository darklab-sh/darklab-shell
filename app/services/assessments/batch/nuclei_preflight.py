# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable Nuclei preflight summaries and launch checks for assessment batches."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.assessments.batch.contracts import AssessmentBatchError
from services.nuclei.template_health import NucleiTemplateHealth


class NucleiPreflightTracker:
    """Count selected Nuclei command intents without retaining target details."""

    def __init__(self, health: NucleiTemplateHealth) -> None:
        self.health = health
        self._commands: set[tuple[str, str]] = set()

    def observe(self, action_id: str, row: Any, include_standard: bool) -> None:
        policy = str(row["policy_level"] or "safe")
        if action_id != "nuclei" or (policy != "safe" and not include_standard):
            return
        target_id = str(row["current_target_id"] or row["target_entity_id"] or "")
        if target_id:
            self._commands.add((target_id, policy))

    def __bool__(self) -> bool:
        return bool(self._commands)

    def public(self) -> dict[str, object] | None:
        if not self._commands:
            return None
        return {**self.health.public(), "command_count": len(self._commands)}

    def summary(self) -> dict[str, object]:
        public = self.public()
        return {"nuclei_preflight": public} if public else {}


def batch_nuclei_preflight(summary: object) -> dict[str, object]:
    if not isinstance(summary, Mapping):
        return {}
    value = summary.get("nuclei_preflight")
    return dict(value) if isinstance(value, Mapping) else {}


def blocked_nuclei_preflight(summary: object) -> bool:
    preflight = batch_nuclei_preflight(summary)
    return (
        preflight.get("launchable") is False
        and str(preflight.get("state") or "")
        in {"missing", "oversized", "invalid", "unreadable", "incompatible", "unavailable"}
        and _count(preflight.get("command_count")) > 0
    )


def validate_batch_nuclei_preflight(
    summary: object,
    *,
    stale_confirmed: object,
) -> None:
    """Block unsafe Nuclei work and require one explicit stale-cache decision."""
    preflight = batch_nuclei_preflight(summary)
    if not preflight:
        return
    state = str(preflight.get("state") or "unavailable")
    if preflight.get("launchable") is not True:
        raise AssessmentBatchError(
            "nuclei_template_preflight_blocked",
            "The managed Nuclei templates aren't ready for this assessment plan.",
            status_code=409,
            details={
                "state": state,
                "reason_code": str(preflight.get("reason_code") or ""),
                "command_count": _count(preflight.get("command_count")),
            },
        )
    if state == "stale" and stale_confirmed is not True:
        raise AssessmentBatchError(
            "nuclei_template_confirmation_required",
            "Continuing with stale managed Nuclei templates requires confirmation.",
            status_code=409,
            details={
                "state": state,
                "release_version": str(preflight.get("release_version") or ""),
                "content_digest": str(preflight.get("content_digest") or ""),
                "command_count": _count(preflight.get("command_count")),
            },
        )


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = [
    "NucleiPreflightTracker",
    "batch_nuclei_preflight",
    "blocked_nuclei_preflight",
    "validate_batch_nuclei_preflight",
]
