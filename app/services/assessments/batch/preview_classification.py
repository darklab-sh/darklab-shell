# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explainable eligibility and target-review classifications for previews."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Any

from services.assessments.base_action_catalog import base_action


_MANUAL_EXCLUDED_STATES = frozenset({"blocked", "skipped", "not_applicable"})
_EVIDENCE_STATES = frozenset({"covered", "needs_review"})
_SPECIAL_CHECKS = {
    "subdomain_takeover_confirmation": "takeover_confirmation",
}
_SPECIAL_ACTIONS = {
    "oast_private_callback": "oast",
    "command:schemathesis": "schemathesis",
}


def check_exclusion_reason(row: Any, frozen: Mapping[str, Any] | None) -> str:
    """Return one stable reason before an ordinary probe plan is compiled."""
    state = str(row["state"] or "")
    source = str(row["state_source"] or "")
    policy = str(row["policy_level"] or "")
    action_key = str(row["recommended_action_key"] or "")
    check_key = str(row["check_key"] or "")
    if source == "manual" and state in _MANUAL_EXCLUDED_STATES:
        return "manual_excluded"
    if str(row["applicability"] or "") != "applicable" or state == "not_applicable":
        return "not_applicable"
    if state in _EVIDENCE_STATES:
        return "already_covered"
    if state == "running":
        return "check_running"
    if state in {"blocked", "skipped"}:
        return "check_excluded"
    if int(row["unavailable_evidence_count"] or 0):
        return "unavailable_evidence"
    if not frozen:
        return "frozen_check_unavailable"
    if (
        str(frozen.get("recommended_action") or "") != action_key
        or str(frozen.get("policy_level") or "") != policy
    ):
        return "frozen_check_changed"
    if policy in {"intrusive", "destructive"}:
        return policy
    if policy not in {"safe", "standard"}:
        return "unsupported_policy"
    if check_key in _SPECIAL_CHECKS:
        return _SPECIAL_CHECKS[check_key]
    if action_key in _SPECIAL_ACTIONS:
        return _SPECIAL_ACTIONS[action_key]
    kind, separator, action_id = action_key.partition(":")
    if (
        kind != "command"
        or not separator
        or not action_id
        or not base_action(action_id)
    ):
        return "non_runnable"
    if not row["current_target_id"]:
        return "target_unavailable"
    if str(row["current_target_type"] or "") != str(row["target_type"] or "") or str(
        row["current_target_value"] or ""
    ) != str(row["target_value"] or ""):
        return "target_changed"
    return ""


def target_review_hints(row: Any) -> tuple[dict[str, str], ...]:
    """Flag review-worthy target origins without automatically excluding them."""
    hints: list[dict[str, str]] = []
    source = str(row["target_source"] or "manual")
    if source not in {"manual", "user"}:
        hints.append(
            {
                "code": "discovered_target",
                "reason": f"Discovered by {source}; review whether this is intended infrastructure or third-party scope.",
            }
        )
    if str(row["target_type"] or "") == "ip":
        try:
            address = ipaddress.ip_address(str(row["target_value"] or ""))
        except ValueError:
            address = None
        if address and (
            address.is_private or address.is_link_local or address.is_reserved
        ):
            hints.append(
                {
                    "code": "infrastructure_address",
                    "reason": "This address is private, link-local, or reserved infrastructure.",
                }
            )
    return tuple(hints)


__all__ = ["check_exclusion_reason", "target_review_hints"]
