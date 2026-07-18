# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded Prometheus metrics for durable workflow executions."""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter, Histogram


WORKFLOW_DURATION_BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 3600.0, 14400.0)
WORKFLOW_EXECUTION_OUTCOMES = frozenset({"completed", "failed", "canceled"})
WORKFLOW_STEP_OUTCOMES = frozenset({"succeeded", "failed", "canceled"})
WORKFLOW_CAPTURE_FAILURE_REASONS = frozenset({
    "required_missing",
    "value_limit",
    "total_limit",
    "invalid_value",
    "other",
})
WORKFLOW_RECOVERY_ACTIONS = frozenset({"recovered", "left_running", "failed", "ignored"})


WORKFLOW_EXECUTIONS_FINISHED = Counter(
    "darklab_workflow_executions_finished",
    "Durable workflow executions finished by bounded outcome.",
    ("outcome",),
)
WORKFLOW_EXECUTION_DURATION = Histogram(
    "darklab_workflow_execution_duration_seconds",
    "Durable workflow execution duration by bounded outcome.",
    ("outcome",),
    buckets=WORKFLOW_DURATION_BUCKETS,
)
WORKFLOW_STEPS_FINISHED = Counter(
    "darklab_workflow_steps_finished",
    "Durable workflow steps finished by bounded outcome.",
    ("outcome",),
)
WORKFLOW_STEP_DURATION = Histogram(
    "darklab_workflow_step_duration_seconds",
    "Durable workflow step duration by bounded outcome.",
    ("outcome",),
    buckets=WORKFLOW_DURATION_BUCKETS,
)
WORKFLOW_CAPTURE_FAILURES = Counter(
    "darklab_workflow_capture_failures",
    "Workflow capture failures by bounded reason.",
    ("reason",),
)
WORKFLOW_CANCELLATIONS = Counter(
    "darklab_workflow_cancellations",
    "Durable workflow executions canceled by operators.",
)
WORKFLOW_RECOVERY_ACTIONS_TOTAL = Counter(
    "darklab_workflow_recovery_actions",
    "Durable workflow startup recovery actions by bounded outcome.",
    ("action",),
)


LABEL_CARDINALITY_POLICIES: dict[str, dict[str, dict[str, Any]]] = {
    "darklab_workflow_executions_finished": {
        "outcome": {"kind": "enum", "values": WORKFLOW_EXECUTION_OUTCOMES, "fallback": "failed"},
    },
    "darklab_workflow_execution_duration_seconds": {
        "outcome": {"kind": "enum", "values": WORKFLOW_EXECUTION_OUTCOMES, "fallback": "failed"},
    },
    "darklab_workflow_steps_finished": {
        "outcome": {"kind": "enum", "values": WORKFLOW_STEP_OUTCOMES, "fallback": "failed"},
    },
    "darklab_workflow_step_duration_seconds": {
        "outcome": {"kind": "enum", "values": WORKFLOW_STEP_OUTCOMES, "fallback": "failed"},
    },
    "darklab_workflow_capture_failures": {
        "reason": {"kind": "enum", "values": WORKFLOW_CAPTURE_FAILURE_REASONS, "fallback": "other"},
    },
    "darklab_workflow_recovery_actions": {
        "action": {"kind": "enum", "values": WORKFLOW_RECOVERY_ACTIONS, "fallback": "failed"},
    },
}

METRIC_DEFINITIONS = (
    WORKFLOW_EXECUTIONS_FINISHED,
    WORKFLOW_EXECUTION_DURATION,
    WORKFLOW_STEPS_FINISHED,
    WORKFLOW_STEP_DURATION,
    WORKFLOW_CAPTURE_FAILURES,
    WORKFLOW_CANCELLATIONS,
    WORKFLOW_RECOVERY_ACTIONS_TOTAL,
)
HISTOGRAM_DEFINITIONS = (WORKFLOW_EXECUTION_DURATION, WORKFLOW_STEP_DURATION)


def _enum(value: str, allowed: frozenset[str], fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def record_workflow_execution_outcome(outcome: str, duration_seconds: float = 0.0) -> None:
    label = _enum(outcome, WORKFLOW_EXECUTION_OUTCOMES, "failed")
    WORKFLOW_EXECUTIONS_FINISHED.labels(label).inc()
    WORKFLOW_EXECUTION_DURATION.labels(label).observe(max(0.0, float(duration_seconds or 0.0)))


def record_workflow_step_outcome(outcome: str, duration_seconds: float = 0.0, *, count: int = 1) -> None:
    label = _enum(outcome, WORKFLOW_STEP_OUTCOMES, "failed")
    safe_count = max(0, int(count or 0))
    if not safe_count:
        return
    WORKFLOW_STEPS_FINISHED.labels(label).inc(safe_count)
    for _index in range(safe_count):
        WORKFLOW_STEP_DURATION.labels(label).observe(max(0.0, float(duration_seconds or 0.0)))


def record_workflow_capture_failure(reason: str) -> None:
    label = _enum(reason, WORKFLOW_CAPTURE_FAILURE_REASONS, "other")
    WORKFLOW_CAPTURE_FAILURES.labels(label).inc()


def record_workflow_cancellation() -> None:
    WORKFLOW_CANCELLATIONS.inc()


def record_workflow_recovery_action(action: str, *, count: int = 1) -> None:
    label = _enum(action, WORKFLOW_RECOVERY_ACTIONS, "failed")
    safe_count = max(0, int(count or 0))
    if safe_count:
        WORKFLOW_RECOVERY_ACTIONS_TOTAL.labels(label).inc(safe_count)
