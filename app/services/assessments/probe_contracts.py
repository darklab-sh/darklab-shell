# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral contracts for Project-scoped probe planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


PROBE_CATALOG_SCHEMA_VERSION = 1
PROBE_PLAN_SCHEMA_VERSION = 1
PROBE_PLAN_DIGEST_VERSION = 1
PROBE_POLICY_LEVELS = ("safe", "standard", "intrusive", "destructive")
PROBE_TARGET_TYPES = frozenset({"domain", "ip", "url"})
PROBE_VIEW_CAPABILITIES = frozenset()
PROBE_LAUNCH_CAPABILITIES = frozenset({"run_commands"})
PROBE_PROTECTED_CAPABILITIES = frozenset({"run_commands", "manage_secrets"})
PROBE_EXCLUSIONS = (
    "dalfox_oast",
    "nuclei_takeover_confirmation",
    "schemathesis",
    "zap",
    "oast_allocation",
    "version_cve_correlation",
)


class ProbeError(ValueError):
    """A stable error shared by probe terminal, browser, and API adapters."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: Mapping[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = dict(details or {})


@dataclass(frozen=True)
class ProbePlanRequest:
    """One caller-independent request to preview a bounded probe."""

    project_id: str
    action_id: str
    entity_id: str = ""
    target_value: str = ""
    nmap_profile: str = ""
    nuclei_profile: str = "safe"
    http_profile_id: str = ""


@dataclass(frozen=True)
class ConfirmedProbePlanRequest:
    """The only caller-controlled values accepted at probe confirmation."""

    confirmed: bool
    plan_digest: str


__all__ = [
    "ConfirmedProbePlanRequest",
    "PROBE_CATALOG_SCHEMA_VERSION",
    "PROBE_EXCLUSIONS",
    "PROBE_LAUNCH_CAPABILITIES",
    "PROBE_PLAN_DIGEST_VERSION",
    "PROBE_PLAN_SCHEMA_VERSION",
    "PROBE_POLICY_LEVELS",
    "PROBE_PROTECTED_CAPABILITIES",
    "PROBE_TARGET_TYPES",
    "PROBE_VIEW_CAPABILITIES",
    "ProbeError",
    "ProbePlanRequest",
]
