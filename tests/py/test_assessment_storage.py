# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment cycle storage and shared read-model coverage."""

from __future__ import annotations

from copy import deepcopy
import uuid

import pytest

from conftest import build_test_config
from core.database import db_connect, db_init
from services.assessments.contracts import (
    AssessmentConflict,
    AssessmentError,
    AssessmentNotFound,
)
from services.assessments.read_model import (
    get_assessment_read_model,
    list_assessment_cycles,
)
from services.assessments.storage import create_assessment_cycle
from services.projects.crud import create_project, delete_project, update_project
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.targets import add_project_target


@pytest.fixture(scope="module", autouse=True)
def _initialize_assessment_schema():
    db_init()


def _profile() -> dict[str, object]:
    return {
        "key": "network",
        "version": "1.0",
        "label": "Network assessment",
        "purpose": "Assess the approved network targets.",
        "target_types": ["domain", "ip", "url"],
        "checks": [
            {
                "key": "service_discovery",
                "version": "1.0",
                "category": "discovery",
                "label": "Service discovery",
                "purpose": "Find reachable services.",
                "target_types": ["domain", "ip"],
                "evidence_rules": [],
                "policy_level": "standard",
                "recommended_action": "command:nmap",
                "completion_guidance": "Run a bounded service scan.",
            },
            {
                "key": "dns_inventory",
                "version": "1.0",
                "category": "discovery",
                "label": "DNS inventory",
                "purpose": "Review DNS records.",
                "target_types": ["domain"],
                "evidence_rules": [],
                "policy_level": "safe",
                "recommended_action": "command:dnsrecon",
                "completion_guidance": "Collect the approved DNS records.",
            },
            {
                "key": "content_discovery",
                "version": "1.0",
                "category": "enumeration",
                "label": "Content discovery",
                "purpose": "Review reachable paths.",
                "target_types": ["url"],
                "evidence_rules": [],
                "policy_level": "standard",
                "recommended_action": "command:katana",
                "completion_guidance": "Run a bounded crawl.",
            },
        ],
    }


@pytest.fixture
def project_factory(monkeypatch: pytest.MonkeyPatch):
    created: list[tuple[str, str, str]] = []
    profile = _profile()
    monkeypatch.setattr(
        "services.assessments.storage.get_assessment_profile",
        lambda key: deepcopy(profile) if key == "network" else None,
    )

    def factory(*, session_id: str = "", team_id: str = "") -> tuple[str, dict[str, object]]:
        session = session_id or "assessment-storage-" + uuid.uuid4().hex
        project = create_project(session, {"name": "Assessment " + uuid.uuid4().hex[:8]}, team_id=team_id)
        assert project is not None
        created.append((session, str(project["id"]), team_id))
        return session, project

    yield factory

    for session_id, project_id, team_id in created:
        delete_project(session_id, project_id, team_id=team_id)


def _add_target(
    session_id: str,
    project_id: str,
    target_type: str,
    value: str,
    *,
    team_id: str = "",
    review_state: str = "confirmed",
) -> dict[str, object]:
    target = add_project_target(
        session_id,
        project_id,
        {
            "type": target_type,
            "value": value,
            "review_state": review_state,
        },
        team_id=team_id,
    )
    assert target is not None
    return target


def test_create_cycle_snapshots_confirmed_targets_and_profile(project_factory):
    session_id, project = project_factory()
    project_id = str(project["id"])
    confirmed = _add_target(session_id, project_id, "domain", "example.com")
    _add_target(
        session_id,
        project_id,
        "ip",
        "192.0.2.10",
        review_state="pending",
    )
    _add_target(
        session_id,
        project_id,
        "url",
        "https://example.com/private",
        review_state="dismissed",
    )

    created = create_assessment_cycle(
        session_id,
        project_id,
        "network",
        actor_member_id="member-1",
    )

    assessment = created["assessment"]
    assert assessment["title"] == "Network assessment"
    assert assessment["profile_key"] == "network"
    assert assessment["profile_version"] == "1.0"
    assert assessment["profile_snapshot"] == _profile()
    assert assessment["owner_kind"] == "personal"
    assert "session_id" not in assessment
    assert assessment["created_by_member_id"] == "member-1"
    assert created["rollup"] == {
        "total_checks": 2,
        "applicable_checks": 2,
        "covered_checks": 0,
        "checks_awaiting_review": 0,
        "untested_checks": 2,
        "excluded_checks": 0,
        "unavailable_evidence_checks": 0,
    }
    assert created["checks"]["total"] == 2
    assert {item["check_key"] for item in created["checks"]["checks"]} == {
        "service_discovery",
        "dns_inventory",
    }
    assert {
        item["target_entity_id"] for item in created["checks"]["checks"]
    } == {confirmed["id"]}


def test_create_cycle_rejects_missing_targets_archived_projects_and_second_active_cycle(
    project_factory,
):
    empty_session, empty_project = project_factory()
    with pytest.raises(AssessmentError, match="no checks"):
        create_assessment_cycle(empty_session, str(empty_project["id"]), "network")

    archived_session, archived_project = project_factory()
    _add_target(archived_session, str(archived_project["id"]), "domain", "archived.example")
    update_project(
        archived_session,
        str(archived_project["id"]),
        {"status": "archived"},
    )
    with pytest.raises(AssessmentConflict, match="read-only"):
        create_assessment_cycle(
            archived_session,
            str(archived_project["id"]),
            "network",
        )

    active_session, active_project = project_factory()
    active_project_id = str(active_project["id"])
    _add_target(active_session, active_project_id, "domain", "active.example")
    create_assessment_cycle(active_session, active_project_id, "network")
    with pytest.raises(AssessmentConflict, match="already has an active"):
        create_assessment_cycle(active_session, active_project_id, "network")


def test_create_cycle_rejects_unknown_profiles_and_out_of_scope_projects(project_factory):
    session_id, project = project_factory()
    project_id = str(project["id"])
    _add_target(session_id, project_id, "domain", "scope.example")

    with pytest.raises(AssessmentError, match="profile was not found"):
        create_assessment_cycle(session_id, project_id, "unknown")
    with pytest.raises(AssessmentNotFound, match="not found in this scope"):
        create_assessment_cycle("another-session", project_id, "network")


def test_assessment_reads_are_isolated_by_personal_and_team_scope(project_factory):
    personal_session, personal_project = project_factory()
    personal_project_id = str(personal_project["id"])
    _add_target(personal_session, personal_project_id, "domain", "personal.example")
    personal = create_assessment_cycle(
        personal_session,
        personal_project_id,
        "network",
    )["assessment"]

    assert get_assessment_read_model(
        "another-session",
        personal_project_id,
        personal["id"],
    ) is None
    assert list_assessment_cycles("another-session", personal_project_id) is None

    team_id = "team-assessment-" + uuid.uuid4().hex
    creator, team_project = project_factory(team_id=team_id)
    team_project_id = str(team_project["id"])
    _add_target(
        creator,
        team_project_id,
        "domain",
        "team.example",
        team_id=team_id,
    )
    team_cycle = create_assessment_cycle(
        creator,
        team_project_id,
        "network",
        team_id=team_id,
    )["assessment"]

    visible = get_assessment_read_model(
        "another-team-member",
        team_project_id,
        team_cycle["id"],
        team_id=team_id,
    )
    assert visible is not None
    assert visible["assessment"]["owner_kind"] == "team"
    assert get_assessment_read_model(
        creator,
        team_project_id,
        team_cycle["id"],
        team_id="other-team",
    ) is None


def test_create_cycle_enforces_cycle_and_check_quotas_in_the_insert_transaction(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "config.CFG",
        build_test_config({
            "max_project_assessments_per_owner": 1,
            "max_project_assessment_checks_per_project": 1,
        }),
    )
    check_session, check_project = project_factory()
    check_project_id = str(check_project["id"])
    _add_target(check_session, check_project_id, "domain", "check-quota.example")
    with pytest.raises(ProjectWorkspaceQuotaExceeded, match="check quota"):
        create_assessment_cycle(check_session, check_project_id, "network")
    with db_connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessments WHERE project_id = ?",
            (check_project_id,),
        ).fetchone()
    assert int(row["count"] or 0) == 0

    monkeypatch.setattr(
        "config.CFG",
        build_test_config({
            "max_project_assessments_per_owner": 1,
            "max_project_assessment_checks_per_project": 10,
        }),
    )
    owner_session = "assessment-owner-quota-" + uuid.uuid4().hex
    _, first_project = project_factory(session_id=owner_session)
    _, second_project = project_factory(session_id=owner_session)
    _add_target(owner_session, str(first_project["id"]), "domain", "one.example")
    _add_target(owner_session, str(second_project["id"]), "domain", "two.example")
    create_assessment_cycle(owner_session, str(first_project["id"]), "network")
    with pytest.raises(ProjectWorkspaceQuotaExceeded, match="cycle quota"):
        create_assessment_cycle(owner_session, str(second_project["id"]), "network")


def test_read_model_rollups_filters_and_pages_checks(project_factory):
    session_id, project = project_factory()
    project_id = str(project["id"])
    _add_target(session_id, project_id, "domain", "rollup.example")
    _add_target(session_id, project_id, "url", "https://rollup.example/app")
    created = create_assessment_cycle(session_id, project_id, "network")
    assessment_id = created["assessment"]["id"]
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, check_key FROM project_assessment_checks "
            "WHERE assessment_id = ? ORDER BY check_key",
            (assessment_id,),
        ).fetchall()
        ids = {str(row["check_key"]): str(row["id"]) for row in rows}
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'covered' "
            "WHERE id = ?",
            (ids["dns_inventory"],),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'needs_review' "
            "WHERE id = ?",
            (ids["service_discovery"],),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'skipped', "
            "state_source = 'manual', state_reason = 'Out of scope' WHERE id = ?",
            (ids["content_discovery"],),
        )
        conn.execute(
            "INSERT INTO project_assessment_evidence "
            "(id, assessment_id, check_id, evidence_type, evidence_id, source_state, "
            "observed_at, unavailable_at, unavailable_reason, match_rule_key, "
            "match_rule_version, linked_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'run', 'deleted-run', 'unavailable', ?, ?, ?, "
            "'completed_dns_inventory', '1.0', 'derived', ?, ?)",
            (
                "aev_" + uuid.uuid4().hex,
                assessment_id,
                ids["dns_inventory"],
                "2026-08-04 12:00:00",
                "2026-08-04 12:30:00",
                "source run was deleted",
                "2026-08-04 12:00:00",
                "2026-08-04 12:30:00",
            ),
        )
        conn.commit()

    read = get_assessment_read_model(
        session_id,
        project_id,
        assessment_id,
        check_limit=2,
    )
    assert read is not None
    assert read["rollup"] == {
        "total_checks": 3,
        "applicable_checks": 3,
        "covered_checks": 1,
        "checks_awaiting_review": 1,
        "untested_checks": 0,
        "excluded_checks": 1,
        "unavailable_evidence_checks": 1,
    }
    assert read["checks"]["total"] == 3
    assert read["checks"]["limit"] == 2
    assert read["checks"]["has_more"] is True
    assert {item["category"] for item in read["category_rollups"]} == {
        "discovery",
        "enumeration",
    }

    unavailable = get_assessment_read_model(
        session_id,
        project_id,
        assessment_id,
        check_filters={"evidence_state": "unavailable"},
    )
    assert unavailable is not None
    assert [item["check_key"] for item in unavailable["checks"]["checks"]] == [
        "dns_inventory"
    ]
    covered = get_assessment_read_model(
        session_id,
        project_id,
        assessment_id,
        check_filters={"state": "covered"},
    )
    assert covered is not None
    assert covered["checks"]["total"] == 1


def test_cycle_list_is_bounded_and_rejects_unsupported_filters(project_factory):
    session_id, project = project_factory()
    project_id = str(project["id"])
    _add_target(session_id, project_id, "domain", "list.example")
    cycle = create_assessment_cycle(session_id, project_id, "network")["assessment"]

    page = list_assessment_cycles(session_id, project_id, limit=1)
    assert page is not None
    assert page["total"] == 1
    assert page["limit"] == 1
    assert page["assessments"][0]["id"] == cycle["id"]
    assert page["assessments"][0]["rollup"]["total_checks"] == 2
    with pytest.raises(AssessmentError, match="status filter"):
        list_assessment_cycles(session_id, project_id, status="reopened")
    with pytest.raises(AssessmentError, match="evidence filter"):
        get_assessment_read_model(
            session_id,
            project_id,
            cycle["id"],
            check_filters={"evidence_state": "stale"},
        )
