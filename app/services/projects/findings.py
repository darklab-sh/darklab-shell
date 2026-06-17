"""
Project finding query and row helpers.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from typing import Any

from core.database import db_connect
from core.output_signals import strip_ansi_codes
from services.atlas.scope import finding_exists_in_scope
from services.atlas.recalculation import recalculate_atlas_findings
from services.atlas.materializer import (
    canonicalize_entity_record,
    upsert_entity,
)
from services.intel.canonical import entity_signature
from services.projects.contracts import (
    FINDING_REVIEW_STATES,
    FINDING_VERIFICATION_STATES,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    MAX_FINDING_TITLE_LEN,
    MAX_LABEL_LEN,
    ProjectWorkspaceError,
)
from services.projects.metadata import (
    _entity_labels_by_id,
    _entity_notes_by_id,
    _metadata_owner_where,
    attach_finding_triage_details,
    finding_triage_verification_status_filter_sql_and_params,
)
from services.projects.scope import shared_owner_where
from services.projects.targets import _canonical_target_payload, _target_payload_from_candidate
from services.projects.utils import (
    normalize_page_window as _normalize_page_window,
    now as _now,
    page_payload as _page_payload,
    trim_text as _trim_text,
)
from services.runs.kinds import is_project_linkable_run_kind, normalize_run_kind


def row_to_finding(row):
    if not row:
        return None
    row_keys = set(row.keys())

    def value(key: str, default: Any = "") -> Any:
        if key not in row_keys:
            return default
        item = row[key]
        return default if item is None else item

    run_id = value("occurrence_run_id") or value("run_id") or value("last_run_id") or value("first_run_id")
    target_id = value("entity_id") or value("target_id")
    kind = value("kind") or value("scope") or "finding"
    status = value("status") or value("review_state") or "new"
    raw_line = value("snippet") or value("raw_line")
    return {
        "id": value("id"),
        "session_id": value("session_id"),
        "team_id": value("team_id"),
        "run_id": run_id,
        "target_id": target_id,
        "entity_id": target_id,
        "subject_key": value("subject_key"),
        "scope": value("scope") or kind,
        "kind": kind,
        "title": value("title"),
        "raw_line": raw_line,
        "line_number": value("line_number", None),
        "severity": value("severity"),
        "fingerprint": value("fingerprint"),
        "review_state": status,
        "status": status,
        "first_seen_at": value("first_seen_at"),
        "last_seen_at": value("last_seen_at"),
        "occurrence_count": int(value("occurrence_count", 0) or 0),
        "created": value("created"),
    }


def command_root(value):
    try:
        parts = shlex.split(str(value or ""))
    except ValueError:
        parts = str(value or "").split()
    return parts[0] if parts else ""


def _finding_target_ids_from_row(row, relationship_target_ids=None, allowed_target_ids=None):
    result = []
    persisted_ids = [
        str(target_id or "")
        for target_id in (relationship_target_ids if isinstance(relationship_target_ids, list) else [])
        if str(target_id or "")
    ]
    allowed_ids = {str(target_id or "") for target_id in allowed_target_ids} if allowed_target_ids is not None else None

    def can_include(target_id):
        return bool(target_id) and (allowed_ids is None or target_id in allowed_ids)

    def add(target_id):
        normalized = str(target_id or "")
        if can_include(normalized) and normalized not in result:
            result.append(normalized)

    primary = str(row["target_id"] or "") if row and "target_id" in row.keys() else ""
    if not persisted_ids or primary in persisted_ids:
        add(primary)
    for target_id in persisted_ids:
        add(target_id)
    return result


def _row_to_project_finding(row, target_ids=None, allowed_target_ids=None):
    finding = row_to_finding(row)
    if not finding:
        return None
    finding["target_ids"] = _finding_target_ids_from_row(row, target_ids, allowed_target_ids)
    finding["run_command"] = row["run_command"] or ""
    finding["command_root"] = command_root(row["run_command"])
    if "source_run_exists" in row.keys():
        finding["source_run_exists"] = bool(row["source_run_exists"])
        finding["orphan_source"] = not bool(row["source_run_exists"])
    return finding


def _metadata_filter_values(filters, key, max_len, *, lower=False):
    raw_values = filters.get(key)
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        raw_items = [raw_values]
    elif isinstance(raw_values, list):
        raw_items = raw_values
    else:
        raw_items = []
    values = []
    seen = set()
    for raw_value in raw_items:
        value = _trim_text(raw_value, max_len)
        if lower:
            value = value.lower()
        if value and value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _project_finding_page_payload(
    findings,
    total,
    limit,
    offset,
    group_counts=None,
    collapsed_group_counts=None,
    group_order=None,
    has_more=None,
):
    return _page_payload(
        "findings",
        findings,
        total,
        limit,
        offset,
        has_more=has_more,
        extra={
            "group_counts": group_counts if isinstance(group_counts, dict) else {},
            "collapsed_group_counts": collapsed_group_counts if isinstance(collapsed_group_counts, dict) else {},
            "group_order": group_order if isinstance(group_order, list) else [],
        },
    )


def _project_finding_source_exists_sql():
    return (
        "("
        "EXISTS ("
        "  SELECT 1 FROM findings_occurrences source_fo "
        "  JOIN runs source_run ON source_run.id = source_fo.run_id "
        "  WHERE source_fo.finding_id = f.id AND source_run.session_id = f.session_id"
        ") "
        "OR EXISTS ("
        "  SELECT 1 FROM runs source_direct "
        "  WHERE source_direct.session_id = f.session_id "
        "  AND ("
        "    source_direct.id = f.run_id "
        "    OR source_direct.id = f.first_run_id "
        "    OR source_direct.id = f.last_run_id"
        "  )"
        ")"
        ")"
    )


def _normalize_finding_review_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("finding review payload must be an object")
    review_state = _trim_text(data.get("review_state"), 32).lower()
    if review_state not in FINDING_REVIEW_STATES:
        raise ProjectWorkspaceError(
            "finding review_state must be new, reviewed, important, false_positive, or needs_followup"
        )
    return review_state


def _run_finding_page_payload(findings, total, limit, offset, occurrence_total=0):
    return _page_payload(
        "findings",
        findings,
        total,
        limit,
        offset,
        extra={"occurrence_total": occurrence_total},
    )


def list_run_findings(session_id, run_id, *, limit=None, offset=0, include_total=False, team_id=""):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    paginated = limit is not None or include_total
    safe_limit, safe_offset = _normalize_page_window(limit, offset, enabled=paginated)
    base_sql = (
        "WITH run_occurrences AS ("
        "  SELECT finding_id, run_id, line_number, snippet, seen_at, "
        "  COUNT(*) OVER (PARTITION BY finding_id) AS run_occurrence_count, "
        "  ROW_NUMBER() OVER ("
        "    PARTITION BY finding_id "
        "    ORDER BY line_number ASC, seen_at ASC, snippet ASC"
        "  ) AS row_num "
        "  FROM findings_occurrences WHERE run_id = ?"
        "), deduped AS ("
        "  SELECT finding_id, run_id, line_number, snippet, seen_at, run_occurrence_count "
        "  FROM run_occurrences WHERE row_num = 1"
        ") "
    )
    with db_connect() as conn:
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id)
        run = conn.execute(
            "SELECT 1 FROM runs WHERE " + run_owner_sql + " AND id = ?",  # nosec
            (*run_owner_params, run_id),
        ).fetchone()
        if not run:
            return None
        total = 0
        occurrence_total = 0
        if paginated:
            total_row = conn.execute(
                base_sql
                + "SELECT COUNT(*) AS count, COALESCE(SUM(d.run_occurrence_count), 0) AS occurrence_total "  # nosec
                "FROM deduped d JOIN findings f ON f.id = d.finding_id",
                (run_id,),
            ).fetchone()
            total = int(total_row["count"] or 0) if total_row else 0
            occurrence_total = int(total_row["occurrence_total"] or 0) if total_row else 0
        query_params: list[object] = [run_id]
        page_sql = ""
        if paginated:
            page_sql = " LIMIT ? OFFSET ?"
            query_params.extend([safe_limit, safe_offset])
        rows = conn.execute(
            base_sql
            + "SELECT f.id, f.session_id, f.entity_id, f.subject_key, f.signature_hash, f.severity, "  # nosec
            "f.kind, f.tool_root, f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            "d.run_id, d.line_number, d.snippet, d.run_occurrence_count "
            "FROM deduped d JOIN findings f ON f.id = d.finding_id "
            "ORDER BY d.line_number ASC, d.seen_at ASC, f.id ASC"
            + page_sql,
            query_params,
        ).fetchall()
    findings = []
    for row in rows:
        finding = row_to_finding(row)
        if finding:
            finding["target_ids"] = [row["entity_id"]] if row["entity_id"] else []
            finding["run_occurrence_count"] = int(row["run_occurrence_count"] or 0)
            findings.append(finding)
    if paginated:
        return _run_finding_page_payload(findings, total, safe_limit, safe_offset, occurrence_total)
    return findings


def update_finding_review_state(session_id, finding_id, data, *, team_id=""):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding id is required")
    review_state = _normalize_finding_review_payload(data)
    with db_connect() as conn:
        if not finding_exists_in_scope(conn, session_id, finding_id, team_id=team_id):
            return None
        result = conn.execute(
            "UPDATE findings SET status = ?, status_updated_at = ? WHERE id = ?",
            (review_state, _now(), finding_id),
        )
        if result.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
            "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
            "fingerprint, title, raw_line, created FROM findings WHERE id = ?",
            [finding_id],
        ).fetchone()
        conn.commit()
    return row_to_finding(row)


def bulk_update_project_finding_review_states(session_id, project_id, data, *, team_id=""):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("finding review payload must be an object")
    raw_finding_ids = data.get("finding_ids")
    if not isinstance(raw_finding_ids, list):
        raise ProjectWorkspaceError("finding_ids are required")
    finding_ids = _metadata_filter_values({"finding_ids": raw_finding_ids}, "finding_ids", MAX_ENTITY_ID_LEN)
    if not finding_ids:
        raise ProjectWorkspaceError("finding_ids are required")
    if len(finding_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        raise ProjectWorkspaceError("too_many")
    review_state = _normalize_finding_review_payload(data)
    with db_connect() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            (*project_owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        placeholders = ",".join("?" for _ in finding_ids)
        found_rows = conn.execute(  # nosec
            "WITH project_runs AS ("  # nosec
            "  SELECT l.entity_id AS run_id FROM project_links l "
            "  JOIN runs r ON r.id = l.entity_id "
            "  WHERE l.project_id = ? AND l.entity_type = 'run' AND " + run_owner_sql +
            "), project_entities AS ("
            "  SELECT l.entity_id FROM project_links l "
            "  JOIN entities e ON e.id = l.entity_id "
            "  WHERE l.project_id = ? AND l.entity_type = 'atlas_entity'"
            ") "
            "SELECT f.id FROM findings f "
            "WHERE 1 = 1 "
            f"AND f.id IN ({placeholders}) " # nosec
            "AND ("
            "  EXISTS ("
            "    SELECT 1 FROM findings_occurrences scope_fo "
            "    JOIN project_runs pr ON pr.run_id = scope_fo.run_id "
            "    WHERE scope_fo.finding_id = f.id"
            "  ) "
            "  OR EXISTS ("
            "    SELECT 1 FROM project_runs pr "
            "    WHERE pr.run_id = f.run_id OR pr.run_id = f.first_run_id OR pr.run_id = f.last_run_id"
            "  ) "
            "  OR EXISTS ("
            "    SELECT 1 FROM project_entities pe "
            "    WHERE pe.entity_id = COALESCE(f.entity_id, f.target_id)"
            "  )"
            ")",
            (project_id, *run_owner_params, project_id, *finding_ids),
        ).fetchall()
        found_ids = {str(row["id"] or "") for row in found_rows if row["id"]}
        if found_ids:
            updated_at = _now()
            conn.executemany(
                "UPDATE findings SET status = ?, status_updated_at = ? WHERE id = ?",
                [(review_state, updated_at, finding_id) for finding_id in sorted(found_ids)],
            )
            conn.commit()
    results = [
        {"finding_id": finding_id, "status": "updated" if finding_id in found_ids else "not_found"}
        for finding_id in finding_ids
    ]
    return {
        "ok": True,
        "review_state": review_state,
        "counts": {
            "updated": len(found_ids),
            "not_found": len(finding_ids) - len(found_ids),
        },
        "results": results,
    }


def list_project_findings(session_id, project_id, filters=None, *, limit=None, offset=0, include_total=False, team_id=""):
    filters = filters if isinstance(filters, dict) else {}
    paginated = limit is not None or include_total
    safe_limit, safe_offset = _normalize_page_window(limit, offset, enabled=paginated)
    with db_connect() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
        metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id, table_alias="filter_label")
        note_metadata_owner_sql, note_metadata_owner_params = _metadata_owner_where(
            session_id,
            team_id,
            table_alias="filter_note",
        )
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            (*project_owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        run_ids = _metadata_filter_values(filters, "run_id", MAX_ENTITY_ID_LEN)
        target_ids = _metadata_filter_values(filters, "target_id", MAX_ENTITY_ID_LEN)
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            target_count = conn.execute(
                "SELECT COUNT(*) AS count FROM project_links "
                "WHERE project_id = ? AND entity_type = 'atlas_entity' "
                f"AND entity_id IN ({placeholders})",  # nosec
                (project_id, *target_ids),
            ).fetchone()
            if not target_count or int(target_count["count"] or 0) != len(target_ids):
                return _project_finding_page_payload([], 0, safe_limit or 0, safe_offset) if paginated else []
        review_states = _metadata_filter_values(filters, "review_state", 32, lower=True)
        if review_states:
            if any(review_state not in FINDING_REVIEW_STATES for review_state in review_states):
                raise ProjectWorkspaceError(
                    "finding review_state must be new, reviewed, important, false_positive, or needs_followup"
                )
        scopes = _metadata_filter_values(filters, "scope", 64, lower=True)
        severities = _metadata_filter_values(filters, "severity", 64, lower=True)
        labels = _metadata_filter_values(filters, "label", MAX_LABEL_LEN)
        verification_statuses = _metadata_filter_values(filters, "verification_status", 64, lower=True)
        if verification_statuses:
            if any(status not in FINDING_VERIFICATION_STATES for status in verification_statuses):
                raise ProjectWorkspaceError(
                    "verification_status must be not_started, ready_to_verify, verified, needs_retest, or not_applicable"
                )
        note_state = _trim_text(filters.get("note_state"), 32).lower()
        if note_state:
            if note_state not in {"noted", "unnoted"}:
                raise ProjectWorkspaceError("note_state must be noted or unnoted")
        orphan_filter = _trim_text(filters.get("orphan_filter") or "hide", 32).lower()
        if orphan_filter not in {"hide", "only", "all"}:
            orphan_filter = "hide"
        collapsed_groups = _metadata_filter_values(filters, "collapsed_group", MAX_ENTITY_ID_LEN)
        include_collapsed_group_counts = (
            _trim_text(filters.get("include_collapsed_group_counts") or "1", 16).lower()
            not in {"0", "false", "no", "off"}
        )
        include_group_counts = (
            _trim_text(filters.get("include_group_counts") or "1", 16).lower()
            not in {"0", "false", "no", "off"}
        )
        known_total = max(0, int(filters.get("known_total") or 0)) if str(filters.get("known_total") or "").isdigit() else 0
        query = _trim_text(filters.get("q"), 128).lower()
        command_filters = _metadata_filter_values(filters, "command_root", 128, lower=True)
        source_exists_sql = _project_finding_source_exists_sql()
        source_run_expr = (
            "COALESCE(NULLIF(f.last_run_id, ''), NULLIF(f.run_id, ''), NULLIF(f.first_run_id, ''))"
        )
        latest_occurrence_run_expr = (
            "(SELECT lfo.run_id FROM findings_occurrences lfo "
            "WHERE lfo.finding_id = f.id "
            "ORDER BY lfo.seen_at DESC, lfo.run_id DESC, lfo.line_number DESC LIMIT 1)"
        )
        latest_occurrence_line_expr = (
            "(SELECT lfo.line_number FROM findings_occurrences lfo "
            "WHERE lfo.finding_id = f.id "
            "ORDER BY lfo.seen_at DESC, lfo.run_id DESC, lfo.line_number DESC LIMIT 1)"
        )
        latest_occurrence_snippet_expr = (
            "(SELECT lfo.snippet FROM findings_occurrences lfo "
            "WHERE lfo.finding_id = f.id "
            "ORDER BY lfo.seen_at DESC, lfo.run_id DESC, lfo.line_number DESC LIMIT 1)"
        )
        page_source_run_expr = (
            "COALESCE(NULLIF(" + latest_occurrence_run_expr + ", ''), "
            "NULLIF(f.last_run_id, ''), NULLIF(f.run_id, ''), NULLIF(f.first_run_id, ''))"
        )
        group_label_expr = "COALESCE(NULLIF(r.command, ''), " + source_run_expr + ")"
        where_clauses = [
            "COALESCE(f.suppressed, FALSE) = FALSE",
            "("
            "EXISTS ("
            "  SELECT 1 FROM findings_occurrences scope_fo "
            "  JOIN project_runs pr ON pr.run_id = scope_fo.run_id "
            "  WHERE scope_fo.finding_id = f.id"
            ") "
            "OR EXISTS ("
            "  SELECT 1 FROM project_runs pr "
            "  WHERE pr.run_id = f.run_id OR pr.run_id = f.first_run_id OR pr.run_id = f.last_run_id"
            ") "
            "OR EXISTS ("
            "  SELECT 1 FROM project_entities pe "
            "  WHERE pe.entity_id = COALESCE(f.entity_id, f.target_id)"
            ")"
            ")",
        ]
        params = [project_id, *run_owner_params, project_id]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            where_clauses.append(
                "("
                "EXISTS ("
                "  SELECT 1 FROM findings_occurrences filter_fo "
                "  WHERE filter_fo.finding_id = f.id "
                f"  AND filter_fo.run_id IN ({placeholders})"  # nosec
                ") "
                f"OR f.run_id IN ({placeholders}) "  # nosec
                f"OR f.first_run_id IN ({placeholders}) "  # nosec
                f"OR f.last_run_id IN ({placeholders})"  # nosec
                ")"
            )
            params.extend([*run_ids, *run_ids, *run_ids, *run_ids])
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            where_clauses.append(
                f"(COALESCE(f.entity_id, f.target_id) IN ({placeholders}) OR f.target_id IN ({placeholders}))"  # nosec
            )
            params.extend([*target_ids, *target_ids])
        if review_states:
            placeholders = ",".join("?" for _ in review_states)
            where_clauses.append(f"f.status IN ({placeholders})")  # nosec
            params.extend(review_states)
        if scopes:
            placeholders = ",".join("?" for _ in scopes)
            where_clauses.append(f"LOWER(f.kind) IN ({placeholders})")  # nosec
            params.extend(scopes)
        if severities:
            placeholders = ",".join("?" for _ in severities)
            where_clauses.append(f"LOWER(f.severity) IN ({placeholders})")  # nosec
            params.extend(severities)
        if query:
            finding_query_fields = (
                "f.id",
                "f.title",
                "f.raw_line",
                "f.fingerprint",
                "f.subject_key",
                "f.severity",
                "f.status",
                "f.kind",
                "f.tool_root",
            )
            where_clauses.append(
                "(" + " OR ".join(f"LOWER(COALESCE({field}, '')) LIKE ?" for field in finding_query_fields) + ")"
            )
            params.extend([f"%{query}%"] * len(finding_query_fields))
        if command_filters:
            command_clauses = []
            for _command_filter in command_filters:
                command_clauses.append("(LOWER(r.command) = ? OR LOWER(r.command) LIKE ?)")
            where_clauses.append("(" + " OR ".join(command_clauses) + ")")
            for command_filter in command_filters:
                params.extend([command_filter, f"{command_filter} %"])
        if labels:
            placeholders = ",".join("?" for _ in labels)
            where_clauses.append(
                "EXISTS ("  # nosec
                "  SELECT 1 FROM entity_labels filter_label "
                "  WHERE " + metadata_owner_sql + " "
                "  AND filter_label.entity_type = 'finding' "
                "  AND filter_label.entity_id = f.id "
                f"  AND filter_label.label IN ({placeholders})"  # nosec
                ")"
            )
            params.extend([*metadata_owner_params, *labels])
        if verification_statuses:
            verification_status_clause, verification_status_params = (
                finding_triage_verification_status_filter_sql_and_params(
                    session_id,
                    verification_statuses,
                    team_id=team_id,
                )
            )
            where_clauses.append(verification_status_clause)
            params.extend(verification_status_params)
        if note_state == "noted":
            where_clauses.append(
                "EXISTS ("  # nosec
                "  SELECT 1 FROM entity_notes filter_note "
                "  WHERE " + note_metadata_owner_sql + " "
                "  AND filter_note.entity_type = 'finding' "
                "  AND filter_note.entity_id = f.id"
                ")"
            )
            params.extend(note_metadata_owner_params)
        elif note_state == "unnoted":
            where_clauses.append(
                "NOT EXISTS ("  # nosec
                "  SELECT 1 FROM entity_notes filter_note "
                "  WHERE " + note_metadata_owner_sql + " "
                "  AND filter_note.entity_type = 'finding' "
                "  AND filter_note.entity_id = f.id"
                ")"
            )
            params.extend(note_metadata_owner_params)
        if orphan_filter == "hide":
            where_clauses.append(source_exists_sql)
        elif orphan_filter == "only":
            where_clauses.append(f"NOT {source_exists_sql}")

        pre_collapse_where_clauses = list(where_clauses)
        pre_collapse_params = list(params)
        if collapsed_groups:
            placeholders = ",".join("?" for _ in collapsed_groups)
            where_clauses.append(group_label_expr + f" NOT IN ({placeholders})")  # nosec
            params.extend(collapsed_groups)

        def build_base_sql(active_where_clauses):
            return (  # nosec
                "WITH project_runs AS ("  # nosec
                "  SELECT l.entity_id AS run_id FROM project_links l "
                "  JOIN runs r ON r.id = l.entity_id "
                "  WHERE l.project_id = ? AND l.entity_type = 'run' AND "
                + run_owner_sql +
                "), project_entities AS ("
                "  SELECT l.entity_id FROM project_links l "
                "  JOIN entities e ON e.id = l.entity_id "
                "  WHERE l.project_id = ? AND l.entity_type = 'atlas_entity'"
                "), project_findings AS ("
                "  SELECT f.id, COALESCE(f.last_seen_at, f.created) AS sort_seen "
                "  FROM findings f "
                "  LEFT JOIN runs r ON r.id = "
                + source_run_expr
                + " AND r.session_id = f.session_id "
                "  WHERE "
                + " AND ".join(active_where_clauses)
                + ") "
            )

        base_sql = build_base_sql(where_clauses)
        total = 0
        group_counts = {}
        collapsed_group_counts = {}
        group_order = []
        has_more = None
        page_limit = safe_limit or 0
        if paginated:
            if include_total:
                total_row = conn.execute(  # nosec
                    base_sql + "SELECT COUNT(*) AS count FROM project_findings",  # nosec
                    params,
                ).fetchone()
                total = int(total_row["count"] or 0) if total_row else 0
            else:
                total = known_total
        query_params = list(params)
        page_sql = ""
        if paginated:
            page_sql = " LIMIT ? OFFSET ?"
            fetch_limit = page_limit + 1 if not include_total else page_limit
            query_params.extend([fetch_limit, safe_offset])
        rows = conn.execute(  # nosec
            base_sql  # nosec
            + "SELECT f.id, f.session_id, COALESCE(f.entity_id, f.target_id) AS entity_id, "
            "f.subject_key, f.signature_hash, f.severity, f.kind, f.tool_root, "
            "f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            + page_source_run_expr
            + " AS run_id, COALESCE("
            + latest_occurrence_line_expr
            + ", f.line_number) AS line_number, "
            "COALESCE("
            + latest_occurrence_snippet_expr
            + ", f.raw_line) AS snippet, r.command AS run_command, "
            "CASE WHEN "
            + source_exists_sql
            + " THEN 1 ELSE 0 END AS source_run_exists "
            "FROM project_findings pf "
            "JOIN findings f ON f.id = pf.id "
            "LEFT JOIN runs r ON r.id = "
            + page_source_run_expr
            + " AND r.session_id = f.session_id "
            "ORDER BY pf.sort_seen DESC, f.id DESC"
            + page_sql,
            query_params,
        ).fetchall()
        if paginated and not include_total and len(rows) > page_limit:
            has_more = True
            rows = rows[:page_limit]
        if paginated and include_group_counts:
            visible_group_labels = []
            visible_group_set = set()
            for row in rows:
                label = str(row["run_command"] or row["run_id"] or "")
                if label and label not in visible_group_set:
                    visible_group_set.add(label)
                    visible_group_labels.append(label)
            collapsed_group_set = {
                str(label or "") for label in collapsed_groups if include_collapsed_group_counts and str(label or "")
            }
            needed_group_labels = []
            needed_group_set = set()
            requested_group_labels = [
                *(collapsed_groups if include_collapsed_group_counts else []),
                *visible_group_labels,
            ]
            for label in requested_group_labels:
                normalized_label = str(label or "")
                if normalized_label and normalized_label not in needed_group_set:
                    needed_group_set.add(normalized_label)
                    needed_group_labels.append(normalized_label)
            if needed_group_labels:
                placeholders = ",".join("?" for _ in needed_group_labels)
                group_rows = conn.execute(  # nosec
                    build_base_sql(pre_collapse_where_clauses)  # nosec
                    + "SELECT "
                    + group_label_expr
                    + " AS group_label, COUNT(*) AS count, MAX(pf.sort_seen) AS group_sort_seen "
                    "FROM project_findings pf "
                    "JOIN findings f ON f.id = pf.id "
                    "LEFT JOIN runs r ON r.id = "
                    + source_run_expr
                    + " AND r.session_id = f.session_id "
                    "WHERE "
                    + group_label_expr
                    + f" IN ({placeholders}) "  # nosec
                    "GROUP BY 1 "
                    "ORDER BY MAX(pf.sort_seen) DESC, group_label ASC",
                    (*pre_collapse_params, *needed_group_labels),
                ).fetchall()
                for group_row in group_rows:
                    label = str(group_row["group_label"] or "")
                    if not label:
                        continue
                    count = int(group_row["count"] or 0)
                    if label in visible_group_set:
                        group_counts[label] = count
                    if label in collapsed_group_set:
                        collapsed_group_counts[label] = count
                    group_order.append(label)
                for label in needed_group_labels:
                    if label not in group_order:
                        group_order.append(label)
        project_target_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
            (project_id,),
        ).fetchall()
        project_target_ids = {str(row["entity_id"] or "") for row in project_target_rows if row["entity_id"]}
        finding_ids = [str(row["id"] or "") for row in rows if row["id"]]
        finding_labels = _entity_labels_by_id(conn, session_id, "finding", finding_ids, team_id=team_id)
        finding_notes = _entity_notes_by_id(conn, session_id, "finding", finding_ids, team_id=team_id)
        findings = [
            item for item in (
                _row_to_project_finding(
                    row,
                    [row["entity_id"]] if row["entity_id"] else [],
                    project_target_ids,
                )
                for row in rows
            )
            if item
        ]
        for item in findings:
            finding_id = str(item["id"] or "")
            item["labels"] = finding_labels.get(finding_id, [])
            item["note"] = finding_notes.get(finding_id)
        attach_finding_triage_details(conn, session_id, findings, team_id=team_id)

    if paginated:
        return _project_finding_page_payload(
            findings,
            total,
            page_limit,
            safe_offset,
            group_counts,
            collapsed_group_counts,
            group_order,
            has_more,
        )
    return findings


def _finding_severity_from_text(text):
    raw_text = str(text or "")
    bracket_match = re.search(r"\[(info|low|medium|high|critical)\]", raw_text, re.I)
    if bracket_match:
        return bracket_match.group(1).lower()
    key_match = re.search(
        r"(?:\"severity\"|'severity'|\bseverity\b|\brisk\b)\s*[:=]\s*[\"']?"
        r"(info|low|medium|high|critical)\b",
        raw_text,
        re.I,
    )
    if key_match:
        return key_match.group(1).lower()
    phrase_match = re.search(r"\b(info|low|medium|high|critical)\s+severity\b", raw_text, re.I)
    if phrase_match:
        return phrase_match.group(1).lower()
    vulners_match = re.search(
        r"^\|_?\s+\S+\s+(10(?:\.0)?|[0-9](?:\.\d)?)\s+https://vulners\.com/\S+",
        raw_text.strip(),
        re.I,
    )
    if vulners_match:
        score = float(vulners_match.group(1))
        if score >= 9.0:
            return "critical"
        if score >= 7.0:
            return "high"
        if score >= 4.0:
            return "medium"
        if score > 0:
            return "low"
        return "info"
    cvss_match = re.search(r"\bcvss\b[^\n\r]{0,32}\bscore\b\s*[:=]?\s*(10(?:\.0)?|[0-9](?:\.\d)?)\b", raw_text, re.I)
    if not cvss_match:
        return ""
    score = float(cvss_match.group(1))
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "info"


_NMAP_VULNERS_ROW_RE = re.compile(
    r"^\|_?\s+(?P<id>\S+)\s+(?P<score>10(?:\.0)?|[0-9](?:\.\d)?)\s+"
    r"(?P<url>https://vulners\.com/\S+)(?P<exploit>\s+\*EXPLOIT\*)?\s*$",
    re.I,
)
_NMAP_VULNERS_CVE_RE = re.compile(r"\bCVE[-_](\d{4})[-_](\d{4,})\b", re.I)
_NMAP_VULNERS_REFERENCE_LIMIT = 20


def _nmap_vulners_row(text: str) -> dict[str, Any] | None:
    match = _NMAP_VULNERS_ROW_RE.match(strip_ansi_codes(str(text or "")).strip())
    if not match:
        return None
    raw_id = str(match.group("id") or "")
    cve_match = _NMAP_VULNERS_CVE_RE.search(raw_id) or _NMAP_VULNERS_CVE_RE.search(str(match.group("url") or ""))
    return {
        "id": raw_id,
        "score": float(match.group("score")),
        "url": str(match.group("url") or ""),
        "exploit": bool(match.group("exploit")),
        "cve": f"CVE-{cve_match.group(1)}-{cve_match.group(2)}".upper() if cve_match else "",
    }


def _nmap_vulners_score_severity(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "info"


def _nmap_service_label(target: str) -> str:
    normalized = re.sub(r"\s+", " ", str(target or "")).strip()
    match = re.match(r"^(?P<host>(?:\[[^\]]+\]|[^:\s]+)):(?P<port>\d+)\s+(?P<service>.+)$", normalized)
    if not match:
        return normalized
    return f"{match.group('service')} on {match.group('host')}:{match.group('port')}"


def _nmap_vulners_reference(row: dict[str, Any]) -> str:
    return f"{row['id']} {row['url']}".strip()


def _nmap_grouped_vulners_line(
    *,
    target: str,
    cve: str = "",
    score: float,
    references: list[str],
) -> str:
    severity = _nmap_vulners_score_severity(score)
    service = _nmap_service_label(target)
    reference_items = references[:_NMAP_VULNERS_REFERENCE_LIMIT]
    if len(references) > len(reference_items):
        reference_items.append(f"+{len(references) - len(reference_items)} more")
    reference_text = "; ".join(reference_items)
    if cve:
        return (
            f"Nmap Vulners: {cve} affects {service} "
            f"(CVSS score {score:g}, severity {severity}); public exploit references: {reference_text}"
        )
    return (
        f"Nmap Vulners: Public exploit references available for {service} "
        f"(max CVSS score {score:g}, severity {severity}); references: {reference_text}"
    )


def _group_nmap_vulners_entries(entries: list[Any]) -> list[Any]:
    if not entries:
        return entries

    result: list[Any] = []
    cve_groups: dict[tuple[str, str], dict[str, Any]] = {}
    public_groups: dict[str, dict[str, Any]] = {}

    def line_index_for(entry: dict[str, Any], fallback: int) -> int:
        value = entry.get("line_index")
        return value if isinstance(value, int) else fallback

    for fallback_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            result.append(entry)
            continue
        row = _nmap_vulners_row(str(entry.get("text") or ""))
        if not row:
            result.append(entry)
            continue
        signals = entry.get("signals")
        signal_values = {str(signal) for signal in signals} if isinstance(signals, list) else set()
        if "findings" not in signal_values:
            result.append(entry)
            continue

        target = re.sub(r"\s+", " ", str(entry.get("target") or "")).strip()
        index = line_index_for(entry, fallback_index)
        if row["cve"]:
            key = (target, row["cve"])
            group = cve_groups.setdefault(
                key,
                {
                    "entry": entry,
                    "target": target,
                    "cve": row["cve"],
                    "score": row["score"],
                    "references": [],
                    "line_index": index,
                    "entities": entry.get("entities"),
                },
            )
            group["score"] = max(float(group["score"]), float(row["score"]))
            group["line_index"] = min(int(group["line_index"]), index)
            if row["exploit"]:
                group["references"].append(_nmap_vulners_reference(row))
            continue

        if not row["exploit"]:
            result.append(entry)
            continue
        group = public_groups.setdefault(
            target,
            {
                "entry": entry,
                "target": target,
                "score": row["score"],
                "references": [],
                "line_index": index,
                "entities": entry.get("entities"),
            },
        )
        group["score"] = max(float(group["score"]), float(row["score"]))
        group["line_index"] = min(int(group["line_index"]), index)
        group["references"].append(_nmap_vulners_reference(row))

    grouped_entries: list[tuple[int, dict[str, Any]]] = []
    for group in cve_groups.values():
        references = [str(item) for item in group["references"] if str(item)]
        if not references:
            grouped_entries.append((int(group["line_index"]), group["entry"]))
            continue
        entry = dict(group["entry"])
        entry["line_index"] = int(group["line_index"])
        entry["target"] = group["target"]
        entry["text"] = _nmap_grouped_vulners_line(
            target=str(group["target"]),
            cve=str(group["cve"]),
            score=float(group["score"]),
            references=references,
        )
        if isinstance(group.get("entities"), list):
            entry["entities"] = group["entities"]
        grouped_entries.append((int(group["line_index"]), entry))

    for group in public_groups.values():
        references = [str(item) for item in group["references"] if str(item)]
        if not references:
            continue
        entry = dict(group["entry"])
        entry["line_index"] = int(group["line_index"])
        entry["target"] = group["target"]
        entry["text"] = _nmap_grouped_vulners_line(
            target=str(group["target"]),
            score=float(group["score"]),
            references=references,
        )
        if isinstance(group.get("entities"), list):
            entry["entities"] = group["entities"]
        grouped_entries.append((int(group["line_index"]), entry))

    if not grouped_entries:
        return result
    grouped_entries.sort(key=lambda item: item[0])
    result.extend(entry for _index, entry in grouped_entries)
    return sorted(
        result,
        key=lambda item: item.get("line_index", 0) if isinstance(item, dict) and isinstance(item.get("line_index"), int) else 0,
    )


def _finding_fingerprint(run_id, line_index, text):
    raw = f"{run_id}\x1f{line_index}\x1f{text}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _finding_signature(tool_root, kind, severity, normalized_signal_key, subject_key):
    raw = "\x1f".join((
        str(tool_root or ""),
        str(kind or "finding"),
        str(severity or ""),
        str(normalized_signal_key or ""),
        str(subject_key or ""),
    )).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _normalize_finding_signal_key(text):
    return re.sub(r"\s+", " ", strip_ansi_codes(str(text or ""))).strip().lower()[:512]


def _nmap_service_subject_from_entry(entry: dict[str, Any], tool_root: str) -> str:
    if tool_root != "nmap":
        return ""
    target = re.sub(r"\s+", " ", str(entry.get("target") or "")).strip().lower()
    if not target or not re.match(r"^(?:\[[^\]]+\]|[^:\s]+):\d+\s+\S+", target):
        return ""
    return f"nmap-service:{target}"[:512]


def _entry_primary_entity(conn, session_id, entry, seen_at, *, team_id=""):
    fallback_payload = _target_payload_from_candidate(entry.get("target") if isinstance(entry, dict) else "")
    if fallback_payload:
        try:
            entity_type, canonical_value = _canonical_target_payload(fallback_payload)
        except ProjectWorkspaceError:
            entity_type = ""
            canonical_value = ""
        if entity_type and canonical_value:
            entity_id = upsert_entity(
                conn,
                session_id,
                entity_type,
                canonical_value,
                team_id=team_id,
                seen_at=seen_at,
                occurrence_count=0,
            )
            return entity_id, entity_signature(entity_type, canonical_value)
    raw_entities = entry.get("entities") if isinstance(entry, dict) else None
    if not isinstance(raw_entities, list):
        raw_entities = []
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        normalized = canonicalize_entity_record(raw_entity)
        if not normalized:
            continue
        entity_type, canonical_value = normalized
        entity_id = upsert_entity(
            conn,
            session_id,
            entity_type,
            canonical_value,
            team_id=team_id,
            seen_at=seen_at,
            occurrence_count=0,
        )
        return entity_id, entity_signature(entity_type, canonical_value)
    return "", ""


def record_run_findings(conn, session_id, run_id, entries, *, team_id=""):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    team_id = str(team_id or "").strip()
    if team_id:
        run = conn.execute(
            "SELECT command, run_kind FROM runs WHERE team_id = ? AND id = ?",
            (team_id, run_id),
        ).fetchone()
    else:
        run = conn.execute(
            "SELECT command, run_kind FROM runs WHERE session_id = ? AND (team_id IS NULL OR team_id = '') AND id = ?",
            (session_id, run_id),
        ).fetchone()
    if not run:
        return []
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        return []

    created = _now()
    existing_rows = conn.execute(
        "SELECT DISTINCT finding_id FROM findings_occurrences WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    existing_finding_ids = [str(row["finding_id"] or "") for row in existing_rows]
    conn.execute("DELETE FROM findings_occurrences WHERE run_id = ?", (run_id,))
    recorded = []
    seen_fingerprints = set()
    tool_root = command_root(run["command"])
    entry_items = entries if isinstance(entries, list) else []
    if tool_root == "nmap":
        entry_items = _group_nmap_vulners_entries(entry_items)
    for fallback_index, entry in enumerate(entry_items):
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "")
        if role in {"section-header", "kv", "help-row", "progress", "status-line", "pty-marker"}:
            continue
        signals = entry.get("signals")
        signal_values = {str(signal) for signal in signals} if isinstance(signals, list) else set()
        kind = str(entry.get("kind") or "")
        if "findings" not in signal_values and kind != "error":
            continue
        raw_line = strip_ansi_codes(str(entry.get("text") or "")).strip()
        if not raw_line:
            continue
        line_index = entry.get("line_index")
        if not isinstance(line_index, int):
            line_index = fallback_index
        fingerprint = _finding_fingerprint(run_id, line_index, raw_line)
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        title = _trim_text(raw_line, MAX_FINDING_TITLE_LEN)
        severity = _finding_severity_from_text(raw_line)
        if kind == "error" and not severity:
            severity = "high"
        entity_id, entity_sig = _entry_primary_entity(conn, session_id, entry, created, team_id=team_id)
        signal_key = _normalize_finding_signal_key(raw_line)
        subject_key = _nmap_service_subject_from_entry(entry, tool_root)
        if not subject_key:
            subject_key = entity_sig if entity_id else f"unscoped:{tool_root}:{signal_key}"
        signature_hash = _finding_signature(tool_root, "finding", severity, signal_key, subject_key)
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
        if row:
            finding_id = str(row["id"])
            conn.execute(
                "UPDATE findings SET run_id = ?, target_id = ?, last_run_id = ?, last_seen_at = ?, "
                "severity = CASE WHEN ? != '' THEN ? ELSE severity END, "
                "title = ?, raw_line = ? WHERE id = ?",
                (run_id, entity_id, run_id, created, severity, severity, title, raw_line, finding_id),
            )
        else:
            owner_id = team_id or session_id
            finding_id = "fnd_" + hashlib.sha256(
                f"{owner_id}\x1f{signature_hash}".encode("utf-8", errors="replace")
            ).hexdigest()[:32]
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, team_id, run_id, target_id, scope, line_number, review_state, "
                "entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
                "status_updated_at, fingerprint, title, raw_line, created) "
                "VALUES (?, ?, ?, ?, ?, 'finding', ?, 'new', ?, ?, ?, ?, 'finding', ?, ?, ?, ?, ?, 0, 'new', '', ?, ?, ?, ?)",
                (
                    finding_id,
                    session_id,
                    team_id,
                    run_id,
                    entity_id,
                    line_index,
                    entity_id or None,
                    subject_key,
                    signature_hash,
                    severity,
                    tool_root,
                    run_id,
                    run_id,
                    created,
                    created,
                    fingerprint,
                    title,
                    raw_line,
                    created,
                ),
            )
        conn.execute(
            "INSERT INTO findings_occurrences "
            "(finding_id, run_id, line_number, snippet, seen_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(finding_id, run_id, line_number) DO NOTHING",
            (finding_id, run_id, line_index, raw_line, created),
        )
        recalculate_atlas_findings(conn, [finding_id])
        full_row = conn.execute(
            "SELECT f.id, f.session_id, f.team_id, COALESCE(f.entity_id, f.target_id) AS entity_id, "
            "f.subject_key, f.signature_hash, f.severity, "
            "f.kind, f.tool_root, f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            "fo.run_id AS occurrence_run_id, fo.line_number, fo.snippet "
            "FROM findings f JOIN findings_occurrences fo ON fo.finding_id = f.id "
            "WHERE f.id = ? AND fo.run_id = ? AND fo.line_number = ?",
            (finding_id, run_id, line_index),
        ).fetchone()
        finding = row_to_finding(full_row)
        if finding:
            finding["target_ids"] = [entity_id] if entity_id else []
            recorded.append(finding)
    if existing_finding_ids:
        recalculate_atlas_findings(conn, existing_finding_ids)
    return recorded
