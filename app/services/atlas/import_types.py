# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser-neutral Atlas import contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportWarning:
    row_number: int
    code: str
    message: str


@dataclass(frozen=True)
class ImportEntity:
    row_number: int
    kind: str
    value: str
    canonical_value: str
    observed_at: str = ""
    external_id: str = ""
    source_detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportFinding:
    row_number: int
    title: str
    severity: str
    subject_key: str
    signature_hash: str
    description: str = ""
    remediation: str = ""
    evidence: str = ""
    affected_entity: ImportEntity | None = None
    external_id: str = ""
    references: list[str] = field(default_factory=list)
    observed_at: str = ""
    source_detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportEvidence:
    row_number: int
    evidence_type: str
    subject_key: str
    label: str
    external_id: str = ""
    observed_at: str = ""
    source_detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportParseResult:
    format_id: str
    row_count: int
    skipped_count: int
    entities: list[ImportEntity]
    findings: list[ImportFinding]
    evidence: list[ImportEvidence]
    warnings: list[ImportWarning]
    suppressed_warning_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_id": self.format_id,
            "row_count": self.row_count,
            "skipped_count": self.skipped_count,
            "entities": [asdict(entity) for entity in self.entities],
            "findings": [asdict(finding) for finding in self.findings],
            "evidence": [asdict(item) for item in self.evidence],
            "warnings": [asdict(warning) for warning in self.warnings],
            "suppressed_warning_count": self.suppressed_warning_count,
        }


__all__ = [
    "ImportEntity",
    "ImportEvidence",
    "ImportFinding",
    "ImportParseResult",
    "ImportWarning",
]
