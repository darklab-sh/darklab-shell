"""
Project finding query and row helpers.
"""

from __future__ import annotations

import hashlib
import re
import shlex

from core.database import db_connect
from core.output_signals import strip_ansi_codes
from services.atlas.materializer import (
    canonicalize_entity_record,
    upsert_entity,
)
from services.intel.canonical import entity_signature
from services.projects.contracts import (
    FINDING_REVIEW_STATES,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    MAX_FINDING_TITLE_LEN,
    MAX_LABEL_LEN,
    ProjectWorkspaceError,
)
from services.projects.metadata import _entity_labels_by_id, _entity_notes_by_id
from services.projects.targets import _canonical_target_payload, _target_payload_from_candidate
from services.projects.utils import now as _now
from services.runs.kinds import is_project_linkable_run_kind, normalize_run_kind


def _trim_text(value, limit):
    return str(value or "").strip()[:limit]


def row_to_finding(row):
    if not row:
        return None
    if "last_run_id" in row.keys():
        run_id = row["run_id"] if "run_id" in row.keys() else row["last_run_id"]
        line_number = row["line_number"] if "line_number" in row.keys() else None
        snippet = row["snippet"] if "snippet" in row.keys() else row["raw_line"]
        target_id = row["entity_id"] or (row["target_id"] if "target_id" in row.keys() else "")
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "run_id": run_id or row["last_run_id"],
            "target_id": target_id,
            "entity_id": target_id,
            "subject_key": row["subject_key"] or "",
            "scope": row["kind"] or "finding",
            "kind": row["kind"] or "finding",
            "title": row["title"],
            "raw_line": snippet or row["raw_line"],
            "line_number": line_number,
            "severity": row["severity"],
            "fingerprint": row["fingerprint"],
            "review_state": row["status"],
            "status": row["status"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "occurrence_count": int(row["occurrence_count"] or 0),
            "created": row["created"],
        }
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "run_id": row["run_id"],
        "target_id": row["target_id"],
        "scope": row["scope"],
        "title": row["title"],
        "raw_line": row["raw_line"],
        "line_number": row["line_number"],
        "severity": row["severity"],
        "fingerprint": row["fingerprint"],
        "review_state": row["review_state"],
        "created": row["created"],
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
    return {
        "findings": findings,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": bool(has_more) if has_more is not None else offset + len(findings) < total,
        "group_counts": group_counts if isinstance(group_counts, dict) else {},
        "collapsed_group_counts": collapsed_group_counts if isinstance(collapsed_group_counts, dict) else {},
        "group_order": group_order if isinstance(group_order, list) else [],
    }


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
    return {
        "findings": findings,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(findings) < total,
        "occurrence_total": occurrence_total,
    }


def list_run_findings(session_id, run_id, *, limit=None, offset=0, include_total=False):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    paginated = limit is not None or include_total
    safe_limit = max(1, min(int(limit or 50), 200)) if paginated else None
    safe_offset = max(0, int(offset or 0)) if paginated else 0
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
        run = conn.execute(
            "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
            (session_id, run_id),
        ).fetchone()
        if not run:
            return None
        total = 0
        occurrence_total = 0
        if paginated:
            total_row = conn.execute(
                base_sql
                + "SELECT COUNT(*) AS count, COALESCE(SUM(d.run_occurrence_count), 0) AS occurrence_total "  # nosec B608
                "FROM deduped d JOIN findings f ON f.id = d.finding_id WHERE f.session_id = ?",
                (run_id, session_id),
            ).fetchone()
            total = int(total_row["count"] or 0) if total_row else 0
            occurrence_total = int(total_row["occurrence_total"] or 0) if total_row else 0
        query_params = [run_id, session_id]
        page_sql = ""
        if paginated:
            page_sql = " LIMIT ? OFFSET ?"
            query_params.extend([safe_limit, safe_offset])
        rows = conn.execute(
            base_sql
            + "SELECT f.id, f.session_id, f.entity_id, f.subject_key, f.signature_hash, f.severity, "  # nosec B608
            "f.kind, f.tool_root, f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            "d.run_id, d.line_number, d.snippet, d.run_occurrence_count "
            "FROM deduped d JOIN findings f ON f.id = d.finding_id "
            "WHERE f.session_id = ? "
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


def update_finding_review_state(session_id, finding_id, data):
    finding_id = _trim_text(finding_id, MAX_ENTITY_ID_LEN)
    if not finding_id:
        raise ProjectWorkspaceError("finding id is required")
    review_state = _normalize_finding_review_payload(data)
    with db_connect() as conn:
        result = conn.execute(
            "UPDATE findings SET status = ?, status_updated_at = ? WHERE session_id = ? AND id = ?",
            (review_state, _now(), session_id, finding_id),
        )
        if result.rowcount <= 0:
            return None
        row = conn.execute(
            "SELECT id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
            "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
            "fingerprint, title, raw_line, created FROM findings WHERE session_id = ? AND id = ?",
            [session_id, finding_id],
        ).fetchone()
        conn.commit()
    return row_to_finding(row)


def bulk_update_project_finding_review_states(session_id, project_id, data):
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
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        placeholders = ",".join("?" for _ in finding_ids)
        found_rows = conn.execute(  # nosec B608
            "WITH project_runs AS ("
            "  SELECT l.entity_id AS run_id FROM project_links l "
            "  JOIN runs r ON r.id = l.entity_id "
            "  WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ?"
            "), project_entities AS ("
            "  SELECT l.entity_id FROM project_links l "
            "  JOIN entities e ON e.id = l.entity_id "
            "  WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ?"
            ") "
            "SELECT f.id FROM findings f "
            "WHERE f.session_id = ? "
            f"AND f.id IN ({placeholders}) "  # nosec B608
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
            (project_id, session_id, project_id, session_id, session_id, *finding_ids),
        ).fetchall()
        found_ids = {str(row["id"] or "") for row in found_rows if row["id"]}
        if found_ids:
            updated_at = _now()
            conn.executemany(
                "UPDATE findings SET status = ?, status_updated_at = ? WHERE session_id = ? AND id = ?",
                [(review_state, updated_at, session_id, finding_id) for finding_id in sorted(found_ids)],
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


def list_project_findings(session_id, project_id, filters=None, *, limit=None, offset=0, include_total=False):
    filters = filters if isinstance(filters, dict) else {}
    paginated = limit is not None or include_total
    safe_limit = max(1, min(int(limit or 50), 200)) if paginated else None
    safe_offset = max(0, int(offset or 0)) if paginated else 0
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
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
            "f.session_id = ?",
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
        params = [project_id, session_id, project_id, session_id, session_id]
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
                "EXISTS ("
                "  SELECT 1 FROM entity_labels filter_label "
                "  WHERE filter_label.session_id = f.session_id "
                "  AND filter_label.entity_type = 'finding' "
                "  AND filter_label.entity_id = f.id "
                f"  AND filter_label.label IN ({placeholders})"  # nosec
                ")"
            )
            params.extend(labels)
        if note_state == "noted":
            where_clauses.append(
                "EXISTS ("
                "  SELECT 1 FROM entity_notes filter_note "
                "  WHERE filter_note.session_id = f.session_id "
                "  AND filter_note.entity_type = 'finding' "
                "  AND filter_note.entity_id = f.id"
                ")"
            )
        elif note_state == "unnoted":
            where_clauses.append(
                "NOT EXISTS ("
                "  SELECT 1 FROM entity_notes filter_note "
                "  WHERE filter_note.session_id = f.session_id "
                "  AND filter_note.entity_type = 'finding' "
                "  AND filter_note.entity_id = f.id"
                ")"
            )
        if orphan_filter == "hide":
            where_clauses.append(source_exists_sql)
        elif orphan_filter == "only":
            where_clauses.append(f"NOT {source_exists_sql}")

        pre_collapse_where_clauses = list(where_clauses)
        pre_collapse_params = list(params)
        if collapsed_groups:
            placeholders = ",".join("?" for _ in collapsed_groups)
            where_clauses.append(group_label_expr + f" NOT IN ({placeholders})")  # nosec B608
            params.extend(collapsed_groups)

        def build_base_sql(active_where_clauses):
            return (  # nosec B608
                "WITH project_runs AS ("  # nosec B608
                "  SELECT l.entity_id AS run_id FROM project_links l "
                "  JOIN runs r ON r.id = l.entity_id "
                "  WHERE l.project_id = ? AND l.entity_type = 'run' AND r.session_id = ?"
                "), project_entities AS ("
                "  SELECT l.entity_id FROM project_links l "
                "  JOIN entities e ON e.id = l.entity_id "
                "  WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND e.session_id = ?"
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
                total_row = conn.execute(  # nosec B608
                    base_sql + "SELECT COUNT(*) AS count FROM project_findings",  # nosec B608
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
        rows = conn.execute(  # nosec B608
            base_sql  # nosec B608
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
                group_rows = conn.execute(  # nosec B608
                    build_base_sql(pre_collapse_where_clauses)  # nosec B608
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
                    + f" IN ({placeholders}) "  # nosec B608
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
        finding_labels = _entity_labels_by_id(conn, session_id, "finding", finding_ids)
        finding_notes = _entity_notes_by_id(conn, session_id, "finding", finding_ids)

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


def _entry_primary_entity(conn, session_id, entry, seen_at):
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
            seen_at=seen_at,
            occurrence_count=0,
        )
        return entity_id, entity_signature(entity_type, canonical_value)
    return "", ""


def record_run_findings(conn, session_id, run_id, entries):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE session_id = ? AND id = ?",
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
    entry_items = entries if isinstance(entries, list) else []
    tool_root = command_root(run["command"])
    for fallback_index, entry in enumerate(entry_items):
        if not isinstance(entry, dict):
            continue
        signals = entry.get("signals")
        signal_values = {str(signal) for signal in signals} if isinstance(signals, list) else set()
        if "findings" not in signal_values:
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
        entity_id, entity_sig = _entry_primary_entity(conn, session_id, entry, created)
        signal_key = _normalize_finding_signal_key(raw_line)
        subject_key = entity_sig if entity_id else f"unscoped:{tool_root}:{signal_key}"
        signature_hash = _finding_signature(tool_root, "finding", severity, signal_key, subject_key)
        row = conn.execute(
            "SELECT id FROM findings WHERE session_id = ? AND signature_hash = ?",
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
            finding_id = "fnd_" + hashlib.sha256(
                f"{session_id}\x1f{signature_hash}".encode("utf-8", errors="replace")
            ).hexdigest()[:32]
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, line_number, review_state, "
                "entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, "
                "status_updated_at, fingerprint, title, raw_line, created) "
                "VALUES (?, ?, ?, ?, 'finding', ?, 'new', ?, ?, ?, ?, 'finding', ?, ?, ?, ?, ?, 0, 'new', '', ?, ?, ?, ?)",
                (
                    finding_id,
                    session_id,
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
        occurrence_row = conn.execute(
            "SELECT COUNT(*) AS count, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at "
            "FROM findings_occurrences WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        last_run = conn.execute(
            "SELECT run_id FROM findings_occurrences WHERE finding_id = ? ORDER BY seen_at DESC, run_id DESC LIMIT 1",
            (finding_id,),
        ).fetchone()
        conn.execute(
            "UPDATE findings SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ?, last_run_id = ? "
            "WHERE id = ?",
            (
                int(occurrence_row["count"] or 0) if occurrence_row else 0,
                occurrence_row["first_seen_at"] if occurrence_row else created,
                occurrence_row["last_seen_at"] if occurrence_row else created,
                last_run["run_id"] if last_run else run_id,
                finding_id,
            ),
        )
        full_row = conn.execute(
            "SELECT f.id, f.session_id, COALESCE(f.entity_id, f.target_id) AS entity_id, "
            "f.subject_key, f.signature_hash, f.severity, "
            "f.kind, f.tool_root, f.first_run_id, f.last_run_id, f.first_seen_at, f.last_seen_at, "
            "f.occurrence_count, f.status, f.fingerprint, f.title, f.raw_line, f.created, "
            "fo.run_id, fo.line_number, fo.snippet "
            "FROM findings f JOIN findings_occurrences fo ON fo.finding_id = f.id "
            "WHERE f.id = ? AND fo.run_id = ? AND fo.line_number = ?",
            (finding_id, run_id, line_index),
        ).fetchone()
        finding = row_to_finding(full_row)
        if finding:
            finding["target_ids"] = [entity_id] if entity_id else []
            recorded.append(finding)
    if existing_finding_ids:
        for finding_id in existing_finding_ids:
            row = conn.execute(
                "SELECT COUNT(*) AS count, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at "
                "FROM findings_occurrences WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            count = int(row["count"] or 0) if row else 0
            if count <= 0:
                conn.execute(
                    "UPDATE findings SET occurrence_count = 0, run_id = '', last_run_id = '', "
                    "first_seen_at = '', last_seen_at = '', line_number = NULL WHERE id = ?",
                    (finding_id,),
                )
                continue
            last_run = conn.execute(
                "SELECT run_id FROM findings_occurrences WHERE finding_id = ? ORDER BY seen_at DESC, run_id DESC LIMIT 1",
                (finding_id,),
            ).fetchone()
            conn.execute(
                "UPDATE findings SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ?, last_run_id = ? "
                "WHERE id = ?",
                (
                    count,
                    row["first_seen_at"] or "",
                    row["last_seen_at"] or "",
                    last_run["run_id"] if last_run else "",
                    finding_id,
                ),
            )
    return recorded
