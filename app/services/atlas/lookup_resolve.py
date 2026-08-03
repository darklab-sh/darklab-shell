# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact, owner-scoped Atlas entity lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from services.atlas.entity_profile import validate_profile_project_scope
from services.atlas.lookup import entity_detail, run_atlas_read
from services.atlas.scope import entity_scope_params, entity_scope_sql, normalize_team_id
from services.intel.canonical import (
    MAX_CANONICAL_VALUE_BYTES,
    CanonicalizationError,
    canonical_entity,
    entity_signature,
)


LOOKUP_MODES = frozenset({"auto", "hostname", "ip", "url"})
LOOKUP_CANDIDATE_LIMIT = 10
_CANDIDATE_FETCH_LIMIT = LOOKUP_CANDIDATE_LIMIT + 1


class AtlasLookupError(ValueError):
    """A stable validation error for browser and API lookup routes."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LookupIdentity:
    requested_type: str
    detected_type: str
    canonical_value: str


def _url_input_message() -> str:
    return "Enter an absolute HTTP(S) URL, including http:// or https://."


def _looks_like_url_without_http_scheme(value: str) -> bool:
    token = str(value or "").strip()
    lowered = token.lower()
    return (
        "://" in token
        or token.startswith("//")
        or any(marker in token for marker in ("/", "?", "#"))
        or lowered.startswith(("http:", "https:"))
    )


def _canonicalize(entity_type: str, value: str) -> str:
    try:
        canonical_value = canonical_entity(entity_type, value)
    except CanonicalizationError as exc:
        if str(exc) == "canonical value is too long":
            raise AtlasLookupError(
                "lookup_value_too_long",
                f"Canonical lookup values cannot exceed {MAX_CANONICAL_VALUE_BYTES} bytes.",
            ) from exc
        labels = {"domain": "hostname", "ip": "IP address", "url": "HTTP(S) URL"}
        label = labels.get(entity_type, "entity")
        raise AtlasLookupError("invalid_lookup_value", f"Enter a valid {label}.") from exc
    if len(canonical_value.encode("utf-8")) > MAX_CANONICAL_VALUE_BYTES:
        raise AtlasLookupError(
            "lookup_value_too_long",
            f"Canonical lookup values cannot exceed {MAX_CANONICAL_VALUE_BYTES} bytes.",
        )
    return canonical_value


def normalize_lookup_identity(mode: object, value: object) -> LookupIdentity:
    """Normalize a user lookup mode and value without consulting storage."""
    requested_type = str(mode or "auto").strip().lower()
    if requested_type not in LOOKUP_MODES:
        raise AtlasLookupError(
            "invalid_lookup_type",
            "Lookup type must be auto, hostname, ip, or url.",
        )
    if not isinstance(value, str) or not value.strip():
        raise AtlasLookupError(
            "missing_lookup_value",
            "Enter a hostname, IP address, or absolute HTTP(S) URL.",
        )
    raw_value = value.strip()

    if requested_type == "url":
        if not raw_value.lower().startswith(("http://", "https://")):
            raise AtlasLookupError("invalid_lookup_value", _url_input_message())
        detected_type = "url"
    elif requested_type == "ip":
        detected_type = "ip"
    elif requested_type == "hostname":
        if _looks_like_url_without_http_scheme(raw_value):
            raise AtlasLookupError("invalid_lookup_value", "Enter a valid hostname without a URL path.")
        detected_type = "domain"
    elif raw_value.lower().startswith(("http://", "https://")):
        detected_type = "url"
    else:
        try:
            canonical_ip = _canonicalize("ip", raw_value)
        except AtlasLookupError:
            if _looks_like_url_without_http_scheme(raw_value):
                raise AtlasLookupError("invalid_lookup_value", _url_input_message()) from None
            detected_type = "domain"
        else:
            return LookupIdentity(requested_type, "ip", canonical_ip)

    return LookupIdentity(
        requested_type,
        detected_type,
        _canonicalize(detected_type, raw_value),
    )


def exact_lookup_candidate_query(
    session_id: str,
    entity_type: str,
    canonical_value: str,
    *,
    team_id: str = "",
    project_id: str = "",
) -> tuple[str, list[Any]]:
    """Return the bounded type/signature seek used by exact lookup."""
    normalized_team_id = normalize_team_id(team_id)
    normalized_project_id = str(project_id or "").strip()
    scope_sql = entity_scope_sql("lookup_e", normalized_team_id)
    project_sql = ""
    project_params: list[Any] = []
    if normalized_project_id:
        project_sql = (
            " AND EXISTS (SELECT 1 FROM project_links lookup_project_link "
            "WHERE lookup_project_link.project_id = ? "
            "AND lookup_project_link.entity_type = 'atlas_entity' "
            "AND lookup_project_link.entity_id = lookup_e.id)"
        )
        project_params.append(normalized_project_id)
    order_sql = ""
    order_params: list[Any] = []
    if normalized_team_id:
        order_sql = (
            "CASE WHEN lookup_e.team_id = ? AND lookup_e.team_id != '' THEN 0 ELSE 1 END, "
        )
        order_params.append(normalized_team_id)
    sql = (
        "SELECT lookup_e.id, lookup_e.team_id, lookup_e.type, lookup_e.canonical_value, "  # nosec B608
        "lookup_e.first_seen_at, lookup_e.last_seen_at, lookup_e.occurrence_count, "
        "lookup_e.suppressed "
        "FROM entities lookup_e "
        "WHERE lookup_e.type = ? AND lookup_e.signature_hash = ? AND "
        + scope_sql
        + project_sql
        + " ORDER BY "
        + order_sql
        + "lookup_e.last_seen_at DESC, lookup_e.id ASC LIMIT ?"
    )
    params: list[Any] = [
        entity_type,
        entity_signature(entity_type, canonical_value),
        *entity_scope_params(session_id, normalized_team_id),
        *project_params,
        *order_params,
        _CANDIDATE_FETCH_LIMIT,
    ]
    return sql, params


def _candidate_record(row, *, team_id: str) -> dict[str, Any]:
    normalized_team_id = normalize_team_id(team_id)
    row_team_id = str(row["team_id"] or "")
    if normalized_team_id and row_team_id == normalized_team_id:
        provenance = "direct_team"
    elif normalized_team_id:
        provenance = "compatibility_visible"
    else:
        provenance = "personal"
    return {
        "entity_id": str(row["id"]),
        "type": str(row["type"]),
        "canonical_value": str(row["canonical_value"]),
        "provenance": provenance,
        "first_seen_at": row["first_seen_at"] or "",
        "last_seen_at": row["last_seen_at"] or "",
        "occurrence_count": int(row["occurrence_count"] or 0),
        "suppressed": bool(row["suppressed"]),
    }


def _resolve_candidate_rows(
    conn,
    session_id: str,
    entity_type: str,
    canonical_value: str,
    *,
    team_id: str,
    project_id: str,
) -> dict[str, Any]:
    sql, params = exact_lookup_candidate_query(
        session_id,
        entity_type,
        canonical_value,
        team_id=team_id,
        project_id=project_id,
    )
    rows = list(conn.execute(sql, params).fetchall())
    normalized_team_id = normalize_team_id(team_id)
    preferred_rows = rows
    if normalized_team_id:
        direct_rows = [row for row in rows if str(row["team_id"] or "") == normalized_team_id]
        if direct_rows:
            preferred_rows = direct_rows
    if not preferred_rows:
        return {"match_state": "not_found", "row": None, "candidates": [], "candidates_truncated": False}
    if len(preferred_rows) == 1:
        return {"match_state": "found", "row": preferred_rows[0], "candidates": [], "candidates_truncated": False}
    truncated = len(preferred_rows) > LOOKUP_CANDIDATE_LIMIT
    candidates = [
        _candidate_record(row, team_id=normalized_team_id)
        for row in preferred_rows[:LOOKUP_CANDIDATE_LIMIT]
    ]
    return {
        "match_state": "ambiguous",
        "row": None,
        "candidates": candidates,
        "candidates_truncated": truncated,
    }


def _url_parent_identity(canonical_url: str) -> tuple[str, str]:
    hostname = str(urlsplit(canonical_url).hostname or "")
    try:
        return "ip", _canonicalize("ip", hostname)
    except AtlasLookupError:
        return "domain", _canonicalize("domain", hostname)


def _parent_host_candidate(
    conn,
    session_id: str,
    canonical_url: str,
    *,
    team_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    parent_type, parent_value = _url_parent_identity(canonical_url)
    resolved = _resolve_candidate_rows(
        conn,
        session_id,
        parent_type,
        parent_value,
        team_id=team_id,
        project_id=project_id,
    )
    if resolved["match_state"] == "not_found":
        return None
    row = resolved["row"]
    return {
        "detected_type": parent_type,
        "canonical_value": parent_value,
        "match_state": resolved["match_state"],
        "entity": _candidate_record(row, team_id=team_id) if row is not None else None,
        "candidates": resolved["candidates"],
        "candidates_truncated": resolved["candidates_truncated"],
    }


def resolve_entity_lookup(
    conn,
    session_id: str,
    value: object,
    *,
    requested_type: object = "auto",
    team_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    """Resolve an exact saved Atlas entity and return its normal profile payload."""
    identity = normalize_lookup_identity(requested_type, value)
    normalized_team_id = normalize_team_id(team_id)
    normalized_project_id = validate_profile_project_scope(
        conn,
        session_id,
        team_id=normalized_team_id,
        project_id=project_id,
    )
    resolved = _resolve_candidate_rows(
        conn,
        session_id,
        identity.detected_type,
        identity.canonical_value,
        team_id=normalized_team_id,
        project_id=normalized_project_id,
    )
    result = {
        "requested_type": identity.requested_type,
        "detected_type": identity.detected_type,
        "canonical_value": identity.canonical_value,
        "project_id": normalized_project_id,
        "match_state": resolved["match_state"],
        "detail": None,
        "candidates": resolved["candidates"],
        "candidates_truncated": resolved["candidates_truncated"],
        "parent_host_candidate": None,
    }
    row = resolved["row"]
    if row is not None:
        result["detail"] = entity_detail(
            conn,
            session_id,
            str(row["id"]),
            team_id=normalized_team_id,
            project_id=normalized_project_id,
        )
        if result["detail"] is None:
            result["match_state"] = "not_found"
        return result
    if identity.detected_type == "url" and resolved["match_state"] == "not_found":
        result["parent_host_candidate"] = _parent_host_candidate(
            conn,
            session_id,
            identity.canonical_value,
            team_id=normalized_team_id,
            project_id=normalized_project_id,
        )
    return result


def resolve_entity_lookup_for_owner(
    session_id: str,
    value: object,
    *,
    requested_type: object = "auto",
    team_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    """Resolve an exact lookup through the configured database connection."""
    return run_atlas_read(lambda conn: resolve_entity_lookup(
        conn,
        session_id,
        value,
        requested_type=requested_type,
        team_id=team_id,
        project_id=project_id,
    ))
