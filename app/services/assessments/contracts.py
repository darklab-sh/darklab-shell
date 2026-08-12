# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Permission-neutral Project assessment service contracts."""

from __future__ import annotations

from services.projects.contracts import ProjectWorkspaceError


ASSESSMENT_STATUSES = frozenset({"active", "completed", "archived"})
ASSESSMENT_CHECK_STATES = frozenset({
    "not_started",
    "running",
    "covered",
    "needs_review",
    "failed",
    "blocked",
    "skipped",
    "not_applicable",
})
ASSESSMENT_APPLICABILITY_STATES = frozenset({"applicable", "not_applicable", "unknown"})
ASSESSMENT_POLICY_LEVELS = frozenset({"safe", "standard", "intrusive", "destructive"})
ASSESSMENT_EVIDENCE_STATES = frozenset({"available", "unavailable"})
ASSESSMENT_MANUAL_CHECK_STATES = frozenset({
    "not_started",
    "blocked",
    "skipped",
    "not_applicable",
})

ASSESSMENT_MAX_TITLE_LEN = 120
ASSESSMENT_MAX_FILTER_LEN = 128
ASSESSMENT_MAX_REASON_LEN = 1000
ASSESSMENT_MAX_EVIDENCE_ID_LEN = 512
ASSESSMENT_PAGE_MAX = 200


class AssessmentError(ProjectWorkspaceError):
    """Raised when an assessment service request is invalid."""


class AssessmentNotFound(AssessmentError):
    """Raised when an assessment or its Project is outside the active scope."""


class AssessmentConflict(AssessmentError):
    """Raised when an assessment lifecycle invariant rejects a mutation."""
