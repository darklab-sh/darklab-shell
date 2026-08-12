# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded saved-evidence signals for Nuclei recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.dns_takeover_event_review import build_dnsx_takeover_event_review
from services.assessments.evidence_matching import canonical_evidence_identity, target_matches
from services.projects.scope import shared_owner_where


NUCLEI_RECOMMENDATION_MAX_RUNS = 64
NUCLEI_RECOMMENDATION_MAX_FINDINGS = 200
NUCLEI_RECOMMENDATION_MAX_SERVICES = 200
NUCLEI_RECOMMENDATION_MAX_EVENTS = 1_000
NUCLEI_RECOMMENDATION_MAX_BYTES = 2 * 1024 * 1024
NUCLEI_RECOMMENDATION_MAX_LABELS = 32


@dataclass
class NucleiTargetSignals:
    technologies: set[str] = field(default_factory=set)
    services: set[str] = field(default_factory=set)
    inferred_cve_count: int = 0
    dangling_record_count: int = 0
    truncated: bool = False


def load_nuclei_recommendation_signals(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    targets: Sequence[Mapping[str, str]],
) -> dict[str, NucleiTargetSignals]:
    """Load target-compatible signals without providers, writes, or launches."""
    normalized = [
        {
            "entity_id": str(item.get("entity_id") or ""),
            "type": str(item.get("type") or ""),
            "value": str(item.get("value") or ""),
        }
        for item in targets
        if str(item.get("entity_id") or "")
    ]
    signals = {item["entity_id"]: NucleiTargetSignals() for item in normalized}
    if not signals:
        return signals
    _load_services(conn, session_id, team_id, project_id, normalized, signals)
    _load_inferred_cves(conn, session_id, team_id, project_id, normalized, signals)
    _load_run_signals(conn, session_id, team_id, project_id, normalized, signals)
    return signals


def _matches(target: Mapping[str, str], entity_type: object, value: object) -> bool:
    identity = canonical_evidence_identity(value, entity_type)
    return bool(identity and target_matches(
        (identity,), target["type"], target["value"], "host_or_descendant",
    ))


def _matched_targets(
    targets: Sequence[Mapping[str, str]], entity_type: object, value: object,
) -> list[str]:
    return [target["entity_id"] for target in targets if _matches(target, entity_type, value)]


def _bounded_label(values: set[str], value: object, signal: NucleiTargetSignals) -> None:
    label = " ".join(str(value or "").split())[:128]
    if not label or label in values:
        return
    if len(values) >= NUCLEI_RECOMMENDATION_MAX_LABELS:
        signal.truncated = True
        return
    values.add(label)


def _load_services(conn, session_id, team_id, project_id, targets, signals) -> None:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e",
    )
    query = "".join((
        "SELECT e.id, e.type, e.canonical_value, e.host_entity_id, e.attributes_json, ",
        "h.type AS host_type, h.canonical_value AS host_value FROM entities e ",
        "LEFT JOIN entities h ON h.id = e.host_entity_id WHERE ",
        owner_sql,
        " AND e.type = 'port' AND COALESCE(e.suppressed, FALSE) = FALSE ",
        "AND EXISTS (SELECT 1 FROM entity_run_links erl JOIN project_links pl ",
        "ON pl.entity_type = 'run' AND pl.entity_id = erl.run_id ",
        "WHERE erl.entity_id = e.id AND pl.project_id = ?) ",
        "ORDER BY e.last_seen_at DESC, e.id DESC LIMIT ?",
    ))
    rows = conn.execute(
        query,
        (*owner_params, project_id, NUCLEI_RECOMMENDATION_MAX_SERVICES + 1),
    ).fetchall()
    truncated = len(rows) > NUCLEI_RECOMMENDATION_MAX_SERVICES
    dialect = dialect_for_backend(get_db_backend())
    for row in rows[:NUCLEI_RECOMMENDATION_MAX_SERVICES]:
        attributes = dialect.decode_json_dict(row["attributes_json"])
        service = str(attributes.get("service") or "").strip()
        if not service:
            continue
        matched = set(_matched_targets(targets, row["type"], row["canonical_value"]))
        matched.update(_matched_targets(targets, row["host_type"], row["host_value"]))
        for target_id in matched:
            _bounded_label(signals[target_id].services, service, signals[target_id])
    if truncated:
        for signal in signals.values():
            signal.truncated = True


def _load_inferred_cves(conn, session_id, team_id, project_id, targets, signals) -> None:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="f",
    )
    query = "".join((
        "SELECT f.id, e.type AS entity_type, e.canonical_value FROM findings f ",
        "JOIN entities e ON e.id = COALESCE(f.entity_id, f.target_id) WHERE ",
        owner_sql,
        " AND f.validation_method = 'version_inference' AND (",
        "EXISTS (SELECT 1 FROM project_links pe WHERE pe.project_id = ? ",
        "AND pe.entity_type = 'atlas_entity' AND pe.entity_id = e.id) OR ",
        "EXISTS (SELECT 1 FROM finding_version_inference_sources fs ",
        "JOIN project_links pr ON pr.entity_type = 'run' AND pr.entity_id = fs.source_id ",
        "WHERE fs.finding_id = f.id AND fs.source_kind = 'run' AND pr.project_id = ?)) ",
        "ORDER BY f.last_seen_at DESC, f.id DESC LIMIT ?",
    ))
    rows = conn.execute(
        query,
        (*owner_params, project_id, project_id, NUCLEI_RECOMMENDATION_MAX_FINDINGS + 1),
    ).fetchall()
    for row in rows[:NUCLEI_RECOMMENDATION_MAX_FINDINGS]:
        for target_id in _matched_targets(targets, row["entity_type"], row["canonical_value"]):
            signals[target_id].inferred_cve_count += 1
    if len(rows) > NUCLEI_RECOMMENDATION_MAX_FINDINGS:
        for signal in signals.values():
            signal.truncated = True


def _load_run_signals(conn, session_id, team_id, project_id, targets, signals) -> None:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    query = "".join((
        "SELECT r.id, r.output_preview FROM project_links pl JOIN runs r ON r.id = pl.entity_id ",
        "WHERE pl.project_id = ? AND pl.entity_type = 'run' AND ",
        owner_sql,
        " AND (r.command = 'httpx' OR r.command LIKE 'httpx %' ",
        "OR r.command = 'dnsx' OR r.command LIKE 'dnsx %') ",
        "ORDER BY COALESCE(r.finished, r.started) DESC, r.id DESC LIMIT ?",
    ))
    rows = conn.execute(
        query,
        (project_id, *owner_params, NUCLEI_RECOMMENDATION_MAX_RUNS + 1),
    ).fetchall()
    dialect = dialect_for_backend(get_db_backend())
    events: list[dict[str, Any]] = []
    allowed_run_ids: set[str] = set()
    used_bytes = 0
    truncated = len(rows) > NUCLEI_RECOMMENDATION_MAX_RUNS
    for row in rows[:NUCLEI_RECOMMENDATION_MAX_RUNS]:
        payload = row["output_preview"]
        used_bytes += len(str(payload or "").encode("utf-8"))
        if used_bytes > NUCLEI_RECOMMENDATION_MAX_BYTES:
            truncated = True
            break
        decoded = dialect.decode_json_list(payload)
        if len(events) + len(decoded) > NUCLEI_RECOMMENDATION_MAX_EVENTS:
            decoded = decoded[:max(0, NUCLEI_RECOMMENDATION_MAX_EVENTS - len(events))]
            truncated = True
        events.extend(item for item in decoded if isinstance(item, dict))
        allowed_run_ids.add(str(row["id"] or ""))
        if len(events) >= NUCLEI_RECOMMENDATION_MAX_EVENTS:
            break
    _collect_technologies(events, targets, signals)
    _collect_dangling_records(events, allowed_run_ids, targets, signals)
    if truncated:
        for signal in signals.values():
            signal.truncated = True


def _collect_technologies(events, targets, signals) -> None:
    for event in events:
        detail = event.get("source_detail")
        if not isinstance(detail, Mapping):
            continue
        candidates = []
        for capture in detail.get("screenshots", []) if isinstance(detail.get("screenshots"), list) else []:
            if isinstance(capture, Mapping):
                candidates.append((capture.get("url"), capture.get("technologies")))
        for observation in detail.get("version_observations", []) if isinstance(detail.get("version_observations"), list) else []:
            if isinstance(observation, Mapping):
                candidates.append((observation.get("target"), [observation.get("technology")]))
        for value, technologies in candidates:
            matched = _matched_targets(targets, "url", value)
            for technology in technologies if isinstance(technologies, list) else []:
                for target_id in matched:
                    _bounded_label(
                        signals[target_id].technologies, technology, signals[target_id],
                    )


def _collect_dangling_records(events, allowed_run_ids, targets, signals) -> None:
    if not allowed_run_ids:
        return
    review = build_dnsx_takeover_event_review(
        events, allowed_source_run_ids=allowed_run_ids,
    )
    if review.get("status") == "rejected":
        for signal in signals.values():
            signal.truncated = True
        return
    for item in review.get("reviews", []):
        if not isinstance(item, Mapping) or item.get("state") != "potential":
            continue
        for target_id in _matched_targets(targets, "domain", item.get("hostname")):
            signals[target_id].dangling_record_count += 1


__all__ = [
    "NucleiTargetSignals",
    "load_nuclei_recommendation_signals",
]
