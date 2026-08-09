# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only Assessment suggestions from saved, explicit service evidence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping

from services.atlas.observations import app_ports_by_host, public_app_port_record


SERVICE_RECOMMENDATION_MAX_ACTIONS = 12


def attach_service_action_recommendations(
    conn: Any,
    checks: list[dict[str, Any]],
    *,
    session_id: str,
    team_id: str,
    project_id: str,
) -> None:
    """Attach bounded suggestions without changing checks or launching actions."""
    targets = {
        str(check.get("target_entity_id") or ""): {
            "type": str(check.get("target_type") or ""),
            "value": str(check.get("target_value") or ""),
        }
        for check in checks
        if str(check.get("target_entity_id") or "")
        and str(check.get("target_type") or "") in {"domain", "ip"}
    }
    if not targets:
        return
    ports_by_target = app_ports_by_host(
        conn,
        session_id,
        team_id,
        project_id,
        list(targets),
        log_context={"project_id": project_id, "surface": "assessment"},
        log_event_namespace="ASSESSMENT_SERVICE_ACTION",
    )
    resolved = {
        target_id: _target_recommendations(
            ports_by_target.get(target_id, []),
            target_type=str(target["type"]),
        )
        for target_id, target in targets.items()
    }
    for check in checks:
        recommendation = resolved.get(str(check.get("target_entity_id") or ""))
        if recommendation and recommendation["evidence_count"]:
            check["service_action_recommendations"] = recommendation


def _target_recommendations(
    ports: Sequence[Mapping[str, Any]],
    *,
    target_type: str,
) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []
    needs_review_count = 0
    unsupported_count = 0
    action_limit_reached = False
    project_ports = [port for port in ports if bool(port.get("_project_linked"))]
    total_count = max(
        [len(project_ports)]
        + [int(port.get("_host_total_count") or 0) for port in project_ports]
    )
    for index, port in enumerate(project_ports):
        public = public_app_port_record(port)
        state = str(public.get("service_evidence_state") or "needs_review")
        if state == "needs_review":
            needs_review_count += 1
            continue
        if state == "unsupported":
            unsupported_count += 1
            continue
        for action in public.get("assessment_actions", []):
            if target_type not in set(action.get("target_types", [])):
                continue
            suggestions.append({
                **dict(action),
                "service": str(public.get("service") or ""),
                "port": int(public.get("port") or 0),
                "proto": str(public.get("proto") or ""),
                "version": str(public.get("version") or ""),
                "launch_mode": "assessment_action_only",
                "auto_launch": False,
            })
            if len(suggestions) >= SERVICE_RECOMMENDATION_MAX_ACTIONS:
                action_limit_reached = index < len(project_ports) - 1
                break
        if len(suggestions) >= SERVICE_RECOMMENDATION_MAX_ACTIONS:
            break
    return {
        "actions": suggestions,
        "action_count": len(suggestions),
        "evidence_count": len(project_ports),
        "needs_review_count": needs_review_count,
        "unsupported_count": unsupported_count,
        "source_truncated": (
            total_count > len(project_ports)
            or action_limit_reached
        ),
        "launch_mode": "assessment_action_only",
        "auto_launch": False,
    }


__all__ = ["attach_service_action_recommendations"]
