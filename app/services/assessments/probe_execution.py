# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared confirmed launch service for Project-scoped probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from services.assessments.probe_confirmation import confirm_project_probe_plan
from services.assessments.probe_broker_launch import launch_confirmed_probe
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_log_context import ProbeLogContext
from services.assessments.probe_observability import observe_probe


@dataclass(frozen=True)
class ProbeExecutionResult:
    """A freshly confirmed plan and its ordinary brokered run."""

    plan: dict[str, Any]
    started: Any
    audit_summary: dict[str, Any]


@observe_probe("launch")
def start_project_probe(
    session_id: str,
    project_id: str,
    probe_request: ProbePlanRequest,
    confirmation: Mapping[str, Any],
    *,
    team_id: str = "",
    team_role: str = "",
    actor_member_id: str = "",
    client_ip: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
    workspace_cwd: str = "",
    handlers: Any,
    start_run: Callable[..., Any],
    broker_available: Callable[[], bool] = lambda: True,
    broker_unavailable_reason: Callable[[], str] = lambda: "Run broker unavailable.",
    thread_name_prefix: str = "probe-run-broker",
    observability: ProbeLogContext | None = None,
) -> ProbeExecutionResult:
    """Rebuild, confirm, and start one explicit Project-bound ordinary run."""
    plan = confirm_project_probe_plan(
        session_id, project_id, probe_request,
        confirmation,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    if not broker_available():
        raise ProbeError(
            "broker_unavailable",
            broker_unavailable_reason(),
            status_code=503,
        )
    started, audit_summary = launch_confirmed_probe(
        plan,
        session_id=session_id,
        project_id=project_id,
        team_id=team_id,
        team_role=team_role,
        actor_member_id=actor_member_id,
        client_ip=client_ip,
        owner_client_id=owner_client_id,
        owner_tab_id=owner_tab_id,
        workspace_cwd=workspace_cwd,
        handlers=handlers,
        start_run=start_run,
        thread_name_prefix=thread_name_prefix,
    )
    return ProbeExecutionResult(plan=plan, started=started, audit_summary=audit_summary)

__all__ = ["ProbeExecutionResult", "start_project_probe"]
