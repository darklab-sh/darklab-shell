# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable queue boundary for reviewed ZAP plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.connectors.zap_job_artifacts import (
    discard_zap_job_plan,
    store_zap_job_plan,
)
from services.connectors.zap_jobs import create_zap_job, new_zap_job_id
from services.connectors.zap_plan_contracts import ReviewedZapAutomationPlan


def queue_zap_job(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    http_profile_id: str,
    http_profile_revision: int,
    plan: ReviewedZapAutomationPlan,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    cfg: Mapping[str, Any] | None = None,
    conn=None,
) -> dict[str, Any]:
    """Durably queue exactly the reviewed plan before a worker can claim it."""
    job_id = new_zap_job_id()
    store_zap_job_plan(job_id, plan, cfg)
    try:
        return create_zap_job(
            session_id,
            project_id,
            assessment_id,
            check_id,
            http_profile_id,
            http_profile_revision,
            plan.summary,
            job_id=job_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            conn=conn,
        )
    except Exception:
        discard_zap_job_plan(job_id, cfg)
        raise


__all__ = ["queue_zap_job"]
