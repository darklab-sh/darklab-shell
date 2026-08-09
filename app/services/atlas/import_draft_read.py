# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, owner-scoped reads for prepared Atlas import drafts."""

from __future__ import annotations

import re
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend, parse_database_backend
from services.atlas.import_analysis import available_options
from services.atlas.import_evidence import preview_samples
from services.atlas.import_helpers import row_set_digest
from services.atlas.import_limits import (
    AtlasImportError,
    preview_sample_limit,
    warning_sample_limit,
)
from services.projects.scope import normalize_team_id
from services.projects.utils import now as project_now

DRAFT_ID_RE = re.compile(r"impd_[0-9a-f]{32}")


def _conn_dialect(conn):
    backend = getattr(conn, "database_backend", get_db_backend())
    return dialect_for_backend(parse_database_backend(backend))


def decode_json_dict(conn, value: Any) -> dict[str, Any]:
    return _conn_dialect(conn).decode_json_dict(value)


def decode_json_list(conn, value: Any) -> list[Any]:
    return _conn_dialect(conn).decode_json_list(value)


def load_draft(conn, session_id: str, draft_id: str, *, team_id: str = ""):
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return conn.execute(
            "SELECT * FROM atlas_import_drafts WHERE team_id = ? AND id = ?",
            (normalized_team_id, draft_id),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM atlas_import_drafts "
        "WHERE (team_id IS NULL OR team_id = '') AND session_id = ? AND id = ?",
        (str(session_id or "").strip(), draft_id),
    ).fetchone()


def get_atlas_import_preview(
    *,
    session_id: str,
    draft_id: str,
    team_id: str = "",
    role: str = "",
) -> dict[str, Any]:
    """Return one bounded, owner-scoped preview for explicit review."""
    normalized_draft_id = str(draft_id or "").strip()
    if not DRAFT_ID_RE.fullmatch(normalized_draft_id):
        raise AtlasImportError("invalid_draft_id", "Import draft id is invalid.")
    with get_db_connect()() as conn:
        draft = load_draft(
            conn,
            session_id,
            normalized_draft_id,
            team_id=team_id,
        )
        if not draft:
            raise AtlasImportError(
                "draft_not_found",
                "Import draft was not found.",
                status_code=404,
            )
        status = str(draft["status"] or "")
        if status == "applied":
            raise AtlasImportError(
                "draft_already_applied",
                "Import draft has already been applied.",
                status_code=409,
            )
        if status != "previewed":
            raise AtlasImportError(
                "draft_not_reviewable",
                "Import draft is not available for review.",
                status_code=409,
            )
        expires_at = str(draft["expires_at"] or "")
        if expires_at < project_now():
            raise AtlasImportError(
                "draft_expired",
                "Import draft has expired.",
                status_code=410,
            )
        normalized_rows = decode_json_dict(conn, draft["normalized_rows_json"])
        stored_digest = str(draft["normalized_rows_sha256"] or "")
        if not stored_digest or row_set_digest(normalized_rows) != stored_digest:
            raise AtlasImportError(
                "digest_mismatch",
                "Import draft no longer matches the previewed row set.",
                status_code=409,
            )
        counts = decode_json_dict(conn, draft["preview_counts_json"])
        warnings = decode_json_list(conn, draft["warning_summary_json"])
        return {
            "ok": True,
            "draft_id": normalized_draft_id,
            "row_set_digest": stored_digest,
            "status": status,
            "created_at": str(draft["created"] or ""),
            "expires_at": expires_at,
            "source_tool": str(draft["source_tool"] or ""),
            "format_id": str(draft["format_id"] or ""),
            "import_name": str(draft["import_name"] or ""),
            "filename": str(draft["filename"] or ""),
            "counts": counts,
            "samples": preview_samples(normalized_rows, preview_sample_limit()),
            "warnings": warnings[:warning_sample_limit()],
            "apply_options": available_options(
                role=role,
                is_team=bool(normalize_team_id(team_id)),
                preview_counts=counts,
            ),
        }
