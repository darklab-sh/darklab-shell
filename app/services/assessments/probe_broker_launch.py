# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Ordinary brokered-run launch for one confirmed Project probe."""

from __future__ import annotations

from typing import Any, Callable

from services.assessments.http_profile_execution import ProtectedHttpLaunch
from services.assessments.probe_cleanup import best_effort_probe_cleanup
from services.assessments.probe_launch import probe_run_launch_context
from services.assessments.probe_protected_launch import materialize_probe_run_launch


def launch_confirmed_probe(
    plan: dict[str, Any],
    *,
    session_id: str,
    project_id: str,
    team_id: str,
    team_role: str,
    actor_member_id: str,
    client_ip: str,
    owner_client_id: str,
    owner_tab_id: str,
    workspace_cwd: str,
    handlers: Any,
    start_run: Callable[..., Any],
    thread_name_prefix: str,
):
    protected: ProtectedHttpLaunch | None = None
    try:
        protected, context = materialize_probe_run_launch(
            session_id, project_id, plan, launch_context=probe_run_launch_context,
            team_id=team_id, actor_member_id=actor_member_id,
        )
        started = start_run(
            original_command=protected.execution_command,
            display_command=plan["display_command"],
            session_id=session_id,
            team_id=team_id,
            team_role=team_role,
            client_ip=client_ip,
            handlers=handlers,
            owner_client_id=owner_client_id,
            owner_tab_id=owner_tab_id,
            workspace_cwd=workspace_cwd,
            link_project_id=project_id,
            private_values=protected.private_values,
            run_cleanup_hook=protected.cleanup,
            thread_name_prefix=thread_name_prefix,
            **context.broker_kwargs(),
        )
    except Exception:
        best_effort_probe_cleanup(protected.cleanup if protected else None)
        raise
    assert protected is not None
    return started, protected.audit_summary

__all__ = ["launch_confirmed_probe"]
