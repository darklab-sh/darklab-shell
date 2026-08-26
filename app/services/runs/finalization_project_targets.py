# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Best-effort Project target discovery during completed-run finalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import logging
from typing import Any, Callable

import config as app_config
from core.helpers import get_log_session_id
from core.output_targets import command_root
from services.commands.registry import command_project_target_inputs
from services.commands.registry_target_parsing import DNS_COMMAND_ROOTS
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.targets import record_project_target_discoveries
from services.runs.persistence import run_finalize_savepoint

log = logging.getLogger("shell")


def _output_confirmed_dns_target_inputs(
    command: str,
    target_inputs: Sequence[Mapping[str, object]],
    recorded_entities: Sequence[object],
) -> list[dict[str, object]]:
    if command_root(command) not in DNS_COMMAND_ROOTS:
        return [dict(item) for item in target_inputs]
    observed = {
        (str(item.get("type") or "").strip().lower(), str(item.get("canonical_value") or "").strip())
        for item in recorded_entities
        if isinstance(item, Mapping)
    }
    confirmed: list[dict[str, object]] = []
    for item in target_inputs:
        raw_value = str(item.get("value") or "").strip()
        if not raw_value:
            continue
        try:
            identity = ("ip", canonical_ip(raw_value))
        except CanonicalizationError:
            try:
                identity = ("domain", canonical_domain(raw_value))
            except CanonicalizationError:
                continue
        if identity in observed:
            confirmed.append(dict(item))
    return confirmed


def discover_project_targets_for_finalize(
    conn: Any,
    session_id: str,
    run_id: str,
    command: str,
    active_project_link: dict[str, Any] | None,
    recorded_entities: Sequence[object] = (),
    *,
    cfg: Mapping[str, Any] | None = None,
    command_project_target_inputs_fn: Callable = command_project_target_inputs,
    record_project_target_discoveries_fn: Callable = record_project_target_discoveries,
) -> list:
    if not active_project_link:
        return []
    try:
        target_inputs = command_project_target_inputs_fn(
            command,
            cfg=app_config.CFG if cfg is None else cfg,
        )
        target_inputs = _output_confirmed_dns_target_inputs(command, target_inputs, recorded_entities)
        return run_finalize_savepoint(
            conn,
            "project_target_discovery",
            lambda: record_project_target_discoveries_fn(
                conn,
                session_id,
                active_project_link["project_id"],
                run_id,
                target_inputs,
            ),
        )
    except ProjectWorkspaceQuotaExceeded as exc:
        active_project_link["target_discovery_skipped_reason"] = str(exc)
        log.warning("PROJECT_TARGET_DISCOVERY_SKIPPED", extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "project_id": active_project_link["project_id"],
            "cmd": command,
            "reason": str(exc),
        })
    except Exception:
        log.error("PROJECT_TARGET_DISCOVERY_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "team_id": str(active_project_link.get("team_id") or ""),
            "project_id": str(active_project_link.get("project_id") or ""),
            "cmd": command,
            "target_discovery_skipped_reason": str(
                active_project_link.get("target_discovery_skipped_reason") or ""
            ),
        })
    return []


__all__ = ["discover_project_targets_for_finalize"]
