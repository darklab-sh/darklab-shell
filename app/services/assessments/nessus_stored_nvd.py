# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stored NVD correlation for applied typed Nessus service evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.assessments.nessus_import_observations import load_nessus_import_version_observations
from services.assessments.stored_nvd_inference import materialize_stored_nvd_cpe_candidate_page


def correlate_nessus_import_with_stored_nvd(
    conn: Any,
    session_id: str,
    *,
    source_batch_id: str,
    team_id: str = "",
    cve_limit: int = 25,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build unsaved candidate pages from persisted exact Nessus observations."""
    parsed = load_nessus_import_version_observations(
        conn, session_id, source_batch_id, team_id=team_id
    )
    pages = []
    candidate_count = 0
    for observation in parsed["observations"]:
        page = materialize_stored_nvd_cpe_candidate_page(
            conn,
            observation,
            source_id=parsed["source_batch_id"],
            source_kind="import",
            observed_at=observation["observed_at"],
            tool_version=observation["tool_version"],
            parser_version=observation["parser_version"],
            limit=cve_limit,
            now=now,
        )
        candidate_count += len(page["candidates"])
        pages.append({**observation, **page})
    return {
        **parsed,
        "observations": pages,
        "observation_count": len(pages),
        "candidate_count": candidate_count,
    }


__all__ = ["correlate_nessus_import_with_stored_nvd"]
