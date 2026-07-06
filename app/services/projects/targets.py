"""
Project target mutation and discovery helpers.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
from urllib.parse import urlparse

import config as _config
from core.database import validate_project_link_source
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.atlas.materializer import upsert_entity, url_host_identity
from services.atlas.scope import metadata_owner_id
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_entity, entity_signature
from services.projects.contracts import (
    MAX_ENTITY_ID_LEN,
    MAX_PROJECT_TARGET_DISCOVERY_FILE_BYTES,
    MAX_PROJECT_TARGET_DISCOVERY_FILE_LINES,
    MAX_PROJECT_TARGET_DISCOVERY_PER_RUN,
    MAX_TARGET_VALUE_LEN,
    PROJECT_TARGET_REVIEW_STATES,
    PROJECT_TARGET_SOURCES,
    PROJECT_TARGET_TYPES,
    ProjectWorkspaceError,
)
from services.projects.links import _insert_project_link
from services.projects.metadata import _attach_target_metadata, _metadata_owner_where
from services.projects.models import row_to_target as _row_to_target
from services.projects.scope import shared_owner_where
from services.projects.utils import (
    normalize_page_window as _normalize_page_window,
    now as _now,
    page_payload as _page_payload,
    quota_exceeded as _quota_exceeded,
    raise_quota as _raise_quota,
    trim_text as _trim_text,
)
from services.workspace.files import WorkspaceError, read_workspace_text_file


log = logging.getLogger("shell")

PROJECT_TARGET_SOURCE_DETAIL_FLAG = "project_target"
PROJECT_TARGET_ENTITY_TYPES = {"domain", "ip", "url"}
# Accepted for older API/import/command metadata, but never advertised as a new target type.
LEGACY_PROJECT_TARGET_TYPE_ALIASES = {"host"}

_URL_RE = re.compile(r"https?://[^\s<>'\"`]+", re.I)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\b",
    re.I,
)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,254}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.?$",
    re.I,
)


def _normalize_target_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("target payload must be an object")
    if any(key in data for key in ("label", "labels", "note", "notes")):
        raise ProjectWorkspaceError("target labels and notes use entity metadata routes")
    clean = {}
    if "type" in data or not partial:
        target_type = _trim_text(data.get("type"), 32).lower()
        if target_type not in PROJECT_TARGET_TYPES | LEGACY_PROJECT_TARGET_TYPE_ALIASES:
            raise ProjectWorkspaceError("target type must be domain, url, or ip")
        clean["type"] = target_type
    if "value" in data or not partial:
        value = _trim_text(data.get("value"), MAX_TARGET_VALUE_LEN)
        if not value:
            raise ProjectWorkspaceError("target value is required")
        clean["value"] = value
    if "source_run_id" in data or not partial:
        clean["source_run_id"] = _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN)
    if "confidence" in data or not partial:
        try:
            confidence = float(data.get("confidence", 1.0))
        except (TypeError, ValueError):
            raise ProjectWorkspaceError("target confidence must be a number") from None
        clean["confidence"] = min(1.0, max(0.0, confidence))
    if "review_state" in data:
        review_state = _trim_text(data.get("review_state"), 32).lower()
        if review_state not in PROJECT_TARGET_REVIEW_STATES:
            raise ProjectWorkspaceError("target review_state must be confirmed, pending, or dismissed")
        clean["review_state"] = review_state
    if "source" in data:
        source = _trim_text(data.get("source"), 32).lower()
        if source not in PROJECT_TARGET_SOURCES:
            raise ProjectWorkspaceError("target source must be user, auto_command, or auto_input_file")
        clean["source"] = source
    if "source_detail" in data:
        source_detail = data.get("source_detail")
        if not isinstance(source_detail, dict):
            raise ProjectWorkspaceError("target source_detail must be an object")
        clean["source_detail"] = {
            _trim_text(key, 64): _trim_text(value, 512)
            for key, value in source_detail.items()
            if _trim_text(key, 64)
        }
    return clean


def _strip_target_token(value):
    return str(value or "").strip().strip("[](){}<>\"'`,;")


def _value_kind(value: object) -> str:
    raw = str(value or "").strip().strip("[]")
    if not raw:
        return "empty"
    try:
        ipaddress.ip_address(raw)
        return "ip_literal"
    except ValueError:
        return "domain_like" if "." in raw else "single_label"


def _value_hash(value: object) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:12]


def _log_target_type_canonicalized(
    event_name: str,
    *,
    level: int,
    session_id: str,
    project_id: str,
    input_type: object,
    resolved_type: str,
    value: object,
    source: str = "",
    team_id: str = "",
) -> None:
    extra = {
        "session": get_log_session_id(session_id),
        "project_id": str(project_id or ""),
        "input_type": str(input_type or ""),
        "resolved_type": str(resolved_type or ""),
        "value_kind": _value_kind(value),
        "value_hash": _value_hash(value),
        "source": str(source or ""),
        "team_scope": bool(team_id),
    }
    if level <= logging.DEBUG:
        log.debug(event_name, extra=extra)
    elif level >= logging.WARNING:
        log.warning(event_name, extra=extra)
    else:
        log.info(event_name, extra=extra)


def _target_payload_from_candidate(value):
    candidate = _strip_target_token(value)
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return {"type": "url", "value": candidate}
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        address = None
    if address is not None:
        return {"type": "ip", "value": str(address)}
    if _DOMAIN_RE.fullmatch(candidate):
        return {"type": "domain", "value": candidate.lower()}
    return None


def _target_payload_from_typed_value(value, value_type):
    raw_value = _strip_target_token(value)
    raw_type = _trim_text(value_type, 32).lower()
    if not raw_value or raw_type not in PROJECT_TARGET_TYPES | LEGACY_PROJECT_TARGET_TYPE_ALIASES | {"target"}:
        return None
    inferred = _target_payload_from_candidate(raw_value)
    if raw_type == "target":
        return inferred
    if inferred and inferred["type"] == raw_type:
        return inferred
    if raw_type in {"domain", "host"} and inferred and inferred["type"] in {"domain", "host", "ip"}:
        return inferred
    if raw_type == "url" and inferred and inferred["type"] == "url":
        return inferred
    if raw_type == "ip":
        try:
            return {"type": "ip", "value": str(ipaddress.ip_address(raw_value))}
        except ValueError:
            return None
    if raw_type in {"domain", "host"} and _HOSTNAME_RE.fullmatch(raw_value):
        try:
            return {"type": "domain", "value": canonical_domain(raw_value.rstrip("."))}
        except CanonicalizationError:
            return None
    return None


def _atlas_type_for_target_type(target_type):
    normalized = _trim_text(target_type, 32).lower()
    if normalized == "host":
        return "domain"
    if normalized in PROJECT_TARGET_ENTITY_TYPES:
        return normalized
    return ""


def _canonical_target_payload(payload):
    payload_type = _trim_text((payload or {}).get("type"), 32).lower()
    target_type = _atlas_type_for_target_type(payload_type)
    if not target_type:
        raise ProjectWorkspaceError("Atlas targets support domain, url, and ip")
    raw_value = _trim_text((payload or {}).get("value"), MAX_TARGET_VALUE_LEN)
    if not raw_value:
        raise ProjectWorkspaceError("target value is required")
    if payload_type == "host":
        try:
            return "ip", canonical_entity("ip", raw_value)
        except CanonicalizationError:
            pass
    try:
        canonical_value = canonical_entity(target_type, raw_value)
    except CanonicalizationError as exc:
        raise ProjectWorkspaceError(str(exc)) from None
    return target_type, canonical_value


def _select_project_target_row(conn, session_id, project_id, entity_id, *, team_id=""):
    project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
    return conn.execute(
        "SELECT e.id, l.project_id, e.type, e.canonical_value, "
        "COALESCE(("
        "SELECT erl.run_id FROM entity_run_links erl "
        "JOIN project_links run_link ON run_link.entity_type = 'run' AND run_link.entity_id = erl.run_id "
        "WHERE erl.entity_id = e.id AND run_link.project_id = l.project_id "
        "ORDER BY erl.last_seen_at DESC, erl.run_id DESC LIMIT 1"
        "), '') AS source_run_id, "
        "l.confidence, l.review_state, l.source, l.source_detail, "
        "e.occurrence_count, e.last_seen_at, e.created, COALESCE(NULLIF(l.updated, ''), l.created) AS updated "
        "FROM project_links l "
        "JOIN projects p ON p.id = l.project_id "
        "JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND " + project_owner_sql + " AND e.id = ?",  # nosec
        (project_id, *project_owner_params, entity_id),
    ).fetchone()


def _project_link_count(conn, project_id, entity_type):
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ? AND entity_type = ?",
        (project_id, entity_type),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def _target_source_detail(source_detail):
    detail = dict(source_detail) if isinstance(source_detail, dict) else {}
    detail[PROJECT_TARGET_SOURCE_DETAIL_FLAG] = True
    return detail


def _source_detail_marks_project_target(source_detail):
    detail = dialect_for_backend(get_db_backend()).decode_json_dict(source_detail)
    if not isinstance(detail, dict):
        return False
    value = detail.get(PROJECT_TARGET_SOURCE_DETAIL_FLAG)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _project_target_link_count(conn, session_id, project_id, *, team_id=""):
    project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
    rows = conn.execute(
        "SELECT l.source, l.source_detail "
        "FROM project_links l "
        "JOIN projects p ON p.id = l.project_id "
        "JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND " + project_owner_sql + " AND e.type IN ('domain', 'ip', 'url')",  # nosec
        (project_id, *project_owner_params),
    ).fetchall()
    count = 0
    for row in rows:
        source = str(row["source"] or "")
        if source in {"auto_command", "auto_input_file"} or _source_detail_marks_project_target(row["source_detail"]):
            count += 1
    return count


def _run_belongs_to_owner(conn, session_id, run_id, *, team_id=""):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT 1 FROM runs WHERE " + owner_sql + " AND id = ?",  # nosec
        (*owner_params, run_id),
    ).fetchone()
    return row is not None


def _ensure_project_entity_link(
    conn,
    session_id,
    project_id,
    entity_type,
    canonical_value,
    source,
    *,
    confidence=1.0,
    review_state="confirmed",
    source_detail=None,
    team_id="",
):
    source = validate_project_link_source(source)
    source_detail = _target_source_detail(source_detail)
    detail_json = dialect_for_backend(get_db_backend()).json_param(source_detail)
    entity_id = upsert_entity(
        conn,
        session_id,
        entity_type,
        canonical_value,
        team_id=team_id,
        seen_at=_now(),
        occurrence_count=0,
    )
    row = conn.execute(
        "SELECT id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
        (project_id, entity_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE project_links SET source = ?, confidence = ?, review_state = ?, source_detail = ?, updated = ? "
            "WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (source, confidence, review_state, detail_json, _now(), project_id, entity_id),
        )
        return entity_id
    if not row and _quota_exceeded(
        _project_link_count(conn, project_id, "atlas_entity"),
        "max_project_entities_per_project",
        5000,
    ):
        _raise_quota("project entity quota exceeded for this project")
    if not row and _quota_exceeded(
        _project_target_link_count(conn, session_id, project_id, team_id=team_id),
        "max_project_targets_per_project",
        200,
    ):
        _raise_quota("project target quota exceeded for this project")
    _insert_project_link(
        conn,
        project_id,
        "atlas_entity",
        entity_id,
        source,
        confidence=confidence,
        review_state=review_state,
        source_detail=source_detail,
    )
    return entity_id


def _link_entity_to_run(conn, entity_id: str, run_id: str, timestamp: str, occurrence_count: int = 0) -> None:
    if not entity_id or not run_id:
        return
    conn.execute(
        "INSERT INTO entity_run_links "
        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(entity_id, run_id) DO NOTHING",
        (entity_id, run_id, timestamp, timestamp, max(0, int(occurrence_count or 0))),
    )


def _link_url_host_to_run(
    conn,
    session_id: str,
    run_id: str,
    canonical_url_value: str,
    timestamp: str,
    *,
    team_id: str = "",
) -> str:
    host_identity = url_host_identity(canonical_url_value)
    if host_identity is None:
        return ""
    host_type, host_value = host_identity
    host_entity_id = upsert_entity(
        conn,
        session_id,
        host_type,
        host_value,
        team_id=team_id,
        seen_at=timestamp,
        occurrence_count=0,
    )
    _link_entity_to_run(conn, host_entity_id, run_id, timestamp, 0)
    return host_entity_id


def ensure_project_target_on_conn(
    conn,
    session_id,
    project_id,
    entity_type,
    canonical_value,
    *,
    source="auto_input_file",
    confidence=1.0,
    review_state="confirmed",
    source_detail=None,
    team_id="",
):
    return _ensure_project_entity_link(
        conn,
        session_id,
        project_id,
        entity_type,
        canonical_value,
        source,
        confidence=confidence,
        review_state=review_state,
        source_detail=source_detail,
        team_id=team_id,
    )


def _target_payloads_from_target_list_file(session_id, raw_item):
    if not isinstance(raw_item, dict) or str(raw_item.get("source_kind") or "") != "flag":
        return []
    if str(raw_item.get("target_list_file") or "") != "1":
        return []
    workspace_path = _trim_text(raw_item.get("value"), MAX_TARGET_VALUE_LEN)
    if not workspace_path or os.path.isabs(workspace_path):
        return []
    try:
        text = read_workspace_text_file(session_id, workspace_path, _config.CFG)
    except (OSError, WorkspaceError) as exc:
        log.warning("PROJECT_TARGET_DISCOVERY_FILE_READ_FAILED", extra={
            "session": get_log_session_id(session_id),
            "workspace_path": workspace_path[:256],
            "error_type": type(exc).__name__,
            "source_name": _trim_text(raw_item.get("source_name"), 128),
            "value_type": _trim_text(raw_item.get("value_type"), 32),
        })
        return []
    payloads = []
    seen = set()
    for raw_line in text[:MAX_PROJECT_TARGET_DISCOVERY_FILE_BYTES].splitlines()[:MAX_PROJECT_TARGET_DISCOVERY_FILE_LINES]:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        payload = _target_payload_from_typed_value(line, raw_item.get("value_type"))
        if not payload:
            continue
        key = (payload["type"], payload["value"])
        if key in seen:
            continue
        seen.add(key)
        payloads.append((payload, {
            "kind": "input_file",
            "name": _trim_text(raw_item.get("source_name"), 128),
            "path": workspace_path,
            "value_type": _trim_text(raw_item.get("value_type"), 32),
        }))
    return payloads


def infer_project_target_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("target payload must be an object")
    if any(key in data for key in ("label", "labels", "note", "notes")):
        raise ProjectWorkspaceError("target labels and notes use entity metadata routes")
    explicit = _target_payload_from_candidate(data.get("value"))
    if explicit:
        return {
            **explicit,
            "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
            "confidence": 1.0,
        }
    text = str(data.get("text") or "")
    for match in _URL_RE.finditer(text):
        inferred = _target_payload_from_candidate(match.group(0))
        if inferred:
            return {
                **inferred,
                "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
                "confidence": 0.9,
            }
    for token in re.split(r"\s+", text):
        inferred = _target_payload_from_candidate(token)
        if inferred:
            return {
                **inferred,
                "source_run_id": _trim_text(data.get("source_run_id"), MAX_ENTITY_ID_LEN),
                "confidence": 0.8,
            }
    raise ProjectWorkspaceError("could not infer a project target from the supplied text")


def _normalized_target_entity_type(target_type):
    normalized = _trim_text(target_type, 32).lower()
    if normalized == "host":
        return "domain"
    return normalized if normalized in PROJECT_TARGET_ENTITY_TYPES else ""


def _target_query_filters(*, target_type="", query="", auto_discovered=False):
    extra_where = []
    params = []
    normalized_type = _normalized_target_entity_type(target_type)
    search = _trim_text(query, MAX_TARGET_VALUE_LEN).lower()
    if search:
        extra_where.append("AND LOWER(e.canonical_value) LIKE ?")
        params.append(f"%{search}%")
    if auto_discovered:
        extra_where.append("AND l.source IN ('auto_command', 'auto_input_file')")
    return normalized_type, " ".join(extra_where), params


def _project_target_page_payload(targets, total, limit, offset, counts_by_type=None):
    return _page_payload(
        "targets",
        targets,
        total,
        limit,
        offset,
        extra={"counts_by_type": counts_by_type if isinstance(counts_by_type, dict) else {}},
    )


def list_project_targets(
    session_id,
    project_id,
    *,
    target_type="",
    query="",
    auto_discovered=False,
    limit=50,
    offset=0,
    team_id="",
    include_provenance=False,
):
    safe_limit, safe_offset = _normalize_page_window(limit, offset)
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
        run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="er")
        metadata_session = metadata_owner_id(session_id, team_id)
        project = conn.execute(
            "SELECT 1 FROM projects p WHERE " + project_owner_sql + " AND p.id = ?",  # nosec
            (*project_owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        normalized_type, extra_where, filter_params = _target_query_filters(
            target_type=target_type,
            query=query,
            auto_discovered=auto_discovered,
        )
        search = _trim_text(query, MAX_TARGET_VALUE_LEN).lower()
        search_like = f"%{search}%"
        auto_filter_enabled = 1 if auto_discovered else 0
        counts_rows = conn.execute(
            "SELECT e.type, COUNT(*) AS count "
            "FROM project_links l "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
            "AND " + project_owner_sql + " AND COALESCE(e.suppressed, FALSE) = FALSE "  # nosec
            "AND e.type IN ('domain', 'ip', 'url') "
            "AND (? = '' OR LOWER(e.canonical_value) LIKE ?) "
            "AND (? = 0 OR l.source IN ('auto_command', 'auto_input_file')) "
            "GROUP BY e.type",
            (project_id, *project_owner_params, search, search_like, auto_filter_enabled),
        ).fetchall()
        counts_by_type = {str(row["type"] or ""): int(row["count"] or 0) for row in counts_rows}
        total = int(counts_by_type.get(normalized_type, 0)) if normalized_type else sum(counts_by_type.values())
        type_filter = "AND e.type IN ('domain', 'ip', 'url') "
        params: list[object] = [
            *run_owner_params,
            metadata_session,
            metadata_session,
            metadata_session,
            project_id,
            *project_owner_params,
        ]
        if normalized_type:
            type_filter += "AND e.type = ? "
            params.append(normalized_type)
        dialect = dialect_for_backend(get_db_backend())
        provider_list_expr = dialect.string_agg_distinct("eis.provider")
        value_order_expr = dialect.case_insensitive_order("e.canonical_value")
        rows = conn.execute(
            "SELECT e.id, l.id AS link_id, l.project_id, e.type, e.canonical_value, "  # nosec
            "COALESCE(("
            "SELECT erl.run_id FROM entity_run_links erl "
            "JOIN project_links run_link ON run_link.entity_type = 'run' AND run_link.entity_id = erl.run_id "
            "WHERE erl.entity_id = e.id AND run_link.project_id = l.project_id "
            "ORDER BY erl.last_seen_at DESC, erl.run_id DESC LIMIT 1"
            "), '') AS source_run_id, "
            "l.confidence, l.review_state, l.source, l.source_detail, "
            "e.occurrence_count, e.suppressed, e.suppressed_reason, e.suppressed_at, "
            "e.last_seen_at, e.created, COALESCE(NULLIF(l.updated, ''), l.created) AS updated, "
            "COALESCE(("
            "SELECT COUNT(DISTINCT erl.run_id) FROM entity_run_links erl "
            "JOIN runs er ON er.id = erl.run_id AND " + run_owner_sql + " "
            "WHERE erl.entity_id = e.id"
            "), 0) AS run_count, "
            "COALESCE(("
            "SELECT COUNT(DISTINCT eis.provider) FROM entity_intel_snapshots eis "
            "WHERE eis.session_id = ? AND eis.entity_id = e.id "
            "AND (eis.status = 'ok' OR eis.status = 'partial')"
            "), 0) AS intel_provider_count, "
            "COALESCE(("
            "SELECT " + provider_list_expr + " FROM entity_intel_snapshots eis "
            "WHERE eis.session_id = ? AND eis.entity_id = e.id "
            "AND (eis.status = 'ok' OR eis.status = 'partial')"
            "), '') AS intel_providers, "
            "COALESCE(("
            "SELECT MAX(eis.fetched_at) FROM entity_intel_snapshots eis "
            "WHERE eis.session_id = ? AND eis.entity_id = e.id "
            "AND (eis.status = 'ok' OR eis.status = 'partial')"
            "), '') AS intel_last_refreshed "
            "FROM project_links l "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' AND " + project_owner_sql + " "
            "AND COALESCE(e.suppressed, FALSE) = FALSE "
            + type_filter
            + (extra_where + " " if extra_where else "")
            + "ORDER BY e.type ASC, "
            + value_order_expr
            + ", e.id ASC"
            + " LIMIT ? OFFSET ?",
            (*params, *filter_params, safe_limit, safe_offset),
        ).fetchall()
        targets = [_row_to_target(row, include_provenance=include_provenance) for row in rows]
        _attach_target_metadata(conn, session_id, targets, team_id=team_id)
    return _project_target_page_payload(targets, total, safe_limit, safe_offset, counts_by_type)


def add_project_target(session_id, project_id, data, *, team_id=""):
    payload = _normalize_target_payload(data)
    entity_type, canonical_value = _canonical_target_payload(payload)
    if payload.get("type") in LEGACY_PROJECT_TARGET_TYPE_ALIASES:
        _log_target_type_canonicalized(
            "PROJECT_TARGET_TYPE_CANONICALIZED",
            level=logging.DEBUG,
            session_id=session_id,
            project_id=project_id,
            input_type=payload.get("type"),
            resolved_type=entity_type,
            value=payload.get("value"),
            source="manual",
            team_id=team_id,
        )
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            [*project_owner_params, project_id],
        ).fetchone()
        if not project:
            return None
        if payload.get("type") in LEGACY_PROJECT_TARGET_TYPE_ALIASES:
            _log_target_type_canonicalized(
                "PROJECT_TARGET_LEGACY_TYPE_ALIAS_USED",
                level=logging.WARNING,
                session_id=session_id,
                project_id=project_id,
                input_type=payload.get("type"),
                resolved_type=entity_type,
                value=payload.get("value"),
                source="manual",
                team_id=team_id,
            )
        if payload["source_run_id"] and not _run_belongs_to_owner(
            conn,
            session_id,
            payload["source_run_id"],
            team_id=team_id,
        ):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        entity_id = _ensure_project_entity_link(
            conn,
            session_id,
            project_id,
            entity_type,
            canonical_value,
            "manual",
            confidence=payload["confidence"],
            review_state=payload.get("review_state", "confirmed"),
            source_detail=payload.get("source_detail"),
            team_id=team_id,
        )
        if payload["source_run_id"]:
            linked_at = _now()
            _link_entity_to_run(conn, entity_id, payload["source_run_id"], linked_at, 0)
            if entity_type == "url":
                _link_url_host_to_run(
                    conn,
                    session_id,
                    payload["source_run_id"],
                    canonical_value,
                    linked_at,
                    team_id=team_id,
                )
        row = _select_project_target_row(conn, session_id, project_id, entity_id, team_id=team_id)
        target = _row_to_target(row)
        _attach_target_metadata(conn, session_id, [target], team_id=team_id)
        conn.commit()
        return target


def record_project_target_discoveries(conn, session_id, project_id, run_id, command_inputs):
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    if not project_id or not run_id:
        return []
    project = conn.execute(
        "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
        (session_id, project_id),
    ).fetchone()
    if not project:
        return []
    created = _now()
    recorded = []
    seen_values = set()
    input_items = command_inputs if isinstance(command_inputs, list) else []
    for raw_item in input_items:
        if len(recorded) >= MAX_PROJECT_TARGET_DISCOVERY_PER_RUN:
            break
        if not isinstance(raw_item, dict):
            continue
        is_target_list_file = str(raw_item.get("target_list_file") or "") == "1"
        direct_payload = None if is_target_list_file else _target_payload_from_typed_value(
            raw_item.get("value"),
            raw_item.get("value_type"),
        )
        source_detail = {
            "kind": _trim_text(raw_item.get("source_kind"), 64),
            "name": _trim_text(raw_item.get("source_name"), 128),
            "value_type": _trim_text(raw_item.get("value_type"), 32),
        }
        source_detail = {key: value for key, value in source_detail.items() if value}
        payload_items = [(direct_payload, source_detail, "auto_command", 1.0)] if direct_payload else []
        if not payload_items:
            payload_items.extend(
                (payload, detail, "auto_input_file", 0.85)
                for payload, detail in _target_payloads_from_target_list_file(session_id, raw_item)
            )
        for payload, detail, source, confidence in payload_items:
            if len(recorded) >= MAX_PROJECT_TARGET_DISCOVERY_PER_RUN:
                break
            if not payload:
                continue
            key = (payload["type"], payload["value"])
            if key in seen_values:
                continue
            seen_values.add(key)
            try:
                entity_type, canonical_value = _canonical_target_payload(payload)
            except ProjectWorkspaceError as exc:
                log.debug("PROJECT_TARGET_DISCOVERY_PAYLOAD_SKIPPED", extra={
                    "session": get_log_session_id(session_id),
                    "project_id": project_id,
                    "run_id": run_id,
                    "source": source,
                    "value_type": _trim_text(detail.get("value_type"), 32),
                    "value_kind": _value_kind(payload.get("value")),
                    "value_hash": _value_hash(payload.get("value")),
                    "reason": str(exc)[:160],
                })
                continue
            existing_entity = conn.execute(
                "SELECT id FROM entities WHERE session_id = ? AND type = ? AND signature_hash = ?",
                (session_id, entity_type, entity_signature(entity_type, canonical_value)),
            ).fetchone()
            already_linked = False
            if existing_entity:
                already_linked = conn.execute(
                    "SELECT 1 FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                    (project_id, existing_entity["id"]),
                ).fetchone() is not None
            entity_id = _ensure_project_entity_link(
                conn,
                session_id,
                project_id,
                entity_type,
                canonical_value,
                source,
                confidence=confidence,
                review_state="pending",
                source_detail=detail,
            )
            _link_entity_to_run(conn, entity_id, run_id, created, 0)
            if entity_type == "url":
                _link_url_host_to_run(conn, session_id, run_id, canonical_value, created)
            if already_linked:
                continue
            row = _select_project_target_row(conn, session_id, project_id, entity_id)
            target = _row_to_target(row)
            if target and all(item.get("id") != target["id"] for item in recorded):
                recorded.append(target)
    return recorded


def update_project_target(session_id, project_id, target_id, data, *, team_id=""):
    target_id = _trim_text(target_id, MAX_ENTITY_ID_LEN)
    payload = _normalize_target_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("target update payload is empty")
    with get_db_connect()() as conn:
        current = _select_project_target_row(conn, session_id, project_id, target_id, team_id=team_id)
        if not current:
            return None
        if "review_state" in payload and payload["review_state"] == "dismissed":
            target = _row_to_target(current)
            if target:
                target["review_state"] = "dismissed"
                target["status"] = "dismissed"
            conn.execute(
                "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                (project_id, target_id),
            )
            conn.commit()
            return target
        target_type = payload.get("type", current["type"])
        value = payload.get("value", current["canonical_value"])
        source_run_id = payload.get("source_run_id", current["source_run_id"])
        if source_run_id and not _run_belongs_to_owner(conn, session_id, source_run_id, team_id=team_id):
            raise ProjectWorkspaceError("source_run_id not found for this session")
        entity_type, canonical_value = _canonical_target_payload({"type": target_type, "value": value})
        if str(target_type or "").strip().lower() in LEGACY_PROJECT_TARGET_TYPE_ALIASES:
            _log_target_type_canonicalized(
                "PROJECT_TARGET_TYPE_CANONICALIZED",
                level=logging.DEBUG,
                session_id=session_id,
                project_id=project_id,
                input_type=target_type,
                resolved_type=entity_type,
                value=value,
                source=payload.get("source", current["source"]),
                team_id=team_id,
            )
            _log_target_type_canonicalized(
                "PROJECT_TARGET_LEGACY_TYPE_ALIAS_USED",
                level=logging.WARNING,
                session_id=session_id,
                project_id=project_id,
                input_type=target_type,
                resolved_type=entity_type,
                value=value,
                source=payload.get("source", current["source"]),
                team_id=team_id,
            )
        entity_id = _ensure_project_entity_link(
            conn,
            session_id,
            project_id,
            entity_type,
            canonical_value,
            payload.get("source", current["source"]),
            confidence=payload.get("confidence", current["confidence"]),
            review_state=payload.get("review_state", current["review_state"]),
            source_detail=payload.get("source_detail"),
            team_id=team_id,
        )
        if entity_id != target_id:
            conn.execute(
                "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                (project_id, target_id),
            )
        if source_run_id:
            conn.execute(
                "INSERT INTO entity_run_links "
                "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                "VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(entity_id, run_id) DO NOTHING",
                (entity_id, source_run_id, _now(), _now()),
            )
        row = _select_project_target_row(conn, session_id, project_id, entity_id, team_id=team_id)
        target = _row_to_target(row)
        _attach_target_metadata(conn, session_id, [target], team_id=team_id)
        conn.commit()
    return target


def delete_project_target(session_id, project_id, target_id, *, team_id=""):
    target_id = _trim_text(target_id, MAX_ENTITY_ID_LEN)
    if not target_id:
        raise ProjectWorkspaceError("target id is required")
    with get_db_connect()() as conn:
        project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + project_owner_sql + " AND id = ?",  # nosec
            (*project_owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        metadata_owner_sql, metadata_owner_params = _metadata_owner_where(session_id, team_id)
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' AND entity_id = ?",  # nosec
            (*metadata_owner_params, target_id),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' AND entity_id = ?",  # nosec
            (*metadata_owner_params, target_id),
        )
        result = conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (project_id, target_id),
        )
        conn.commit()
    return result.rowcount > 0
