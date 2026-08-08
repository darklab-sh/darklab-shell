# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded HTTPx screenshot artifact discovery during run finalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from typing import Any

from core.helpers import get_log_session_id
from services.metrics_lazy import app_metrics
from services.runs.finalization_web_surface_query import load_protected_workspace_paths
from services.runs.finalization_web_surface_storage import reconcile_screenshot_storage
from services.runs.httpx_workspace_artifact_metadata import HTTPX_SCREENSHOT_DIRECTORY
from services.workspace.settings import workspace_settings


HTTPX_SCREENSHOT_ARTIFACT_MAX = 200
HTTPX_SCREENSHOT_EVENT_MAX = 1_000
log = logging.getLogger("shell")


def append_httpx_screenshot_artifacts(
    artifacts: object,
    entries: Sequence[object],
    workspace_owner: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
    retain: bool = True,
    run_id: str = "",
    session_id: str = "",
    team_id: str = "",
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    """Append verified image children of one validated HTTPx output directory."""
    existing = [dict(item) for item in artifacts if isinstance(item, Mapping)] if isinstance(artifacts, list) else []
    directories = _marked_directories(existing)
    if len(directories) != 1:
        return existing
    directory = directories[0]
    settings = workspace_settings(cfg)
    seen = {str(item.get("workspace_path") or "") for item in existing}
    paths, truncated = _event_artifact_paths(entries)
    candidates = [path for path in paths if path not in seen]
    if not candidates:
        return existing
    protected_paths: set[str] = set()
    protected_lookup_failed = False
    protected_lookup_error = ""
    if conn is not None:
        try:
            protected_paths = load_protected_workspace_paths(
                conn,
                candidates,
                run_id=run_id,
                session_id=session_id,
                team_id=team_id,
            )
        except Exception as exc:
            protected_lookup_failed = True
            protected_lookup_error = type(exc).__name__
            protected_paths = set(candidates)
    result = reconcile_screenshot_storage(
        workspace_owner,
        candidates,
        directory,
        settings=settings,
        cfg=cfg,
        retain=retain,
        max_artifacts=HTTPX_SCREENSHOT_ARTIFACT_MAX,
        protected_paths=protected_paths,
    )
    existing.extend(result.artifacts)
    log_extra = {
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "candidate_count": result.candidate_count,
        "invalid_count": result.invalid_count,
        "retained_count": len(result.artifacts),
        "removed_count": result.removed_count,
        "cleanup_failed_count": result.cleanup_failed_count,
        "protected_cleanup_skip_count": result.protected_cleanup_skip_count,
        "protected_lookup_failed": protected_lookup_failed,
        "protected_lookup_error": protected_lookup_error,
        "candidate_truncated": truncated,
    }
    if protected_lookup_failed:
        log.warning("HTTPX_SCREENSHOT_PROTECTED_PATH_LOOKUP_FAILED", extra=log_extra)
    if result.quota_rejected_count or result.usage_unavailable or truncated:
        app_metrics.record_workspace_quota_rejection()
        log.warning("HTTPX_SCREENSHOT_STORAGE_LIMIT_REACHED", extra={
            **log_extra,
            "quota_rejected_count": result.quota_rejected_count,
            "available_file_slots": result.available_file_slots,
            "available_bytes": result.available_bytes,
            "usage_unavailable": result.usage_unavailable,
        })
    if result.cleanup_failed_count:
        log.warning("HTTPX_SCREENSHOT_CLEANUP_INCOMPLETE", extra=log_extra)
    if result.protected_cleanup_skip_count:
        log.warning("HTTPX_SCREENSHOT_CLEANUP_SKIPPED_PROTECTED", extra=log_extra)
    elif result.removed_count:
        log.debug("HTTPX_SCREENSHOT_OUTPUT_CLEANED", extra=log_extra)
    return existing


def _marked_directories(artifacts: list[dict[str, Any]]) -> list[str]:
    paths = []
    for item in artifacts:
        path = str(item.get("workspace_path") or "").strip()
        if (
            item.get("structured_output") == HTTPX_SCREENSHOT_DIRECTORY
            and item.get("kind") in {"output", "read_write"}
            and path
            and path not in paths
        ):
            paths.append(path)
    return paths


def _event_artifact_paths(entries: Sequence[object]) -> tuple[list[str], bool]:
    paths = []
    for item in entries[:HTTPX_SCREENSHOT_EVENT_MAX]:
        detail = item.get("source_detail") if isinstance(item, Mapping) else None
        screenshots = detail.get("screenshots") if isinstance(detail, Mapping) else None
        for screenshot in screenshots if isinstance(screenshots, list) else []:
            path = str(screenshot.get("artifact_path") or "").strip() if isinstance(screenshot, Mapping) else ""
            if path and path not in paths:
                paths.append(path)
                if len(paths) >= HTTPX_SCREENSHOT_EVENT_MAX:
                    return paths, True
    return paths, False


__all__ = ["HTTPX_SCREENSHOT_ARTIFACT_MAX", "append_httpx_screenshot_artifacts"]
