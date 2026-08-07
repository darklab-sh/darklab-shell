# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded filtering for normalized Project Web Surface captures."""

from __future__ import annotations

from collections.abc import Mapping

MAX_GALLERY_ROWS = 200
_PUBLIC_FIELDS = (
    "url",
    "artifact_path",
    "status_code",
    "title",
    "technologies",
    "captured_at",
    "visual_hash",
    "source_run_id",
    "profile_role",
)


def filter_web_surface_rows(
    rows: object,
    *,
    target: str = "",
    status_code: int | None = None,
    technology: str = "",
    profile_role: str = "",
    visual_hash: str = "",
    changed_since: object = None,
    offset: int = 0,
    limit: int = MAX_GALLERY_ROWS,
) -> list[dict[str, object]]:
    """Filter and page metadata rows; binary artifacts remain behind Files routes."""
    values = rows if isinstance(rows, list) else []
    try:
        page_offset = max(0, int(offset))
    except (TypeError, ValueError):
        page_offset = 0
    try:
        page_limit = min(MAX_GALLERY_ROWS, max(0, int(limit)))
    except (TypeError, ValueError):
        page_limit = MAX_GALLERY_ROWS
    target_key = str(target or "").strip().casefold()
    technology_key = str(technology or "").strip().casefold()
    role_key = str(profile_role or "").strip().casefold()
    hash_key = str(visual_hash or "").strip().casefold()
    previous = {str(value).strip().casefold() for value in changed_since} if isinstance(changed_since, (list, tuple, set)) else set()
    result: list[dict[str, object]] = []
    for row in values:
        if not isinstance(row, Mapping):
            continue
        if target_key and target_key not in str(row.get("url") or "").casefold():
            continue
        if status_code is not None and row.get("status_code") != status_code:
            continue
        technologies = {str(item).strip().casefold() for item in row.get("technologies", []) if str(item).strip()}
        if technology_key and technology_key not in technologies:
            continue
        if role_key and str(row.get("profile_role") or "").casefold() != role_key:
            continue
        row_hash = str(row.get("visual_hash") or "").casefold()
        if hash_key and row_hash != hash_key:
            continue
        if previous and row_hash in previous:
            continue
        if page_offset:
            page_offset -= 1
            continue
        result.append({key: row[key] for key in _PUBLIC_FIELDS if key in row})
        if len(result) >= page_limit:
            break
    return result
