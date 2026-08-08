# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""One bounded command plan for the app-owned takeover fingerprint."""

from __future__ import annotations

import shlex
from typing import Any, Mapping

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.historical_urls import normalize_scope_domain
from services.assessments.nuclei_takeover_contracts import (
    NUCLEI_TAKEOVER_DISPLAY_TEMPLATE,
)


def reviewed_takeover_command_plan(
    target_type: str,
    target_value: str,
    *,
    protected_display: bool = True,
) -> CommandPlan | None:
    """Return the non-destructive one-domain provider-fingerprint plan."""
    domain = normalize_scope_domain(target_value)
    if target_type != "domain" or not domain:
        return None
    selector = (
        f" -t {NUCLEI_TAKEOVER_DISPLAY_TEMPLATE} -jsonl -dr -ni"
        if protected_display
        else ""
    )
    return CommandPlan(
        f"nuclei -u {shlex.quote('https://' + domain)} -rl 2 -c 1 "
        f"-timeout 10 -retries 0 -silent{selector}",
        "One approved domain and one app-owned reviewed provider fingerprint; "
        "one request, no redirects, no resource claim, and no takeover action.",
        1,
        30,
        "none",
    )


def reviewed_takeover_launch_plan_matches(plan: Mapping[str, Any]) -> bool:
    """Return whether one launch plan still matches the dedicated safe contract."""
    action = plan.get("action")
    target = plan.get("target")
    http_profile = plan.get("http_profile")
    expected = reviewed_takeover_command_plan(
        str(target.get("type") or "") if isinstance(target, Mapping) else "",
        str(target.get("value") or "") if isinstance(target, Mapping) else "",
    )
    return bool(
        plan.get("launchable") is True
        and str(plan.get("profile_key") or "") == "web"
        and str(plan.get("policy_level") or "") == "safe"
        and isinstance(action, Mapping)
        and action.get("key") == "command:nuclei"
        and action.get("kind") == "command"
        and action.get("id") == "nuclei"
        and isinstance(target, Mapping)
        and isinstance(http_profile, Mapping)
        and not str(http_profile.get("id") or "")
        and expected is not None
        and str(plan.get("display_command") or "") == expected.command
    )


__all__ = ["reviewed_takeover_command_plan", "reviewed_takeover_launch_plan_matches"]
