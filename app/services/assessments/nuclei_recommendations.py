# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explain bounded Nuclei recommendations from saved assessment evidence."""

from __future__ import annotations

from typing import Any

from services.assessments.nuclei_recommendation_evidence import (
    NucleiTargetSignals,
    load_nuclei_recommendation_signals,
)
from services.assessments.nuclei_takeover_contracts import NUCLEI_TAKEOVER_CHECK_KEY


_STANDARD_CHECK_KEY = "vulnerability_templates"
_INTRUSIVE_CHECK_KEY = "intrusive_template_validation"


def attach_nuclei_recommendations(
    conn: Any,
    checks: list[dict[str, Any]],
    *,
    session_id: str,
    team_id: str,
    project_id: str,
) -> None:
    """Attach read-only recommendations to Nuclei checks in one bounded page."""
    relevant = [
        check for check in checks
        if check.get("recommended_action_key") == "command:nuclei"
    ]
    if not relevant:
        return
    targets = list({
        str(check.get("target_entity_id") or ""): {
            "entity_id": str(check.get("target_entity_id") or ""),
            "type": str(check.get("target_type") or ""),
            "value": str(check.get("target_value") or ""),
        }
        for check in relevant
        if str(check.get("target_entity_id") or "")
    }.values())
    signals = load_nuclei_recommendation_signals(
        conn, session_id, team_id, project_id, targets,
    )
    for check in relevant:
        signal = signals.get(
            str(check.get("target_entity_id") or ""), NucleiTargetSignals(),
        )
        check["nuclei_recommendation"] = _recommendation(check, signal)


def _recommendation(
    check: dict[str, Any], signal: NucleiTargetSignals,
) -> dict[str, Any]:
    check_key = str(check.get("check_key") or "")
    reasons = []
    if signal.inferred_cve_count:
        reasons.append((
            "inferred_cve",
            f"{signal.inferred_cve_count} version-based CVE candidate"
            f"{'s' if signal.inferred_cve_count != 1 else ''}",
        ))
    if signal.technologies:
        reasons.append((
            "detected_technology",
            f"{len(signal.technologies)} detected technolog"
            f"{'ies' if len(signal.technologies) != 1 else 'y'}",
        ))
    if signal.services:
        reasons.append((
            "service_evidence",
            f"{len(signal.services)} identified service"
            f"{'s' if len(signal.services) != 1 else ''}",
        ))
    if check_key == NUCLEI_TAKEOVER_CHECK_KEY:
        reasons = [(
            "dangling_record",
            f"{signal.dangling_record_count} potential dangling DNS record"
            f"{'s' if signal.dangling_record_count != 1 else ''}",
        )] if signal.dangling_record_count else []
        profile_key = "safe"
    elif check_key == _STANDARD_CHECK_KEY:
        profile_key = "standard"
    else:
        reasons = []
        profile_key = "intrusive" if check_key == _INTRUSIVE_CHECK_KEY else ""
    recommended = bool(reasons)
    if recommended:
        summary = (
            f"The {profile_key} Nuclei profile is recommended from saved evidence: "
            + ", ".join(label for _code, label in reasons)
            + ". Review its exact bounds before starting a run."
        )
    elif profile_key == "intrusive":
        summary = (
            "Intrusive Nuclei checks remain a separate operator decision and are never "
            "recommended automatically from saved evidence."
        )
    else:
        summary = (
            "No compatible saved signal currently recommends this Nuclei profile. "
            "Opening the check does not start a scan."
        )
    return {
        "recommended": recommended,
        "profile_key": profile_key,
        "reason_codes": [code for code, _label in reasons],
        "summary": summary,
        "signals": {
            "technology_count": len(signal.technologies),
            "technologies": sorted(signal.technologies)[:3],
            "inferred_cve_count": signal.inferred_cve_count,
            "service_count": len(signal.services),
            "services": sorted(signal.services)[:3],
            "dangling_record_count": signal.dangling_record_count,
        },
        "source_truncated": signal.truncated,
        "launch_mode": "manual_confirmation_only",
        "auto_launch": False,
    }


__all__ = ["attach_nuclei_recommendations"]
