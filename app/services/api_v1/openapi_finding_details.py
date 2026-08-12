# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI properties for the bounded finding-detail contract."""

from __future__ import annotations

from typing import Any


FINDING_DETAIL_REQUIRED = (
    "summary",
    "impact",
    "reproduction_steps",
    "confidence",
    "cve_ids",
    "cwe_ids",
    "cvss_vector",
    "cvss_score",
    "references",
)


def finding_detail_properties() -> dict[str, Any]:
    return {
        "summary": {"type": "string", "maxLength": 4000},
        "impact": {"type": "string", "maxLength": 20000},
        "reproduction_steps": {"type": "string", "maxLength": 20000},
        "confidence": {"type": "string", "enum": ["unknown", "low", "medium", "high"]},
        "cve_ids": {
            "type": "array",
            "maxItems": 50,
            "items": {"type": "string", "pattern": "^CVE-[0-9]{4}-[0-9]{4,}$"},
        },
        "cwe_ids": {
            "type": "array",
            "maxItems": 50,
            "items": {"type": "string", "pattern": "^CWE-[0-9]+$"},
        },
        "cvss_vector": {"type": "string", "maxLength": 256},
        "cvss_score": {"type": "number", "minimum": 0, "maximum": 10, "nullable": True},
        "references": {
            "type": "array",
            "maxItems": 50,
            "items": {"type": "string", "format": "uri", "maxLength": 2048},
        },
    }
