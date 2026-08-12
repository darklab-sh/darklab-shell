# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fresh confirmation and run binding for one private-OAST reservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.assessments.assessment_oast import (
    AssessmentOastError,
    assessment_oast_provider_ready,
    confirmed_assessment_oast_plan,
)
from services.assessments.dalfox_oast_contracts import DALFOX_OAST_ACTION_KEY
from services.connectors.oast_config import oast_connector_settings
from services.connectors.oast_correlation_lifecycle import activate_oast_correlation
from services.connectors.oast_correlations import (
    OastCorrelationError,
    oast_correlation_for_owner,
)


_LAUNCH_FIELDS = frozenset({
    "confirmed",
    "http_profile_id",
    "parameter_observation_id",
    "plan_digest",
    "source_run_id",
    "workspace_cwd",
})


@dataclass(frozen=True)
class ConfirmedAssessmentOastLaunch:
    """One redacted plan paired with a private ready callback identity."""

    plan: dict[str, Any]
    correlation_id: str
    callback_url: str = field(repr=False)
    callback_host: str = field(repr=False)


def _deadline(value: object) -> datetime:
    try:
        deadline = datetime.fromisoformat(str(value or ""))
    except ValueError as exc:
        raise AssessmentOastError(
            "oast_correlation_unavailable",
            "The private OAST reservation is unavailable.",
            status_code=409,
        ) from exc
    if deadline.tzinfo is None:
        raise AssessmentOastError(
            "oast_correlation_unavailable",
            "The private OAST reservation is unavailable.",
            status_code=409,
        )
    return deadline.astimezone(timezone.utc)


def _launchable_correlation(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    correlation_id: str,
    *,
    team_id: str,
) -> dict[str, Any]:
    correlation = oast_correlation_for_owner(
        session_id,
        str(correlation_id or "").strip(),
        team_id=team_id,
    )
    if correlation is None or any(
        str(correlation.get(key) or "") != expected
        for key, expected in (
            ("project_id", project_id),
            ("assessment_id", assessment_id),
            ("check_id", check_id),
            ("action_key", DALFOX_OAST_ACTION_KEY),
        )
    ):
        raise AssessmentOastError(
            "oast_correlation_not_found",
            "Private OAST correlation not found.",
            status_code=404,
        )
    if (
        str(correlation.get("status") or "") != "reserved"
        or str(correlation.get("run_id") or "")
        or _deadline(correlation.get("active_until")) <= datetime.now(timezone.utc)
    ):
        raise AssessmentOastError(
            "oast_correlation_unavailable",
            "The private OAST reservation is no longer available for launch.",
            status_code=409,
        )
    settings = oast_connector_settings()
    origin_digest = sha256(settings.base_url.encode("utf-8")).hexdigest()
    if (
        not settings.enabled
        or not settings.privacy_acknowledged
        or settings.allowed_domain != str(correlation.get("allowed_domain") or "")
        or origin_digest != str(correlation.get("service_origin_sha256") or "")
    ):
        raise AssessmentOastError(
            "oast_provider_scope_changed",
            "The private OAST provider scope changed. Prepare a new callback.",
            status_code=409,
        )
    if not assessment_oast_provider_ready(correlation):
        raise AssessmentOastError(
            "oast_provider_not_ready",
            "The private OAST callback is still being prepared.",
            status_code=409,
        )
    return correlation


def confirm_assessment_oast_launch(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    correlation_id: str,
    data: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> ConfirmedAssessmentOastLaunch:
    """Rebuild the plan and require one exact ready reservation."""
    plan = confirmed_assessment_oast_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        data,
        team_id=team_id,
        actor_member_id=actor_member_id,
        allowed_fields=_LAUNCH_FIELDS,
    )
    correlation = _launchable_correlation(
        session_id,
        project_id,
        assessment_id,
        check_id,
        correlation_id,
        team_id=team_id,
    )
    callback_host = str(correlation.get("callback_domain") or "")
    return ConfirmedAssessmentOastLaunch(
        plan,
        str(correlation.get("id") or ""),
        f"https://{callback_host}",
        callback_host,
    )


def activate_assessment_oast_run(
    launch: ConfirmedAssessmentOastLaunch,
    session_id: str,
    run_id: str,
    *,
    team_id: str = "",
) -> None:
    """Recheck readiness and bind the correlation to the broker-created run."""
    plan = launch.plan
    _launchable_correlation(
        session_id,
        str(plan.get("project_id") or ""),
        str(plan.get("assessment_id") or ""),
        str(plan.get("check_id") or ""),
        launch.correlation_id,
        team_id=team_id,
    )
    try:
        activate_oast_correlation(
            session_id,
            launch.correlation_id,
            run_id,
            team_id=team_id,
        )
    except OastCorrelationError as exc:
        raise AssessmentOastError(exc.code, str(exc), status_code=409) from exc


__all__ = [
    "ConfirmedAssessmentOastLaunch",
    "activate_assessment_oast_run",
    "confirm_assessment_oast_launch",
]
