# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Human-readable Assessment action plan output."""

from __future__ import annotations

from typing import Any

from ..formatting import print_table


def print_assessment_action_plan(plan: dict[str, Any]) -> None:
    raw_target = plan.get("target")
    raw_action = plan.get("action")
    raw_http_profile = plan.get("http_profile")
    target = raw_target if isinstance(raw_target, dict) else {}
    action = raw_action if isinstance(raw_action, dict) else {}
    http_profile = raw_http_profile if isinstance(raw_http_profile, dict) else {}
    print_table([{
        "action": action.get("key") or "", "policy": plan.get("policy_level") or "",
        "target": f"{target.get('type') or ''}:{target.get('value') or ''}",
        "http_profile": http_profile.get("name") or "None",
        "launchable": bool(plan.get("launchable")), "command": plan.get("display_command") or "",
    }], ("action", "policy", "target", "http_profile", "launchable", "command"))


__all__ = ["print_assessment_action_plan"]
