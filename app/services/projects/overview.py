"""
Project overview contract helpers.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.atlas.lookup import _row_to_intel_snapshot, summarize_intel_snapshots
from services.atlas.scope import metadata_owner_id
from services.projects.contracts import FINDING_REVIEW_STATES, FINDING_VERIFICATION_STATES
from services.projects.metadata import _metadata_owner_where
from services.projects.models import row_to_project, row_to_target
from services.projects.monitoring import get_project_monitoring_summary
from services.projects.overview_intel import (
    CERT_STATUS_EXPIRED as CERT_STATUS_EXPIRED,
    CERT_STATUS_EXPIRING_14D as CERT_STATUS_EXPIRING_14D,
    CERT_STATUS_EXPIRING_30D as CERT_STATUS_EXPIRING_30D,
    CERT_STATUS_HEALTHY as CERT_STATUS_HEALTHY,
    CERT_STATUS_ORDER,
    CERT_STATUS_UNKNOWN,
    _overview_intel_extract,
    _overview_snapshots_are_stale,
    classify_certificate_status as classify_certificate_status,
)

from services.projects.overview_app import (
    _overview_app_evidence,
    _overview_app_port_run_count,
    _overview_app_ports_by_host,
    _overview_app_services,
    _overview_port_provenance,
    _overview_public_app_port_record,
    _overview_scan_observations_by_entity,
    _overview_url_host_entity_ids,
)
from services.projects.queries import _project_atlas_entity_select_sql, _project_entity_owner_clause
from services.projects.scope import project_select_columns, shared_owner_where
from services.projects.targets import _canonical_target_payload
from services.projects.utils import now as _now
from services.teams.storage import token_hash


OVERVIEW_PAYLOAD_VERSION = 1
OVERVIEW_TARGET_LIMIT = 200
OVERVIEW_TARGET_HIGHLIGHT_LIMIT = 5

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
_APP_PORT_LIST_LIMIT = _PORT_LIST_LIMIT
_APP_PORT_BANNER_LIMIT = 160
_SERVICE_LIST_LIMIT = 24
_RECENT_CHANGE_LIMIT = 10
_OVERVIEW_ACTIVITY_LIMIT = 5
_OVERVIEW_GAP_LIMIT = 5
_OVERVIEW_LOG_SAMPLE_LIMIT = 5

_ACTIVITY_TARGET_TABS = {
    "entity": "entities",
    "finding": "findings",
    "file": "artifacts",
    "import": "entities",
    "package": "packages",
    "project": "details",
    "report": "report",
    "run": "runs",
    "target": "details",
}

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
            "open_port_count": 0,
            "service_count": 0,
            "provider_count": 0,
            "app_port_count": 0,
            "port_divergence_target_count": 0,
            "app_scan_target_count": 0,
            "app_port_target_count": 0,
            "scanned_no_ports_seen_count": 0,
            "unscanned_target_count": 0,
            "awaiting_verification_target_count": 0,
            "needs_followup_target_count": 0,
            "recent_change_state": RECENT_CHANGE_NOT_MONITORED,
        },
        "recent_changes": [],
        "operational_tempo": {
            "last_run_at": "",
            "last_run_id": "",
            "runs_last_7d": 0,
            "last_finding_triaged_at": "",
            "last_finding_triaged_id": "",
            "last_artifact_at": "",
            "last_artifact_id": "",
        },
        "recent_activity": [],
        "coverage_gaps": {
            "untouched_targets": [],
            "awaiting_verification": [],
            "needs_followup": [],
        },
        "deliverables_status": {
            "last_package_at": "",
            "last_package_id": "",
            "last_package_name": "",
            "last_package_build_at": "",
            "last_package_build_job_id": "",
            "last_report_saved_at": "",
            "last_report_id": "",
            "last_report_exported_at": "",
            "last_report_export_job_id": "",
            "latest_finding_activity_at": "",
            "report_freshness": "not_started",
        },
    }


def overview_identity_for_target_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    """Map a Project target payload onto the existing Atlas entity identity contract."""
    entity_type, canonical_value = _canonical_target_payload(payload)
    return {
        "entity_type": entity_type,
        "canonical_value": canonical_value,
        "display_label": f"{entity_type}:{canonical_value}",
    }


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
    with get_db_connect()() as conn:
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
        url_host_entity_ids = _overview_url_host_entity_ids(conn, session_id, team_id, targets, log_context)
        app_lookup_ids = sorted({*target_ids, *url_host_entity_ids.values()})
        observations_by_entity = _overview_scan_observations_by_entity(conn, session_id, team_id, app_lookup_ids)
        app_ports_by_host = _overview_app_ports_by_host(conn, session_id, team_id, project_id, app_lookup_ids, log_context)
        operational_tempo = _overview_operational_tempo(conn, session_id, team_id, project_id, target_ids)
        recent_activity = _overview_recent_activity(conn, session_id, team_id, project_id)
        deliverables_status = _overview_deliverables_status(conn, session_id, team_id, project_id, target_ids)

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
        observations_by_entity,
        app_ports_by_host,
        url_host_entity_ids,
        recent_changes,
        log_context=log_context,
    )
    payload["recent_changes"] = recent_changes[:_RECENT_CHANGE_LIMIT]
    payload["operational_tempo"] = operational_tempo
    payload["recent_activity"] = recent_activity
    payload["rollups"] = _overview_rollups(payload["targets"], recent_change_state)
    payload["coverage_gaps"] = _overview_coverage_gaps(payload["targets"])
    payload["deliverables_status"] = deliverables_status
    log.debug("PROJECT_OVERVIEW_PAYLOAD_BUILT", extra={
        **log_context,
        "target_count": len(targets),
        "snapshot_entity_count": len(snapshots_by_entity),
        "finding_entity_count": len(findings_by_entity),
        "app_port_host_count": len(app_ports_by_host),
        "url_host_entity_count": len(url_host_entity_ids),
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
    finding_owner_sql = "AND f.team_id = ? " if team_id else "AND f.session_id = ? AND f.team_id = '' "
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


def _run_owner_clause(session_id: str, team_id: str, *, alias: str = "r") -> tuple[str, tuple[Any, ...]]:
    prefix = f"{alias}." if alias else ""
    if team_id:
        return f"{prefix}team_id = ?", (team_id,)
    return f"{prefix}session_id = ? AND {prefix}team_id = ''", (session_id,)


def _project_run_ids(conn, session_id: str, team_id: str, project_id: str) -> list[str]:
    run_owner_sql, run_owner_params = _run_owner_clause(session_id, team_id, alias="r")
    rows = conn.execute(
        "SELECT DISTINCT r.id "
        "FROM project_links l JOIN runs r ON r.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'run' AND " + run_owner_sql,  # nosec
        (project_id, *run_owner_params),
    ).fetchall()
    return [str(row["id"] or "") for row in rows if str(row["id"] or "")]


def _overview_operational_tempo(
    conn,
    session_id: str,
    team_id: str,
    project_id: str,
    target_ids: list[str],
) -> dict[str, Any]:
    run_ids = _project_run_ids(conn, session_id, team_id, project_id)
    tempo = {
        "last_run_at": "",
        "last_run_id": "",
        "runs_last_7d": 0,
        "last_finding_triaged_at": "",
        "last_finding_triaged_id": "",
        "last_artifact_at": "",
        "last_artifact_id": "",
    }
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        run_row = conn.execute(
            "SELECT id, COALESCE(NULLIF(finished, ''), started) AS activity_at "
            "FROM runs "
            f"WHERE id IN ({placeholders}) "  # nosec
            "ORDER BY activity_at DESC, id DESC LIMIT 1",
            tuple(run_ids),
        ).fetchone()
        if run_row:
            tempo["last_run_at"] = str(run_row["activity_at"] or "")
            tempo["last_run_id"] = str(run_row["id"] or "")
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM runs "
            f"WHERE id IN ({placeholders}) AND COALESCE(NULLIF(finished, ''), started) >= ?",  # nosec
            (*run_ids, cutoff),
        ).fetchone()
        tempo["runs_last_7d"] = int(count_row["count"] or 0) if count_row else 0
        artifact_row = conn.execute(
            "SELECT id, created FROM run_file_artifacts "
            f"WHERE run_id IN ({placeholders}) "  # nosec
            "ORDER BY created DESC, id DESC LIMIT 1",
            tuple(run_ids),
        ).fetchone()
        if artifact_row:
            tempo["last_artifact_at"] = str(artifact_row["created"] or "")
            tempo["last_artifact_id"] = str(artifact_row["id"] or "")

    if target_ids:
        placeholders = ",".join("?" for _ in target_ids)
        finding_owner_sql = "AND f.team_id = ? " if team_id else "AND f.session_id = ? AND f.team_id = '' "
        finding_owner_params = (team_id,) if team_id else (session_id,)
        triage_owner_sql, triage_owner_params = _metadata_owner_where(session_id, team_id, table_alias="ftd")
        triage_row = conn.execute(
            "SELECT f.id, ftd.updated "
            "FROM findings f JOIN finding_triage_details ftd ON ftd.finding_id = f.id AND " + triage_owner_sql + " "  # nosec
            "WHERE (COALESCE(f.entity_id, f.target_id) IN (" + placeholders + ") "  # nosec
            "OR f.target_id IN (" + placeholders + ")) "  # nosec
            + finding_owner_sql
            + "ORDER BY ftd.updated DESC, f.id DESC LIMIT 1",
            (*triage_owner_params, *target_ids, *target_ids, *finding_owner_params),
        ).fetchone()
        if triage_row:
            tempo["last_finding_triaged_at"] = str(triage_row["updated"] or "")
            tempo["last_finding_triaged_id"] = str(triage_row["id"] or "")
    return tempo


def _activity_summary(details: Mapping[str, Any] | None) -> str:
    source = details if isinstance(details, Mapping) else {}
    preferred = (
        "name",
        "label",
        "source",
        "review_state",
        "status",
        "redaction_mode",
        "package_id",
        "report_id",
        "file_path",
        "source_path",
        "destination_path",
        "path",
        "old_path",
        "new_path",
    )
    parts = []
    for key in preferred:
        value = source.get(key)
        if value is None or value == "":
            continue
        parts.append(f"{key.replace('_', ' ')}: {value}")
    if not parts:
        for key, value in list(source.items())[:3]:
            if value is None or value == "":
                continue
            parts.append(f"{str(key).replace('_', ' ')}: {value}")
    return " · ".join(str(part) for part in parts[:3])


def _overview_activity_link(target_type: str, target_id: str) -> dict[str, str]:
    normalized_type = str(target_type or "").strip()
    normalized_id = str(target_id or "").strip()
    tab = _ACTIVITY_TARGET_TABS.get(normalized_type, "")
    if not tab:
        return {}
    return {
        "tab": tab,
        "target_type": normalized_type,
        "target_id": normalized_id,
    }


def _overview_recent_activity(conn, session_id: str, team_id: str, project_id: str) -> list[dict[str, Any]]:
    dialect = dialect_for_backend(get_db_backend())
    owner_sql, owner_params = _overview_audit_owner_scope(session_id, team_id)
    rows = conn.execute(
        "SELECT id, event_type, target_type, target_id, details, created "
        "FROM audit_events "
        "WHERE project_id = ? AND " + owner_sql + " "  # nosec
        "ORDER BY created DESC, id DESC LIMIT ?",
        (project_id, *owner_params, _OVERVIEW_ACTIVITY_LIMIT),
    ).fetchall()
    result = []
    for row in rows:
        details = dialect.decode_json_dict(row["details"])
        target_type = str(row["target_type"] or "")
        target_id = str(row["target_id"] or "")
        result.append({
            "id": str(row["id"] or ""),
            "created": str(row["created"] or ""),
            "event_type": str(row["event_type"] or ""),
            "target_type": target_type,
            "target_id": target_id,
            "summary": _activity_summary(details),
            "deep_link": _overview_activity_link(target_type, target_id),
        })
    return result


def _overview_audit_owner_scope(session_id: str, team_id: str) -> tuple[str, tuple[Any, ...]]:
    if team_id:
        return "team_id = ?", (team_id,)
    return "owner_session_hash = ? AND team_id = ''", (token_hash(session_id),)


def _overview_latest_completed_audit_event(
    conn,
    session_id: str,
    team_id: str,
    project_id: str,
    event_type: str,
) -> dict[str, str]:
    owner_sql, owner_params = _overview_audit_owner_scope(session_id, team_id)
    dialect = dialect_for_backend(get_db_backend())
    rows = conn.execute(
        "SELECT id, target_id, job_id, details, created "
        "FROM audit_events "
        "WHERE project_id = ? AND event_type = ? AND " + owner_sql + " "  # nosec
        "ORDER BY created DESC, id DESC LIMIT 20",
        (project_id, event_type, *owner_params),
    ).fetchall()
    for row in rows:
        details = dialect.decode_json_dict(row["details"])
        if str(details.get("status") or "").strip().lower() != "complete":
            continue
        return {
            "id": str(row["id"] or ""),
            "target_id": str(row["target_id"] or ""),
            "job_id": str(row["job_id"] or details.get("job_id") or ""),
            "created": str(row["created"] or ""),
        }
    return {}


def _overview_latest_package(conn, session_id: str, team_id: str, project_id: str) -> dict[str, str]:
    package_where = "project_id = ?"
    package_params: list[Any] = [project_id]
    if not team_id:
        package_where += " AND session_id = ?"
        package_params.append(session_id)
    row = conn.execute(
        "SELECT id, name, status, updated, created "
        "FROM evidence_packages WHERE " + package_where + " "  # nosec
        "ORDER BY updated DESC, created DESC, id DESC LIMIT 1",
        tuple(package_params),
    ).fetchone()
    if not row:
        return {}
    return {
        "id": str(row["id"] or ""),
        "name": str(row["name"] or ""),
        "status": str(row["status"] or ""),
        "updated": str(row["updated"] or row["created"] or ""),
    }


def _overview_latest_report(conn, session_id: str, team_id: str, project_id: str) -> dict[str, str]:
    if team_id:
        report_where = "team_id = ? AND project_id = ?"
        report_params: tuple[Any, ...] = (team_id, project_id)
    else:
        report_where = "session_id = ? AND team_id = '' AND project_id = ?"
        report_params = (session_id, project_id)
    row = conn.execute(
        "SELECT id, updated, created FROM project_reports WHERE " + report_where + " "  # nosec
        "ORDER BY updated DESC, created DESC, id DESC LIMIT 1",
        report_params,
    ).fetchone()
    if not row:
        return {}
    return {
        "id": str(row["id"] or ""),
        "updated": str(row["updated"] or row["created"] or ""),
    }


def _overview_latest_finding_activity_at(
    conn,
    session_id: str,
    team_id: str,
    target_ids: list[str],
) -> str:
    if not target_ids:
        return ""
    placeholders = ",".join("?" for _ in target_ids)
    finding_owner_sql = "AND f.team_id = ? " if team_id else "AND f.session_id = ? AND f.team_id = '' "
    finding_owner_params = (team_id,) if team_id else (session_id,)
    triage_owner_sql, triage_owner_params = _metadata_owner_where(session_id, team_id, table_alias="ftd")
    rows = conn.execute(
        "SELECT f.last_seen_at, f.created, ftd.updated AS triage_updated "
        "FROM findings f "
        "LEFT JOIN finding_triage_details ftd ON ftd.finding_id = f.id AND " + triage_owner_sql + " "  # nosec
        "WHERE (COALESCE(f.entity_id, f.target_id) IN (" + placeholders + ") "  # nosec
        "OR f.target_id IN (" + placeholders + ")) "  # nosec
        + finding_owner_sql,
        (*triage_owner_params, *target_ids, *target_ids, *finding_owner_params),
    ).fetchall()
    latest = ""
    for row in rows:
        latest = max(
            latest,
            str(row["last_seen_at"] or ""),
            str(row["created"] or ""),
            str(row["triage_updated"] or ""),
        )
    return latest


def _overview_report_freshness(report_saved_at: str, report_exported_at: str, finding_activity_at: str) -> str:
    latest_report_at = max(str(report_saved_at or ""), str(report_exported_at or ""))
    latest_finding_at = str(finding_activity_at or "")
    if not latest_report_at:
        return "not_started"
    if not latest_finding_at:
        return "no_finding_activity"
    return "fresh" if latest_report_at >= latest_finding_at else "stale"


def _overview_deliverables_status(
    conn,
    session_id: str,
    team_id: str,
    project_id: str,
    target_ids: list[str],
) -> dict[str, Any]:
    latest_package = _overview_latest_package(conn, session_id, team_id, project_id)
    latest_report = _overview_latest_report(conn, session_id, team_id, project_id)
    package_build = _overview_latest_completed_audit_event(
        conn,
        session_id,
        team_id,
        project_id,
        "package.build",
    )
    report_export = _overview_latest_completed_audit_event(
        conn,
        session_id,
        team_id,
        project_id,
        "report.build",
    )
    finding_activity_at = _overview_latest_finding_activity_at(conn, session_id, team_id, target_ids)
    report_saved_at = str(latest_report.get("updated") or "")
    report_exported_at = str(report_export.get("created") or "")
    return {
        "last_package_at": str(latest_package.get("updated") or ""),
        "last_package_id": str(latest_package.get("id") or ""),
        "last_package_name": str(latest_package.get("name") or ""),
        "last_package_build_at": str(package_build.get("created") or ""),
        "last_package_build_job_id": str(package_build.get("job_id") or package_build.get("target_id") or ""),
        "last_report_saved_at": report_saved_at,
        "last_report_id": str(latest_report.get("id") or ""),
        "last_report_exported_at": report_exported_at,
        "last_report_export_job_id": str(report_export.get("job_id") or report_export.get("target_id") or ""),
        "latest_finding_activity_at": finding_activity_at,
        "report_freshness": _overview_report_freshness(report_saved_at, report_exported_at, finding_activity_at),
    }




def _overview_target_rows(
    targets: list[dict[str, Any]],
    snapshots_by_entity: dict[str, list[dict[str, Any]]],
    findings_by_entity: dict[str, list[dict[str, Any]]],
    observations_by_entity: dict[str, dict[str, Any]],
    app_ports_by_host: dict[str, list[dict[str, Any]]],
    url_host_entity_ids: dict[str, str],
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
        app_host_entity_id = url_host_entity_ids.get(entity_id, "") if entity_type == "url" else entity_id
        raw_app_ports = app_ports_by_host.get(app_host_entity_id, []) if app_host_entity_id else []
        app_port_total_count = 0
        if raw_app_ports:
            first_app_port = raw_app_ports[0]
            if isinstance(first_app_port, Mapping):
                app_port_total_count = int(first_app_port.get("_host_total_count") or len(raw_app_ports))
        project_entity_port_count = sum(
            1 for port in raw_app_ports if isinstance(port, Mapping) and bool(port.get("_project_linked"))
        )
        app_port_run_count = _overview_app_port_run_count(raw_app_ports)
        app_ports = [_overview_public_app_port_record(port) for port in raw_app_ports if isinstance(port, Mapping)]
        app_evidence = _overview_app_evidence(
            observations_by_entity.get(app_host_entity_id),
            app_port_count=app_port_total_count,
            app_port_run_count=app_port_run_count,
            project_entity_port_count=project_entity_port_count,
            host_entity_id=app_host_entity_id if entity_type == "url" else "",
            scope_note=(
                "App ports are tracked on the URL host entity, not the URL itself."
                if entity_type == "url" and app_host_entity_id else
                "App ports are tracked on host entities; resolve this URL's host to show app port evidence."
                if entity_type == "url" else ""
            ),
        )
        app_services = _overview_app_services(app_ports)
        port_provenance = _overview_port_provenance(
            app_ports,
            intel_extract["open_ports"],
            app_evidence,
            has_provider_intel=has_intel,
        )
        top_severity = highest_actionable_finding_severity(findings)
        hints = target_deep_link_hints(
            entity_id,
            run_id=str(target.get("source_run_id") or ""),
            severity=top_severity,
        )
        if project_entity_port_count > 0 and app_host_entity_id:
            hints["ports"] = {
                "entity_type": "port",
                "host_entity_id": app_host_entity_id,
            }
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
                "has_app_scan_evidence": int(app_evidence.get("scan_run_count") or 0) > 0,
                "has_app_ports": bool(app_ports),
                "has_recent_changes": entity_id in recent_targets,
            },
            "app_evidence": app_evidence,
            "app_ports": app_ports,
            "app_port_count": app_port_total_count,
            "app_services": app_services,
            "port_provenance": port_provenance,
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
    app_port_totals_by_host: dict[str, int] = {}
    app_scan_target_count = 0
    app_port_target_count = 0
    port_divergence_target_count = 0
    scanned_no_ports_seen_count = 0
    awaiting_verification_target_count = 0
    needs_followup_target_count = 0
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
        raw_app_evidence = target.get("app_evidence")
        app_evidence = raw_app_evidence if isinstance(raw_app_evidence, Mapping) else {}
        if int(app_evidence.get("scan_run_count") or 0) > 0:
            app_scan_target_count += 1
        raw_app_ports = target.get("app_ports")
        app_ports = raw_app_ports if isinstance(raw_app_ports, list) else []
        host_id = str(app_evidence.get("host_entity_id") or target.get("entity_id") or target.get("id") or "")
        app_port_total = max(0, int(target.get("app_port_count") or len(app_ports)))
        if app_port_total > 0:
            app_port_totals_by_host[host_id] = max(app_port_totals_by_host.get(host_id, 0), app_port_total)
        if app_port_total > 0:
            app_port_target_count += 1
        raw_provenance = target.get("port_provenance")
        provenance = raw_provenance if isinstance(raw_provenance, Mapping) else {}
        raw_divergence = provenance.get("divergence")
        divergence = raw_divergence if isinstance(raw_divergence, Mapping) else {}
        if bool(divergence.get("has_drift")):
            port_divergence_target_count += 1
        if str(app_evidence.get("coverage_state") or "") == "scanned_no_ports_seen":
            scanned_no_ports_seen_count += 1
        raw_counts = target.get("finding_counts")
        counts = raw_counts if isinstance(raw_counts, Mapping) else {}
        raw_review = counts.get("by_review_state")
        review = raw_review if isinstance(raw_review, Mapping) else {}
        raw_verification = counts.get("by_verification_state")
        verification = raw_verification if isinstance(raw_verification, Mapping) else {}
        if (
            int(verification.get("not_started") or 0)
            + int(verification.get("ready_to_verify") or 0)
            + int(verification.get("needs_retest") or 0)
        ) > 0:
            awaiting_verification_target_count += 1
        if (int(review.get("new") or 0) + int(review.get("needs_followup") or 0)) > 0:
            needs_followup_target_count += 1
    return {
        "target_count": len(targets),
        "certificate_statuses": certificate_statuses,
        "finding_severities": finding_severities,
        "open_port_count": len(ports),
        "service_count": len(services),
        "provider_count": len(provider_ids),
        "app_port_count": sum(app_port_totals_by_host.values()),
        "port_divergence_target_count": port_divergence_target_count,
        "app_scan_target_count": app_scan_target_count,
        "app_port_target_count": app_port_target_count,
        "scanned_no_ports_seen_count": scanned_no_ports_seen_count,
        "unscanned_target_count": max(0, len(targets) - app_scan_target_count),
        "awaiting_verification_target_count": awaiting_verification_target_count,
        "needs_followup_target_count": needs_followup_target_count,
        "recent_change_state": recent_change_state,
    }


def _overview_gap_item(target: Mapping[str, Any], reason: str, detail: str, hints_key: str = "entities") -> dict[str, Any]:
    raw_hints = target.get("deep_link_hints")
    hints = raw_hints if isinstance(raw_hints, Mapping) else {}
    raw_tab_hints = hints.get(hints_key)
    tab_hints = raw_tab_hints if isinstance(raw_tab_hints, Mapping) else {}
    return {
        "entity_id": str(target.get("entity_id") or target.get("id") or ""),
        "display_label": str(target.get("display_label") or target.get("value") or target.get("entity_id") or ""),
        "reason": reason,
        "detail": detail,
        "deep_link": {
            "tab": "findings" if hints_key == "findings" else "entities",
            "hints": {str(key): str(value) for key, value in tab_hints.items() if str(value or "")},
        },
    }


def _overview_coverage_gaps(targets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    gaps = {
        "untouched_targets": [],
        "awaiting_verification": [],
        "needs_followup": [],
    }
    for target in targets:
        raw_app_evidence = target.get("app_evidence")
        app_evidence = raw_app_evidence if isinstance(raw_app_evidence, Mapping) else {}
        if int(app_evidence.get("scan_run_count") or 0) <= 0:
            gaps["untouched_targets"].append(_overview_gap_item(
                target,
                "no_app_scan",
                "No app-captured scan has touched this target.",
                "entities",
            ))
        raw_counts = target.get("finding_counts")
        counts = raw_counts if isinstance(raw_counts, Mapping) else {}
        raw_review = counts.get("by_review_state")
        review = raw_review if isinstance(raw_review, Mapping) else {}
        raw_verification = counts.get("by_verification_state")
        verification = raw_verification if isinstance(raw_verification, Mapping) else {}
        waiting = (
            int(verification.get("not_started") or 0)
            + int(verification.get("ready_to_verify") or 0)
            + int(verification.get("needs_retest") or 0)
        )
        if waiting > 0:
            noun = "finding" if waiting == 1 else "findings"
            gaps["awaiting_verification"].append(_overview_gap_item(
                target,
                "awaiting_verification",
                f"{waiting} {noun} awaiting verification.",
                "findings",
            ))
        followup = int(review.get("new") or 0) + int(review.get("needs_followup") or 0)
        if followup > 0:
            noun = "finding needs" if followup == 1 else "findings need"
            gaps["needs_followup"].append(_overview_gap_item(
                target,
                "needs_followup",
                f"{followup} {noun} review or follow-up.",
                "findings",
            ))
    return {key: items[:_OVERVIEW_GAP_LIMIT] for key, items in gaps.items()}


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
