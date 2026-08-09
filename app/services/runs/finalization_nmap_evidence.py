# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Coordinate one Nmap XML read across independent finalization consumers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from services.runs.finalization_nmap_service_evidence import (
    persist_nmap_service_evidence_for_finalize,
)
from services.runs.finalization_nmap_xml import load_nmap_xml_for_finalize
from services.runs.finalization_version_inference import (
    materialize_nmap_inferences_for_finalize,
)


def materialize_nmap_evidence_for_finalize(
    conn: Any,
    session_id: str,
    team_id: str,
    run_id: str,
    exit_code: int,
    finished_iso: str,
    workspace_artifacts: object,
    workspace_owner: Any,
    *,
    cfg: Mapping[str, Any] | None,
    read_owner_workspace_text_file_fn: Callable,
    persist_nmap_xml_service_observations_fn: Callable,
    materialize_nmap_xml_version_inferences_fn: Callable,
) -> tuple[dict | None, dict | None]:
    """Load once, then isolate informational facts from version inference."""
    payload = load_nmap_xml_for_finalize(
        session_id,
        team_id,
        run_id,
        exit_code,
        workspace_artifacts,
        workspace_owner,
        cfg=cfg,
        read_owner_workspace_text_file_fn=read_owner_workspace_text_file_fn,
    )
    service_summary = persist_nmap_service_evidence_for_finalize(
        conn,
        session_id,
        team_id,
        run_id,
        payload,
        finished_iso,
        persist_nmap_xml_service_observations_fn=persist_nmap_xml_service_observations_fn,
    )
    inference_summary = materialize_nmap_inferences_for_finalize(
        conn,
        session_id,
        team_id,
        run_id,
        payload,
        finished_iso,
        materialize_nmap_xml_version_inferences_fn=materialize_nmap_xml_version_inferences_fn,
    )
    return service_summary, inference_summary


__all__ = ["materialize_nmap_evidence_for_finalize"]
