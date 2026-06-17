"""
Filesystem-backed evidence package archive build jobs.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
import secrets
import time

from config import CFG, resolve_data_dir
from core.helpers import get_log_session_id
from services import metrics as app_metrics
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import EvidencePackageTooLarge
from services.projects.package_archive import build_evidence_package_archive

_JOB_ID_RE = re.compile(r"^epj_[a-f0-9]{24}$")
_JOB_TTL = timedelta(hours=2)
_JOB_DIR = Path(resolve_data_dir()) / "evidence-package-jobs"
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="evidence-package")
log = logging.getLogger("shell")


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _ensure_job_dir():
    _JOB_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)


def _job_id():
    return "epj_" + secrets.token_hex(12)


def _safe_job_id(job_id):
    normalized = str(job_id or "").strip()
    return normalized if _JOB_ID_RE.fullmatch(normalized) else ""


def _job_path(job_id):
    safe = _safe_job_id(job_id)
    if not safe:
        return None
    return _JOB_DIR / f"{safe}.json"


def _archive_path(job_id):
    safe = _safe_job_id(job_id)
    if not safe:
        return None
    return _JOB_DIR / f"{safe}.zip"


def _read_job(job_id):
    path = _job_path(job_id)
    if path is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_job(job):
    _ensure_job_dir()
    safe = _safe_job_id(job.get("id"))
    if not safe:
        return
    path = _JOB_DIR / f"{safe}.json"
    payload = dict(job)
    payload["updated_at"] = _iso(_now())
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def _public_job(job):
    if not isinstance(job, dict):
        return None
    public = {
        "id": job.get("id") or "",
        "status": job.get("status") or "unknown",
        "phase": job.get("phase") or "",
        "message": job.get("message") or "",
        "created_at": job.get("created_at") or "",
        "updated_at": job.get("updated_at") or "",
    }
    for key in ("archive_bytes", "filename", "error", "error_status"):
        if job.get(key) not in (None, ""):
            public[key] = job.get(key)
    if isinstance(job.get("metrics"), dict):
        public["metrics"] = job["metrics"]
    return public


def cleanup_evidence_package_archive_jobs():
    _ensure_job_dir()
    cutoff = _now() - _JOB_TTL
    for path in _JOB_DIR.glob("epj_*.json"):
        try:
            updated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if updated >= cutoff:
            continue
        job = _read_job(path.stem) or {}
        archive_path = job.get("archive_path")
        if archive_path:
            try:
                Path(archive_path).unlink()
            except OSError:
                pass
        try:
            path.unlink()
        except OSError:
            pass


def _matches(job, session_id, project_id, package_id, *, team_id=""):
    if not isinstance(job, dict):
        return False
    if job.get("project_id") != project_id or job.get("package_id") != package_id:
        return False
    job_team_id = str(job.get("team_id") or "")
    if team_id:
        return job_team_id == str(team_id or "")
    return not job_team_id and job.get("session_id") == session_id


def get_evidence_package_archive_job(session_id, project_id, package_id, job_id, *, team_id=""):
    job = _read_job(job_id)
    if not isinstance(job, dict) or not _matches(job, session_id, project_id, package_id, team_id=team_id):
        return None
    return _public_job(job)


def evidence_package_archive_for_job(session_id, project_id, package_id, job_id, *, team_id=""):
    job = _read_job(job_id)
    if not isinstance(job, dict) or not _matches(job, session_id, project_id, package_id, team_id=team_id):
        return None
    if job.get("status") != "complete":
        return {"status": job.get("status") or "unknown", "error": job.get("error") or ""}
    path = Path(str(job.get("archive_path") or ""))
    try:
        path.relative_to(_JOB_DIR)
    except ValueError:
        return {"status": "failed", "error": "archive path is invalid"}
    if not path.is_file():
        return {"status": "failed", "error": "archive is no longer available"}
    return {
        "status": "complete",
        "path": str(path),
        "filename": job.get("filename") or "evidence-package.zip",
        "mimetype": job.get("mimetype") or "application/zip",
        "archive_bytes": int(job.get("archive_bytes") or 0),
        "metrics": job.get("metrics") if isinstance(job.get("metrics"), dict) else {},
        "skipped_artifacts": int(job.get("skipped_artifacts") or 0),
    }


def discard_evidence_package_archive_job(job_id, *, archive=True):
    job = _read_job(job_id)
    if archive and isinstance(job, dict) and job.get("archive_path"):
        try:
            Path(str(job["archive_path"])).unlink()
        except OSError:
            pass
    path = _job_path(job_id)
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass


def _audit_failure_reason(status, error=""):
    if str(status or "").strip().lower() != "failed":
        return ""
    normalized = str(error or "").strip().lower()
    if "package not found" in normalized:
        return "package_not_found"
    if "project not found" in normalized:
        return "project_not_found"
    if "invalid job id" in normalized:
        return "invalid_job_id"
    if "too large" in normalized or "size limit" in normalized:
        return "size_limit"
    return "build_failed"


def _audit_log_extra(job, *, details):
    return {
        "job_id": str(job.get("id") or ""),
        "project_id": str(job.get("project_id") or ""),
        "package_id": str(job.get("package_id") or ""),
        "team_id": str(job.get("team_id") or ""),
        "actor_member_id": str(job.get("actor_member_id") or ""),
        **dict(details),
    }


def _record_job_audit(job, *, status, error="", archive_bytes=0, metrics=None):
    details = {
        "project_id": str(job.get("project_id") or ""),
        "package_id": str(job.get("package_id") or ""),
        "job_id": str(job.get("id") or ""),
        "status": status,
    }
    reason = _audit_failure_reason(status, error)
    if reason:
        details["reason"] = reason
    if archive_bytes:
        details["archive_bytes"] = int(archive_bytes)
    if isinstance(metrics, dict):
        for key in ("run_count", "finding_count", "artifact_count", "target_count"):
            if key in metrics:
                details[key] = int(metrics.get(key) or 0)
    try:
        record_event(
            AuditEventType.PACKAGE_BUILD,
            target_id=str(job.get("package_id") or ""),
            project_id=str(job.get("project_id") or ""),
            job_id=str(job.get("id") or ""),
            correlation_id=str(job.get("id") or ""),
            session_id=str(job.get("session_id") or ""),
            actor_session_id=str(job.get("session_id") or ""),
            team_id=str(job.get("team_id") or ""),
            actor_member_id=str(job.get("actor_member_id") or ""),
            details=details,
        )
    except Exception:
        log.exception("PACKAGE_BUILD_AUDIT_FAILED", extra=_audit_log_extra(job, details=details))


def _run_job(job_id, cfg_snapshot):
    job = _read_job(job_id)
    if not isinstance(job, dict):
        return
    started = time.perf_counter()

    def _update(status, phase, message, **extra):
        current = _read_job(job_id) or job
        current.update({
            "status": status,
            "phase": phase,
            "message": message,
        })
        current.update(extra)
        _write_job(current)

    def _progress(phase, message):
        _update("running", phase, message)

    _update("running", "loading", "Loading package")
    try:
        archive = build_evidence_package_archive(
            job["session_id"],
            job["project_id"],
            job["package_id"],
            cfg=cfg_snapshot,
            progress_callback=_progress,
            archive_dir=str(_JOB_DIR),
            team_id=str(job.get("team_id") or ""),
            build_job_id=str(job.get("id") or ""),
        )
    except EvidencePackageTooLarge as exc:
        app_metrics.record_evidence_package_build("too_large", time.perf_counter() - started)
        log.warning("PACKAGE_BUILD_FAILED", extra={
            "session": get_log_session_id(str(job.get("session_id") or "")),
            "team_id": str(job.get("team_id") or ""),
            "actor_member_id": str(job.get("actor_member_id") or ""),
            "project_id": job.get("project_id"),
            "package_id": job.get("package_id"),
            "job_id": job_id,
            "stage": "archive",
            "error_status": 413,
            "error": str(exc),
        })
        _record_job_audit(job, status="failed", error=str(exc))
        _update("failed", "failed", str(exc), error=str(exc), error_status=413)
        return
    except Exception as exc:
        app_metrics.record_evidence_package_build("error", time.perf_counter() - started)
        log.error("PACKAGE_JOB_FAILED", exc_info=True, extra={
            "session": get_log_session_id(str(job.get("session_id") or "")),
            "team_id": str(job.get("team_id") or ""),
            "actor_member_id": str(job.get("actor_member_id") or ""),
            "project_id": job.get("project_id"),
            "package_id": job.get("package_id"),
            "job_id": job_id,
            "stage": "archive",
            "error": str(exc),
        })
        _record_job_audit(job, status="failed", error=str(exc))
        _update("failed", "failed", "Package archive build failed.", error=str(exc), error_status=500)
        return
    if archive is None:
        app_metrics.record_evidence_package_build("not_found", time.perf_counter() - started)
        _record_job_audit(job, status="failed", error="package not found")
        _update("failed", "not_found", "Package not found.", error="package not found", error_status=404)
        return
    destination = _archive_path(job_id)
    if destination is None:
        app_metrics.record_evidence_package_build("error", time.perf_counter() - started)
        _record_job_audit(job, status="failed", error="invalid job id")
        _update("failed", "failed", "Package archive build failed.", error="invalid job id", error_status=500)
        return
    os.replace(archive["path"], destination)
    metrics = archive.get("metrics") if isinstance(archive.get("metrics"), dict) else {}
    archive_bytes = int(metrics.get("archive_bytes") or archive.get("byte_size") or destination.stat().st_size)
    app_metrics.record_evidence_package_build(
        "success",
        time.perf_counter() - started,
        archive_bytes=archive_bytes,
        skipped_artifacts=int(metrics.get("skipped_artifacts") or 0),
        skipped_other_items=max(
            0,
            int(metrics.get("skipped_items") or 0) - int(metrics.get("skipped_artifacts") or 0),
        ),
    )
    _record_job_audit(job, status="complete", archive_bytes=archive_bytes, metrics=metrics)
    _update(
        "complete",
        "complete",
        "Archive ready",
        archive_path=str(destination),
        filename=archive.get("filename") or "evidence-package.zip",
        mimetype=archive.get("mimetype") or "application/zip",
        archive_bytes=archive_bytes,
        skipped_artifacts=len(archive.get("skipped_artifacts") or []),
        metrics=metrics,
    )


def start_evidence_package_archive_job(session_id, project_id, package_id, *, cfg=None, team_id="", actor_member_id=""):
    cleanup_evidence_package_archive_jobs()
    _ensure_job_dir()
    created = _iso(_now())
    job = {
        "id": _job_id(),
        "session_id": session_id,
        "team_id": str(team_id or ""),
        "actor_member_id": str(actor_member_id or ""),
        "project_id": project_id,
        "package_id": package_id,
        "status": "queued",
        "phase": "queued",
        "message": "Queued archive build",
        "created_at": created,
        "updated_at": created,
    }
    _write_job(job)
    cfg_snapshot = dict(CFG if cfg is None else cfg)
    _EXECUTOR.submit(_run_job, job["id"], cfg_snapshot)
    return _public_job(job)
