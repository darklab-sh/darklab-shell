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
from services.assessments.batch.preview_compiler import compile_batch_preview
from services.assessments.batch.cancellation import cancel_assessment_batch
from services.assessments.batch.start import start_assessment_batch
from services.assessments.batch.storage_read import get_batch_parent
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
    monkeypatch.setattr(
        "services.assessments.batch.retry_draft.probe_planning_runtime",
        _runtime,
    )
    monkeypatch.setattr(
        "services.assessments.batch.retry_draft.probe_planning_runtime",
        _runtime,
    )
    yield session_id, project_id, assessment_id, str(target["id"])
    with get_db_connect()() as conn:
        conn.execute(
            "DELETE FROM assessment_batch_previews WHERE assessment_id = ?",
            (assessment_id,),
        )
        conn.execute(
            "DELETE FROM workflow_executions WHERE project_id = ? "
            "AND execution_kind = 'assessment_batch'",
            (project_id,),
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


def _start_batch(
    session_id: str,
    project_id: str,
    assessment_id: str,
) -> dict[str, object]:
    preview = compile_batch_preview(session_id, project_id, assessment_id)
    return start_assessment_batch(
        session_id,
        project_id,
        assessment_id,
        preview_id=str(preview["preview_id"]),
        plan_digest=preview["plan_digest"],
        confirmed=True,
    )


def _assessment_status(assessment_id: str) -> str:
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT status FROM project_assessments WHERE id = ?",
            (assessment_id,),
        ).fetchone()
    return str(row["status"] if row else "")


def _settle_route_source(batch_id: str) -> None:
    with get_db_connect()() as conn:
        children = conn.execute(
            "SELECT step_id, ordinal FROM workflow_execution_children "
            "WHERE execution_id = ? ORDER BY step_id, ordinal",
            (batch_id,),
        ).fetchall()
        assert len(children) == 2
        for row, status, error_code in (
            (children[0], "succeeded", ""),
            (children[1], "failed", "feature_unavailable"),
        ):
            conn.execute(
                "UPDATE workflow_execution_children SET status = ?, error_code = ? "
                "WHERE execution_id = ? AND step_id = ? AND ordinal = ?",
                (status, error_code, batch_id, row["step_id"], row["ordinal"]),
            )
        conn.execute(
            "UPDATE workflow_executions SET status = 'failed' WHERE id = ?",
            (batch_id,),
        )
        conn.commit()


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
def test_batch_start_is_idempotent_audited_and_cancel_is_project_scoped(
    client,
    route_cycle,
    monkeypatch,
    prefix,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    headers = _api_headers(session_id) if prefix else _browser_headers(session_id)
    preview_route = (
        f"{prefix}/projects/{project_id}/assessments/{assessment_id}/batch-previews"
    )
    preview = client.post(preview_route, headers=headers, json={}).get_json()["preview"]
    monkeypatch.setattr(
        "services.assessments.batch.lifecycle_actions.launch_assessment_batch",
        lambda batch_id: {
            "status": "queued",
            "batch_id": batch_id,
            "launched": 0,
            "reason_code": "fairness_limit",
        },
    )
    payload = {
        "preview_id": preview["preview_id"],
        "plan_digest": preview["plan_digest"],
        "confirmed": True,
    }
    start_route = (
        f"{prefix}/projects/{project_id}/assessments/{assessment_id}/assessment-batches"
    )

    first = client.post(start_route, headers=headers, json=payload)
    replay = client.post(start_route, headers=headers, json=payload)

    assert first.status_code == replay.status_code == 202
    first_payload = first.get_json()
    replay_payload = replay.get_json()
    batch_id = first_payload["batch"]["batch_id"]
    assert replay_payload["batch"]["batch_id"] == batch_id
    assert first_payload["launch"]["launched"] == 0
    with get_db_connect()() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions WHERE id = ?",
            (batch_id,),
        ).fetchone()["n"] == 1
        event_types = [
            str(row["event_type"])
            for row in conn.execute(
                "SELECT event_type FROM audit_events WHERE target_id = ? "
                "ORDER BY created, id",
                (batch_id,),
            ).fetchall()
        ]
    assert event_types == ["assessment_batch.start", "assessment_batch.start"]

    hidden = client.post(
        f"{prefix}/projects/prj_wrong/assessment-batches/{batch_id}/cancel",
        headers=headers,
        json={},
    )
    assert hidden.status_code == 404
    hidden_payload = hidden.get_json()
    assert (
        hidden_payload.get("code") == "batch_not_found"
        or hidden_payload["error"]["code"] == "batch_not_found"
    )
    canceled = client.post(
        f"{prefix}/projects/{project_id}/assessment-batches/{batch_id}/cancel",
        headers=headers,
        json={},
    )
    assert canceled.status_code == 200
    assert canceled.get_json()["batch"]["status"] == "canceled"
    with get_db_connect()() as conn:
        cancel_event = conn.execute(
            "SELECT details FROM audit_events WHERE target_id = ? "
            "AND event_type = 'assessment_batch.cancel'",
            (batch_id,),
        ).fetchone()
    assert cancel_event is not None
    assert project_id in str(cancel_event["details"])


@pytest.mark.parametrize("prefix", ["", "/api/v1"])
def test_retry_preview_and_start_are_lineage_scoped_capability_gated_and_audited(
    client,
    route_cycle,
    monkeypatch,
    prefix,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    headers = _api_headers(session_id) if prefix else _browser_headers(session_id)
    source = _start_batch(session_id, project_id, assessment_id)
    source_id = str(source["batch_id"])
    _settle_route_source(source_id)
    preview_route = (
        f"{prefix}/projects/{project_id}/assessment-batches/{source_id}/retry-previews"
    )

    created = client.post(preview_route, headers=headers, json={})

    assert created.status_code == 201
    preview = created.get_json()["preview"]
    assert preview["source_batch_id"] == source_id
    assert preview["selected_item_count"] == 1
    wrong_project = client.post(
        f"{prefix}/projects/prj_wrong/assessment-batches/{source_id}/retry-previews",
        headers=headers,
        json={},
    )
    assert wrong_project.status_code == 404
    monkeypatch.setattr(
        "services.assessments.batch.retry_actions.launch_assessment_batch",
        lambda batch_id: {
            "status": "queued",
            "batch_id": batch_id,
            "launched": 0,
            "reason_code": "fairness_limit",
        },
    )
    started = client.post(
        f"{prefix}/projects/{project_id}/assessment-batches/{source_id}/retry",
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "plan_digest": preview["plan_digest"],
            "confirmed": True,
        },
    )

    assert started.status_code == 202
    retry = started.get_json()["batch"]
    assert retry["source_batch_id"] == source_id
    assert retry["batch_id"] != source_id
    with get_db_connect()() as conn:
        audit = conn.execute(
            "SELECT event_type, details FROM audit_events WHERE target_id = ?",
            (retry["batch_id"],),
        ).fetchone()
        source_event = conn.execute(
            "SELECT retry_batch_id FROM assessment_batch_events "
            "WHERE batch_id = ? AND event_type = 'retry_created'",
            (source_id,),
        ).fetchone()
    assert audit is not None
    assert audit["event_type"] == "assessment_batch.retry"
    assert source_id in str(audit["details"])
    assert source_event["retry_batch_id"] == retry["batch_id"]


@pytest.mark.parametrize("prefix", ["", "/api/v1"])
def test_batch_start_and_cancel_reject_unbounded_or_unsupported_bodies(
    client,
    route_cycle,
    prefix,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    headers = _api_headers(session_id) if prefix else _browser_headers(session_id)
    start_route = (
        f"{prefix}/projects/{project_id}/assessments/{assessment_id}/assessment-batches"
    )
    invalid = client.post(start_route, headers=headers, json={"unexpected": True})
    oversized = client.post(
        start_route,
        headers={**headers, "Content-Type": "application/json"},
        data='{"preview_id":"' + "x" * (16 * 1024) + '"}',
    )
    bad_cancel = client.post(
        f"{prefix}/projects/{project_id}/assessment-batches/wfx_missing/cancel",
        headers=headers,
        json={"force": True},
    )

    assert invalid.status_code == 400
    invalid_payload = invalid.get_json()
    assert (
        invalid_payload.get("code") == "invalid_batch_start"
        or invalid_payload["error"]["code"] == "invalid_batch_start"
    )
    assert oversized.status_code == 413
    oversized_payload = oversized.get_json()
    assert (
        oversized_payload.get("code") == "batch_mutation_request_too_large"
        or oversized_payload["error"]["code"]
        == "batch_mutation_request_too_large"
    )
    assert bad_cancel.status_code == 400
    bad_cancel_payload = bad_cancel.get_json()
    assert (
        bad_cancel_payload.get("code") == "invalid_batch_cancel"
        or bad_cancel_payload["error"]["code"] == "invalid_batch_cancel"
    )


def test_browser_and_api_batch_reads_share_bounded_pages_and_stable_rollups(
    client,
    route_cycle,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    batches = [
        _start_batch(session_id, project_id, assessment_id)
        for _index in range(2)
    ]
    batch_ids = {str(batch["batch_id"]) for batch in batches}
    first_batch_id = str(batches[0]["batch_id"])
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'skipped', "
            "error_code = 'failure_limit' WHERE execution_id = ? "
            "AND step_id = 'chunk_0001' AND ordinal = 0",
            (first_batch_id,),
        )
        conn.commit()

    browser_headers = _browser_headers(session_id)
    api_headers = _api_headers(session_id)
    browser_list = client.get(
        f"/projects/{project_id}/assessment-batches",
        query_string={"assessment_id": assessment_id, "limit": 1},
        headers=browser_headers,
    )
    assert browser_list.status_code == 200
    browser_page = browser_list.get_json()
    assert len(browser_page["batches"]) == 1
    assert browser_page["has_more"] is True
    browser_next = client.get(
        f"/projects/{project_id}/assessment-batches",
        query_string={"cursor": browser_page["next_cursor"], "limit": 1},
        headers=browser_headers,
    ).get_json()
    assert {batch["batch_id"] for batch in [*browser_page["batches"], *browser_next["batches"]]} == batch_ids
    assert browser_next["has_more"] is False

    api_list = client.get(
        f"/api/v1/projects/{project_id}/assessment-batches",
        query_string={"assessment_id": assessment_id},
        headers=api_headers,
    )
    assert api_list.status_code == 200
    assert {batch["batch_id"] for batch in api_list.get_json()["batches"]} == batch_ids

    for prefix, headers in (("", browser_headers), ("/api/v1", api_headers)):
        detail = client.get(
            f"{prefix}/assessment-batches/{first_batch_id}", headers=headers
        )
        assert detail.status_code == 200
        progress = detail.get_json()["batch"]["progress"]
        assert (progress["pending"], progress["skipped"], progress["canceled"]) == (
            1,
            1,
            0,
        )
        items = client.get(
            f"{prefix}/assessment-batches/{first_batch_id}/items",
            query_string={"limit": 1},
            headers=headers,
        )
        assert items.status_code == 200
        item_page = items.get_json()
        assert item_page["has_more"] is True
        assert item_page["next_cursor"] == 1
        assert item_page["items"][0]["status"] == "skipped"
        assert item_page["items"][0]["check_count"] >= 1
        events = client.get(
            f"{prefix}/assessment-batches/{first_batch_id}/events",
            query_string={"limit": 1},
            headers=headers,
        )
        assert events.status_code == 200
        event_page = events.get_json()
        assert event_page["has_more"] is True
        assert event_page["next_cursor"] == 1
        assert event_page["events"][0]["event_type"] == "parent_created"

    foreign = "tok_batch_routes_read_foreign_" + uuid.uuid4().hex
    _register_token(foreign)
    hidden = client.get(
        f"/api/v1/assessment-batches/{first_batch_id}",
        headers=_api_headers(foreign),
    )
    assert hidden.status_code == 404
    assert hidden.get_json()["error"]["code"] == "batch_not_found"
    invalid = client.get(
        f"/api/v1/projects/{project_id}/assessment-batches",
        query_string={"cursor": "not-a-cursor"},
        headers=api_headers,
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_batch_cursor"

    for batch_id in batch_ids:
        canceled = cancel_assessment_batch(session_id, batch_id)
        assert canceled is not None


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
    monkeypatch.setattr(
        "services.assessments.batch.retry_draft.probe_planning_runtime",
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
    for prefix, headers, preview in (
        ("", _browser_headers(viewer, team_id), browser.get_json()["preview"]),
        ("/api/v1", _api_headers(viewer, team_id), api.get_json()["preview"]),
    ):
        denied = client.post(
            f"{prefix}/projects/{project_id}/assessments/{assessment_id}/assessment-batches",
            headers=headers,
            json={
                "preview_id": preview["preview_id"],
                "plan_digest": preview["plan_digest"],
                "confirmed": True,
            },
        )
        assert denied.status_code == 403

    source = start_assessment_batch(
        owner,
        project_id,
        assessment_id,
        preview_id=str(browser.get_json()["preview"]["preview_id"]),
        plan_digest=browser.get_json()["preview"]["plan_digest"],
        confirmed=True,
        team_id=team_id,
    )
    source_id = str(source["batch_id"])
    _settle_route_source(source_id)
    for prefix, headers in (
        ("", _browser_headers(viewer, team_id)),
        ("/api/v1", _api_headers(viewer, team_id)),
    ):
        retry_preview_response = client.post(
            f"{prefix}/projects/{project_id}/assessment-batches/"
            f"{source_id}/retry-previews",
            headers=headers,
            json={},
        )
        assert retry_preview_response.status_code == 201
        retry_preview = retry_preview_response.get_json()["preview"]
        denied = client.post(
            f"{prefix}/projects/{project_id}/assessment-batches/{source_id}/retry",
            headers=headers,
            json={
                "preview_id": retry_preview["preview_id"],
                "plan_digest": retry_preview["plan_digest"],
                "confirmed": True,
            },
        )
        assert denied.status_code == 403


@pytest.mark.parametrize("prefix", ["", "/api/v1"])
@pytest.mark.parametrize("next_status", ["completed", "archived"])
def test_assessment_lifecycle_waits_for_batch_cancellation_and_requires_a_fresh_request(
    client,
    route_cycle,
    prefix,
    next_status,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    batch = _start_batch(session_id, project_id, assessment_id)
    batch_id = str(batch["batch_id"])
    headers = _api_headers(session_id) if prefix else _browser_headers(session_id)
    route = f"{prefix}/projects/{project_id}/assessments/{assessment_id}"

    pending = client.patch(route, headers=headers, json={"status": next_status})

    assert pending.status_code == 409
    payload = pending.get_json()
    if prefix:
        assert payload["error"]["code"] == "assessment_batch_cancellation_pending"
        assert payload["error"]["details"] == {
            "batch_id": batch_id,
            "batch_ids": [batch_id],
        }
    else:
        assert payload["code"] == "assessment_batch_cancellation_pending"
        assert payload["batch_id"] == batch_id
        assert payload["batch_ids"] == [batch_id]
    assert _assessment_status(assessment_id) == "active"
    assert get_batch_parent(session_id, batch_id)["status"] == "canceled"

    applied = client.patch(route, headers=headers, json={"status": next_status})

    assert applied.status_code == 200
    assert applied.get_json()["assessment"]["status"] == next_status


@pytest.mark.parametrize("prefix", ["", "/api/v1"])
def test_assessment_delete_waits_for_batch_cancellation_before_deleting(
    client,
    route_cycle,
    prefix,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    batch = _start_batch(session_id, project_id, assessment_id)
    batch_id = str(batch["batch_id"])
    archived_at = datetime.now(timezone.utc).isoformat()
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE project_assessments SET status = 'archived', completed_at = ?, "
            "archived_at = ? WHERE id = ?",
            (archived_at, archived_at, assessment_id),
        )
        conn.commit()
    headers = _api_headers(session_id) if prefix else _browser_headers(session_id)
    route = f"{prefix}/projects/{project_id}/assessments/{assessment_id}"

    pending = client.delete(route, headers=headers)

    assert pending.status_code == 409
    payload = pending.get_json()
    if prefix:
        assert payload["error"]["details"]["batch_id"] == batch_id
    else:
        assert payload["batch_id"] == batch_id
    assert _assessment_status(assessment_id) == "archived"
    assert get_batch_parent(session_id, batch_id)["status"] == "canceled"

    deleted = client.delete(route, headers=headers)

    assert deleted.status_code == 200
    assert _assessment_status(assessment_id) == ""


def test_project_delete_cancels_every_active_batch_then_cleans_coordinator_state(
    client,
    route_cycle,
):
    session_id, project_id, assessment_id, _target_id = route_cycle
    batch_ids = {
        str(_start_batch(session_id, project_id, assessment_id)["batch_id"])
        for _index in range(2)
    }
    assert len(batch_ids) == 2

    pending = client.delete(
        f"/projects/{project_id}",
        headers=_browser_headers(session_id),
    )

    assert pending.status_code == 409
    payload = pending.get_json()
    assert payload["code"] == "assessment_batch_cancellation_pending"
    assert set(payload["batch_ids"]) == batch_ids
    assert payload["batch_id"] in batch_ids
    with get_db_connect()() as conn:
        assert conn.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    assert {
        str(get_batch_parent(session_id, batch_id)["status"])
        for batch_id in batch_ids
    } == {"canceled"}

    deleted = client.delete(
        f"/projects/{project_id}",
        headers=_browser_headers(session_id),
    )

    assert deleted.status_code == 200
    with get_db_connect()() as conn:
        assert conn.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM workflow_executions WHERE project_id = ? "
            "AND execution_kind = 'assessment_batch'",
            (project_id,),
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM assessment_batch_previews WHERE project_id = ?",
            (project_id,),
        ).fetchone() is None
