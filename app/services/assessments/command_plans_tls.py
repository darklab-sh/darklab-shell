# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded command templates for maintained TLS assessment checks."""

from __future__ import annotations

import ipaddress
import shlex

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.command_target_urls import default_https_target


def tls_command_plans(target_type: str, target_value: str) -> dict[str, CommandPlan]:
    """Return the fixed certificate and configuration plans for one host."""
    endpoint = target_value
    if target_type == "ip":
        try:
            if ipaddress.ip_address(target_value).version == 6:
                endpoint = f"[{target_value}]:443"
        except ValueError:
            return {}
    quoted_endpoint = shlex.quote(endpoint)
    quoted_url = shlex.quote(default_https_target(target_type, target_value))
    return {
        "sslyze": CommandPlan(
            f"sslyze --certinfo {quoted_endpoint}",
            "Certificate-chain validation for one approved TLS host.",
            None,
            120,
        ),
        "testssl": CommandPlan(
            f"testssl --fast --severity HIGH {quoted_url}",
            "A fixed fast, high-severity TLS review for one approved host.",
            None,
            300,
        ),
    }


__all__ = ["tls_command_plans"]
