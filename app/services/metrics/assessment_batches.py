# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded metrics for durable assessment-batch coordination."""

from __future__ import annotations

from prometheus_client import Counter


ASSESSMENT_BATCH_RECOVERY_ACTIONS = frozenset(
    {"recovered", "left_running", "failed", "ignored"}
)
ASSESSMENT_BATCH_RECOVERY_ACTIONS_TOTAL = Counter(
    "darklab_assessment_batch_recovery_actions",
    "Durable assessment-batch startup recovery actions by bounded outcome.",
    ("action",),
)

LABEL_CARDINALITY_POLICIES = {
    "darklab_assessment_batch_recovery_actions": {
        "action": {
            "kind": "enum",
            "values": ASSESSMENT_BATCH_RECOVERY_ACTIONS,
            "fallback": "failed",
        }
    }
}
METRIC_DEFINITIONS = (ASSESSMENT_BATCH_RECOVERY_ACTIONS_TOTAL,)
HISTOGRAM_DEFINITIONS: tuple[object, ...] = ()


def record_assessment_batch_recovery_action(action: str, *, count: int = 1) -> None:
    label = str(action or "").strip().lower()
    if label not in ASSESSMENT_BATCH_RECOVERY_ACTIONS:
        label = "failed"
    safe_count = max(0, int(count or 0))
    if safe_count:
        ASSESSMENT_BATCH_RECOVERY_ACTIONS_TOTAL.labels(label).inc(safe_count)


__all__ = ["record_assessment_batch_recovery_action"]
