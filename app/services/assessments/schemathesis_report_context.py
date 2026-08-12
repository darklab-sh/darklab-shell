# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Typed provenance and private reader for one Schemathesis report."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import re

from services.assessments.schemathesis_report import parse_schemathesis_ndjson
from services.assessments.schemathesis_report_contracts import SchemathesisReport
from services.assessments.schemathesis_schema import ReviewedOpenApiSchema

_PROFILE_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,31}")
_SCOPE_ID_RE = re.compile(r"(?:prj|asm|ach)_[A-Za-z0-9][A-Za-z0-9_-]{2,63}")


@dataclass(frozen=True)
class ReviewedSchemathesisReportContext:
    """Bind the expected report to its reviewed schema and profile snapshot."""
    schema: ReviewedOpenApiSchema
    project_id: str
    assessment_id: str
    check_id: str
    profile_key: str
    profile_version: str
    read_report: Callable[[], bytes] = field(repr=False, compare=False)
    def __post_init__(self) -> None:
        if (
            type(self.schema) is not ReviewedOpenApiSchema
            or not all(_SCOPE_ID_RE.fullmatch(str(value or "")) for value in (self.project_id, self.assessment_id, self.check_id))
            or not _PROFILE_RE.fullmatch(str(self.profile_key or ""))
            or not _VERSION_RE.fullmatch(str(self.profile_version or ""))
            or not callable(self.read_report)
        ):
            raise ValueError("invalid reviewed Schemathesis report context")

    def parse(self) -> SchemathesisReport:
        return parse_schemathesis_ndjson(self.read_report(), self.schema, profile_key=self.profile_key,
            profile_version=self.profile_version)


__all__ = ["ReviewedSchemathesisReportContext"]
