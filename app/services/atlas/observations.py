# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared app-observation summaries for Atlas and Project Overview."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.intel.canonical import CanonicalizationError, parse_canonical_port
from services.assessments.service_actions import service_actions, service_evidence_state
from services.assessments.nmap_profiles import public_nmap_profile
from services.projects.scope import shared_owner_where


APP_PORT_LIST_LIMIT = 24
APP_PORT_BANNER_LIMIT = 160
APP_SERVICE_LIST_LIMIT = 24
_LOG_SAMPLE_LIMIT = 5

log = logging.getLogger("shell")


def scan_observations_by_entity(
    conn,
    session_id: str,
    team_id: str,
    entity_ids: Sequence[str],
) -> dict[str, dict[str, Any]]:
    """Return bounded port-scan observations grouped by target entity."""
    ids = sorted({str(entity_id or "") for entity_id in entity_ids if str(entity_id or "")})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    owner_sql = "team_id = ?" if team_id else "session_id = ? AND team_id = ''"
    owner_params = (team_id,) if team_id else (session_id,)
    rows = conn.execute(
        "SELECT entity_id, run_id, command_root, observed_at, port_entity_count "
        "FROM scan_target_observations "
        f"WHERE entity_id IN ({placeholders}) AND scan_kind = 'port_scan' AND " + owner_sql + " "  # nosec
        "ORDER BY observed_at DESC, run_id DESC",
        (*ids, *owner_params),
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


def app_ports_by_host(
    conn,
    session_id: str,
    team_id: str,
    project_id: str,
    host_entity_ids: Sequence[str],
    *,
    log_context: Mapping[str, Any] | None = None,
    log_event_namespace: str = "ATLAS_ENTITY_PROFILE",
) -> dict[str, list[dict[str, Any]]]:
    """Return bounded, deduplicated app-captured port evidence by host."""
    ids = sorted({str(entity_id or "") for entity_id in host_entity_ids if str(entity_id or "")})
    if not ids:
        return {}
    event_extra = dict(log_context or {})
    event_namespace = str(log_event_namespace or "ATLAS_ENTITY_PROFILE").strip().upper()
    placeholders = ",".join("?" for _ in ids)
    owner_sql = "e.team_id = ?" if team_id else "e.session_id = ? AND e.team_id = ''"
    owner_params = (team_id,) if team_id else (session_id,)
    rows = conn.execute(
        "SELECT e.id, e.host_entity_id, e.canonical_value, e.attributes_json, "
        "e.last_seen_at, e.occurrence_count, "
        "EXISTS ("
        "SELECT 1 FROM project_links pl "
        "WHERE pl.project_id = ? AND pl.entity_type = 'atlas_entity' AND pl.entity_id = e.id"
        ") OR EXISTS ("
        "SELECT 1 FROM entity_run_links per "
        "JOIN project_links prl ON prl.entity_type = 'run' AND prl.entity_id = per.run_id "
        "WHERE per.entity_id = e.id AND prl.project_id = ?"
        ") AS project_linked "
        "FROM entities e "
        f"WHERE e.type = 'port' AND e.host_entity_id IN ({placeholders}) AND " + owner_sql + " "  # nosec
        "AND COALESCE(e.suppressed, FALSE) = FALSE "
        "AND EXISTS (SELECT 1 FROM entity_run_links erl WHERE erl.entity_id = e.id) "
        "ORDER BY e.host_entity_id ASC, e.last_seen_at DESC, e.id DESC",
        (project_id, project_id, *ids, *owner_params),
    ).fetchall()
    run_ids_by_entity = _app_port_run_ids_by_entity(
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
            if warn_count < _LOG_SAMPLE_LIMIT:
                _log_app_port_skip(event_namespace, event_extra, row, reason="missing_host_entity_id")
                warn_count += 1
            continue
        port_record, skip_reason = _app_port_record(row, dialect=dialect)
        if not port_record:
            skipped_malformed_count += 1
            if warn_count < _LOG_SAMPLE_LIMIT:
                _log_app_port_skip(
                    event_namespace,
                    event_extra,
                    row,
                    reason=skip_reason or "invalid_canonical_port",
                )
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
            existing_service = str(existing.get("service") or "").strip().casefold()
            incoming_service = str(port_record.get("service") or "").strip().casefold()
            if existing_service and incoming_service and existing_service != incoming_service:
                existing["_service_conflict"] = True
            existing["occurrence_count"] = int(existing.get("occurrence_count") or 0) + int(
                port_record.get("occurrence_count") or 0
            )
        existing["_project_linked"] = bool(existing.get("_project_linked")) or bool(
            port_record.get("_project_linked")
        )
        existing_run_ids = existing.get("_run_ids")
        if isinstance(existing_run_ids, set):
            existing_run_ids.update(port_record.get("_run_ids", set()))
            existing["source_run_count"] = len(existing_run_ids)
    parsed_by_host = {
        host_id: sorted(records.values(), key=lambda item: (int(item["port"]), str(item["proto"])))
        for host_id, records in by_host.items()
    }
    truncated_host_count = sum(1 for records in parsed_by_host.values() if len(records) > APP_PORT_LIST_LIMIT)
    result = {}
    for host_id, records in parsed_by_host.items():
        total_count = len(records)
        host_run_ids = {
            str(run_id)
            for record in records
            for run_id in record.get("_run_ids", set())
            if str(run_id or "")
        }
        project_linked_count = sum(1 for record in records if bool(record.get("_project_linked")))
        visible_records = records[:APP_PORT_LIST_LIMIT]
        for record in visible_records:
            record["_host_total_count"] = total_count
            record["_host_run_count"] = len(host_run_ids)
            record["_host_project_linked_count"] = project_linked_count
        result[host_id] = visible_records
    log.debug(f"{event_namespace}_APP_PORT_SCAN_SUMMARY", extra={
        **event_extra,
        "lookup_host_count": len(ids),
        "raw_port_row_count": len(rows),
        "parsed_port_count": sum(len(records) for records in parsed_by_host.values()),
        "host_count": len(result),
        "skipped_missing_host_count": skipped_missing_host_count,
        "skipped_malformed_count": skipped_malformed_count,
        "duplicate_port_count": duplicate_port_count,
        "truncated_host_count": truncated_host_count,
    })
    return result


def _log_app_port_skip(
    event_namespace: str,
    event_extra: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    reason: str,
) -> None:
    log.warning(f"{event_namespace}_APP_PORT_ROW_SKIPPED", extra={
        **dict(event_extra),
        "port_entity_id": str(row["id"] or "") if "id" in row.keys() else "",
        "host_entity_id": str(row["host_entity_id"] or "") if "host_entity_id" in row.keys() else "",
        "reason": reason,
    })


def _app_port_run_ids_by_entity(
    conn,
    session_id: str,
    team_id: str,
    entity_ids: Sequence[str],
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


def _app_port_record(row: Mapping[str, Any], *, dialect) -> tuple[dict[str, Any], str]:
    try:
        _host_type, _host, port_text, proto = parse_canonical_port(str(row["canonical_value"] or ""))
    except CanonicalizationError:
        return {}, "invalid_canonical_port"
    try:
        port = int(port_text)
    except (TypeError, ValueError):
        return {}, "invalid_port_number"
    attributes = dialect.decode_json_dict(row["attributes_json"] if "attributes_json" in row.keys() else "{}")
    service = _trim_text(attributes.get("service"))
    version = _trim_text(attributes.get("version"))
    banner = _trim_text(attributes.get("banner"), limit=APP_PORT_BANNER_LIMIT)
    result: dict[str, Any] = {
        "port": port,
        "proto": proto,
        "service": service,
        "version": version,
        "banner_available": bool(banner),
        "occurrence_count": max(0, int(row["occurrence_count"] or 0)),
        "last_seen_at": str(row["last_seen_at"] or ""),
        "source_run_count": 0,
    }
    if banner:
        result["banner"] = banner
    result["_project_linked"] = bool(row["project_linked"]) if "project_linked" in row.keys() else False
    return result, ""


def public_app_port_record(port: Mapping[str, Any]) -> dict[str, Any]:
    result = {str(key): value for key, value in port.items() if not str(key).startswith("_")}
    conflict = bool(port.get("_service_conflict"))
    evidence_state = "needs_review" if conflict else service_evidence_state(
        str(result.get("service") or ""),
        port=int(result.get("port") or 0),
    )
    result["service_evidence_state"] = evidence_state
    if conflict:
        result["service_evidence_reason"] = (
            "Saved scanners reported conflicting services for this port; review the evidence "
            "before choosing an action."
        )
    actions = []
    for action in service_actions(str(result.get("service") or "")):
        public_action = {
            "key": action.key,
            "label": action.label,
            "rationale": action.rationale,
            "command": action.command,
            "policy_level": action.policy_level,
            "target_types": sorted(action.target_types),
            "required_features": sorted(action.required_features),
            "expected_evidence": sorted(action.expected_evidence),
            "unsupported_conditions": list(action.unsupported_conditions),
        }
        if action.nmap_profile:
            public_action["nmap_profile"] = public_nmap_profile(action.nmap_profile)
        if not conflict:
            actions.append(public_action)
    if actions:
        result["assessment_actions"] = actions
    return result


def app_port_run_count(app_ports: Sequence[Mapping[str, Any]]) -> int:
    if app_ports:
        host_run_count = app_ports[0].get("_host_run_count")
        if isinstance(host_run_count, int):
            return max(0, host_run_count)
    run_ids: set[str] = set()
    for port in app_ports:
        raw_run_ids = port.get("_run_ids") if isinstance(port, Mapping) else None
        if isinstance(raw_run_ids, set):
            run_ids.update(str(run_id) for run_id in raw_run_ids if str(run_id or ""))
    return len(run_ids)


def _trim_text(value: Any, *, limit: int = 120) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:max(0, limit - 3)].rstrip() + "..."


def app_services(app_ports: Sequence[Mapping[str, Any]]) -> list[str]:
    services: list[str] = []
    for port in app_ports:
        service = str(port.get("service") or "").strip()
        if not service:
            continue
        version = str(port.get("version") or "").strip()
        label = f"{service} ({version})" if version else service
        if label not in services:
            services.append(label)
        if len(services) >= APP_SERVICE_LIST_LIMIT:
            break
    return services


def app_evidence_summary(
    observation: Mapping[str, Any] | None,
    *,
    app_port_count: int | None = None,
    app_port_run_count: int = 0,
    project_entity_port_count: int = 0,
    host_entity_id: str = "",
    scope_note: str = "",
    applicable: bool = True,
) -> dict[str, Any]:
    """Normalize the app's own port-scan evidence without implying certainty."""
    source = observation if isinstance(observation, Mapping) else {}
    scan_run_count = int(source.get("scan_run_count") or 0)
    port_entity_count = int(source.get("port_entity_count") or 0)
    visible_port_count = port_entity_count if app_port_count is None else int(app_port_count or 0)
    if not applicable:
        coverage_state = "not_applicable"
    elif visible_port_count > 0:
        coverage_state = "app_ports_found"
    elif scan_run_count > 0:
        coverage_state = "scanned_no_ports_seen"
    else:
        coverage_state = "not_scanned"
    roots = source.get("command_roots")
    command_roots = [str(root or "") for root in roots] if isinstance(roots, list) else []
    return {
        "applicable": bool(applicable),
        "coverage_state": coverage_state,
        "scan_run_count": scan_run_count,
        "last_observed_at": str(source.get("last_observed_at") or ""),
        "port_entity_count": port_entity_count,
        "app_port_count": max(0, visible_port_count),
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
