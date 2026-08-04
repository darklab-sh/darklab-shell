# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact, owner-scoped Atlas entity lookup."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any
from urllib.parse import urlsplit

from core.helpers import get_log_session_id
from services.atlas.entity_profile import validate_profile_project_scope
from services.atlas.input_validation import is_ip_network_range
from services.atlas.lookup import entity_detail, run_atlas_read
from services.atlas.lookup_query import LOOKUP_CANDIDATE_LIMIT, exact_lookup_candidate_query
from services.atlas.scope import normalize_team_id
from services.intel.canonical import (
    MAX_CANONICAL_VALUE_BYTES,
    CanonicalizationError,
    canonical_entity,
)


LOOKUP_MODES = frozenset({"auto", "hostname", "ip", "url"})

log = logging.getLogger("shell")


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


_URL_INPUT_MESSAGE = "Enter an absolute HTTP(S) URL, including http:// or https://."


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
        raise AtlasLookupError("invalid_lookup_type", "Lookup type must be auto, hostname, ip, or url.")
    if not isinstance(value, str) or not value.strip():
        raise AtlasLookupError(
            "missing_lookup_value",
            "Enter a hostname, IP address, or absolute HTTP(S) URL.",
        )
    raw_value = value.strip()
    if is_ip_network_range(raw_value):
        raise AtlasLookupError("invalid_lookup_value", "Quick Lookup resolves single hosts, not network ranges.")

    if requested_type == "url":
        if not raw_value.lower().startswith(("http://", "https://")):
            raise AtlasLookupError("invalid_lookup_value", _URL_INPUT_MESSAGE)
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
                raise AtlasLookupError("invalid_lookup_value", _URL_INPUT_MESSAGE) from None
            detected_type = "domain"
        else:
            return LookupIdentity(requested_type, "ip", canonical_ip)

    return LookupIdentity(
        requested_type,
        detected_type,
        _canonicalize(detected_type, raw_value),
    )


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
    lookup_role: str = "requested",
) -> dict[str, Any]:
    started = time.perf_counter()
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
        result = {"match_state": "not_found", "row": None, "candidates": [], "candidates_truncated": False}
    elif len(preferred_rows) == 1:
        result = {"match_state": "found", "row": preferred_rows[0], "candidates": [], "candidates_truncated": False}
    else:
        truncated = len(preferred_rows) > LOOKUP_CANDIDATE_LIMIT
        candidates = [
            _candidate_record(row, team_id=normalized_team_id)
            for row in preferred_rows[:LOOKUP_CANDIDATE_LIMIT]
        ]
        result = {
            "match_state": "ambiguous",
            "row": None,
            "candidates": candidates,
            "candidates_truncated": truncated,
        }

    fields = {
        "session": get_log_session_id(session_id),
        "entity_type": entity_type,
        "scope_kind": "team" if normalized_team_id else "personal",
        "project_scoped": bool(project_id),
        "lookup_role": lookup_role,
        "row_count": len(rows),
        "preferred_count": len(preferred_rows),
        "direct_team_preferred": bool(normalized_team_id and preferred_rows is not rows),
        "match_state": result["match_state"],
        "candidates_truncated": bool(result["candidates_truncated"]),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
    log.debug("ATLAS_LOOKUP_CANDIDATES_RESOLVED", extra=fields)
    if result["match_state"] == "ambiguous":
        log.warning("ATLAS_LOOKUP_AMBIGUOUS", extra=fields)
    return result


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
        lookup_role="parent_host",
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
            log.warning("ATLAS_LOOKUP_PROFILE_UNAVAILABLE", extra={
                "session": get_log_session_id(session_id),
                "entity_type": identity.detected_type,
                "entity_id": str(row["id"])[:160],
                "scope_kind": "team" if normalized_team_id else "personal",
                "project_scoped": bool(normalized_project_id),
                "reason": "selected_entity_not_visible_to_profile",
            })
            result["match_state"] = "not_found"
        else:
            return result
    if identity.detected_type == "url" and result["match_state"] == "not_found":
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
