# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only browser route contracts for Project-scoped probe planning."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

from conftest import reusable_test_app
from core.database import db_connect
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.assessments.storage import create_assessment_cycle
from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
from services.projects.links import link_run_to_project_on_conn
from services.runs.contracts import RunSpawnError


@pytest.fixture
def client():
    return reusable_test_app(__name__).test_client()


@pytest.fixture(autouse=True)
def _probe_runtime(monkeypatch):
    monkeypatch.setattr(
        "services.assessments.probe_service.resolve_runtime_command",
        lambda command: f"/usr/bin/{command}",
    )
    monkeypatch.setattr(
        "services.assessments.probe_service.managed_nuclei_template_snapshot",
        lambda: NucleiTemplateCacheSnapshot(
            "ready", "v10.4.3", "sha256:" + "a" * 64, 12,
        ),
    )


def _headers(session_id: str, team_id: str = "") -> dict[str, str]:
    headers = {"X-Session-ID": session_id}
    if team_id:
        headers["X-Team-ID"] = team_id
    return headers


def _create_project(client, session_id: str, *, team_id: str = "") -> dict:
    response = client.post(
        "/projects",
        headers=_headers(session_id, team_id),
        json={"name": "Probe route Project"},
    )
    assert response.status_code == 201
    return response.get_json()["project"]


def _create_target(
    client,
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    target_type: str = "domain",
    value: str = "probe-route.example.com",
) -> dict:
    response = client.post(
        f"/projects/{project_id}/targets",
        headers=_headers(session_id, team_id),
        json={"type": target_type, "value": value},
    )
    assert response.status_code == 201
    return response.get_json()["target"]


def _table_counts() -> tuple[int, int, int]:
    with db_connect() as conn:
        counts = tuple(
            int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
            for table in ("runs", "audit_events", "project_assessment_evidence")
        )
    return counts[0], counts[1], counts[2]


def _register_token(token: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
            (token, now, ""),
        )
        conn.commit()


def _create_protected_http_profile(
    client,
    token: str,
    project_id: str,
    target_value: str,
    *,
    secret_value: str = "probe-profile-secret",
    base_url: str = "",
    allowed_host: str = "",
) -> tuple[str, str]:
    stored = client.post(
        "/session/secrets",
        headers={"X-Session-ID": token},
        json={"name": "PROBE_HTTP_TOKEN", "value": secret_value},
    )
    assert stored.status_code == 201
    created = client.post(
        f"/api/v1/projects/{project_id}/http-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Protected probe application",
            "role": "user",
            "base_url": base_url or f"https://{target_value}",
            "scope_roots": [base_url or f"https://{target_value}"],
            "allowed_hosts": [allowed_host or target_value],
            "include_paths": ["/app"],
            "exclude_paths": ["/app/private"],
            "headers": [{
                "name": "X-Probe-Token",
                "secret_name": "PROBE_HTTP_TOKEN",
            }],
            "rate_limit_per_second": 3,
            "concurrency": 2,
        },
    )
    assert created.status_code == 201
    return created.get_json()["profile"]["id"], secret_value


def _join_team_member(
    client,
    owner: str,
    member: str,
    team_id: str,
    role: str,
) -> None:
    invite = client.post(
        f"/session/teams/{team_id}/invites",
        headers=_headers(owner),
        json={"role": role, "label": f"Probe {role}"},
    )
    assert invite.status_code == 201
    joined = client.post(
        "/session/teams/join",
        headers=_headers(member),
        json={"code": invite.get_json()["invite"]["code"], "display_name": role.title()},
    )
    assert joined.status_code in {200, 201}


def test_probe_routes_list_resolve_and_plan_without_writes(client, caplog):
    session_id = "tok_probe_routes_" + uuid.uuid4().hex
    _register_token(session_id)
    project = _create_project(client, session_id)
    target = _create_target(client, session_id, project["id"])
    before = _table_counts()

    catalog_response = client.get(
        f"/projects/{project['id']}/probes?service=https&target_type=url",
        headers=_headers(session_id),
    )
    resolve_response = client.post(
        f"/projects/{project['id']}/probes/targets/resolve",
        json={"target_value": target["value"]},
        headers=_headers(session_id),
    )
    plan_response = client.get(
        f"/projects/{project['id']}/probes/plan",
        query_string={"action_id": "nmap", "entity_id": target["id"], "nmap_profile": "tls"},
        headers=_headers(session_id),
    )

    assert catalog_response.status_code == 200
    catalog = catalog_response.get_json()["catalog"]
    assert catalog["schema_version"] == 1
    assert {item["id"] for item in catalog["actions"]} == {
        "curl", "dalfox", "httpx", "katana", "nuclei", "sqlmap",
    }
    assert catalog["service_recommendations"][0]["action_id"] == "httpx"
    assert resolve_response.get_json()["target"] == {
        "entity_id": target["id"],
        "type": "domain",
        "value": target["value"],
    }
    assert plan_response.status_code == 200
    plan = plan_response.get_json()["plan"]
    assert plan["project_id"] == project["id"]
    assert plan["target"]["entity_id"] == target["id"]
    assert plan["display_command"].startswith("nmap ")
    assert "--script ssl-cert,ssl-enum-ciphers" in plan["display_command"]
    assert plan["availability"]["available"] is True
    assert _table_counts() == before
    assert target["value"] not in caplog.text

    rejected = client.post(
        f"/projects/{project['id']}/probes/targets/resolve",
        json={"target_value": target["value"], "entity_id": target["id"]},
        headers=_headers(session_id),
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["code"] == "unsupported_fields"
    query_rejected = client.post(
        f"/projects/{project['id']}/probes/targets/resolve",
        query_string={"target_value": target["value"]},
        json={"target_value": target["value"]},
        headers=_headers(session_id),
    )
    assert query_rejected.status_code == 400
    assert query_rejected.get_json()["code"] == "unsupported_fields"

    for prefix, headers in (
        (f"/projects/{project['id']}", _headers(session_id)),
        (f"/api/v1/projects/{project['id']}", {"Authorization": f"Bearer {session_id}"}),
    ):
        invalid_catalog = client.get(
            f"{prefix}/probes?target_type=cidr",
            headers=headers,
        )
        assert invalid_catalog.status_code == 400
        payload = invalid_catalog.get_json()
        assert payload.get("code") == "invalid_target_type" or (
            payload.get("error") or {}
        ).get("code") == "invalid_target_type"


def test_probe_routes_fail_closed_for_foreign_archived_and_value_only_plans(client):
    session_id = "probe-owner-" + uuid.uuid4().hex
    foreign_id = "probe-foreign-" + uuid.uuid4().hex
    project = _create_project(client, session_id)
    target = _create_target(client, session_id, project["id"])
    route = f"/projects/{project['id']}/probes"

    assert client.get(route, headers=_headers(foreign_id)).status_code == 404
    missing_entity = client.get(
        f"{route}/plan",
        query_string={"action_id": "ping", "target_value": target["value"]},
        headers=_headers(session_id),
    )
    assert missing_entity.status_code == 400
    assert missing_entity.get_json()["code"] == "entity_id_required"

    archived = client.put(
        f"/projects/{project['id']}",
        headers=_headers(session_id),
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    archived_catalog = client.get(route, headers=_headers(session_id))
    assert archived_catalog.status_code == 409
    assert archived_catalog.get_json()["code"] == "project_archived"


def test_team_viewer_can_read_probe_catalog_and_plan(client):
    owner = "tok_" + uuid.uuid4().hex
    viewer = "tok_" + uuid.uuid4().hex
    _register_token(owner)
    _register_token(viewer)
    team_response = client.post(
        "/session/teams",
        headers=_headers(owner),
        json={"name": "Probe team " + uuid.uuid4().hex[:8], "display_name": "Owner"},
    )
    assert team_response.status_code == 201
    team_id = team_response.get_json()["team"]["id"]
    invite = client.post(
        f"/session/teams/{team_id}/invites",
        headers=_headers(owner),
        json={"role": "viewer", "label": "Probe viewer"},
    )
    joined = client.post(
        "/session/teams/join",
        headers=_headers(viewer),
        json={"code": invite.get_json()["invite"]["code"], "display_name": "Viewer"},
    )
    assert joined.status_code in {200, 201}
    project = _create_project(client, owner, team_id=team_id)
    target = _create_target(client, owner, project["id"], team_id=team_id)

    catalog = client.get(
        f"/projects/{project['id']}/probes",
        headers=_headers(viewer, team_id),
    )
    plan = client.get(
        f"/projects/{project['id']}/probes/plan",
        query_string={"action_id": "ping", "entity_id": target["id"]},
        headers=_headers(viewer, team_id),
    )
    assert catalog.status_code == 200
    assert plan.status_code == 200
    assert plan.get_json()["plan"]["target"]["value"] == target["value"]
    protected_plan = client.get(
        f"/projects/{project['id']}/probes/plan",
        query_string={
            "action_id": "httpx",
            "entity_id": target["id"],
            "http_profile_id": "hpr_not_visible_to_viewer",
        },
        headers=_headers(viewer, team_id),
    )
    assert protected_plan.status_code == 403
    denied = client.post(
        f"/projects/{project['id']}/probes/run",
        headers=_headers(viewer, team_id),
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": plan.get_json()["plan"]["plan_digest"],
        },
    )
    assert denied.status_code == 403


def test_team_probe_role_matrix_keeps_protected_launches_admin_only(client, monkeypatch):
    owner = "tok_" + uuid.uuid4().hex
    viewer = "tok_" + uuid.uuid4().hex
    operator = "tok_" + uuid.uuid4().hex
    admin = "tok_" + uuid.uuid4().hex
    for token in (owner, viewer, operator, admin):
        _register_token(token)
    team_response = client.post(
        "/session/teams",
        headers=_headers(owner),
        json={"name": "Probe matrix " + uuid.uuid4().hex[:8], "display_name": "Owner"},
    )
    assert team_response.status_code == 201
    team_id = team_response.get_json()["team"]["id"]
    for token, role in ((viewer, "viewer"), (operator, "operator"), (admin, "admin")):
        _join_team_member(client, owner, token, team_id, role)
    project = _create_project(client, owner, team_id=team_id)
    target = _create_target(client, owner, project["id"], team_id=team_id)
    def api_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "X-Team-ID": team_id}
    profile = client.post(
        f"/api/v1/projects/{project['id']}/http-profiles",
        headers=api_headers(owner),
        json={
            "name": "Team probe profile",
            "base_url": f"https://{target['value']}",
            "allowed_hosts": [target["value"]],
        },
    )
    assert profile.status_code == 201
    profile_id = profile.get_json()["profile"]["id"]
    route = f"/api/v1/projects/{project['id']}/probes"
    for token in (viewer, operator, admin, owner):
        assert client.get(route, headers=api_headers(token)).status_code == 200
        assert client.post(
            f"{route}/plan",
            headers=api_headers(token),
            json={"action_id": "ping", "entity_id": target["id"]},
        ).status_code == 200

    monkeypatch.setattr("blueprints.api_v1.broker_available", lambda: True)
    monkeypatch.setattr(
        "blueprints.api_v1._start_brokered_run_service",
        lambda **_kwargs: SimpleNamespace(run_id="run_probe_matrix", status="queued"),
    )
    viewer_plan = client.post(
        f"{route}/plan",
        headers=api_headers(viewer),
        json={"action_id": "ping", "entity_id": target["id"]},
    ).get_json()["plan"]
    viewer_launch = client.post(
        f"{route}/run",
        headers=api_headers(viewer),
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": viewer_plan["plan_digest"],
        },
    )
    assert viewer_launch.status_code == 403

    operator_plan = client.post(
        f"{route}/plan",
        headers=api_headers(operator),
        json={"action_id": "ping", "entity_id": target["id"]},
    ).get_json()["plan"]
    operator_launch = client.post(
        f"{route}/run",
        headers=api_headers(operator),
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": operator_plan["plan_digest"],
        },
    )
    assert operator_launch.status_code == 202
    assert client.post(
        f"{route}/plan",
        headers=api_headers(operator),
        json={
            "action_id": "httpx",
            "entity_id": target["id"],
            "http_profile_id": profile_id,
        },
    ).status_code == 403

    for token in (admin, owner):
        protected_body = {
            "action_id": "httpx",
            "entity_id": target["id"],
            "http_profile_id": profile_id,
        }
        protected_plan = client.post(
            f"{route}/plan",
            headers=api_headers(token),
            json=protected_body,
        )
        assert protected_plan.status_code == 200
        launched = client.post(
            f"{route}/run",
            headers=api_headers(token),
            json={
                **protected_body,
                "confirmed": True,
                "plan_digest": protected_plan.get_json()["plan"]["plan_digest"],
            },
        )
        assert launched.status_code == 202


def _probe_plan(client, session_id: str, project_id: str, entity_id: str) -> dict:
    response = client.get(
        f"/projects/{project_id}/probes/plan",
        query_string={"action_id": "ping", "entity_id": entity_id},
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    return response.get_json()["plan"]


def test_probe_launch_revalidates_and_binds_the_requested_project_and_tab(
    client, monkeypatch
):
    session_id = "probe-launch-" + uuid.uuid4().hex
    project = _create_project(client, session_id)
    target = _create_target(client, session_id, project["id"])
    plan = _probe_plan(client, session_id, project["id"], target["id"])
    started_calls = []

    def _start(**kwargs):
        started_calls.append(kwargs)
        return SimpleNamespace(run_id="run_probe_route", status="queued")

    monkeypatch.setattr("blueprints.run.broker_available", lambda: True)
    monkeypatch.setattr("blueprints.run._start_brokered_run_service", _start)
    logger = mock.Mock()
    monkeypatch.setattr("blueprints.projects.log", logger)
    response = client.post(
        f"/projects/{project['id']}/probes/run",
        headers={
            **_headers(session_id), "X-Client-ID": "client-probe",
            "X-Request-ID": "probe-browser-request",
        },
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": plan["plan_digest"],
            "tab_id": "tab-probe",
            "workspace_cwd": "evidence",
        },
    )

    assert response.status_code == 202
    assert response.get_json()["run"]["run_id"] == "run_probe_route"
    assert response.get_json()["project_id"] == project["id"]
    assert len(started_calls) == 1
    launch = started_calls[0]
    assert launch["original_command"] == plan["display_command"]
    assert launch["display_command"] == plan["display_command"]
    assert launch["link_project_id"] == project["id"]
    assert launch["owner_client_id"] == "client-probe"
    assert launch["owner_tab_id"] == "tab-probe"
    assert launch["workspace_cwd"] == "evidence"
    assert launch["trusted_execution_args"] == ()
    log_call = next(
        call for call in logger.info.call_args_list
        if call.args == ("PROJECT_PROBE_LAUNCHED",)
    )
    assert log_call.kwargs["extra"]["request_id"] == "probe-browser-request"
    assert log_call.kwargs["extra"]["source"] == "browser_terminal"
    with db_connect() as conn:
        audit = conn.execute(
            "SELECT request_id FROM audit_events WHERE target_id = ?",
            ("run_probe_route",),
        ).fetchone()
    assert audit["request_id"] == "probe-browser-request"


def test_probe_launch_itself_writes_no_cycle_evidence_but_finalized_run_can_cover(
    client,
    monkeypatch,
):
    session_id = "probe-coverage-" + uuid.uuid4().hex
    project = _create_project(client, session_id)
    target = _create_target(client, session_id, project["id"])
    profile = {
        "key": "probe-coverage",
        "version": "1.0",
        "label": "Probe coverage",
        "purpose": "Prove ordinary run reconciliation.",
        "target_types": ["domain"],
        "checks": [{
            "key": "host_reachability",
            "version": "1.0",
            "category": "discovery",
            "label": "Host reachability",
            "purpose": "Reach the host.",
            "target_types": ["domain"],
            "evidence_rules": [{
                "key": "completed_reachability_run",
                "version": "1.0",
                "evidence_types": ["run"],
                "command_roots": ["ping"],
                "workflow_actions": [],
                "structured_output_kinds": [],
                "target_match": "exact",
                "completion": "succeeded",
                "compatible_versions": ["*"],
                "negative_evidence": True,
            }],
            "policy_level": "safe",
            "recommended_action": "command:ping",
            "completion_guidance": "Run the bounded reachability probe.",
        }],
    }
    monkeypatch.setattr(
        "services.assessments.storage.get_assessment_profile",
        lambda key: profile if key == "probe-coverage" else None,
    )
    assessment = create_assessment_cycle(
        session_id,
        project["id"],
        "probe-coverage",
    )["assessment"]
    plan = _probe_plan(client, session_id, project["id"], target["id"])
    started_calls = []
    monkeypatch.setattr("blueprints.run.broker_available", lambda: True)
    monkeypatch.setattr(
        "blueprints.run._start_brokered_run_service",
        lambda **kwargs: started_calls.append(kwargs) or SimpleNamespace(
            run_id="run_probe_coverage", status="queued"
        ),
    )
    launched = client.post(
        f"/projects/{project['id']}/probes/run",
        headers=_headers(session_id),
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": plan["plan_digest"],
        },
    )
    assert launched.status_code == 202
    with db_connect() as conn:
        before = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessment_evidence "
            "WHERE assessment_id = ?",
            (assessment["id"],),
        ).fetchone()
        assert before["count"] == 0
        launch = started_calls[0]
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, team_id, run_kind, command, started, finished, exit_code) "
            "VALUES (?, ?, '', 'external', ?, ?, ?, 0)",
            (
                "run_probe_coverage",
                session_id,
                launch["display_command"],
                "2026-08-13 00:00:00",
                "2026-08-13 00:00:01",
            ),
        )
        assert link_run_to_project_on_conn(
            conn,
            session_id,
            launch["link_project_id"],
            "run_probe_coverage",
        ) is not None
        first = reconcile_run_evidence_on_conn(conn, "run_probe_coverage")
        second = reconcile_run_evidence_on_conn(conn, "run_probe_coverage")
        check = conn.execute(
            "SELECT state FROM project_assessment_checks WHERE assessment_id = ?",
            (assessment["id"],),
        ).fetchone()
        conn.commit()

    assert first["evidence_linked"] == 1
    assert second["evidence_already_linked"] == 1
    assert check["state"] == "covered"


def test_probe_launch_rejects_stale_targets_unknown_fields_and_unavailable_broker(
    client, monkeypatch
):
    session_id = "probe-launch-errors-" + uuid.uuid4().hex
    project = _create_project(client, session_id)
    target = _create_target(client, session_id, project["id"])
    plan = _probe_plan(client, session_id, project["id"], target["id"])
    route = f"/projects/{project['id']}/probes/run"
    body = {
        "action_id": "ping",
        "entity_id": target["id"],
        "confirmed": True,
        "plan_digest": plan["plan_digest"],
    }

    unknown = client.post(route, headers=_headers(session_id), json={**body, "command": "ping evil"})
    assert unknown.status_code == 400
    assert unknown.get_json()["code"] == "unsupported_fields"

    monkeypatch.setattr("blueprints.run.broker_available", lambda: False)
    monkeypatch.setattr("blueprints.run.broker_unavailable_reason", lambda: "Broker offline")
    unavailable = client.post(route, headers=_headers(session_id), json=body)
    assert unavailable.status_code == 503
    assert unavailable.get_json()["code"] == "broker_unavailable"

    archived = client.put(
        f"/projects/{project['id']}",
        headers=_headers(session_id),
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    stale = client.post(route, headers=_headers(session_id), json=body)
    assert stale.status_code == 409
    assert stale.get_json()["code"] == "project_archived"


def test_api_v1_probe_catalog_plan_and_launch_share_the_project_bound_service(
    client, monkeypatch
):
    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target = _create_target(client, token, project["id"])
    api_headers = {
        "Authorization": f"Bearer {token}", "X-Request-ID": "probe-api-request",
    }

    catalog = client.get(f"/api/v1/projects/{project['id']}/probes", headers=api_headers)
    resolved = client.post(
        f"/api/v1/projects/{project['id']}/probes/targets/resolve",
        headers=api_headers,
        json={"target_value": target["value"]},
    )
    planned = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=api_headers,
        json={"action_id": "ping", "entity_id": target["id"]},
    )
    assert catalog.status_code == 200
    assert resolved.status_code == 200
    assert resolved.get_json()["target"]["entity_id"] == target["id"]
    assert planned.status_code == 200
    plan = planned.get_json()["plan"]

    calls = []
    monkeypatch.setattr("blueprints.api_v1.broker_available", lambda: True)
    logger = mock.Mock()
    monkeypatch.setattr("blueprints.api_v1.log", logger)
    monkeypatch.setattr(
        "blueprints.api_v1._start_brokered_run_service",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
            run_id="run_api_probe", status="queued"
        ),
    )
    launched = client.post(
        f"/api/v1/projects/{project['id']}/probes/run",
        headers=api_headers,
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": plan["plan_digest"],
        },
    )

    assert launched.status_code == 202
    assert launched.get_json()["run"]["id"] == "run_api_probe"
    assert calls[0]["link_project_id"] == project["id"]
    assert calls[0]["owner_tab_id"] == ""
    assert calls[0]["display_command"] == plan["display_command"]
    log_call = next(
        call for call in logger.info.call_args_list
        if call.args == ("API_PROJECT_PROBE_LAUNCHED",)
    )
    assert log_call.kwargs["extra"]["request_id"] == "probe-api-request"
    assert log_call.kwargs["extra"]["source"] == "api_v1"


def test_api_v1_probe_routes_require_auth_and_reject_client_owned_plan_fields(client):
    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target = _create_target(client, token, project["id"])
    route = f"/api/v1/projects/{project['id']}/probes/plan"

    assert client.get(f"/api/v1/projects/{project['id']}/probes").status_code == 401
    rejected = client.post(
        route,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "display_command": "ping attacker.example",
        },
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["error"]["code"] == "unsupported_fields"

    resolve_route = f"/api/v1/projects/{project['id']}/probes/targets/resolve"
    assert client.post(resolve_route, json={"target_value": target["value"]}).status_code == 401
    malformed = client.post(
        resolve_route,
        headers={"Authorization": f"Bearer {token}"},
        json={"target_value": target["value"], "entity_id": target["id"]},
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "unsupported_fields"


def test_protected_probe_preview_explains_disabled_and_unsupported_profiles(client):
    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target = _create_target(client, token, project["id"])
    profile_id, _secret_value = _create_protected_http_profile(
        client,
        token,
        project["id"],
        target["value"],
    )
    headers = {"Authorization": f"Bearer {token}"}
    unsupported = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=headers,
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "http_profile_id": profile_id,
        },
    )
    assert unsupported.status_code == 200
    unsupported_plan = unsupported.get_json()["plan"]
    assert unsupported_plan["launchable"] is False
    assert unsupported_plan["availability"]["code"] == "http_profile_unavailable"

    disabled = client.patch(
        f"/api/v1/projects/{project['id']}/http-profiles/{profile_id}",
        headers=headers,
        json={"enabled": False, "revision": 1},
    )
    assert disabled.status_code == 200
    disabled_preview = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=headers,
        json={
            "action_id": "httpx",
            "entity_id": target["id"],
            "http_profile_id": profile_id,
        },
    )
    assert disabled_preview.status_code == 200
    disabled_plan = disabled_preview.get_json()["plan"]
    assert disabled_plan["launchable"] is False
    assert disabled_plan["availability"]["code"] == "http_profile_unavailable"
    assert "disabled" in disabled_plan["availability"]["reason"].casefold()


def test_api_v1_protected_probe_is_redacted_project_bound_and_cleanup_safe(
    client,
    monkeypatch,
    tmp_path,
):
    from services.assessments import http_profile_runtime

    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target = _create_target(client, token, project["id"])
    profile_id, secret_value = _create_protected_http_profile(
        client,
        token,
        project["id"],
        target["value"],
    )
    headers = {"Authorization": f"Bearer {token}"}
    plan_body = {
        "action_id": "httpx",
        "entity_id": target["id"],
        "http_profile_id": profile_id,
    }
    preview = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=headers,
        json=plan_body,
    )

    assert preview.status_code == 200
    plan = preview.get_json()["plan"]
    assert plan["http_profile"] == {
        "id": profile_id,
        "name": "Protected probe application",
        "role": "user",
        "credential_use": ["headers"],
        "scope": {
            "allowed_hosts": [target["value"]],
            "scope_roots": [f"https://{target['value']}"],
            "include_paths": ["/app"],
            "exclude_paths": ["/app/private"],
        },
        "enabled": True,
        "revision": 1,
        "rate_limit_per_second": 3,
        "concurrency": 2,
    }
    assert plan["bounds"]["credential_use"] == "protected_http_profile"
    assert plan["display_command"].endswith("-sf [protected]")
    assert secret_value not in preview.get_data(as_text=True)
    assert not ({"headers", "secret_refs", "file_refs", "private_args"} & plan["http_profile"].keys())

    monkeypatch.setattr(http_profile_runtime, "_scanner_user_exists", lambda: False)
    monkeypatch.setattr(http_profile_runtime, "resolve_data_dir", lambda _cfg: str(tmp_path))
    calls = []
    monkeypatch.setattr("blueprints.api_v1.broker_available", lambda: True)
    monkeypatch.setattr(
        "blueprints.api_v1._start_brokered_run_service",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
            run_id="run_protected_probe", status="queued"
        ),
    )
    launched = client.post(
        f"/api/v1/projects/{project['id']}/probes/run",
        headers=headers,
        json={
            **plan_body,
            "confirmed": True,
            "plan_digest": plan["plan_digest"],
        },
    )

    assert launched.status_code == 202
    launch = calls[0]
    assert launch["link_project_id"] == project["id"]
    assert launch["display_command"] == plan["display_command"]
    assert "[protected]" not in launch["original_command"]
    assert secret_value not in launch["original_command"]
    assert launch["trusted_execution_args"][:1] == ("-sf",)
    secret_path = Path(launch["trusted_execution_args"][1])
    assert secret_path.is_file()
    assert secret_value in secret_path.read_text(encoding="utf-8")
    assert secret_value in launch["private_values"]
    assert str(secret_path) in launch["private_values"]
    assert secret_value not in launched.get_data(as_text=True)
    with db_connect() as conn:
        audit_row = conn.execute(
            "SELECT details FROM audit_events "
            "WHERE event_type = 'probe.launch' AND target_id = ?",
            ("run_protected_probe",),
        ).fetchone()
    assert audit_row is not None
    audit_details = json.loads(audit_row["details"] or "{}")
    assert audit_details["profile_id"] == profile_id
    assert audit_details["profile_role"] == "user"
    assert audit_details["credential_use"] == ["headers"]
    assert audit_details.get("omitted_detail_keys", 0) == 0
    assert set(audit_details) == {
        "action", "credential_use", "entity_id", "policy_level", "profile_id",
        "profile_role", "project_id", "run_id", "source",
    }
    assert secret_value not in json.dumps(audit_details)
    assert str(secret_path) not in json.dumps(audit_details)
    assert callable(launch["run_cleanup_hook"])
    launch["run_cleanup_hook"]()
    assert not secret_path.parent.exists()


@pytest.mark.parametrize(("target_type", "target_value", "base_url", "allowed_host"), (
    ("domain", "scope-domain.example", "https://scope-domain.example/app", "scope-domain.example"),
    ("ip", "2001:db8::20", "https://[2001:db8::20]/app", "2001:db8::20"),
    ("url", "https://scope-url.example/app/page", "https://scope-url.example/app", "scope-url.example"),
))
def test_protected_probe_plan_shows_the_same_redacted_scope_for_each_web_target(
    client,
    target_type,
    target_value,
    base_url,
    allowed_host,
):
    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target = _create_target(
        client,
        token,
        project["id"],
        target_type=target_type,
        value=target_value,
    )
    profile_id, secret_value = _create_protected_http_profile(
        client,
        token,
        project["id"],
        target_value,
        base_url=base_url,
        allowed_host=allowed_host,
    )

    response = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers={"Authorization": f"Bearer {token}"},
        json={"action_id": "httpx", "entity_id": target["id"], "http_profile_id": profile_id},
    )

    assert response.status_code == 200
    profile = response.get_json()["plan"]["http_profile"]
    assert profile["role"] == "user"
    assert profile["scope"] == {
        "allowed_hosts": [allowed_host],
        "scope_roots": [base_url],
        "include_paths": ["/app"],
        "exclude_paths": ["/app/private"],
    }
    rendered = response.get_data(as_text=True)
    assert secret_value not in rendered
    assert "PROBE_HTTP_TOKEN" not in rendered


def test_ipv6_web_probe_plans_use_bracketed_urls_with_and_without_a_profile(client):
    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target_value = "2001:db8::21"
    target = _create_target(
        client,
        token,
        project["id"],
        target_type="ip",
        value=target_value,
    )
    profile_id, _secret_value = _create_protected_http_profile(
        client,
        token,
        project["id"],
        target_value,
        base_url=f"https://[{target_value}]/app",
        allowed_host=target_value,
    )
    route = f"/api/v1/projects/{project['id']}/probes/plan"
    headers = {"Authorization": f"Bearer {token}"}

    for action_id in ("curl", "httpx", "dalfox", "nuclei"):
        for protected in (False, True):
            response = client.post(
                route,
                headers=headers,
                json={
                    "action_id": action_id,
                    "entity_id": target["id"],
                    **({"http_profile_id": profile_id} if protected else {}),
                },
            )
            assert response.status_code == 200, (action_id, protected)
            command = response.get_json()["plan"]["display_command"]
            assert f"https://[{target_value}]" in command
            assert f"https://{target_value}" not in command


def test_protected_probe_rejects_stale_profile_and_cleans_failed_spawn(
    client,
    monkeypatch,
    tmp_path,
):
    from services.assessments import http_profile_runtime

    token = "tok_" + uuid.uuid4().hex
    _register_token(token)
    project = _create_project(client, token)
    target = _create_target(client, token, project["id"])
    profile_id, _secret_value = _create_protected_http_profile(
        client,
        token,
        project["id"],
        target["value"],
    )
    headers = {"Authorization": f"Bearer {token}"}
    plan_body = {
        "action_id": "httpx",
        "entity_id": target["id"],
        "http_profile_id": profile_id,
    }
    first = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=headers,
        json=plan_body,
    ).get_json()["plan"]
    updated = client.patch(
        f"/api/v1/projects/{project['id']}/http-profiles/{profile_id}",
        headers=headers,
        json={"rate_limit_per_second": 4, "revision": 1},
    )
    assert updated.status_code == 200
    monkeypatch.setattr("blueprints.api_v1.broker_available", lambda: True)
    stale = client.post(
        f"/api/v1/projects/{project['id']}/probes/run",
        headers=headers,
        json={
            **plan_body,
            "confirmed": True,
            "plan_digest": first["plan_digest"],
        },
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "stale_plan"

    current = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=headers,
        json=plan_body,
    ).get_json()["plan"]
    monkeypatch.setattr(http_profile_runtime, "_scanner_user_exists", lambda: False)
    monkeypatch.setattr(http_profile_runtime, "resolve_data_dir", lambda _cfg: str(tmp_path))
    material_paths = []

    def _failed_start(**kwargs):
        material_paths.append(Path(kwargs["trusted_execution_args"][1]).parent)
        raise RunSpawnError("spawn failed after protected materialization")

    monkeypatch.setattr("blueprints.api_v1._start_brokered_run_service", _failed_start)
    failed = client.post(
        f"/api/v1/projects/{project['id']}/probes/run",
        headers=headers,
        json={
            **plan_body,
            "confirmed": True,
            "plan_digest": current["plan_digest"],
        },
    )
    assert failed.status_code == 500
    assert failed.get_json()["error"]["code"] == "spawn_failed"
    assert len(material_paths) == 1
    assert not material_paths[0].exists()

    from services.assessments import probe_protected_launch
    from services.assessments.http_profile_target_scope import HttpProfileExecutionError
    from services.assessments.probe_contracts import ProbeError

    cleanup_calls = []
    protected = probe_protected_launch.ProtectedHttpLaunch(
        execution_command="httpx -u probe-route.example.com",
        trusted_execution_args=("-H", "Authorization: protected"),
        private_values=("Authorization: protected",),
        cleanup=lambda: cleanup_calls.append("cleaned"),
        audit_summary={},
    )
    monkeypatch.setattr(
        probe_protected_launch,
        "materialize_http_profile_launch",
        lambda *_args, **_kwargs: protected,
    )

    def _rejected_context(*_args, **_kwargs):
        raise HttpProfileExecutionError(
            "profile_scope_changed",
            "Profile scope changed after materialization.",
            status_code=409,
        )

    with pytest.raises(ProbeError, match="Profile scope changed") as exc_info:
        probe_protected_launch.materialize_probe_run_launch(
            token,
            project["id"],
            current,
            launch_context=_rejected_context,
        )
    assert exc_info.value.code == "profile_scope_changed"
    assert exc_info.value.status_code == 409
    assert cleanup_calls == ["cleaned"]
