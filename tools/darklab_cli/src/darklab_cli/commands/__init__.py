# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Focused command handlers for the darklab CLI."""

from .assessment import handle_assessment
from .advisory import handle_advisory
from .evidence import handle_evidence
from .probe import handle_probe
from .risk import handle_risk

__all__ = ["handle_advisory", "handle_assessment", "handle_evidence", "handle_probe", "handle_risk"]
