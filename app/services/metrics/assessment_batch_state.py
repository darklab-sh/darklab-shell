# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scrape-time gauges derived from durable assessment-batch state."""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client.core import GaugeMetricFamily

from services.assessments.batch.contracts import (
    BATCH_COULD_NOT_CANCEL_ERROR_CODE,
    BATCH_UNAVAILABLE_ERROR_CODES,
)
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


log = logging.getLogger("shell")

ACTIVE_STATUSES = ("queued", "running", "canceling")
EXECUTION_OUTCOMES = ("succeeded", "partial", "failed", "canceled")
ITEM_OUTCOMES = (
    "pending",
    "launching",
    "running",
    "succeeded",
    "failed",
    "unavailable",
    "canceled",
    "skipped",
    "could_not_cancel",
)


def _item_outcome(status: object, error_code: object) -> str:
    normalized_status = str(status or "")
    normalized_error = str(error_code or "")
    if normalized_status == "failed" and normalized_error == BATCH_COULD_NOT_CANCEL_ERROR_CODE:
        return "could_not_cancel"
    if normalized_status == "failed" and normalized_error in BATCH_UNAVAILABLE_ERROR_CODES:
        return "unavailable"
    return normalized_status if normalized_status in ITEM_OUTCOMES else "failed"


def _state_counts(conn: Any) -> tuple[dict[str, int], int, dict[str, int], dict[str, int]]:
    active = {status: 0 for status in ACTIVE_STATUSES}
    executions = {outcome: 0 for outcome in EXECUTION_OUTCOMES}
    items = {outcome: 0 for outcome in ITEM_OUTCOMES}
    active_rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM workflow_executions "
        "WHERE execution_kind = ? AND status IN ('queued', 'running', 'canceling') "
        "GROUP BY status",
        (ASSESSMENT_BATCH_EXECUTION_KIND,),
    ).fetchall()
    for row in active_rows:
        status = str(row["status"] or "")
        if status in active:
            active[status] = int(row["n"] or 0)

    queue_row = conn.execute(
        "SELECT COUNT(*) AS n FROM workflow_execution_children c "
        "JOIN workflow_executions e ON e.id = c.execution_id "
        "WHERE e.execution_kind = ? AND e.status IN ('queued', 'running', 'canceling') "
        "AND c.status = 'pending' AND c.attempt = ("
        "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
        "WHERE latest.execution_id = c.execution_id AND latest.step_id = c.step_id "
        "AND latest.ordinal = c.ordinal)",
        (ASSESSMENT_BATCH_EXECUTION_KIND,),
    ).fetchone()
    queue_depth = int(queue_row["n"] or 0) if queue_row else 0

    execution_rows = conn.execute(
        "SELECT e.id, e.status, SUM(CASE WHEN c.status != 'succeeded' THEN 1 ELSE 0 END) "
        "AS non_success FROM workflow_executions e "
        "LEFT JOIN workflow_execution_children c ON c.execution_id = e.id AND c.attempt = ("
        "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
        "WHERE latest.execution_id = c.execution_id AND latest.step_id = c.step_id "
        "AND latest.ordinal = c.ordinal) "
        "WHERE e.execution_kind = ? AND e.status IN ('completed', 'failed', 'canceled') "
        "GROUP BY e.id, e.status",
        (ASSESSMENT_BATCH_EXECUTION_KIND,),
    ).fetchall()
    for row in execution_rows:
        status = str(row["status"] or "")
        outcome = status
        if status == "completed":
            outcome = "partial" if int(row["non_success"] or 0) else "succeeded"
        if outcome in executions:
            executions[outcome] += 1

    item_rows = conn.execute(
        "SELECT c.status, c.error_code, COUNT(*) AS n "
        "FROM workflow_execution_children c "
        "JOIN workflow_executions e ON e.id = c.execution_id "
        "WHERE e.execution_kind = ? AND c.attempt = ("
        "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
        "WHERE latest.execution_id = c.execution_id AND latest.step_id = c.step_id "
        "AND latest.ordinal = c.ordinal) GROUP BY c.status, c.error_code",
        (ASSESSMENT_BATCH_EXECUTION_KIND,),
    ).fetchall()
    for row in item_rows:
        items[_item_outcome(row["status"], row["error_code"])] += int(row["n"] or 0)
    return active, queue_depth, executions, items


def assessment_batch_metric_families(conn: Any):
    """Return bounded gauge families, using zeroes when durable state is unavailable."""
    active = {status: 0 for status in ACTIVE_STATUSES}
    queue_depth = 0
    executions = {outcome: 0 for outcome in EXECUTION_OUTCOMES}
    items = {outcome: 0 for outcome in ITEM_OUTCOMES}
    if conn is not None:
        try:
            active, queue_depth, executions, items = _state_counts(conn)
        except Exception:
            log.debug("METRICS_ASSESSMENT_BATCH_STATE_COLLECT_FAILED", exc_info=True)

    active_metric = GaugeMetricFamily(
        "darklab_assessment_batches_active",
        "Active durable assessment batches by bounded status.",
        labels=("status",),
    )
    queue_metric = GaugeMetricFamily(
        "darklab_assessment_batch_queue_depth",
        "Latest-attempt assessment-batch items waiting to launch.",
    )
    execution_metric = GaugeMetricFamily(
        "darklab_assessment_batches_retained",
        "Retained terminal assessment batches by bounded outcome.",
        labels=("outcome",),
    )
    item_metric = GaugeMetricFamily(
        "darklab_assessment_batch_items_retained",
        "Retained latest-attempt assessment-batch items by bounded outcome.",
        labels=("outcome",),
    )
    for status, count in active.items():
        active_metric.add_metric([status], count)
    queue_metric.add_metric([], queue_depth)
    for outcome, count in executions.items():
        execution_metric.add_metric([outcome], count)
    for outcome, count in items.items():
        item_metric.add_metric([outcome], count)
    return active_metric, queue_metric, execution_metric, item_metric


__all__ = ["assessment_batch_metric_families"]
