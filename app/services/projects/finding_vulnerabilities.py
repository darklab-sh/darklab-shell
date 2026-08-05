# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalized vulnerability identifiers carried by saved findings."""

from __future__ import annotations

import re
from typing import Any


_CVE_IN_TEXT_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)


def extract_cve_ids(*values: Any) -> tuple[str, ...]:
    found: set[str] = set()
    for value in values:
        found.update(match.upper() for match in _CVE_IN_TEXT_RE.findall(str(value or "")))
    return tuple(sorted(found))


def finding_cves(finding: dict[str, Any]) -> tuple[str, ...]:
    explicit = finding.get("cve_ids")
    if isinstance(explicit, (list, tuple)):
        normalized = extract_cve_ids(*explicit)
        if normalized:
            return normalized
    return extract_cve_ids(
        finding.get("title"),
        finding.get("raw_line"),
        finding.get("fingerprint"),
        finding.get("subject_key"),
    )
