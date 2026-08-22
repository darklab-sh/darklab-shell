# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Focused parser registration modules for the darklab CLI."""
from .assessment import register_assessment_parser
from .advisory import register_advisory_parser
from .evidence import register_evidence_parser
from .finding import register_finding_parser
from .probe import register_probe_parser
from .risk import register_risk_parser
__all__ = ["register_advisory_parser", "register_assessment_parser", "register_evidence_parser",
           "register_finding_parser", "register_probe_parser", "register_risk_parser"]
