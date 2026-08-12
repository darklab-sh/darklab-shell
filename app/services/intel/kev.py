# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalization for the CISA Known Exploited Vulnerabilities catalog."""

from __future__ import annotations

from typing import Any

from services.intel.canonical import CanonicalizationError, canonical_cve

MAX_KEV_ROWS = 4096


def normalize_kev_catalog(raw: object) -> list[dict[str, Any]]:
    """Parse bounded CISA KEV JSON records without trusting arbitrary fields."""
    payload = raw if isinstance(raw, dict) else {}
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        return []
    result: list[dict[str, Any]] = []
    for item in vulnerabilities[:MAX_KEV_ROWS]:
        if not isinstance(item, dict):
            continue
        try:
            cve = canonical_cve(str(item.get("cveID") or ""))
        except CanonicalizationError:
            continue
        if not cve:
            continue
        result.append({
            "cve": cve,
            "vendor": str(item.get("vendorProject") or "")[:160],
            "product": str(item.get("product") or "")[:160],
            "name": str(item.get("vulnerabilityName") or "")[:240],
            "date_added": str(item.get("dateAdded") or "")[:32],
            "due_date": str(item.get("dueDate") or "")[:32],
            "known_ransomware_use": str(item.get("knownRansomwareCampaignUse") or "Unknown")[:16],
        })
    return result
