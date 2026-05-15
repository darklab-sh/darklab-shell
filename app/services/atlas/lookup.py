"""Read helpers for the Session Entity Atlas."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from services.atlas.materializer import ATLAS_ENTITY_TYPES
from services.intel.registry import provider_label
from services.projects.contracts import FINDING_REVIEW_STATES


FINDING_STATUS_ORDER = {
    "new": 0,
    "needs_followup": 1,
    "important": 2,
    "reviewed": 3,
    "false_positive": 4,
}

ATLAS_ENTITY_EXPORT_FIELDS = (
    "id",
    "type",
    "canonical_value",
    "first_seen_at",
    "last_seen_at",
    "occurrence_count",
    "labels",
    "notes",
    "project_names",
    "intel_providers_with_data",
)

MAX_INTEL_SUMMARY_HIGHLIGHTS = 8
ORPHAN_FILTERS = {"all", "hide", "only"}


def _row_to_entity(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "type": row["type"],
        "canonical_value": row["canonical_value"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "occurrence_count": int(row["occurrence_count"] or 0),
        "created": row["created"],
    }


def _normalize_orphan_filter(value: str | None) -> str:
    orphan_filter = str(value or "hide").strip().lower()
    return orphan_filter if orphan_filter in ORPHAN_FILTERS else "hide"


def _orphan_params(orphan_filter: str) -> list[str]:
    normalized = _normalize_orphan_filter(orphan_filter)
    return [normalized, normalized, normalized]


def _row_to_project_link(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "source": row["source"],
        "created": row["created"],
    }


def _row_to_label(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }


def _row_to_note(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "body": row["body"],
        "created": row["created"],
        "updated": row["updated"],
    }


def _row_to_run_link(row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "command": row["command"],
        "run_kind": row["run_kind"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "occurrence_count": int(row["occurrence_count"] or 0),
    }


def _row_to_intel_snapshot(row) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        parsed = json.loads(row["data_json"] or "{}")
        if isinstance(parsed, dict):
            data = parsed
    except (TypeError, json.JSONDecodeError):
        data = {}
    return {
        "id": row["id"],
        "provider": row["provider"],
        "status": row["status"],
        "summary": row["summary"],
        "data": data,
        "fetched_at": row["fetched_at"],
        "expires_at": row["expires_at"],
    }


def _intel_provider_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    provider = str(snapshot.get("provider") or "").strip().lower()
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    providers = data.get("providers") if isinstance(data, dict) else {}
    if not isinstance(providers, dict):
        return {}
    payload = providers.get(provider)
    if isinstance(payload, dict):
        return payload
    for key, value in providers.items():
        if str(key or "").strip().lower() == provider and isinstance(value, dict):
            return value
    return {}


def _snapshot_has_intel(snapshot: dict[str, Any]) -> bool:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), dict) else {}
    summary = data.get("summary") if isinstance(data, dict) else None
    if isinstance(summary, dict):
        providers = summary.get("providers_with_data")
        if isinstance(providers, list) and providers:
            return True
        has_intel = summary.get("has_intel")
        if isinstance(has_intel, bool):
            return has_intel
    return bool(_intel_provider_payload(snapshot))


def _highlight(label: str, value: object, provider: str, tone: str = "neutral") -> dict[str, str] | None:
    rendered = _render_value(value)
    if not rendered:
        return None
    provider_id = str(provider or "").strip().lower()
    return {
        "label": label,
        "value": rendered,
        "provider": provider_id,
        "provider_label": provider_label(provider_id),
        "tone": tone,
    }


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value) if isinstance(value, float) and value.is_integer() else value)
    if isinstance(value, str):
        return value.strip()
    return ""


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _list_values(value: object, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    results = []
    for item in value:
        rendered = _render_value(item)
        if rendered and rendered not in results:
            results.append(rendered)
        if len(results) >= limit:
            break
    return results


def _join_list(value: object, *, limit: int = 6) -> str:
    values = _list_values(value, limit=limit)
    if not values:
        return ""
    extra = len(value) - len(values) if isinstance(value, list) else 0
    suffix = f" +{extra} more" if extra > 0 else ""
    return ", ".join(values) + suffix


def _analysis_stats(value: object) -> str:
    stats = value if isinstance(value, dict) else {}
    malicious = _int_or_none(stats.get("malicious")) or 0
    suspicious = _int_or_none(stats.get("suspicious")) or 0
    harmless = _int_or_none(stats.get("harmless")) or 0
    if malicious or suspicious:
        return f"{malicious} malicious · {suspicious} suspicious"
    if harmless:
        return f"{harmless} harmless"
    return ""


def _asn_summary(value: object) -> str:
    row = value if isinstance(value, dict) else {}
    asn = _render_value(row.get("asn") or row.get("number"))
    name = _render_value(row.get("name") or row.get("description"))
    if asn and not asn.upper().startswith("AS"):
        asn = f"AS{asn}"
    return " ".join(part for part in (asn, name) if part)


def _location_summary(value: object) -> str:
    row = value if isinstance(value, dict) else {}
    return ", ".join(
        part for part in (
            _render_value(row.get("city")),
            _render_value(row.get("region")),
            _render_value(row.get("country") or row.get("country_code")),
        )
        if part
    )


def _pulse_count(value: object) -> str:
    count = _int_or_none(value)
    if count is None:
        return ""
    return f"{count} pulse{'s' if count != 1 else ''}"


def _highlights_for_provider(
    entity_type: str,
    provider: str,
    payload: dict[str, Any],
) -> list[dict[str, str]]:
    items: list[dict[str, str] | None] = []
    if entity_type == "ip":
        items = _ip_highlights(provider, payload)
    elif entity_type == "domain":
        items = _domain_highlights(provider, payload)
    elif entity_type == "hash":
        items = _hash_highlights(provider, payload)
    elif entity_type == "cve":
        items = _cve_highlights(provider, payload)
    elif entity_type == "url":
        items = _url_highlights(provider, payload)
    return [item for item in items if item]


def _ip_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "shodan":
        return [
            _highlight("Open ports", _join_list(payload.get("ports"), limit=8), provider),
            _highlight("CVEs", _join_list(payload.get("cves"), limit=5), provider, "warning"),
            _highlight("Last updated", payload.get("last_update"), provider),
        ]
    if provider == "censys":
        return [
            _highlight("Open ports", _join_list(payload.get("ports"), limit=8), provider),
            _highlight("Names", _join_list(payload.get("names"), limit=4), provider),
            _highlight("ASN", _asn_summary(payload.get("autonomous_system")), provider),
            _highlight("Location", _location_summary(payload.get("location")), provider),
        ]
    if provider == "greynoise":
        noise = payload.get("noise")
        riot = payload.get("riot")
        noise_parts = []
        if isinstance(noise, bool):
            noise_parts.append(f"noise: {'yes' if noise else 'no'}")
        if isinstance(riot, bool):
            noise_parts.append(f"RIOT: {'yes' if riot else 'no'}")
        return [
            _highlight("GreyNoise", " · ".join(noise_parts), provider),
            _highlight("Classification", payload.get("classification"), provider),
            _highlight("Name", payload.get("name"), provider),
        ]
    if provider == "abuseipdb":
        score = _int_or_none(payload.get("abuse_confidence_score"))
        return [
            _highlight("Abuse score", f"{score}/100" if score is not None else "", provider),
            _highlight("Reports", payload.get("total_reports"), provider),
            _highlight("Network", payload.get("isp") or payload.get("domain"), provider),
            _highlight("Country", payload.get("country_code"), provider),
        ]
    if provider == "ipinfo":
        location = ", ".join(
            part for part in (
                _render_value(payload.get("city")),
                _render_value(payload.get("region")),
                _render_value(payload.get("country")),
            )
            if part
        )
        asn = " ".join(
            part for part in (
                _render_value(payload.get("asn")),
                _render_value(payload.get("org")),
            )
            if part
        )
        return [
            _highlight("ASN", asn, provider),
            _highlight("Hostname", payload.get("hostname") or payload.get("domain"), provider),
            _highlight("Location", location, provider),
        ]
    if provider == "teamcymru":
        asn = " ".join(
            part for part in (
                _render_value(payload.get("asn")),
                _render_value(payload.get("name")),
            )
            if part
        )
        return [
            _highlight("ASN", asn, provider),
            _highlight("Prefix", payload.get("prefix"), provider),
            _highlight("Registry", payload.get("registry"), provider),
        ]
    if provider == "routeviews":
        return [
            _highlight("Prefix", payload.get("prefix"), provider),
            _highlight("Origins", _join_list(payload.get("origins"), limit=5), provider),
            _highlight("RPKI", payload.get("rpki"), provider),
        ]
    return _shared_ioc_highlights(provider, payload)


def _domain_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "virustotal":
        return [
            _highlight("Analysis", _analysis_stats(payload.get("last_analysis_stats")), provider),
            _highlight("Reputation", payload.get("reputation"), provider),
        ]
    if provider == "crtsh":
        return [
            _highlight("Certificates", payload.get("certificate_count"), provider),
            _highlight("Names", _join_list(payload.get("names"), limit=4), provider),
            _highlight("Last seen", payload.get("last_seen"), provider),
        ]
    if provider == "urlscan":
        return [_highlight("urlscan results", payload.get("result_count"), provider)]
    if provider == "securitytrails":
        return [_highlight("Subdomains", payload.get("subdomain_count"), provider)]
    return _shared_ioc_highlights(provider, payload)


def _hash_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "virustotal":
        return [
            _highlight("Verdict", payload.get("verdict"), provider, "warning"),
            _highlight("Analysis", _analysis_stats(payload.get("last_analysis_stats")), provider),
            _highlight("Type", payload.get("type_description"), provider),
        ]
    if provider == "hibp":
        count = _int_or_none(payload.get("count")) or 0
        return [_highlight("Pwned password", f"{count} matches" if count else "not found", provider)]
    return _shared_ioc_highlights(provider, payload)


def _cve_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    return [
        _highlight("Severity", payload.get("severity"), provider, "warning"),
        _highlight("Score", payload.get("score"), provider, "warning"),
        _highlight("Exploits", payload.get("exploit_count"), provider, "warning"),
        _highlight("Published", payload.get("published"), provider),
    ]


def _url_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    if provider == "urlhaus":
        return [
            _highlight("URL status", payload.get("status") or payload.get("query_status"), provider, "warning"),
            _highlight("Threat", payload.get("threat"), provider, "warning"),
            _highlight("Host", payload.get("host"), provider),
        ]
    if provider == "urlscan":
        return [_highlight("urlscan results", payload.get("result_count"), provider)]
    return _shared_ioc_highlights(provider, payload)


def _shared_ioc_highlights(provider: str, payload: dict[str, Any]) -> list[dict[str, str] | None]:
    return [
        _highlight("Pulses", _pulse_count(payload.get("pulse_count")), provider),
        _highlight("Reputation", payload.get("reputation"), provider),
        _highlight("URLs", payload.get("url_count"), provider),
        _highlight("Payloads", payload.get("payload_count"), provider),
        _highlight("IOCs", payload.get("ioc_count"), provider),
        _highlight("Malware", _join_list(payload.get("malware"), limit=4), provider, "warning"),
        _highlight("Tags", _join_list(payload.get("tags"), limit=5), provider),
    ]


def _dedupe_highlights(highlights: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for item in highlights:
        key = (item["label"], item["value"], item["provider"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= MAX_INTEL_SUMMARY_HIGHLIGHTS:
            break
    return result


def summarize_intel_snapshots(
    entity_type: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    providers_with_data: list[str] = []
    highlights: list[dict[str, str]] = []
    latest_fetched_at = ""
    for snapshot in snapshots:
        provider = str(snapshot.get("provider") or "").strip().lower()
        if not provider:
            continue
        fetched_at = str(snapshot.get("fetched_at") or "")
        if fetched_at > latest_fetched_at:
            latest_fetched_at = fetched_at
        has_data = _snapshot_has_intel(snapshot)
        payload = _intel_provider_payload(snapshot)
        if has_data and provider not in providers_with_data:
            providers_with_data.append(provider)
        if str(snapshot.get("status") or "") == "ok" and payload:
            highlights.extend(_highlights_for_provider(str(entity_type or ""), provider, payload))
    highlights = _dedupe_highlights(highlights)
    status = "none"
    if snapshots:
        status = "available" if providers_with_data or highlights else "empty"
    return {
        "status": status,
        "providers_with_data": providers_with_data,
        "highlight_count": len(highlights),
        "highlights": highlights,
        "updated_at": latest_fetched_at,
    }


def _row_to_finding(row) -> dict[str, Any]:
    snippet = row["snippet"] if "snippet" in row.keys() else ""
    raw_line = row["raw_line"] or ""
    line_number = row["line_number"] if "line_number" in row.keys() else None
    return {
        "id": row["id"],
        "entity_id": row["entity_id"] or "",
        "entity_type": (row["entity_type"] if "entity_type" in row.keys() else "") or "",
        "entity_value": (row["entity_value"] if "entity_value" in row.keys() else "") or "",
        "subject_key": row["subject_key"] or "",
        "severity": row["severity"] or "",
        "kind": row["kind"] or "finding",
        "tool_root": row["tool_root"] or "",
        "first_run_id": row["first_run_id"] or "",
        "last_run_id": row["last_run_id"] or "",
        "run_id": row["last_run_id"] or "",
        "run_command": row["run_command"] if "run_command" in row.keys() else "",
        "run_kind": row["run_kind"] if "run_kind" in row.keys() else "",
        "first_seen_at": row["first_seen_at"] or "",
        "last_seen_at": row["last_seen_at"] or "",
        "occurrence_count": int(row["occurrence_count"] or 0),
        "status": row["status"] or "new",
        "review_state": row["status"] or "new",
        "title": row["title"] or "",
        "raw_line": snippet or raw_line,
        "line_number": line_number,
        "created": row["created"] or "",
    }


def _metadata_for_entity(conn, session_id: str, entity_id: str) -> dict[str, Any]:
    labels = conn.execute(
        "SELECT id, label, source, created "
        "FROM entity_labels WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ? "
        "ORDER BY label COLLATE NOCASE ASC, created ASC",
        (session_id, entity_id),
    ).fetchall()
    note = conn.execute(
        "SELECT id, body, created, updated "
        "FROM entity_notes WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
        (session_id, entity_id),
    ).fetchone()
    links = conn.execute(
        "SELECT l.id, l.project_id, p.name AS project_name, l.entity_type, l.entity_id, l.source, l.created "
        "FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE p.session_id = ? AND l.entity_type = 'atlas_entity' AND l.entity_id = ? "
        "ORDER BY l.created DESC",
        (session_id, entity_id),
    ).fetchall()
    return {
        "labels": [_row_to_label(row) for row in labels],
        "note": _row_to_note(note),
        "project_links": [_row_to_project_link(row) for row in links],
    }


def atlas_summary(conn, session_id: str, *, orphan_filter: str = "hide") -> dict[str, Any]:
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    rows = conn.execute(
        "SELECT e.type, COUNT(*) AS count FROM entities e WHERE e.session_id = ? "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        "))) "
        "GROUP BY e.type",
        [session_id, *_orphan_params(normalized_orphan_filter)],
    ).fetchall()
    counts = {entity_type: 0 for entity_type in sorted(ATLAS_ENTITY_TYPES)}
    for row in rows:
        counts[str(row["type"])] = int(row["count"] or 0)
    finding_count = int(conn.execute(
        "SELECT COUNT(*) AS count FROM findings f WHERE f.session_id = ? "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        "))) ",
        [session_id, *_orphan_params(normalized_orphan_filter)],
    ).fetchone()["count"] or 0)
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "findings": finding_count,
    }


def _normalize_finding_statuses(values: list[str] | None) -> list[str]:
    statuses: list[str] = []
    for value in values or []:
        status = str(value or "").strip().lower()
        if status in FINDING_REVIEW_STATES and status not in statuses:
            statuses.append(status)
    return statuses


def list_findings(
    conn,
    session_id: str,
    *,
    query: str = "",
    project_id: str = "",
    review_states: list[str] | None = None,
    orphan_filter: str = "hide",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    search = str(query or "").strip().lower()
    search_like = f"%{search}%" if search else ""
    project_filter = str(project_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    statuses = _normalize_finding_statuses(review_states)
    status_params = [*statuses, "", "", "", "", ""][:5]
    params: list[Any] = [
        session_id,
        search,
        search_like,
        search_like,
        search_like,
        search_like,
        project_filter,
        project_filter,
        len(statuses),
        *status_params,
        *_orphan_params(normalized_orphan_filter),
    ]
    total = int(conn.execute(
        "SELECT COUNT(*) AS count FROM findings f "
        "LEFT JOIN entities e ON e.id = f.entity_id "
        "WHERE f.session_id = ? "
        "AND (? = '' OR lower(f.title) LIKE ? OR lower(f.raw_line) LIKE ? "
        "OR lower(f.tool_root) LIKE ? OR lower(COALESCE(e.canonical_value, '')) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = f.entity_id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = f.session_id"
        ")) "
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        "))) ",
        params,
    ).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows = conn.execute(
        "SELECT f.id, f.entity_id, e.type AS entity_type, e.canonical_value AS entity_value, "
        "f.subject_key, f.severity, f.kind, f.tool_root, f.first_run_id, f.last_run_id, "
        "r.command AS run_command, r.run_kind AS run_kind, "
        "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, f.raw_line, f.created, "
        "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, "
        "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet "
        "FROM findings f "
        "LEFT JOIN entities e ON e.id = f.entity_id "
        "LEFT JOIN runs r ON r.id = f.last_run_id AND r.session_id = f.session_id "
        "WHERE f.session_id = ? "
        "AND (? = '' OR lower(f.title) LIKE ? OR lower(f.raw_line) LIKE ? "
        "OR lower(f.tool_root) LIKE ? OR lower(COALESCE(e.canonical_value, '')) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = f.entity_id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = f.session_id"
        ")) "
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        "))) "
        "ORDER BY CASE f.status "
        "WHEN 'new' THEN 0 WHEN 'needs_followup' THEN 1 WHEN 'important' THEN 2 "
        "WHEN 'reviewed' THEN 3 WHEN 'false_positive' THEN 4 ELSE 9 END, "
        "f.last_seen_at DESC, f.created DESC LIMIT ? OFFSET ?",
        [*params, page_limit, page_offset],
    ).fetchall()
    counts = {status: 0 for status in sorted(FINDING_REVIEW_STATES, key=lambda item: FINDING_STATUS_ORDER.get(item, 99))}
    count_rows = conn.execute(
        "SELECT f.status, COUNT(*) AS count FROM findings f WHERE f.session_id = ? "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM findings_occurrences orphan_fo "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id "
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id"
        "))) "
        "GROUP BY f.status",
        [session_id, *_orphan_params(normalized_orphan_filter)],
    ).fetchall()
    for row in count_rows:
        status = str(row["status"] or "new")
        counts[status] = int(row["count"] or 0)
    return {
        "findings": [_row_to_finding(row) for row in rows],
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
        "counts": counts,
    }


def list_entities(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    orphan_filter: str = "hide",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip().lower()
    search_like = f"%{search}%" if search else ""
    project_filter = str(project_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    common_params: list[Any] = [
        session_id,
        normalized_type,
        normalized_type,
        search,
        search_like,
        project_filter,
        project_filter,
        *_orphan_params(normalized_orphan_filter),
    ]
    total = int(conn.execute(
        "SELECT COUNT(*) AS count "
        "FROM entities e "
        "WHERE e.session_id = ? "
        "AND (? = '' OR e.type = ?) "
        "AND (? = '' OR lower(e.canonical_value) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = e.id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = e.session_id"
        ")) "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        "))) ",
        common_params,
    ).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows = conn.execute(
        "SELECT e.id, e.session_id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, "
        "e.occurrence_count, e.created, COUNT(DISTINCT entity_run.id) AS run_count "
        "FROM entities e "
        "LEFT JOIN entity_run_links erl ON erl.entity_id = e.id "
        "LEFT JOIN runs entity_run ON entity_run.id = erl.run_id AND entity_run.session_id = e.session_id "
        "WHERE e.session_id = ? "
        "AND (? = '' OR e.type = ?) "
        "AND (? = '' OR lower(e.canonical_value) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = e.id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = e.session_id"
        ")) "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        "))) "
        "GROUP BY e.id "
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ? OFFSET ?",
        [*common_params, page_limit, page_offset],
    ).fetchall()
    entities = []
    for row in rows:
        item = _row_to_entity(row)
        item["run_count"] = int(row["run_count"] or 0)
        metadata = _metadata_for_entity(conn, session_id, item["id"])
        item["labels"] = metadata["labels"]
        item["note"] = metadata["note"]
        item["project_links"] = metadata["project_links"]
        item["project_link_count"] = len(metadata["project_links"])
        entities.append(item)
    return {
        "entities": entities,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
    }


def _has_intel_data(data_json: str) -> bool:
    try:
        payload = json.loads(data_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    summary = payload.get("summary")
    if isinstance(summary, dict):
        providers = summary.get("providers_with_data")
        if isinstance(providers, list) and providers:
            return True
        has_intel = summary.get("has_intel")
        if isinstance(has_intel, bool):
            return has_intel
    return False


def _query_export_entities(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    orphan_filter: str = "hide",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip().lower()
    search_like = f"%{search}%" if search else ""
    project_filter = str(project_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    page_limit = max(1, min(int(limit or 10000), 10000))
    params: list[Any] = [
        session_id,
        normalized_type,
        normalized_type,
        search,
        search_like,
        project_filter,
        project_filter,
        *_orphan_params(normalized_orphan_filter),
        page_limit,
    ]
    rows = conn.execute(
        "SELECT e.id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, e.occurrence_count "
        "FROM entities e "
        "WHERE e.session_id = ? "
        "AND (? = '' OR e.type = ?) "
        "AND (? = '' OR lower(e.canonical_value) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = e.id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = e.session_id"
        ")) "
        "AND (? = 'all' "
        "OR (? = 'hide' AND EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        ")) "
        "OR (? = 'only' AND NOT EXISTS ("
        "  SELECT 1 FROM entity_run_links orphan_erl "
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id "
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id"
        "))) "
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ?",
        params,
    ).fetchall()
    entities = [
        {
            "id": row["id"],
            "type": row["type"],
            "canonical_value": row["canonical_value"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "occurrence_count": int(row["occurrence_count"] or 0),
            "labels": [],
            "notes": "",
            "project_names": [],
            "intel_providers_with_data": [],
        }
        for row in rows
    ]
    entity_ids = [str(row["id"]) for row in entities]
    if not entity_ids:
        return entities
    placeholders = ",".join("?" for _ in entity_ids)
    labels = conn.execute(
        "SELECT entity_id, label FROM entity_labels "
        "WHERE session_id = ? AND entity_type = 'atlas_entity' "
        f"AND entity_id IN ({placeholders}) ORDER BY label COLLATE NOCASE ASC",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    notes = conn.execute(
        "SELECT entity_id, body FROM entity_notes "
        "WHERE session_id = ? AND entity_type = 'atlas_entity' "
        f"AND entity_id IN ({placeholders})",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    projects = conn.execute(
        "SELECT l.entity_id, p.name FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE p.session_id = ? AND l.entity_type = 'atlas_entity' "
        f"AND l.entity_id IN ({placeholders}) ORDER BY p.name COLLATE NOCASE ASC",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    snapshots = conn.execute(
        "SELECT entity_id, provider, data_json FROM entity_intel_snapshots "
        f"WHERE session_id = ? AND entity_id IN ({placeholders}) ORDER BY provider COLLATE NOCASE ASC",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    by_id = {str(entity["id"]): entity for entity in entities}
    for row in labels:
        by_id[str(row["entity_id"])]["labels"].append(str(row["label"] or ""))
    for row in notes:
        by_id[str(row["entity_id"])]["notes"] = str(row["body"] or "")
    for row in projects:
        by_id[str(row["entity_id"])]["project_names"].append(str(row["name"] or ""))
    for row in snapshots:
        if _has_intel_data(str(row["data_json"] or "")):
            by_id[str(row["entity_id"])]["intel_providers_with_data"].append(str(row["provider"] or ""))
    return entities


def atlas_entities_export(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    orphan_filter: str = "hide",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    return _query_export_entities(
        conn,
        session_id,
        entity_type=entity_type,
        query=query,
        project_id=project_id,
        orphan_filter=orphan_filter,
        limit=limit,
    )


def _export_csv_value(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item or ""))
    return str(value or "")


def atlas_entities_export_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ATLAS_ENTITY_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _export_csv_value(row.get(field)) for field in ATLAS_ENTITY_EXPORT_FIELDS})
    return output.getvalue()


def atlas_entities_export_jsonl(rows: list[dict[str, Any]]) -> str:
    lines = [
        json.dumps({field: row.get(field) for field in ATLAS_ENTITY_EXPORT_FIELDS}, sort_keys=True)
        for row in rows
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def entity_detail(conn, session_id: str, entity_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, session_id, type, canonical_value, first_seen_at, last_seen_at, "
        "occurrence_count, created FROM entities WHERE session_id = ? AND id = ?",
        (session_id, entity_id),
    ).fetchone()
    if not row:
        return None
    entity = _row_to_entity(row)
    metadata = _metadata_for_entity(conn, session_id, entity["id"])
    entity.update(metadata)
    run_rows = conn.execute(
        "SELECT erl.run_id, r.command, r.run_kind, r.started, r.finished, r.exit_code, "
        "erl.first_seen_at, erl.last_seen_at, erl.occurrence_count "
        "FROM entity_run_links erl JOIN runs r ON r.id = erl.run_id "
        "WHERE erl.entity_id = ? AND r.session_id = ? "
        "ORDER BY erl.last_seen_at DESC, r.started DESC",
        (entity_id, session_id),
    ).fetchall()
    snapshot_rows = conn.execute(
        "SELECT id, provider, status, summary, data_json, fetched_at, expires_at "
        "FROM entity_intel_snapshots WHERE session_id = ? AND entity_id = ? "
        "ORDER BY fetched_at DESC, provider ASC",
        (session_id, entity_id),
    ).fetchall()
    finding_rows = conn.execute(
        "SELECT id, entity_id, subject_key, severity, kind, tool_root, first_run_id, last_run_id, "
        "first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created "
        "FROM findings WHERE session_id = ? AND entity_id = ? "
        "ORDER BY last_seen_at DESC, created DESC",
        (session_id, entity_id),
    ).fetchall()
    intel_snapshots = [_row_to_intel_snapshot(snapshot) for snapshot in snapshot_rows]
    return {
        "entity": entity,
        "runs": [_row_to_run_link(run) for run in run_rows],
        "intel_snapshots": intel_snapshots,
        "intel_summary": summarize_intel_snapshots(entity["type"], intel_snapshots),
        "findings": [_row_to_finding(finding) for finding in finding_rows],
    }
