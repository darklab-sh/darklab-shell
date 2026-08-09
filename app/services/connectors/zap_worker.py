# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable worker for operator-managed OWASP ZAP jobs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import logging
import os
import signal
import time
from typing import Any

from config import resolve_effective_cfg
from runtime_bootstrap import bootstrap_runtime
from services.atlas.import_workflow import preview_atlas_import
from services.connectors.zap_config import (
    resolve_zap_api_key,
    zap_connector_settings,
)
from services.connectors.zap_job_artifacts import (
    atlas_draft_id_for_zap_job,
    discard_zap_job_plan,
    load_zap_job_plan,
    save_zap_job_report,
    stale_zap_job_plan_ids,
    store_zap_job_plan,
)
from services.connectors.zap_job_lifecycle import (
    expire_zap_jobs,
    record_zap_job_progress,
    record_zap_job_submission,
    transition_zap_job,
)
from services.connectors.zap_worker_lock import acquire_zap_worker_lock
from services.connectors.zap_jobs import (
    ZapJobError,
    create_zap_job,
    new_zap_job_id,
    remote_zap_job_count,
    staged_zap_job_ids,
    zap_jobs_for_worker,
)
from services.connectors.zap_plan_contracts import ReviewedZapAutomationPlan
from services.connectors.zap_transport import (
    cancel_zap_automation_plan,
    download_zap_report,
    fetch_zap_plan_progress,
    submit_zap_automation_plan,
)


log = logging.getLogger("shell")
_STOP = False
_TICK_SECONDS = 5.0
_RECOVERY_GRACE = timedelta(minutes=5)


def _handle_stop(_signum, _frame) -> None:
    global _STOP
    _STOP = True


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
    """Durably queue exactly the reviewed plan bytes before a worker can claim them."""
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


def _fail_job(job_id: str, status: str, exc: BaseException, cfg) -> None:
    if isinstance(exc, ZapJobError) and exc.code == "zap_job_transition_conflict":
        return
    code = str(getattr(exc, "code", "zap_job_failed") or "zap_job_failed")[:80]
    detail = str(exc) if getattr(exc, "code", "") else "The ZAP job failed"
    try:
        transition_zap_job(
            job_id,
            (status,),
            "failed",
            error_code=code,
            error_detail=detail,
        )
    except ZapJobError as transition_error:
        if transition_error.code != "zap_job_transition_conflict":
            raise
    discard_zap_job_plan(job_id, cfg)
    log.warning(
        "ZAP_JOB_FAILED",
        extra={"job_id": job_id, "phase": status, "error_class": type(exc).__name__},
    )


def _preview_report(job: Mapping[str, Any], payload: bytes) -> str:
    draft_id = atlas_draft_id_for_zap_job(str(job.get("id") or ""))
    result = preview_atlas_import(
        session_id=str(job.get("session_id") or ""),
        team_id=str(job.get("team_id") or ""),
        actor_member_id=str(job.get("actor_member_id") or ""),
        role=str(job.get("actor_role") or ""),
        file_content=payload,
        filename=str(job.get("report_filename") or ""),
        format_id="zap_json",
        source_tool="OWASP ZAP",
        import_name="ZAP assessment report",
        draft_id=draft_id,
    )
    if str(result.get("draft_id") or "") != draft_id:
        raise ZapJobError("zap_import_preview_invalid", "The ZAP import preview is invalid")
    return draft_id


def _inflight_is_fresh(job: Mapping[str, Any]) -> bool:
    value = job.get("updated_at")
    if isinstance(value, datetime):
        updated = value
    else:
        try:
            updated = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return False
    if updated.tzinfo is None:
        return False
    return datetime.now(timezone.utc) - updated.astimezone(timezone.utc) < _RECOVERY_GRACE


def _download_and_preview(job: dict[str, Any], settings, api_key: str, cfg) -> None:
    report = download_zap_report(
        settings,
        api_key,
        str(job["id"]),
        str(job.get("report_filename") or ""),
    )
    save_zap_job_report(job, report, cfg)
    draft_id = _preview_report(job, report.payload)
    transition_zap_job(
        str(job["id"]),
        ("downloading",),
        "ready",
        report_bytes=report.byte_count,
        report_sha256=report.sha256,
        import_source_id=draft_id,
    )


def process_zap_job(job: dict[str, Any], settings, api_key: str, cfg=None) -> None:
    job_id = str(job.get("id") or "")
    status = str(job.get("status") or "")
    claimed_download = False
    try:
        if status == "queued":
            job = transition_zap_job(job_id, ("queued",), "submitting")
            status = "submitting"
            plan = load_zap_job_plan(job, cfg)
            try:
                remote_id = submit_zap_automation_plan(settings, api_key, job_id, plan)
                job = record_zap_job_submission(job_id, remote_id)
            except Exception as exc:  # noqa: BLE001
                raise ZapJobError(
                    "zap_submission_state_uncertain",
                    "ZAP submission ended before its remote plan id was saved",
                ) from exc
            discard_zap_job_plan(job_id, cfg)
            status = str(job.get("status") or "")
            if status == "running":
                return
        if status == "submitting":
            if _inflight_is_fresh(job):
                return
            raise ZapJobError(
                "zap_submission_state_uncertain",
                "ZAP submission was interrupted before its remote plan id was saved",
            )
        if status == "cancel_requested":
            remote_id = str(job.get("remote_plan_id") or "")
            if not remote_id:
                if _inflight_is_fresh(job):
                    return
                raise ZapJobError(
                    "zap_cancel_state_uncertain",
                    "ZAP cancellation could not identify the remote plan",
                )
            try:
                cancel_zap_automation_plan(settings, api_key, remote_id)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "ZAP_CANCEL_RETRY",
                    extra={"job_id": job_id, "error_class": type(exc).__name__},
                )
                return
            transition_zap_job(job_id, ("cancel_requested",), "canceled")
            discard_zap_job_plan(job_id, cfg)
            return
        if status == "running":
            progress = fetch_zap_plan_progress(settings, api_key, str(job.get("remote_plan_id") or ""))
            job = record_zap_job_progress(job_id, progress)
            if not progress.complete:
                return
            job = transition_zap_job(job_id, ("running",), "downloading")
            status = "downloading"
            claimed_download = True
        if status == "downloading":
            if not claimed_download and _inflight_is_fresh(job):
                return
            _download_and_preview(job, settings, api_key, cfg)
    except Exception as exc:  # noqa: BLE001
        _fail_job(job_id, status, exc, cfg)


def run_once(
    *,
    limit: int = 50,
    cfg: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    active_cfg = resolve_effective_cfg(cfg)
    expire_zap_jobs()
    stale_plan_ids = stale_zap_job_plan_ids(active_cfg)
    retained_plan_ids = staged_zap_job_ids(stale_plan_ids)
    for job_id in stale_plan_ids:
        if job_id not in retained_plan_ids:
            discard_zap_job_plan(job_id, active_cfg)
    jobs = zap_jobs_for_worker(limit=limit)
    if not jobs:
        return 0
    settings = zap_connector_settings(active_cfg)
    try:
        api_key = resolve_zap_api_key(settings, environ=environ)
    except Exception as exc:  # noqa: BLE001
        for job in jobs:
            status = str(job.get("status") or "")
            if status == "cancel_requested":
                log.warning(
                    "ZAP_CANCEL_CREDENTIAL_RETRY",
                    extra={
                        "job_id": str(job.get("id") or ""),
                        "error_class": type(exc).__name__,
                    },
                )
                continue
            _fail_job(str(job.get("id") or ""), status, exc, active_cfg)
        return len(jobs)
    remote_count = remote_zap_job_count()
    processed = 0
    for job in jobs:
        if str(job.get("status") or "") == "queued":
            if remote_count >= settings.max_concurrent_jobs:
                continue
            remote_count += 1
        process_zap_job(job, settings, api_key, active_cfg)
        processed += 1
    return processed


def run_forever(*, tick_seconds: float = _TICK_SECONDS, limit: int = 50) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    with acquire_zap_worker_lock(resolve_effective_cfg()) as acquired:
        if not acquired:
            log.info("ZAP_WORKER_LOCK_HELD")
            return
        log.info("ZAP_WORKER_STARTED", extra={"pid": os.getpid()})
        while not _STOP:
            try:
                run_once(limit=limit)
            except Exception:  # noqa: BLE001
                log.error("ZAP_WORKER_TICK_FAILED", exc_info=True)
            time.sleep(max(0.5, float(tick_seconds)))
        log.info("ZAP_WORKER_STOPPED", extra={"pid": os.getpid()})


def main() -> None:
    bootstrap_runtime(
        resolve_effective_cfg(),
        init_metrics=False,
        init_process=True,
        init_db=True,
        runtime_name="zap_worker",
    )
    run_forever()


if __name__ == "__main__":
    main()
