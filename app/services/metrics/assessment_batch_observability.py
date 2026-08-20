# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded event metrics for assessment-batch execution."""

from __future__ import annotations

from prometheus_client import Counter, Histogram


ASSESSMENT_BATCH_LAUNCH_OUTCOMES = frozenset({"launched", "rejected", "failed"})
ASSESSMENT_BATCH_REJECTION_REASONS = frozenset(
    {"stale", "scope", "target", "profile", "feature", "policy", "other"}
)
ASSESSMENT_BATCH_DEFERRAL_REASONS = frozenset(
    {"batch", "owner", "instance", "target", "other"}
)
ASSESSMENT_BATCH_LAUNCH_LATENCY_BUCKETS = (
    0.01,
    0.05,
    0.1,
    0.5,
    1.0,
    5.0,
    10.0,
    30.0,
    60.0,
    300.0,
)

ASSESSMENT_BATCH_LAUNCH_LATENCY = Histogram(
    "darklab_assessment_batch_launch_latency_seconds",
    "Assessment-batch item latency from claim through launch by bounded outcome.",
    ("outcome",),
    buckets=ASSESSMENT_BATCH_LAUNCH_LATENCY_BUCKETS,
)
ASSESSMENT_BATCH_REJECTIONS = Counter(
    "darklab_assessment_batch_rejections",
    "Assessment-batch prelaunch rejections by bounded reason.",
    ("reason",),
)
ASSESSMENT_BATCH_DEFERRALS = Counter(
    "darklab_assessment_batch_concurrency_deferrals",
    "Assessment-batch launch deferrals by bounded concurrency reason.",
    ("reason",),
)

LABEL_CARDINALITY_POLICIES = {
    "darklab_assessment_batch_launch_latency_seconds": {
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_BATCH_LAUNCH_OUTCOMES,
            "fallback": "failed",
        }
    },
    "darklab_assessment_batch_rejections": {
        "reason": {
            "kind": "enum",
            "values": ASSESSMENT_BATCH_REJECTION_REASONS,
            "fallback": "other",
        }
    },
    "darklab_assessment_batch_concurrency_deferrals": {
        "reason": {
            "kind": "enum",
            "values": ASSESSMENT_BATCH_DEFERRAL_REASONS,
            "fallback": "other",
        }
    },
}
METRIC_DEFINITIONS = (
    ASSESSMENT_BATCH_LAUNCH_LATENCY,
    ASSESSMENT_BATCH_REJECTIONS,
    ASSESSMENT_BATCH_DEFERRALS,
)
HISTOGRAM_DEFINITIONS = (ASSESSMENT_BATCH_LAUNCH_LATENCY,)

_REJECTION_REASON_BY_CODE = {
    "plan_changed": "stale",
    "scope_unavailable": "scope",
    "scope_rejected": "scope",
    "target_unavailable": "target",
    "profile_unavailable": "profile",
    "feature_unavailable": "feature",
    "policy_changed": "policy",
}
_DEFERRAL_REASON_BY_CODE = {
    "batch_parallel_limit": "batch",
    "owner_parallel_limit": "owner",
    "instance_parallel_limit": "instance",
    "target_parallel_limit": "target",
}


def record_assessment_batch_launch(outcome: str, duration_seconds: float) -> None:
    label = str(outcome or "").strip().lower()
    if label not in ASSESSMENT_BATCH_LAUNCH_OUTCOMES:
        label = "failed"
    ASSESSMENT_BATCH_LAUNCH_LATENCY.labels(label).observe(
        max(0.0, float(duration_seconds or 0.0))
    )


def record_assessment_batch_rejection(error_code: str) -> None:
    reason = _REJECTION_REASON_BY_CODE.get(str(error_code or ""), "other")
    ASSESSMENT_BATCH_REJECTIONS.labels(reason).inc()


def record_assessment_batch_deferral(reason_code: str) -> None:
    reason = _DEFERRAL_REASON_BY_CODE.get(str(reason_code or ""), "other")
    ASSESSMENT_BATCH_DEFERRALS.labels(reason).inc()


__all__ = [
    "record_assessment_batch_deferral",
    "record_assessment_batch_launch",
    "record_assessment_batch_rejection",
]
