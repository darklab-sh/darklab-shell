# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compatibility exports for bounded assessment evidence readers."""

from __future__ import annotations

from services.assessments.assessment_evidence_previews import (
    attach_evidence_previews,
)
from services.assessments.assessment_evidence_recent import (
    recent_assessment_evidence,
)


__all__ = ["attach_evidence_previews", "recent_assessment_evidence"]
