# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reproducible public-risk snapshots for reports and evidence packages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from core.database_access import get_db_connect
from .links import finding_cves
from .store import get_configured_feed_status


SNAPSHOT_SCHEMA_VERSION = 1
NON_ENDORSEMENT = (
    "FIRST and CISA provide the source data and do not endorse darklab_shell "
    "or this assessment."
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
    owns_connection = conn is None
    active = conn or get_db_connect()()
    try:
        records: list[dict[str, Any]] = []
        for offset in range(0, len(cve_ids), 500):
            chunk = cve_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = active.execute(
                f"SELECT * FROM cve_risk_records WHERE cve_id IN ({placeholders}) "  # nosec B608
                "ORDER BY cve_id",
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
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cve_ids": cve_ids,
            "sources": sources,
            "records": records,
            "non_endorsement": NON_ENDORSEMENT,
        }
    finally:
        if owns_connection:
            active.close()
