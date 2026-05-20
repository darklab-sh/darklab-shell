"""Read helpers for the Session Entity Atlas."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from core.database import DB_BACKEND
from core.database_backend import dialect_for_backend
from services.atlas.materializer import ATLAS_ENTITY_TYPES
from services.intel.registry import provider_label
from services.projects.contracts import FINDING_REVIEW_STATES
from services.storage.body_store import load_text_body, stored_body_pointer


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
    "suppressed",
    "suppressed_reason",
    "suppressed_at",
)

MAX_INTEL_SUMMARY_HIGHLIGHTS = 8
ORPHAN_FILTERS = {"all", "hide", "only"}
SUPPRESSION_FILTERS = {"all", "hide", "only"}
ENTITY_DETAIL_RUN_LIMIT = 50
ENTITY_DETAIL_FINDING_LIMIT = 50
ATLAS_RUN_FILTER_LIMIT = 50


def _sql_join(parts: tuple[str, ...]) -> str:
    return "".join(parts)


def _row_to_entity(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "type": row["type"],
        "canonical_value": row["canonical_value"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "occurrence_count": int(row["occurrence_count"] or 0),
        "suppressed": bool(row["suppressed"]) if "suppressed" in row.keys() else False,
        "suppressed_reason": (row["suppressed_reason"] if "suppressed_reason" in row.keys() else "") or "",
        "suppressed_at": (row["suppressed_at"] if "suppressed_at" in row.keys() else "") or "",
        "created": row["created"],
    }


def _row_to_source_run(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["id"],
        "command": row["command"] or "",
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "entity_count": int(row["entity_count"] or 0),
        "finding_count": int(row["finding_count"] or 0),
    }


def atlas_counts_by_run(conn, session_id: str, run_ids: list[str]) -> dict[str, dict[str, int]]:
    ids = list(dict.fromkeys(str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()))
    counts = {
        run_id: {"atlas_entity_count": 0, "atlas_finding_count": 0}
        for run_id in ids
    }
    if not ids:
        return counts
    dialect = dialect_for_backend(DB_BACKEND)
    run_filter_sql, run_filter_params = dialect.in_clause("id", ids)
    rows_sql = _sql_join((
        "WITH candidate_runs AS (",
        "  SELECT id FROM runs WHERE session_id = ? AND ",
        run_filter_sql,
        "), entity_counts AS (",
        "  SELECT erl.run_id, COUNT(DISTINCT erl.entity_id) AS entity_count ",
        "  FROM entity_run_links erl ",
        "  JOIN candidate_runs candidate ON candidate.id = erl.run_id ",
        "  JOIN entities e ON e.id = erl.entity_id ",
        "  WHERE e.session_id = ? ",
        "  GROUP BY erl.run_id",
        "), finding_run_pairs AS (",
        "  SELECT fo.run_id, fo.finding_id ",
        "  FROM findings_occurrences fo ",
        "  JOIN candidate_runs candidate ON candidate.id = fo.run_id ",
        "  JOIN findings f ON f.id = fo.finding_id ",
        "  WHERE f.session_id = ? ",
        "  UNION ",
        "  SELECT f.run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.run_id ",
        "  WHERE f.session_id = ? AND COALESCE(f.run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.first_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.first_run_id ",
        "  WHERE f.session_id = ? AND COALESCE(f.first_run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.last_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.last_run_id ",
        "  WHERE f.session_id = ? AND COALESCE(f.last_run_id, '') != ''",
        "), finding_counts AS (",
        "  SELECT run_id, COUNT(DISTINCT finding_id) AS finding_count ",
        "  FROM finding_run_pairs ",
        "  GROUP BY run_id",
        ") ",
        "SELECT candidate.id AS run_id, ",
        "COALESCE(entity_counts.entity_count, 0) AS entity_count, ",
        "COALESCE(finding_counts.finding_count, 0) AS finding_count ",
        "FROM candidate_runs candidate ",
        "LEFT JOIN entity_counts ON entity_counts.run_id = candidate.id ",
        "LEFT JOIN finding_counts ON finding_counts.run_id = candidate.id",
    ))
    rows = conn.execute(
        rows_sql,
        [session_id, *run_filter_params, session_id, session_id, session_id, session_id, session_id],
    ).fetchall()
    for row in rows:
        run_id = str(row["run_id"] or "")
        if run_id in counts:
            counts[run_id]["atlas_entity_count"] = int(row["entity_count"] or 0)
            counts[run_id]["atlas_finding_count"] = int(row["finding_count"] or 0)
    return counts


def _normalize_orphan_filter(value: str | None) -> str:
    orphan_filter = str(value or "hide").strip().lower()
    return orphan_filter if orphan_filter in ORPHAN_FILTERS else "hide"


def _orphan_params(orphan_filter: str) -> list[str]:
    normalized = _normalize_orphan_filter(orphan_filter)
    return [normalized, normalized, normalized]


def _normalize_suppression_filter(value: str | None) -> str:
    suppression_filter = str(value or "hide").strip().lower()
    return suppression_filter if suppression_filter in SUPPRESSION_FILTERS else "hide"


def _suppression_params(suppression_filter: str) -> list[str]:
    normalized = _normalize_suppression_filter(suppression_filter)
    return [normalized, normalized, normalized]


def _suppression_clause(alias: str) -> str:
    return (
        f"AND (? = 'all' "
        f"OR (? = 'hide' AND COALESCE({alias}.suppressed, FALSE) = FALSE) "
        f"OR (? = 'only' AND COALESCE({alias}.suppressed, FALSE) = TRUE)) "
    )


def list_source_runs(
    conn,
    session_id: str,
    *,
    query: str = "",
    run_id: str = "",
    limit: int = ATLAS_RUN_FILTER_LIMIT,
) -> dict[str, Any]:
    """Return recent/searchable runs that currently contribute Atlas rows."""
    search = str(query or "").strip()
    selected_run_id = str(run_id or "").strip()
    search_like = dialect_for_backend(DB_BACKEND).text_search_param(search) if search else ""
    safe_limit = max(1, min(int(limit or ATLAS_RUN_FILTER_LIMIT), ATLAS_RUN_FILTER_LIMIT))
    rows_sql = _sql_join((
        "WITH source_run_ids AS (",
        "  SELECT erl.run_id AS run_id ",
        "  FROM entity_run_links erl ",
        "  JOIN entities e ON e.id = erl.entity_id ",
        "  WHERE e.session_id = ? ",
        "  UNION ",
        "  SELECT fo.run_id AS run_id ",
        "  FROM findings_occurrences fo ",
        "  JOIN findings f ON f.id = fo.finding_id ",
        "  WHERE f.session_id = ? ",
        "  UNION ",
        "  SELECT f.run_id AS run_id FROM findings f WHERE f.session_id = ? AND COALESCE(f.run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.first_run_id AS run_id FROM findings f WHERE f.session_id = ? AND COALESCE(f.first_run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.last_run_id AS run_id FROM findings f WHERE f.session_id = ? AND COALESCE(f.last_run_id, '') != '' ",
        "  UNION ",
        "  SELECT ? AS run_id WHERE ? != ''",
        "), candidate_runs AS (",
        "  SELECT r.id, r.command, r.started, r.finished, r.exit_code ",
        "  FROM runs r ",
        "  JOIN source_run_ids source ON source.run_id = r.id ",
        "  WHERE r.session_id = ? ",
        "  AND (? = '' OR r.id = ? OR ",
        dialect_for_backend(DB_BACKEND).text_search_expr("r.command"),
        "  ) ",
        "  ORDER BY CASE WHEN r.id = ? THEN 0 ELSE 1 END, r.started DESC, r.id DESC ",
        "  LIMIT ?",
        "), entity_counts AS (",
        "  SELECT erl.run_id, COUNT(DISTINCT erl.entity_id) AS entity_count ",
        "  FROM entity_run_links erl ",
        "  JOIN candidate_runs candidate ON candidate.id = erl.run_id ",
        "  JOIN entities e ON e.id = erl.entity_id ",
        "  WHERE e.session_id = ? ",
        "  GROUP BY erl.run_id",
        "), finding_run_pairs AS (",
        "  SELECT fo.run_id, fo.finding_id ",
        "  FROM findings_occurrences fo ",
        "  JOIN candidate_runs candidate ON candidate.id = fo.run_id ",
        "  JOIN findings f ON f.id = fo.finding_id ",
        "  WHERE f.session_id = ? ",
        "  UNION ",
        "  SELECT f.run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.run_id ",
        "  WHERE f.session_id = ? AND COALESCE(f.run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.first_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.first_run_id ",
        "  WHERE f.session_id = ? AND COALESCE(f.first_run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.last_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.last_run_id ",
        "  WHERE f.session_id = ? AND COALESCE(f.last_run_id, '') != ''",
        "), finding_counts AS (",
        "  SELECT run_id, COUNT(DISTINCT finding_id) AS finding_count ",
        "  FROM finding_run_pairs ",
        "  GROUP BY run_id",
        ") ",
        "SELECT candidate.id, candidate.command, candidate.started, candidate.finished, candidate.exit_code, ",
        "COALESCE(entity_counts.entity_count, 0) AS entity_count, ",
        "COALESCE(finding_counts.finding_count, 0) AS finding_count ",
        "FROM candidate_runs candidate ",
        "LEFT JOIN entity_counts ON entity_counts.run_id = candidate.id ",
        "LEFT JOIN finding_counts ON finding_counts.run_id = candidate.id ",
        "ORDER BY CASE WHEN candidate.id = ? THEN 0 ELSE 1 END, candidate.started DESC, candidate.id DESC",
    ))
    rows = conn.execute(
        rows_sql,
        [
            session_id,
            session_id,
            session_id,
            session_id,
            session_id,
            selected_run_id,
            selected_run_id,
            session_id,
            search,
            selected_run_id,
            search_like,
            selected_run_id,
            safe_limit,
            session_id,
            session_id,
            session_id,
            session_id,
            session_id,
            selected_run_id,
        ],
    ).fetchall()
    return {"runs": [_row_to_source_run(row) for row in rows], "limit": safe_limit}


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


def _label_order_sql(prefix: str = "") -> str:
    column = f"{prefix}label" if prefix else "label"
    return dialect_for_backend(DB_BACKEND).case_insensitive_order(column) + ", created ASC"


def _name_order_sql(prefix: str = "") -> str:
    column = f"{prefix}name" if prefix else "name"
    return dialect_for_backend(DB_BACKEND).case_insensitive_order(column)


def _provider_order_sql() -> str:
    return dialect_for_backend(DB_BACKEND).case_insensitive_order("provider")


def _atlas_search_clause(columns: list[str], extra_exprs: tuple[str, ...] = ()) -> str:
    dialect = dialect_for_backend(DB_BACKEND)
    expressions = [dialect.text_search_expr(column) for column in columns]
    expressions.extend(extra_exprs)
    return "AND (? = '' OR " + " OR ".join(expressions) + ") "


def _metadata_search_expr(table_name: str, alias: str, owner_alias: str, entity_type: str, entity_id_sql: str) -> str:
    column = "label" if table_name == "entity_labels" else "body"
    return _sql_join((
        "EXISTS (",
        f"SELECT 1 FROM {table_name} {alias} ",  # nosec
        f"WHERE {alias}.session_id = {owner_alias}.session_id ",
        f"AND {alias}.entity_type = '{entity_type}' ",
        f"AND {alias}.entity_id = {entity_id_sql} ",
        "AND ",
        dialect_for_backend(DB_BACKEND).text_search_expr(f"{alias}.{column}"),
        ")",
    ))


def _entity_metadata_search_exprs(owner_alias: str, entity_id_sql: str) -> tuple[str, str]:
    return (
        _metadata_search_expr("entity_labels", "entity_search_label", owner_alias, "atlas_entity", entity_id_sql),
        _metadata_search_expr("entity_notes", "entity_search_note", owner_alias, "atlas_entity", entity_id_sql),
    )


def _finding_metadata_search_exprs() -> tuple[str, str, str, str]:
    return (
        _metadata_search_expr("entity_labels", "finding_search_label", "f", "finding", "f.id"),
        _metadata_search_expr("entity_notes", "finding_search_note", "f", "finding", "f.id"),
        _metadata_search_expr("entity_labels", "finding_entity_search_label", "f", "atlas_entity", "e.id"),
        _metadata_search_expr("entity_notes", "finding_entity_search_note", "f", "atlas_entity", "e.id"),
    )


def _load_json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        if not stored_body_pointer(value):
            return value
        text = load_text_body(value)
    elif isinstance(value, str) or value is None:
        text = load_text_body(value)
    else:
        return {}
    return dialect_for_backend(DB_BACKEND).decode_json_dict(text)


def _row_to_intel_snapshot(row) -> dict[str, Any]:
    data = _load_json_dict(row["data_json"])
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
        "suppressed": bool(row["suppressed"]) if "suppressed" in row.keys() else False,
        "suppressed_reason": (row["suppressed_reason"] if "suppressed_reason" in row.keys() else "") or "",
        "suppressed_at": (row["suppressed_at"] if "suppressed_at" in row.keys() else "") or "",
        "title": row["title"] or "",
        "raw_line": snippet or raw_line,
        "line_number": line_number,
        "created": row["created"] or "",
    }


def _metadata_for_entity(conn, session_id: str, entity_id: str) -> dict[str, Any]:
    labels = conn.execute(
        "SELECT id, label, source, created "  # nosec B608
        "FROM entity_labels WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ? "
        "ORDER BY " + _label_order_sql(),
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


def _list_metadata_for_entities(conn, session_id: str, entity_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not entity_ids:
        return {}
    dialect = dialect_for_backend(DB_BACKEND)
    entity_filter_sql, entity_filter_params = dialect.in_clause("entity_id", entity_ids)
    link_filter_sql, link_filter_params = dialect.in_clause("l.entity_id", entity_ids)
    metadata = {
        entity_id: {
            "labels": [],
            "project_link_count": 0,
        }
        for entity_id in entity_ids
    }
    labels = conn.execute(
        "SELECT entity_id, id, label, source, created "
        "FROM entity_labels WHERE session_id = ? AND entity_type = 'atlas_entity' "
        "AND " + entity_filter_sql + " ORDER BY " + _label_order_sql(),  # nosec
        [session_id, *entity_filter_params],
    ).fetchall()
    for row in labels:
        entity_id = str(row["entity_id"] or "")
        if entity_id in metadata:
            metadata[entity_id]["labels"].append(_row_to_label(row))
    links = conn.execute(
        "SELECT l.entity_id, COUNT(*) AS count "
        "FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE p.session_id = ? AND l.entity_type = 'atlas_entity' "
        "AND " + link_filter_sql + " GROUP BY l.entity_id",  # nosec
        [session_id, *link_filter_params],
    ).fetchall()
    for row in links:
        entity_id = str(row["entity_id"] or "")
        if entity_id in metadata:
            metadata[entity_id]["project_link_count"] = int(row["count"] or 0)
    return metadata


def atlas_summary(
    conn,
    session_id: str,
    *,
    run_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
) -> dict[str, Any]:
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    entity_counts_sql = _sql_join((
        "SELECT e.type, COUNT(*) AS count FROM entities e WHERE e.session_id = ? ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM entity_run_links filter_erl ",
        "  JOIN runs filter_run ON filter_run.id = filter_erl.run_id ",
        "  WHERE filter_erl.entity_id = e.id ",
        "  AND filter_run.session_id = e.session_id ",
        "  AND filter_erl.run_id = ?",
        ")) ",
        _suppression_clause("e"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        "))) ",
        "GROUP BY e.type",
    ))
    rows = conn.execute(
        entity_counts_sql,
        [
            session_id,
            run_filter,
            run_filter,
            *_suppression_params(normalized_suppression_filter),
            *_orphan_params(normalized_orphan_filter),
        ],
    ).fetchall()
    counts = {entity_type: 0 for entity_type in sorted(ATLAS_ENTITY_TYPES)}
    for row in rows:
        counts[str(row["type"])] = int(row["count"] or 0)
    finding_count_sql = _sql_join((
        "SELECT COUNT(*) AS count FROM findings f WHERE f.session_id = ? ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM findings_occurrences filter_run_fo ",
        "  JOIN runs filter_run ON filter_run.id = filter_run_fo.run_id ",
        "  WHERE filter_run_fo.finding_id = f.id ",
        "  AND filter_run.session_id = f.session_id ",
        "  AND filter_run_fo.run_id = ?",
        ") OR f.run_id = ? OR f.first_run_id = ? OR f.last_run_id = ?) ",
        _suppression_clause("f"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        "))) ",
    ))
    finding_count = int(conn.execute(
        finding_count_sql,
        [
            session_id,
            run_filter,
            run_filter,
            run_filter,
            run_filter,
            run_filter,
            *_suppression_params(normalized_suppression_filter),
            *_orphan_params(normalized_orphan_filter),
        ],
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
    run_id: str = "",
    review_states: list[str] | None = None,
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    search = str(query or "").strip()
    search_like = dialect_for_backend(DB_BACKEND).text_search_param(search) if search else ""
    search_columns = [
        "f.title",
        "f.raw_line",
        "f.tool_root",
        "e.canonical_value",
    ]
    search_exprs = _finding_metadata_search_exprs()
    search_clause = _atlas_search_clause(search_columns, search_exprs)
    project_filter = str(project_id or "").strip()
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    statuses = _normalize_finding_statuses(review_states)
    status_params = [*statuses, "", "", "", "", ""][:5]
    params: list[Any] = [
        session_id,
        search,
        *([search_like] * (len(search_columns) + len(search_exprs))),
        project_filter,
        project_filter,
        run_filter,
        run_filter,
        run_filter,
        run_filter,
        run_filter,
        len(statuses),
        *status_params,
        *_suppression_params(normalized_suppression_filter),
        *_orphan_params(normalized_orphan_filter),
    ]
    total_sql = _sql_join((
        "SELECT COUNT(*) AS count FROM findings f ",
        "LEFT JOIN entities e ON e.id = f.entity_id ",
        "WHERE f.session_id = ? ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = f.entity_id ",
        "  AND filter_link.project_id = ? ",
        "  AND filter_project.session_id = f.session_id",
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM findings_occurrences filter_run_fo ",
        "  JOIN runs filter_run ON filter_run.id = filter_run_fo.run_id ",
        "  WHERE filter_run_fo.finding_id = f.id ",
        "  AND filter_run.session_id = f.session_id ",
        "  AND filter_run_fo.run_id = ?",
        ") OR f.run_id = ? OR f.first_run_id = ? OR f.last_run_id = ?) ",
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) ",
        _suppression_clause("f"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        "))) ",
    ))
    total = int(conn.execute(total_sql, params).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows_sql = _sql_join((
        "SELECT f.id, f.entity_id, e.type AS entity_type, e.canonical_value AS entity_value, ",
        "f.subject_key, f.severity, f.kind, f.tool_root, f.first_run_id, f.last_run_id, ",
        "r.command AS run_command, r.run_kind AS run_kind, ",
        "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, f.raw_line, f.created, ",
        "f.suppressed, f.suppressed_reason, f.suppressed_at, ",
        "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id ",
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, ",
        "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id ",
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet ",
        "FROM findings f ",
        "LEFT JOIN entities e ON e.id = f.entity_id ",
        "LEFT JOIN runs r ON r.id = f.last_run_id AND r.session_id = f.session_id ",
        "WHERE f.session_id = ? ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = f.entity_id ",
        "  AND filter_link.project_id = ? ",
        "  AND filter_project.session_id = f.session_id",
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM findings_occurrences filter_run_fo ",
        "  JOIN runs filter_run ON filter_run.id = filter_run_fo.run_id ",
        "  WHERE filter_run_fo.finding_id = f.id ",
        "  AND filter_run.session_id = f.session_id ",
        "  AND filter_run_fo.run_id = ?",
        ") OR f.run_id = ? OR f.first_run_id = ? OR f.last_run_id = ?) ",
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) ",
        _suppression_clause("f"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        "))) ",
        "ORDER BY CASE f.status ",
        "WHEN 'new' THEN 0 WHEN 'needs_followup' THEN 1 WHEN 'important' THEN 2 ",
        "WHEN 'reviewed' THEN 3 WHEN 'false_positive' THEN 4 ELSE 9 END, ",
        "f.last_seen_at DESC, f.created DESC LIMIT ? OFFSET ?",
    ))
    rows = conn.execute(rows_sql, [*params, page_limit, page_offset]).fetchall()
    counts = {status: 0 for status in sorted(FINDING_REVIEW_STATES, key=lambda item: FINDING_STATUS_ORDER.get(item, 99))}
    status_counts_sql = _sql_join((
        "SELECT f.status, COUNT(*) AS count FROM findings f WHERE f.session_id = ? ",
        _suppression_clause("f"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM findings_occurrences orphan_fo ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_fo.run_id ",
        "  WHERE orphan_fo.finding_id = f.id AND orphan_run.session_id = f.session_id",
        "))) ",
        "GROUP BY f.status",
    ))
    count_rows = conn.execute(
        status_counts_sql,
        [
            session_id,
            *_suppression_params(normalized_suppression_filter),
            *_orphan_params(normalized_orphan_filter),
        ],
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


def finding_detail(conn, session_id: str, finding_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT f.id, f.entity_id, e.type AS entity_type, e.canonical_value AS entity_value, "
        "f.subject_key, f.severity, f.kind, f.tool_root, f.first_run_id, f.last_run_id, "
        "r.command AS run_command, r.run_kind AS run_kind, "
        "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, f.raw_line, f.created, "
        "f.suppressed, f.suppressed_reason, f.suppressed_at, "
        "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, "
        "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet "
        "FROM findings f "
        "LEFT JOIN entities e ON e.id = f.entity_id "
        "LEFT JOIN runs r ON r.id = f.last_run_id AND r.session_id = f.session_id "
        "WHERE f.session_id = ? AND f.id = ?",
        (session_id, finding_id),
    ).fetchone()
    if not row:
        return None
    occurrence_rows = conn.execute(
        "SELECT fo.run_id, r.command, r.run_kind, r.started, r.finished, r.exit_code, "
        "fo.line_number, fo.snippet, fo.seen_at "
        "FROM findings_occurrences fo "
        "JOIN runs r ON r.id = fo.run_id "
        "WHERE fo.finding_id = ? AND r.session_id = ? "
        "ORDER BY fo.seen_at DESC, fo.run_id DESC, fo.line_number DESC LIMIT ?",
        (finding_id, session_id, ENTITY_DETAIL_RUN_LIMIT),
    ).fetchall()
    return {
        "finding": _row_to_finding(row),
        "occurrences": [
            {
                "run_id": occurrence["run_id"],
                "command": occurrence["command"] or "",
                "run_kind": occurrence["run_kind"] or "",
                "started": occurrence["started"],
                "finished": occurrence["finished"],
                "exit_code": occurrence["exit_code"],
                "line_number": occurrence["line_number"],
                "snippet": occurrence["snippet"] or "",
                "seen_at": occurrence["seen_at"],
            }
            for occurrence in occurrence_rows
        ],
        "detail_limits": {
            "occurrences": {
                "limit": ENTITY_DETAIL_RUN_LIMIT,
                "offset": 0,
                "shown": len(occurrence_rows),
                "has_more": len(occurrence_rows) >= ENTITY_DETAIL_RUN_LIMIT,
            },
        },
    }


def list_entities(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    run_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip()
    search_like = dialect_for_backend(DB_BACKEND).text_search_param(search) if search else ""
    search_columns = ["e.canonical_value"]
    search_exprs = _entity_metadata_search_exprs("e", "e.id")
    search_clause = _atlas_search_clause(search_columns, search_exprs)
    project_filter = str(project_id or "").strip()
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    common_params: list[Any] = [
        session_id,
        normalized_type,
        normalized_type,
        search,
        *([search_like] * (len(search_columns) + len(search_exprs))),
        project_filter,
        project_filter,
        run_filter,
        run_filter,
        *_suppression_params(normalized_suppression_filter),
        *_orphan_params(normalized_orphan_filter),
    ]
    total_sql = _sql_join((
        "SELECT COUNT(*) AS count ",
        "FROM entities e ",
        "WHERE e.session_id = ? ",
        "AND (? = '' OR e.type = ?) ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = e.id ",
        "  AND filter_link.project_id = ? ",
        "  AND filter_project.session_id = e.session_id",
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM entity_run_links filter_erl ",
        "  JOIN runs filter_run ON filter_run.id = filter_erl.run_id ",
        "  WHERE filter_erl.entity_id = e.id ",
        "  AND filter_run.session_id = e.session_id ",
        "  AND filter_erl.run_id = ?",
        ")) ",
        _suppression_clause("e"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        "))) ",
    ))
    total = int(conn.execute(total_sql, common_params).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows_sql = _sql_join((
        "SELECT e.id, e.session_id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, ",
        "e.occurrence_count, e.suppressed, e.suppressed_reason, e.suppressed_at, e.created, "
        "COUNT(DISTINCT entity_run.id) AS run_count ",
        "FROM entities e ",
        "LEFT JOIN entity_run_links erl ON erl.entity_id = e.id ",
        "LEFT JOIN runs entity_run ON entity_run.id = erl.run_id AND entity_run.session_id = e.session_id ",
        "WHERE e.session_id = ? ",
        "AND (? = '' OR e.type = ?) ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = e.id ",
        "  AND filter_link.project_id = ? ",
        "  AND filter_project.session_id = e.session_id",
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM entity_run_links filter_erl ",
        "  JOIN runs filter_run ON filter_run.id = filter_erl.run_id ",
        "  WHERE filter_erl.entity_id = e.id ",
        "  AND filter_run.session_id = e.session_id ",
        "  AND filter_erl.run_id = ?",
        ")) ",
        _suppression_clause("e"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        "))) ",
        "GROUP BY e.id ",
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ? OFFSET ?",
    ))
    rows = conn.execute(rows_sql, [*common_params, page_limit, page_offset]).fetchall()
    list_metadata = _list_metadata_for_entities(conn, session_id, [str(row["id"]) for row in rows])
    entities = []
    for row in rows:
        item = _row_to_entity(row)
        item["run_count"] = int(row["run_count"] or 0)
        metadata = list_metadata.get(str(item["id"]), {})
        item["labels"] = metadata.get("labels", [])
        item["project_link_count"] = int(metadata.get("project_link_count") or 0)
        entities.append(item)
    return {
        "entities": entities,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
    }


def _has_intel_data(data_json: object) -> bool:
    payload = _load_json_dict(data_json)
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
    run_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip()
    search_like = dialect_for_backend(DB_BACKEND).text_search_param(search) if search else ""
    search_columns = ["e.canonical_value"]
    search_exprs = _entity_metadata_search_exprs("e", "e.id")
    search_clause = _atlas_search_clause(search_columns, search_exprs)
    project_filter = str(project_id or "").strip()
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    page_limit = max(1, min(int(limit or 10000), 10000))
    params: list[Any] = [
        session_id,
        normalized_type,
        normalized_type,
        search,
        *([search_like] * (len(search_columns) + len(search_exprs))),
        project_filter,
        project_filter,
        run_filter,
        run_filter,
        *_suppression_params(normalized_suppression_filter),
        *_orphan_params(normalized_orphan_filter),
        page_limit,
    ]
    rows_sql = _sql_join((
        "SELECT e.id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, e.occurrence_count, "
        "e.suppressed, e.suppressed_reason, e.suppressed_at ",
        "FROM entities e ",
        "WHERE e.session_id = ? ",
        "AND (? = '' OR e.type = ?) ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = e.id ",
        "  AND filter_link.project_id = ? ",
        "  AND filter_project.session_id = e.session_id",
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM entity_run_links filter_erl ",
        "  JOIN runs filter_run ON filter_run.id = filter_erl.run_id ",
        "  WHERE filter_erl.entity_id = e.id ",
        "  AND filter_run.session_id = e.session_id ",
        "  AND filter_erl.run_id = ?",
        ")) ",
        _suppression_clause("e"),
        "AND (? = 'all' ",
        "OR (? = 'hide' AND EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        ")) ",
        "OR (? = 'only' AND NOT EXISTS (",
        "  SELECT 1 FROM entity_run_links orphan_erl ",
        "  JOIN runs orphan_run ON orphan_run.id = orphan_erl.run_id ",
        "  WHERE orphan_erl.entity_id = e.id AND orphan_run.session_id = e.session_id",
        "))) ",
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ?",
    ))
    rows = conn.execute(rows_sql, params).fetchall()
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
            "suppressed": bool(row["suppressed"]),
            "suppressed_reason": row["suppressed_reason"] or "",
            "suppressed_at": row["suppressed_at"] or "",
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
        f"AND entity_id IN ({placeholders}) ORDER BY " + _label_order_sql(),  # nosec
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
        f"AND l.entity_id IN ({placeholders}) ORDER BY " + _name_order_sql("p."),  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    snapshots = conn.execute(
        "SELECT entity_id, provider, data_json FROM entity_intel_snapshots "
        f"WHERE session_id = ? AND entity_id IN ({placeholders}) ORDER BY " + _provider_order_sql(),  # nosec
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
        if _has_intel_data(row["data_json"]):
            by_id[str(row["entity_id"])]["intel_providers_with_data"].append(str(row["provider"] or ""))
    return entities


def atlas_entities_export(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    run_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    return _query_export_entities(
        conn,
        session_id,
        entity_type=entity_type,
        query=query,
        project_id=project_id,
        run_id=run_id,
        orphan_filter=orphan_filter,
        suppression_filter=suppression_filter,
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


def entity_detail(
    conn,
    session_id: str,
    entity_id: str,
    *,
    runs_offset: int = 0,
    findings_offset: int = 0,
) -> dict[str, Any] | None:
    safe_runs_offset = max(0, int(runs_offset or 0))
    safe_findings_offset = max(0, int(findings_offset or 0))
    row = conn.execute(
        "SELECT id, session_id, type, canonical_value, first_seen_at, last_seen_at, "
        "occurrence_count, suppressed, suppressed_reason, suppressed_at, created "
        "FROM entities WHERE session_id = ? AND id = ?",
        (session_id, entity_id),
    ).fetchone()
    if not row:
        return None
    entity = _row_to_entity(row)
    metadata = _metadata_for_entity(conn, session_id, entity["id"])
    entity.update(metadata)
    run_total_row = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_run_links erl JOIN runs r ON r.id = erl.run_id "
        "WHERE erl.entity_id = ? AND r.session_id = ?",
        (entity_id, session_id),
    ).fetchone()
    finding_total_row = conn.execute(
        "SELECT COUNT(*) AS count FROM findings WHERE session_id = ? AND entity_id = ? "
        "AND COALESCE(suppressed, FALSE) = FALSE",
        (session_id, entity_id),
    ).fetchone()
    run_total = int(run_total_row["count"] or 0) if run_total_row else 0
    finding_total = int(finding_total_row["count"] or 0) if finding_total_row else 0
    run_rows = conn.execute(
        "SELECT erl.run_id, r.command, r.run_kind, r.started, r.finished, r.exit_code, "
        "erl.first_seen_at, erl.last_seen_at, erl.occurrence_count "
        "FROM entity_run_links erl JOIN runs r ON r.id = erl.run_id "
        "WHERE erl.entity_id = ? AND r.session_id = ? "
        "ORDER BY erl.last_seen_at DESC, r.started DESC LIMIT ? OFFSET ?",
        (entity_id, session_id, ENTITY_DETAIL_RUN_LIMIT, safe_runs_offset),
    ).fetchall()
    snapshot_rows = conn.execute(
        "SELECT id, provider, status, summary, data_json, fetched_at, expires_at "
        "FROM entity_intel_snapshots WHERE session_id = ? AND entity_id = ? "
        "ORDER BY fetched_at DESC, provider ASC",
        (session_id, entity_id),
    ).fetchall()
    finding_rows = conn.execute(
        "SELECT id, entity_id, subject_key, severity, kind, tool_root, first_run_id, last_run_id, "
        "first_seen_at, last_seen_at, occurrence_count, status, suppressed, suppressed_reason, suppressed_at, "
        "title, raw_line, created "
        "FROM findings WHERE session_id = ? AND entity_id = ? AND COALESCE(suppressed, FALSE) = FALSE "
        "ORDER BY last_seen_at DESC, created DESC LIMIT ? OFFSET ?",
        (session_id, entity_id, ENTITY_DETAIL_FINDING_LIMIT, safe_findings_offset),
    ).fetchall()
    intel_snapshots = [_row_to_intel_snapshot(snapshot) for snapshot in snapshot_rows]
    return {
        "entity": entity,
        "runs": [_row_to_run_link(run) for run in run_rows],
        "intel_snapshots": intel_snapshots,
        "intel_summary": summarize_intel_snapshots(entity["type"], intel_snapshots),
        "findings": [_row_to_finding(finding) for finding in finding_rows],
        "detail_limits": {
            "runs": {
                "limit": ENTITY_DETAIL_RUN_LIMIT,
                "offset": safe_runs_offset,
                "shown": len(run_rows),
                "total": run_total,
                "has_more": safe_runs_offset + len(run_rows) < run_total,
            },
            "findings": {
                "limit": ENTITY_DETAIL_FINDING_LIMIT,
                "offset": safe_findings_offset,
                "shown": len(finding_rows),
                "total": finding_total,
                "has_more": safe_findings_offset + len(finding_rows) < finding_total,
            },
        },
    }
