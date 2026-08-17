# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reproducible public-risk snapshots for reports and evidence packages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from core.database_access import db_connection_scope
from .links import finding_cves
from .nvd_advisory import get_advisory_source_status
from .store import get_configured_feed_status


SNAPSHOT_SCHEMA_VERSION = 2
NON_ENDORSEMENT = (
    "FIRST, CISA, and NIST provide the source data and do not endorse darklab_shell "
    "or this assessment."
)
_CVE_RISK_SNAPSHOT_ROWS_SQL = (
    "SELECT * FROM cve_risk_records WHERE cve_id IN ({placeholders}) ORDER BY cve_id"
)


def _selected_cves(findings: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({cve_id for finding in findings for cve_id in finding_cves(finding)})


def build_cve_risk_snapshot(
    findings: Iterable[dict[str, Any]],
    conn: Any | None = None,
    *,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cve_ids = _selected_cves(findings)
    if not cve_ids:
        return {}
    with db_connection_scope(conn) as active:
        records: list[dict[str, Any]] = []
        for offset in range(0, len(cve_ids), 500):
            chunk = cve_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = active.execute(
                _CVE_RISK_SNAPSHOT_ROWS_SQL.format(placeholders=placeholders),
                tuple(chunk),
            ).fetchall()
            for row in rows:
                record = dict(row)
                record["kev_listed"] = bool(record.get("kev_listed"))
                records.append(record)
        persisted = {
            str(row["source"]): dict(row)
            for row in active.execute(
                "SELECT source, checksum_sha256 FROM cve_risk_sources ORDER BY source"
            ).fetchall()
        }
        sources = []
        for source in get_configured_feed_status(active, cfg=cfg):
            item = dict(source)
            item["checksum_sha256"] = str(
                persisted.get(str(item.get("source") or ""), {}).get("checksum_sha256") or ""
            )
            sources.append(item)
        nvd_source = get_advisory_source_status(active, cfg=cfg)
        if nvd_source.get("status") != "unavailable" or nvd_source.get("acquisition_mode") != "disabled":
            sources.append(nvd_source)
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cve_ids": cve_ids,
            "sources": sources,
            "records": records,
            "non_endorsement": NON_ENDORSEMENT,
        }
