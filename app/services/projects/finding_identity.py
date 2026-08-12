# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable observation and remediation identities for saved findings."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from services.projects.finding_provenance import normalize_finding_validation_method


def owner_scope_key(finding: dict[str, Any]) -> tuple[str, str]:
    team_id = str(finding.get("team_id") or "")
    session_id = "" if team_id else str(finding.get("session_id") or "")
    return session_id, team_id


def canonical_affected_subject(finding: dict[str, Any]) -> str:
    """Return the narrowest exact affected-subject key available."""
    entity_id = str(finding.get("entity_id") or finding.get("target_id") or "").strip()
    if entity_id:
        return f"entity:{entity_id}"
    subject_key = str(finding.get("subject_key") or "").strip()
    if subject_key:
        return f"subject:{subject_key}"
    explicit = finding.get("affected_subject")
    if isinstance(explicit, dict):
        explicit_type = str(explicit.get("type") or "").strip().lower()
        explicit_value = str(
            explicit.get("canonical_value") or explicit.get("value") or ""
        ).strip()
        if explicit_type and explicit_value:
            return f"subject:{explicit_type}\x1f{explicit_value}"
    elif str(explicit or "").strip():
        return f"subject:{str(explicit).strip()}"
    observation_id = str(finding.get("id") or "").strip()
    return f"observation:{observation_id}"


def stable_rule_identity(finding: dict[str, Any]) -> str:
    """Return a stable rule key without deriving identity from editable prose."""
    persisted = str(finding.get("rule_identity") or "").strip()
    if persisted:
        return persisted[:512]
    for key in ("rule_id", "check_key", "template_id"):
        value = str(finding.get(key) or "").strip()
        if value:
            return f"{key}:{value}"[:512]
    signature_hash = str(finding.get("signature_hash") or "").strip()
    if signature_hash:
        return f"signature:{signature_hash[:512]}"
    finding_id = str(finding.get("id") or "").strip()
    return f"observation:{finding_id}"


def _identity_subject_material(finding: dict[str, Any]) -> str:
    # Preserve the established remediation hash for existing CVE findings.
    legacy_subject = str(
        finding.get("entity_id")
        or finding.get("target_id")
        or finding.get("subject_key")
        or finding.get("fingerprint")
        or ""
    )
    if legacy_subject:
        return legacy_subject
    if finding.get("affected_subject"):
        return canonical_affected_subject(finding)
    return str(finding.get("id") or "")


def remediation_identity(finding: dict[str, Any], vulnerability_or_rule: str) -> str:
    session_id, team_id = owner_scope_key(finding)
    normalized_identity = str(vulnerability_or_rule or "").strip().upper()
    material = "\x1f".join(
        (team_id, session_id, _identity_subject_material(finding), normalized_identity)
    )
    return "rmd_" + hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:32]


def observation_identity(finding: dict[str, Any], vulnerability_or_rule: str) -> str:
    session_id, team_id = owner_scope_key(finding)
    origin = str(finding.get("origin") or "").strip().lower()
    validation_method = normalize_finding_validation_method(
        finding.get("validation_method"),
        origin=origin,
    )
    material = "\x1f".join((
        team_id,
        session_id,
        _identity_subject_material(finding),
        stable_rule_identity(finding),
        str(vulnerability_or_rule or "").strip().upper(),
        validation_method,
    ))
    return "obs_" + hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:32]


def finding_identity_references(
    finding: dict[str, Any],
    vulnerability_ids: Iterable[str] = (),
) -> list[dict[str, str]]:
    """Return one observation reference per exact vulnerability or fallback rule."""
    vulnerabilities = sorted({
        str(value or "").strip().upper()
        for value in vulnerability_ids
        if str(value or "").strip()
    })
    rule_identity = stable_rule_identity(finding)
    identities = [("vulnerability", value, value) for value in vulnerabilities]
    if not identities:
        identities = [("rule", "", f"RULE:{rule_identity}")]
    validation_method = normalize_finding_validation_method(
        finding.get("validation_method"),
        origin=finding.get("origin"),
    )
    return [{
        "observation_id": observation_identity(finding, identity_value),
        "remediation_id": remediation_identity(finding, identity_value),
        "identity_kind": identity_kind,
        "vulnerability_id": vulnerability_id,
        "rule_identity": rule_identity,
        "affected_subject": canonical_affected_subject(finding),
        "validation_method": validation_method,
    } for identity_kind, vulnerability_id, identity_value in identities]
