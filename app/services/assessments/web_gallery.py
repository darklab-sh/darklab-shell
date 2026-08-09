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


def normalize_web_surface_filters(values: object) -> dict[str, object]:
    """Normalize bounded collection filters shared by browser and API readers."""
    source = values if isinstance(values, Mapping) else {}
    status_value = source.get("status_code")
    try:
        status_code = int(status_value) if isinstance(status_value, (str, int)) else None
    except (TypeError, ValueError):
        status_code = None
    if status_code is not None and not 100 <= status_code <= 599:
        status_code = None
    return {
        "target": str(source.get("target") or "").strip()[:512],
        "status_code": status_code,
        "technology": str(source.get("technology") or "").strip()[:80],
        "profile_role": str(source.get("profile_role") or "").strip()[:80],
        "visual_hash": str(source.get("visual_hash") or "").strip()[:256],
    }


def web_surface_filters_active(filters: Mapping[str, object]) -> bool:
    """Return whether a normalized filter set narrows the collection."""
    return any(value is not None and value != "" for value in filters.values())


def web_surface_row_matches(row: object, filters: Mapping[str, object]) -> bool:
    """Match one metadata row without exposing non-public capture fields."""
    if not isinstance(row, Mapping):
        return False
    target = str(filters.get("target") or "").casefold()
    if target and target not in str(row.get("url") or "").casefold():
        return False
    status_code = filters.get("status_code")
    if status_code is not None and row.get("status_code") != status_code:
        return False
    technology = str(filters.get("technology") or "").casefold()
    role = str(filters.get("profile_role") or "").casefold()
    visual_hash = str(filters.get("visual_hash") or "").casefold()
    technologies = {str(item).strip().casefold() for item in row.get("technologies", []) if str(item).strip()}
    return not (
        (technology and technology not in technologies)
        or (role and str(row.get("profile_role") or "").casefold() != role)
        or (visual_hash and str(row.get("visual_hash") or "").casefold() != visual_hash)
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
    if page_limit == 0:
        return []
    filters = normalize_web_surface_filters({
        "target": target,
        "status_code": status_code,
        "technology": technology,
        "profile_role": profile_role,
        "visual_hash": visual_hash,
    })
    previous = (
        {str(value).strip().casefold() for value in changed_since}
        if isinstance(changed_since, (list, tuple, set))
        else set()
    )
    result: list[dict[str, object]] = []
    for row in values:
        if not web_surface_row_matches(row, filters):
            continue
        row_hash = str(row.get("visual_hash") or "").casefold()
        if previous and row_hash in previous:
            continue
        if page_offset:
            page_offset -= 1
            continue
        result.append({key: row[key] for key in _PUBLIC_FIELDS if key in row})
        if len(result) >= page_limit:
            break
    return result


def web_surface_rows_from_events(events: object) -> list[dict[str, object]]:
    """Extract normalized screenshot metadata from persisted run-event wires."""
    values = events if isinstance(events, list) else []
    rows: list[dict[str, object]] = []
    for event in values:
        if not isinstance(event, Mapping):
            continue
        detail = event.get("source_detail")
        if not isinstance(detail, Mapping):
            continue
        captures = detail.get("screenshots")
        if not isinstance(captures, list):
            continue
        for capture in captures:
            if not isinstance(capture, Mapping) or not capture.get("url"):
                continue
            rows.append({key: capture[key] for key in _PUBLIC_FIELDS if key in capture})
            if len(rows) >= MAX_GALLERY_ROWS:
                return rows
    return rows
