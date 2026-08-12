# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only stored NVD correlation for structured HTTPx observations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from services.assessments.httpx_version_observations import normalize_httpx_version_observations
from services.assessments.stored_nvd_inference import materialize_stored_nvd_cpe_candidate_page


def correlate_httpx_json_with_stored_nvd(
    conn: Any,
    record: dict[str, Any] | None,
    *,
    source_run_id: str,
    tool_version: str,
    cve_limit: int = 25,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build unsaved candidate pages for bounded exact HTTPx JSON CPEs."""
    parsed = normalize_httpx_version_observations(record, source_run_id=source_run_id)
    normalized_tool_version = _text(tool_version, 128)
    pages = []
    candidate_count = 0
    for observation in parsed["observations"]:
        page = materialize_stored_nvd_cpe_candidate_page(
            conn,
            observation,
            source_id=parsed["source_run_id"],
            source_kind="run",
            observed_at=parsed["observed_at"],
            tool_version=normalized_tool_version,
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
        "tool_version": normalized_tool_version,
        "observations": pages,
        "observation_count": len(pages),
        "candidate_count": candidate_count,
    }


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


__all__ = ["correlate_httpx_json_with_stored_nvd"]
