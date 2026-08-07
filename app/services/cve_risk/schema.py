# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared table inventory for CVE risk intelligence."""

SHARED_TABLES: tuple[str, ...] = (
    "cve_advisory_cpe_matches",
    "cve_advisory_lookup_cache",
    "cve_advisory_sources",
    "cve_risk_records",
    "cve_risk_refresh_leases",
    "cve_risk_sources",
    "cve_risk_work_items",
    "finding_cve_links",
    "package_advisories",
    "package_advisory_ranges",
    "risk_escalation_observations",
    "risk_escalation_projects",
    "risk_escalation_states",
    "risk_escalations",
)
