# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Execution-kind event adapters for shared fan-out transitions."""

from __future__ import annotations

from typing import Any

from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


def _is_assessment_batch(row: Any) -> bool:
    return str(row["execution_kind"] or "") == ASSESSMENT_BATCH_EXECUTION_KIND


def record_child_bound_on_conn(conn: Any, row: Any, run_id: str) -> None:
    if not _is_assessment_batch(row):
        return
    from services.assessments.batch.lifecycle_events import (  # noqa: PLC0415
        record_batch_child_bound_on_conn,
    )

    record_batch_child_bound_on_conn(conn, row, run_id)


def record_child_settled_on_conn(
    conn: Any,
    row: Any,
    *,
    status: str,
    error_code: str,
    retry_child_id: str = "",
) -> None:
    if not _is_assessment_batch(row):
        return
    from services.assessments.batch.lifecycle_events import (  # noqa: PLC0415
        record_batch_child_settled_on_conn,
    )

    record_batch_child_settled_on_conn(
        conn,
        row,
        status=status,
        error_code=error_code,
        retry_child_id=retry_child_id,
    )


__all__ = ["record_child_bound_on_conn", "record_child_settled_on_conn"]
