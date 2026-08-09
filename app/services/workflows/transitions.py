# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared durable workflow step transition selection."""

from __future__ import annotations

from collections.abc import Mapping


def transition_for_step(
    definition: Mapping[str, object],
    step_id: str,
    *,
    exit_code: int,
    capture_failed: bool = False,
) -> tuple[str, str]:
    """Choose a saved step's next destination from its bounded outcome."""
    raw_steps = definition.get("steps")
    steps = [step for step in raw_steps if isinstance(step, Mapping)] if isinstance(raw_steps, list) else []
    index = next((position for position, step in enumerate(steps) if step.get("id") == step_id), -1)
    if index < 0:
        return "stop", "definition_error"
    raw_next = steps[index].get("next")
    next_value: Mapping[str, object] = raw_next if isinstance(raw_next, Mapping) else {}
    raw_codes = next_value.get("codes")
    codes: Mapping[str, object] = raw_codes if isinstance(raw_codes, Mapping) else {}
    code_destination = None if capture_failed else codes.get(str(exit_code))
    if code_destination:
        return str(code_destination), f"exit_code:{exit_code}"
    success = exit_code == 0 and not capture_failed
    outcome = "success" if success else "failure"
    if destination := next_value.get(outcome):
        return str(destination), outcome
    if success:
        if index + 1 < len(steps):
            return str(steps[index + 1].get("id") or "stop"), "implicit_success"
        return "complete", "implicit_success"
    return "stop", "capture_failure" if capture_failed else "implicit_failure"
