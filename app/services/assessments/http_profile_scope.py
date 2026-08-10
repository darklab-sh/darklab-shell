# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Confirmed Project target scope for reusable HTTP profiles."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from services.assessments.http_profile_contracts import (
    HttpProfileConflict,
    HttpProfileError,
    HttpProfileNotFound,
)
from services.assessments.http_profile_validation import normalize_http_host
from services.projects.scope import shared_owner_where


log = logging.getLogger("shell")


def project_hosts(
    conn: Any,
    session_id: str,
    project_id: str,
    *,
    team_id: str,
    require_active: bool = False,
) -> set[str]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    sql = "".join((
        "SELECT p.status, e.type, e.canonical_value FROM projects p ",
        "LEFT JOIN project_links pl ON pl.project_id = p.id ",
        "AND pl.entity_type = 'atlas_entity' AND pl.review_state = 'confirmed' ",
        "LEFT JOIN entities e ON e.id = pl.entity_id AND COALESCE(e.suppressed, FALSE) = FALSE ",
        "WHERE ",
        owner_sql,
        " AND p.id = ? ORDER BY e.type ASC, e.canonical_value ASC",
    ))
    rows = conn.execute(sql, (*owner_params, project_id)).fetchall()
    if not rows:
        raise HttpProfileNotFound("HTTP profile Project was not found in this owner scope")
    if require_active and str(rows[0]["status"] or "") == "archived":
        raise HttpProfileConflict("archived Projects cannot change HTTP profiles")
    hosts: set[str] = set()
    invalid_target_count = 0
    invalid_target_types: set[str] = set()
    for row in rows:
        entity_type = str(row["type"] or "")
        value = str(row["canonical_value"] or "")
        try:
            if entity_type in {"domain", "ip"} and value:
                hosts.add(normalize_http_host(value))
            elif entity_type == "url" and value:
                host = str(urlsplit(value).hostname or "")
                if host:
                    hosts.add(normalize_http_host(host))
        except (HttpProfileError, ValueError):
            invalid_target_count += 1
            invalid_target_types.add(entity_type or "unknown")
    if invalid_target_count:
        log.warning(
            "PROJECT_HTTP_PROFILE_INVALID_TARGETS_SKIPPED",
            extra={
                "project_id": project_id,
                "team_scope": bool(team_id),
                "invalid_target_count": invalid_target_count,
                "invalid_target_types": sorted(invalid_target_types),
            },
        )
    return hosts
