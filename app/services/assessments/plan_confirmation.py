# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared digest confirmation for side-effect-free action previews."""

from __future__ import annotations

from typing import Any, Callable, Mapping


class PlanConfirmationFailure(ValueError):
    """An adapter-neutral confirmation failure."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def confirm_current_plan(
    data: Any,
    load_plan: Callable[[], dict[str, Any]],
    *,
    subject: str,
    allowed_fields: frozenset[str],
) -> dict[str, Any]:
    """Rebuild and compare a preview before an adapter starts side effects."""
    title = subject.capitalize()
    if not isinstance(data, Mapping):
        raise PlanConfirmationFailure(
            "invalid_body",
            "Request body must be a JSON object.",
        )
    if set(data) - allowed_fields:
        raise PlanConfirmationFailure(
            "unsupported_fields",
            f"{title} launch contains unsupported fields.",
        )
    if data.get("confirmed") is not True:
        raise PlanConfirmationFailure(
            "confirmation_required",
            f"Explicit {subject} launch confirmation is required.",
            status_code=409,
        )
    supplied_digest = str(data.get("plan_digest") or "").strip()
    if not supplied_digest:
        raise PlanConfirmationFailure(
            "plan_digest_required",
            f"The {subject} launch plan digest is required.",
        )
    plan = load_plan()
    if supplied_digest != plan.get("plan_digest"):
        raise PlanConfirmationFailure(
            "stale_plan",
            f"The {subject} launch plan changed. Review the current plan and confirm again.",
            status_code=409,
        )
    if not plan.get("launchable"):
        raise PlanConfirmationFailure(
            "action_unavailable",
            str(plan.get("unavailable_reason") or f"{title} action is unavailable."),
            status_code=409,
        )
    return plan


__all__ = ["PlanConfirmationFailure", "confirm_current_plan"]
