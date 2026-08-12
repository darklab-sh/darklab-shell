# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable contracts for reviewable ZAP Automation Framework plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ZapPlanError(ValueError):
    """Raised when a reviewable ZAP plan cannot be generated safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ZapAutomationPlanSummary:
    policy_level: str
    authentication_role: str
    targets: tuple[str, ...]
    include_rule_count: int
    exclusion_rule_count: int
    job_types: tuple[str, ...]
    job_timeout_seconds: int
    report_file: str
    scope_policy_id: str
    allowed_target_cidrs_sha256: str
    egress_proxy: str

    def to_dict(self) -> dict[str, Any]:
        """Return the non-secret summary intended for operator review."""
        return {
            "policy_level": self.policy_level,
            "authentication_role": self.authentication_role,
            "targets": list(self.targets),
            "include_rule_count": self.include_rule_count,
            "exclusion_rule_count": self.exclusion_rule_count,
            "job_types": list(self.job_types),
            "job_timeout_seconds": self.job_timeout_seconds,
            "report_file": self.report_file,
            "scope_policy_id": self.scope_policy_id,
            "allowed_target_cidrs_sha256": self.allowed_target_cidrs_sha256,
            "egress_proxy": self.egress_proxy,
        }


@dataclass(frozen=True)
class ReviewedZapAutomationPlan:
    yaml_bytes: bytes
    summary: ZapAutomationPlanSummary
