# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Execution-kind dispatch for terminal fan-out parent checkpoints."""

from __future__ import annotations

from typing import Any

from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import FanoutCheckpoint


def finalize_kind_parent_on_conn(
    conn: Any,
    row: Any,
    checkpoint: FanoutCheckpoint,
    *,
    finished: str,
) -> tuple[bool, dict[str, object] | None]:
    if str(row["execution_kind"] or "") != ASSESSMENT_BATCH_EXECUTION_KIND:
        return False, None
    from services.assessments.batch.parent_completion import (  # noqa: PLC0415
        finalize_batch_chunk_on_conn,
    )

    return True, finalize_batch_chunk_on_conn(
        conn,
        row,
        checkpoint,
        finished=finished,
    )


__all__ = ["finalize_kind_parent_on_conn"]
