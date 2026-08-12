# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded OWASP ZAP Automation Framework plan generation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from services.connectors.zap_config import ZapConnectorSettings
from services.connectors.zap_plan_contracts import (
    ReviewedZapAutomationPlan,
    ZapAutomationPlanSummary,
    ZapPlanError,
)
from services.connectors.zap_plan_scope import (
    MAX_TARGETS,
    canonical_target_url,
    review_zap_plan_scope,
    reviewed_rate_limit,
    scope_pattern,
)
from services.connectors.zap_scope import ReviewedZapTarget
from services.connectors.zap_scope_policy import allowed_target_cidrs_sha256

_MAX_PLAN_BYTES = 65536
_MAX_BODY_BYTES = 1048576
_REPORT_FILE = "darklab-zap-report.json"


def build_zap_automation_plan(
    settings: ZapConnectorSettings,
    targets: Sequence[ReviewedZapTarget],
    http_profile: Mapping[str, Any],
    *,
    policy_level: str = "safe",
    scope_exclusions: Sequence[object] = (),
    intrusive_enabled: bool = False,
) -> ReviewedZapAutomationPlan:
    """Build a portable, non-secret plan for review before remote submission."""
    if not settings.enabled:
        raise ZapPlanError("zap_connector_disabled", "ZAP connector is disabled")
    if not targets or len(targets) > MAX_TARGETS:
        raise ZapPlanError("zap_target_limit", "ZAP plans require between one and eight targets")
    policy = str(policy_level or "").strip().lower()
    if policy not in {"safe", "intrusive"}:
        raise ZapPlanError("zap_policy_invalid", "ZAP policy must be safe or intrusive")
    if policy == "intrusive" and not intrusive_enabled:
        raise ZapPlanError(
            "zap_intrusive_disabled",
            "Intrusive ZAP plans are disabled by operator policy",
        )

    canonical_targets = tuple(dict.fromkeys(canonical_target_url(target) for target in targets))
    if len(canonical_targets) != len(targets):
        raise ZapPlanError("zap_target_duplicate", "ZAP plan targets must be unique")
    role, include_paths, exclusions = review_zap_plan_scope(
        http_profile,
        canonical_targets,
        scope_exclusions,
    )
    origins = tuple(dict.fromkeys(
        urlunsplit((urlsplit(target).scheme, urlsplit(target).netloc, "", "", ""))
        for target in canonical_targets
    ))
    include_patterns = [
        scope_pattern(origin, path)
        for origin in origins
        for path in include_paths
    ] if include_paths else [
        scope_pattern(
            urlunsplit((urlsplit(target).scheme, urlsplit(target).netloc, "", "", "")),
            urlsplit(target).path or "/",
        )
        for target in canonical_targets
    ]
    exclusion_patterns = [
        scope_pattern(origin, path)
        for origin in origins
        for path in exclusions
    ]

    total_minutes = max(1, math.ceil(settings.job_timeout_seconds / 60))
    phase_count = len(canonical_targets) + (3 if policy == "intrusive" else 1)
    phase_minutes = max(1, total_minutes // phase_count)
    spider_minutes = min(5, phase_minutes)
    passive_minutes = min(5, phase_minutes)
    context_name = f"darklab-{role}"
    jobs: list[dict[str, Any]] = [{
        "type": "passiveScan-config",
        "parameters": {
            "maxAlertsPerRule": 20,
            "scanOnlyInScope": True,
            "maxBodySizeInBytesToScan": _MAX_BODY_BYTES,
            "enableTags": False,
        },
    }]
    for target in canonical_targets:
        jobs.append({
            "type": "spider",
            "parameters": {
                "context": context_name,
                "url": target,
                "maxDuration": spider_minutes,
                "maxDepth": 5,
                "maxChildren": 100,
                "acceptCookies": True,
                "handleParameters": "use_all",
                "logoutAvoidance": True,
                "maxParseSizeBytes": _MAX_BODY_BYTES,
                "parseComments": False,
                "parseGit": False,
                "parseDsStore": False,
                "parseRobotsTxt": True,
                "parseSitemapXml": True,
                "parseSVNEntries": False,
                "postForm": False,
                "processForm": False,
                "sendRefererHeader": False,
                "threadCount": 1,
            },
        })
    jobs.append({
        "type": "passiveScan-wait",
        "parameters": {"maxDuration": passive_minutes},
    })
    if policy == "intrusive":
        active_minutes = min(15, max(1, total_minutes - phase_minutes * phase_count))
        rate = reviewed_rate_limit(http_profile)
        jobs.extend([{
            "type": "activeScan",
            "parameters": {
                "context": context_name,
                "defaultStrength": "Low",
                "defaultThreshold": "Medium",
                "maxRuleDurationInMins": min(3, active_minutes),
                "maxScanDurationInMins": active_minutes,
                "addQueryParam": False,
                "delayInMs": max(1, math.ceil(1000 / rate)),
                "handleAntiCSRFTokens": True,
                "injectPluginIdInHeader": False,
                "scanHeadersAllRequests": False,
                "threadPerHost": 1,
                "maxAlertsPerRule": 10,
            },
        }, {
            "type": "passiveScan-wait",
            "parameters": {"maxDuration": passive_minutes},
        }])
    jobs.append({
        "type": "report",
        "parameters": {
            "template": "traditional-json",
            "reportDir": ".",
            "reportFile": _REPORT_FILE,
            "reportTitle": "darklab_shell Project assessment",
            "displayReport": False,
        },
    })
    plan = {
        "env": {
            "proxy": {
                "hostname": settings.egress_proxy_host,
                "port": settings.egress_proxy_port,
            },
            "contexts": [{
                "name": context_name,
                "urls": list(canonical_targets),
                "includePaths": include_patterns,
                "excludePaths": exclusion_patterns,
            }],
            "parameters": {
                "failOnError": True,
                "failOnWarning": False,
                "continueOnFailure": False,
                "progressToStdout": False,
            },
        },
        "jobs": jobs,
    }
    yaml_bytes = yaml.safe_dump(plan, sort_keys=False).encode("utf-8")
    if len(yaml_bytes) > _MAX_PLAN_BYTES:
        raise ZapPlanError("zap_plan_size_limit", "The generated ZAP plan is too large")
    job_types = tuple(str(job["type"]) for job in jobs)
    return ReviewedZapAutomationPlan(
        yaml_bytes=yaml_bytes,
        summary=ZapAutomationPlanSummary(
            policy_level=policy,
            authentication_role=role,
            targets=canonical_targets,
            include_rule_count=len(include_patterns),
            exclusion_rule_count=len(exclusion_patterns),
            job_types=job_types,
            job_timeout_seconds=settings.job_timeout_seconds,
            report_file=_REPORT_FILE,
            scope_policy_id=settings.scope_policy_id,
            allowed_target_cidrs_sha256=allowed_target_cidrs_sha256(settings),
            egress_proxy=f"{settings.egress_proxy_host}:{settings.egress_proxy_port}",
        ),
    )
