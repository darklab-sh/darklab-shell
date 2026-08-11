# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Pure recovery and scope helpers for the ZAP worker."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from services.connectors.zap_config import ZapConnectorSettings
from services.connectors.zap_jobs import ZapJobError
from services.connectors.zap_scope_policy import (
    allowed_target_cidrs_sha256,
    review_zap_scope_policy,
)


_RECOVERY_GRACE = timedelta(minutes=5)


def inflight_zap_job_is_fresh(job: Mapping[str, Any]) -> bool:
    """Return whether an in-flight claim remains inside its recovery window."""
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


def review_zap_job_scope_policy(
    job: Mapping[str, Any],
    settings: ZapConnectorSettings,
    token: str,
) -> None:
    """Re-attest a queued job against the scanner-side scope boundary."""
    summary = job.get("plan_summary")
    targets = summary.get("targets") if isinstance(summary, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(targets, list):
        raise ZapJobError(
            "zap_scope_policy_targets_invalid",
            "Queued ZAP job is missing its reviewed targets",
        )
    expected_proxy = f"{settings.egress_proxy_host}:{settings.egress_proxy_port}"
    if (
        summary.get("scope_policy_id") != settings.scope_policy_id
        or summary.get("allowed_target_cidrs_sha256")
        != allowed_target_cidrs_sha256(settings)
        or summary.get("egress_proxy") != expected_proxy
    ):
        raise ZapJobError(
            "zap_scope_policy_changed",
            "ZAP scanner-side scope policy changed after plan review",
        )
    hosts = tuple(urlsplit(str(target)).hostname or "" for target in targets)
    review_zap_scope_policy(settings, hosts, token=token)


__all__ = ["inflight_zap_job_is_fresh", "review_zap_job_scope_policy"]
