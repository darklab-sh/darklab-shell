# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser and API v1 contracts for bounded assessment-batch previews."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from conftest import reusable_test_app
from core.database_access import get_db_connect
from services.assessments.base_action_catalog import ACTIONS
from services.assessments.probe_runtime import ProbePlanningRuntime
from services.assessments.storage import create_assessment_cycle
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
from services.projects.crud import create_project, delete_project
from services.projects.targets import add_project_target


def _register_token(token: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) "
            "VALUES (?, ?, ?)",
            (token, now, ""),
        )
        conn.commit()


def _runtime() -> ProbePlanningRuntime:
    return ProbePlanningRuntime(
        available_features=frozenset(
            {*ACTIONS, "reviewed_nse_profiles", "managed_nuclei_templates"}
        ),
        intrusive_actions_enabled=True,
        template_snapshot=NucleiTemplateCacheSnapshot(
            "ready", "v10.4.7", "sha256:" + "1" * 64, 100
        ),
    )


@pytest.fixture
def client():
    return reusable_test_app(__name__).test_client()


@pytest.fixture
def route_cycle(monkeypatch: pytest.MonkeyPatch):
    session_id = "tok_batch_routes_" + uuid.uuid4().hex
    _register_token(session_id)
    project = create_project(session_id, {"name": "Batch route Project"})
    assert project is not None
    project_id = str(project["id"])
    target = add_project_target(
        session_id,
        project_id,
        {
            "type": "domain",
            "value": "batch-route.example.test",
            "source": "user",
            "review_state": "confirmed",
        },
    )
    assert target is not None
    cycle = create_assessment_cycle(session_id, project_id, "network")
    assessment_id = str(cycle["assessment"]["id"])
    monkeypatch.setattr(
        "services.assessments.batch.preview_draft.probe_planning_runtime",
        _runtime,
    )
    yield session_id, project_id, assessment_id, str(target["id"])
    with get_db_connect()() as conn:
        conn.execute(
            "DELETE FROM assessment_batch_previews WHERE assessment_id = ?",
            (assessment_id,),
        )
        conn.commit()
    delete_project(session_id, project_id)


def _browser_headers(session_id: str, team_id: str = "") -> dict[str, str]:
    headers = {"X-Session-ID": session_id}
    if team_id:
        headers["X-Team-ID"] = team_id
    return headers


def _api_headers(session_id: str, team_id: str = "") -> dict[str, str]:
    headers = {"Authorization": f"Bearer {session_id}"}
    if team_id:
        headers["X-Team-ID"] = team_id
    return headers


def _preview_counts() -> tuple[int, int, int]:
    with get_db_connect()() as conn:
        return tuple(
            int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            for table in ("workflow_executions", "runs", "audit_events")
        )


def test_browser_preview_create_read_and_page_are_owner_scoped_and_side_effect_free(
    client,
    route_cycle,
):
    session_id, project_id, assessment_id, target_id = route_cycle
    route = f"/projects/{project_id}/assessments/{assessment_id}/batch-previews"
    before = _preview_counts()

    created = client.post(route, headers=_browser_headers(session_id), json={})

    assert created.status_code == 201
    preview = created.get_json()["preview"]
    assert preview["project_id"] == project_id
    assert preview["assessment_id"] == assessment_id
    assert preview["summary"]["selected_target_entity_ids"] == [target_id]
    assert preview["selected_item_count"] == 2
    assert preview["candidate_item_count"] == 3
    assert _preview_counts() == before

    preview_id = preview["preview_id"]
    summary = client.get(
        f"/assessment-batch-previews/{preview_id}",
        headers=_browser_headers(session_id),
    )
    first = client.get(
        f"/assessment-batch-previews/{preview_id}/items",
        query_string={"limit": 1},
        headers=_browser_headers(session_id),
    )
    second = client.get(
        f"/assessment-batch-previews/{preview_id}/items",
        query_string={"cursor": first.get_json()["next_cursor"], "limit": 100},
        headers=_browser_headers(session_id),
    )
    assert summary.status_code == 200
    assert summary.get_json()["preview"] == preview
    assert len(first.get_json()["items"]) == 1
    assert first.get_json()["next_cursor"] == 1
    assert [item["item_index"] for item in second.get_json()["items"]] == [1, 2]
    assert second.get_json()["next_cursor"] is None

    foreign = "tok_batch_routes_foreign_" + uuid.uuid4().hex
    _register_token(foreign)
    hidden = client.get(
        f"/assessment-batch-previews/{preview_id}",
        headers=_browser_headers(foreign),
    )
    assert hidden.status_code == 404
    assert hidden.get_json()["code"] == "preview_not_found"


def test_api_preview_uses_the_same_digest_pages_and_stable_errors(client, route_cycle):
    session_id, project_id, assessment_id, _target_id = route_cycle
    route = f"/api/v1/projects/{project_id}/assessments/{assessment_id}/batch-previews"
    headers = _api_headers(session_id)

    created = client.post(
        route,
        headers=headers,
        json={"include_standard": True, "item_limit": 3, "max_parallel": 3},
    )

    assert created.status_code == 201
    preview = created.get_json()["preview"]
    assert preview["selected_item_count"] == 3
    assert preview["summary"]["requires_standard_confirmation"] is True
    assert preview["concurrency"]["batch"] == 3
    preview_id = preview["preview_id"]
    summary = client.get(
        f"/api/v1/assessment-batch-previews/{preview_id}", headers=headers
    )
    page = client.get(
        f"/api/v1/assessment-batch-previews/{preview_id}/items",
        query_string={"limit": 2},
        headers=headers,
    )
    assert summary.get_json()["preview"] == preview
    assert len(page.get_json()["items"]) == 2
    assert page.get_json()["next_cursor"] == 2

    invalid = client.post(route, headers=headers, json={"unknown": True})
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == {
        "code": "invalid_batch_selection",
        "message": "Assessment batch selection contains unsupported fields.",
        "details": {"fields": ["unknown"]},
    }
    invalid_cursor = client.get(
        f"/api/v1/assessment-batch-previews/{preview_id}/items",
        query_string={"cursor": "not-an-integer"},
        headers=headers,
    )
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.get_json()["error"]["code"] == "invalid_preview_cursor"


@pytest.mark.parametrize("prefix", ["", "/api/v1"])
def test_preview_routes_reject_invalid_and_oversized_request_bodies(
    client,
    route_cycle,
    prefix,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    route = f"{prefix}/projects/{project_id}/assessments/{assessment_id}/batch-previews"
    headers = _api_headers(session_id) if prefix else _browser_headers(session_id)

    invalid = client.post(
        route,
        headers={**headers, "Content-Type": "application/json"},
        data="[",
    )
    oversized = client.post(
        route,
        headers={**headers, "Content-Type": "application/json"},
        data='{"categories":["' + "x" * (64 * 1024) + '"]}',
    )

    assert invalid.status_code == 400
    invalid_payload = invalid.get_json()
    assert (
        invalid_payload.get("code") == "invalid_batch_selection"
        or invalid_payload["error"]["code"] == "invalid_batch_selection"
    )
    assert oversized.status_code == 413
    oversized_payload = oversized.get_json()
    assert (
        oversized_payload.get("code") == "batch_preview_request_too_large"
        or oversized_payload["error"]["code"] == "batch_preview_request_too_large"
    )


def test_team_viewer_can_compile_and_read_a_batch_preview(client, monkeypatch):
    owner = "tok_batch_owner_" + uuid.uuid4().hex
    viewer = "tok_batch_viewer_" + uuid.uuid4().hex
    _register_token(owner)
    _register_token(viewer)
    team_response = client.post(
        "/session/teams",
        headers=_browser_headers(owner),
        json={"name": "Batch viewer team", "display_name": "Owner"},
    )
    assert team_response.status_code == 201
    team_id = str(team_response.get_json()["team"]["id"])
    invite = client.post(
        f"/session/teams/{team_id}/invites",
        headers=_browser_headers(owner),
        json={"role": "viewer", "label": "Batch viewer"},
    )
    joined = client.post(
        "/session/teams/join",
        headers=_browser_headers(viewer),
        json={
            "code": invite.get_json()["invite"]["code"],
            "display_name": "Viewer",
        },
    )
    assert joined.status_code in {200, 201}
    project = create_project(owner, {"name": "Batch viewer Project"}, team_id=team_id)
    assert project is not None
    project_id = str(project["id"])
    target = add_project_target(
        owner,
        project_id,
        {
            "type": "domain",
            "value": "batch-viewer.example.test",
            "review_state": "confirmed",
        },
        team_id=team_id,
    )
    assert target is not None
    cycle = create_assessment_cycle(owner, project_id, "network", team_id=team_id)
    assessment_id = str(cycle["assessment"]["id"])
    monkeypatch.setattr(
        "services.assessments.batch.preview_draft.probe_planning_runtime",
        _runtime,
    )

    browser = client.post(
        f"/projects/{project_id}/assessments/{assessment_id}/batch-previews",
        headers=_browser_headers(viewer, team_id),
        json={},
    )
    api = client.post(
        f"/api/v1/projects/{project_id}/assessments/{assessment_id}/batch-previews",
        headers=_api_headers(viewer, team_id),
        json={},
    )
    assert browser.status_code == 201
    assert api.status_code == 201
    assert (
        browser.get_json()["preview"]["plan_digest"]
        == api.get_json()["preview"]["plan_digest"]
    )
