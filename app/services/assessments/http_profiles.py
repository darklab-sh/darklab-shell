# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scoped persistence for reusable Project HTTP assessment profiles."""

from __future__ import annotations

import secrets
from typing import Any, Mapping

from config import resolve_effective_cfg
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.http_profile_contracts import (
    HttpProfileConflict,
    HttpProfileError,
    HttpProfileNotFound,
)
from services.assessments.http_profile_scope import project_hosts as _project_hosts
from services.assessments.http_profile_secret_references import (
    available_secret_names as _available_secret_names,
    canonicalize_secret_references as _canonicalize_secret_references,
    referenced_secret_names as _referenced_secret_names,
    secret_reference_lookup as _secret_reference_lookup,
)
from services.assessments.http_profile_validation import (
    HTTP_PROFILE_INPUT_FIELDS,
    normalize_http_profile_payload,
)
from services.commands.registry import load_all_workflows
from services.projects.scope import shared_owner_where
from services.projects.utils import cfg_int, now, raise_quota
from services.teams.scope import owner_context_for_scope
from services.workspace.files import WorkspaceError, owner_workspace_path_info


DEFAULT_MAX_HTTP_PROFILES_PER_PROJECT = 50
_SECRET_REFERENCE_LABELS = {
    "bearer_token": "Bearer token Secret",
    "cookie": "Cookie Secret",
    "basic_username": "Basic username Secret",
    "basic_password": "Basic password Secret",
    "proxy_authorization": "Proxy authorization Secret",
    "client_key_passphrase": "Client-key passphrase Secret",
}
_SELECT_COLUMNS = (
    "h.id, h.session_id, h.team_id, h.project_id, h.name, h.name_key, h.role_key, "
    "h.base_url, h.scope_roots_json, h.allowed_hosts_json, h.headers_json, "
    "h.secret_refs_json, h.file_refs_json, h.proxy_url, h.login_workflow_id, "
    "h.token_capture_rules_json, h.include_paths_json, h.exclude_paths_json, "
    "h.rate_limit_per_second, h.concurrency, h.enabled, h.revision, h.created_at, h.updated_at"
)


def _new_profile_id() -> str:
    return "htp_" + secrets.token_hex(12)


def _owner_where(session_id: str, team_id: str, *, alias: str = "h") -> tuple[str, tuple[str, ...]]:
    return shared_owner_where(session_id, team_id=team_id, table_alias=alias)


def _decode_list(value: Any) -> list[Any]:
    return dialect_for_backend(get_db_backend()).decode_json_list(value)


def _decode_dict(value: Any) -> dict[str, Any]:
    return dialect_for_backend(get_db_backend()).decode_json_dict(value)


def _json(value: Any) -> Any:
    return dialect_for_backend(get_db_backend()).json_param(value)


def _internal_profile(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"] or ""),
        "session_id": str(row["session_id"] or ""),
        "team_id": str(row["team_id"] or ""),
        "project_id": str(row["project_id"] or ""),
        "name": str(row["name"] or ""),
        "name_key": str(row["name_key"] or ""),
        "role": str(row["role_key"] or "anonymous"),
        "base_url": str(row["base_url"] or ""),
        "scope_roots": [str(value) for value in _decode_list(row["scope_roots_json"])],
        "allowed_hosts": [str(value) for value in _decode_list(row["allowed_hosts_json"])],
        "headers": [dict(value) for value in _decode_list(row["headers_json"]) if isinstance(value, Mapping)],
        "secret_refs": {str(key): str(value) for key, value in _decode_dict(row["secret_refs_json"]).items()},
        "file_refs": {str(key): str(value) for key, value in _decode_dict(row["file_refs_json"]).items()},
        "proxy_url": str(row["proxy_url"] or ""),
        "login_workflow_id": str(row["login_workflow_id"] or ""),
        "token_capture_rules": [
            dict(value)
            for value in _decode_list(row["token_capture_rules_json"])
            if isinstance(value, Mapping)
        ],
        "include_paths": [str(value) for value in _decode_list(row["include_paths_json"])],
        "exclude_paths": [str(value) for value in _decode_list(row["exclude_paths_json"])],
        "rate_limit_per_second": int(row["rate_limit_per_second"] or 0),
        "concurrency": int(row["concurrency"] or 0),
        "enabled": bool(row["enabled"]),
        "revision": int(row["revision"] or 1),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _profile_row(
    conn: Any,
    session_id: str,
    project_id: str,
    profile_id: str,
    *,
    team_id: str,
) -> Any:
    owner_sql, owner_params = _owner_where(session_id, team_id)
    sql = "".join((
        "SELECT ",
        _SELECT_COLUMNS,
        " FROM project_http_profiles h WHERE ",
        owner_sql,
        " AND h.project_id = ? AND h.id = ?",
    ))
    return conn.execute(sql, (*owner_params, project_id, profile_id)).fetchone()


def _workflow_ids(conn: Any, session_id: str, team_id: str) -> set[str]:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="w"
    )
    # The owner clause comes from shared_owner_where; all values stay bound.
    sql = "SELECT w.id FROM user_workflows w WHERE " + owner_sql  # nosec
    rows = conn.execute(sql, owner_params).fetchall()
    ids = {str(row["id"] or "") for row in rows}
    ids.update(
        str(item.get("id") or "")
        for item in load_all_workflows(resolve_effective_cfg())
        if isinstance(item, Mapping)
    )
    return ids


def _validate_references(
    conn: Any,
    session_id: str,
    team_id: str,
    actor_member_id: str,
    profile: dict[str, Any],
) -> None:
    owner_id = team_id or session_id
    references = _secret_reference_lookup(conn, owner_id)
    missing_fields = {
        _SECRET_REFERENCE_LABELS.get(str(slot), "Protected Secret")
        for slot, value in profile.get("secret_refs", {}).items()
        if str(value) and str(value) not in references
    }
    if any(
        str(header.get("secret_name") or "") not in references
        for header in profile.get("headers", [])
        if isinstance(header, Mapping) and str(header.get("secret_name") or "")
    ):
        missing_fields.add("Custom header Secrets")
    if missing_fields:
        raise HttpProfileError(
            "HTTP profile Secret references aren't available in this Project scope: "
            + ", ".join(sorted(missing_fields))
        )
    _canonicalize_secret_references(profile, references)
    workflow_id = str(profile.get("login_workflow_id") or "")
    if workflow_id and workflow_id not in _workflow_ids(conn, session_id, team_id):
        raise HttpProfileError("HTTP profile login workflow was not found in this owner scope")
    owner = owner_context_for_scope(
        session_id,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    for path in profile.get("file_refs", {}).values():
        try:
            info = owner_workspace_path_info(owner, str(path))
        except WorkspaceError as exc:
            raise HttpProfileError("HTTP profile references an unavailable Files path") from exc
        if str(info.get("kind") or "") != "file":
            raise HttpProfileError("HTTP profile client credential references must be Files")


def _validate_project_scope(
    conn: Any,
    session_id: str,
    project_id: str,
    profile: Mapping[str, Any],
    *,
    team_id: str,
) -> None:
    project_hosts = _project_hosts(
        conn,
        session_id,
        project_id,
        team_id=team_id,
        require_active=True,
    )
    if not project_hosts:
        raise HttpProfileError("HTTP profile requires a confirmed Project web target")
    outside = sorted(set(profile.get("allowed_hosts", [])) - project_hosts)
    if outside:
        raise HttpProfileError("HTTP profile allowed hosts must be confirmed Project targets")


def _name_in_use(
    conn: Any,
    project_id: str,
    name_key: str,
    *,
    exclude_profile_id: str = "",
) -> bool:
    row = conn.execute(
        "SELECT id FROM project_http_profiles WHERE project_id = ? AND name_key = ?",
        (project_id, name_key),
    ).fetchone()
    return bool(row and str(row["id"] or "") != exclude_profile_id)


def _reference_counts(profile: Mapping[str, Any]) -> dict[str, int]:
    return {
        "secret_refs": len(_referenced_secret_names(profile)),
        "file_refs": len(profile.get("file_refs", {})),
        "headers": len(profile.get("headers", [])),
        "scope_roots": len(profile.get("scope_roots", [])),
        "allowed_hosts": len(profile.get("allowed_hosts", [])),
        "capture_rules": len(profile.get("token_capture_rules", [])),
    }


def http_profile_audit_summary(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return ids and counts safe for logs and audit details."""
    counts = profile.get("reference_counts")
    if not isinstance(counts, Mapping):
        counts = profile.get("counts")
    if not isinstance(counts, Mapping):
        counts = _reference_counts(profile)
    return {
        "project_id": str(profile.get("project_id") or ""),
        "profile_id": str(profile.get("id") or ""),
        "role": str(profile.get("role") or ""),
        "enabled": bool(profile.get("enabled")),
        "counts": {str(key): int(value) for key, value in counts.items()},
    }


def _serialize_profile(
    conn: Any,
    profile: Mapping[str, Any],
    *,
    include_references: bool,
) -> dict[str, Any]:
    headers = profile.get("headers", [])
    secret_refs = profile.get("secret_refs", {})
    file_refs = profile.get("file_refs", {})
    item = {
        "id": str(profile.get("id") or ""),
        "team_id": str(profile.get("team_id") or ""),
        "project_id": str(profile.get("project_id") or ""),
        "name": str(profile.get("name") or ""),
        "role": str(profile.get("role") or ""),
        "base_url": str(profile.get("base_url") or ""),
        "scope_roots": list(profile.get("scope_roots", [])),
        "allowed_hosts": list(profile.get("allowed_hosts", [])),
        "header_names": [str(header.get("name") or "") for header in headers],
        "credential_use": sorted(
            {str(key) for key, value in secret_refs.items() if str(value)}
            | ({"headers"} if headers else set())
            | ({"client_certificate"} if file_refs else set())
        ),
        "proxy_configured": bool(profile.get("proxy_url")),
        "login_workflow_id": str(profile.get("login_workflow_id") or ""),
        "capture_rule_count": len(profile.get("token_capture_rules", [])),
        "include_paths": list(profile.get("include_paths", [])),
        "exclude_paths": list(profile.get("exclude_paths", [])),
        "rate_limit_per_second": int(profile.get("rate_limit_per_second") or 0),
        "concurrency": int(profile.get("concurrency") or 0),
        "enabled": bool(profile.get("enabled")),
        "revision": int(profile.get("revision") or 1),
        "created_at": str(profile.get("created_at") or ""),
        "updated_at": str(profile.get("updated_at") or ""),
        "protected_references_visible": include_references,
        "reference_counts": _reference_counts(profile),
    }
    if include_references:
        available_secrets = _available_secret_names(
            conn, str(profile.get("team_id") or profile.get("session_id") or "")
        )
        item["headers"] = [
            {
                "name": str(header.get("name") or ""),
                "secret_name": str(header.get("secret_name") or ""),
                "available": str(header.get("secret_name") or "") in available_secrets,
            }
            for header in headers
        ]
        item["secret_refs"] = {
            str(key): {"name": str(value), "available": str(value) in available_secrets}
            for key, value in secret_refs.items()
        }
        item["file_refs"] = dict(file_refs)
        item["proxy_url"] = str(profile.get("proxy_url") or "")
        item["token_capture_rules"] = [dict(value) for value in profile.get("token_capture_rules", [])]
    return item


def list_http_profiles(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    include_references: bool = False,
) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        try:
            _project_hosts(conn, session_id, project_id, team_id=team_id)
        except HttpProfileNotFound:
            return None
        owner_sql, owner_params = _owner_where(session_id, team_id)
        sql = "".join((
            "SELECT ",
            _SELECT_COLUMNS,
            " FROM project_http_profiles h WHERE ",
            owner_sql,
            " AND h.project_id = ? ORDER BY LOWER(h.name) ASC, h.id ASC",
        ))
        rows = conn.execute(sql, (*owner_params, project_id)).fetchall()
        profiles = [
            _serialize_profile(conn, _internal_profile(row), include_references=include_references)
            for row in rows
        ]
    return {"profiles": profiles, "total": len(profiles)}


def get_http_profile(
    session_id: str,
    project_id: str,
    profile_id: str,
    *,
    team_id: str = "",
    include_references: bool = False,
) -> dict[str, Any] | None:
    with get_db_connect()() as conn:
        row = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
        if not row:
            return None
        return _serialize_profile(
            conn, _internal_profile(row), include_references=include_references
        )


def _project_profile_count(conn: Any, project_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM project_http_profiles WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row["count"] or 0) if row else 0


def create_http_profile_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    data: object,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    profile = normalize_http_profile_payload(data)
    _validate_project_scope(conn, session_id, project_id, profile, team_id=team_id)
    _validate_references(conn, session_id, team_id, actor_member_id, profile)
    if _name_in_use(conn, project_id, profile["name_key"]):
        raise HttpProfileConflict("HTTP profile name is already in use for this Project")
    limit = cfg_int(
        "max_project_http_profiles_per_project",
        DEFAULT_MAX_HTTP_PROFILES_PER_PROJECT,
    )
    current_count = _project_profile_count(conn, project_id)
    if limit > 0 and current_count >= limit:
        raise_quota(
            "HTTP profile quota exceeded for this Project",
            quota_kind="http_profile_project",
            owner_kind="team" if team_id else "personal",
            project_id=project_id,
            limit=limit,
            current_count=current_count,
            requested_count=1,
        )
    profile_id = _new_profile_id()
    created_at = now()
    conn.execute(
        "INSERT INTO project_http_profiles ("
        "id, session_id, team_id, project_id, name, name_key, role_key, base_url, "
        "scope_roots_json, allowed_hosts_json, headers_json, secret_refs_json, file_refs_json, "
        "proxy_url, login_workflow_id, token_capture_rules_json, include_paths_json, "
        "exclude_paths_json, rate_limit_per_second, concurrency, enabled, revision, "
        "created_by_session_id, created_by_member_id, updated_by_session_id, "
        "updated_by_member_id, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
        (
            profile_id,
            session_id,
            team_id,
            project_id,
            profile["name"],
            profile["name_key"],
            profile["role"],
            profile["base_url"],
            _json(profile["scope_roots"]),
            _json(profile["allowed_hosts"]),
            _json(profile["headers"]),
            _json(profile["secret_refs"]),
            _json(profile["file_refs"]),
            profile["proxy_url"],
            profile["login_workflow_id"],
            _json(profile["token_capture_rules"]),
            _json(profile["include_paths"]),
            _json(profile["exclude_paths"]),
            profile["rate_limit_per_second"],
            profile["concurrency"],
            profile["enabled"],
            session_id,
            actor_member_id,
            session_id,
            actor_member_id,
            created_at,
            created_at,
        ),
    )
    row = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
    return _serialize_profile(conn, _internal_profile(row), include_references=True)


def _editable_payload(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {field: profile.get(field) for field in HTTP_PROFILE_INPUT_FIELDS}


def update_http_profile_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    profile_id: str,
    data: object,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise HttpProfileError("HTTP profile payload must be an object")
    if set(data) - (HTTP_PROFILE_INPUT_FIELDS | {"revision"}):
        raise HttpProfileError("HTTP profile payload contains unsupported fields")
    if "revision" not in data:
        raise HttpProfileError("HTTP profile revision is required")
    row = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
    if not row:
        raise HttpProfileNotFound("HTTP profile was not found in this Project scope")
    current = _internal_profile(row)
    try:
        expected_revision = int(str(data.get("revision")))
    except (TypeError, ValueError) as exc:
        raise HttpProfileError("HTTP profile revision must be an integer") from exc
    if expected_revision != current["revision"]:
        raise HttpProfileConflict("HTTP profile was changed by another request")
    merged = _editable_payload(current)
    merged.update({key: value for key, value in data.items() if key != "revision"})
    profile = normalize_http_profile_payload(merged)
    _validate_project_scope(conn, session_id, project_id, profile, team_id=team_id)
    _validate_references(conn, session_id, team_id, actor_member_id, profile)
    if _name_in_use(conn, project_id, profile["name_key"], exclude_profile_id=profile_id):
        raise HttpProfileConflict("HTTP profile name is already in use for this Project")
    updated_at = now()
    result = conn.execute(
        "UPDATE project_http_profiles SET name = ?, name_key = ?, role_key = ?, base_url = ?, "
        "scope_roots_json = ?, allowed_hosts_json = ?, headers_json = ?, secret_refs_json = ?, "
        "file_refs_json = ?, proxy_url = ?, login_workflow_id = ?, token_capture_rules_json = ?, "
        "include_paths_json = ?, exclude_paths_json = ?, rate_limit_per_second = ?, concurrency = ?, "
        "enabled = ?, revision = revision + 1, updated_by_session_id = ?, "
        "updated_by_member_id = ?, updated_at = ? WHERE id = ? AND revision = ?",
        (
            profile["name"],
            profile["name_key"],
            profile["role"],
            profile["base_url"],
            _json(profile["scope_roots"]),
            _json(profile["allowed_hosts"]),
            _json(profile["headers"]),
            _json(profile["secret_refs"]),
            _json(profile["file_refs"]),
            profile["proxy_url"],
            profile["login_workflow_id"],
            _json(profile["token_capture_rules"]),
            _json(profile["include_paths"]),
            _json(profile["exclude_paths"]),
            profile["rate_limit_per_second"],
            profile["concurrency"],
            profile["enabled"],
            session_id,
            actor_member_id,
            updated_at,
            profile_id,
            expected_revision,
        ),
    )
    if result.rowcount != 1:
        raise HttpProfileConflict("HTTP profile was changed by another request")
    updated = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
    return _serialize_profile(conn, _internal_profile(updated), include_references=True)


def delete_http_profile_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    profile_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    row = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
    if not row:
        raise HttpProfileNotFound("HTTP profile was not found in this Project scope")
    _project_hosts(
        conn,
        session_id,
        project_id,
        team_id=team_id,
        require_active=True,
    )
    profile = _internal_profile(row)
    conn.execute("DELETE FROM project_http_profiles WHERE id = ?", (profile_id,))
    return http_profile_audit_summary(profile)
