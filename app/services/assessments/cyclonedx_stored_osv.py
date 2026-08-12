# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only stored OSV correlation for exact CycloneDX components."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.assessments.cyclonedx_package_observations import (
    parse_cyclonedx_package_observations,
)
from services.assessments.stored_osv_inference import materialize_stored_osv_package_candidate_page


def correlate_cyclonedx_json_with_stored_osv(
    conn: Any,
    payload: bytes | str,
    *,
    source_batch_id: str,
    observed_at: str = "",
    advisory_limit: int = 25,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build unsaved candidate pages for bounded exact CycloneDX PURLs."""
    parsed = parse_cyclonedx_package_observations(
        payload,
        source_batch_id=source_batch_id,
        observed_at=observed_at,
    )
    pages = []
    candidate_count = 0
    for observation in parsed["observations"]:
        page = materialize_stored_osv_package_candidate_page(
            conn,
            observation,
            source_batch_id=parsed["source_batch_id"],
            observed_at=parsed["observed_at"],
            tool_version=parsed["tool_version"],
            parser_version=parsed["parser_version"],
            limit=advisory_limit,
            now=now,
        )
        candidate_count += len(page["candidates"])
        pages.append({
            **observation,
            **page,
        })
    return {
        **parsed,
        "observations": pages,
        "observation_count": len(pages),
        "candidate_count": candidate_count,
    }


__all__ = ["correlate_cyclonedx_json_with_stored_osv"]
