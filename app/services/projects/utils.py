"""
Shared project workspace utility helpers.
"""

from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone

from services.projects.contracts import ProjectWorkspaceQuotaExceeded

log = logging.getLogger("shell")


def cfg_int(key, default, *, cfg=None):
    if cfg is None:
        from config import CFG
        cfg = CFG
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


def raise_quota(message):
    log.warning("PROJECT_QUOTA_HIT", extra={"reason": str(message or "")})
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


def new_evidence_package_id() -> str:
    return "pkg_" + secrets.token_hex(8)


def trim_text(value, limit):
    return str(value or "").strip()[:limit]


def text_exceeds_limit(value, limit):
    return len(str(value or "").strip()) > limit
