# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private ZAP plan spool and owner-visible report storage."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any

from config import resolve_data_dir
from services.connectors.zap_http import ZapTransportError
from services.connectors.zap_plan_contracts import (
    ReviewedZapAutomationPlan,
    ZapAutomationPlanSummary,
)
from services.connectors.zap_transport import DownloadedZapReport, zap_transfer_paths
from services.teams.scope import owner_context_for_scope
from services.workspace.files import write_owner_workspace_text_file


_MAX_PLAN_BYTES = 65536


class ZapJobArtifactError(RuntimeError):
    """Raised when a durable ZAP artifact can't be retained safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _spool_dir(cfg: Mapping[str, Any] | None = None) -> Path:
    path = Path(resolve_data_dir(cfg)) / "zap-connector-jobs"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _plan_path(job_id: str, cfg: Mapping[str, Any] | None = None) -> Path:
    zap_transfer_paths(job_id, "report.json")
    return _spool_dir(cfg) / f"{job_id}.yaml"


def store_zap_job_plan(
    job_id: str,
    plan: ReviewedZapAutomationPlan,
    cfg: Mapping[str, Any] | None = None,
) -> None:
    payload = bytes(plan.yaml_bytes)
    if not payload or len(payload) > _MAX_PLAN_BYTES:
        raise ZapJobArtifactError("zap_plan_invalid", "The reviewed ZAP plan is invalid")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ZapJobArtifactError("zap_plan_invalid", "The reviewed ZAP plan is invalid") from exc
    destination = _plan_path(job_id, cfg)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(destination.parent)) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except OSError as exc:
        raise ZapJobArtifactError("zap_plan_store_failed", "The reviewed ZAP plan could not be queued") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _summary_from_job(job: Mapping[str, Any]) -> ZapAutomationPlanSummary:
    value = job.get("plan_summary")
    if not isinstance(value, Mapping):
        raise ZapJobArtifactError("zap_plan_invalid", "The queued ZAP plan summary is invalid")
    try:
        summary = ZapAutomationPlanSummary(
            policy_level=str(value["policy_level"]),
            authentication_role=str(value["authentication_role"]),
            targets=tuple(str(item) for item in value["targets"]),
            include_rule_count=int(value["include_rule_count"]),
            exclusion_rule_count=int(value["exclusion_rule_count"]),
            job_types=tuple(str(item) for item in value["job_types"]),
            job_timeout_seconds=int(value["job_timeout_seconds"]),
            report_file=str(value["report_file"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ZapJobArtifactError("zap_plan_invalid", "The queued ZAP plan summary is invalid") from exc
    if summary.to_dict() != dict(value) or summary.report_file != str(job.get("report_filename") or ""):
        raise ZapJobArtifactError("zap_plan_invalid", "The queued ZAP plan summary is invalid")
    return summary


def load_zap_job_plan(
    job: Mapping[str, Any],
    cfg: Mapping[str, Any] | None = None,
) -> ReviewedZapAutomationPlan:
    path = _plan_path(str(job.get("id") or ""), cfg)
    try:
        with path.open("rb") as handle:
            payload = handle.read(_MAX_PLAN_BYTES + 1)
    except OSError as exc:
        raise ZapJobArtifactError("zap_plan_unavailable", "The queued ZAP plan is unavailable") from exc
    if not payload or len(payload) > _MAX_PLAN_BYTES:
        raise ZapJobArtifactError("zap_plan_invalid", "The queued ZAP plan is invalid")
    return ReviewedZapAutomationPlan(yaml_bytes=payload, summary=_summary_from_job(job))


def discard_zap_job_plan(job_id: str, cfg: Mapping[str, Any] | None = None) -> None:
    try:
        _plan_path(job_id, cfg).unlink(missing_ok=True)
    except (OSError, ZapTransportError):
        return


def stale_zap_job_plan_ids(
    cfg: Mapping[str, Any] | None = None,
    *,
    now: float | None = None,
    grace_seconds: int = 300,
) -> tuple[str, ...]:
    """Return a bounded set of old plan spools eligible for database reconciliation."""
    cutoff = (time.time() if now is None else float(now)) - max(60, int(grace_seconds))
    candidates: list[str] = []
    for path in sorted(_spool_dir(cfg).glob("zpj_*.yaml"))[:256]:
        try:
            path_stat = path.lstat()
        except OSError:
            continue
        if not stat.S_ISREG(path_stat.st_mode) or path_stat.st_mtime > cutoff:
            continue
        try:
            zap_transfer_paths(path.stem, "report.json")
        except ZapTransportError:
            continue
        candidates.append(path.stem)
    return tuple(candidates)


def zap_report_workspace_path(job_id: str, report_filename: str) -> str:
    zap_transfer_paths(job_id, report_filename)
    return f"assessments/zap/{job_id}/{report_filename}"


def save_zap_job_report(
    job: Mapping[str, Any],
    report: DownloadedZapReport,
    cfg: Mapping[str, Any] | None = None,
) -> str:
    try:
        text = report.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ZapJobArtifactError("zap_report_invalid", "The ZAP report is not valid UTF-8 JSON") from exc
    owner = owner_context_for_scope(
        str(job.get("session_id") or ""),
        team_id=str(job.get("team_id") or ""),
        actor_member_id=str(job.get("actor_member_id") or ""),
    )
    relative_path = zap_report_workspace_path(
        str(job.get("id") or ""),
        str(job.get("report_filename") or ""),
    )
    written = write_owner_workspace_text_file(owner, relative_path, text, cfg)
    if int(written.get("size") or 0) != report.byte_count:
        raise ZapJobArtifactError("zap_report_invalid", "The ZAP report could not be retained exactly")
    return relative_path


def atlas_draft_id_for_zap_job(job_id: str) -> str:
    zap_transfer_paths(job_id, "report.json")
    suffix = hashlib.sha256(job_id.encode("ascii")).hexdigest()[:32]
    return f"impd_{suffix}"


__all__ = [
    "ZapJobArtifactError",
    "atlas_draft_id_for_zap_job",
    "discard_zap_job_plan",
    "load_zap_job_plan",
    "save_zap_job_report",
    "stale_zap_job_plan_ids",
    "store_zap_job_plan",
    "zap_report_workspace_path",
]
