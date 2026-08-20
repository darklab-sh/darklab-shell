# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded metrics for operator assessment-batch lifecycle actions."""

from __future__ import annotations

from prometheus_client import Counter


ASSESSMENT_BATCH_ACTIONS = frozenset({"start", "cancel", "retry"})
ASSESSMENT_BATCH_ACTION_OUTCOMES = frozenset({"accepted", "rejected", "failed"})
ASSESSMENT_BATCH_ACTIONS_TOTAL = Counter(
    "darklab_assessment_batch_lifecycle_actions",
    "Assessment-batch lifecycle requests by bounded action and outcome.",
    ("action", "outcome"),
)

LABEL_CARDINALITY_POLICIES = {
    "darklab_assessment_batch_lifecycle_actions": {
        "action": {
            "kind": "enum",
            "values": ASSESSMENT_BATCH_ACTIONS,
            "fallback": "start",
        },
        "outcome": {
            "kind": "enum",
            "values": ASSESSMENT_BATCH_ACTION_OUTCOMES,
            "fallback": "failed",
        },
    }
}
METRIC_DEFINITIONS = (ASSESSMENT_BATCH_ACTIONS_TOTAL,)
HISTOGRAM_DEFINITIONS: tuple[object, ...] = ()


def record_assessment_batch_action(action: str, outcome: str) -> None:
    normalized_action = str(action or "").strip().lower()
    normalized_outcome = str(outcome or "").strip().lower()
    if normalized_action not in ASSESSMENT_BATCH_ACTIONS:
        normalized_action = "start"
    if normalized_outcome not in ASSESSMENT_BATCH_ACTION_OUTCOMES:
        normalized_outcome = "failed"
    ASSESSMENT_BATCH_ACTIONS_TOTAL.labels(normalized_action, normalized_outcome).inc()


__all__ = ["record_assessment_batch_action"]
