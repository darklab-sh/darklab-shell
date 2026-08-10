# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Provider-free preview confirmation and public private-OAST state."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import re
from typing import Any

from core.database_access import get_db_connect
from services.assessments.dalfox_oast_contracts import (
    DALFOX_OAST_ACTION_KEY,
    DALFOX_OAST_VALIDATION_CHECK_KEY,
)
from services.assessments.recommended_actions import get_recommended_action_plan
from services.assessments.recommended_action_queries import load_action_row
from services.connectors.oast_config import oast_connector_settings
from services.connectors.oast_correlations import (
    OastCorrelationError,
    oast_correlation_for_owner,
    oast_correlations_for_owner_check,
    reserve_oast_correlation,
)
from services.connectors.oast_provider_spool import (
    OastProviderSessionSpoolError,
    oast_provider_session_is_staged,
)


_PLAN_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_RESERVATION_FIELDS = frozenset({
    "confirmed",
    "parameter_observation_id",
    "plan_digest",
    "source_run_id",
})
_LIVE_STATUSES = frozenset({"reserved", "active"})


class AssessmentOastError(ValueError):
    """A stable private-OAST assessment route error."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _oast_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str,
    actor_member_id: str = "",
    evidence_selection: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    plan = get_recommended_action_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        team_id=team_id,
        actor_member_id=actor_member_id,
        evidence_selection=evidence_selection,
    )
    if (
        str(plan.get("check_key") or "") != DALFOX_OAST_VALIDATION_CHECK_KEY
        or str((plan.get("action") or {}).get("key") or "")
        != DALFOX_OAST_ACTION_KEY
    ):
        raise AssessmentOastError(
            "oast_action_not_found",
            "Private OAST validation is not available for this assessment check.",
            status_code=404,
        )
    return plan


def _assert_oast_check_scope(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str,
) -> None:
    with get_db_connect()() as conn:
        row = load_action_row(
            conn,
            session_id,
            team_id,
            project_id,
            assessment_id,
            check_id,
        )
    if (
        str(row["check_key"] or "") != DALFOX_OAST_VALIDATION_CHECK_KEY
        or str(row["recommended_action_key"] or "") != DALFOX_OAST_ACTION_KEY
    ):
        raise AssessmentOastError(
            "oast_action_not_found",
            "Private OAST validation is not available for this assessment check.",
            status_code=404,
        )


def _confirmed_oast_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    data: Any,
    *,
    team_id: str,
    actor_member_id: str,
) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise AssessmentOastError(
            "invalid_body",
            "Request body must be a JSON object.",
        )
    if set(data) - _RESERVATION_FIELDS:
        raise AssessmentOastError(
            "unsupported_fields",
            "Private OAST reservation contains unsupported fields.",
        )
    if data.get("confirmed") is not True:
        raise AssessmentOastError(
            "confirmation_required",
            "Explicit private OAST reservation confirmation is required.",
            status_code=409,
        )
    supplied_digest = str(data.get("plan_digest") or "").strip()
    if not _PLAN_DIGEST_RE.fullmatch(supplied_digest):
        raise AssessmentOastError(
            "plan_digest_required",
            "The private OAST plan digest is required.",
        )
    selection = {
        key: str(data.get(key) or "").strip()
        for key in ("source_run_id", "parameter_observation_id")
    }
    plan = _oast_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        team_id=team_id,
        actor_member_id=actor_member_id,
        evidence_selection=selection,
    )
    if supplied_digest != str(plan.get("plan_digest") or ""):
        raise AssessmentOastError(
            "stale_plan",
            "The private OAST plan changed. Review it and confirm again.",
            status_code=409,
        )
    oast = plan.get("oast")
    if not isinstance(oast, Mapping) or oast.get("preparable") is not True:
        raise AssessmentOastError(
            "oast_action_unavailable",
            str(plan.get("unavailable_reason") or "Private OAST is unavailable."),
            status_code=409,
        )
    return plan


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value or "").strip()
    return text or None


def _provider_ready(correlation: Mapping[str, Any]) -> bool:
    if str(correlation.get("status") or "") not in _LIVE_STATUSES:
        return False
    try:
        return oast_provider_session_is_staged(str(correlation.get("id") or ""))
    except OastProviderSessionSpoolError:
        return False


def _public_correlation(
    correlation: Mapping[str, Any],
    *,
    reveal_ready_callback: bool,
) -> dict[str, Any]:
    ready = _provider_ready(correlation)
    callback_url = "https://[private-oast-callback]"
    if ready and reveal_ready_callback:
        callback_url = f"https://{str(correlation.get('callback_domain') or '')}"
    return {
        "id": str(correlation.get("id") or ""),
        "project_id": str(correlation.get("project_id") or ""),
        "assessment_id": str(correlation.get("assessment_id") or ""),
        "check_id": str(correlation.get("check_id") or ""),
        "action_key": str(correlation.get("action_key") or ""),
        "run_id": str(correlation.get("run_id") or ""),
        "status": str(correlation.get("status") or ""),
        "provider_ready": ready,
        "callback_url": callback_url,
        "interaction_count": int(correlation.get("interaction_count") or 0),
        "duplicate_count": int(correlation.get("duplicate_count") or 0),
        "rejected_count": int(correlation.get("rejected_count") or 0),
        "error_code": str(correlation.get("error_code") or ""),
        "created_at": _timestamp(correlation.get("created_at")),
        "updated_at": _timestamp(correlation.get("updated_at")),
        "activated_at": _timestamp(correlation.get("activated_at")),
        "closed_at": _timestamp(correlation.get("closed_at")),
        "active_until": _timestamp(correlation.get("active_until")),
        "purge_at": _timestamp(correlation.get("purge_at")),
    }


def reserve_assessment_oast(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    data: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
) -> dict[str, Any]:
    """Confirm the current redacted plan and reserve one callback identity."""
    plan = _confirmed_oast_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        data,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    oast = plan["oast"]
    try:
        correlation = reserve_oast_correlation(
            session_id,
            project_id,
            assessment_id,
            check_id,
            DALFOX_OAST_ACTION_KEY,
            oast_connector_settings(),
            team_id=team_id,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            window_seconds=int(oast["reservation_window_seconds"]),
        )
    except OastCorrelationError as exc:
        raise AssessmentOastError(
            exc.code,
            str(exc),
            status_code=409,
        ) from exc
    return _public_correlation(correlation, reveal_ready_callback=False)


def list_assessment_oast_correlations(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str = "",
) -> list[dict[str, Any]]:
    """Return bounded newest-first recovery state for one exact OAST check."""
    _assert_oast_check_scope(
        session_id,
        project_id,
        assessment_id,
        check_id,
        team_id=team_id,
    )
    rows = oast_correlations_for_owner_check(
        session_id,
        project_id,
        assessment_id,
        check_id,
        team_id=team_id,
        limit=10,
    )
    return [
        _public_correlation(row, reveal_ready_callback=False)
        for row in rows
    ]


def get_assessment_oast_correlation(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    correlation_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return exact nested status and reveal only a staged callback identity."""
    row = oast_correlation_for_owner(
        session_id,
        str(correlation_id or "").strip(),
        team_id=team_id,
    )
    if row is None or any(
        str(row.get(key) or "") != expected
        for key, expected in (
            ("project_id", project_id),
            ("assessment_id", assessment_id),
            ("check_id", check_id),
        )
    ):
        raise AssessmentOastError(
            "oast_correlation_not_found",
            "Private OAST correlation not found.",
            status_code=404,
        )
    return _public_correlation(row, reveal_ready_callback=True)


__all__ = [
    "AssessmentOastError",
    "get_assessment_oast_correlation",
    "list_assessment_oast_correlations",
    "reserve_assessment_oast",
]
