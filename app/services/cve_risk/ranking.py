# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explainable CVE enrichment and deterministic fix-first ordering."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping

from core.database_access import get_db_connect
from .links import (
    canonical_affected_subject,
    finding_cves,
    finding_evidence_keys,
    finding_priority_context,
    finding_validation_method,
    owner_scope_key,
    remediation_identity,
)
from .nvd_advisory import get_advisory_source_status
from .store import get_configured_feed_status


_SQL_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_EPSS_MAX_SQL = (
    "(SELECT MAX(risk_order_record.epss_probability) "
    "FROM finding_cve_links risk_order_link "
    "JOIN cve_risk_records risk_order_record "
    "ON risk_order_record.cve_id = risk_order_link.cve_id "
    "WHERE risk_order_link.finding_id = {finding_id})"
)
_PERCENTILE_MAX_SQL = (
    "(SELECT MAX(risk_order_record.epss_percentile) "
    "FROM finding_cve_links risk_order_link "
    "JOIN cve_risk_records risk_order_record "
    "ON risk_order_record.cve_id = risk_order_link.cve_id "
    "WHERE risk_order_link.finding_id = {finding_id})"
)
_CVSS_MAX_SQL = (
    "(SELECT MAX(risk_order_record.cvss_score) "
    "FROM finding_cve_links risk_order_link "
    "JOIN cve_risk_records risk_order_record "
    "ON risk_order_record.cve_id = risk_order_link.cve_id "
    "WHERE risk_order_link.finding_id = {finding_id})"
)
_RISK_ORDER_SQL = (
    "CASE WHEN EXISTS (SELECT 1 FROM finding_cve_links risk_order_link "
    "JOIN cve_risk_records risk_order_record "
    "ON risk_order_record.cve_id = risk_order_link.cve_id "
    "WHERE risk_order_link.finding_id = {finding_id} "
    "AND risk_order_record.kev_listed = TRUE) THEN 0 ELSE 1 END, "
    "CASE WHEN {epss_max} IS NULL THEN 1 ELSE 0 END, {epss_max} DESC, "
    "CASE WHEN {percentile_max} IS NULL THEN 1 ELSE 0 END, {percentile_max} DESC, "
    "CASE WHEN {cvss_max} IS NULL THEN 1 ELSE 0 END, {cvss_max} DESC, "
    "{age_expression} DESC, {finding_id} DESC"
)
_CVE_RISK_ROWS_SQL = "SELECT * FROM cve_risk_records WHERE cve_id IN ({placeholders})"


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nvd_freshness(row: dict[str, Any], advisory_source: dict[str, Any]) -> str:
    source_status = str(advisory_source.get("status") or "unavailable")
    if source_status in {"failed", "unavailable"}:
        return source_status
    if str(row.get("nvd_origin") or "unavailable") == "unavailable":
        return "unavailable"
    expires_at = str(row.get("nvd_expires_at") or "")
    if expires_at:
        try:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                return "stale"
        except ValueError:
            return "stale"
    return source_status


def _risk_payload(
    row: dict[str, Any],
    *,
    feed_status: dict[str, dict[str, Any]],
    advisory_source: dict[str, Any],
) -> dict[str, Any]:
    epss = feed_status.get("epss", {})
    kev = feed_status.get("kev", {})
    raw_cwes = row.get("cwe_ids_json")
    try:
        cwes = json.loads(str(raw_cwes or "[]"))
    except json.JSONDecodeError:
        cwes = []
    nvd_freshness = _nvd_freshness(row, advisory_source)
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
        "advisory_status": str(row.get("advisory_status") or "unknown"),
        "cvss": {
            "version": str(row.get("cvss_version") or ""),
            "vector": str(row.get("cvss_vector") or ""),
            "score": _number(row.get("cvss_score")),
            "severity": str(row.get("cvss_severity") or ""),
            "cwes": cwes if isinstance(cwes, list) else [],
            "source": "nvd",
            "source_version": str(row.get("nvd_source_version") or ""),
            "published_at": str(row.get("nvd_published_at") or ""),
            "modified_at": str(row.get("nvd_modified_at") or ""),
            "fetched_at": str(row.get("nvd_fetched_at") or ""),
            "expires_at": str(row.get("nvd_expires_at") or ""),
            "origin": str(row.get("nvd_origin") or "unavailable"),
            "freshness": nvd_freshness,
        },
        "public_exploit_available": None,
        "priority_reasons": [],
    }


def explain_cve_priority(risk: dict[str, Any], *, cvss_score: Any = None) -> list[str]:
    reasons: list[str] = []
    kev = _dict_value(risk.get("kev"))
    epss = _dict_value(risk.get("epss"))
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
    stored_cvss = _dict_value(risk.get("cvss"))
    cvss = _number(cvss_score)
    if cvss is None:
        cvss = _number(stored_cvss.get("score"))
    if cvss is not None:
        reasons.append(f"CVSS {cvss:.1f}")
    status = str(risk.get("advisory_status") or "unknown")
    if status in {"disputed", "rejected", "withdrawn"}:
        reasons.append(f"NVD status: {status}")
    return reasons


def cve_risk_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    risk = _dict_value(item.get("risk")) or item
    kev = _dict_value(risk.get("kev"))
    epss = _dict_value(risk.get("epss"))
    probability = _number(epss.get("probability"))
    percentile = _number(epss.get("percentile"))
    cvss_signal = _dict_value(risk.get("cvss"))
    cvss = _number(item.get("cvss_score"))
    if cvss is None:
        cvss = _number(cvss_signal.get("score"))
    return (
        0 if bool(kev.get("listed")) else 1,
        1 if probability is None else 0,
        -(probability or 0.0),
        1 if percentile is None else 0,
        -(percentile or 0.0),
        1 if cvss is None else 0,
        -(cvss or 0.0),
    )


def _sort_by_cve_risk(items: list[dict[str, Any]]) -> None:
    """Apply public-risk ordering with newest and id descending as tie-breakers."""
    items.sort(key=lambda item: (
        str(item.get("first_seen_at") or item.get("created") or ""),
        str(
            item.get("remediation_id")
            or item.get("id")
            or _dict_value(item.get("risk")).get("cve_id")
            or item.get("cve_id")
            or ""
        ),
    ), reverse=True)
    items.sort(key=cve_risk_sort_key)


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
    # The identifier and age expression are restricted to the allowlist above.
    finding_id = f"{alias}.id"
    epss_max = _EPSS_MAX_SQL.format(finding_id=finding_id)
    percentile_max = _PERCENTILE_MAX_SQL.format(finding_id=finding_id)
    cvss_max = _CVSS_MAX_SQL.format(finding_id=finding_id)
    return _RISK_ORDER_SQL.format(
        finding_id=finding_id,
        epss_max=epss_max,
        percentile_max=percentile_max,
        cvss_max=cvss_max,
        age_expression=age_expression,
    )


def _finding_with_owner(
    finding: dict[str, Any],
    *,
    owner_by_finding_id: Mapping[str, tuple[str, str]] | None,
) -> dict[str, Any]:
    if not owner_by_finding_id:
        return finding
    owner = owner_by_finding_id.get(str(finding.get("id") or ""))
    if owner is None:
        return finding
    return {**finding, "session_id": owner[0], "team_id": owner[1]}


def attach_risk_to_findings(
    findings: list[dict[str, Any]],
    conn: Any | None = None,
    *,
    owner_by_finding_id: Mapping[str, tuple[str, str]] | None = None,
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
                _CVE_RISK_ROWS_SQL.format(placeholders=placeholders),
                tuple(chunk),
            ).fetchall())
        feed_status = {item["source"]: item for item in get_configured_feed_status(active)}
        advisory_source = get_advisory_source_status(active)
        risk_by_cve = {
            str(row["cve_id"]): _risk_payload(
                dict(row),
                feed_status=feed_status,
                advisory_source=advisory_source,
            )
            for row in rows
        }
        for finding in findings:
            finding_id = str(finding.get("id") or "")
            identity_finding = _finding_with_owner(
                finding,
                owner_by_finding_id=owner_by_finding_id,
            )
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
                    "advisory_status": "unknown",
                    "cvss": {
                        "score": None,
                        "severity": "",
                        "cwes": [],
                        "freshness": "unavailable",
                    },
                    "public_exploit_available": None,
                    "priority_reasons": [],
                }))
                risk["priority_reasons"] = explain_cve_priority(
                    risk, cvss_score=finding.get("cvss_score")
                )
                enriched.append(risk)
            _sort_by_cve_risk(enriched)
            remediation_groups = [{
                "remediation_id": remediation_identity(identity_finding, cve_id),
                "vulnerability_id": cve_id,
                "affected_subject": canonical_affected_subject(identity_finding),
            } for cve_id in cves]
            finding["cve_ids"] = list(cves)
            finding["cve_risk"] = enriched
            finding["risk"] = enriched[0]
            finding["remediation_groups"] = remediation_groups
            primary_cve_id = str(enriched[0].get("cve_id") or "")
            finding["remediation_id"] = next(
                reference["remediation_id"]
                for reference in remediation_groups
                if reference["vulnerability_id"] == primary_cve_id
            )
            finding["priority_context"] = finding_priority_context(finding)
        return findings
    finally:
        if owns_connection:
            active.close()


def _aggregate_priority_context(observations: list[dict[str, Any]]) -> dict[str, Any]:
    confidence: list[Any] = []
    exposures: list[Any] = []
    assets: list[dict[str, str]] = []
    asset_keys: set[str] = set()
    for observation in observations:
        context = finding_priority_context(observation)
        confidence_value = context.get("confidence")
        if confidence_value is not None and confidence_value not in confidence:
            confidence.append(confidence_value)
        exposure_value = context.get("exposure")
        if exposure_value is not None and exposure_value not in exposures:
            exposures.append(exposure_value)
        asset = context.get("asset") if isinstance(context.get("asset"), dict) else {}
        if asset:
            asset_key = json.dumps(asset, sort_keys=True, separators=(",", ":"))
            if asset_key not in asset_keys:
                asset_keys.add(asset_key)
                assets.append(asset)
    confidence_order = {"confirmed": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    confidence.sort(key=lambda value: (
        confidence_order.get(str(value).strip().lower(), 5),
        str(value).lower(),
    ))
    exposures.sort(key=lambda value: str(value).lower())
    assets.sort(key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")))
    return {"confidence": confidence, "exposure": exposures, "assets": assets}


def build_remediation_worklist(
    findings: list[dict[str, Any]],
    conn: Any | None = None,
    *,
    owner_by_finding_id: Mapping[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Collapse scoped observations into one deterministic fix-first row."""
    attach_risk_to_findings(
        findings,
        conn=conn,
        owner_by_finding_id=owner_by_finding_id,
    )
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for finding in findings:
        if bool(finding.get("suppressed")):
            continue
        review_state = str(
            finding.get("review_state") or finding.get("status") or "new"
        ).strip().lower()
        if review_state in {"false_positive", "resolved"}:
            continue
        identity_finding = _finding_with_owner(
            finding,
            owner_by_finding_id=owner_by_finding_id,
        )
        session_id, team_id = owner_scope_key(identity_finding)
        risk_by_cve = {
            str(item.get("cve_id") or ""): item
            for item in finding.get("cve_risk", [])
            if isinstance(item, dict)
        }
        for reference in finding.get("remediation_groups", []):
            if not isinstance(reference, dict):
                continue
            remediation_id = str(reference.get("remediation_id") or "")
            vulnerability_id = str(reference.get("vulnerability_id") or "")
            if not remediation_id or not vulnerability_id:
                continue
            key = (session_id, team_id, remediation_id)
            group = grouped.setdefault(key, {
                "remediation_id": remediation_id,
                "vulnerability_id": vulnerability_id,
                "affected_subject": str(reference.get("affected_subject") or ""),
                "observations": [],
                "evidence_keys": set(),
                "validation_methods": set(),
            })
            observation = dict(finding)
            observation["risk"] = risk_by_cve.get(vulnerability_id, finding.get("risk"))
            group["observations"].append(observation)
            group["evidence_keys"].update(finding_evidence_keys(finding))
            group["validation_methods"].add(finding_validation_method(finding))

    worklist: list[dict[str, Any]] = []
    for group in grouped.values():
        observations = group.pop("observations")
        evidence_keys = group.pop("evidence_keys")
        validation_methods = group.pop("validation_methods")
        _sort_by_cve_risk(observations)
        representative = observations[0]
        observed_times = [
            str(item.get("first_seen_at") or item.get("created") or "")
            for item in observations
            if str(item.get("first_seen_at") or item.get("created") or "")
        ]
        worklist.append({
            **group,
            "representative_finding_id": str(representative.get("id") or ""),
            "observation_count": len(observations),
            "evidence_count": len(evidence_keys),
            "validation_methods": sorted(validation_methods),
            "priority_context": _aggregate_priority_context(observations),
            "risk": representative.get("risk"),
            "first_seen_at": min(observed_times) if observed_times else "",
        })
    _sort_by_cve_risk(worklist)
    return worklist
