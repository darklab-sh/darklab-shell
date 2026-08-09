# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded ZAP plan submission, progress, cancellation, and report transfer."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from services.connectors.zap_config import ZapConnectorSettings
from services.connectors.zap_http import (
    ZapTransportError,
    zap_json_request,
    zap_request_bytes,
)
from services.connectors.zap_plan_contracts import ReviewedZapAutomationPlan
from services.connectors.zap_remote_progress import (
    ReviewedZapRemoteProgress,
    review_zap_remote_progress,
)


_JOB_ID_RE = re.compile(r"zpj_[0-9a-f]{32}")
_PLAN_ID_RE = re.compile(r"(?:0|[1-9][0-9]{0,9})")
_REPORT_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_MAX_PLAN_BYTES = 65536


@dataclass(frozen=True)
class ZapTransferPaths:
    plan_file: str
    plan_api_path: str
    report_file: str


@dataclass(frozen=True)
class DownloadedZapReport:
    payload: bytes
    sha256: str

    @property
    def byte_count(self) -> int:
        return len(self.payload)


def zap_transfer_paths(job_id: str, report_filename: str) -> ZapTransferPaths:
    """Return traversal-free names below ZAP's configured transfer directory."""
    job = str(job_id or "").strip()
    report = str(report_filename or "").strip()
    if not _JOB_ID_RE.fullmatch(job):
        raise ZapTransportError("zap_job_id_invalid", "The ZAP job id is invalid")
    if (
        not _REPORT_FILE_RE.fullmatch(report)
        or report in {".", ".."}
    ):
        raise ZapTransportError("zap_report_name_invalid", "The ZAP report name is invalid")
    directory = f"darklab/jobs/{job}"
    plan_file = f"{directory}/plan.yaml"
    return ZapTransferPaths(
        plan_file=plan_file,
        plan_api_path=f"${{XFER}}/{plan_file}",
        report_file=f"{directory}/{report}",
    )


def submit_zap_automation_plan(
    settings: ZapConnectorSettings,
    api_key: str,
    job_id: str,
    plan: ReviewedZapAutomationPlan,
) -> str:
    """Upload one reviewed plan and return ZAP's strictly validated plan id."""
    paths = zap_transfer_paths(job_id, plan.summary.report_file)
    if not plan.yaml_bytes or len(plan.yaml_bytes) > _MAX_PLAN_BYTES:
        raise ZapTransportError("zap_plan_invalid", "The reviewed ZAP plan is invalid")
    try:
        plan_text = plan.yaml_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ZapTransportError("zap_plan_invalid", "The reviewed ZAP plan is invalid") from exc
    uploaded = zap_json_request(
        settings,
        api_key,
        "/OTHER/core/other/fileUpload/",
        form={"fileName": paths.plan_file, "fileContents": plan_text},
    )
    upload_confirmation = uploaded.get("Uploaded")
    if not isinstance(upload_confirmation, str) or not upload_confirmation.strip():
        raise ZapTransportError(
            "zap_response_invalid",
            "ZAP did not confirm the plan upload",
        )
    submitted = zap_json_request(
        settings,
        api_key,
        "/JSON/automation/action/runPlan/",
        query={"filePath": paths.plan_api_path},
    )
    plan_id = str(submitted.get("planId") or "").strip()
    if set(submitted) != {"planId"} or not _PLAN_ID_RE.fullmatch(plan_id):
        raise ZapTransportError(
            "zap_response_invalid",
            "ZAP returned an invalid plan id",
        )
    return plan_id


def fetch_zap_plan_progress(
    settings: ZapConnectorSettings,
    api_key: str,
    remote_plan_id: str,
) -> ReviewedZapRemoteProgress:
    plan_id = str(remote_plan_id or "").strip()
    if not _PLAN_ID_RE.fullmatch(plan_id):
        raise ZapTransportError("zap_plan_id_invalid", "The ZAP plan id is invalid")
    payload = zap_json_request(
        settings,
        api_key,
        "/JSON/automation/view/planProgress/",
        query={"planId": plan_id},
    )
    return review_zap_remote_progress(payload, expected_plan_id=plan_id)


def cancel_zap_automation_plan(
    settings: ZapConnectorSettings,
    api_key: str,
    remote_plan_id: str,
) -> None:
    plan_id = str(remote_plan_id or "").strip()
    if not _PLAN_ID_RE.fullmatch(plan_id):
        raise ZapTransportError("zap_plan_id_invalid", "The ZAP plan id is invalid")
    response = zap_json_request(
        settings,
        api_key,
        "/JSON/automation/action/stopPlan/",
        query={"planId": plan_id},
    )
    if response != {"Result": "OK"}:
        raise ZapTransportError(
            "zap_response_invalid",
            "ZAP did not confirm cancellation",
        )


def download_zap_report(
    settings: ZapConnectorSettings,
    api_key: str,
    job_id: str,
    report_filename: str,
) -> DownloadedZapReport:
    paths = zap_transfer_paths(job_id, report_filename)
    payload = zap_request_bytes(
        settings,
        api_key,
        "/OTHER/core/other/fileDownload/",
        query={"fileName": paths.report_file},
        max_bytes=settings.max_report_bytes,
    )
    if not payload:
        raise ZapTransportError("zap_report_invalid", "ZAP returned an empty report")
    return DownloadedZapReport(
        payload=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


__all__ = [
    "DownloadedZapReport",
    "ZapTransferPaths",
    "cancel_zap_automation_plan",
    "download_zap_report",
    "fetch_zap_plan_progress",
    "submit_zap_automation_plan",
    "zap_transfer_paths",
]
