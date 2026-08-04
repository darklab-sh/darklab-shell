# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Low-cardinality CVE risk feed and escalation metrics."""

from prometheus_client import Counter, Gauge


CVE_RISK_REFRESHES = Counter(
    "darklab_cve_risk_refreshes_total",
    "CVE risk feed refresh attempts",
    ("source", "outcome"),
)
CVE_RISK_RECORDS = Gauge(
    "darklab_cve_risk_records",
    "Records in the last accepted CVE risk feed",
    ("source",),
)
CVE_RISK_FEED_AGE_SECONDS = Gauge(
    "darklab_cve_risk_feed_age_seconds",
    "Age of the accepted CVE risk feed",
    ("source",),
)
CVE_RISK_WORK_ITEMS = Counter(
    "darklab_cve_risk_work_items_total",
    "Changed-CVE work item outcomes",
    ("source", "outcome"),
)
RISK_ESCALATIONS_CREATED = Counter(
    "darklab_risk_escalations_created_total",
    "Owner-scoped risk escalation events",
    ("source", "transition"),
)
CVE_ADVISORY_ACQUISITIONS = Counter(
    "darklab_cve_advisory_acquisitions_total",
    "Normalized CVE advisory acquisition outcomes",
    ("source", "mode", "outcome"),
)
