"""Watcher diff helpers built on shared run comparison primitives."""

from __future__ import annotations

from typing import Any

from services.diff.classifiers import diff_with_classifiers


def run_row(conn, session_token: str, run_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT runs.*, art.rel_path "
        "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
        "WHERE runs.session_id = ? AND runs.id = ?",
        (session_token, run_id),
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
