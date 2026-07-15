# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Application-observed port evidence helpers for Project Overview."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.materializer import url_host_identity
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip, parse_canonical_port
from services.projects.scope import shared_owner_where

_APP_PORT_LIST_LIMIT = 24
_APP_PORT_BANNER_LIMIT = 160
_SERVICE_LIST_LIMIT = 24
_OVERVIEW_LOG_SAMPLE_LIMIT = 5

log = logging.getLogger("shell")

def _overview_scan_observations_by_entity(
    conn,
    session_id: str,
    team_id: str,
    target_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not target_ids:
        return {}
    placeholders = ",".join("?" for _ in target_ids)
    owner_sql = "team_id = ?" if team_id else "session_id = ? AND team_id = ''"
    owner_params = (team_id,) if team_id else (session_id,)
    rows = conn.execute(
        "SELECT entity_id, run_id, command_root, observed_at, port_entity_count "
        "FROM scan_target_observations "
        f"WHERE entity_id IN ({placeholders}) AND scan_kind = 'port_scan' AND " + owner_sql + " "  # nosec
        "ORDER BY observed_at DESC, run_id DESC",
        (*target_ids, *owner_params),
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        entity_id = str(row["entity_id"] or "")
        if not entity_id:
            continue
        item = grouped.setdefault(entity_id, {
            "scan_run_count": 0,
            "last_observed_at": "",
            "port_entity_count": 0,
            "command_roots": [],
            "_run_ids": set(),
        })
        run_id = str(row["run_id"] or "")
        if run_id and run_id not in item["_run_ids"]:
            item["_run_ids"].add(run_id)
            item["scan_run_count"] += 1
        observed_at = str(row["observed_at"] or "")
        if observed_at and observed_at > str(item["last_observed_at"] or ""):
            item["last_observed_at"] = observed_at
        item["port_entity_count"] += int(row["port_entity_count"] or 0)
        root = str(row["command_root"] or "").strip().lower()
        if root and root not in item["command_roots"]:
            item["command_roots"].append(root)
    for item in grouped.values():
        item.pop("_run_ids", None)
        item["command_roots"] = sorted(item["command_roots"])
    return grouped


def _overview_app_ports_by_host(
    conn,
    session_id: str,
    team_id: str,
    project_id: str,
    target_ids: list[str],
    log_context: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    if not target_ids:
        return {}
    event_extra = dict(log_context)
    placeholders = ",".join("?" for _ in target_ids)
    owner_sql = "e.team_id = ?" if team_id else "e.session_id = ? AND e.team_id = ''"
    owner_params = (team_id,) if team_id else (session_id,)
    rows = conn.execute(
        "SELECT e.id, e.host_entity_id, e.canonical_value, e.attributes_json, e.last_seen_at, "
        "EXISTS ("
        "SELECT 1 FROM project_links pl "
        "WHERE pl.project_id = ? AND pl.entity_type = 'atlas_entity' AND pl.entity_id = e.id"
        ") AS project_linked "
        "FROM entities e "
        f"WHERE e.type = 'port' AND e.host_entity_id IN ({placeholders}) AND " + owner_sql + " "  # nosec
        "AND COALESCE(e.suppressed, FALSE) = FALSE "
        "AND EXISTS (SELECT 1 FROM entity_run_links erl WHERE erl.entity_id = e.id) "
        "ORDER BY e.host_entity_id ASC, e.last_seen_at DESC, e.id DESC",
        (project_id, *target_ids, *owner_params),
    ).fetchall()
    run_ids_by_entity = _overview_app_port_run_ids_by_entity(
        conn,
        session_id,
        team_id,
        [str(row["id"] or "") for row in rows],
    )
    dialect = dialect_for_backend(get_db_backend())
    by_host: dict[str, dict[tuple[int, str], dict[str, Any]]] = defaultdict(dict)
    skipped_missing_host_count = 0
    skipped_malformed_count = 0
    duplicate_port_count = 0
    warn_count = 0
    for row in rows:
        host_entity_id = str(row["host_entity_id"] or "")
        if not host_entity_id:
            skipped_missing_host_count += 1
            if warn_count < _OVERVIEW_LOG_SAMPLE_LIMIT:
                _overview_log_app_port_skip(event_extra, row, reason="missing_host_entity_id")
                warn_count += 1
            continue
        port_record, skip_reason = _overview_app_port_record(row, dialect=dialect)
        if not port_record:
            skipped_malformed_count += 1
            if warn_count < _OVERVIEW_LOG_SAMPLE_LIMIT:
                _overview_log_app_port_skip(event_extra, row, reason=skip_reason or "invalid_canonical_port")
                warn_count += 1
            continue
        port_record["_run_ids"] = set(run_ids_by_entity.get(str(row["id"] or ""), set()))
        key = (int(port_record["port"]), str(port_record["proto"]))
        existing = by_host[host_entity_id].get(key)
        if existing is None:
            existing = port_record
            by_host[host_entity_id][key] = existing
        else:
            duplicate_port_count += 1
        existing["_project_linked"] = bool(existing.get("_project_linked")) or bool(port_record.get("_project_linked"))
        existing_run_ids = existing.get("_run_ids")
        if isinstance(existing_run_ids, set):
            existing_run_ids.update(port_record.get("_run_ids", set()))
    parsed_by_host = {
        host_id: sorted(records.values(), key=lambda item: (int(item["port"]), str(item["proto"])))
        for host_id, records in by_host.items()
    }
    truncated_host_count = sum(1 for records in parsed_by_host.values() if len(records) > _APP_PORT_LIST_LIMIT)
    result = {}
    for host_id, records in parsed_by_host.items():
        total_count = len(records)
        visible_records = records[:_APP_PORT_LIST_LIMIT]
        for record in visible_records:
            record["_host_total_count"] = total_count
        result[host_id] = visible_records
    log.debug("PROJECT_OVERVIEW_APP_PORT_SCAN_SUMMARY", extra={
        **event_extra,
        "lookup_host_count": len(target_ids),
        "raw_port_row_count": len(rows),
        "parsed_port_count": sum(len(records) for records in parsed_by_host.values()),
        "host_count": len(result),
        "skipped_missing_host_count": skipped_missing_host_count,
        "skipped_malformed_count": skipped_malformed_count,
        "duplicate_port_count": duplicate_port_count,
        "truncated_host_count": truncated_host_count,
    })
    return result


def _overview_log_app_port_skip(event_extra: Mapping[str, Any], row: Mapping[str, Any], *, reason: str) -> None:
    log.warning("PROJECT_OVERVIEW_APP_PORT_ROW_SKIPPED", extra={
        **dict(event_extra),
        "port_entity_id": str(row["id"] or "") if "id" in row.keys() else "",
        "host_entity_id": str(row["host_entity_id"] or "") if "host_entity_id" in row.keys() else "",
        "reason": reason,
    })


def _overview_app_port_run_ids_by_entity(
    conn,
    session_id: str,
    team_id: str,
    entity_ids: list[str],
) -> dict[str, set[str]]:
    ids = sorted({str(entity_id or "") for entity_id in entity_ids if str(entity_id or "")})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="er")
    rows = conn.execute(
        "SELECT erl.entity_id, erl.run_id "
        "FROM entity_run_links erl "
        "JOIN runs er ON er.id = erl.run_id AND " + run_owner_sql + " "  # nosec
        f"WHERE erl.entity_id IN ({placeholders})",  # nosec
        (*run_owner_params, *ids),
    ).fetchall()
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        entity_id = str(row["entity_id"] or "")
        run_id = str(row["run_id"] or "")
        if entity_id and run_id:
            result[entity_id].add(run_id)
    return result


def _overview_app_port_record(row: Mapping[str, Any], *, dialect) -> tuple[dict[str, Any], str]:
    try:
        _host_type, _host, port_text, proto = parse_canonical_port(str(row["canonical_value"] or ""))
    except CanonicalizationError:
        return {}, "invalid_canonical_port"
    try:
        port = int(port_text)
    except (TypeError, ValueError):
        return {}, "invalid_port_number"
    attributes = dialect.decode_json_dict(row["attributes_json"] if "attributes_json" in row.keys() else "{}")
    service = _overview_trim_text(attributes.get("service"))
    version = _overview_trim_text(attributes.get("version"))
    banner = _overview_trim_text(attributes.get("banner"), limit=_APP_PORT_BANNER_LIMIT)
    result: dict[str, Any] = {
        "port": port,
        "proto": proto,
        "service": service,
        "version": version,
    }
    if banner:
        result["banner"] = banner
    result["_project_linked"] = bool(row["project_linked"]) if "project_linked" in row.keys() else False
    return result, ""


def _overview_public_app_port_record(port: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in port.items() if not str(key).startswith("_")}


def _overview_app_port_run_count(app_ports: list[dict[str, Any]]) -> int:
    run_ids: set[str] = set()
    for port in app_ports:
        raw_run_ids = port.get("_run_ids") if isinstance(port, Mapping) else None
        if isinstance(raw_run_ids, set):
            run_ids.update(str(run_id) for run_id in raw_run_ids if str(run_id or ""))
    return len(run_ids)


def _overview_trim_text(value: Any, *, limit: int = 120) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:max(0, limit - 3)].rstrip() + "..."


def _overview_app_services(app_ports: list[dict[str, Any]]) -> list[str]:
    services: list[str] = []
    for port in app_ports:
        service = str(port.get("service") or "").strip()
        if not service:
            continue
        version = str(port.get("version") or "").strip()
        label = f"{service} ({version})" if version else service
        if label not in services:
            services.append(label)
        if len(services) >= _SERVICE_LIST_LIMIT:
            break
    return services


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


def _overview_port_provenance(
    app_ports: list[dict[str, Any]],
    provider_ports: list[int],
    app_evidence: Mapping[str, Any],
    *,
    has_provider_intel: bool,
) -> dict[str, Any]:
    app_numbers = {int(port["port"]) for port in app_ports if isinstance(port.get("port"), int)}
    provider_numbers = {int(port) for port in provider_ports if isinstance(port, int)}
    app_only = sorted(app_numbers - provider_numbers)
    provider_only = sorted(provider_numbers - app_numbers)
    has_app_scan = int(app_evidence.get("scan_run_count") or 0) > 0
    has_drift = has_app_scan and (bool(provider_only) or (has_provider_intel and bool(app_only)))
    return {
        "app": app_ports,
        "provider": provider_ports,
        "divergence": {
            "app_only": app_only,
            "provider_only": provider_only,
            "has_drift": has_drift,
        },
    }


def _overview_app_evidence(
    observation: Mapping[str, Any] | None,
    *,
    app_port_count: int | None = None,
    app_port_run_count: int = 0,
    project_entity_port_count: int = 0,
    host_entity_id: str = "",
    scope_note: str = "",
) -> dict[str, Any]:
    source = observation if isinstance(observation, Mapping) else {}
    scan_run_count = int(source.get("scan_run_count") or 0)
    port_entity_count = int(source.get("port_entity_count") or 0)
    visible_port_count = port_entity_count if app_port_count is None else int(app_port_count or 0)
    if visible_port_count > 0:
        coverage_state = "app_ports_found"
    elif scan_run_count > 0:
        coverage_state = "scanned_no_ports_seen"
    else:
        coverage_state = "not_scanned"
    roots = source.get("command_roots")
    command_roots = [str(root or "") for root in roots] if isinstance(roots, list) else []
    return {
        "coverage_state": coverage_state,
        "scan_run_count": scan_run_count,
        "last_observed_at": str(source.get("last_observed_at") or ""),
        "port_entity_count": port_entity_count,
        "app_port_run_count": max(0, int(app_port_run_count or 0)),
        "project_entity_port_count": max(0, int(project_entity_port_count or 0)),
        "command_roots": [root for root in command_roots if root],
        "host_entity_id": str(host_entity_id or ""),
        "scope_note": str(scope_note or ""),
        "coverage_caveat": (
            "No app-captured ports were surfaced by the observed scan runs; this does not prove no ports exist."
            if coverage_state == "scanned_no_ports_seen" else ""
        ),
    }
