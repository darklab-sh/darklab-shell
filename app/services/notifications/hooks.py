"""Notification hook points for application events."""

from __future__ import annotations

import logging
from typing import Any

import config as app_config
from core.helpers import get_log_session_id
from core.redaction import apply_redaction_rules
from services.notifications import dispatcher
from services.notifications.payloads import build_run_complete_payload
from services.runs.kinds import RUN_KIND_EXTERNAL, normalize_run_kind

log = logging.getLogger("shell")


def _redact_summary_fields(fields: dict[str, Any], *, cfg=None) -> dict[str, Any]:
    rules = app_config.get_share_redaction_rules(cfg)
    redacted: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, str):
            redacted[key] = apply_redaction_rules(value, rules)
        else:
            redacted[key] = value
    return redacted


def _run_complete_summary(finalize_summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = finalize_summary if isinstance(finalize_summary, dict) else {}
    payload: dict[str, Any] = {
        "artifact_count": int(summary.get("artifact_count") or 0),
        "finding_count": int(summary.get("finding_count") or 0),
        "atlas_entity_count": int(summary.get("atlas_entity_count") or 0),
        "project_target_count": int(summary.get("project_target_count") or 0),
    }
    for key in ("output_kind_counts", "output_signal_counts", "output_entity_type_counts"):
        value = summary.get(key)
        if isinstance(value, dict) and value:
            payload[key] = {str(item_key): int(item_value or 0) for item_key, item_value in value.items()}
    return payload


def enqueue_run_complete(
    *,
    run_id: str,
    session_id: str,
    command: str,
    exit_code: int,
    run_kind: str,
    team_id: str = "",
    finalize_summary: dict[str, Any] | None = None,
    cfg=None,
    conn=None,
) -> list[str]:
    """Queue run-complete notifications for external non-PTY run finalization."""
    normalized_kind = normalize_run_kind(run_kind, command=command)
    if normalized_kind != RUN_KIND_EXTERNAL:
        return []
    summary_fields = _redact_summary_fields(_run_complete_summary(finalize_summary), cfg=cfg)
    payload = build_run_complete_payload(
        {
            "id": run_id,
            "session_id": session_id,
            "command": command,
            "exit_code": exit_code,
        },
        summary_fields,
    )
    try:
        return dispatcher.enqueue(
            "run_complete",
            payload,
            session_id,
            conn=conn,
            run_id=run_id,
            team_id=team_id,
        )
    except Exception:
        log.error("NOTIFICATION_RUN_COMPLETE_ENQUEUE_ERROR", exc_info=True, extra={
            "run_id": run_id,
            "session": get_log_session_id(session_id),
        })
        return []
