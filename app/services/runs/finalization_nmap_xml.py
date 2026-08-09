# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Load one validated owner-scoped Nmap XML artifact during finalization."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.metrics_lazy import app_metrics
from services.runs.workspace_artifact_metadata import (
    NMAP_XML_SOURCE_FLAG,
    NMAP_XML_STRUCTURED_OUTPUT,
)
from services.workspace.files import read_owner_workspace_text_file

log = logging.getLogger("shell")


def _marked_nmap_xml_path(workspace_artifacts: object) -> tuple[str, int]:
    paths = []
    items = workspace_artifacts if isinstance(workspace_artifacts, list) else []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if (
            item.get("structured_output") != NMAP_XML_STRUCTURED_OUTPUT
            or item.get("source_flag") != NMAP_XML_SOURCE_FLAG
            or item.get("kind") not in {"output", "read_write"}
        ):
            continue
        workspace_path = str(item.get("workspace_path") or "").strip()
        if workspace_path and workspace_path not in paths:
            paths.append(workspace_path)
    return (paths[0] if len(paths) == 1 else "", len(paths))


def load_nmap_xml_for_finalize(
    session_id: str,
    team_id: str,
    run_id: str,
    exit_code: int,
    workspace_artifacts: object,
    workspace_owner: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
    read_owner_workspace_text_file_fn: Callable = read_owner_workspace_text_file,
) -> str | None:
    """Read one unambiguous structured artifact without exposing its path in logs."""
    if int(exit_code) != 0:
        return None
    workspace_path, marked_count = _marked_nmap_xml_path(workspace_artifacts)
    if not workspace_path:
        if marked_count > 1:
            log.warning("NMAP_STRUCTURED_EVIDENCE_ARTIFACT_REJECTED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "marked_artifact_count": marked_count,
            })
        return None
    try:
        return read_owner_workspace_text_file_fn(workspace_owner, workspace_path, cfg)
    except Exception as exc:
        app_metrics.record_run_finalize_error("nmap_evidence")
        log.error("NMAP_STRUCTURED_EVIDENCE_READ_ERROR", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "error_class": type(exc).__name__,
        })
        return None


__all__ = ["load_nmap_xml_for_finalize"]
