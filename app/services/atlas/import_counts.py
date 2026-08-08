# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preview and apply count projections for Atlas imports."""

from __future__ import annotations

from typing import Any

from services.atlas.import_analysis import analysis_counts


def preview_counts(parse_payload: dict[str, Any], analysis: dict[str, int]) -> dict[str, Any]:
    collections = {
        key: value if isinstance((value := parse_payload.get(key)), list) else []
        for key in ("entities", "findings", "evidence", "warnings")
    }
    return {
        "rows": int(parse_payload.get("row_count") or 0),
        "skipped": int(parse_payload.get("skipped_count") or 0),
        "valid": sum(len(collections[key]) for key in ("entities", "findings", "evidence")),
        "warnings": len(collections["warnings"]),
        "duplicate": int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"]),
        "new": _new_count(analysis),
        "updated": int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"]),
        **analysis,
    }


def current_apply_counts(
    conn,
    session_id: str,
    team_id: str,
    normalized_rows: dict[str, Any],
    preview_counts_payload: dict[str, Any],
) -> dict[str, Any]:
    counts = dict(preview_counts_payload)
    analysis = analysis_counts(conn, session_id, team_id, normalized_rows)
    counts.update(analysis)
    counts["duplicate"] = int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"])
    counts["new"] = _new_count(analysis)
    counts["updated"] = int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"])
    return counts


def _new_count(analysis: dict[str, int]) -> int:
    return sum(int(analysis[key]) for key in ("entity_new", "finding_new", "evidence_new"))


__all__ = ["current_apply_counts", "preview_counts"]
