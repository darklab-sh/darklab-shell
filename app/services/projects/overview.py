"""
Project overview contract helpers.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from core.database import db_connect
from core.helpers import get_log_session_id
from services.atlas.lookup import _row_to_intel_snapshot, _snapshot_has_intel, summarize_intel_snapshots
from services.atlas.scope import metadata_owner_id
from services.projects.contracts import FINDING_REVIEW_STATES, FINDING_VERIFICATION_STATES
from services.projects.metadata import _metadata_owner_where
from services.projects.models import row_to_project, row_to_target
from services.projects.monitoring import get_project_monitoring_summary
from services.projects.queries import _project_atlas_entity_select_sql, _project_entity_owner_clause
from services.projects.scope import project_select_columns, shared_owner_where
from services.projects.targets import _canonical_target_payload
from services.projects.utils import now as _now


OVERVIEW_PAYLOAD_VERSION = 1
OVERVIEW_TARGET_LIMIT = 200
OVERVIEW_TARGET_HIGHLIGHT_LIMIT = 5

CERT_STATUS_EXPIRED = "expired"
CERT_STATUS_EXPIRING_14D = "expiring_14d"
CERT_STATUS_EXPIRING_30D = "expiring_30d"
CERT_STATUS_HEALTHY = "healthy"
CERT_STATUS_UNKNOWN = "unknown"
CERT_STATUS_ORDER = (
    CERT_STATUS_EXPIRED,
    CERT_STATUS_EXPIRING_14D,
    CERT_STATUS_EXPIRING_30D,
    CERT_STATUS_HEALTHY,
    CERT_STATUS_UNKNOWN,
)

RECENT_CHANGE_WINDOWED = "windowed"
RECENT_CHANGE_WATCHER_CONTEXT_ONLY = "watcher-context-only"
RECENT_CHANGE_NOT_MONITORED = "not-monitored"

FINDING_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

FINDING_REVIEW_STATE_ORDER = ("new", "reviewed", "important", "needs_followup", "false_positive")
FINDING_VERIFICATION_STATE_ORDER = (
    "not_started",
    "ready_to_verify",
    "verified",
    "needs_retest",
    "not_applicable",
)
_TARGET_ENTITY_TYPES = {"domain", "ip", "url"}
_PORT_LIST_LIMIT = 24
_SERVICE_LIST_LIMIT = 24
_RECENT_CHANGE_LIMIT = 10

log = logging.getLogger("shell")


def overview_payload_contract(project: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the stable top-level shape that the overview endpoint will fill."""
    return {
        "project": dict(project or {}),
        "generated_at": "",
        "payload_version": OVERVIEW_PAYLOAD_VERSION,
        "targets": [],
        "rollups": {
            "target_count": 0,
            "certificate_statuses": {status: 0 for status in CERT_STATUS_ORDER},
            "finding_severities": {severity: 0 for severity in FINDING_SEVERITY_RANK},
            "recent_change_state": RECENT_CHANGE_NOT_MONITORED,
        },
        "recent_changes": [],
    }


def overview_identity_for_target_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    """Map a Project target payload onto the existing Atlas entity identity contract."""
    entity_type, canonical_value = _canonical_target_payload(payload)
    return {
        "entity_type": entity_type,
        "canonical_value": canonical_value,
        "display_label": f"{entity_type}:{canonical_value}",
    }


def classify_certificate_status(days_until_expiry: int | None, *, has_certificate_data: bool = True) -> str:
    if not has_certificate_data or days_until_expiry is None:
        return CERT_STATUS_UNKNOWN
    if days_until_expiry < 0:
        return CERT_STATUS_EXPIRED
    if days_until_expiry <= 14:
        return CERT_STATUS_EXPIRING_14D
    if days_until_expiry <= 30:
        return CERT_STATUS_EXPIRING_30D
    return CERT_STATUS_HEALTHY


def severity_rank(severity: str) -> int:
    return FINDING_SEVERITY_RANK.get(str(severity or "").strip().lower(), 99)


def highest_actionable_finding_severity(findings: Iterable[Mapping[str, Any]]) -> str:
    best = ""
    best_rank = 99
    for finding in findings:
        if bool(finding.get("suppressed")):
            continue
        review_state = str(
            finding.get("review_state")
            or finding.get("status")
            or ""
        ).strip().lower()
        if review_state == "false_positive":
            continue
        severity = str(finding.get("severity") or "").strip().lower()
        rank = severity_rank(severity)
        if severity and rank < best_rank:
            best = severity
            best_rank = rank
    return best


def finding_state_counts(findings: Iterable[Mapping[str, Any]], *, include_verification: bool = True) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "by_review_state": {state: 0 for state in FINDING_REVIEW_STATE_ORDER},
        "suppressed": 0,
    }
    if include_verification:
        counts["by_verification_state"] = {state: 0 for state in FINDING_VERIFICATION_STATE_ORDER}
    for finding in findings:
        if bool(finding.get("suppressed")):
            counts["suppressed"] += 1
        review_state = str(
            finding.get("review_state")
            or finding.get("status")
            or ""
        ).strip().lower()
        if review_state in FINDING_REVIEW_STATES:
            counts["by_review_state"][review_state] += 1
        verification_state = str(
            finding.get("verification_status")
            or finding.get("verification_state")
            or ""
        ).strip().lower()
        if include_verification and verification_state in FINDING_VERIFICATION_STATES:
            counts["by_verification_state"][verification_state] += 1
    return counts


def classify_recent_change_state(monitoring_payload: Mapping[str, Any] | None) -> str:
    payload = monitoring_payload if isinstance(monitoring_payload, Mapping) else {}
    if payload.get("digest_window") or payload.get("window_summary"):
        return RECENT_CHANGE_WINDOWED
    monitors = payload.get("monitors")
    timeline = payload.get("timeline")
    if (isinstance(monitors, list) and monitors) or (isinstance(timeline, list) and timeline):
        return RECENT_CHANGE_WATCHER_CONTEXT_ONLY
    counts = payload.get("counts")
    if isinstance(counts, Mapping) and any(int(value or 0) > 0 for value in counts.values()):
        return RECENT_CHANGE_WATCHER_CONTEXT_ONLY
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        if any(
            int(summary.get(key) or 0) > 0
            for key in ("changed_monitor_count", "recovered_monitor_count", "failed_monitor_count")
        ):
            return RECENT_CHANGE_WATCHER_CONTEXT_ONLY
        top_changes = summary.get("top_changes")
        if isinstance(top_changes, list) and top_changes:
            return RECENT_CHANGE_WATCHER_CONTEXT_ONLY
    return RECENT_CHANGE_NOT_MONITORED


def target_deep_link_hints(
    entity_id: str,
    *,
    run_id: str = "",
    review_state: str = "",
    severity: str = "",
) -> dict[str, dict[str, str]]:
    target_id = str(entity_id or "").strip()
    hints = {
        "entities": {},
        "findings": {},
    }
    if target_id:
        hints["entities"]["target_id"] = target_id
        hints["findings"]["target_id"] = target_id
        hints["findings"]["orphan_filter"] = "all"
    normalized_run_id = str(run_id or "").strip()
    if normalized_run_id:
        hints["entities"]["run_id"] = normalized_run_id
    normalized_review_state = str(review_state or "").strip().lower()
    if normalized_review_state in FINDING_REVIEW_STATES:
        hints["findings"]["review_state"] = normalized_review_state
    normalized_severity = str(severity or "").strip().lower()
    if normalized_severity in FINDING_SEVERITY_RANK:
        hints["findings"]["severity"] = normalized_severity
    return hints


def get_project_intel_overview(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    window_start: str = "",
    window_end: str = "",
) -> dict[str, Any] | None:
    """Return the Project-scoped target intelligence overview payload."""
    log_context = _overview_log_context(session_id, team_id, project_id)
    log.debug("PROJECT_OVERVIEW_BUILD_STARTED", extra={
        **log_context,
        "target_limit": OVERVIEW_TARGET_LIMIT,
        "windowed": bool(window_start or window_end),
    })
    with db_connect() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project_row = conn.execute(
            "SELECT " + project_select_columns() + " FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project_row:
            log.debug("PROJECT_OVERVIEW_BUILD_MISS", extra={
                **log_context,
                "reason": "project_not_found",
            })
            return None
        project = row_to_project(project_row)
        if project is None:
            log.debug("PROJECT_OVERVIEW_BUILD_MISS", extra={
                **log_context,
                "reason": "project_decode_failed",
            })
            return None
        metadata_session = metadata_owner_id(session_id, team_id)
        entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id)
        target_rows = conn.execute(
            _project_atlas_entity_select_sql(target_only=True, team_id=team_id) + " LIMIT ?",
            (
                *owner_params,
                metadata_session,
                metadata_session,
                metadata_session,
                project_id,
                *entity_owner_params,
                OVERVIEW_TARGET_LIMIT + 1
            ),
        ).fetchall()
        targets = [target for row in target_rows if (target := row_to_target(row)) is not None]
        target_truncated = len(targets) > OVERVIEW_TARGET_LIMIT
        if target_truncated:
            log.warning("PROJECT_OVERVIEW_TARGET_LIMIT_REACHED", extra={
                **log_context,
                "target_limit": OVERVIEW_TARGET_LIMIT,
                "loaded_target_count": len(targets),
            })
            targets = targets[:OVERVIEW_TARGET_LIMIT]
        target_ids = [str(target["id"]) for target in targets if target.get("id")]
        snapshots_by_entity = _overview_snapshots_by_entity(conn, metadata_session, target_ids)
        findings_by_entity = _overview_findings_by_entity(conn, session_id, team_id, target_ids)

    monitoring_payload = get_project_monitoring_summary(
        session_id,
        project_id,
        team_id=team_id,
        window_start=window_start,
        window_end=window_end,
    )
    recent_change_state = classify_recent_change_state(monitoring_payload)
    recent_changes = _overview_recent_changes(monitoring_payload, target_ids, log_context=log_context)

    payload = overview_payload_contract(project)
    payload["generated_at"] = _now()
    payload["targets"] = _overview_target_rows(
        targets,
        snapshots_by_entity,
        findings_by_entity,
        recent_changes,
        log_context=log_context,
    )
    payload["recent_changes"] = recent_changes[:_RECENT_CHANGE_LIMIT]
    payload["rollups"] = _overview_rollups(payload["targets"], recent_change_state)
    log.debug("PROJECT_OVERVIEW_PAYLOAD_BUILT", extra={
        **log_context,
        "target_count": len(targets),
        "snapshot_entity_count": len(snapshots_by_entity),
        "finding_entity_count": len(findings_by_entity),
        "recent_change_state": recent_change_state,
        "recent_change_count": len(recent_changes),
        "payload_target_count": len(payload["targets"]),
        "target_truncated": target_truncated,
    })
    return payload


def _overview_log_context(session_id: str, team_id: str, project_id: str) -> dict[str, Any]:
    return {
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
    }


def _overview_snapshots_by_entity(conn, metadata_session: str, target_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not target_ids:
        return {}
    placeholders = ",".join("?" for _ in target_ids)
    rows = conn.execute(
        "SELECT id, entity_id, provider, status, summary, data_json, fetched_at, expires_at "
        "FROM entity_intel_snapshots "
        f"WHERE session_id = ? AND entity_id IN ({placeholders}) "  # nosec
        "ORDER BY entity_id ASC, fetched_at DESC, provider ASC",
        (metadata_session, *target_ids),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["entity_id"] or "")].append(_row_to_intel_snapshot(row))
    return grouped


def _overview_findings_by_entity(
    conn,
    session_id: str,
    team_id: str,
    target_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not target_ids:
        return {}
    placeholders = ",".join("?" for _ in target_ids)
    finding_owner_sql = "AND f.team_id = ? " if team_id else "AND f.session_id = ? AND COALESCE(f.team_id, '') = '' "
    finding_owner_params = (team_id,) if team_id else (session_id,)
    triage_owner_sql, triage_owner_params = _metadata_owner_where(session_id, team_id, table_alias="ftd")
    rows = conn.execute(
        "SELECT f.id, COALESCE(f.entity_id, f.target_id) AS entity_id, f.target_id, "
        "COALESCE(NULLIF(f.severity, ''), 'info') AS severity, "
        "COALESCE(NULLIF(f.status, ''), COALESCE(NULLIF(f.review_state, ''), 'new')) AS review_state, "
        "COALESCE(f.suppressed, FALSE) AS suppressed, "
        "COALESCE(ftd.verification_status, 'not_started') AS verification_status, "
        "f.title, f.last_seen_at, f.created "
        "FROM findings f "
        "LEFT JOIN finding_triage_details ftd ON ftd.finding_id = f.id AND " + triage_owner_sql + " "  # nosec
        "WHERE (COALESCE(f.entity_id, f.target_id) IN (" + placeholders + ") "  # nosec
        "OR f.target_id IN (" + placeholders + ")) "  # nosec
        + finding_owner_sql
        + "ORDER BY f.last_seen_at DESC, f.created DESC",
        (*triage_owner_params, *target_ids, *target_ids, *finding_owner_params),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        entity_id = str(row["entity_id"] or "")
        if not entity_id:
            continue
        grouped[entity_id].append({
            "id": str(row["id"] or ""),
            "entity_id": entity_id,
            "target_id": str(row["target_id"] or ""),
            "severity": str(row["severity"] or "info"),
            "review_state": str(row["review_state"] or "new"),
            "suppressed": bool(row["suppressed"]),
            "verification_status": str(row["verification_status"] or "not_started"),
            "title": str(row["title"] or ""),
            "last_seen_at": str(row["last_seen_at"] or ""),
            "created": str(row["created"] or ""),
        })
    return grouped


def _overview_target_rows(
    targets: list[dict[str, Any]],
    snapshots_by_entity: dict[str, list[dict[str, Any]]],
    findings_by_entity: dict[str, list[dict[str, Any]]],
    recent_changes: list[dict[str, Any]],
    *,
    log_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    recent_targets = {target_id for change in recent_changes for target_id in change.get("target_ids", [])}
    rows = []
    for target in targets:
        entity_id = str(target.get("id") or "")
        entity_type = str(target.get("type") or "")
        snapshots = snapshots_by_entity.get(entity_id, [])
        intel_summary = summarize_intel_snapshots(entity_type, snapshots)
        intel_extract = _overview_intel_extract(snapshots, entity_id=entity_id, log_context=log_context)
        has_intel = str(intel_summary.get("status") or "") == "available"
        has_stale_intel = has_intel and _overview_snapshots_are_stale(snapshots)
        findings = findings_by_entity.get(entity_id, [])
        top_severity = highest_actionable_finding_severity(findings)
        hints = target_deep_link_hints(
            entity_id,
            run_id=str(target.get("source_run_id") or ""),
            severity=top_severity,
        )
        rows.append({
            "entity_id": entity_id,
            "id": entity_id,
            "type": entity_type,
            "value": str(target.get("value") or target.get("canonical_value") or ""),
            "display_label": _overview_display_label(target),
            "target_review_state": str(target.get("review_state") or "confirmed"),
            "source_flags": {
                "project_target": True,
                "has_intel": has_intel,
                "has_stale_intel": has_stale_intel,
                "has_findings": bool(findings),
                "has_recent_changes": entity_id in recent_targets,
            },
            "open_ports": intel_extract["open_ports"],
            "services": intel_extract["services"],
            "certificate": intel_extract["certificate"],
            "top_finding_severity": top_severity,
            "finding_counts": finding_state_counts(findings),
            "intel_summary": {
                **intel_summary,
                "highlights": list(intel_summary.get("highlights") or [])[:OVERVIEW_TARGET_HIGHLIGHT_LIMIT],
            },
            "recent_change_markers": [
                change for change in recent_changes if entity_id in change.get("target_ids", [])
            ][:OVERVIEW_TARGET_HIGHLIGHT_LIMIT],
            "deep_link_hints": hints,
        })
    rows.sort(key=_overview_target_sort_key)
    return rows


def _overview_snapshots_are_stale(snapshots: list[dict[str, Any]]) -> bool:
    usable_snapshots = [snapshot for snapshot in snapshots if _snapshot_has_intel(snapshot)]
    if not usable_snapshots:
        return False
    expired_snapshots = [
        snapshot
        for snapshot in usable_snapshots
        if _is_past_datetime(snapshot.get("expires_at"))
    ]
    return bool(expired_snapshots) and len(expired_snapshots) == len(usable_snapshots)


def _overview_display_label(target: Mapping[str, Any]) -> str:
    entity_type = str(target.get("type") or "").strip()
    value = str(target.get("value") or target.get("canonical_value") or "").strip()
    return f"{entity_type}:{value}" if entity_type and value else value or str(target.get("id") or "")


def _overview_target_sort_key(target: Mapping[str, Any]) -> tuple[int, int, str]:
    severity = str(target.get("top_finding_severity") or "")
    raw_certificate = target.get("certificate")
    certificate = raw_certificate if isinstance(raw_certificate, dict) else {}
    cert_status = str(certificate.get("status") or CERT_STATUS_UNKNOWN)
    return (
        severity_rank(severity),
        CERT_STATUS_ORDER.index(cert_status) if cert_status in CERT_STATUS_ORDER else 99,
        str(target.get("display_label") or ""),
    )


def _overview_rollups(targets: list[dict[str, Any]], recent_change_state: str) -> dict[str, Any]:
    certificate_statuses = {status: 0 for status in CERT_STATUS_ORDER}
    finding_severities = {severity: 0 for severity in FINDING_SEVERITY_RANK}
    ports: set[int] = set()
    services: set[str] = set()
    provider_ids: set[str] = set()
    for target in targets:
        raw_certificate = target.get("certificate")
        certificate = raw_certificate if isinstance(raw_certificate, dict) else {}
        cert_status = str(certificate.get("status") or CERT_STATUS_UNKNOWN)
        if cert_status in certificate_statuses:
            certificate_statuses[cert_status] += 1
        severity = str(target.get("top_finding_severity") or "")
        if severity in finding_severities:
            finding_severities[severity] += 1
        ports.update(port for port in target.get("open_ports", []) if isinstance(port, int))
        services.update(str(service) for service in target.get("services", []) if str(service or ""))
        raw_intel_summary = target.get("intel_summary")
        intel_summary = raw_intel_summary if isinstance(raw_intel_summary, dict) else {}
        provider_ids.update(str(provider) for provider in intel_summary.get("providers_with_data", []) if str(provider or ""))
    return {
        "target_count": len(targets),
        "certificate_statuses": certificate_statuses,
        "finding_severities": finding_severities,
        "open_port_count": len(ports),
        "service_count": len(services),
        "provider_count": len(provider_ids),
        "recent_change_state": recent_change_state,
    }


def _overview_recent_changes(
    monitoring_payload: Mapping[str, Any] | None,
    target_ids: list[str],
    *,
    log_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(monitoring_payload, Mapping):
        return []
    target_id_set = set(target_ids)
    summary = monitoring_payload.get("window_summary")
    if not isinstance(summary, Mapping):
        summary = monitoring_payload.get("summary") if isinstance(monitoring_payload.get("summary"), Mapping) else {}
    changes = summary.get("top_changes") if isinstance(summary, Mapping) else []
    if not isinstance(changes, list):
        return []
    result = []
    for change in changes:
        if not isinstance(change, Mapping):
            continue
        raw_target_ids = change.get("target_ids")
        if isinstance(raw_target_ids, list):
            normalized_ids = [str(item or "") for item in raw_target_ids if str(item or "")]
            ids = [item for item in normalized_ids if item in target_id_set]
            dropped_count = len(normalized_ids) - len(ids)
            if dropped_count > 0:
                log.warning("PROJECT_OVERVIEW_RECENT_CHANGE_TARGETS_DROPPED", extra={
                    **dict(log_context or {}),
                    "fire_id": str(change.get("fire_id") or change.get("id") or ""),
                    "dropped_target_count": dropped_count,
                    "matched_target_count": len(ids),
                })
        else:
            ids = []
        result.append({
            "fire_id": str(change.get("fire_id") or change.get("id") or ""),
            "watcher_id": str(change.get("watcher_id") or ""),
            "severity": str(change.get("severity") or ""),
            "state": str(change.get("state") or change.get("status") or change.get("fire_kind") or ""),
            "target_ids": ids,
            "created": str(change.get("created") or ""),
        })
    return result


def _overview_intel_extract(
    snapshots: list[dict[str, Any]],
    *,
    entity_id: str = "",
    log_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    open_ports: list[int] = []
    services: list[str] = []
    cert_expires_at = ""
    cert_days: int | None = None
    has_cert_data = False
    latest_fetched = ""
    invalid_cert_dates: dict[str, int] = defaultdict(int)
    for snapshot in _overview_extraction_snapshots(snapshots):
        latest_fetched = max(latest_fetched, str(snapshot.get("fetched_at") or ""))
        for provider, payload in _provider_payloads(snapshot, entity_id=entity_id, log_context=log_context):
            for port in _payload_ports(payload):
                if port not in open_ports:
                    open_ports.append(port)
            for service in _payload_services(payload):
                if service not in services:
                    services.append(service)
            expiry = _certificate_expiry_from_payload(payload)
            if expiry:
                has_cert_data = True
                days_until = _days_until(expiry)
                if days_until is None:
                    invalid_cert_dates[provider] += 1
                    continue
                if not cert_expires_at or expiry < cert_expires_at:
                    cert_expires_at = expiry
                    cert_days = days_until
    for provider, invalid_count in invalid_cert_dates.items():
        log.warning("PROJECT_OVERVIEW_CERT_DATE_PARSE_FAILED", extra={
            **dict(log_context or {}),
            "entity_id": entity_id,
            "provider": provider,
            "invalid_cert_date_count": invalid_count,
        })
    open_ports.sort()
    services.sort(key=str.lower)
    return {
        "open_ports": open_ports[:_PORT_LIST_LIMIT],
        "services": services[:_SERVICE_LIST_LIMIT],
        "certificate": {
            "status": classify_certificate_status(cert_days, has_certificate_data=has_cert_data),
            "expires_at": cert_expires_at,
            "days_until_expiry": cert_days,
            "last_checked_at": latest_fetched,
        },
    }


def _latest_snapshots_by_provider(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_provider: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        provider = str(snapshot.get("provider") or "").strip().lower()
        if not provider:
            provider = str(snapshot.get("id") or "")
        current = latest_by_provider.get(provider)
        if current is None or str(snapshot.get("fetched_at") or "") > str(current.get("fetched_at") or ""):
            latest_by_provider[provider] = snapshot
    return sorted(
        latest_by_provider.values(),
        key=lambda snapshot: (str(snapshot.get("fetched_at") or ""), str(snapshot.get("provider") or "")),
        reverse=True,
    )


def _overview_extraction_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_snapshots = _latest_snapshots_by_provider(snapshots)
    fresh_snapshots = [
        snapshot for snapshot in latest_snapshots
        if _snapshot_has_intel(snapshot) and not _is_past_datetime(snapshot.get("expires_at"))
    ]
    return fresh_snapshots or latest_snapshots


def _provider_payloads(
    snapshot: Mapping[str, Any],
    *,
    entity_id: str = "",
    log_context: Mapping[str, Any] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), Mapping) else {}
    providers = data.get("providers") if isinstance(data, Mapping) else {}
    if not isinstance(providers, dict):
        _log_skipped_provider_payload(
            snapshot,
            entity_id,
            provider="",
            payload=providers,
            log_context=log_context,
        )
        return []
    payloads = []
    for provider, payload in providers.items():
        provider_id = str(provider or "")
        if isinstance(payload, dict):
            payloads.append((provider_id, payload))
        else:
            _log_skipped_provider_payload(
                snapshot,
                entity_id,
                provider=provider_id,
                payload=payload,
                log_context=log_context,
            )
    return payloads


def _log_skipped_provider_payload(
    snapshot: Mapping[str, Any],
    entity_id: str,
    *,
    provider: str,
    payload: object,
    log_context: Mapping[str, Any] | None = None,
) -> None:
    status = str(snapshot.get("status") or "")
    event_extra = {
        **dict(log_context or {}),
        "entity_id": entity_id,
        "snapshot_id": str(snapshot.get("id") or ""),
        "provider": provider,
        "status": status,
        "shape": type(payload).__name__,
    }
    if status == "ok":
        log.warning("PROJECT_OVERVIEW_INTEL_PAYLOAD_SKIPPED", extra=event_extra)
    else:
        log.debug("PROJECT_OVERVIEW_INTEL_PAYLOAD_SKIPPED", extra=event_extra)


def _payload_ports(payload: Mapping[str, Any]) -> list[int]:
    values: list[int] = []
    raw_ports = payload.get("ports")
    if isinstance(raw_ports, list):
        for item in raw_ports:
            port = _int_value(item)
            if port is not None and 0 < port <= 65535:
                values.append(port)
    raw_results = payload.get("results")
    if isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, Mapping):
                port = _int_value(item.get("port"))
                if port is not None and 0 < port <= 65535:
                    values.append(port)
    return values


def _payload_services(payload: Mapping[str, Any]) -> list[str]:
    values = []
    for key in ("services", "protocols", "cpes"):
        raw = payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                rendered = str(item or "").strip()
                if rendered:
                    values.append(rendered)
    raw_results = payload.get("results")
    if isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, Mapping):
                rendered = str(item.get("service") or item.get("protocol") or "").strip()
                if rendered:
                    values.append(rendered)
    return values


def _certificate_expiry_from_payload(payload: Mapping[str, Any]) -> str:
    for key in ("latest_expiry", "not_after", "expires_at", "valid_to", "expiration", "expiry", "leaf_not_after"):
        value = _clean_date(payload.get(key))
        if value:
            return value
    for key in ("certificate", "cert", "tls"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            value = _certificate_expiry_from_payload(nested)
            if value:
                return value
    certificates = payload.get("certificates")
    if isinstance(certificates, list):
        values = [
            value
            for item in certificates
            if isinstance(item, Mapping)
            and (value := _certificate_expiry_from_payload(item))
        ]
        return min(values) if values else ""
    return ""


def _clean_date(value: object) -> str:
    rendered = str(value or "").strip()
    if not rendered:
        return ""
    return rendered.replace("Z", "+00:00")


def _days_until(value: str) -> int | None:
    parsed = _parse_overview_datetime(value)
    if parsed is None:
        return None
    delta = parsed - datetime.now(timezone.utc)
    return delta.days


def _is_past_datetime(value: object) -> bool:
    parsed = _parse_overview_datetime(value)
    return parsed is not None and parsed < datetime.now(timezone.utc)


def _parse_overview_datetime(value: object) -> datetime | None:
    rendered = _clean_date(value)
    if not rendered:
        return None
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(rendered)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
