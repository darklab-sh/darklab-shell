"""
Shared project workspace utility helpers.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from services.projects.contracts import ProjectWorkspaceQuotaExceeded


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


def raise_quota(message):
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
