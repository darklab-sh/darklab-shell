# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared post-baseline tables owned by domain services."""

from services.assessments.schema import SHARED_TABLES as ASSESSMENT_TABLES
from services.cve_risk.schema import SHARED_TABLES as CVE_RISK_TABLES
from services.projects.finding_dispositions_schema import SHARED_TABLES as DISPOSITION_TABLES
from services.projects.finding_evidence_schema import SHARED_TABLES as FINDING_EVIDENCE_TABLES


SHARED_TABLES: tuple[str, ...] = (
    *ASSESSMENT_TABLES,
    *CVE_RISK_TABLES,
    *DISPOSITION_TABLES,
    *FINDING_EVIDENCE_TABLES,
)
