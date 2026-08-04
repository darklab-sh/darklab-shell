# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explainable CVE enrichment and deterministic fix-first ordering."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from core.database_access import get_db_connect
from .links import finding_cves, remediation_identity
from .store import get_configured_feed_status


_SQL_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _risk_payload(row: dict[str, Any], *, feed_status: dict[str, dict[str, Any]]) -> dict[str, Any]:
    epss = feed_status.get("epss", {})
    kev = feed_status.get("kev", {})
    return {
        "cve_id": str(row.get("cve_id") or ""),
        "kev": {
            "listed": bool(row.get("kev_listed")),
            "date_added": str(row.get("kev_date_added") or ""),
            "due_date": str(row.get("kev_due_date") or ""),
            "required_action": str(row.get("kev_required_action") or ""),
            "known_ransomware_campaign_use": str(
                row.get("kev_known_ransomware_campaign_use") or ""
            ),
            "source_version": str(row.get("kev_source_version") or ""),
            "source_published_at": str(kev.get("published_at") or ""),
            "freshness": str(kev.get("status") or "unavailable"),
        },
        "epss": {
            "probability": _number(row.get("epss_probability")),
            "percentile": _number(row.get("epss_percentile")),
            "model_version": str(row.get("epss_model_version") or ""),
            "score_date": str(row.get("epss_published_at") or ""),
            "source_version": str(row.get("epss_source_version") or ""),
            "source_published_at": str(epss.get("published_at") or ""),
            "freshness": str(epss.get("status") or "unavailable"),
        },
        "public_exploit_available": None,
        "priority_reasons": [],
    }


def explain_cve_priority(risk: dict[str, Any], *, cvss_score: Any = None) -> list[str]:
    reasons: list[str] = []
    kev = risk.get("kev") if isinstance(risk.get("kev"), dict) else {}
    epss = risk.get("epss") if isinstance(risk.get("epss"), dict) else {}
    if bool(kev.get("listed")):
        reasons.append("Listed in CISA KEV")
    probability = _number(epss.get("probability"))
    percentile = _number(epss.get("percentile"))
    if probability is not None:
        reasons.append(f"EPSS {probability * 100:.1f}% probability")
    else:
        reasons.append("EPSS unavailable")
    if percentile is not None:
        reasons.append(f"EPSS {percentile * 100:.1f}th percentile")
    cvss = _number(cvss_score)
    if cvss is not None:
        reasons.append(f"CVSS {cvss:.1f}")
    return reasons


def cve_risk_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    risk = item.get("risk") if isinstance(item.get("risk"), dict) else item
    kev = risk.get("kev") if isinstance(risk.get("kev"), dict) else {}
    epss = risk.get("epss") if isinstance(risk.get("epss"), dict) else {}
    probability = _number(epss.get("probability"))
    percentile = _number(epss.get("percentile"))
    cvss = _number(item.get("cvss_score") or risk.get("cvss_score"))
    return (
        0 if bool(kev.get("listed")) else 1,
        1 if probability is None else 0,
        -(probability or 0.0),
        1 if percentile is None else 0,
        -(percentile or 0.0),
        1 if cvss is None else 0,
        -(cvss or 0.0),
        str(item.get("first_seen_at") or item.get("created") or ""),
        str(item.get("remediation_id") or item.get("id") or ""),
    )


def cve_risk_order_sql(alias: str, *, age_expression: str) -> str:
    """Return the shared server-side ordering for one finding-row alias."""
    if not _SQL_IDENTIFIER_RE.fullmatch(alias):
        raise ValueError("unsupported CVE risk ordering alias")
    supported_age_expressions = {
        f"{alias}.created",
        f"COALESCE(NULLIF({alias}.first_seen_at, ''), {alias}.created)",
    }
    if age_expression not in supported_age_expressions:
        raise ValueError("unsupported CVE risk ordering age expression")
    finding_id = f"{alias}.id"
    epss_max = (
        "(SELECT MAX(risk_order_record.epss_probability) "  # nosec B608 -- identifiers validated above
        "FROM finding_cve_links risk_order_link "
        "JOIN cve_risk_records risk_order_record "
        "ON risk_order_record.cve_id = risk_order_link.cve_id "
        f"WHERE risk_order_link.finding_id = {finding_id})"
    )
    percentile_max = (
        "(SELECT MAX(risk_order_record.epss_percentile) "  # nosec B608 -- identifiers validated above
        "FROM finding_cve_links risk_order_link "
        "JOIN cve_risk_records risk_order_record "
        "ON risk_order_record.cve_id = risk_order_link.cve_id "
        f"WHERE risk_order_link.finding_id = {finding_id})"
    )
    return (
        "CASE WHEN EXISTS (SELECT 1 FROM finding_cve_links risk_order_link "  # nosec B608 -- identifiers validated above
        "JOIN cve_risk_records risk_order_record "
        "ON risk_order_record.cve_id = risk_order_link.cve_id "
        f"WHERE risk_order_link.finding_id = {finding_id} "
        "AND risk_order_record.kev_listed = TRUE) THEN 0 ELSE 1 END, "
        f"CASE WHEN {epss_max} IS NULL THEN 1 ELSE 0 END, {epss_max} DESC, "
        f"CASE WHEN {percentile_max} IS NULL THEN 1 ELSE 0 END, {percentile_max} DESC, "
        f"{age_expression} DESC, {finding_id} DESC"
    )


def attach_risk_to_findings(
    findings: list[dict[str, Any]],
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    if not findings:
        return findings
    cves_by_finding: dict[str, tuple[str, ...]] = {}
    cve_ids: set[str] = set()
    for finding in findings:
        finding_id = str(finding.get("id") or "")
        cves = finding_cves(finding)
        cves_by_finding[finding_id] = cves
        cve_ids.update(cves)
    if not cve_ids:
        return findings
    owns_connection = conn is None
    active = conn or get_db_connect()()
    try:
        rows: list[Any] = []
        ordered = sorted(cve_ids)
        for offset in range(0, len(ordered), 500):
            chunk = ordered[offset:offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(active.execute(
                f"SELECT * FROM cve_risk_records WHERE cve_id IN ({placeholders})",  # nosec B608
                tuple(chunk),
            ).fetchall())
        feed_status = {item["source"]: item for item in get_configured_feed_status(active)}
        risk_by_cve = {
            str(row["cve_id"]): _risk_payload(dict(row), feed_status=feed_status)
            for row in rows
        }
        for finding in findings:
            finding_id = str(finding.get("id") or "")
            cves = cves_by_finding.get(finding_id, ())
            if not cves:
                continue
            enriched: list[dict[str, Any]] = []
            for cve_id in cves:
                risk = deepcopy(risk_by_cve.get(cve_id, {
                    "cve_id": cve_id,
                    "kev": {"listed": False, "freshness": "unavailable"},
                    "epss": {
                        "probability": None,
                        "percentile": None,
                        "freshness": "unavailable",
                    },
                    "public_exploit_available": None,
                    "priority_reasons": [],
                }))
                risk["priority_reasons"] = explain_cve_priority(
                    risk, cvss_score=finding.get("cvss_score")
                )
                enriched.append(risk)
            enriched.sort(key=cve_risk_sort_key)
            finding["cve_ids"] = list(cves)
            finding["cve_risk"] = enriched
            finding["risk"] = enriched[0]
            finding["remediation_id"] = remediation_identity(finding, enriched[0]["cve_id"])
        return findings
    finally:
        if owns_connection:
            active.close()
