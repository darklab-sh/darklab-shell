# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""One bounded active-Dalfox plan derived from reviewed query evidence."""

from __future__ import annotations

import shlex
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.dalfox_parameter_evidence import (
    ReviewedDalfoxParameterEvidence,
)
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    dalfox_parameter_observation_id,
)


DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER = 64
DALFOX_XSS_RATE_LIMIT_PER_SECOND = 2
DALFOX_XSS_REQUEST_LIMIT = 256
DALFOX_XSS_SCAN_TIMEOUT_SECONDS = 60
DALFOX_XSS_TIME_LIMIT_SECONDS = 90
DALFOX_XSS_WORKERS = 1


def reviewed_dalfox_xss_command_plan(
    evidence: ReviewedDalfoxParameterEvidence,
) -> CommandPlan | None:
    """Return the fixed intrusive plan for one saved query-parameter observation."""
    if type(evidence) is not ReviewedDalfoxParameterEvidence or evidence.location != "Query":
        return None
    if (
        not evidence.source_run_id
        or not evidence.tool_version
        or evidence.parser_version != DALFOX_DISCOVERY_PARSER_VERSION
        or evidence.observation_id != dalfox_parameter_observation_id(
            evidence.source_run_id,
            evidence.target,
            evidence.location,
            evidence.parameter,
        )
    ):
        return None
    try:
        evidence.xss_context(request_limit=DALFOX_XSS_REQUEST_LIMIT)
        query_names = {
            name for name, _value in parse_qsl(
                urlsplit(evidence.target).query,
                keep_blank_values=True,
                max_num_fields=256,
            )
        }
    except (TypeError, ValueError):
        return None
    if evidence.parameter not in query_names or ":" in evidence.parameter:
        return None
    target = shlex.quote(evidence.target)
    parameter = shlex.quote(f"{evidence.parameter}:query")
    return CommandPlan(
        f"dalfox scan {target} --input-type url --param {parameter} --skip-discovery "
        f"--skip-mining --format jsonl --no-color --timeout 10 "
        f"--scan-timeout {DALFOX_XSS_SCAN_TIMEOUT_SECONDS} --retries 0 "
        f"--rate-limit {DALFOX_XSS_RATE_LIMIT_PER_SECOND} "
        f"--workers {DALFOX_XSS_WORKERS} --max-concurrent-targets 1 "
        f"--max-targets-per-host 1 --max-payloads-per-param "
        f"{DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER} --limit 64 "
        "--limit-result-type all --skip-waf-probe --waf-bypass off --insecure=false",
        "One reviewed query parameter, at most 64 injected payloads, two requests "
        "per second, one worker, no redirects, discovery, mining, WAF probing, "
        "bypass mutation, remote payloads, or OAST, and a 60-second scan-stage limit.",
        DALFOX_XSS_REQUEST_LIMIT,
        DALFOX_XSS_TIME_LIMIT_SECONDS,
        "none",
    )


def reviewed_dalfox_xss_command_matches(
    command: Any,
    evidence: ReviewedDalfoxParameterEvidence,
) -> bool:
    """Return whether a command is the exact app-owned plan for saved evidence."""
    expected = reviewed_dalfox_xss_command_plan(evidence)
    return expected is not None and str(command or "") == expected.command


__all__ = [
    "DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER",
    "DALFOX_XSS_RATE_LIMIT_PER_SECOND",
    "DALFOX_XSS_REQUEST_LIMIT",
    "DALFOX_XSS_SCAN_TIMEOUT_SECONDS",
    "DALFOX_XSS_TIME_LIMIT_SECONDS",
    "DALFOX_XSS_WORKERS",
    "reviewed_dalfox_xss_command_matches",
    "reviewed_dalfox_xss_command_plan",
]
