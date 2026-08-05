# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fields for shared finding remediation dispositions."""

from __future__ import annotations

from typing import Any


def finding_disposition_properties() -> dict[str, Any]:
    return {
        "review_state": {"type": "string"},
        "review_state_source": {
            "type": "string",
            "enum": ["observation", "remediation_group"],
        },
        "disposition_updated_at": {"type": "string"},
        "has_remediation": {"type": "boolean"},
        "remediation_preview": {"type": "string"},
        "remediation_source": {
            "type": "string",
            "enum": ["observation", "remediation_group"],
        },
        "remediation_updated_at": {"type": "string"},
    }
