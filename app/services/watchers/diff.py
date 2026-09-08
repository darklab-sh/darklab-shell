# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Watcher diff helpers built on shared run comparison primitives."""

from __future__ import annotations

from typing import Any

from services.diff.classifiers import diff_with_classifiers
from services.teams.ownership_queries import composite_owner_predicate
from services.teams.scope import personal_owner_context


def run_row(conn, session_token: str, run_id: str) -> dict[str, Any] | None:
    owner = composite_owner_predicate(
        personal_owner_context(session_token),
        owner_column="runs.session_id",
        key_values=(("runs.id", run_id),),
    )
    row = conn.execute(
        "SELECT runs.*, art.rel_path "
        "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
        "WHERE " + owner.sql,  # nosec B608
        owner.params,
    ).fetchone()
    return dict(row) if row else None


def diff_runs(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    *,
    options: dict[str, Any] | None = None,
    conn=None,
):
    return diff_with_classifiers(baseline_run, current_run, options=options, conn=conn)
