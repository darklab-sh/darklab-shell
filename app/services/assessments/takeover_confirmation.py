# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed, version-pinned confirmation for potential DNS takeovers."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import datetime
import hashlib
import re
from typing import Any

from services.assessments.dns_takeover_correlation import (
    DNSX_TARGET_CORRELATION_VERSION,
    correlate_dnsx_target_observation,
)
from services.assessments.nuclei_takeover_identity import (
    NUCLEI_TAKEOVER_JSON_PARSER_VERSION,
    canonical_nuclei_matched_hostname,
    nuclei_takeover_observation_id,
)
from services.assessments.takeover_detection import evaluate_takeover_signal


NUCLEI_TAKEOVER_CONFIRMATION_VERSION = "nuclei-takeover-confirmation-v1"
NUCLEI_TAKEOVER_MAX_ALLOWED_RUNS = 512
NUCLEI_TAKEOVER_MAX_REVIEWED_TEMPLATES = 64
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TEMPLATE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,159}\Z")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}\Z")


def confirm_takeover_with_nuclei(
    review: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    *,
    dns_source_observation: Mapping[str, Any] | None,
    dns_target_observation: Mapping[str, Any] | None,
    reviewed_templates: Mapping[str, Mapping[str, Any]],
    allowed_source_run_ids: Collection[str],
) -> dict[str, Any]:
    """Confirm one potential signal only from exact app-owned Nuclei evidence."""
    result = dict(review) if isinstance(review, Mapping) else {}
    item = evidence if isinstance(evidence, Mapping) else {}
    rejection = _validate_boundary(
        result,
        item,
        dns_source_observation,
        dns_target_observation,
        reviewed_templates,
        allowed_source_run_ids,
    )
    if rejection:
        result["confirmation_status"] = "rejected"
        result["confirmation_reason"] = rejection
        return result

    template_id = str(item["template_id"])
    template = reviewed_templates[template_id]
    hostname = canonical_nuclei_matched_hostname(result["hostname"])
    source_run_id = str(item["source_run_id"])
    version = str(template["template_version"])
    digest = str(template["template_digest"])
    observed_at = str(item["observed_at"])
    confirmation_id = _confirmation_id(
        hostname, source_run_id, template_id, version, digest, observed_at,
    )
    result.update({
        "state": "confirmed",
        "reason": "reviewed_nuclei_template_match",
        "confirmation_status": "confirmed",
        "confirmation": {
            "confirmation_id": confirmation_id,
            "confirmation_version": NUCLEI_TAKEOVER_CONFIRMATION_VERSION,
            "method": "nuclei_template",
            "template_id": template_id,
            "template_version": version,
            "template_digest": digest,
            "source_run_id": source_run_id,
            "source_observation_id": str(item["observation_id"]),
            "parser_version": NUCLEI_TAKEOVER_JSON_PARSER_VERSION,
            "matched_hostname": hostname,
            "observed_at": observed_at,
            "policy_level": str(template["policy_level"]),
        },
    })
    return result


def _validate_boundary(
    review: dict[str, Any],
    evidence: Mapping[str, Any] | None,
    dns_source_observation: Mapping[str, Any] | None,
    dns_target_observation: Mapping[str, Any] | None,
    templates: Mapping[str, Mapping[str, Any]],
    allowed_runs: Collection[str],
) -> str:
    runs = _allowed_runs(allowed_runs)
    if runs is None:
        return "invalid_run_allowlist"
    if not _valid_dns_review(review, dns_source_observation, dns_target_observation, runs):
        return "invalid_dns_review"
    hostname = canonical_nuclei_matched_hostname(review.get("hostname"))
    if not isinstance(templates, Mapping) or not 0 < len(templates) <= NUCLEI_TAKEOVER_MAX_REVIEWED_TEMPLATES:
        return "invalid_template_registry"
    if (
        not isinstance(evidence, Mapping)
        or evidence.get("adapter") != "nuclei"
        or evidence.get("parser_version") != NUCLEI_TAKEOVER_JSON_PARSER_VERSION
    ):
        return "invalid_nuclei_evidence"
    template_id = str(evidence.get("template_id") or "")
    template = templates.get(template_id)
    if not _TEMPLATE_ID_RE.fullmatch(template_id) or not isinstance(template, Mapping):
        return "template_not_reviewed"
    version = str(template.get("template_version") or "")
    digest = str(template.get("template_digest") or "")
    policy = str(template.get("policy_level") or "")
    if not _VERSION_RE.fullmatch(version) or not _DIGEST_RE.fullmatch(digest):
        return "invalid_template_registry"
    if policy not in {"safe", "standard"}:
        return "template_policy_not_allowed"
    if evidence.get("match_state") != "matched":
        return "template_not_matched"
    if str(evidence.get("template_version") or "") != version:
        return "template_version_mismatch"
    if str(evidence.get("template_digest") or "") != digest:
        return "template_digest_mismatch"
    if str(evidence.get("policy_level") or "") != policy:
        return "template_policy_mismatch"
    source_run_id = str(evidence.get("source_run_id") or "")
    if source_run_id not in runs:
        return "source_run_not_allowed"
    matched_hostname = canonical_nuclei_matched_hostname(evidence.get("matched_hostname"))
    if matched_hostname != hostname:
        return "matched_target_mismatch"
    observed_at = str(evidence.get("observed_at") or "")
    if not _aware_timestamp(observed_at):
        return "invalid_observation_time"
    expected_id = nuclei_takeover_observation_id(
        source_run_id, matched_hostname, observed_at, template_id, version, digest, policy,
    )
    if evidence.get("observation_id") != expected_id:
        return "invalid_observation_identity"
    return ""


def _valid_dns_review(
    review: dict[str, Any],
    source: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None,
    allowed_runs: set[str],
) -> bool:
    if (
        review.get("correlation_version") != DNSX_TARGET_CORRELATION_VERSION
        or not isinstance(source, Mapping)
        or not isinstance(target, Mapping)
    ):
        return False
    joined = correlate_dnsx_target_observation(
        source, target, allowed_source_run_ids=allowed_runs,
    )
    if not joined:
        return False
    derived = evaluate_takeover_signal(joined)
    return (
        review.get("state") == "potential"
        and review.get("reason") == "dangling_cname"
        and derived.get("state") == "potential"
        and canonical_nuclei_matched_hostname(review.get("hostname")) == derived.get("hostname")
        and review.get("source_observation") == joined.get("source_observation")
        and review.get("target_observation") == joined.get("target_observation")
    )


def _allowed_runs(values: Collection[str]) -> set[str] | None:
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Collection)
        or not 0 < len(values) <= NUCLEI_TAKEOVER_MAX_ALLOWED_RUNS
    ):
        return None
    runs = {str(value or "").strip() for value in values}
    if any(not value or len(value) > 128 or any(ord(char) < 32 for char in value) for value in runs):
        return None
    return runs


def _aware_timestamp(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _confirmation_id(*parts: str) -> str:
    return "ntc_" + hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


__all__ = [
    "NUCLEI_TAKEOVER_CONFIRMATION_VERSION",
    "NUCLEI_TAKEOVER_MAX_ALLOWED_RUNS",
    "NUCLEI_TAKEOVER_MAX_REVIEWED_TEMPLATES",
    "confirm_takeover_with_nuclei",
]
