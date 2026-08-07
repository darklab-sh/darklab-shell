# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded command templates for saved Assessment recommendations."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Mapping


_COMMAND_TARGET_TYPES = {
    "curl": frozenset({"domain", "ip", "url"}),
    "ping": frozenset({"domain", "ip"}),
    "nmap": frozenset({"domain", "ip"}),
    "dnsrecon": frozenset({"domain"}),
    "httpx": frozenset({"domain", "ip", "url"}),
    "katana": frozenset({"domain", "url"}),
    "nuclei": frozenset({"domain", "ip", "url"}),
}


@dataclass(frozen=True)
class CommandPlan:
    command: str
    boundary: str
    request_limit: int | None
    time_limit_seconds: int | None
    credential_use: str = "none"


def command_plan(
    action_id: str,
    target_type: str,
    target_value: str,
    *,
    web_target: str = "",
    http_profile: Mapping[str, Any] | None = None,
    protected_display: bool = True,
) -> CommandPlan | None:
    """Return one bounded command without resolving any protected values."""
    if target_type not in _COMMAND_TARGET_TYPES.get(action_id, frozenset()):
        return None
    quoted = shlex.quote(target_value)
    selected_web_target = web_target or target_value
    if (
        not web_target
        and target_type in {"domain", "ip"}
        and action_id in {"curl", "httpx", "katana", "nuclei"}
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
        elif header_uses:
            protected_suffix = " -H [protected]" if action_id == "katana" else " -sf [protected]"
        if action_id == "nuclei" and "client_certificate" in uses:
            protected_suffix += " -cc [protected] -ck [protected]"
    httpx_bounds = f" -rl {rate} -threads {concurrency}" if http_profile else ""
    plans = {
        "curl": CommandPlan(
            f"curl -q --silent --show-error --head --no-location --noproxy '*' "
            f"--proto '=http,https' --connect-timeout 10 --max-time 30 {quoted_web}"
            f"{protected_suffix}",
            "One HEAD request to one approved HTTP target, with no redirects, a "
            "10-second connect timeout, and a 30-second total timeout.",
            1,
            30,
            credential_use,
        ),
        "ping": CommandPlan(
            f"ping -c 4 -W 2 {quoted}",
            "Four probes against one approved host.",
            4,
            10,
        ),
        "nmap": CommandPlan(
            f"nmap -sT -sV -Pn --top-ports 100 --max-retries 2 "
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
        "httpx": CommandPlan(
            f"httpx -u {quoted_web} -status-code -title -tech-detect -silent"
            f"{httpx_bounds}{protected_suffix}",
            "One approved host or URL with response metadata only.",
            None,
            None,
            credential_use,
        ),
        "katana": CommandPlan(
            f"katana -u {quoted_web} -d 1 -dr -c {concurrency} -rl {rate} "
            f"-timeout 10 -silent{protected_suffix}",
            f"One approved web target, crawl depth 1, concurrency {concurrency}, and "
            "10-second request timeouts.",
            None,
            None,
            credential_use,
        ),
        "nuclei": CommandPlan(
            f"nuclei -u {quoted_web} -severity high,critical -rl {rate} "
            f"-c {concurrency} -timeout 10 -retries 1 -silent{protected_suffix}",
            f"One approved target, high/critical templates, {rate} requests per second, "
            f"concurrency {concurrency}, and one retry.",
            None,
            None,
            credential_use,
        ),
    }
    return plans.get(action_id)
