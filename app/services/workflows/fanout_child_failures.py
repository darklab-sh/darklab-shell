# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable retry and failure-limit decisions for fan-out child attempts."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.workflows.fanout_checkpoint import FanoutCheckpoint
from services.workflows.fanout_policy import FanoutPolicy, normalize_fanout_policy, should_retry


@dataclass(frozen=True)
class FanoutFailureResolution:
    """Private durable changes selected for one failed attempt."""

    checkpoint: FanoutCheckpoint
    retry_child_id: str = ""
    failure_limit_reached: bool = False
    skipped_ordinals: tuple[int, ...] = ()


def fanout_policy_for_row(row: Any) -> FanoutPolicy:
    dialect = dialect_for_backend(get_db_backend())
    definition = dialect.decode_json_dict(row["definition_snapshot"])
    raw_steps = definition.get("steps")
    for step in raw_steps if isinstance(raw_steps, list) else []:
        if not isinstance(step, Mapping) or str(step.get("id") or "") != str(row["step_id"]):
            continue
        raw_policy = step.get("for_each")
        if isinstance(raw_policy, Mapping):
            return normalize_fanout_policy(dict(raw_policy))
        break
    raise ValueError("fan-out child parent policy is unavailable")


def _create_retry_child(conn: Any, row: Any, *, now: str) -> str:
    child_id = "wfc_" + secrets.token_hex(8)
    conn.execute(
        "INSERT INTO workflow_execution_children "
        "(id, execution_id, step_id, ordinal, attempt, run_id, status, error_code, created) "
        "VALUES (?, ?, ?, ?, ?, '', 'pending', '', ?)",
        (
            child_id,
            str(row["execution_id"]),
            str(row["step_id"]),
            int(row["ordinal"]),
            int(row["attempt"]) + 1,
            now,
        ),
    )
    return child_id


def _skip_unstarted_children(
    conn: Any,
    row: Any,
    checkpoint: FanoutCheckpoint,
    *,
    now: str,
) -> tuple[int, ...]:
    skipped: list[int] = []
    for ordinal in checkpoint.pending:
        changed = conn.execute(
            "UPDATE workflow_execution_children "
            "SET status = 'skipped', error_code = 'failure_limit', finished = ? "
            "WHERE execution_id = ? AND step_id = ? AND ordinal = ? AND status = 'pending'",
            (now, str(row["execution_id"]), str(row["step_id"]), ordinal),
        )
        if changed.rowcount != 1:
            raise ValueError("fan-out pending child state is out of sync")
        skipped.append(ordinal)
    for ordinal in checkpoint.running:
        changed = conn.execute(
            "UPDATE workflow_execution_children "
            "SET status = 'skipped', error_code = 'failure_limit', finished = ? "
            "WHERE execution_id = ? AND step_id = ? AND ordinal = ? "
            "AND status = 'launching' AND run_id = ''",
            (now, str(row["execution_id"]), str(row["step_id"]), ordinal),
        )
        if changed.rowcount == 1:
            skipped.append(ordinal)
    return tuple(sorted(skipped))


def resolve_failed_fanout_child(
    conn: Any,
    row: Any,
    checkpoint: FanoutCheckpoint,
    error_code: str,
    *,
    now: str,
) -> FanoutFailureResolution:
    """Create a bounded retry or apply the parent's terminal failure limit."""
    policy = fanout_policy_for_row(row)
    ordinal = int(row["ordinal"])
    attempt = int(row["attempt"])
    retry_allowed = (
        len(checkpoint.failed) < policy.max_failures
        and should_retry(policy, attempt=attempt, error_code=error_code)
    )
    if retry_allowed:
        retry_child_id = _create_retry_child(conn, row, now=now)
        return FanoutFailureResolution(
            checkpoint=checkpoint.reset_running([ordinal]),
            retry_child_id=retry_child_id,
        )

    terminal = checkpoint.mark_failed([ordinal])
    failure_limit_reached = len(terminal.failed) >= policy.max_failures
    skipped = (
        _skip_unstarted_children(conn, row, terminal, now=now)
        if failure_limit_reached
        else ()
    )
    if skipped:
        terminal = terminal.mark_skipped(list(skipped))
    return FanoutFailureResolution(
        checkpoint=terminal,
        failure_limit_reached=failure_limit_reached,
        skipped_ordinals=skipped,
    )
