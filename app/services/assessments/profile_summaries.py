# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Privacy-safe assessment profile summaries for read surfaces."""

from typing import Any

from services.assessments.profiles import list_assessment_profiles


def list_assessment_profile_summaries() -> list[dict[str, Any]]:
    return [
        {
            "key": str(profile.get("key") or ""),
            "version": str(profile.get("version") or ""),
            "label": str(profile.get("label") or ""),
            "purpose": str(profile.get("purpose") or ""),
            "target_types": [
                str(value or "")
                for value in profile.get("target_types", [])
                if str(value or "")
            ],
            "check_count": len(profile.get("checks", [])),
        }
        for profile in list_assessment_profiles()
    ]
