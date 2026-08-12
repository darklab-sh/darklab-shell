# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Immutable, owner-safe results from one reviewed Schemathesis report."""

from __future__ import annotations

from dataclasses import dataclass


SCHEMATHESIS_REPORT_TOOL_VERSION = "4.24.3"


class SchemathesisReportError(ValueError):
    """A stable rejection for malformed, incompatible, or oversized report data."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SchemathesisFailureExample:
    """One minimized failure without request or response bodies."""

    fingerprint: str
    operation: str
    method: str
    path: str
    check_name: str
    failure_type: str
    title: str
    severity: str
    response_status: int | None
    parameter_names: tuple[str, ...]
    body_media_type: str
    example_digest: str
    message_digest: str


@dataclass(frozen=True)
class SchemathesisOperationEvidence:
    """Bounded factual coverage for one schema operation observed in the report."""

    operation: str
    method: str
    path: str
    status: str
    case_count: int
    failure_count: int
    response_statuses: tuple[int, ...]
    failures: tuple[SchemathesisFailureExample, ...]


@dataclass(frozen=True)
class SchemathesisReport:
    """Reviewed per-operation results plus immutable tool and schema provenance."""

    tool_version: str
    profile_key: str
    profile_version: str
    schema_artifact_id: str
    schema_sha256: str
    schema_version: str
    seed: int
    stop_reason: str
    running_time_seconds: float
    complete: bool
    expected_operation_count: int
    observed_operation_count: int
    case_count: int
    failure_count: int
    missing_operations: tuple[str, ...]
    operations: tuple[SchemathesisOperationEvidence, ...]


__all__ = [
    "SCHEMATHESIS_REPORT_TOOL_VERSION",
    "SchemathesisFailureExample",
    "SchemathesisOperationEvidence",
    "SchemathesisReport",
    "SchemathesisReportError",
]
