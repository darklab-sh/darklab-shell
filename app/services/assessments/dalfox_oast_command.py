# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded blind-XSS command derived from reviewed parameter evidence."""

from __future__ import annotations

import re
import shlex
from urllib.parse import parse_qsl, urlsplit

from services.assessments.command_plan_contracts import CommandPlan
from services.assessments.dalfox_parameter_evidence import (
    ReviewedDalfoxParameterEvidence,
)
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    dalfox_parameter_observation_id,
)
from services.assessments.dalfox_xss_command import (
    DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER,
    DALFOX_XSS_RATE_LIMIT_PER_SECOND,
    DALFOX_XSS_REQUEST_LIMIT,
    DALFOX_XSS_SCAN_TIMEOUT_SECONDS,
    DALFOX_XSS_TIME_LIMIT_SECONDS,
    DALFOX_XSS_WORKERS,
)


DALFOX_OAST_DISPLAY_CALLBACK = "https://[private-oast-callback]"
_CALLBACK_HOST_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


def _reviewed_callback_url(value: str) -> str | None:
    callback = str(value or "").strip()
    if callback == DALFOX_OAST_DISPLAY_CALLBACK:
        return callback
    try:
        parsed = urlsplit(callback)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.netloc != parsed.hostname
        or not _CALLBACK_HOST_RE.fullmatch(parsed.hostname)
    ):
        return None
    return f"https://{parsed.hostname}"


def reviewed_dalfox_oast_command_plan(
    evidence: ReviewedDalfoxParameterEvidence,
    *,
    callback_url: str = DALFOX_OAST_DISPLAY_CALLBACK,
) -> CommandPlan | None:
    """Return one fixed blind-XSS plan for a saved query parameter and callback."""
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
    callback = _reviewed_callback_url(callback_url)
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
    if (
        callback is None
        or evidence.parameter not in query_names
        or ":" in evidence.parameter
    ):
        return None
    target = shlex.quote(evidence.target)
    parameter = shlex.quote(f"{evidence.parameter}:query")
    reviewed_callback = shlex.quote(callback)
    return CommandPlan(
        f"dalfox scan {target} --input-type url --param {parameter} --skip-discovery "
        f"--skip-mining --blind {reviewed_callback} --format jsonl --no-color "
        f"--timeout 10 --scan-timeout {DALFOX_XSS_SCAN_TIMEOUT_SECONDS} "
        f"--retries 0 --rate-limit {DALFOX_XSS_RATE_LIMIT_PER_SECOND} "
        f"--workers {DALFOX_XSS_WORKERS} --max-concurrent-targets 1 "
        f"--max-targets-per-host 1 --max-payloads-per-param "
        f"{DALFOX_XSS_MAX_PAYLOADS_PER_PARAMETER} --limit 64 "
        "--limit-result-type all --skip-waf-probe --waf-bypass off "
        "--insecure=false",
        "One reviewed query parameter, one private app-owned HTTPS callback, at "
        "most 64 payloads, two requests per second, one worker, no redirects, "
        "discovery, mining, WAF probing, bypass mutation, remote payloads, or "
        "scanner-managed OAST, and a 60-second scan-stage limit.",
        DALFOX_XSS_REQUEST_LIMIT,
        DALFOX_XSS_TIME_LIMIT_SECONDS,
        "none",
    )


__all__ = [
    "DALFOX_OAST_DISPLAY_CALLBACK",
    "reviewed_dalfox_oast_command_plan",
]
