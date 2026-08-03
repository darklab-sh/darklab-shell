# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Application-observed port evidence helpers for Project Overview."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from services.atlas.materializer import url_host_identity
from services.atlas.intel_evidence import port_provenance as _overview_port_provenance  # noqa: F401
from services.atlas.observations import (
    app_evidence_summary as _overview_app_evidence,  # noqa: F401 - compatibility export
    app_port_run_count as _overview_app_port_run_count,  # noqa: F401 - compatibility export
    app_ports_by_host,
    app_services as _overview_app_services,  # noqa: F401 - compatibility export
    public_app_port_record as _overview_public_app_port_record,  # noqa: F401 - compatibility export
    scan_observations_by_entity as _overview_scan_observations_by_entity,  # noqa: F401 - compatibility export
)
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip

_OVERVIEW_LOG_SAMPLE_LIMIT = 5

log = logging.getLogger("shell")


def _overview_app_ports_by_host(
    conn,
    session_id: str,
    team_id: str,
    project_id: str,
    target_ids: list[str],
    log_context: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    return app_ports_by_host(
        conn,
        session_id,
        team_id,
        project_id,
        target_ids,
        log_context=log_context,
        log_event_namespace="PROJECT_OVERVIEW",
    )


def _overview_url_host_entity_ids(
    conn,
    session_id: str,
    team_id: str,
    targets: list[dict[str, Any]],
    log_context: Mapping[str, Any],
) -> dict[str, str]:
    url_hosts: dict[str, tuple[str, str]] = {}
    result: dict[str, str] = {}
    url_target_count = 0
    invalid_url_host_count = 0
    warn_count = 0
    event_extra = dict(log_context)
    url_target_ids: list[str] = []
    for target in targets:
        if str(target.get("type") or "") != "url":
            continue
        url_target_count += 1
        target_id = str(target.get("id") or "")
        if target_id:
            url_target_ids.append(target_id)
    if url_target_ids:
        owner_sql = "url_e.team_id = ?" if team_id else "url_e.session_id = ? AND url_e.team_id = ''"
        owner_params = (team_id,) if team_id else (session_id,)
        host_owner_sql = "host_e.team_id = ?" if team_id else "host_e.session_id = ? AND host_e.team_id = ''"
        host_owner_params = (team_id,) if team_id else (session_id,)
        placeholders = ",".join("?" for _ in url_target_ids)
        rows = conn.execute(
            "SELECT url_e.id AS url_id, host_e.id AS host_id "
            "FROM entities url_e "
            "JOIN entities host_e ON host_e.id = url_e.host_entity_id "
            f"WHERE url_e.id IN ({placeholders}) AND " + owner_sql + " "  # nosec
            "AND " + host_owner_sql + " "  # nosec
            "AND COALESCE(host_e.suppressed, FALSE) = FALSE",
            (*url_target_ids, *owner_params, *host_owner_params),
        ).fetchall()
        result = {
            str(row["url_id"] or ""): str(row["host_id"] or "")
            for row in rows
            if str(row["url_id"] or "") and str(row["host_id"] or "")
        }
    stored_host_link_count = len(result)
    for target in targets:
        if str(target.get("type") or "") != "url":
            continue
        target_id = str(target.get("id") or "")
        if target_id in result:
            continue
        host_type, host_value, skip_reason, derived_host_type = _overview_url_host_identity(
            str(target.get("value") or target.get("canonical_value") or "")
        )
        if target_id and host_type and host_value:
            url_hosts[target_id] = (host_type, host_value)
        else:
            invalid_url_host_count += 1
            if target_id and warn_count < _OVERVIEW_LOG_SAMPLE_LIMIT:
                log.warning("PROJECT_OVERVIEW_URL_HOST_RESOLUTION_SKIPPED", extra={
                    **event_extra,
                    "target_id": target_id,
                    "reason": skip_reason or "invalid_host",
                    "derived_host_type": derived_host_type,
                })
                warn_count += 1
    if not url_hosts:
        log.debug("PROJECT_OVERVIEW_URL_HOST_RESOLUTION_SUMMARY", extra={
            **event_extra,
            "url_target_count": url_target_count,
            "stored_host_link_count": stored_host_link_count,
            "fallback_candidate_count": 0,
            "fallback_resolved_count": 0,
            "fallback_missing_host_entity_count": 0,
            "resolved_host_count": len(result),
            "missing_host_entity_count": 0,
            "invalid_url_host_count": invalid_url_host_count,
        })
        return result
    owner_sql = "team_id = ?" if team_id else "session_id = ? AND team_id = ''"
    owner_params = (team_id,) if team_id else (session_id,)
    host_pairs = sorted({pair for pair in url_hosts.values()})
    pair_clause = " OR ".join("(type = ? AND canonical_value = ?)" for _ in host_pairs)
    pair_params = tuple(value for pair in host_pairs for value in pair)
    rows = conn.execute(
        "SELECT id, type, canonical_value FROM entities "
        "WHERE (" + pair_clause + ") AND " + owner_sql + " "  # nosec
        "AND COALESCE(suppressed, FALSE) = FALSE "
        "ORDER BY type ASC, canonical_value ASC, last_seen_at DESC, id DESC",
        (*pair_params, *owner_params),
    ).fetchall()
    host_entity_ids: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (str(row["type"] or ""), str(row["canonical_value"] or ""))
        if key not in host_entity_ids and str(row["id"] or ""):
            host_entity_ids[key] = str(row["id"])
    for target_id, (host_type, host_value) in url_hosts.items():
        host_entity_id = host_entity_ids.get((host_type, host_value), "")
        if host_entity_id:
            result[target_id] = host_entity_id
    fallback_resolved_count = max(0, len(result) - stored_host_link_count)
    fallback_missing_host_entity_count = max(0, len(url_hosts) - fallback_resolved_count)
    log.debug("PROJECT_OVERVIEW_URL_HOST_RESOLUTION_SUMMARY", extra={
        **event_extra,
        "url_target_count": url_target_count,
        "stored_host_link_count": stored_host_link_count,
        "fallback_candidate_count": len(url_hosts),
        "fallback_resolved_count": fallback_resolved_count,
        "fallback_missing_host_entity_count": fallback_missing_host_entity_count,
        "resolved_host_count": len(result),
        "missing_host_entity_count": fallback_missing_host_entity_count,
        "invalid_url_host_count": invalid_url_host_count,
    })
    return result


def _overview_url_host_identity(value: str) -> tuple[str, str, str, str]:
    identity = url_host_identity(value)
    if identity is not None:
        return identity[0], identity[1], "", identity[0]
    try:
        host = str(urlsplit(value).hostname or "")
    except ValueError:
        return "", "", "invalid_url", ""
    if not host:
        return "", "", "missing_host", ""
    try:
        return "ip", canonical_ip(host), "", "ip"
    except CanonicalizationError:
        pass
    try:
        return "domain", canonical_domain(host), "", "domain"
    except CanonicalizationError:
        return "", "", "invalid_host", ""
