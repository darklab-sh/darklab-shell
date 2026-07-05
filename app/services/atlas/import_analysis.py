"""Atlas import preview and apply analysis helpers."""

from __future__ import annotations

from typing import Any

from services.intel.canonical import entity_signature
from services.projects.scope import shared_owner_where
from services.teams.capabilities import Capability, role_can


def normalize_options(raw_options: Any) -> dict[str, bool]:
    options = raw_options if isinstance(raw_options, dict) else {}
    return {
        "import_entities": bool(options.get("import_entities")),
        "import_findings": bool(options.get("import_findings")),
        "link_to_project": bool(options.get("link_to_project")),
        "create_project_targets": bool(options.get("create_project_targets")),
    }


def required_capabilities(options: dict[str, bool], preview_counts: dict[str, Any]) -> set[Capability]:
    required: set[Capability] = set()
    if options["import_entities"]:
        required.add(Capability.MUTATE_PROJECTS)
    if options["import_findings"]:
        required.add(Capability.TRIAGE_FINDINGS)
        if int(preview_counts.get("finding_subject_entities_to_create") or 0) > 0:
            required.add(Capability.MUTATE_PROJECTS)
    if options["link_to_project"] or options["create_project_targets"]:
        required.add(Capability.MUTATE_PROJECTS)
    return required


def required_capabilities_for_apply(options: dict[str, Any], preview_counts: dict[str, Any]) -> set[Capability]:
    return required_capabilities(normalize_options(options), preview_counts)


def available_options(*, role: str = "", is_team: bool = False, preview_counts: dict[str, Any]) -> dict[str, Any]:
    def allowed(capability: Capability) -> bool:
        return (not is_team) or role_can(role, capability)

    finding_requires_entities = int(preview_counts.get("finding_subject_entities_to_create") or 0) > 0
    import_findings_allowed = allowed(Capability.TRIAGE_FINDINGS) and (
        not finding_requires_entities or allowed(Capability.MUTATE_PROJECTS)
    )
    return {
        "import_entities": {
            "available": int(preview_counts.get("entity_valid") or 0) > 0 and allowed(Capability.MUTATE_PROJECTS),
            "requires": [Capability.MUTATE_PROJECTS.value],
        },
        "import_findings": {
            "available": int(preview_counts.get("finding_valid") or 0) > 0 and import_findings_allowed,
            "requires": [
                Capability.TRIAGE_FINDINGS.value,
                *([Capability.MUTATE_PROJECTS.value] if finding_requires_entities else []),
            ],
        },
        "link_to_project": {
            "available": allowed(Capability.MUTATE_PROJECTS),
            "requires": [Capability.MUTATE_PROJECTS.value],
        },
        "create_project_targets": {
            "available": int(preview_counts.get("project_target_candidates") or 0) > 0
            and allowed(Capability.MUTATE_PROJECTS),
            "requires": [Capability.MUTATE_PROJECTS.value],
        },
    }


def entity_key(entity: dict[str, Any]) -> tuple[str, str]:
    return str(entity.get("kind") or ""), str(entity.get("canonical_value") or entity.get("value") or "")


def target_entity_candidates(normalized_rows: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    def add(entity: Any) -> None:
        if not isinstance(entity, dict):
            return
        key = entity_key(entity)
        if key[0] in {"domain", "ip", "url"} and key[1]:
            candidates.setdefault(key, entity)

    for entity in normalized_rows.get("entities") or []:
        add(entity)
    for finding in normalized_rows.get("findings") or []:
        affected = finding.get("affected_entity") if isinstance(finding, dict) else None
        add(affected)
    return candidates


def project_target_exists(conn, project_id: str, key: tuple[str, str]) -> bool:
    entity_type, canonical_value = key
    row = conn.execute(
        "SELECT 1 FROM project_links pl "
        "JOIN entities e ON e.id = pl.entity_id "
        "WHERE pl.project_id = ? AND pl.entity_type = 'atlas_entity' "
        "AND e.type = ? AND e.canonical_value = ?",
        (project_id, entity_type, canonical_value),
    ).fetchone()
    return row is not None


def entity_id_for(conn, session_id: str, team_id: str, entity: dict[str, Any]) -> str:
    entity_type, canonical_value = entity_key(entity)
    signature_hash = entity_signature(entity_type, canonical_value)
    if team_id:
        row = conn.execute(
            "SELECT id FROM entities WHERE team_id = ? AND type = ? AND signature_hash = ?",
            (team_id, entity_type, signature_hash),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM entities WHERE session_id = ? AND team_id = '' AND type = ? AND signature_hash = ?",
            (session_id, entity_type, signature_hash),
        ).fetchone()
    return str(row["id"]) if row else ""


def finding_id_for(conn, session_id: str, team_id: str, finding: dict[str, Any]) -> str:
    signature_hash = str(finding.get("signature_hash") or "")
    if team_id:
        row = conn.execute(
            "SELECT id FROM findings WHERE team_id = ? AND signature_hash = ?",
            (team_id, signature_hash),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM findings WHERE session_id = ? AND team_id = '' AND signature_hash = ?",
            (session_id, signature_hash),
        ).fetchone()
    return str(row["id"]) if row else ""


def project_accessible(conn, session_id: str, project_id: str, *, team_id: str = "") -> bool:
    if not project_id:
        return False
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ? AND status != 'archived'",  # nosec
        (*owner_params, project_id),
    ).fetchone()
    return row is not None


def analysis_counts(conn, session_id: str, team_id: str, normalized_rows: dict[str, Any]) -> dict[str, int]:
    entities = [item for item in normalized_rows.get("entities") or [] if isinstance(item, dict)]
    findings = [item for item in normalized_rows.get("findings") or [] if isinstance(item, dict)]
    entity_keys = {entity_key(entity) for entity in entities}
    finding_entity_keys = {
        entity_key(entity)
        for finding in findings
        if isinstance((entity := finding.get("affected_entity")), dict)
    }
    target_candidates = target_entity_candidates(normalized_rows)
    all_entity_keys = sorted(entity_keys | finding_entity_keys)
    existing_entity_keys = set()
    for entity_type, canonical_value in all_entity_keys:
        if not entity_type or not canonical_value:
            continue
        probe = {"kind": entity_type, "canonical_value": canonical_value}
        if entity_id_for(conn, session_id, team_id, probe):
            existing_entity_keys.add((entity_type, canonical_value))
    existing_findings = sum(1 for finding in findings if finding_id_for(conn, session_id, team_id, finding))
    return {
        "entity_valid": len(entity_keys),
        "entity_new": len(entity_keys - existing_entity_keys),
        "entity_duplicate": len(entity_keys & existing_entity_keys),
        "finding_valid": len(findings),
        "finding_new": max(0, len(findings) - existing_findings),
        "finding_duplicate": existing_findings,
        "finding_subject_entities_to_create": len(finding_entity_keys - existing_entity_keys),
        "project_target_candidates": len(target_candidates),
    }


def preview_counts(parse_payload: dict[str, Any], analysis: dict[str, int]) -> dict[str, Any]:
    raw_entities = parse_payload.get("entities")
    raw_findings = parse_payload.get("findings")
    raw_warnings = parse_payload.get("warnings")
    entities: list[Any] = raw_entities if isinstance(raw_entities, list) else []
    findings: list[Any] = raw_findings if isinstance(raw_findings, list) else []
    warnings: list[Any] = raw_warnings if isinstance(raw_warnings, list) else []
    return {
        "rows": int(parse_payload.get("row_count") or 0),
        "skipped": int(parse_payload.get("skipped_count") or 0),
        "valid": len(entities) + len(findings),
        "warnings": len(warnings),
        "duplicate": int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"]),
        "new": int(analysis["entity_new"]) + int(analysis["finding_new"]),
        "updated": int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"]),
        **analysis,
    }


def current_apply_counts(
    conn,
    session_id: str,
    team_id: str,
    normalized_rows: dict[str, Any],
    preview_counts_payload: dict[str, Any],
) -> dict[str, Any]:
    counts = dict(preview_counts_payload)
    analysis = analysis_counts(conn, session_id, team_id, normalized_rows)
    counts.update(analysis)
    counts["duplicate"] = int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"])
    counts["new"] = int(analysis["entity_new"]) + int(analysis["finding_new"])
    counts["updated"] = int(analysis["entity_duplicate"]) + int(analysis["finding_duplicate"])
    return counts


def entity_occurrence_stats(
    normalized_rows: dict[str, Any],
    options: dict[str, bool],
    now: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    stats: dict[tuple[str, str], dict[str, Any]] = {}

    def add(entity: dict[str, Any]) -> None:
        key = entity_key(entity)
        entity_type, canonical_value = key
        if not entity_type or not canonical_value:
            return
        observed_at = str(entity.get("observed_at") or now)
        current = stats.get(key)
        if current is None:
            stats[key] = {
                "count": 1,
                "first_observed_at": observed_at,
                "last_observed_at": observed_at,
                "row_number": int(entity.get("row_number") or 0),
                "row_numbers": {int(entity.get("row_number") or 0)} if int(entity.get("row_number") or 0) > 0 else set(),
                "external_id": str(entity.get("external_id") or ""),
                "source_detail": entity.get("source_detail") if isinstance(entity.get("source_detail"), dict) else {},
            }
            return
        row_number = int(entity.get("row_number") or 0)
        row_numbers = current["row_numbers"] if isinstance(current.get("row_numbers"), set) else set()
        if row_number > 0 and row_number in row_numbers:
            return
        if row_number > 0:
            row_numbers.add(row_number)
            current["row_numbers"] = row_numbers
        current["count"] = int(current["count"]) + 1
        if observed_at < str(current["first_observed_at"]):
            current["first_observed_at"] = observed_at
            current["row_number"] = row_number
        if observed_at > str(current["last_observed_at"]):
            current["last_observed_at"] = observed_at
        if not current["external_id"] and entity.get("external_id"):
            current["external_id"] = str(entity.get("external_id") or "")
        if not current["source_detail"] and isinstance(entity.get("source_detail"), dict):
            current["source_detail"] = entity.get("source_detail")

    if options["import_entities"] or options["create_project_targets"]:
        for entity in normalized_rows.get("entities") or []:
            if isinstance(entity, dict):
                add(entity)
    if options["import_findings"] or options["create_project_targets"]:
        for finding in normalized_rows.get("findings") or []:
            affected = finding.get("affected_entity") if isinstance(finding, dict) else None
            if isinstance(affected, dict):
                add(affected)
    return stats
