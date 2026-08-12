# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort workspace artifact capture during run finalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.metrics_lazy import app_metrics
from services.projects.artifacts import record_run_file_artifacts
from services.runs.finalization_web_surface import append_httpx_screenshot_artifacts
from services.runs.persistence import run_finalize_savepoint
from services.runs.workspace_artifacts import workspace_artifacts_with_sizes


log = logging.getLogger("shell")


def save_run_file_artifacts_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    command: str,
    workspace_artifacts: object,
    workspace_owner: Any,
    *,
    persisted_entries: Sequence[object] = (),
    exit_code: int = 0,
    cfg: Mapping[str, Any] | None = None,
    workspace_artifacts_with_sizes_fn: Callable = workspace_artifacts_with_sizes,
) -> list:
    if not workspace_artifacts:
        return []
    artifact_candidates = workspace_artifacts
    try:
        artifact_candidates = append_httpx_screenshot_artifacts(
            workspace_artifacts, persisted_entries, workspace_owner,
            cfg=cfg,
            retain=int(exit_code) == 0,
            run_id=run_id,
            session_id=session_id,
            team_id=team_id,
            conn=conn,
        )
    except Exception:
        app_metrics.record_run_finalize_error("httpx_screenshot_artifacts")
        log.error("HTTPX_SCREENSHOT_ARTIFACT_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
        })
    try:
        if team_id:
            sized = workspace_artifacts_with_sizes_fn(
                session_id, artifact_candidates, owner_context=workspace_owner,
            )
        else:
            sized = workspace_artifacts_with_sizes_fn(session_id, artifact_candidates)
        return run_finalize_savepoint(
            conn,
            "run_file_artifacts",
            lambda: record_run_file_artifacts(
                conn,
                session_id,
                run_id,
                sized,
                **({"owner_context": workspace_owner} if team_id else {}),
            ),
        )
    except Exception:
        log.error("PROJECT_RUN_ARTIFACT_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
        return []


__all__ = ["save_run_file_artifacts_for_finalize"]
