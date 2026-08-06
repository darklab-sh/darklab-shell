# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project entity label and note helpers.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import config as _config
from core.database import validate_project_entity_type
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.atlas.scope import (
    entity_exists_in_scope,
    finding_exists_in_scope,
    finding_source_scope_params,
    finding_source_scope_sql,
    metadata_owner_id,
)
from services.projects.contracts import (
    ENTITY_METADATA_TYPES,
    MAX_ENTITY_ID_LEN,
    MAX_ENTITY_NOTE_BODY_LEN,
    MAX_FINDING_REMEDIATION_LEN,
    MAX_FINDING_VERIFICATION_NOTES_LEN,
    MAX_FINDING_VERIFICATION_STEPS_LEN,
    MAX_LABEL_LEN,
    MAX_PROJECT_NOTES_LEN,
    FINDING_VERIFICATION_STATES,
    ProjectWorkspaceError,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.finding_details import finding_detail_fields
from services.projects.finding_dispositions import (
    remediation_guidance_by_finding_id,
    set_remediation_group_guidance,
)
from services.projects.scope import normalize_team_id, shared_owner_where
from services.projects.utils import text_exceeds_limit as _text_exceeds_limit, trim_text as _trim_text
from services.teams.scope import team_owner_context
from services.workspace.files import WorkspaceError, resolve_owner_workspace_path, resolve_workspace_path


_FINAL_VERIFICATION_STATES = frozenset({"verified", "needs_retest", "not_applicable"})


def _cfg_int(key, default, *, cfg=None):
    cfg = _config.resolve_effective_cfg(cfg)
    try:
        value = int(cfg.get(key, default))
    except (AttributeError, TypeError, ValueError):
        value = default
    return max(0, value)


def _quota_exceeded(count, key, default):
    limit = _cfg_int(key, default)
    return limit > 0 and count >= limit


def _raise_quota(message):
    raise ProjectWorkspaceQuotaExceeded(message)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _label_order_sql() -> str:
    return dialect_for_backend(get_db_backend()).case_insensitive_order("label") + ", created ASC"


def _new_entity_label_id() -> str:
    return "lbl_" + secrets.token_hex(8)


def _new_entity_note_id() -> str:
    return "note_" + secrets.token_hex(8)


def _new_finding_triage_id() -> str:
    return "ftri_" + secrets.token_hex(8)


def _row_to_label(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }
    if hasattr(row, "keys") and "team_id" in row.keys():
        item["team_id"] = row["team_id"] or ""
    return item


def _row_to_entity_note(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "session_id": row["session_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "body": row["body"],
        "created": row["created"],
        "updated": row["updated"],
    }
    if hasattr(row, "keys") and "team_id" in row.keys():
        item["team_id"] = row["team_id"] or ""
    return item


def _row_to_finding_triage(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "session_id": row["session_id"],
        "finding_id": row["finding_id"],
        "remediation": row["remediation"],
        "verification_steps": row["verification_steps"],
        "verification_status": row["verification_status"],
        "verification_notes": row["verification_notes"],
        "created": row["created"],
        "updated": row["updated"],
    }
    if hasattr(row, "keys") and "team_id" in row.keys():
        item["team_id"] = row["team_id"] or ""
    row_keys = set(row.keys()) if hasattr(row, "keys") else set()
    disposition_at = (
        str(row["verification_updated_at"] or "")
        if "verification_updated_at" in row_keys
        else ""
    )
    if item["verification_status"] in _FINAL_VERIFICATION_STATES and disposition_at:
        member_id = (
            str(row["verification_updated_by_member_id"] or "")
            if "verification_updated_by_member_id" in row_keys
            else ""
        )
        display_name = (
            str(row["verification_actor_display_name"] or "")
            if "verification_actor_display_name" in row_keys
            else ""
        )
        actor = {"kind": "team_member", "member_id": member_id}
        if display_name:
            actor["display_name"] = display_name
        if not member_id:
            actor = {"kind": "session"}
        item["verification_disposition"] = {
            "status": item["verification_status"],
            "actor": actor,
            "updated_at": disposition_at,
        }
    else:
        item["verification_disposition"] = None
    return item


def _metadata_row_owner_values(session_id, team_id=""):
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return str(session_id or "").strip() or normalized_team_id, normalized_team_id
    return str(session_id or "").strip(), ""


def _metadata_owner_where(session_id, team_id="", *, table_alias=""):
    prefix = f"{table_alias}." if table_alias else ""
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        legacy_session_id = _metadata_session_id(session_id, normalized_team_id)
        return (
            f"({prefix}team_id = ? OR "
            f"(({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?))",
            (normalized_team_id, legacy_session_id),
        )
    return (
        f"{prefix}session_id = ? AND {prefix}team_id = ''",
        (str(session_id or "").strip(),),
    )


def finding_triage_verification_status_filter_sql_and_params(
    session_id: str,
    statuses: list[str],
    *,
    team_id: str = "",
    table_alias: str = "filter_triage",
    finding_alias: str = "f",
) -> tuple[str, list[str]]:
    if not statuses:
        return "", []
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id, table_alias=table_alias)
    placeholders = ",".join("?" for _ in statuses)
    triage_prefix = f"{table_alias}." if table_alias else ""
    finding_prefix = f"{finding_alias}." if finding_alias else ""
    finding_match_sql = f"{triage_prefix}finding_id = {finding_prefix}id"
    if "not_started" in statuses:
        return (
            "("
            "NOT EXISTS ("
            f"  SELECT 1 FROM finding_triage_details {table_alias} "
            f"  WHERE {owner_sql} AND {finding_match_sql}"
            ") "
            "OR EXISTS ("
            f"  SELECT 1 FROM finding_triage_details {table_alias} "
            f"  WHERE {owner_sql} AND {finding_match_sql} "
            f"  AND {triage_prefix}verification_status IN ({placeholders})"  # nosec
            ")"
            ")",
            [*owner_params, *owner_params, *statuses],
        )
    return (
        "EXISTS ("
        f"  SELECT 1 FROM finding_triage_details {table_alias} "
        f"  WHERE {owner_sql} AND {finding_match_sql} "
        f"  AND {triage_prefix}verification_status IN ({placeholders})"  # nosec
        ")",
        [*owner_params, *statuses],
    )


def _count_entity_metadata_for_ids(conn, table, entity_type, entity_ids, *, session_id="", team_id=""):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    params = [entity_type, *values]
    owner_sql = ""
    owner_params: tuple[str, ...] = ()
    if session_id or team_id:
        owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM {table} "  # nosec
        f"WHERE entity_type = ? AND entity_id IN ({placeholders})"
        + (f" AND {owner_sql}" if owner_sql else ""),
        [*params, *owner_params],
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _metadata_session_id(session_id, team_id=""):
    return metadata_owner_id(session_id, team_id)


def _entity_labels_by_id(conn, session_id, entity_type, entity_ids, *, team_id=""):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return {}
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "  # nosec
        "FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY " + _label_order_sql(),
        [*owner_params, entity_type, *values],
    ).fetchall()
    grouped = {value: [] for value in values}
    seen = set()
    for row in rows:
        dedupe_key = (str(row["entity_id"]), str(row["label"]))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        grouped.setdefault(str(row["entity_id"]), []).append(_row_to_label(row))
    return grouped


def _entity_notes_by_id(conn, session_id, entity_type, entity_ids, *, team_id=""):
    values = [str(value) for value in entity_ids if value]
    if not values:
        return {}
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "  # nosec
        "FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? "
        f"AND entity_id IN ({placeholders})",
        [*owner_params, entity_type, *values],
    ).fetchall()
    return {str(row["entity_id"]): _row_to_entity_note(row) for row in rows}


def _finding_triage_by_id(conn, session_id, finding_ids, *, team_id=""):
    values = [str(value) for value in finding_ids if value]
    if not values:
        return {}
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT id, session_id, team_id, finding_id, remediation, verification_steps, "
        "verification_status, verification_notes, verification_updated_by_member_id, "
        "verification_updated_at, "
        "COALESCE((SELECT display_name FROM team_members WHERE id = "
        "finding_triage_details.verification_updated_by_member_id), '') "
        "AS verification_actor_display_name, created, updated "
        "FROM finding_triage_details WHERE " + owner_sql + f" AND finding_id IN ({placeholders})",  # nosec
        [*owner_params, *values],
    ).fetchall()
    return {str(row["finding_id"]): _row_to_finding_triage(row) for row in rows}


def _full_finding_triage_by_id(conn, session_id, finding_ids, *, team_id=""):
    values = [str(value) for value in finding_ids if value]
    if not values:
        return {}
    scope_sql = finding_source_scope_sql("f", team_id)
    scope_params = finding_source_scope_params(session_id, team_id)
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT f.id, f.session_id, f.team_id, f.entity_id, f.target_id, "  # nosec B608
        "f.subject_key, f.signature_hash, f.origin, f.validation_method, f.status, "
        "f.kind, f.tool_root, f.title, f.raw_line, f.fingerprint, f.cve_ids_json "
        "FROM findings f WHERE " + scope_sql + f" AND f.id IN ({placeholders})",
        [*scope_params, *values],
    ).fetchall()
    findings = [{**dict(row), **finding_detail_fields(row)} for row in rows]
    if not findings:
        return {}
    from services.cve_risk.ranking import attach_risk_to_findings

    normalized_team_id = normalize_team_id(team_id)
    owner_by_finding_id = {
        str(row["id"]): (
            ("", normalized_team_id)
            if normalized_team_id
            else (str(row["session_id"] or ""), str(row["team_id"] or ""))
        )
        for row in rows
    }
    attach_risk_to_findings(
        findings,
        conn=conn,
        owner_by_finding_id=owner_by_finding_id,
    )
    guidance_by_id = remediation_guidance_by_finding_id(
        conn,
        findings,
        owner_by_finding_id=owner_by_finding_id,
    )
    triage_by_id = _finding_triage_by_id(
        conn,
        session_id,
        values,
        team_id=team_id,
    )
    combined = {}
    for finding in findings:
        finding_id = str(finding.get("id") or "")
        finding["remediation_guidance"] = guidance_by_id.get(finding_id, "")
        triage = _triage_with_remediation_guidance(
            finding,
            triage_by_id.get(finding_id),
            session_id=session_id,
            team_id=team_id,
        )
        if triage:
            combined[finding_id] = triage
    return combined


def default_finding_triage_details(session_id, finding_id, *, team_id=""):
    item = {
        "id": "",
        "session_id": str(session_id or "").strip(),
        "finding_id": str(finding_id or "").strip(),
        "remediation": "",
        "verification_steps": "",
        "verification_status": "not_started",
        "verification_notes": "",
        "created": "",
        "updated": "",
        "remediation_id": "",
        "remediation_group_id": "",
        "remediation_group_merged": False,
        "remediation_group_member_count": 1,
        "remediation_source": "observation",
        "remediation_updated_at": "",
        "verification_disposition": None,
    }
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        item["session_id"] = _metadata_session_id(session_id, normalized_team_id)
        item["team_id"] = normalized_team_id
    else:
        item["team_id"] = ""
    return item


def _text_preview(value, limit=160):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def compact_finding_triage_details(triage):
    item = triage if isinstance(triage, dict) else {}
    remediation = str(item.get("remediation") or "")
    verification_steps = str(item.get("verification_steps") or "")
    verification_notes = str(item.get("verification_notes") or "")
    return {
        "verification_status": str(item.get("verification_status") or "not_started"),
        "has_remediation": bool(remediation.strip()),
        "has_verification_steps": bool(verification_steps.strip()),
        "has_verification_notes": bool(verification_notes.strip()),
        "remediation_preview": _text_preview(remediation),
        "verification_steps_preview": _text_preview(verification_steps),
        "remediation_id": str(item.get("remediation_id") or ""),
        "remediation_group_id": str(item.get("remediation_group_id") or ""),
        "remediation_group_merged": bool(item.get("remediation_group_merged")),
        "remediation_group_member_count": int(
            item.get("remediation_group_member_count") or 1
        ),
        "remediation_source": str(item.get("remediation_source") or "observation"),
        "remediation_updated_at": str(item.get("remediation_updated_at") or ""),
        "verification_disposition": (
            dict(item["verification_disposition"])
            if isinstance(item.get("verification_disposition"), dict)
            else None
        ),
    }


def _triage_with_remediation_guidance(finding, triage, *, session_id="", team_id=""):
    base = dict(triage) if isinstance(triage, dict) else default_finding_triage_details(
        session_id,
        str(finding.get("id") or ""),
        team_id=team_id,
    )
    remediation_id = str(finding.get("remediation_id") or "")
    reference = next(
        (
            item
            for item in finding.get("observation_references", [])
            if isinstance(item, dict)
            and str(item.get("remediation_id") or "") == remediation_id
        ),
        {},
    )
    source = str(reference.get("remediation_source") or "observation")
    if source == "remediation_group":
        base["remediation"] = str(
            finding.get("remediation_guidance")
            if "remediation_guidance" in finding
            else reference.get("remediation_preview") or ""
        )
    base["remediation_id"] = remediation_id
    base["remediation_group_id"] = str(
        reference.get("remediation_group_id") or remediation_id
    )
    base["remediation_group_merged"] = bool(
        reference.get("remediation_group_merged")
    )
    base["remediation_group_member_count"] = int(
        reference.get("remediation_group_member_count") or 1
    )
    base["remediation_source"] = source
    base["remediation_updated_at"] = str(
        reference.get("remediation_updated_at") or ""
    )
    if (
        not str(base.get("remediation") or "").strip()
        and not str(base.get("verification_steps") or "").strip()
        and str(base.get("verification_status") or "not_started") == "not_started"
        and not str(base.get("verification_notes") or "").strip()
    ):
        return None
    return base


def attach_finding_triage_details(conn, session_id, findings, *, team_id=""):
    items = [finding for finding in findings if finding]
    if not items:
        return items
    finding_ids = [str(finding.get("id") or "") for finding in items if finding.get("id")]
    triage_map = _finding_triage_by_id(conn, session_id, finding_ids, team_id=team_id)
    for finding in items:
        triage = triage_map.get(str(finding.get("id") or ""))
        combined = _triage_with_remediation_guidance(
            finding,
            triage,
            session_id=session_id,
            team_id=team_id,
        )
        finding["triage"] = compact_finding_triage_details(combined)
        finding["verification_status"] = finding["triage"]["verification_status"]
    return items


def _attach_project_notes(conn, session_id, projects, *, team_id=""):
    items = [project for project in projects if project]
    if not items:
        return items
    note_map = _entity_notes_by_id(conn, session_id, "project", [project["id"] for project in items], team_id=team_id)
    for project in items:
        project["note"] = note_map.get(str(project["id"]))
    return items


def _attach_project_labels(conn, session_id, projects, *, team_id=""):
    items = [project for project in projects if project]
    if not items:
        return items
    label_map = _entity_labels_by_id(conn, session_id, "project", [project["id"] for project in items], team_id=team_id)
    for project in items:
        project["labels"] = label_map.get(str(project["id"]), [])
    return items


def _attach_package_metadata(conn, session_id, packages, *, team_id=""):
    items = [package for package in packages if package]
    if not items:
        return items
    package_ids = [package["id"] for package in items]
    label_map = _entity_labels_by_id(conn, session_id, "package", package_ids, team_id=team_id)
    note_map = _entity_notes_by_id(conn, session_id, "package", package_ids, team_id=team_id)
    for package in items:
        package_id = str(package["id"])
        package["labels"] = label_map.get(package_id, [])
        package["note"] = note_map.get(package_id)
    return items


def _attach_target_metadata(conn, session_id, targets, *, team_id=""):
    items = [target for target in targets if target]
    if not items:
        return items
    target_ids = [target["id"] for target in items]
    label_map = _entity_labels_by_id(conn, session_id, "atlas_entity", target_ids, team_id=team_id)
    legacy_label_map = _entity_labels_by_id(conn, session_id, "target", target_ids, team_id=team_id)
    note_map = _entity_notes_by_id(conn, session_id, "atlas_entity", target_ids, team_id=team_id)
    legacy_note_map = _entity_notes_by_id(conn, session_id, "target", target_ids, team_id=team_id)
    for target in items:
        target_id = str(target["id"])
        target["labels"] = [*label_map.get(target_id, []), *legacy_label_map.get(target_id, [])]
        target["note"] = note_map.get(target_id) or legacy_note_map.get(target_id)
    return items


def _save_project_note(conn, session_id, project_id, notes, *, team_id=""):
    body = _trim_text(notes, MAX_PROJECT_NOTES_LEN)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    now = _now()
    if not body:
        conn.execute(
            "DELETE FROM entity_notes WHERE " + owner_sql + " AND entity_type = 'project' AND entity_id = ?",  # nosec
            (*owner_params, project_id),
        )
        return
    existing = conn.execute(
        "SELECT id FROM entity_notes WHERE " + owner_sql + " AND entity_type = 'project' AND entity_id = ?",  # nosec
        (*owner_params, project_id),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE entity_notes SET session_id = ?, team_id = ?, body = ?, updated = ? WHERE id = ?",
            (metadata_session, metadata_team_id, body, now, existing["id"]),
        )
        return
    count_sql, count_params = _metadata_owner_where(session_id, team_id)
    session_count = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_notes WHERE " + count_sql,  # nosec
        count_params,
    ).fetchone()
    if _quota_exceeded(
        int(session_count["count"] or 0) if session_count else 0,
        "max_entity_notes_per_session",
        2000,
    ):
        _raise_quota("note quota exceeded for this session")
    for _ in range(10):
        note_id = _new_entity_note_id()
        result = conn.execute(
            "INSERT INTO entity_notes "
            "(id, session_id, team_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, ?, 'project', ?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (note_id, metadata_session, metadata_team_id, project_id, body, now, now),
        )
        if result.rowcount:
            return
    raise ProjectWorkspaceError("could not allocate an entity note id")


def _normalize_metadata_target(entity_type, entity_id):
    try:
        entity_type = validate_project_entity_type(_trim_text(entity_type, 64))
    except ValueError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    if entity_type not in ENTITY_METADATA_TYPES:
        raise ProjectWorkspaceError(f"entity metadata does not support {entity_type}")
    if entity_type == "target":
        entity_type = "atlas_entity"
    entity_id = _trim_text(entity_id, MAX_ENTITY_ID_LEN)
    if not entity_id:
        raise ProjectWorkspaceError("entity_id is required")
    return entity_type, entity_id


def _normalize_label_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("label payload must be an object")
    label = _trim_text(data.get("label"), MAX_LABEL_LEN)
    if not label:
        raise ProjectWorkspaceError("label is required")
    return label


def _normalize_entity_note_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("note payload must be an object")
    clean = {}
    if "body" in data or not partial:
        body = _trim_text(data.get("body"), MAX_ENTITY_NOTE_BODY_LEN)
        if not body:
            raise ProjectWorkspaceError("note body is required")
        clean["body"] = body
    return clean


def _normalize_finding_triage_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("finding triage payload must be an object")
    verification_status = _trim_text(data.get("verification_status") or "not_started", 64)
    if verification_status not in FINDING_VERIFICATION_STATES:
        raise ProjectWorkspaceError("invalid verification_status")
    for field, limit in (
        ("remediation", MAX_FINDING_REMEDIATION_LEN),
        ("verification_steps", MAX_FINDING_VERIFICATION_STEPS_LEN),
        ("verification_notes", MAX_FINDING_VERIFICATION_NOTES_LEN),
    ):
        if _text_exceeds_limit(data.get(field), limit):
            raise ProjectWorkspaceError(f"{field} exceeds maximum length")
    return {
        "remediation": _trim_text(data.get("remediation"), MAX_FINDING_REMEDIATION_LEN),
        "verification_steps": _trim_text(data.get("verification_steps"), MAX_FINDING_VERIFICATION_STEPS_LEN),
        "verification_status": verification_status,
        "verification_notes": _trim_text(data.get("verification_notes"), MAX_FINDING_VERIFICATION_NOTES_LEN),
    }


def _finding_triage_payload_is_empty(payload):
    return (
        not payload["remediation"]
        and not payload["verification_steps"]
        and payload["verification_status"] == "not_started"
        and not payload["verification_notes"]
    )


def _finding_belongs_to_scope(conn, session_id, finding_id, *, team_id=""):
    return finding_exists_in_scope(conn, session_id, finding_id, team_id=team_id)


def _workspace_file_belongs_to_session(session_id, entity_id, *, team_id=""):
    try:
        normalized_team_id = normalize_team_id(team_id)
        if normalized_team_id:
            path = resolve_owner_workspace_path(
                team_owner_context(normalized_team_id, actor_session_id=session_id),
                entity_id,
                _config.CFG,
            )
        else:
            path = resolve_workspace_path(session_id, entity_id, _config.CFG)
        return path.is_file()
    except (OSError, WorkspaceError):
        return False


def _shared_record_exists(conn, session_id, table, entity_id, *, team_id=""):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE {owner_sql} AND id = ?",  # nosec
        (*owner_params, entity_id),
    ).fetchone()
    return row is not None


def _entity_belongs_to_session(conn, session_id, entity_type, entity_id, *, team_id=""):
    normalized_team_id = normalize_team_id(team_id)
    if entity_type == "workspace_file":
        return _workspace_file_belongs_to_session(session_id, entity_id, team_id=normalized_team_id)
    if entity_type in {"atlas_entity", "target"}:
        return entity_exists_in_scope(conn, session_id, entity_id, team_id=normalized_team_id)
    elif entity_type == "project":
        return _shared_record_exists(conn, session_id, "projects", entity_id, team_id=normalized_team_id)
    elif entity_type == "run":
        return _shared_record_exists(conn, session_id, "runs", entity_id, team_id=normalized_team_id)
    elif entity_type == "snapshot":
        return _shared_record_exists(conn, session_id, "snapshots", entity_id, team_id=normalized_team_id)
    elif entity_type == "run_file_artifact":
        if normalized_team_id:
            row = conn.execute(
                "SELECT 1 FROM run_file_artifacts rfa "
                "JOIN runs r ON r.id = rfa.run_id "
                "WHERE r.team_id = ? AND rfa.id = ?",
                (normalized_team_id, entity_id),
            ).fetchone()
            return row is not None
        row = conn.execute(
            "SELECT 1 FROM run_file_artifacts WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
        return row is not None
    elif entity_type == "finding":
        return finding_exists_in_scope(conn, session_id, entity_id, team_id=normalized_team_id)
    elif entity_type == "package":
        if normalized_team_id:
            row = conn.execute(
                "SELECT 1 FROM evidence_packages WHERE team_id = ? AND id = ?",
                (normalized_team_id, entity_id),
            ).fetchone()
            return row is not None
        row = conn.execute(
            "SELECT 1 FROM evidence_packages WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
        return row is not None
    else:
        return False
    return row is not None


def list_entity_labels(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with get_db_connect()() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        rows = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ? "
            "ORDER BY " + _label_order_sql(),
            (*owner_params, entity_type, entity_id),
        ).fetchall()
    labels = []
    seen = set()
    for row in rows:
        label = str(row["label"])
        if label in seen:
            continue
        seen.add(label)
        labels.append(_row_to_label(row))
    return labels


def add_entity_label(session_id, entity_type, entity_id, data, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    created = _now()
    with get_db_connect()() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? "
            "AND entity_id = ? AND label = ?",
            [*owner_params, entity_type, entity_id, label],
        ).fetchone()
        if row:
            if normalize_team_id(team_id) and str(row["team_id"] or "") != metadata_team_id:
                conn.execute(
                    "UPDATE entity_labels SET session_id = ?, team_id = ? WHERE id = ?",
                    (metadata_session, metadata_team_id, row["id"]),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "
                    "FROM entity_labels WHERE id = ?",
                    (row["id"],),
                ).fetchone()
            return _row_to_label(row)
        count_sql, count_params = _metadata_owner_where(session_id, team_id)
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels WHERE " + count_sql,  # nosec
            count_params,
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_labels_per_session",
            5000,
        ):
            _raise_quota("label quota exceeded for this session")
        entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_labels "
            "WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            [*owner_params, entity_type, entity_id],
        ).fetchone()
        if _quota_exceeded(
            int(entity_count["count"] or 0) if entity_count else 0,
            "max_entity_labels_per_entity",
            20,
        ):
            _raise_quota("label quota exceeded for this entity")
        for _ in range(10):
            label_id = _new_entity_label_id()
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, team_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?, 'manual', ?)",
                (label_id, metadata_session, metadata_team_id, entity_type, entity_id, label, created),
            )
            row = conn.execute(
                "SELECT id, session_id, team_id, entity_type, entity_id, label, source, created "
                "FROM entity_labels WHERE id = ?",
                [label_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_label(row)
        raise ProjectWorkspaceError("could not allocate an entity label id")


def delete_entity_label(session_id, entity_type, entity_id, data, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    label = _normalize_label_payload(data)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with get_db_connect()() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_labels WHERE " + owner_sql + " AND entity_type = ? "  # nosec
            "AND entity_id = ? AND label = ?",
            (*owner_params, entity_type, entity_id, label),
        )
        conn.commit()
    return result.rowcount > 0


def entity_metadata_target_exists(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    with get_db_connect()() as conn:
        return _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id)


def get_entity_note(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with get_db_connect()() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        row = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
            "FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            (*owner_params, entity_type, entity_id),
        ).fetchone()
    return _row_to_entity_note(row)


def upsert_entity_note(session_id, entity_type, entity_id, data, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    payload = _normalize_entity_note_payload(data)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    now = _now()
    with get_db_connect()() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        existing = conn.execute(
            "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
            "FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            [*owner_params, entity_type, entity_id],
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE entity_notes SET session_id = ?, team_id = ?, body = ?, updated = ? WHERE id = ?",
                (metadata_session, metadata_team_id, payload["body"], now, existing["id"]),
            )
            row = conn.execute(
                "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
                "FROM entity_notes WHERE id = ?",
                [existing["id"]],
            ).fetchone()
            conn.commit()
            return _row_to_entity_note(row)
        count_sql, count_params = _metadata_owner_where(session_id, team_id)
        session_count = conn.execute(
            "SELECT COUNT(*) AS count FROM entity_notes WHERE " + count_sql,  # nosec
            count_params,
        ).fetchone()
        if _quota_exceeded(
            int(session_count["count"] or 0) if session_count else 0,
            "max_entity_notes_per_session",
            2000,
        ):
            _raise_quota("note quota exceeded for this session")
        for _ in range(10):
            note_id = _new_entity_note_id()
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, team_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    metadata_session,
                    metadata_team_id,
                    entity_type,
                    entity_id,
                    payload["body"],
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, team_id, entity_type, entity_id, body, created, updated "
                "FROM entity_notes WHERE id = ?",
                [note_id],
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_entity_note(row)
        raise ProjectWorkspaceError("could not allocate an entity note id")


def delete_entity_note(session_id, entity_type, entity_id, *, team_id=""):
    entity_type, entity_id = _normalize_metadata_target(entity_type, entity_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with get_db_connect()() as conn:
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id, team_id=team_id):
            return None
        result = conn.execute(
            "DELETE FROM entity_notes WHERE " + owner_sql + " AND entity_type = ? AND entity_id = ?",  # nosec
            (*owner_params, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0


def get_finding_triage_details(session_id, finding_id, *, team_id=""):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding_id is required")
    with get_db_connect()() as conn:
        if not _finding_belongs_to_scope(conn, session_id, finding_id, team_id=team_id):
            return None
        return _finding_triage_details_on_conn(
            conn,
            session_id,
            finding_id,
            team_id=team_id,
        )


def _finding_triage_details_on_conn(conn, session_id, finding_id, *, team_id=""):
    return _full_finding_triage_by_id(
        conn,
        session_id,
        [finding_id],
        team_id=team_id,
    ).get(finding_id)


def finding_triage_target_exists(session_id, finding_id, *, team_id=""):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding_id is required")
    with get_db_connect()() as conn:
        return _finding_belongs_to_scope(conn, session_id, finding_id, team_id=team_id)


def upsert_finding_triage_details(
    session_id,
    finding_id,
    data,
    *,
    team_id="",
    actor_member_id="",
):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding_id is required")
    with get_db_connect()() as conn:
        if not _finding_belongs_to_scope(conn, session_id, finding_id, team_id=team_id):
            return None
        result = upsert_finding_triage_details_on_conn(
            conn,
            session_id,
            finding_id,
            data,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
        conn.commit()
        return result


def upsert_finding_triage_details_on_conn(
    conn,
    session_id,
    finding_id,
    data,
    *,
    team_id="",
    actor_member_id="",
    now="",
):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding_id is required")
    payload = _normalize_finding_triage_payload(data)
    metadata_session, metadata_team_id = _metadata_row_owner_values(session_id, team_id)
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    timestamp = _trim_text(now, 64) or _now()
    guidance_update = set_remediation_group_guidance(
        conn,
        {finding_id},
        remediation=payload["remediation"],
        updated_at=timestamp,
        owner_scope=("", metadata_team_id) if metadata_team_id else (metadata_session, ""),
    )
    if guidance_update["remediation_group_count"] == 0:
        return None
    observation_payload = {**payload, "remediation": ""}
    existing = conn.execute(
        "SELECT id, session_id, team_id, finding_id, remediation, verification_steps, "
        "verification_status, verification_notes, verification_updated_by_session_id, "
        "verification_updated_by_member_id, verification_updated_at, created, updated "
        "FROM finding_triage_details WHERE " + owner_sql + " AND finding_id = ?",  # nosec
        [*owner_params, finding_id],
    ).fetchone()
    previous_status = str(existing["verification_status"] or "not_started") if existing else "not_started"
    next_status = observation_payload["verification_status"]
    final_disposition_changed = (
        next_status in _FINAL_VERIFICATION_STATES
        and (
            next_status != previous_status
            or not existing
            or not str(existing["verification_updated_at"] or "")
        )
    )
    if final_disposition_changed:
        verification_actor_session = metadata_session
        verification_actor_member = _trim_text(actor_member_id, MAX_ENTITY_ID_LEN)
        verification_updated_at = timestamp
    elif next_status in _FINAL_VERIFICATION_STATES and existing:
        verification_actor_session = str(existing["verification_updated_by_session_id"] or "")
        verification_actor_member = str(existing["verification_updated_by_member_id"] or "")
        verification_updated_at = str(existing["verification_updated_at"] or "")
    else:
        verification_actor_session = ""
        verification_actor_member = ""
        verification_updated_at = ""
    if _finding_triage_payload_is_empty(observation_payload):
        if existing:
            conn.execute("DELETE FROM finding_triage_details WHERE id = ?", [existing["id"]])
        if _finding_triage_payload_is_empty(payload):
            return None
        return _finding_triage_details_on_conn(
            conn,
            session_id,
            finding_id,
            team_id=team_id,
        )
    if existing:
        conn.execute(
            "UPDATE finding_triage_details SET session_id = ?, team_id = ?, remediation = ?, "
            "verification_steps = ?, verification_status = ?, verification_notes = ?, "
            "verification_updated_by_session_id = ?, verification_updated_by_member_id = ?, "
            "verification_updated_at = ?, updated = ? WHERE id = ?",
            (
                metadata_session,
                metadata_team_id,
                observation_payload["remediation"],
                observation_payload["verification_steps"],
                observation_payload["verification_status"],
                observation_payload["verification_notes"],
                verification_actor_session,
                verification_actor_member,
                verification_updated_at,
                timestamp,
                existing["id"],
            ),
        )
        return _finding_triage_details_on_conn(
            conn,
            session_id,
            finding_id,
            team_id=team_id,
        )
    count_sql, count_params = _metadata_owner_where(session_id, team_id)
    owner_count = conn.execute(
        "SELECT COUNT(*) AS count FROM finding_triage_details WHERE " + count_sql,  # nosec
        count_params,
    ).fetchone()
    if _quota_exceeded(
        int(owner_count["count"] or 0) if owner_count else 0,
        "max_finding_triage_details_per_owner",
        5000,
    ):
        _raise_quota("finding triage quota exceeded for this owner")
    triage_id = _new_finding_triage_id()
    conflict_target = (
        "ON CONFLICT(team_id, finding_id) WHERE team_id != '' DO UPDATE SET "
        if metadata_team_id
        else "ON CONFLICT(session_id, finding_id) WHERE team_id IS NULL OR team_id = '' DO UPDATE SET "
    )
    conn.execute(
        "INSERT INTO finding_triage_details "
        "(id, session_id, team_id, finding_id, remediation, verification_steps, "
        "verification_status, verification_notes, verification_updated_by_session_id, "
        "verification_updated_by_member_id, verification_updated_at, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        f"{conflict_target}"  # nosec
        "session_id = excluded.session_id, "
        "team_id = excluded.team_id, "
        "remediation = excluded.remediation, "
        "verification_steps = excluded.verification_steps, "
        "verification_status = excluded.verification_status, "
        "verification_notes = excluded.verification_notes, "
        "verification_updated_by_session_id = excluded.verification_updated_by_session_id, "
        "verification_updated_by_member_id = excluded.verification_updated_by_member_id, "
        "verification_updated_at = excluded.verification_updated_at, "
        "updated = excluded.updated",
        (
            triage_id,
            metadata_session,
            metadata_team_id,
            finding_id,
            observation_payload["remediation"],
            observation_payload["verification_steps"],
            observation_payload["verification_status"],
            observation_payload["verification_notes"],
            verification_actor_session,
            verification_actor_member,
            verification_updated_at,
            timestamp,
            timestamp,
        ),
    )
    return _finding_triage_details_on_conn(
        conn,
        session_id,
        finding_id,
        team_id=team_id,
    )


def delete_finding_triage_details(session_id, finding_id, *, team_id=""):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding_id is required")
    owner_sql, owner_params = _metadata_owner_where(session_id, team_id)
    with get_db_connect()() as conn:
        if not _finding_belongs_to_scope(conn, session_id, finding_id, team_id=team_id):
            return None
        result = conn.execute(
            "DELETE FROM finding_triage_details WHERE " + owner_sql + " AND finding_id = ?",  # nosec
            [*owner_params, finding_id],
        )
        conn.commit()
    return result.rowcount > 0
