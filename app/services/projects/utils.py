# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Shared project workspace utility helpers.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import cast

from config import resolve_effective_cfg
from services.projects.contracts import ProjectWorkspaceQuotaExceeded

log = logging.getLogger("shell")

_QUOTA_KINDS = frozenset({
    "assessment_check_owner",
    "assessment_check_project",
    "assessment_cycle_owner",
    "assessment_cycle_project",
    "assessment_evidence_owner",
    "assessment_evidence_project",
    "assessment_finding_reconciliation",
    "http_profile_project",
    "project_workspace",
})


def cfg_int(key, default, *, cfg=None):
    cfg = resolve_effective_cfg(cfg)
    try:
        value = int(cfg.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = default
    return max(0, value)


def cfg_mb_bytes(key, default_mb, *, cfg=None):
    return cfg_int(key, default_mb, cfg=cfg) * 1024 * 1024


def quota_exceeded(count, key, default):
    limit = cfg_int(key, default)
    return limit > 0 and count >= limit


def normalize_page_limit(value, default=50, maximum=200):
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def normalize_page_offset(value):
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, parsed)


def normalize_page_window(limit=None, offset=0, *, default=50, maximum=200, enabled=True):
    if not enabled:
        return None, 0
    return normalize_page_limit(limit, default, maximum), normalize_page_offset(offset)


def page_metadata(total, limit, offset, item_count, *, has_more=None):
    safe_total = max(0, int(total or 0))
    safe_limit = max(0, int(limit or 0))
    safe_offset = normalize_page_offset(offset)
    safe_item_count = max(0, int(item_count or 0))
    return {
        "total": safe_total,
        "limit": safe_limit,
        "offset": safe_offset,
        "has_more": bool(has_more) if has_more is not None else safe_offset + safe_item_count < safe_total,
    }


def page_payload(items_key, items, total, limit, offset, *, has_more=None, extra=None):
    payload = {items_key: items}
    payload.update(page_metadata(total, limit, offset, len(items), has_more=has_more))
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def metadata_filter_values(filters, key, max_len, *, lower=False):
    raw_values = filters.get(key)
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        raw_items = [raw_values]
    elif isinstance(raw_values, list):
        raw_items = raw_values
    else:
        raw_items = []
    values = []
    seen = set()
    for raw_value in raw_items:
        value = trim_text(raw_value, max_len)
        if lower:
            value = value.lower()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _quota_count(value: object, default: int = 0) -> int:
    try:
        numeric_value = cast(str | bytes | bytearray | int | float, value)
        parsed = int(numeric_value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, parsed)


def raise_quota(
    message,
    *,
    quota_kind="project_workspace",
    owner_kind="unknown",
    project_id="",
    assessment_id="",
    check_id="",
    limit=0,
    current_count=0,
    requested_count=1,
):
    bounded_quota_kind = str(quota_kind or "").strip().lower()
    if bounded_quota_kind not in _QUOTA_KINDS:
        bounded_quota_kind = "project_workspace"
    bounded_owner_kind = str(owner_kind or "").strip().lower()
    if bounded_owner_kind not in {"personal", "team"}:
        bounded_owner_kind = "unknown"
    log.warning(
        "PROJECT_QUOTA_HIT",
        extra={
            "quota_kind": bounded_quota_kind,
            "owner_kind": bounded_owner_kind,
            "project_id": str(project_id or "")[:64],
            "assessment_id": str(assessment_id or "")[:64],
            "check_id": str(check_id or "")[:64],
            "limit": _quota_count(limit),
            "current_count": _quota_count(current_count),
            "requested_count": _quota_count(requested_count, 1),
        },
    )
    raise ProjectWorkspaceQuotaExceeded(message)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def new_project_id() -> str:
    return "prj_" + secrets.token_hex(8)


def new_project_link_id() -> str:
    return "pln_" + secrets.token_hex(8)


def new_run_file_artifact_id() -> str:
    return "rfa_" + secrets.token_hex(8)


def new_entity_label_id() -> str:
    return "lbl_" + secrets.token_hex(8)


def new_entity_note_id() -> str:
    return "note_" + secrets.token_hex(8)


def new_project_target_id() -> str:
    return "tgt_" + secrets.token_hex(8)


def new_finding_id() -> str:
    return "fnd_" + secrets.token_hex(8)


def new_finding_target_id() -> str:
    return "fnt_" + secrets.token_hex(8)


def new_finding_evidence_link_id() -> str:
    return "fev_" + secrets.token_hex(8)


def new_evidence_package_id() -> str:
    return "pkg_" + secrets.token_hex(8)


def trim_text(value, limit):
    return str(value or "").strip()[:limit]


def text_exceeds_limit(value, limit):
    return len(str(value or "").strip()) > limit
