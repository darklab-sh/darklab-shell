# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Small pure helpers for Atlas import workflows."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.helpers import get_log_session_id
from services.teams.capabilities import Capability

MAX_SOURCE_TOOL_LEN = 64
MAX_FILENAME_LEN = 160


def safe_label(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def safe_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def safe_filename(value: Any) -> str:
    filename = str(value or "").replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^A-Za-z0-9._ -]+", "_", filename).strip(" .")
    return filename[:MAX_FILENAME_LEN]


def source_tool_key(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_")[:MAX_SOURCE_TOOL_LEN]


def stable_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def row_set_digest(normalized_rows: dict[str, Any]) -> str:
    return sha256_text(stable_json(normalized_rows))


def safe_count_fields(counts: dict[str, Any]) -> dict[str, int]:
    fields: dict[str, int] = {}
    for key in (
        "rows",
        "valid",
        "skipped",
        "warnings",
        "duplicate",
        "new",
        "updated",
        "entity_valid",
        "entity_new",
        "entity_duplicate",
        "finding_valid",
        "finding_new",
        "finding_duplicate",
        "finding_subject_entities_to_create",
        "project_target_candidates",
        "entities_created",
        "entities_updated",
        "findings_created",
        "findings_updated",
        "finding_remediations_imported",
        "entity_links",
        "finding_occurrences",
        "project_links_added",
        "project_links_existing",
        "project_targets_created",
        "project_targets_existing",
    ):
        if key not in counts:
            continue
        try:
            fields[key] = int(counts.get(key) or 0)
        except (TypeError, ValueError):
            fields[key] = 0
    return fields


def required_capability_values(required: set[Capability] | list[Capability] | tuple[Capability, ...]) -> list[str]:
    return sorted(capability.value for capability in required)


def filename_log_fields(filename: str) -> dict[str, Any]:
    return {
        "has_filename": bool(filename),
        "filename_sha256_prefix": hashlib.sha256(filename.encode("utf-8", errors="replace")).hexdigest()[:12]
        if filename else "",
    }


def option_log_fields(options: dict[str, bool]) -> dict[str, bool]:
    return {
        **options,
        **{f"option_{key}": value for key, value in options.items()},
    }


def apply_context_fields(
    *,
    session_id: str,
    team_id: str,
    actor_member_id: str,
    role: str,
    draft_id: str,
    batch_id: str,
    project_id: str,
    options: dict[str, bool],
) -> dict[str, Any]:
    return {
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "actor_role": role,
        "draft_id": draft_id,
        "batch_id": batch_id,
        "project_id": project_id,
        **option_log_fields(options),
    }


def update_apply_log_context(log_context: dict[str, Any] | None, **fields: Any) -> None:
    if log_context is not None:
        log_context.update(fields)
