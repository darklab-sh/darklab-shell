# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable browser and API response for lifecycle-triggered batch cancellation."""

from __future__ import annotations

from flask import jsonify, request

from services.assessments.batch.lifecycle_guard import (
    BATCH_LIFECYCLE_PENDING_CODE,
    BATCH_LIFECYCLE_PENDING_MESSAGE,
    BatchLifecycleCancellation,
    signal_lifecycle_cancellation,
)


def batch_lifecycle_pending_response(
    pending: BatchLifecycleCancellation,
    session_id: str,
    *,
    team_id: str = "",
    api: bool = False,
    signal: bool = True,
):
    """Commit-safe signal plus one cross-surface conflict response."""
    if signal:
        signal_lifecycle_cancellation(pending, session_id, team_id=team_id)
    details = pending.public_details()
    if api:
        payload: dict[str, object] = {"error": {
            "code": BATCH_LIFECYCLE_PENDING_CODE,
            "message": BATCH_LIFECYCLE_PENDING_MESSAGE,
            "details": details,
        }}
    else:
        payload = {
            "error": BATCH_LIFECYCLE_PENDING_MESSAGE,
            "code": BATCH_LIFECYCLE_PENDING_CODE,
            **details,
        }
    return jsonify(payload), 409


def assessment_check_filters() -> dict[str, str]:
    """Return the shared browser/API assessment-check query filters."""
    return {
        "category": str(request.args.get("category") or ""),
        "state": str(request.args.get("state") or ""),
        "target_type": str(request.args.get("target_type") or ""),
        "policy_level": str(request.args.get("policy_level") or ""),
        "evidence_state": str(request.args.get("evidence_state") or ""),
    }


__all__ = ["assessment_check_filters", "batch_lifecycle_pending_response"]
