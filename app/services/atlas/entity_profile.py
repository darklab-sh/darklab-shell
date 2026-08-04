# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded relationship and finding summaries for Atlas entity profiles."""

from __future__ import annotations

from typing import Any

from services.atlas.finding_rollups import (
    add_finding_rollup_group,
    empty_finding_rollup,
)
from services.atlas.intel_evidence import extract_intel_evidence, port_provenance
from services.atlas.intel_profile import intel_overview
from services.atlas.lookup_metadata import list_metadata_for_entities
from services.atlas.observations import (
    app_evidence_summary,
    app_port_run_count,
    app_ports_by_host,
    app_services,
    public_app_port_record,
    scan_observations_by_entity,
)
from services.atlas.records import entity_row_to_dict, finding_row_to_dict
from services.atlas.scope import (
    entity_scope_params,
    entity_scope_sql,
    finding_source_scope_params,
    finding_source_scope_sql,
    metadata_owner_params,
    metadata_owner_sql,
    project_scope_params,
    project_scope_sql,
)
from services.projects.contracts import ProjectWorkspaceError
from services.projects.entity_monitoring import entity_project_monitoring_context


RELATED_ENTITY_LIMIT = 25
RELATIONSHIP_SAMPLE_LIMIT = 5
FINDING_SAMPLE_LIMIT = 5
FINDING_PAGE_LIMIT = 50
_ENTITY_COLUMNS = (
    "id, session_id, type, canonical_value, host_entity_id, attributes_json, "
    "first_seen_at, last_seen_at, occurrence_count, suppressed, suppressed_reason, suppressed_at, created"
)


def profile_intel_overview(
    entity: dict[str, Any],
    snapshots: list[dict[str, Any]],
    summary: dict[str, Any],
    observed: dict[str, Any],
) -> dict[str, Any]:
    """Combine normalized Intel coverage with provider and app evidence."""
    evidence = extract_intel_evidence(snapshots, entity_id=str(entity.get("id") or ""))
    result = intel_overview(summary)
    result.update({
        "provider_ports": evidence["open_ports"],
        "provider_services": evidence["services"],
        "certificate": evidence["certificate"],
        "port_provenance": port_provenance(
            observed["app_ports"],
            evidence["open_ports"],
            observed["app_evidence"],
            has_provider_intel=str(summary.get("status") or "") == "available",
        ),
    })
    return result


def load_profile_project_monitoring(
    session_id: str,
    entity_id: str,
    *,
    team_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    """Load project-only watcher context without broadening owner profiles."""
    return entity_project_monitoring_context(
        session_id,
        project_id,
        entity_id,
        team_id=team_id,
    )


def _project_entity_clause(alias: str, project_id: str) -> tuple[str, list[str]]:
    if not project_id:
        return "", []
    return (
        " AND EXISTS (SELECT 1 FROM project_links profile_link "  # nosec
        "WHERE profile_link.project_id = ? AND profile_link.entity_type = 'atlas_entity' "
        f"AND profile_link.entity_id = {alias}.id)",
        [project_id],
    )


def _profile_scope(team_id: str, project_id: str) -> dict[str, Any]:
    return {
        "kind": "project" if project_id else "owner",
        "owner_kind": "team" if team_id else "personal",
        "team_id": team_id,
        "project_id": project_id,
    }


def validate_profile_project(
    conn,
    session_id: str,
    entity_id: str,
    *,
    team_id: str = "",
    project_id: str = "",
) -> bool:
    """Validate the project context and report whether the entity is visible in it."""
    normalized_project_id = validate_profile_project_scope(
        conn,
        session_id,
        team_id=team_id,
        project_id=project_id,
    )
    if not normalized_project_id:
        return True
    linked = conn.execute(
        "SELECT 1 FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
        (normalized_project_id, entity_id),
    ).fetchone()
    return linked is not None


def validate_profile_project_scope(
    conn,
    session_id: str,
    *,
    team_id: str = "",
    project_id: str = "",
) -> str:
    """Validate and return an owner-scoped profile project id."""
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        return ""
    owner_sql = project_scope_sql("profile_project", team_id)
    project = conn.execute(
        "SELECT 1 FROM projects profile_project WHERE " + owner_sql + " AND profile_project.id = ?",  # nosec
        [*project_scope_params(session_id, team_id), normalized_project_id],
    ).fetchone()
    if not project:
        raise ProjectWorkspaceError("project not found")
    return normalized_project_id


def _decorate_entities(
    conn,
    session_id: str,
    rows,
    *,
    team_id: str,
    project_id: str,
) -> list[dict[str, Any]]:
    entities = [entity_row_to_dict(row) for row in rows]
    ids = [str(entity["id"]) for entity in entities]
    metadata = list_metadata_for_entities(
        conn,
        session_id,
        ids,
        metadata_owner_sql=metadata_owner_sql("", team_id),
        project_scope_sql_value=project_scope_sql("p", team_id),
        team_id=team_id,
    )
    for entity in entities:
        entity.update(metadata.get(str(entity["id"]), {}))
        entity["open_hint"] = {
            "entity_id": entity["id"],
            "project_id": project_id,
        }
    return entities


def _load_parent_host(
    conn,
    session_id: str,
    host_entity_id: str,
    *,
    team_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    if not host_entity_id:
        return None
    owner_sql = entity_scope_sql("parent_e", team_id)
    project_sql, project_params = _project_entity_clause("parent_e", project_id)
    row = conn.execute(
        "SELECT " + _ENTITY_COLUMNS + " FROM entities parent_e WHERE " + owner_sql  # nosec
        + " AND parent_e.id = ? AND COALESCE(parent_e.suppressed, FALSE) = FALSE"
        + project_sql,
        [*entity_scope_params(session_id, team_id), host_entity_id, *project_params],
    ).fetchone()
    parents = _decorate_entities(
        conn,
        session_id,
        [row] if row else [],
        team_id=team_id,
        project_id=project_id,
    )
    return parents[0] if parents else None


def _load_related_entities(
    conn,
    session_id: str,
    entity_id: str,
    entity_type: str,
    *,
    team_id: str,
    project_id: str,
    offset: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    owner_sql = entity_scope_sql("child_e", team_id)
    owner_params = entity_scope_params(session_id, team_id)
    project_sql, project_params = _project_entity_clause("child_e", project_id)
    common_sql = (
        " FROM entities child_e WHERE " + owner_sql
        + " AND child_e.type = ? AND child_e.host_entity_id = ? "
        "AND child_e.host_entity_id != '' "
        "AND COALESCE(child_e.suppressed, FALSE) = FALSE"
        + project_sql
    )
    common_params = [*owner_params, entity_type, entity_id, *project_params]
    total_row = conn.execute("SELECT COUNT(*) AS count" + common_sql, common_params).fetchone()  # nosec
    total = int(total_row["count"] or 0) if total_row else 0
    rows = conn.execute(
        "SELECT " + _ENTITY_COLUMNS + common_sql  # nosec
        + " ORDER BY child_e.last_seen_at DESC, child_e.occurrence_count DESC, child_e.canonical_value ASC "
        "LIMIT ? OFFSET ?",
        [*common_params, RELATED_ENTITY_LIMIT, offset],
    ).fetchall()
    entities = _decorate_entities(
        conn,
        session_id,
        rows,
        team_id=team_id,
        project_id=project_id,
    )
    return entities, {
        "limit": RELATED_ENTITY_LIMIT,
        "offset": offset,
        "shown": len(entities),
        "total": total,
        "has_more": offset + len(entities) < total,
    }


def load_profile_relationships(
    conn,
    session_id: str,
    entity: dict[str, Any],
    *,
    team_id: str = "",
    project_id: str = "",
    related_urls_offset: int = 0,
    related_ports_offset: int = 0,
) -> dict[str, Any]:
    scope = _profile_scope(team_id, project_id)
    safe_url_offset = max(0, int(related_urls_offset or 0))
    safe_port_offset = max(0, int(related_ports_offset or 0))
    related_urls: list[dict[str, Any]] = []
    related_ports: list[dict[str, Any]] = []
    empty_limit = {"limit": RELATED_ENTITY_LIMIT, "offset": 0, "shown": 0, "total": 0, "has_more": False}
    url_limit = dict(empty_limit, offset=safe_url_offset)
    port_limit = dict(empty_limit, offset=safe_port_offset)
    if str(entity.get("type") or "") in {"domain", "ip"}:
        related_urls, url_limit = _load_related_entities(
            conn,
            session_id,
            str(entity["id"]),
            "url",
            team_id=team_id,
            project_id=project_id,
            offset=safe_url_offset,
        )
        related_ports, port_limit = _load_related_entities(
            conn,
            session_id,
            str(entity["id"]),
            "port",
            team_id=team_id,
            project_id=project_id,
            offset=safe_port_offset,
        )
    parent_host = _load_parent_host(
        conn,
        session_id,
        str(entity.get("host_entity_id") or ""),
        team_id=team_id,
        project_id=project_id,
    )
    return {
        "scope": scope,
        "parent_host": parent_host,
        "related_urls": related_urls,
        "related_ports": related_ports,
        "relationship_summary": {
            "parent_host": {
                "type": str(parent_host.get("type") or "") if parent_host else "",
                "total": 1 if parent_host else 0,
                "sample": [parent_host] if parent_host else [],
            },
            "related_urls": {
                "type": "url",
                "total": url_limit["total"],
                "sample": related_urls[:RELATIONSHIP_SAMPLE_LIMIT],
            },
            "related_ports": {
                "type": "port",
                "total": port_limit["total"],
                "sample": related_ports[:RELATIONSHIP_SAMPLE_LIMIT],
            },
        },
        "detail_limits": {"related_urls": url_limit, "related_ports": port_limit},
    }


def load_profile_observed(
    conn,
    session_id: str,
    entity: dict[str, Any],
    relationships: dict[str, Any],
    *,
    source_run_count: int,
    team_id: str = "",
) -> dict[str, Any]:
    """Build the app-owned observation group for an Atlas entity profile."""
    entity_type = str(entity.get("type") or "")
    entity_id = str(entity.get("id") or "")
    host_entity_id = str(entity.get("host_entity_id") or "")
    applicable = entity_type in {"domain", "ip", "url", "port"}
    lookup_entity_id = entity_id if entity_type in {"domain", "ip"} else host_entity_id
    parent_host = relationships.get("parent_host")
    if entity_type in {"url", "port"} and not isinstance(parent_host, dict):
        lookup_entity_id = ""

    scope_note = ""
    if entity_type == "url":
        scope_note = (
            "App scan coverage and ports are tracked on the parent host, not this URL."
            if lookup_entity_id else
            "No stored parent host is available in this scope, so app scan coverage can't be resolved for this URL."
        )
    elif entity_type == "port":
        scope_note = (
            "App scan coverage is tracked on the parent host, not this port."
            if lookup_entity_id else
            "No stored parent host is available in this scope, so app scan coverage can't be resolved for this port."
        )

    observations = scan_observations_by_entity(
        conn,
        session_id,
        team_id,
        [lookup_entity_id] if applicable and lookup_entity_id else [],
    )
    scope = relationships.get("scope")
    profile_project_id = str(scope.get("project_id") or "") if isinstance(scope, dict) else ""
    app_ports_by_host_id = app_ports_by_host(
        conn,
        session_id,
        team_id,
        profile_project_id,
        [lookup_entity_id] if applicable and lookup_entity_id else [],
    )
    raw_app_ports = app_ports_by_host_id.get(lookup_entity_id, [])
    app_port_count = 0
    if raw_app_ports:
        app_port_count = int(raw_app_ports[0].get("_host_total_count") or len(raw_app_ports))
    app_port_runs = app_port_run_count(raw_app_ports)
    project_entity_port_count = 0
    if raw_app_ports:
        project_entity_port_count = int(raw_app_ports[0].get("_host_project_linked_count") or 0)
    public_app_ports = [public_app_port_record(port) for port in raw_app_ports]
    return {
        "state": "observed",
        "source_run_count": max(0, int(source_run_count or 0)),
        "occurrence_count": max(0, int(entity.get("occurrence_count") or 0)),
        "first_seen_at": str(entity.get("first_seen_at") or ""),
        "last_seen_at": str(entity.get("last_seen_at") or ""),
        "app_ports": public_app_ports,
        "app_port_count": app_port_count,
        "app_ports_truncated": app_port_count > len(public_app_ports),
        "app_services": app_services(public_app_ports),
        "app_evidence": app_evidence_summary(
            observations.get(lookup_entity_id),
            app_port_count=app_port_count,
            app_port_run_count=app_port_runs,
            project_entity_port_count=project_entity_port_count,
            host_entity_id=host_entity_id if entity_type in {"url", "port"} else "",
            scope_note=scope_note,
            applicable=applicable,
        ),
        "project_monitoring": load_profile_project_monitoring(
            session_id,
            entity_id,
            team_id=team_id,
            project_id=profile_project_id,
        ),
    }


def profile_finding_project_clause(project_id: str) -> tuple[str, list[str]]:
    if not project_id:
        return "", []
    return (
        " AND (EXISTS (SELECT 1 FROM project_links profile_entity_link "
        "WHERE profile_entity_link.project_id = ? AND profile_entity_link.entity_type = 'atlas_entity' "
        "AND profile_entity_link.entity_id = f.entity_id) "
        "OR EXISTS (SELECT 1 FROM findings_occurrences profile_fo "
        "JOIN project_links profile_occurrence_link ON profile_occurrence_link.entity_type = 'run' "
        "AND profile_occurrence_link.entity_id = profile_fo.run_id "
        "WHERE profile_fo.finding_id = f.id AND profile_occurrence_link.project_id = ?) "
        "OR EXISTS (SELECT 1 FROM project_links profile_run_link "
        "WHERE profile_run_link.project_id = ? AND profile_run_link.entity_type = 'run' "
        "AND (profile_run_link.entity_id = f.run_id OR profile_run_link.entity_id = f.first_run_id "
        "OR profile_run_link.entity_id = f.last_run_id)))",
        [project_id, project_id, project_id],
    )


def _finding_bucket_clause(
    session_id: str,
    entity_id: str,
    bucket: str,
    *,
    team_id: str,
    host_entity: bool,
) -> tuple[str, list[str]] | None:
    if bucket == "direct":
        return "f.entity_id = ?", [entity_id]
    if not host_entity:
        return None
    owner_sql = entity_scope_sql("bucket_e", team_id)
    owner_params = entity_scope_params(session_id, team_id)
    if bucket in {"related_urls", "related_ports"}:
        child_type = "url" if bucket == "related_urls" else "port"
        return (
            "f.entity_id IN (SELECT bucket_e.id FROM entities bucket_e "  # nosec
            "WHERE bucket_e.host_entity_id = ? AND bucket_e.host_entity_id != '' "
            "AND bucket_e.type = ? AND " + owner_sql + ")",
            [entity_id, child_type, *owner_params],
        )
    return (
        "(f.entity_id = ? OR f.entity_id IN (SELECT bucket_e.id FROM entities bucket_e "  # nosec
        "WHERE bucket_e.host_entity_id = ? AND bucket_e.host_entity_id != '' "
        "AND bucket_e.type IN ('url', 'port') AND " + owner_sql + "))",
        [entity_id, entity_id, *owner_params],
    )


def _profile_findings_cte(
    session_id: str,
    bucket_sql: str,
    bucket_params: list[str],
    *,
    team_id: str,
    project_id: str,
) -> tuple[str, list[str]]:
    finding_sql = finding_source_scope_sql("f", team_id)
    triage_sql = metadata_owner_sql("profile_ftd", team_id)
    project_sql, project_params = profile_finding_project_clause(project_id)
    sql = (
        "WITH profile_findings AS (SELECT f.*, e.type AS entity_type, e.canonical_value AS entity_value, "  # nosec
        "COALESCE((SELECT profile_ftd.verification_status FROM finding_triage_details profile_ftd "
        "WHERE " + triage_sql + " AND profile_ftd.finding_id = f.id "
        "ORDER BY profile_ftd.updated DESC LIMIT 1), 'not_started') AS verification_status_key "
        "FROM findings f LEFT JOIN entities e ON e.id = f.entity_id WHERE " + finding_sql
        + " AND " + bucket_sql + project_sql + ") "
    )
    params = [
        *metadata_owner_params(session_id, team_id),
        *finding_source_scope_params(session_id, team_id),
        *bucket_params,
        *project_params,
    ]
    return sql, params


def _empty_rollup(
    entity_id: str,
    bucket: str,
    project_id: str,
    *,
    applicable: bool,
) -> dict[str, Any]:
    return {
        **empty_finding_rollup(applicable=applicable),
        "navigation_hint": {
            "surface": "atlas_findings",
            "profile_entity_id": entity_id,
            "relationship": bucket,
            "project_id": project_id,
        },
    }


def _finding_rollup(
    conn,
    session_id: str,
    entity_id: str,
    bucket: str,
    *,
    team_id: str,
    project_id: str,
    host_entity: bool,
) -> dict[str, Any]:
    bucket_clause = _finding_bucket_clause(session_id, entity_id, bucket, team_id=team_id, host_entity=host_entity)
    rollup = _empty_rollup(
        entity_id,
        bucket,
        project_id,
        applicable=bucket_clause is not None,
    )
    if bucket_clause is None:
        return rollup
    cte_sql, params = _profile_findings_cte(
        session_id,
        bucket_clause[0],
        bucket_clause[1],
        team_id=team_id,
        project_id=project_id,
    )
    rows = conn.execute(
        cte_sql  # nosec
        + "SELECT COALESCE(NULLIF(LOWER(severity), ''), 'unknown') AS severity_key, "
        "COALESCE(NULLIF(LOWER(status), ''), 'new') AS review_state_key, "
        "COALESCE(NULLIF(LOWER(verification_status_key), ''), 'not_started') AS verification_state_key, "
        "COALESCE(suppressed, FALSE) AS is_suppressed, COUNT(*) AS finding_count, "
        "COALESCE(SUM(occurrence_count), 0) AS occurrence_count, "
        "MAX(COALESCE(NULLIF(last_seen_at, ''), created)) AS latest_activity_at "
        "FROM profile_findings GROUP BY 1, 2, 3, 4",
        params,
    ).fetchall()
    for row in rows:
        add_finding_rollup_group(
            rollup,
            count=int(row["finding_count"] or 0),
            occurrence_count=int(row["occurrence_count"] or 0),
            severity=str(row["severity_key"] or "unknown"),
            review_state=str(row["review_state_key"] or "new"),
            verification_state=str(row["verification_state_key"] or "not_started"),
            suppressed=bool(row["is_suppressed"]),
            latest_activity_at=str(row["latest_activity_at"] or ""),
        )
    samples = conn.execute(
        cte_sql  # nosec
        + "SELECT * FROM profile_findings WHERE COALESCE(suppressed, FALSE) = FALSE "
        "ORDER BY CASE LOWER(COALESCE(severity, '')) "
        "WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 "
        "WHEN 'info' THEN 4 ELSE 5 END, "
        "CASE status WHEN 'important' THEN 0 WHEN 'needs_followup' THEN 1 WHEN 'new' THEN 2 "
        "WHEN 'reviewed' THEN 3 WHEN 'false_positive' THEN 4 ELSE 5 END, "
        "last_seen_at DESC, created DESC LIMIT ?",
        [*params, FINDING_SAMPLE_LIMIT],
    ).fetchall()
    rollup["sample"] = [
        {**finding_row_to_dict(row), "verification_status": str(row["verification_status_key"] or "not_started")}
        for row in samples
    ]
    return rollup


def load_profile_finding_summary(
    conn,
    session_id: str,
    entity: dict[str, Any],
    *,
    team_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    entity_id = str(entity["id"])
    host_entity = str(entity.get("type") or "") in {"domain", "ip"}
    buckets = {
        bucket: _finding_rollup(
            conn,
            session_id,
            entity_id,
            bucket,
            team_id=team_id,
            project_id=project_id,
            host_entity=host_entity,
        )
        for bucket in ("direct", "related_urls", "related_ports", "combined")
    }
    return {"scope": _profile_scope(team_id, project_id), **buckets}


def load_profile_finding_page(
    conn,
    session_id: str,
    entity: dict[str, Any],
    *,
    bucket: str = "direct",
    team_id: str = "",
    project_id: str = "",
    offset: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one bounded, visible finding bucket for an entity profile."""
    normalized_bucket = str(bucket or "direct").strip().lower()
    if normalized_bucket not in {"direct", "related_urls", "related_ports", "combined"}:
        raise ValueError("invalid finding bucket")
    entity_id = str(entity["id"])
    host_entity = str(entity.get("type") or "") in {"domain", "ip"}
    bucket_clause = _finding_bucket_clause(
        session_id,
        entity_id,
        normalized_bucket,
        team_id=team_id,
        host_entity=host_entity,
    )
    safe_offset = max(0, int(offset or 0))
    if bucket_clause is None:
        return [], {
            "bucket": normalized_bucket,
            "limit": FINDING_PAGE_LIMIT,
            "offset": safe_offset,
            "shown": 0,
            "total": 0,
            "has_more": False,
        }
    cte_sql, params = _profile_findings_cte(
        session_id,
        bucket_clause[0],
        bucket_clause[1],
        team_id=team_id,
        project_id=project_id,
    )
    total_row = conn.execute(
        cte_sql + "SELECT COUNT(*) AS count FROM profile_findings "  # nosec
        "WHERE COALESCE(suppressed, FALSE) = FALSE",
        params,
    ).fetchone()
    total = int(total_row["count"] or 0) if total_row else 0
    rows = conn.execute(
        cte_sql  # nosec
        + "SELECT * FROM profile_findings WHERE COALESCE(suppressed, FALSE) = FALSE "
        "ORDER BY last_seen_at DESC, created DESC LIMIT ? OFFSET ?",
        [*params, FINDING_PAGE_LIMIT, safe_offset],
    ).fetchall()
    findings = [
        {
            **finding_row_to_dict(row),
            "verification_status": str(row["verification_status_key"] or "not_started"),
        }
        for row in rows
    ]
    return findings, {
        "bucket": normalized_bucket,
        "limit": FINDING_PAGE_LIMIT,
        "offset": safe_offset,
        "shown": len(findings),
        "total": total,
        "has_more": safe_offset + len(findings) < total,
    }
