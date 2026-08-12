# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private-OAST state for the shared Assessment action-plan contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.dalfox_oast_actions import DalfoxOastActionContext
from services.assessments.dalfox_oast_contracts import DALFOX_OAST_ACTION_KEY


class PrivateOastDecision(NamedTuple):
    command: CommandPlan | None
    unavailable_reason: str


def private_oast_decision(
    action_key: str,
    target: Mapping[str, str] | None,
    http_profile: Mapping[str, Any] | None,
    context: DalfoxOastActionContext,
) -> PrivateOastDecision:
    """Build the redacted command while keeping the generic launch unavailable."""
    if (
        action_key != DALFOX_OAST_ACTION_KEY
        or not target
        or target["type"] != "url"
    ):
        return PrivateOastDecision(
            None,
            "The reviewed private OAST action no longer matches its saved URL contract.",
        )
    unavailable_reason = context.unavailable_reason()
    if unavailable_reason:
        return PrivateOastDecision(None, unavailable_reason)
    command = context.command_plan(http_profile)
    if command is None:
        return PrivateOastDecision(
            None,
            "No bounded private OAST command is available for this saved action.",
        )
    return PrivateOastDecision(
        command,
        "Prepare a private callback before this reviewed action can start.",
    )


def public_private_oast_plan(
    context: DalfoxOastActionContext,
    command: CommandPlan | None,
) -> dict[str, Any]:
    """Return only provider-free state for the public preview."""
    return {
        "evidence_selection": context.public_selection(),
        "oast": {
            "preparable": bool(command is not None and not context.unavailable_reason()),
            "callback_url": "https://[private-oast-callback]",
            "reservation_window_seconds": context.reservation_window_seconds(),
        },
    }


__all__ = ["private_oast_decision", "public_private_oast_plan"]
