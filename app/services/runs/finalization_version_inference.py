# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort Atlas and version-inference work during run finalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from typing import Any, Callable

from core.helpers import get_log_session_id
from services.assessments.nmap_inference_materialization import (
    materialize_nmap_xml_version_inferences,
)
from services.atlas.materializer import materialize_run_entities
from services.metrics_lazy import app_metrics
from services.runs.persistence import run_finalize_savepoint
from services.runs.workspace_artifact_metadata import (
    NMAP_XML_SOURCE_FLAG,
    NMAP_XML_STRUCTURED_OUTPUT,
)
from services.workspace.files import read_owner_workspace_text_file

log = logging.getLogger("shell")
_INFERENCE_COUNT_FIELDS = (
    "observation_count",
    "candidate_count",
    "attempted_count",
    "materialized_count",
    "finding_created_count",
    "source_created_count",
    "rejected_count",
    "skipped_count",
)


def materialize_run_entities_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    command: str,
    persisted_entries: Sequence[object],
    finished_iso: str,
    *,
    materialize_run_entities_fn: Callable = materialize_run_entities,
) -> list:
    try:
        return run_finalize_savepoint(
            conn,
            "atlas_entities",
            lambda: materialize_run_entities_fn(
                conn,
                session_id,
                run_id,
                persisted_entries,
                team_id=team_id,
                seen_at=finished_iso,
                command=command,
            ),
        )
    except Exception:
        app_metrics.record_run_finalize_error("entity_materialize")
        log.error("ATLAS_ENTITY_CAPTURE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "cmd": command,
        })
    return []


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


def _safe_inference_summary(summary: object) -> dict[str, int | bool]:
    value = summary if isinstance(summary, Mapping) else {}
    return {
        **{key: max(0, int(value.get(key) or 0)) for key in _INFERENCE_COUNT_FIELDS},
        "truncated": bool(value.get("truncated")),
    }


def materialize_nmap_inferences_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    exit_code: int,
    finished_iso: str,
    workspace_artifacts: object,
    workspace_owner: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
    read_owner_workspace_text_file_fn: Callable = read_owner_workspace_text_file,
    materialize_nmap_xml_version_inferences_fn: Callable = materialize_nmap_xml_version_inferences,
) -> dict[str, int | bool] | None:
    """Materialize one validated Nmap XML artifact without risking the saved run."""
    if int(exit_code) != 0:
        return None
    workspace_path, marked_count = _marked_nmap_xml_path(workspace_artifacts)
    if not workspace_path:
        if marked_count > 1:
            log.warning("NMAP_VERSION_INFERENCE_ARTIFACT_REJECTED", extra={
                "run_id": run_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "marked_artifact_count": marked_count,
            })
        return None
    try:
        payload = read_owner_workspace_text_file_fn(workspace_owner, workspace_path, cfg)
        safe_summary = run_finalize_savepoint(
            conn,
            "nmap_version_inference",
            lambda: _safe_inference_summary(
                materialize_nmap_xml_version_inferences_fn(
                    conn,
                    session_id,
                    payload,
                    source_run_id=run_id,
                    team_id=team_id,
                    observed_at=finished_iso,
                )
            ),
        )
    except Exception as exc:
        app_metrics.record_run_finalize_error("version_inference")
        log.error("NMAP_VERSION_INFERENCE_FINALIZE_ERROR", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "error_class": type(exc).__name__,
        })
        return None
    log.info("NMAP_VERSION_INFERENCE_FINALIZED", extra={
        "run_id": run_id,
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        **safe_summary,
    })
    return safe_summary


__all__ = [
    "materialize_nmap_inferences_for_finalize",
    "materialize_run_entities_for_finalize",
]
