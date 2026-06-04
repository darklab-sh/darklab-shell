"""Shared route orchestration for AI run assists."""

from __future__ import annotations

import logging
from typing import Any

from flask import has_request_context

from config import CFG
from core.database import db_connect
from core.helpers import get_client_ip, get_log_session_id, ip_is_in_cidrs
from core.output_signals import extract_target
from core.process import active_run_belongs_to_scope, active_runs_for_session
from services.ai import ai_cfg
from services.ai.context import build_run_context
from services.ai.coordination import AICoordinationUnavailable, check_ai_route_rate_limit, enqueue_lock
from services.ai.prompts import resolved_prompt_version
from services.ai.schemas import NEXT_COMMANDS_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION
from services.ai.storage import enqueue_assist, list_recent_assists_for_run
from services import metrics as app_metrics
from services.projects.active import get_active_project
from services.projects.targets import list_project_targets

log = logging.getLogger("shell")


class AIAssistRouteError(RuntimeError):
    """Route-safe AI assist error with a stable code and HTTP status."""

    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


def list_run_assists(session_id: str, run_id: str, *, team_id: str = "") -> list[dict[str, Any]]:
    if not _run_belongs_to_owner(session_id, run_id, team_id=team_id):
        raise AIAssistRouteError("not_found", "Run not found.", status_code=404)
    return [_public_assist(row) for row in list_recent_assists_for_run(session_id, run_id, team_id=team_id)]


def enqueue_summary_assist(
    session_id: str,
    run_id: str,
    *,
    team_id: str = "",
    force: bool = False,
    cfg: dict | None = None,
) -> tuple[dict[str, Any], int]:
    active_cfg = CFG if cfg is None else cfg
    settings = ai_cfg(active_cfg)
    if not settings["enabled"]:
        raise AIAssistRouteError("ai_disabled", "AI assists are disabled.", status_code=403)
    if not settings["feature_summary"]:
        raise AIAssistRouteError("ai_feature_disabled", "AI summaries are disabled.", status_code=403)
    if _active_run_exists(session_id, run_id, team_id=team_id):
        raise AIAssistRouteError("ai_run_active", "AI assists are only available for completed runs.", status_code=409)
    row = _owned_run_row(session_id, run_id, team_id=team_id)
    if row is None:
        raise AIAssistRouteError("not_found", "Run not found.", status_code=404)
    if not str(row.get("finished") or ""):
        raise AIAssistRouteError("ai_run_active", "AI assists are only available for completed runs.", status_code=409)
    _enforce_ai_write_rate_limit(session_id, active_cfg, variant="summary")

    context = build_run_context(run_id, session_id=session_id, team_id=team_id, cfg=active_cfg, variant="summary")
    if not context.useful:
        raise AIAssistRouteError("ai_no_context", "Run does not have enough useful context for an AI assist.", status_code=422)
    prompt_version, prompt_source = resolved_prompt_version(settings.get("prompt_version_override"))
    active_project_id, project_targets = _active_project_snapshot(session_id, team_id=team_id)
    project_targets = [*project_targets, *_source_run_targets(row)]
    try:
        with enqueue_lock(
            session_id,
            run_id,
            "summary",
            model=settings["model"],
            prompt_version=prompt_version,
            team_id=team_id,
        ) as locked:
            if not locked:
                raise AIAssistRouteError("ai_busy", "AI assist request is already being queued.", status_code=429)
            assist, inserted = enqueue_assist(
                session_id,
                run_id,
                "summary",
                context,
                team_id=team_id,
                cfg=active_cfg,
                prompt_version=prompt_version,
                prompt_version_source=prompt_source,
                payload_schema_version=SUMMARY_SCHEMA_VERSION,
                active_project_id=active_project_id,
                project_target_snapshot=project_targets,
                force=force,
            )
    except AICoordinationUnavailable as exc:
        raise AIAssistRouteError("ai_unavailable", str(exc), status_code=503) from exc
    except AIAssistRouteError:
        raise
    except RuntimeError as exc:
        raise AIAssistRouteError("ai_busy", "AI assist queue is full.", status_code=429) from exc
    public = _public_assist(assist)
    status_code = 202 if inserted or public["status"] in {"queued", "in_progress"} else 200
    _log_enqueue_result(
        public,
        run_id=run_id,
        session_id=session_id,
        variant="summary",
        inserted=inserted,
        force=force,
        settings=settings,
        prompt_version=prompt_version,
        prompt_source=prompt_source,
        context=context,
    )
    return public, status_code


def enqueue_next_commands_assist(
    session_id: str,
    run_id: str,
    *,
    team_id: str = "",
    force: bool = False,
    cfg: dict | None = None,
) -> tuple[dict[str, Any], int]:
    active_cfg = CFG if cfg is None else cfg
    settings = ai_cfg(active_cfg)
    if not settings["enabled"]:
        raise AIAssistRouteError("ai_disabled", "AI assists are disabled.", status_code=403)
    if not settings["feature_next_commands"]:
        raise AIAssistRouteError("ai_feature_disabled", "AI next-command suggestions are disabled.", status_code=403)
    if _active_run_exists(session_id, run_id, team_id=team_id):
        raise AIAssistRouteError("ai_run_active", "AI assists are only available for completed runs.", status_code=409)
    row = _owned_run_row(session_id, run_id, team_id=team_id)
    if row is None:
        raise AIAssistRouteError("not_found", "Run not found.", status_code=404)
    if not str(row.get("finished") or ""):
        raise AIAssistRouteError("ai_run_active", "AI assists are only available for completed runs.", status_code=409)
    _enforce_ai_write_rate_limit(session_id, active_cfg, variant="next_commands")

    context = build_run_context(run_id, session_id=session_id, team_id=team_id, cfg=active_cfg, variant="next_commands")
    if not context.useful:
        raise AIAssistRouteError("ai_no_context", "Run does not have enough useful context for an AI assist.", status_code=422)
    prompt_version, prompt_source = resolved_prompt_version(settings.get("prompt_version_override"))
    active_project_id, project_targets = _active_project_snapshot(session_id, team_id=team_id)
    project_targets = [*project_targets, *_source_run_targets(row)]
    try:
        with enqueue_lock(
            session_id,
            run_id,
            "next_commands",
            model=settings["model"],
            prompt_version=prompt_version,
            team_id=team_id,
        ) as locked:
            if not locked:
                raise AIAssistRouteError("ai_busy", "AI assist request is already being queued.", status_code=429)
            assist, inserted = enqueue_assist(
                session_id,
                run_id,
                "next_commands",
                context,
                team_id=team_id,
                cfg=active_cfg,
                prompt_version=prompt_version,
                prompt_version_source=prompt_source,
                payload_schema_version=NEXT_COMMANDS_SCHEMA_VERSION,
                active_project_id=active_project_id,
                project_target_snapshot=project_targets,
                force=force,
            )
    except AICoordinationUnavailable as exc:
        raise AIAssistRouteError("ai_unavailable", str(exc), status_code=503) from exc
    except AIAssistRouteError:
        raise
    except RuntimeError as exc:
        raise AIAssistRouteError("ai_busy", "AI assist queue is full.", status_code=429) from exc
    public = _public_assist(assist)
    status_code = 202 if inserted or public["status"] in {"queued", "in_progress"} else 200
    _log_enqueue_result(
        public,
        run_id=run_id,
        session_id=session_id,
        variant="next_commands",
        inserted=inserted,
        force=force,
        settings=settings,
        prompt_version=prompt_version,
        prompt_source=prompt_source,
        context=context,
    )
    return public, status_code


def _enforce_ai_write_rate_limit(session_id: str, cfg: dict, *, variant: str) -> None:
    bypass_session_limit, client_ip = _diagnostics_client_bypasses_session_limit(cfg)
    try:
        result = check_ai_route_rate_limit(session_id, cfg=cfg, bypass_session_limit=bypass_session_limit)
    except AICoordinationUnavailable as exc:
        raise AIAssistRouteError("ai_unavailable", str(exc), status_code=503) from exc
    if result.allowed:
        if bypass_session_limit:
            log.info(
                "AI_RATE_LIMIT_SESSION_BYPASSED",
                extra={
                    "ip": client_ip,
                    "session": get_log_session_id(session_id),
                    "variant": variant,
                },
            )
        return
    log.warning(
        "AI_RATE_LIMIT_REJECTED",
        extra={
            "ip": client_ip,
            "session": get_log_session_id(session_id),
            "variant": variant,
            "error_code": result.error_code,
            "retry_after_seconds": result.retry_after_seconds,
            "bypass_session_limit": bypass_session_limit,
        },
    )
    app_metrics.record_ai_request(variant, "rate_limited", error_code=result.error_code)
    raise AIAssistRouteError(
        result.error_code or "ai_rate_limited",
        result.message or "AI assists are rate limited.",
        status_code=429,
    )


def _diagnostics_client_bypasses_session_limit(cfg: dict) -> tuple[bool, str]:
    if not has_request_context():
        return False, ""
    client_ip = get_client_ip()
    allowed_cidrs = cfg.get("diagnostics_allowed_cidrs") or []
    if ip_is_in_cidrs(client_ip, allowed_cidrs):
        return True, client_ip
    return False, client_ip


def _log_enqueue_result(
    public: dict[str, Any],
    *,
    run_id: str,
    session_id: str,
    variant: str,
    inserted: bool,
    force: bool,
    settings: dict[str, Any],
    prompt_version: str,
    prompt_source: str,
    context,
) -> None:
    log.info(
        "AI_ASSIST_ENQUEUE_RESULT",
        extra={
            "assist_id": str(public.get("id") or ""),
            "run_id": run_id,
            "session": get_log_session_id(session_id),
            "variant": variant,
            "status": str(public.get("status") or ""),
            "inserted": inserted,
            "force": force,
            "model": settings["model"],
            "prompt_version": prompt_version,
            "prompt_version_source": prompt_source,
            "input_chars": context.input_chars,
            "estimated_input_tokens": context.estimated_input_tokens,
            "redacted_bytes": context.redacted_bytes,
            "pre_redaction_bytes": context.pre_redaction_bytes,
        },
    )


def _owned_run_row(session_id: str, run_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    if team_id:
        sql = "SELECT id, session_id, team_id, command, finished, exit_code FROM runs WHERE team_id = ? AND id = ?"
        params = (team_id, run_id)
    else:
        sql = (
            "SELECT id, session_id, team_id, command, finished, exit_code FROM runs "
            "WHERE session_id = ? AND (team_id IS NULL OR team_id = '') AND id = ?"
        )
        params = (session_id, run_id)
    with db_connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _run_belongs_to_owner(session_id: str, run_id: str, *, team_id: str = "") -> bool:
    if _active_run_exists(session_id, run_id, team_id=team_id):
        return True
    return _owned_run_row(session_id, run_id, team_id=team_id) is not None


def _active_run_exists(session_id: str, run_id: str, *, team_id: str = "") -> bool:
    if active_run_belongs_to_scope(run_id, session_id, team_id):
        return True
    return any(
        str(active.get("run_id") or "") == run_id
        for active in active_runs_for_session(session_id, team_id=team_id)
    )


def _active_project_snapshot(session_id: str, *, team_id: str = "") -> tuple[str, list[dict[str, Any]]]:
    project = get_active_project(session_id, team_id=team_id)
    if not project:
        return "", []
    project_id = str(project.get("id") or "")
    page = list_project_targets(session_id, project_id, limit=100, offset=0, team_id=team_id)
    targets = []
    for target in (page or {}).get("targets", []):
        value = str(target.get("canonical_value") or target.get("value") or "").strip()
        target_type = str(target.get("type") or "").strip()
        if value:
            targets.append({"type": target_type, "value": value})
    return project_id, targets


def _source_run_targets(row: dict[str, Any]) -> list[dict[str, Any]]:
    target = extract_target(str(row.get("command") or ""))
    if not target:
        return []
    return [{"type": "source_run_target", "value": target}]


def _public_assist(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "run_id": str(row.get("run_id") or ""),
        "variant": str(row.get("variant") or ""),
        "status": str(row.get("status") or ""),
        "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
        "progress": row.get("progress") if isinstance(row.get("progress"), dict) else {},
        "error_code": str(row.get("error_code") or ""),
        "error_message": str(row.get("error_message") or ""),
        "model": str(row.get("model") or ""),
        "prompt_version": str(row.get("prompt_version") or ""),
        "prompt_version_source": str(row.get("prompt_version_source") or ""),
        "payload_schema_version": str(row.get("payload_schema_version") or ""),
        "input_chars": int(row.get("input_chars") or 0),
        "output_chars": int(row.get("output_chars") or 0),
        "estimated_input_tokens": int(row.get("estimated_input_tokens") or 0),
        "duration_ms": int(row.get("duration_ms") or 0),
        "redacted_bytes": int(row.get("redacted_bytes") or 0),
        "pre_redaction_bytes": int(row.get("pre_redaction_bytes") or 0),
        "active_project_id": str(row.get("active_project_id") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
