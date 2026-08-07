# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded command templates for saved Assessment recommendations."""

from __future__ import annotations

import shlex
from typing import Any, Mapping

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.command_plans_web import web_command_plans
from services.assessments.nmap_profiles import nmap_profile_args


_COMMAND_TARGET_TYPES = {
    "curl": frozenset({"domain", "ip", "url"}),
    "ping": frozenset({"domain", "ip"}),
    "nmap": frozenset({"domain", "ip"}),
    "dnsrecon": frozenset({"domain"}),
    "httpx": frozenset({"domain", "ip", "url"}),
    "katana": frozenset({"domain", "url"}),
    "nuclei": frozenset({"domain", "ip", "url"}),
    "dalfox": frozenset({"domain", "ip", "url"}),
    "sqlmap": frozenset({"url"}),
}


def command_plan(
    action_id: str,
    target_type: str,
    target_value: str,
    *,
    web_target: str = "",
    http_profile: Mapping[str, Any] | None = None,
    protected_display: bool = True,
    nmap_profile: str = "",
) -> CommandPlan | None:
    """Return one bounded command without resolving any protected values."""
    if target_type not in _COMMAND_TARGET_TYPES.get(action_id, frozenset()):
        return None
    quoted = shlex.quote(target_value)
    selected_web_target = web_target or target_value
    if (
        not web_target
        and target_type in {"domain", "ip"}
        and action_id in {"curl", "httpx", "katana", "nuclei", "dalfox"}
    ):
        selected_web_target = f"https://{target_value}"
    quoted_web = shlex.quote(selected_web_target)
    rate = int((http_profile or {}).get("rate_limit_per_second") or 10)
    concurrency = int((http_profile or {}).get("concurrency") or 5)
    credential_use = "protected_http_profile" if http_profile else "none"
    protected_suffix = ""
    if http_profile and protected_display:
        uses = set(http_profile.get("credential_use") or [])
        header_uses = uses - {"client_certificate"}
        if action_id == "curl" and uses:
            protected_suffix = " --config [protected]"
        elif action_id == "dalfox" and header_uses:
            protected_suffix = " --config [protected]"
        elif action_id == "sqlmap" and header_uses:
            protected_suffix = " -c [protected]"
        elif header_uses:
            protected_suffix = " -H [protected]" if action_id == "katana" else " -sf [protected]"
        if action_id == "nuclei" and "client_certificate" in uses:
            protected_suffix += " -cc [protected] -ck [protected]"
    nmap_args = " ".join(nmap_profile_args(nmap_profile))
    nmap_script_suffix = f" {nmap_args}" if nmap_args else ""
    plans = {
        "ping": CommandPlan(
            f"ping -c 4 -W 2 {quoted}",
            "Four probes against one approved host.",
            4,
            10,
        ),
        "nmap": CommandPlan(
            f"nmap -sT -sV -Pn --top-ports 100 --max-retries 2{nmap_script_suffix} "
            f"--host-timeout 10m {quoted}",
            "One approved host, the top 100 TCP ports, and a 10-minute host timeout.",
            100,
            600,
        ),
        "dnsrecon": CommandPlan(
            f"dnsrecon -d {quoted} -t std",
            "Standard DNS record checks for one approved domain; no brute force or zone walk.",
            None,
            None,
        ),
        **web_command_plans(
            quoted_web,
            rate,
            concurrency,
            credential_use,
            protected_suffix,
            profiled=bool(http_profile),
        ),
    }
    return plans.get(action_id)
