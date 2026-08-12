# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Materialize confirmed takeover findings from compatible saved evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.assessments.dns_takeover_event_review import build_dnsx_takeover_event_review
from services.assessments.nuclei_takeover_command import reviewed_takeover_command_plan
from services.assessments.nuclei_takeover_templates import reviewed_nuclei_takeover_launch
from services.assessments.takeover_confirmation import confirm_takeover_with_nuclei
from services.assessments.takeover_finding_evidence import project_takeover_evidence
from services.assessments.takeover_finding_persistence import persist_takeover_confirmation


def materialize_takeover_confirmation(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    run_id: str,
    command: str,
    exit_code: int,
    entries: Sequence[object],
) -> dict[str, Any] | None:
    """Save one finding only after revalidating DNS and app-owned Nuclei evidence."""
    nuclei = _single_nuclei_observation(entries, run_id)
    if int(exit_code) != 0 or nuclei is None:
        return None
    evidence, nuclei_line = nuclei
    hostname = str(evidence.get("matched_hostname") or "")
    expected_plan = reviewed_takeover_command_plan("domain", hostname)
    if expected_plan is None or command != expected_plan.command:
        return None
    reviewed = reviewed_nuclei_takeover_launch()
    project_evidence = project_takeover_evidence(
        conn, session_id, team_id, project_id, run_id, entries,
    )
    if project_evidence is None:
        return None
    review = build_dnsx_takeover_event_review(
        project_evidence["dns_events"],
        allowed_source_run_ids=project_evidence["allowed_run_ids"],
    )
    potential = [
        item for item in review.get("reviews", [])
        if isinstance(item, Mapping)
        and item.get("state") == "potential"
        and item.get("hostname") == hostname
    ]
    if len(potential) != 1:
        return None
    source = _source_row(project_evidence["dns_rows"], potential[0].get("source_observation"))
    target = _source_row(project_evidence["dns_rows"], potential[0].get("target_observation"))
    if source is None or target is None:
        return None
    confirmed = confirm_takeover_with_nuclei(
        potential[0],
        evidence,
        dns_source_observation=source["observation"],
        dns_target_observation=target["observation"],
        reviewed_templates={reviewed.template.template_id: reviewed.template.registry_entry()},
        allowed_source_run_ids=project_evidence["allowed_run_ids"],
    )
    if confirmed.get("confirmation_status") != "confirmed":
        return None
    return persist_takeover_confirmation(
        conn, session_id, team_id, project_id, run_id, hostname,
        confirmed, nuclei_line, source, target,
    )


def _single_nuclei_observation(
    entries: Sequence[object],
    run_id: str,
) -> tuple[dict[str, Any], int] | None:
    rows: list[tuple[dict[str, Any], int]] = []
    for fallback_index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        detail = entry.get("source_detail")
        values = detail.get("nuclei_takeover_observations") if isinstance(detail, Mapping) else None
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, Mapping) or str(value.get("source_run_id") or "") != run_id:
                return None
            line_number = entry.get("line_index")
            rows.append((dict(value), line_number if isinstance(line_number, int) else fallback_index))
    return rows[0] if len(rows) == 1 else None


def _source_row(rows: object, reference: object) -> dict[str, Any] | None:
    if not isinstance(rows, Mapping) or not isinstance(reference, Mapping):
        return None
    row = rows.get(str(reference.get("observation_id") or ""))
    return dict(row) if isinstance(row, Mapping) else None


__all__ = ["materialize_takeover_confirmation"]
