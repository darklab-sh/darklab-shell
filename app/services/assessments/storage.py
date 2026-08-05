# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment cycle persistence and immutable profile snapshot creation."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Mapping

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.contracts import (
    ASSESSMENT_MAX_TITLE_LEN,
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.profiles import get_assessment_profile
from services.projects.scope import shared_owner_where
from services.projects.utils import cfg_int, now, raise_quota


DEFAULT_MAX_ASSESSMENTS_PER_OWNER = 100
DEFAULT_MAX_ASSESSMENTS_PER_PROJECT = 25
DEFAULT_MAX_ASSESSMENT_CHECKS_PER_OWNER = 250_000
DEFAULT_MAX_ASSESSMENT_CHECKS_PER_PROJECT = 50_000


def _new_assessment_id() -> str:
    return "asm_" + secrets.token_hex(12)


def _new_check_id() -> str:
    return "ach_" + secrets.token_hex(12)


def _bounded_title(value: object, fallback: str) -> str:
    title = str(value or "").strip() or str(fallback or "").strip()
    if not title:
        raise AssessmentError("assessment title is required")
    if len(title) > ASSESSMENT_MAX_TITLE_LEN:
        raise AssessmentError(
            f"assessment title exceeds {ASSESSMENT_MAX_TITLE_LEN} characters"
        )
    return title


def _target_hash(target_value: str) -> str:
    return hashlib.sha256(target_value.encode("utf-8")).hexdigest()


def _project_row(conn: Any, session_id: str, project_id: str, *, team_id: str) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    query = "".join((
        "SELECT p.id, p.status FROM projects p WHERE ",
        owner_sql,
        " AND p.id = ?",
    ))
    return conn.execute(
        query,
        (*owner_params, project_id),
    ).fetchone()


def _confirmed_project_targets(
    conn: Any,
    session_id: str,
    project_id: str,
    *,
    team_id: str,
) -> list[dict[str, str]]:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    query = "".join((
        "SELECT e.id, e.type, e.canonical_value ",
        "FROM project_links l ",
        "JOIN projects p ON p.id = l.project_id ",
        "JOIN entities e ON e.id = l.entity_id ",
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' ",
        "AND ",
        owner_sql,
        " AND l.review_state = 'confirmed' ",
        "AND COALESCE(e.suppressed, FALSE) = FALSE ",
        "AND e.type IN ('domain', 'ip', 'port', 'url') ",
        "ORDER BY e.type ASC, LOWER(e.canonical_value) ASC, e.id ASC",
    ))
    rows = conn.execute(
        query,
        (project_id, *owner_params),
    ).fetchall()
    return [
        {
            "entity_id": str(row["id"] or ""),
            "type": str(row["type"] or ""),
            "value": str(row["canonical_value"] or ""),
        }
        for row in rows
        if row["id"] and row["type"] and row["canonical_value"]
    ]


def _check_instances(
    profile: Mapping[str, Any],
    targets: list[dict[str, str]],
) -> list[dict[str, str]]:
    instances: list[dict[str, str]] = []
    for check in profile.get("checks", []):
        if not isinstance(check, Mapping):
            continue
        accepted_types = {
            str(value or "").strip().lower()
            for value in check.get("target_types", [])
        }
        for target in targets:
            if target["type"] not in accepted_types:
                continue
            instances.append({
                "category": str(check.get("category") or ""),
                "check_key": str(check.get("key") or ""),
                "target_entity_id": target["entity_id"],
                "target_type": target["type"],
                "target_value": target["value"],
                "target_value_hash": _target_hash(target["value"]),
                "policy_level": str(check.get("policy_level") or "safe"),
                "recommended_action_key": str(
                    check.get("recommended_action") or ""
                ),
            })
    return instances


def _count(conn: Any, sql: str, params: tuple[object, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row["count"] or 0) if row else 0


def _raise_if_quota_would_be_exceeded(
    current: int,
    added: int,
    config_key: str,
    default: int,
    message: str,
) -> None:
    limit = cfg_int(config_key, default)
    if limit > 0 and current + added > limit:
        raise_quota(message)


def _enforce_create_quotas(
    conn: Any,
    session_id: str,
    project_id: str,
    check_count: int,
    *,
    team_id: str,
) -> None:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="a",
    )
    owner_cycle_sql = "".join((
        "SELECT COUNT(*) AS count FROM project_assessments a WHERE ",
        owner_sql,
    ))
    owner_cycle_count = _count(
        conn,
        owner_cycle_sql,
        owner_params,
    )
    project_cycle_count = _count(
        conn,
        "SELECT COUNT(*) AS count FROM project_assessments WHERE project_id = ?",
        (project_id,),
    )
    owner_check_sql = "".join((
        "SELECT COUNT(*) AS count FROM project_assessment_checks c ",
        "JOIN project_assessments a ON a.id = c.assessment_id WHERE ",
        owner_sql,
    ))
    owner_check_count = _count(
        conn,
        owner_check_sql,
        owner_params,
    )
    project_check_count = _count(
        conn,
        "SELECT COUNT(*) AS count FROM project_assessment_checks c "
        "JOIN project_assessments a ON a.id = c.assessment_id "
        "WHERE a.project_id = ?",
        (project_id,),
    )
    _raise_if_quota_would_be_exceeded(
        owner_cycle_count,
        1,
        "max_project_assessments_per_owner",
        DEFAULT_MAX_ASSESSMENTS_PER_OWNER,
        "assessment cycle quota exceeded for this owner",
    )
    _raise_if_quota_would_be_exceeded(
        project_cycle_count,
        1,
        "max_project_assessments_per_project",
        DEFAULT_MAX_ASSESSMENTS_PER_PROJECT,
        "assessment cycle quota exceeded for this project",
    )
    _raise_if_quota_would_be_exceeded(
        owner_check_count,
        check_count,
        "max_project_assessment_checks_per_owner",
        DEFAULT_MAX_ASSESSMENT_CHECKS_PER_OWNER,
        "assessment check quota exceeded for this owner",
    )
    _raise_if_quota_would_be_exceeded(
        project_check_count,
        check_count,
        "max_project_assessment_checks_per_project",
        DEFAULT_MAX_ASSESSMENT_CHECKS_PER_PROJECT,
        "assessment check quota exceeded for this project",
    )


def create_assessment_cycle(
    session_id: str,
    project_id: str,
    profile_key: str,
    *,
    title: str = "",
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Create one active cycle and its target-specific check snapshot."""
    normalized_session_id = str(session_id or "").strip()
    normalized_project_id = str(project_id or "").strip()
    normalized_team_id = str(team_id or "").strip()
    normalized_profile_key = str(profile_key or "").strip().lower()
    if not normalized_session_id:
        raise AssessmentError("assessment session is required")
    if not normalized_project_id:
        raise AssessmentError("assessment project is required")
    selected_profile = get_assessment_profile(normalized_profile_key)
    if not selected_profile or str(selected_profile.get("key") or "") != normalized_profile_key:
        raise AssessmentError("assessment profile was not found")
    assessment_title = _bounded_title(title, str(selected_profile.get("label") or ""))
    created_at = now()
    assessment_id = _new_assessment_id()
    dialect = dialect_for_backend(get_db_backend())

    with get_db_connect()() as conn:
        project = _project_row(
            conn,
            normalized_session_id,
            normalized_project_id,
            team_id=normalized_team_id,
        )
        if not project:
            raise AssessmentNotFound("project was not found in this scope")
        if str(project["status"] or "") == "archived":
            raise AssessmentConflict("archived projects are read-only")
        active = conn.execute(
            "SELECT 1 FROM project_assessments WHERE project_id = ? AND status = 'active'",
            (normalized_project_id,),
        ).fetchone()
        if active:
            raise AssessmentConflict("project already has an active assessment")
        targets = _confirmed_project_targets(
            conn,
            normalized_session_id,
            normalized_project_id,
            team_id=normalized_team_id,
        )
        checks = _check_instances(selected_profile, targets)
        if not checks:
            raise AssessmentError(
                "assessment profile has no checks for the project's confirmed targets"
            )
        _enforce_create_quotas(
            conn,
            normalized_session_id,
            normalized_project_id,
            len(checks),
            team_id=normalized_team_id,
        )
        result = conn.execute(
            "INSERT INTO project_assessments "
            "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
            "profile_snapshot, status, started_at, completed_at, archived_at, "
            "created_by_session_id, created_by_member_id, updated_by_session_id, "
            "updated_by_member_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            (
                assessment_id,
                normalized_session_id,
                normalized_team_id,
                normalized_project_id,
                assessment_title,
                normalized_profile_key,
                str(selected_profile.get("version") or ""),
                dialect.json_param(selected_profile),
                created_at,
                normalized_session_id,
                str(actor_member_id or "").strip(),
                normalized_session_id,
                str(actor_member_id or "").strip(),
                created_at,
                created_at,
            ),
        )
        if not result.rowcount:
            raise AssessmentConflict("project already has an active assessment")
        for check in checks:
            conn.execute(
                "INSERT INTO project_assessment_checks "
                "(id, assessment_id, category, check_key, target_entity_id, target_type, "
                "target_value, target_value_hash, applicability, policy_level, state, "
                "state_source, state_reason, recommended_action_key, first_evidence_at, "
                "last_evidence_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'applicable', ?, 'not_started', "
                "'derived', '', ?, NULL, NULL, ?, ?)",
                (
                    _new_check_id(),
                    assessment_id,
                    check["category"],
                    check["check_key"],
                    check["target_entity_id"],
                    check["target_type"],
                    check["target_value"],
                    check["target_value_hash"],
                    check["policy_level"],
                    check["recommended_action_key"],
                    created_at,
                    created_at,
                ),
            )
        conn.commit()

    from services.assessments.read_model import get_assessment_read_model  # noqa: PLC0415

    created = get_assessment_read_model(
        normalized_session_id,
        normalized_project_id,
        assessment_id,
        team_id=normalized_team_id,
    )
    if created is None:
        raise AssessmentNotFound("created assessment could not be loaded")
    return created
