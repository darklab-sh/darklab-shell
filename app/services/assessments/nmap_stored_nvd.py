# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only stored NVD correlation for structured Nmap observations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.assessments.nmap_version_observations import parse_nmap_xml_cpe_observations
from services.assessments.stored_nvd_inference import materialize_stored_nvd_cpe_candidate_page


def correlate_nmap_xml_with_stored_nvd(
    conn: Any,
    payload: bytes | str,
    *,
    source_run_id: str,
    observed_at: str = "",
    cve_limit: int = 25,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build unsaved candidate pages for bounded exact Nmap XML CPEs."""
    parsed = parse_nmap_xml_cpe_observations(
        payload,
        source_run_id=source_run_id,
        observed_at=observed_at,
    )
    pages = []
    candidate_count = 0
    for observation in parsed["observations"]:
        page = materialize_stored_nvd_cpe_candidate_page(
            conn,
            observation,
            source_id=parsed["source_run_id"],
            source_kind="run",
            observed_at=parsed["observed_at"],
            tool_version=parsed["tool_version"],
            parser_version=parsed["parser_version"],
            limit=cve_limit,
            now=now,
        )
        candidate_count += len(page["candidates"])
        pages.append({
            "observation_id": observation["observation_id"],
            "target": observation["target"],
            **page,
        })
    return {
        **parsed,
        "observations": pages,
        "observation_count": len(pages),
        "candidate_count": candidate_count,
    }


__all__ = ["correlate_nmap_xml_with_stored_nvd"]
