# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared finding rollup helpers for Atlas and Project Overview."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from services.projects.contracts import FINDING_REVIEW_STATES, FINDING_VERIFICATION_STATES


FINDING_SEVERITIES = ("critical", "high", "medium", "low", "info", "unknown")
FINDING_REVIEW_STATE_ORDER = (
    "new",
    "needs_followup",
    "important",
    "reviewed",
    "false_positive",
)
FINDING_VERIFICATION_STATE_ORDER = (
    "not_started",
    "ready_to_verify",
    "verified",
    "needs_retest",
    "not_applicable",
)
FINDING_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def severity_rank(severity: str) -> int:
    return FINDING_SEVERITY_RANK.get(str(severity or "").strip().lower(), 99)


def empty_finding_rollup(*, applicable: bool = True) -> dict[str, Any]:
    return {
        "applicable": applicable,
        "total": 0,
        "all_total": 0,
        "suppressed": 0,
        "occurrence_count": 0,
        "latest_activity_at": "",
        "by_severity": {severity: 0 for severity in FINDING_SEVERITIES},
        "by_review_state": {state: 0 for state in FINDING_REVIEW_STATE_ORDER},
        "by_verification_state": {state: 0 for state in FINDING_VERIFICATION_STATE_ORDER},
        "by_suppression": {"visible": 0, "suppressed": 0},
        "sample": [],
    }


def add_finding_rollup_group(
    rollup: dict[str, Any],
    *,
    count: int,
    occurrence_count: int,
    severity: str,
    review_state: str,
    verification_state: str,
    suppressed: bool,
    latest_activity_at: str,
) -> None:
    safe_count = max(0, int(count or 0))
    rollup["all_total"] += safe_count
    if suppressed:
        rollup["suppressed"] += safe_count
        rollup["by_suppression"]["suppressed"] += safe_count
        return
    severity_key = str(severity or "unknown").strip().lower()
    review_key = str(review_state or "new").strip().lower()
    verification_key = str(verification_state or "not_started").strip().lower()
    rollup["total"] += safe_count
    rollup["occurrence_count"] += max(0, int(occurrence_count or 0))
    rollup["by_suppression"]["visible"] += safe_count
    normalized_severity = severity_key if severity_key in FINDING_SEVERITIES else "unknown"
    rollup["by_severity"][normalized_severity] += safe_count
    if review_key in FINDING_REVIEW_STATES:
        rollup["by_review_state"][review_key] += safe_count
    if verification_key in FINDING_VERIFICATION_STATES:
        rollup["by_verification_state"][verification_key] += safe_count
    activity = str(latest_activity_at or "")
    if activity > str(rollup["latest_activity_at"] or ""):
        rollup["latest_activity_at"] = activity


def finding_rollup_from_records(findings: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rollup = empty_finding_rollup()
    for finding in findings:
        add_finding_rollup_group(
            rollup,
            count=1,
            occurrence_count=max(0, int(finding.get("occurrence_count") or 0)),
            severity=str(finding.get("severity") or "unknown"),
            review_state=str(finding.get("review_state") or finding.get("status") or "new"),
            verification_state=str(
                finding.get("verification_status")
                or finding.get("verification_state")
                or "not_started"
            ),
            suppressed=bool(finding.get("suppressed")),
            latest_activity_at=max(
                str(finding.get("last_seen_at") or ""),
                str(finding.get("created") or ""),
            ),
        )
    return rollup


def finding_counts_from_rollup(
    rollup: Mapping[str, Any],
    *,
    include_verification: bool = True,
) -> dict[str, Any]:
    result = {
        "by_review_state": dict(rollup.get("by_review_state") or {}),
        "suppressed": max(0, int(rollup.get("suppressed") or 0)),
    }
    if include_verification:
        result["by_verification_state"] = dict(rollup.get("by_verification_state") or {})
    return result


def finding_state_counts(
    findings: Iterable[Mapping[str, Any]],
    *,
    include_verification: bool = True,
) -> dict[str, Any]:
    return finding_counts_from_rollup(
        finding_rollup_from_records(findings),
        include_verification=include_verification,
    )


def highest_actionable_finding_severity(findings: Iterable[Mapping[str, Any]]) -> str:
    best = ""
    best_rank = 99
    for finding in findings:
        if bool(finding.get("suppressed")):
            continue
        review_state = str(
            finding.get("review_state") or finding.get("status") or ""
        ).strip().lower()
        if review_state == "false_positive":
            continue
        severity = str(finding.get("severity") or "").strip().lower()
        rank = severity_rank(severity)
        if severity and rank < best_rank:
            best = severity
            best_rank = rank
    return best
