# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resumable owner-scoped risk escalation derived from changed public feeds."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import uuid

from config import resolve_effective_cfg
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.metrics.cve_risk import CVE_RISK_WORK_ITEMS, RISK_ESCALATIONS_CREATED
from .links import group_observations, observations_for_cve


log = logging.getLogger("shell")
ACK_STATES = frozenset({"new", "acknowledged", "expected", "needs_action", "resolved"})
NVD_TRANSITIONS = frozenset({
    "nvd_cvss_downgraded",
    "nvd_disputed",
    "nvd_reinstated",
    "nvd_rejected",
    "nvd_withdrawn",
})
MAX_ACK_NOTE_CHARS = 1000
_FINDING_OCCURRENCE_RUNS_SQL = (
    "SELECT DISTINCT run_id FROM findings_occurrences "
    "WHERE finding_id IN ({placeholders})"
)
_PROJECT_LINKS_SQL = (
    "SELECT DISTINCT project_id FROM project_links WHERE entity_type = ? "
    "AND entity_id IN ({placeholders})"
)
_PROJECT_RISK_ESCALATIONS_SQL = (
    "SELECT r.* FROM risk_escalation_projects rp "
    "JOIN risk_escalations r ON r.id = rp.escalation_id "
    "WHERE {where_sql} ORDER BY r.created_at DESC, r.id DESC LIMIT ?"
)
_ACKNOWLEDGE_ESCALATION_SQL = (
    "SELECT r.* FROM risk_escalations r "
    "JOIN risk_escalation_projects rp ON rp.escalation_id = r.id "
    "WHERE r.id = ? AND rp.project_id = ? AND {owner_clause}"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = resolve_effective_cfg(cfg).get("cve_risk")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _projects_for_observations(conn: Any, observations: list[dict[str, Any]]) -> set[str]:
    finding_ids = {str(item.get("id") or "") for item in observations if str(item.get("id") or "")}
    entity_ids = {
        str(item.get("entity_id") or item.get("target_id") or "")
        for item in observations
        if str(item.get("entity_id") or item.get("target_id") or "")
    }
    run_ids = {
        str(item.get("run_id") or item.get("last_run_id") or item.get("first_run_id") or "")
        for item in observations
        if str(item.get("run_id") or item.get("last_run_id") or item.get("first_run_id") or "")
    }
    ordered_findings = sorted(finding_ids)
    for offset in range(0, len(ordered_findings), 500):
        chunk = ordered_findings[offset:offset + 500]
        if not chunk:
            continue
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            _FINDING_OCCURRENCE_RUNS_SQL.format(placeholders=placeholders),
            tuple(chunk),
        ).fetchall()
        run_ids.update(str(row["run_id"] or "") for row in rows if str(row["run_id"] or ""))
    project_ids: set[str] = set()
    for entity_type, values in (
        ("finding", finding_ids),
        ("atlas_entity", entity_ids),
        ("run", run_ids),
    ):
        ordered = sorted(values)
        for offset in range(0, len(ordered), 500):
            chunk = ordered[offset:offset + 500]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                _PROJECT_LINKS_SQL.format(placeholders=placeholders),
                (entity_type, *chunk),
            ).fetchall()
            project_ids.update(str(row["project_id"]) for row in rows)
    return project_ids


def _state_row(
    conn: Any,
    owner_session_id: str,
    owner_team_id: str,
    remediation_id: str,
    cve_id: str,
) -> Any:
    return conn.execute(
        "SELECT * FROM risk_escalation_states WHERE owner_session_id = ? AND owner_team_id = ? "
        "AND remediation_id = ? AND cve_id = ?",
        (owner_session_id, owner_team_id, remediation_id, cve_id),
    ).fetchone()


def _upsert_state(
    conn: Any,
    *,
    owner_session_id: str,
    owner_team_id: str,
    remediation_id: str,
    cve_id: str,
    kev_listed: bool,
    epss_active: bool,
    epss_probability: float | None,
    epss_model_version: str,
    feed_version: str,
    now: str,
) -> None:
    conn.execute(
        "INSERT INTO risk_escalation_states ("
        "owner_session_id, owner_team_id, remediation_id, cve_id, kev_listed, epss_active, "
        "epss_probability, epss_model_version, last_feed_version, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT("
        "owner_session_id, owner_team_id, remediation_id, cve_id) DO UPDATE SET "
        "kev_listed = excluded.kev_listed, epss_active = excluded.epss_active, "
        "epss_probability = excluded.epss_probability, "
        "epss_model_version = excluded.epss_model_version, "
        "last_feed_version = excluded.last_feed_version, updated_at = excluded.updated_at",
        (
            owner_session_id,
            owner_team_id,
            remediation_id,
            cve_id,
            kev_listed,
            epss_active,
            epss_probability,
            epss_model_version,
            feed_version,
            now,
        ),
    )


def _create_escalation(
    conn: Any,
    *,
    work: Mapping[str, Any],
    owner_session_id: str,
    owner_team_id: str,
    remediation_id: str,
    observations: list[dict[str, Any]],
    transition_kind: str,
    published_at: str,
    model_changed: bool,
    now: str,
) -> str:
    escalation_id = "rsk_" + uuid.uuid4().hex
    conn.execute(
        "INSERT INTO risk_escalations ("
        "id, owner_session_id, owner_team_id, remediation_id, cve_id, source, transition_kind, "
        "feed_version, old_value, new_value, old_source_version, new_source_version, "
        "source_published_at, model_version, model_changed, observation_count, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(owner_session_id, owner_team_id, remediation_id, source, feed_version, transition_kind) "
        "DO NOTHING",
        (
            escalation_id,
            owner_session_id,
            owner_team_id,
            remediation_id,
            str(work["cve_id"]),
            str(work["source"]),
            transition_kind,
            str(work["feed_version"]),
            str(work["old_value"] or ""),
            str(work["new_value"] or ""),
            str(work.get("old_source_version") or ""),
            str(work.get("new_source_version") or work["feed_version"] or ""),
            published_at,
            str(work["new_model_version"] or ""),
            model_changed,
            len(observations),
            now,
            now,
        ),
    )
    row = conn.execute(
        "SELECT id FROM risk_escalations WHERE owner_session_id = ? AND owner_team_id = ? "
        "AND remediation_id = ? AND source = ? AND feed_version = ? AND transition_kind = ?",
        (
            owner_session_id,
            owner_team_id,
            remediation_id,
            str(work["source"]),
            str(work["feed_version"]),
            transition_kind,
        ),
    ).fetchone()
    canonical_id = str(row["id"])
    for observation in observations[:500]:
        finding_id = str(observation.get("id") or "")
        if finding_id:
            conn.execute(
                "INSERT INTO risk_escalation_observations (escalation_id, finding_id) "
                "VALUES (?, ?) ON CONFLICT(escalation_id, finding_id) DO NOTHING",
                (canonical_id, finding_id),
            )
    project_ids = _projects_for_observations(conn, observations)
    for project_id in project_ids:
        conn.execute(
            "INSERT INTO risk_escalation_projects (escalation_id, project_id) VALUES (?, ?) "
            "ON CONFLICT(escalation_id, project_id) DO NOTHING",
            (canonical_id, project_id),
        )
    if canonical_id == escalation_id:
        RISK_ESCALATIONS_CREATED.labels(
            source=str(work["source"]), transition=transition_kind
        ).inc()
        log.info("RISK_ESCALATION_CREATED", extra={
            "source": str(work["source"]),
            "transition_kind": transition_kind,
            "feed_version": str(work["feed_version"]),
            "owner_kind": "team" if owner_team_id else "personal",
            "observation_count": min(len(observations), 500),
            "project_count": len(project_ids),
            "model_changed": model_changed,
        })
    return canonical_id


def _process_group(
    conn: Any,
    work: Mapping[str, Any],
    key: tuple[str, str, str],
    observations: list[dict[str, Any]],
    *,
    activation: float,
    reset: float,
    published_at: str,
    now: str,
) -> int:
    owner_session_id, owner_team_id, remediation_id = key
    state = _state_row(
        conn, owner_session_id, owner_team_id, remediation_id, str(work["cve_id"])
    )
    source = str(work["source"])
    if source == "nvd":
        transition = str(work["transition_kind"] or "")
        if transition not in NVD_TRANSITIONS:
            raise ValueError("unsupported NVD risk transition")
        _create_escalation(
            conn,
            work=work,
            owner_session_id=owner_session_id,
            owner_team_id=owner_team_id,
            remediation_id=remediation_id,
            observations=observations,
            transition_kind=transition,
            published_at=published_at,
            model_changed=False,
            now=now,
        )
        return 1
    old_probability = _float(work["old_value"])
    new_probability = _float(work["new_value"])
    old_model = str(work["old_model_version"] or "")
    new_model = str(work["new_model_version"] or "")
    kev_listed = bool(state["kev_listed"]) if state else (
        _bool(work["old_value"]) if source == "kev" else False
    )
    epss_active = bool(state["epss_active"]) if state else (
        old_probability is not None and old_probability >= activation
    )
    current_probability = _float(state["epss_probability"]) if state else old_probability
    current_model = str(state["epss_model_version"] or "") if state else old_model
    transition = ""
    if source == "kev":
        new_listed = _bool(work["new_value"])
        if new_listed != kev_listed:
            transition = "kev_added" if new_listed else "kev_removed"
        kev_listed = new_listed
    elif source == "epss":
        if not epss_active and new_probability is not None and new_probability >= activation:
            transition = "epss_activated"
            epss_active = True
        elif epss_active and (new_probability is None or new_probability < reset):
            transition = "epss_reset"
            epss_active = False
        current_probability = new_probability
        current_model = new_model
    else:
        raise ValueError("unsupported CVE risk work source")
    _upsert_state(
        conn,
        owner_session_id=owner_session_id,
        owner_team_id=owner_team_id,
        remediation_id=remediation_id,
        cve_id=str(work["cve_id"]),
        kev_listed=kev_listed,
        epss_active=epss_active,
        epss_probability=current_probability,
        epss_model_version=current_model,
        feed_version=str(work["feed_version"]),
        now=now,
    )
    if not transition:
        return 0
    _create_escalation(
        conn,
        work=work,
        owner_session_id=owner_session_id,
        owner_team_id=owner_team_id,
        remediation_id=remediation_id,
        observations=observations,
        transition_kind=transition,
        published_at=published_at,
        model_changed=bool(old_model and new_model and old_model != new_model),
        now=now,
    )
    return 1


def _owner_cursor(key: tuple[str, str, str]) -> str:
    return "\x1f".join(key)


def _work_remaining(conn: Any, *, max_attempts: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM cve_risk_work_items "
        "WHERE status IN ('pending', 'failed') AND attempts < ?",
        (max_attempts,),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _source_published_at(conn: Any, source: str) -> str:
    if source == "nvd":
        row = conn.execute(
            "SELECT published_at FROM cve_advisory_sources WHERE source = 'nvd'"
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT published_at FROM cve_risk_sources WHERE source = ?",
            (source,),
        ).fetchone()
    return str(row["published_at"] or "") if row else ""


def process_risk_work(
    conn: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    settings = _settings(cfg)
    batch = max(1, min(int(limit or settings.get("work_batch_size") or 100), 1000))
    owner_batch = max(1, min(int(settings.get("owner_batch_size") or 100), 1000))
    max_attempts = max(1, min(int(settings.get("work_max_attempts") or 5), 20))
    activation = float(settings.get("epss_activation_probability") or 0.10)
    reset = float(settings.get("epss_reset_probability") or 0.08)
    due_at = _now()
    rows = conn.execute(
        "SELECT * FROM cve_risk_work_items WHERE status IN ('pending', 'failed') "
        "AND attempts < ? AND (next_attempt_at = '' OR next_attempt_at <= ?) "
        "ORDER BY created_at, id LIMIT ?",
        (max_attempts, due_at, batch),
    ).fetchall()
    completed = 0
    escalations = 0
    for row in rows:
        work = dict(row)
        work_id = str(work["id"])
        now = _now()
        conn.execute("SAVEPOINT cve_risk_work_item")
        try:
            conn.execute(
                "UPDATE cve_risk_work_items SET status = 'processing', last_error = '', "
                "updated_at = ? WHERE id = ?",
                (now, work_id),
            )
            observations = observations_for_cve(conn, str(work["cve_id"]))
            groups = group_observations(observations, str(work["cve_id"]))
            cursor = str(work.get("cursor_owner_key") or "")
            remaining_groups = [
                key for key in sorted(groups) if not cursor or _owner_cursor(key) > cursor
            ]
            selected_groups = remaining_groups[:owner_batch]
            published_at = _source_published_at(conn, str(work["source"]))
            for key in selected_groups:
                escalations += _process_group(
                    conn,
                    work,
                    key,
                    groups[key],
                    activation=activation,
                    reset=reset,
                    published_at=published_at,
                    now=now,
                )
            if len(remaining_groups) > len(selected_groups):
                next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
                conn.execute(
                    "UPDATE cve_risk_work_items SET status = 'pending', cursor_owner_key = ?, "
                    "next_attempt_at = ?, updated_at = ? WHERE id = ?",
                    (_owner_cursor(selected_groups[-1]), next_attempt, _now(), work_id),
                )
                outcome = "partial"
            else:
                conn.execute(
                    "UPDATE cve_risk_work_items SET status = 'complete', cursor_owner_key = '', "
                    "next_attempt_at = '', updated_at = ? WHERE id = ?",
                    (_now(), work_id),
                )
                completed += 1
                outcome = "complete"
            conn.execute("RELEASE SAVEPOINT cve_risk_work_item")
            CVE_RISK_WORK_ITEMS.labels(source=str(work["source"]), outcome=outcome).inc()
        except Exception as exc:
            conn.execute("ROLLBACK TO SAVEPOINT cve_risk_work_item")
            conn.execute("RELEASE SAVEPOINT cve_risk_work_item")
            attempts = int(work.get("attempts") or 0) + 1
            delay = min(3600, 2 ** min(attempts, 10))
            next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            conn.execute(
                "UPDATE cve_risk_work_items SET status = 'failed', attempts = ?, next_attempt_at = ?, "
                "last_error = ?, updated_at = ? WHERE id = ?",
                (attempts, next_attempt, type(exc).__name__, _now(), work_id),
            )
            CVE_RISK_WORK_ITEMS.labels(source=str(work["source"]), outcome="failed").inc()
            log.error("CVE_RISK_WORK_ITEM_FAILED", exc_info=True, extra={
                "source": str(work["source"]),
                "attempt": attempts,
                "max_attempts": max_attempts,
                "error_type": type(exc).__name__,
            })
    return {
        "processed": completed,
        "escalations": escalations,
        "remaining": _work_remaining(conn, max_attempts=max_attempts),
    }


def list_project_risk_escalations(
    conn: Any,
    project_id: str,
    *,
    start: str = "",
    end: str = "",
    limit: int = 25,
) -> list[dict[str, Any]]:
    clauses = ["rp.project_id = ?"]
    params: list[Any] = [project_id]
    if start:
        clauses.append("r.created_at >= ?")
        params.append(start)
    if end:
        clauses.append("r.created_at <= ?")
        params.append(end)
    params.append(max(1, min(int(limit), 100)))
    where_sql = " AND ".join(clauses)
    rows = conn.execute(
        _PROJECT_RISK_ESCALATIONS_SQL.format(where_sql=where_sql),
        tuple(params),
    ).fetchall()
    return [{
        "id": str(row["id"]),
        "kind": "risk_escalation",
        "cve_id": str(row["cve_id"]),
        "source": str(row["source"]),
        "transition_kind": str(row["transition_kind"]),
        "feed_version": str(row["feed_version"]),
        "old_value": str(row["old_value"] or ""),
        "new_value": str(row["new_value"] or ""),
        "old_source_version": str(row["old_source_version"] or ""),
        "new_source_version": str(row["new_source_version"] or ""),
        "source_published_at": str(row["source_published_at"] or ""),
        "model_version": str(row["model_version"] or ""),
        "model_changed": bool(row["model_changed"]),
        "observation_count": int(row["observation_count"] or 0),
        "ack_state": str(row["ack_state"]),
        "ack_note": str(row["ack_note"] or ""),
        "ack_by": str(row["ack_by"] or ""),
        "ack_at": str(row["ack_at"] or ""),
        "created": str(row["created_at"]),
    } for row in rows]


def acknowledge_escalation(
    conn: Any,
    escalation_id: str,
    *,
    session_id: str,
    team_id: str = "",
    ack_state: str,
    ack_note: str = "",
    actor_session_id: str = "",
    actor_member_id: str = "",
    project_id: str = "",
) -> dict[str, Any] | None:
    normalized_state = str(ack_state or "").strip().lower()
    if normalized_state not in ACK_STATES:
        raise ValueError("unsupported risk escalation acknowledgement state")
    if team_id:
        team = conn.execute("SELECT status FROM teams WHERE id = ?", (team_id,)).fetchone()
        if team is not None and str(team["status"] or "") == "archived":
            raise ValueError("archived teams cannot change risk escalation acknowledgement")
        owner_clause = "r.owner_team_id = ?"
        owner_params: tuple[Any, ...] = (team_id,)
    else:
        owner_clause = "r.owner_team_id = '' AND r.owner_session_id = ?"
        owner_params = (session_id,)
    row = conn.execute(
        _ACKNOWLEDGE_ESCALATION_SQL.format(owner_clause=owner_clause),
        (escalation_id, project_id, *owner_params),
    ).fetchone()
    if row is None:
        return None
    previous = str(row["ack_state"] or "new")
    note = str(ack_note or "").strip()[:MAX_ACK_NOTE_CHARS]
    now = _now()
    conn.execute(
        "UPDATE risk_escalations SET ack_state = ?, ack_note = ?, ack_by = ?, ack_at = ?, updated_at = ? "
        "WHERE id = ?",
        (normalized_state, note, actor_session_id or session_id, now, now, escalation_id),
    )
    record_event(
        AuditEventType.RISK_ESCALATION_ACK,
        target_id=escalation_id,
        session_id=session_id,
        team_id=team_id,
        actor_session_id=actor_session_id or session_id,
        actor_member_id=actor_member_id,
        project_id=project_id,
        details={
            "from_state": previous,
            "to_state": normalized_state,
            "note_chars": len(note),
            "source": str(row["source"]),
            "transition_kind": str(row["transition_kind"]),
            "observation_count": min(int(row["observation_count"] or 0), 500),
        },
        conn=conn,
    )
    return {
        "id": escalation_id,
        "ack_state": normalized_state,
        "ack_note": note,
        "ack_by": actor_session_id or session_id,
        "ack_at": now,
    }
