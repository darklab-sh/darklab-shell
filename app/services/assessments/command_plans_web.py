# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded web-tool plans for saved Assessment recommendations."""

from services.assessments.command_plan_contracts import CommandPlan


def web_command_plans(
    target: str,
    rate: int,
    concurrency: int,
    credential_use: str,
    protected_suffix: str,
    *,
    profiled: bool,
    nuclei_args: tuple[str, ...] = ("-severity", "high,critical"),
) -> dict[str, CommandPlan]:
    """Return the maintained web command-plan family for one target."""
    httpx_bounds = f" -rl {rate} -threads {concurrency}" if profiled else ""
    return {
        "curl": CommandPlan(
            f"curl -q --silent --show-error --head --no-location --noproxy '*' "
            f"--proto '=http,https' --connect-timeout 10 --max-time 30 {target}"
            f"{protected_suffix}",
            "One HEAD request to one approved HTTP target, with no redirects, a "
            "10-second connect timeout, and a 30-second total timeout.",
            1,
            30,
            credential_use,
        ),
        "httpx": CommandPlan(
            f"httpx -u {target} -status-code -title -tech-detect -silent"
            f"{httpx_bounds}{protected_suffix}",
            "One approved host or URL with response metadata only.",
            None,
            None,
            credential_use,
        ),
        "katana": CommandPlan(
            f"katana -u {target} -d 1 -dr -c {concurrency} -rl {rate} "
            f"-timeout 10 -silent{protected_suffix}",
            f"One approved web target, crawl depth 1, concurrency {concurrency}, and "
            "10-second request timeouts.",
            None,
            None,
            credential_use,
        ),
        "nuclei": CommandPlan(
            f"nuclei -u {target} {' '.join(nuclei_args)} -rl {rate} "
            f"-c {concurrency} -timeout 10 -retries 1 -silent{protected_suffix}",
            f"One approved target, high/critical templates, {rate} requests per second, "
            f"concurrency {concurrency}, and one retry.",
            None,
            None,
            credential_use,
        ),
        "dalfox": CommandPlan(
            f"dalfox {target} --only-discovery --skip-mining-dict --format jsonl "
            f"--no-color --timeout 10 --scan-timeout 60 --rate-limit {rate} "
            f"--workers {concurrency} --max-concurrent-targets 1 "
            f"--max-targets-per-host 1{protected_suffix}",
            f"One approved target, parameter discovery only, {rate} requests per second, "
            f"concurrency {concurrency}, no redirects or remote wordlists, and a "
            "60-second scan-stage timeout.",
            None,
            60,
            credential_use,
        ),
        "sqlmap": CommandPlan(
            f"sqlmap -u {target} --batch --level 1 --risk 1 --technique BEU "
            f"--timeout 10 --retries 1 --threads {concurrency} --time-limit 120 "
            f"--ignore-redirects --disable-coloring --no-logging{protected_suffix}",
            "One approved URL, detection-only SQL injection checks using Boolean, "
            "Error, and Union techniques; no redirects, extraction, or takeover actions.",
            None,
            120,
            credential_use,
        ),
    }
