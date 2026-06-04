"""Atlas auto-promote rule storage and matching helpers."""

from __future__ import annotations

import fnmatch
import ipaddress
import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import config as _config
from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_log_session_id
from services.intel.canonical import CanonicalizationError, canonical_entity
from services.intel.schema import ENTITY_TYPES
from services.projects.contracts import MAX_ENTITY_ID_LEN, ProjectWorkspaceError, ProjectWorkspaceNotFound
from services.projects.links import (
    _budget_available,
    _consume_budget,
    _insert_project_link,
    _project_link_budgets,
)
from services.projects.scope import shared_owner_where
from services.projects.utils import cfg_int, now as _now, raise_quota as _raise_quota, trim_text as _trim_text


AUTO_PROMOTE_LINK_SOURCE = "auto_promote_rule"
AUTO_PROMOTE_TABLE = "project_auto_promote_rules"
AUTO_PROMOTE_ENTITY_TYPE = "atlas_entity"
AUTO_PROMOTE_TARGET_KINDS = frozenset({"any", *ENTITY_TYPES})
AUTO_PROMOTE_MATCH_MODES = frozenset({"exact", "contains", "wildcard", "domain_suffix", "cidr", "regex"})
PROMOTABLE_PROJECT_LINK_SOURCES = frozenset({"auto_command", "auto_input_file"})
MIN_BROAD_PATTERN_CHARS = 3
DEFAULT_PREVIEW_LIMIT = 200
DEFAULT_APPLY_LIMIT = 1000
DEFAULT_RUN_MATCH_LIMIT = 100
DEFAULT_RUN_RULE_LIMIT = 50
LIKE_ESCAPE_CHAR = "\\"
DOMAIN_SUFFIX_TARGET_KINDS = frozenset({"any", "domain", "url"})
CIDR_TARGET_KINDS = frozenset({"any", "ip"})


log = logging.getLogger("shell")


def _new_rule_id() -> str:
    import secrets

    return "apr_" + secrets.token_hex(8)


def _bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on", "enabled"}:
        return True
    if token in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _list_strings(value: object, *, limit: int = MAX_ENTITY_ID_LEN) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list | tuple | set) else [value]
    return [_trim_text(item, limit) for item in values if _trim_text(item, limit)]


def _command_root(value: object) -> str:
    return str(value or "").strip().split(maxsplit=1)[0].lower()


def _escape_like_pattern(value: str) -> str:
    return (
        value.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR + LIKE_ESCAPE_CHAR)
        .replace("%", LIKE_ESCAPE_CHAR + "%")
        .replace("_", LIKE_ESCAPE_CHAR + "_")
    )


def _exact_any_patterns(pattern: str) -> list[str]:
    values = {pattern.strip().lower()}
    for entity_type in sorted(ENTITY_TYPES):
        try:
            if entity_type == "hash" and ":" in pattern:
                algorithm, token = pattern.split(":", 1)
                values.add(canonical_entity(entity_type, token, algorithm=algorithm).lower())
            else:
                values.add(canonical_entity(entity_type, pattern).lower())
        except CanonicalizationError:
            continue
    return sorted(values)


def _rule_filters(rule: Mapping[str, Any]) -> dict[str, Any]:
    filters = rule.get("filters")
    return dict(filters) if isinstance(filters, Mapping) else {}


def _source_filter_counts(rule: Mapping[str, Any]) -> dict[str, int]:
    filters = _rule_filters(rule)
    return {
        "source_run_filter_count": len(_list_strings(filters.get("source_run_ids"))),
        "source_command_root_filter_count": len([
            root
            for root in (_command_root(item) for item in _list_strings(filters.get("source_command_roots"), limit=128))
            if root
        ]),
    }


def _safe_rule_fields(rule: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "project_id": str(rule.get("project_id") or ""),
        "rule_id": str(rule.get("id") or ""),
        "target_entity_kind": str(rule.get("target_entity_kind") or ""),
        "match_mode": str(rule.get("match_mode") or ""),
    }


def _log_context(session_id: str, team_id: str, project_id: str, rule: Mapping[str, Any], *, run_id: str = ""):
    context = {
        "session": get_log_session_id(session_id),
        "team_id": team_id,
        **_safe_rule_fields(rule),
        "project_id": project_id or str(rule.get("project_id") or ""),
    }
    if run_id:
        context["run_id"] = run_id
    context.update(_source_filter_counts(rule))
    return context


def _log_warn_if_limited(
    result: Mapping[str, Any],
    session_id: str,
    team_id: str,
    project_id: str,
    rule: Mapping[str, Any],
    *,
    run_id: str = "",
):
    context = _log_context(session_id, team_id, project_id, rule, run_id=run_id)
    quota_limited_count = int(result.get("quota_limited_count") or 0)
    if quota_limited_count:
        log.warning("PROJECT_AUTO_PROMOTE_QUOTA_LIMITED", extra={
            **context,
            "quota_limited_count": quota_limited_count,
            "linked_count": int(result.get("linked_count") or 0),
            "new_link_count": int(result.get("new_link_count") or 0),
            "promoted_count": int(result.get("promoted_count") or 0),
        })
    match_cap_limited_count = int(result.get("match_cap_limited_count") or 0)
    candidate_scan_limited_count = int(result.get("candidate_scan_limited_count") or 0)
    if match_cap_limited_count or candidate_scan_limited_count:
        log.warning("PROJECT_AUTO_PROMOTE_MATCH_CAP_LIMITED", extra={
            **context,
            "match_cap_limited_count": match_cap_limited_count,
            "candidate_scan_limited_count": candidate_scan_limited_count,
            "matched_count": int(result.get("matched_count") or 0),
            "matched_in_scan_count": int(result.get("matched_in_scan_count") or 0),
            "candidate_scan_count": int(result.get("candidate_scan_count") or 0),
            "candidate_scan_limit": int(result.get("candidate_scan_limit") or 0),
            "limit": int(result.get("limit") or 0),
            "truncated": bool(result.get("truncated") or result.get("candidate_scan_truncated")),
        })


def _row_value(row: Any, key: str) -> Any:
    if not row:
        return None
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _promotable_project_link(row: Any) -> bool:
    if not row:
        return False
    return (
        str(_row_value(row, "source") or "") in PROMOTABLE_PROJECT_LINK_SOURCES
        and str(_row_value(row, "review_state") or "") == "pending"
    )


def _non_wildcard_chars(pattern: str) -> int:
    return len([ch for ch in pattern if ch not in {"*", "?", "[", "]", "!"}])


def _normalize_target_kind(value: object) -> str:
    target_kind = str(value or "any").strip().lower()
    if target_kind == "host":
        target_kind = "domain"
    if target_kind not in AUTO_PROMOTE_TARGET_KINDS:
        raise ProjectWorkspaceError("unsupported auto-promote target entity kind")
    return target_kind


def _normalize_match_mode(value: object) -> str:
    match_mode = str(value or "").strip().lower()
    if match_mode not in AUTO_PROMOTE_MATCH_MODES:
        raise ProjectWorkspaceError("unsupported auto-promote match mode")
    return match_mode


def _normalize_filters(value: object) -> dict[str, Any]:
    filters = dict(value) if isinstance(value, Mapping) else {}
    source_run_ids = _list_strings(filters.get("source_run_ids"))
    source_command_roots = [_command_root(item) for item in _list_strings(filters.get("source_command_roots"), limit=128)]
    source_command_roots = [root for root in source_command_roots if root]
    normalized: dict[str, Any] = {
        "source_run_ids": source_run_ids,
        "source_command_roots": source_command_roots,
        "first_seen_after_rule_created": _bool(filters.get("first_seen_after_rule_created"), default=False),
        "include_suppressed": _bool(filters.get("include_suppressed"), default=False),
    }
    runtime_run_id = _trim_text(filters.get("_runtime_run_id"), MAX_ENTITY_ID_LEN)
    if runtime_run_id:
        normalized["_runtime_run_id"] = runtime_run_id
    return normalized


def _normalize_pattern(match_mode: str, target_kind: str, pattern: object) -> str:
    raw = str(pattern or "").strip()
    if not raw:
        raise ProjectWorkspaceError("auto-promote pattern is required")
    if match_mode == "regex":
        raise ProjectWorkspaceError("regex auto-promote rules need a safe regex engine before they can be enabled")
    if match_mode == "domain_suffix":
        if target_kind not in DOMAIN_SUFFIX_TARGET_KINDS:
            raise ProjectWorkspaceError("domain_suffix auto-promote rules only support any, domain, or url targets")
        try:
            return canonical_entity("domain", raw.lstrip("."))
        except CanonicalizationError as exc:
            raise ProjectWorkspaceError("invalid domain suffix pattern") from exc
    if match_mode == "cidr":
        if target_kind not in CIDR_TARGET_KINDS:
            raise ProjectWorkspaceError("cidr auto-promote rules only support any or ip targets")
        try:
            return str(ipaddress.ip_network(raw, strict=False))
        except ValueError as exc:
            raise ProjectWorkspaceError("invalid CIDR pattern") from exc
    if match_mode == "exact" and target_kind != "any":
        try:
            if target_kind == "hash" and ":" in raw:
                algorithm, token = raw.split(":", 1)
                return canonical_entity(target_kind, token, algorithm=algorithm)
            return canonical_entity(target_kind, raw)
        except CanonicalizationError as exc:
            raise ProjectWorkspaceError("invalid exact-match pattern") from exc
    if match_mode == "contains" and len(raw) < MIN_BROAD_PATTERN_CHARS:
        raise ProjectWorkspaceError("contains auto-promote patterns must be at least 3 characters")
    if match_mode == "wildcard" and _non_wildcard_chars(raw) < MIN_BROAD_PATTERN_CHARS:
        raise ProjectWorkspaceError("wildcard auto-promote patterns need at least 3 non-wildcard characters")
    return raw


def normalize_rule_payload(data: Mapping[str, Any] | None, *, existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ProjectWorkspaceError("auto-promote rule payload must be an object")
    current = dict(existing or {})
    name = _trim_text(data.get("name", current.get("name")), 120)
    if not name:
        raise ProjectWorkspaceError("auto-promote rule name is required")
    target_kind = _normalize_target_kind(data.get("target_entity_kind", current.get("target_entity_kind", "any")))
    match_mode = _normalize_match_mode(data.get("match_mode", current.get("match_mode")))
    pattern = _normalize_pattern(match_mode, target_kind, data.get("pattern", current.get("pattern")))
    filters = _normalize_filters(data.get("filters", data.get("filters_json", current.get("filters", {}))))
    return {
        "name": name,
        "enabled": _bool(data.get("enabled", current.get("enabled", True)), default=True),
        "target_entity_kind": target_kind,
        "match_mode": match_mode,
        "pattern": pattern,
        "filters": filters,
        "apply_on_run": _bool(data.get("apply_on_run", current.get("apply_on_run", False)), default=False),
    }


def _decode_filters(value: object) -> dict[str, Any]:
    return _normalize_filters(dialect_for_backend(DB_BACKEND).decode_json_dict(value))


def row_to_rule(row) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "enabled": bool(row["enabled"]),
        "target_entity_kind": row["target_entity_kind"],
        "match_mode": row["match_mode"],
        "pattern": row["pattern"],
        "filters": _decode_filters(row["filters_json"]),
        "apply_on_run": bool(row["apply_on_run"]),
        "created_by_session_id": row["created_by_session_id"],
        "created_by_member_id": row["created_by_member_id"],
        "created": row["created"],
        "updated": row["updated"],
        "last_applied_at": row["last_applied_at"],
        "match_count": int(row["match_count"] or 0),
        "linked_count": int(row["linked_count"] or 0),
    }


def _project_exists(conn, session_id: str, project_id: str, *, team_id: str = "") -> bool:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ? AND status != 'archived'",  # nosec
        (*owner_params, project_id),
    ).fetchone()
    return bool(row)


def _project_rule_count(conn, project_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM project_auto_promote_rules WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def create_rule_on_conn(
    conn,
    session_id: str,
    project_id: str,
    data: Mapping[str, Any],
    *,
    team_id: str = "",
    member_id: str = "",
) -> dict[str, Any]:
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id or not _project_exists(conn, session_id, project_id, team_id=team_id):
        raise ProjectWorkspaceNotFound("project not found")
    rule_limit = cfg_int("max_project_auto_promote_rules_per_project", 100, cfg=_config.CFG)
    if rule_limit > 0 and _project_rule_count(conn, project_id) >= rule_limit:
        _raise_quota("project auto-promote rule quota exceeded for this project")
    payload = normalize_rule_payload(data)
    timestamp = _now()
    rule_id = _new_rule_id()
    filters_json = dialect_for_backend(DB_BACKEND).json_param(payload["filters"])
    conn.execute(
        "INSERT INTO project_auto_promote_rules "
        "(id, project_id, name, enabled, target_entity_kind, match_mode, pattern, filters_json, apply_on_run, "
        "created_by_session_id, created_by_member_id, created, updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rule_id,
            project_id,
            payload["name"],
            payload["enabled"],
            payload["target_entity_kind"],
            payload["match_mode"],
            payload["pattern"],
            filters_json,
            payload["apply_on_run"],
            str(session_id or ""),
            _trim_text(member_id, MAX_ENTITY_ID_LEN),
            timestamp,
            timestamp,
        ),
    )
    row = conn.execute("SELECT * FROM project_auto_promote_rules WHERE id = ?", (rule_id,)).fetchone()
    return row_to_rule(row)


def create_rule(session_id: str, project_id: str, data: Mapping[str, Any], *, team_id: str = "", member_id: str = ""):
    with db_connect() as conn:
        rule = create_rule_on_conn(conn, session_id, project_id, data, team_id=team_id, member_id=member_id)
        conn.commit()
    return rule


def list_rules_on_conn(conn, session_id: str, project_id: str, *, team_id: str = "") -> list[dict[str, Any]] | None:
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id or not _project_exists(conn, session_id, project_id, team_id=team_id):
        return None
    rows = conn.execute(
        "SELECT * FROM project_auto_promote_rules WHERE project_id = ? ORDER BY updated DESC, name ASC",
        (project_id,),
    ).fetchall()
    return [row_to_rule(row) for row in rows]


def list_rules(session_id: str, project_id: str, *, team_id: str = "") -> list[dict[str, Any]] | None:
    with db_connect() as conn:
        return list_rules_on_conn(conn, session_id, project_id, team_id=team_id)


def get_rule(session_id: str, project_id: str, rule_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    with db_connect() as conn:
        return get_rule_on_conn(conn, session_id, project_id, rule_id, team_id=team_id)


def get_rule_on_conn(conn, session_id: str, project_id: str, rule_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    rule_id = _trim_text(rule_id, MAX_ENTITY_ID_LEN)
    if not project_id or not rule_id or not _project_exists(conn, session_id, project_id, team_id=team_id):
        return None
    row = conn.execute(
        "SELECT * FROM project_auto_promote_rules WHERE project_id = ? AND id = ?",
        (project_id, rule_id),
    ).fetchone()
    return row_to_rule(row) if row else None


def update_rule_on_conn(
    conn,
    session_id: str,
    project_id: str,
    rule_id: str,
    data: Mapping[str, Any],
    *,
    team_id: str = "",
) -> dict[str, Any] | None:
    current = get_rule_on_conn(conn, session_id, project_id, rule_id, team_id=team_id)
    if current is None:
        return None
    payload = normalize_rule_payload(data, existing=current)
    timestamp = _now()
    conn.execute(
        "UPDATE project_auto_promote_rules "
        "SET name = ?, enabled = ?, target_entity_kind = ?, match_mode = ?, pattern = ?, filters_json = ?, "
        "apply_on_run = ?, updated = ? "
        "WHERE project_id = ? AND id = ?",
        (
            payload["name"],
            payload["enabled"],
            payload["target_entity_kind"],
            payload["match_mode"],
            payload["pattern"],
            dialect_for_backend(DB_BACKEND).json_param(payload["filters"]),
            payload["apply_on_run"],
            timestamp,
            project_id,
            rule_id,
        ),
    )
    return get_rule_on_conn(conn, session_id, project_id, rule_id, team_id=team_id)


def update_rule(session_id: str, project_id: str, rule_id: str, data: Mapping[str, Any], *, team_id: str = ""):
    with db_connect() as conn:
        rule = update_rule_on_conn(conn, session_id, project_id, rule_id, data, team_id=team_id)
        conn.commit()
    return rule


def delete_rule_on_conn(conn, session_id: str, project_id: str, rule_id: str, *, team_id: str = "") -> bool | None:
    current = get_rule_on_conn(conn, session_id, project_id, rule_id, team_id=team_id)
    if current is None:
        return None
    result = conn.execute(
        "DELETE FROM project_auto_promote_rules WHERE project_id = ? AND id = ?",
        (project_id, rule_id),
    )
    return bool(result.rowcount)


def delete_rule(session_id: str, project_id: str, rule_id: str, *, team_id: str = "") -> bool | None:
    with db_connect() as conn:
        deleted = delete_rule_on_conn(conn, session_id, project_id, rule_id, team_id=team_id)
        conn.commit()
    return deleted


def preview_rule(session_id: str, project_id: str, rule: Mapping[str, Any], *, team_id: str = "", limit: int | None = None):
    with db_connect() as conn:
        return preview_rule_on_conn(conn, session_id, project_id, rule, team_id=team_id, limit=limit)


def apply_stored_rule(session_id: str, project_id: str, rule_id: str, *, team_id: str = "", limit: int | None = None):
    with db_connect() as conn:
        conn.execute(dialect_for_backend(DB_BACKEND).begin_immediate_sql())
        rule = get_rule_on_conn(conn, session_id, project_id, rule_id, team_id=team_id)
        if rule is None:
            conn.commit()
            return None
        result = apply_rule_on_conn(conn, session_id, project_id, rule, team_id=team_id, limit=limit)
        conn.commit()
    return result


def _rule_from_input(rule: Mapping[str, Any]) -> dict[str, Any]:
    if "filters_json" in rule:
        return row_to_rule(rule)
    if "filters" in rule and "match_mode" in rule and "target_entity_kind" in rule and "pattern" in rule:
        normalized = normalize_rule_payload(rule)
        resolved = {**dict(rule), **normalized}
    else:
        resolved = normalize_rule_payload(rule)
    filters = _rule_filters(resolved)
    if _bool(filters.get("first_seen_after_rule_created"), default=False) and not str(resolved.get("created") or ""):
        resolved["created"] = _now()
    return resolved


def _rule_enabled(rule: Mapping[str, Any]) -> bool:
    return _bool(rule.get("enabled"), default=True)


def _domain_suffix_subject(entity_type: str, value: str) -> str:
    normalized_type = str(entity_type or "").lower()
    if normalized_type not in {"domain", "url"}:
        return ""
    comparable = str(value or "").strip().rstrip(".").lower()
    if normalized_type != "url":
        return comparable
    parsed = urlsplit(comparable)
    return str(parsed.hostname or "").rstrip(".").lower()


def _python_match(rule: Mapping[str, Any], value: str, *, entity_type: str = "") -> bool:
    match_mode = str(rule["match_mode"])
    pattern = str(rule["pattern"])
    comparable = str(value or "")
    if match_mode == "wildcard":
        return bool(re.fullmatch(fnmatch.translate(pattern), comparable, flags=re.I))
    if match_mode == "domain_suffix":
        suffix = pattern.lower()
        subject = _domain_suffix_subject(entity_type, comparable)
        return subject == suffix or subject.endswith("." + suffix)
    if match_mode == "cidr":
        if str(entity_type or "").lower() != "ip":
            return False
        try:
            return ipaddress.ip_address(comparable) in ipaddress.ip_network(pattern, strict=False)
        except ValueError:
            return False
    if match_mode == "exact":
        return comparable.lower() == pattern.lower()
    if match_mode == "contains":
        return pattern.lower() in comparable.lower()
    return False


def _append_source_filters(where_parts: list[str], params: list[Any], rule: Mapping[str, Any], session_id: str, team_id: str):
    filters = _rule_filters(rule)
    source_run_ids = _list_strings(filters.get("source_run_ids"))
    runtime_run_id = _trim_text(filters.get("_runtime_run_id"), MAX_ENTITY_ID_LEN)
    source_command_roots = [_command_root(item) for item in _list_strings(filters.get("source_command_roots"), limit=128)]
    source_command_roots = [root for root in source_command_roots if root]
    if not runtime_run_id and not source_run_ids and not source_command_roots:
        return
    run_owner_sql, run_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="source_run")
    source_where = [
        "erl.entity_id = e.id",
        "source_run.id = erl.run_id",
        run_owner_sql,
    ]
    params.extend(run_owner_params)
    if runtime_run_id:
        source_where.append("source_run.id = ?")
        params.append(runtime_run_id)
    if source_run_ids:
        source_where.append("source_run.id IN (" + ",".join("?" for _ in source_run_ids) + ")")
        params.extend(source_run_ids)
    if source_command_roots:
        command_root_sql = dialect_for_backend(DB_BACKEND).command_root_expr("source_run.command")
        source_where.append(command_root_sql + " IN (" + ",".join("?" for _ in source_command_roots) + ")")
        params.extend(source_command_roots)
    where_parts.append(
        "EXISTS ("
        "SELECT 1 FROM entity_run_links erl JOIN runs source_run ON source_run.id = erl.run_id "
        "WHERE " + " AND ".join(source_where) + ")"  # nosec
    )


def _candidate_rows(conn, session_id: str, project_id: str, rule: Mapping[str, Any], *, team_id: str, limit: int):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="e")
    where_parts = [owner_sql]
    params: list[Any] = [*owner_params]
    target_kind = str(rule["target_entity_kind"])
    if target_kind != "any":
        where_parts.append("e.type = ?")
        params.append(target_kind)
    filters = _rule_filters(rule)
    if not _bool(filters.get("include_suppressed"), default=False):
        where_parts.append("COALESCE(e.suppressed, FALSE) = FALSE")
    if _bool(filters.get("first_seen_after_rule_created"), default=False) and str(rule.get("created") or ""):
        where_parts.append("e.first_seen_at >= ?")
        params.append(str(rule["created"]))
    match_mode = str(rule["match_mode"])
    pattern = str(rule["pattern"])
    if match_mode == "exact":
        if target_kind == "any":
            exact_patterns = _exact_any_patterns(pattern)
            placeholders = ", ".join("?" for _ in exact_patterns)
            where_parts.append(f"LOWER(e.canonical_value) IN ({placeholders})")
            params.extend(exact_patterns)
        else:
            where_parts.append("LOWER(e.canonical_value) = ?")
            params.append(pattern.lower())
    elif match_mode == "contains":
        where_parts.append("LOWER(e.canonical_value) LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like_pattern(pattern.lower())}%")
    _append_source_filters(where_parts, params, rule, session_id, team_id)
    sql = (
        "SELECT e.id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, e.suppressed "
        "FROM entities e "
        "WHERE " + " AND ".join(where_parts) + " "  # nosec
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC "
        "LIMIT ?"
    )
    return conn.execute(sql, (*params, max(1, limit + 1))).fetchall()


def _matching_rows(rule: Mapping[str, Any], rows) -> list:
    if rule["match_mode"] in {"exact", "contains"}:
        return list(rows)
    return [
        row for row in rows
        if _python_match(rule, str(row["canonical_value"] or ""), entity_type=str(row["type"] or ""))
    ]


def preview_rule_on_conn(
    conn,
    session_id: str,
    project_id: str,
    rule: Mapping[str, Any],
    *,
    team_id: str = "",
    limit: int | None = None,
    include_suppressed_count: bool = True,
) -> dict[str, Any]:
    normalized = _rule_from_input(rule)
    if not _rule_enabled(normalized):
        raise ProjectWorkspaceError("disabled auto-promote rules cannot be previewed or applied")
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id or not _project_exists(conn, session_id, project_id, team_id=team_id):
        raise ProjectWorkspaceNotFound("project not found")
    safe_limit = max(1, int(limit or cfg_int("max_project_auto_promote_preview_matches", DEFAULT_PREVIEW_LIMIT)))
    sql_matched_mode = normalized["match_mode"] in {"exact", "contains"}
    scan_limit = safe_limit if sql_matched_mode else cfg_int("max_project_auto_promote_scan_candidates", 5000)
    scan_limit = max(safe_limit, scan_limit)
    rows = _candidate_rows(conn, session_id, project_id, normalized, team_id=team_id, limit=scan_limit)
    candidate_scan_truncated = not sql_matched_mode and len(rows) > scan_limit
    scanned_rows = rows[:scan_limit]
    matched_rows = list(scanned_rows)
    if not sql_matched_mode:
        matched_rows = _matching_rows(normalized, scanned_rows)
    candidates = matched_rows[:safe_limit]
    skipped_suppressed_count = 0
    filters = _rule_filters(normalized)
    if include_suppressed_count and not _bool(filters.get("include_suppressed"), default=False):
        suppressed_rule = {**normalized, "filters": {**filters, "include_suppressed": True}}
        suppressed_rows = _candidate_rows(conn, session_id, project_id, suppressed_rule, team_id=team_id, limit=scan_limit)
        suppressed_scanned_rows = suppressed_rows[:scan_limit]
        skipped_suppressed_count = len([
            row for row in _matching_rows(suppressed_rule, suppressed_scanned_rows) if bool(row["suppressed"])
        ])
    entity_ids = [str(row["id"]) for row in candidates]
    linked_by_id: dict[str, Any] = {}
    if entity_ids:
        placeholders = ",".join("?" for _ in entity_ids)
        linked_by_id = {
            str(row["entity_id"]): row
            for row in conn.execute(
                "SELECT entity_id, source, review_state FROM project_links "
                "WHERE project_id = ? AND entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                (project_id, *entity_ids),
            ).fetchall()
        }
    new_link_budget, new_entity_budget = _project_link_budgets(conn, project_id, AUTO_PROMOTE_ENTITY_TYPE)
    promotable_count = len([
        entity_id for entity_id in entity_ids if _promotable_project_link(linked_by_id.get(entity_id))
    ])
    new_link_count = len([entity_id for entity_id in entity_ids if entity_id not in linked_by_id])
    quota_available = new_link_budget if new_link_budget is not None else new_link_count
    if new_entity_budget is not None:
        quota_available = min(quota_available, new_entity_budget)
    quota_limited_count = max(0, new_link_count - quota_available)
    match_cap_limited = len(rows) > safe_limit if sql_matched_mode else len(matched_rows) > safe_limit
    shown_match_count = len(candidates)
    matched_in_scan_count = len(matched_rows)
    match_count_is_capped = match_cap_limited or candidate_scan_truncated
    total_matches_known = not match_count_is_capped
    result = {
        "rule": normalized,
        "matches": [
            {
                "id": row["id"],
                "type": row["type"],
                "canonical_value": row["canonical_value"],
                "already_linked": (
                    str(row["id"]) in linked_by_id
                    and not _promotable_project_link(linked_by_id.get(str(row["id"])))
                ),
                "promotable": _promotable_project_link(linked_by_id.get(str(row["id"]))),
            }
            for row in candidates
        ],
        "matched_count": shown_match_count,
        "shown_match_count": shown_match_count,
        "matched_in_scan_count": matched_in_scan_count,
        "match_count_is_capped": match_count_is_capped,
        "total_matches": matched_in_scan_count if total_matches_known else None,
        "total_matches_known": total_matches_known,
        "already_linked_count": len([
            entity_id
            for entity_id in entity_ids
            if entity_id in linked_by_id and not _promotable_project_link(linked_by_id.get(entity_id))
        ]),
        "promotable_count": promotable_count,
        "new_link_count": new_link_count,
        "skipped_suppressed_count": skipped_suppressed_count,
        "quota_limited_count": quota_limited_count,
        "match_cap_limited_count": 1 if match_cap_limited else 0,
        "candidate_scan_limited_count": 1 if candidate_scan_truncated else 0,
        "candidate_scan_truncated": candidate_scan_truncated,
        "candidate_scan_count": len(scanned_rows),
        "candidate_scan_limit": scan_limit,
        "truncated": len(matched_rows) > safe_limit or candidate_scan_truncated,
        "limit": safe_limit,
    }
    log.debug("PROJECT_AUTO_PROMOTE_MATCH_SCAN", extra={
        **_log_context(session_id, team_id, project_id, normalized),
        "sql_matched": sql_matched_mode,
        "include_suppressed": _bool(filters.get("include_suppressed"), default=False),
        "scan_limit": scan_limit,
        "limit": safe_limit,
        "candidate_count": len(scanned_rows),
        "matched_count": shown_match_count,
        "matched_in_scan_count": matched_in_scan_count,
        "already_linked_count": result["already_linked_count"],
        "promotable_count": promotable_count,
        "new_link_count": new_link_count,
        "quota_limited_count": quota_limited_count,
        "match_cap_limited_count": result["match_cap_limited_count"],
        "candidate_scan_limited_count": result["candidate_scan_limited_count"],
        "truncated": result["truncated"],
    })
    if include_suppressed_count:
        _log_warn_if_limited(result, session_id, team_id, project_id, normalized)
    return result


def apply_rule_on_conn(
    conn,
    session_id: str,
    project_id: str,
    rule: Mapping[str, Any],
    *,
    team_id: str = "",
    limit: int | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    safe_limit = max(1, int(limit or cfg_int("max_project_auto_promote_apply_matches", DEFAULT_APPLY_LIMIT, cfg=_config.CFG)))
    preview = preview_rule_on_conn(
        conn,
        session_id,
        project_id,
        rule,
        team_id=team_id,
        limit=safe_limit,
        include_suppressed_count=False,
    )
    normalized = preview["rule"]
    new_link_budget, new_entity_budget = _project_link_budgets(conn, project_id, AUTO_PROMOTE_ENTITY_TYPE)
    linked = 0
    promoted = 0
    rejected = 0
    for item in preview["matches"]:
        if item["already_linked"]:
            continue
        source_detail = {
            "rule_id": str(normalized.get("id") or ""),
            "rule_name": str(normalized.get("name") or ""),
            "target_entity_kind": normalized["target_entity_kind"],
            "match_mode": normalized["match_mode"],
            "pattern": normalized["pattern"],
        }
        if item.get("promotable"):
            detail_json = dialect_for_backend(DB_BACKEND).json_param(source_detail)
            timestamp = _now()
            cursor = conn.execute(
                "UPDATE project_links "
                "SET source = ?, confidence = ?, review_state = 'confirmed', source_detail = ?, updated = ? "
                "WHERE project_id = ? AND entity_type = ? AND entity_id = ? "
                "AND source IN ('auto_command', 'auto_input_file') AND review_state = 'pending'",
                (
                    AUTO_PROMOTE_LINK_SOURCE,
                    1.0,
                    detail_json,
                    timestamp,
                    project_id,
                    AUTO_PROMOTE_ENTITY_TYPE,
                    item["id"],
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) > 0:
                linked += 1
                promoted += 1
            continue
        if not _budget_available(new_link_budget, new_entity_budget):
            rejected += 1
            continue
        _insert_project_link(
            conn,
            project_id,
            AUTO_PROMOTE_ENTITY_TYPE,
            item["id"],
            AUTO_PROMOTE_LINK_SOURCE,
            source_detail=source_detail,
        )
        linked += 1
        new_link_budget = _consume_budget(new_link_budget)
        new_entity_budget = _consume_budget(new_entity_budget)
    if str(normalized.get("id") or ""):
        timestamp = _now()
        conn.execute(
            "UPDATE project_auto_promote_rules "
            "SET last_applied_at = ?, match_count = ?, linked_count = ?, updated = ? WHERE id = ?",
            (timestamp, preview["matched_count"], linked, timestamp, normalized["id"]),
        )
    result = {
        **preview,
        "linked_count": linked,
        "promoted_count": promoted,
        "quota_limited_count": rejected,
    }
    log.debug("PROJECT_AUTO_PROMOTE_LINK_DECISION_SUMMARY", extra={
        **_log_context(session_id, team_id, project_id, normalized, run_id=run_id),
        "sql_matched": normalized["match_mode"] in {"exact", "contains"},
        "include_suppressed": _bool(_rule_filters(normalized).get("include_suppressed"), default=False),
        "limit": safe_limit,
        "candidate_count": int(result.get("candidate_scan_count") or 0),
        "matched_count": int(result.get("matched_count") or 0),
        "matched_in_scan_count": int(result.get("matched_in_scan_count") or 0),
        "already_linked_count": int(result.get("already_linked_count") or 0),
        "promotable_count": int(result.get("promotable_count") or 0),
        "new_link_count": int(result.get("new_link_count") or 0),
        "linked_count": linked,
        "promoted_count": promoted,
        "quota_limited_count": int(result.get("quota_limited_count") or 0),
        "match_cap_limited_count": int(result.get("match_cap_limited_count") or 0),
        "candidate_scan_limited_count": int(result.get("candidate_scan_limited_count") or 0),
        "truncated": bool(result.get("truncated") or result.get("candidate_scan_truncated")),
    })
    _log_warn_if_limited(result, session_id, team_id, project_id, normalized, run_id=run_id)
    return result


def apply_run_rules_on_conn(
    conn,
    session_id: str,
    run_id: str,
    *,
    team_id: str = "",
    match_limit: int | None = None,
    rule_limit: int | None = None,
) -> dict[str, Any]:
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    if not run_id:
        return {
            "rules_evaluated": 0,
            "projects_evaluated": 0,
            "matched_count": 0,
            "linked_count": 0,
            "promoted_count": 0,
            "already_linked_count": 0,
            "skipped_suppressed_count": 0,
            "quota_limited_count": 0,
            "match_cap_limited_count": 0,
            "rule_cap_limited_count": 0,
            "results": [],
        }
    safe_match_limit = max(
        1,
        int(match_limit or cfg_int("max_project_auto_promote_run_matches", DEFAULT_RUN_MATCH_LIMIT, cfg=_config.CFG)),
    )
    safe_rule_limit = max(
        1,
        int(rule_limit or cfg_int("max_project_auto_promote_rules_per_run", DEFAULT_RUN_RULE_LIMIT, cfg=_config.CFG)),
    )
    project_owner_sql, project_owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
    rows = conn.execute(
        "SELECT r.* FROM project_auto_promote_rules r "
        "JOIN projects p ON p.id = r.project_id "
        "WHERE " + project_owner_sql + " AND p.status != 'archived' "  # nosec
        "AND r.enabled = TRUE AND r.apply_on_run = TRUE "
        "ORDER BY r.updated DESC, r.id ASC "
        "LIMIT ?",
        (*project_owner_params, safe_rule_limit + 1),
    ).fetchall()
    rules = [row_to_rule(row) for row in rows[:safe_rule_limit]]
    results = []
    summary = {
        "rules_evaluated": 0,
        "projects_evaluated": 0,
        "matched_count": 0,
        "linked_count": 0,
        "promoted_count": 0,
        "already_linked_count": 0,
        "skipped_suppressed_count": 0,
        "quota_limited_count": 0,
        "match_cap_limited_count": 0,
        "rule_cap_limited_count": 1 if len(rows) > safe_rule_limit else 0,
        "results": results,
    }
    if summary["rule_cap_limited_count"]:
        log.warning("PROJECT_AUTO_PROMOTE_RULE_CAP_LIMITED", extra={
            "session": get_log_session_id(session_id),
            "team_id": team_id,
            "run_id": run_id,
            "rule_cap_limited_count": summary["rule_cap_limited_count"],
            "candidate_rule_count": len(rows),
            "rule_limit": safe_rule_limit,
        })
    project_ids = set()
    for rule in rules:
        project_ids.add(rule["project_id"])
        runtime_filters = dict(rule.get("filters") or {})
        runtime_filters["_runtime_run_id"] = run_id
        runtime_rule = {**rule, "filters": runtime_filters}
        try:
            result = apply_rule_on_conn(
                conn,
                session_id,
                rule["project_id"],
                runtime_rule,
                team_id=team_id,
                limit=safe_match_limit,
                run_id=run_id,
            )
        except Exception:
            log.error("PROJECT_AUTO_PROMOTE_RULE_RUN_APPLY_ERROR", exc_info=True, extra={
                **_log_context(session_id, team_id, rule["project_id"], rule, run_id=run_id),
                "limit": safe_match_limit,
            })
            raise
        summary["rules_evaluated"] += 1
        summary["matched_count"] += int(result.get("matched_count") or 0)
        summary["linked_count"] += int(result.get("linked_count") or 0)
        summary["promoted_count"] += int(result.get("promoted_count") or 0)
        summary["already_linked_count"] += int(result.get("already_linked_count") or 0)
        summary["skipped_suppressed_count"] += int(result.get("skipped_suppressed_count") or 0)
        summary["quota_limited_count"] += int(result.get("quota_limited_count") or 0)
        summary["match_cap_limited_count"] += int(result.get("match_cap_limited_count") or 0)
        results.append({
            "project_id": rule["project_id"],
            "rule_id": rule["id"],
            "matched_count": int(result.get("matched_count") or 0),
            "linked_count": int(result.get("linked_count") or 0),
            "promoted_count": int(result.get("promoted_count") or 0),
            "already_linked_count": int(result.get("already_linked_count") or 0),
            "quota_limited_count": int(result.get("quota_limited_count") or 0),
            "match_cap_limited_count": int(result.get("match_cap_limited_count") or 0),
        })
    summary["projects_evaluated"] = len(project_ids)
    return summary
