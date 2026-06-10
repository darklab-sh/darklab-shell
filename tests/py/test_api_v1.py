import inspect
import json
import sqlite3
import stat
import sys
import uuid
from dataclasses import fields
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import app as shell_app
import config
import core.process as process
from core.database import DB_PATH
from services.scheduler.models import CADENCE_PRESETS, Schedule
from services.watchers.models import WATCHER_OPTION_DEFAULTS, Watcher, WatcherFire


ROOT_DIR = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT_DIR / "tools" / "darklab_cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


def get_client():
    shell_app.app.config["TESTING"] = True
    return shell_app.app.test_client()


def _token(client):
    return json.loads(client.get("/session/token/generate").data)["session_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_run(
    session_id: str,
    *,
    run_id: str | None = None,
    command: str = "echo api",
    output: str | list[str] = "ok",
    team_id: str = "",
) -> str:
    run_id = run_id or "api_run_" + session_id[-8:]
    output_lines = output if isinstance(output, list) else [str(output)]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, session_id, team_id, run_kind, command, started, finished, exit_code, output, output_preview, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated, output_search_text) "
            "VALUES (?, ?, ?, 'external', ?, '2026-05-19T00:00:00+00:00', "
            "'2026-05-19T00:00:01+00:00', 0, '', ?, 0, ?, 0, 0, ?)",
            (
                run_id,
                session_id,
                team_id,
                command,
                json.dumps([{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in output_lines]),
                len(output_lines),
                "\n".join(output_lines),
            ),
        )
        conn.commit()
    return run_id


def _ai_assist_count_for_run(run_id: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT COUNT(*) FROM ai_run_assists WHERE run_id = ?", (run_id,)).fetchone()
    return int(row[0] if row else 0)


def _audit_event_rows(*, target_id: str = "", event_type: str = "") -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[str] = []
    if target_id:
        where.append("target_id = ?")
        params.append(target_id)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT event_type, target_type, target_id, team_id, actor_member_id, actor_role, details "
            "FROM audit_events" + where_sql + " ORDER BY created, id",
            params,
        ).fetchall()
    return [
        {
            "event_type": row[0],
            "target_type": row[1],
            "target_id": row[2],
            "team_id": row[3],
            "actor_member_id": row[4],
            "actor_role": row[5],
            "details": json.loads(row[6] or "{}"),
        }
        for row in rows
    ]


def _create_project(client, token, *, name="API Project"):
    resp = client.post("/projects", json={"name": name}, headers={"X-Session-ID": token})
    assert resp.status_code == 201
    return json.loads(resp.data)["project"]


def _create_api_team(client, owner_token: str, *, name: str = "API Team") -> str:
    resp = client.post(
        "/api/v1/teams",
        headers=_headers(owner_token),
        json={"name": f"{name} {uuid.uuid4().hex[:8]}", "display_name": "API owner"},
    )
    assert resp.status_code == 201
    return str(json.loads(resp.data)["team"]["id"])


def _add_api_team_member(client, owner_token: str, member_token: str, team_id: str, *, role: str = "viewer") -> None:
    invite = client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=_headers(owner_token),
        json={"role": role, "label": f"API {role}"},
    )
    assert invite.status_code == 201
    joined = client.post(
        "/api/v1/teams/join",
        headers=_headers(member_token),
        json={"code": json.loads(invite.data)["invite"]["code"], "display_name": f"API {role}"},
    )
    assert joined.status_code == 201


def _team_headers(token: str, team_id: str) -> dict[str, str]:
    return {**_headers(token), "X-Team-ID": team_id}


_API_V1_TEAM_SCOPED_READ_ROUTES = (
    "api_history",
    "api_history_search",
    "api_atlas_summary",
    "api_atlas_runs",
    "api_atlas_entities",
    "api_atlas_entity",
    "api_atlas_findings",
    "api_atlas_finding",
    "api_history_run",
    "api_history_run_output",
    "api_history_run_artifacts",
    "api_history_run_artifact_download",
    "api_projects",
    "api_project",
    "api_project_findings",
    "api_project_runs",
    "api_project_entities",
    "api_project_packages",
    "api_schedules",
    "api_schedule",
    "api_schedule_fires",
    "api_watchers",
    "api_watcher",
    "api_watcher_fires",
    "api_notification_channels",
    "api_notification_events",
    "api_active_runs",
    "api_run_status",
    "api_run_wait",
    "api_run_ai_assists",
    "api_run_stream",
)


_API_V1_TEAM_SCOPED_WRITE_ROUTES = {
    "api_schedule_create": "Capability.MANAGE_AUTOMATION",
    "api_schedule_update": "Capability.MANAGE_AUTOMATION",
    "api_schedule_delete": "Capability.MANAGE_AUTOMATION",
    "api_schedule_run_now": "Capability.MANAGE_AUTOMATION",
    "api_watcher_create": "Capability.MANAGE_AUTOMATION",
    "api_watcher_update": "Capability.MANAGE_AUTOMATION",
    "api_watcher_delete": "Capability.MANAGE_AUTOMATION",
    "api_watcher_run_now": "Capability.MANAGE_AUTOMATION",
    "api_watcher_accept_baseline": "Capability.MANAGE_AUTOMATION",
    "api_notification_channel_create": "_require_notification_manage_scope(",
    "api_notification_channel_update": "_require_notification_manage_scope(",
    "api_notification_channel_delete": "_require_notification_manage_scope(",
    "api_notification_channel_test": "_require_notification_manage_scope(",
    "api_runs_start": "Capability.RUN_COMMANDS",
    "api_run_ai_summary": "Capability.RUN_COMMANDS",
    "api_run_ai_next_commands": "Capability.RUN_COMMANDS",
    "api_run_cancel": "Capability.RUN_COMMANDS",
    "api_run_project_link": "Capability.MUTATE_PROJECTS",
    "api_run_project_unlink": "Capability.MUTATE_PROJECTS",
}


_TEAM_MANAGEMENT_CAPABILITY_ROUTES = {
    ("blueprints.api_v1", "api_teams_update"): ("Capability.ARCHIVE_TEAM",),
    ("blueprints.api_v1", "api_teams_invites_create"): (
        "Capability.MANAGE_OWNERS",
        "Capability.MANAGE_INVITES",
    ),
    ("blueprints.api_v1", "api_teams_invites_revoke"): ("Capability.MANAGE_INVITES",),
    ("blueprints.api_v1", "api_teams_members_update"): (
        "Capability.MANAGE_OWNERS",
        "Capability.MANAGE_MEMBERS",
    ),
    ("blueprints.api_v1", "api_teams_members_remove"): (
        "Capability.MANAGE_OWNERS",
        "Capability.MANAGE_MEMBERS",
    ),
    ("blueprints.api_v1", "api_teams_recovery_rotate"): ("Capability.MANAGE_RECOVERY",),
    ("blueprints.teams", "session_teams_update"): ("Capability.ARCHIVE_TEAM",),
    ("blueprints.teams", "session_teams_invites_create"): (
        "Capability.MANAGE_OWNERS",
        "Capability.MANAGE_INVITES",
    ),
    ("blueprints.teams", "session_teams_invites_revoke"): ("Capability.MANAGE_INVITES",),
    ("blueprints.teams", "session_teams_members_update"): (
        "Capability.MANAGE_OWNERS",
        "Capability.MANAGE_MEMBERS",
    ),
    ("blueprints.teams", "session_teams_members_remove"): (
        "Capability.MANAGE_OWNERS",
        "Capability.MANAGE_MEMBERS",
    ),
    ("blueprints.teams", "session_teams_recovery_rotate"): ("Capability.MANAGE_RECOVERY",),
}


def test_api_v1_team_scoped_route_contracts_are_explicit():
    import blueprints.api_v1 as api_blueprint

    for route_name in _API_V1_TEAM_SCOPED_READ_ROUTES:
        source = inspect.getsource(getattr(api_blueprint, route_name))
        assert "_api_request_scope(" in source, route_name

    for route_name, capability_token in _API_V1_TEAM_SCOPED_WRITE_ROUTES.items():
        source = inspect.getsource(getattr(api_blueprint, route_name))
        assert "_api_request_scope(" in source or "_require_notification_manage_scope(" in source, route_name
        assert capability_token in source, route_name


def test_team_management_route_capability_contracts_are_explicit():
    for module_name, route_name in _TEAM_MANAGEMENT_CAPABILITY_ROUTES:
        module = import_module(module_name)
        source = inspect.getsource(getattr(module, route_name))
        assert "require_capability(" in source, route_name
        for capability_token in _TEAM_MANAGEMENT_CAPABILITY_ROUTES[(module_name, route_name)]:
            assert capability_token in source, route_name


def test_api_v1_rejects_missing_and_anonymous_auth():
    client = get_client()

    missing = client.get("/api/v1/whoami")
    anonymous = client.get(
        "/api/v1/whoami",
        headers={"X-Session-ID": "a1b2c3d4-0000-4000-8000-000000000001"},
    )

    assert missing.status_code == 401
    assert json.loads(missing.data)["error"]["code"] == "missing_token"
    assert anonymous.status_code == 401
    assert json.loads(anonymous.data)["error"]["code"] == "invalid_token"


def test_api_v1_rejects_revoked_token():
    client = get_client()
    token = _token(client)

    revoke = client.post("/session/token/revoke", json={"token": token}, headers={"X-Session-ID": token})
    resp = client.get("/api/v1/whoami", headers=_headers(token))

    assert revoke.status_code == 200
    assert resp.status_code == 401
    assert json.loads(resp.data)["error"]["code"] == "revoked_token"


def test_api_v1_whoami_accepts_bearer_token():
    from services.api_v1.auth import current_api_session

    client = get_client()
    token = _token(client)

    resp = client.get("/api/v1/whoami", headers=_headers(token))
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["token_created"]
    assert data["last_seen_at"]
    assert "session_id" not in data
    assert "tok_" not in json.dumps(data)
    assert "tok_" not in json.dumps(data["token_created"])
    assert "tok_" not in json.dumps(data["last_seen_at"])

    with shell_app.app.test_request_context("/api/v1/whoami", headers=_headers(token)):
        try:
            current_api_session()
        except RuntimeError as exc:
            assert "require_api_auth" in str(exc)
        else:
            raise AssertionError("current_api_session should require the auth decorator cache")


def test_api_v1_read_routes_use_api_rate_limit(monkeypatch):
    client = get_client()
    token = _token(client)
    remote_addr = f"198.51.100.{int(uuid.uuid4().hex[:2], 16)}"
    monkeypatch.setitem(shell_app.CFG, "rate_limit_per_minute", 1)
    monkeypatch.setitem(shell_app.CFG, "rate_limit_per_second", 1)

    first = client.get("/api/v1/whoami", headers=_headers(token), environ_base={"REMOTE_ADDR": remote_addr})
    second = client.get("/api/v1/whoami", headers=_headers(token), environ_base={"REMOTE_ADDR": remote_addr})

    assert first.status_code == 200
    assert second.status_code == 429
    assert json.loads(second.data)["error"]["code"] == "rate_limited"


def test_api_v1_team_routes_use_team_rate_limit_per_token(monkeypatch):
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    remote_addr = f"198.51.100.{int(uuid.uuid4().hex[:2], 16)}"
    monkeypatch.setitem(shell_app.CFG, "rate_limit_per_minute", 1000)
    monkeypatch.setitem(shell_app.CFG, "rate_limit_per_second", 1000)
    monkeypatch.setitem(shell_app.CFG, "team_read_rate_limit_per_minute", 1)
    monkeypatch.setitem(shell_app.CFG, "team_read_rate_limit_per_second", 100)
    monkeypatch.setitem(shell_app.CFG, "team_write_rate_limit_per_minute", 1000)

    first = client.get("/api/v1/teams", headers=_headers(token), environ_base={"REMOTE_ADDR": remote_addr})
    second = client.get("/api/v1/teams", headers=_headers(token), environ_base={"REMOTE_ADDR": remote_addr})
    other = client.get("/api/v1/teams", headers=_headers(other_token), environ_base={"REMOTE_ADDR": remote_addr})

    assert first.status_code == 200
    assert second.status_code == 429
    assert json.loads(second.data)["error"]["code"] == "rate_limited"
    assert other.status_code == 200


def test_api_v1_team_write_routes_use_separate_team_rate_limit(monkeypatch):
    client = get_client()
    token = _token(client)
    remote_addr = f"198.51.100.{int(uuid.uuid4().hex[:2], 16)}"
    monkeypatch.setitem(shell_app.CFG, "rate_limit_per_minute", 1000)
    monkeypatch.setitem(shell_app.CFG, "rate_limit_per_second", 1000)
    monkeypatch.setitem(shell_app.CFG, "team_read_rate_limit_per_minute", 1000)
    monkeypatch.setitem(shell_app.CFG, "team_read_rate_limit_per_second", 1000)
    monkeypatch.setitem(shell_app.CFG, "team_write_rate_limit_per_minute", 1)

    first = client.post(
        "/api/v1/teams",
        headers=_headers(token),
        json={"name": "Rate Team " + uuid.uuid4().hex[:8]},
        environ_base={"REMOTE_ADDR": remote_addr},
    )
    second = client.post(
        "/api/v1/teams",
        headers=_headers(token),
        json={"name": "Rate Team " + uuid.uuid4().hex[:8]},
        environ_base={"REMOTE_ADDR": remote_addr},
    )
    read_after_write = client.get("/api/v1/teams", headers=_headers(token), environ_base={"REMOTE_ADDR": remote_addr})

    assert first.status_code == 201
    assert second.status_code == 429
    assert json.loads(second.data)["error"]["code"] == "rate_limited"
    assert read_after_write.status_code == 200


def test_api_v1_history_is_token_scoped_and_uses_page_envelope():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(token, command="echo api scoped", output=["before", "api scoped output", "after"])
    _seed_run(other_token, command="echo other", output="api scoped output")

    resp = client.get("/api/v1/history?limit=10&offset=0&q=scoped", headers=_headers(token))
    search = client.get("/api/v1/history/search?q=scoped&context=1&limit=10", headers=_headers(token))
    missing_query = client.get("/api/v1/history/search", headers=_headers(token))
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert data["total"] >= 1
    assert any(item["id"] == run_id for item in data["runs"])
    assert all(item["command"] != "echo other" for item in data["runs"])
    assert search.status_code == 200
    search_data = json.loads(search.data)
    assert search_data["query"] == "scoped"
    assert search_data["context"] == 1
    assert search_data["matches"] == [{
        "run_id": run_id,
        "command": "echo api scoped",
        "started": "2026-05-19T00:00:00+00:00",
        "finished": "2026-05-19T00:00:01+00:00",
        "line_number": 2,
        "line": "api scoped output",
        "kind": "info",
        "role": "body",
        "signals": [],
        "entities": [],
        "context_before": ["before"],
        "context_after": ["after"],
    }]
    assert missing_query.status_code == 400
    assert json.loads(missing_query.data)["error"]["code"] == "missing_query"

    valid_since = client.get("/api/v1/history?since=2026-05-19T00:00:00Z", headers=_headers(token))
    invalid_since = client.get("/api/v1/history?since=last-week", headers=_headers(token))
    invalid_until = client.get("/api/v1/history?until=tomorrow", headers=_headers(token))

    assert valid_since.status_code == 200
    assert invalid_since.status_code == 400
    assert invalid_until.status_code == 400
    assert json.loads(invalid_since.data)["error"]["code"] == "invalid_since"
    assert json.loads(invalid_until.data)["error"]["code"] == "invalid_until"


def test_api_v1_history_honors_team_scope_header(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    member_token = _token(client)
    outsider_token = _token(client)
    team_resp = client.post(
        "/session/teams",
        headers={"X-Session-ID": token},
        json={"name": "API Scope Operators " + uuid.uuid4().hex[:8], "display_name": "API owner"},
    )
    team_id = json.loads(team_resp.data)["team"]["id"]
    invite = client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=_headers(token),
        json={"role": "operator", "label": "History teammate"},
    )
    join = client.post(
        "/api/v1/teams/join",
        headers=_headers(member_token),
        json={"code": json.loads(invite.data)["invite"]["code"], "display_name": "History teammate"},
    )
    personal_run_id = _seed_run(
        token,
        run_id="api-team-scope-personal",
        command="echo personal scope",
        output="personal scope output",
    )
    team_run_id = _seed_run(
        token,
        run_id="api-team-scope-team",
        command="echo team scope",
        output="team scope output",
        team_id=team_id,
    )

    personal = client.get("/api/v1/history?limit=20", headers=_headers(token))
    team = client.get("/api/v1/history?limit=20", headers={**_headers(token), "X-Team-ID": team_id})
    outsider = client.get(
        "/api/v1/history?limit=20",
        headers={**_headers(outsider_token), "X-Team-ID": team_id},
    )
    member_team = client.get("/api/v1/history?limit=20", headers={**_headers(member_token), "X-Team-ID": team_id})
    team_detail = client.get(
        f"/api/v1/history/{team_run_id}",
        headers={**_headers(token), "X-Team-ID": team_id},
    )
    member_detail = client.get(
        f"/api/v1/history/{team_run_id}",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    member_output = client.get(
        f"/api/v1/runs/{team_run_id}/output?format=json",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    member_search = client.get(
        "/api/v1/history/search?q=team%20scope&limit=20",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    member_status = client.get(
        f"/api/v1/runs/{team_run_id}",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    member_wait = client.post(
        f"/api/v1/runs/{team_run_id}/wait?timeout=0",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    monkeypatch.setattr(api_blueprint, "stream_run_events", lambda *_args, **_kwargs: iter(["data: allowed\n\n"]))
    member_stream = client.get(
        f"/api/v1/runs/{team_run_id}/stream",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    personal_detail_blocked = client.get(f"/api/v1/history/{team_run_id}", headers=_headers(token))

    assert team_resp.status_code == 201
    assert invite.status_code == 201
    assert join.status_code == 201
    assert personal.status_code == 200
    personal_ids = {item["id"] for item in json.loads(personal.data)["runs"]}
    assert personal_run_id in personal_ids
    assert team_run_id not in personal_ids
    assert team.status_code == 200
    team_ids = {item["id"] for item in json.loads(team.data)["runs"]}
    assert team_run_id in team_ids
    assert personal_run_id not in team_ids
    assert member_team.status_code == 200
    member_team_ids = {item["id"] for item in json.loads(member_team.data)["runs"]}
    assert team_run_id in member_team_ids
    assert personal_run_id not in member_team_ids
    assert outsider.status_code == 403
    assert json.loads(outsider.data)["error"]["code"] == "team_forbidden"
    assert team_detail.status_code == 200
    assert json.loads(team_detail.data)["run"]["id"] == team_run_id
    assert member_detail.status_code == 200
    assert json.loads(member_detail.data)["run"]["id"] == team_run_id
    assert member_output.status_code == 200
    assert json.loads(member_output.data)["lines"] == ["team scope output"]
    assert member_search.status_code == 200
    assert [item["run_id"] for item in json.loads(member_search.data)["matches"]] == [team_run_id]
    assert member_status.status_code == 200
    assert json.loads(member_status.data)["run"]["id"] == team_run_id
    assert member_wait.status_code == 200
    assert json.loads(member_wait.data)["run"]["id"] == team_run_id
    assert member_stream.status_code == 200
    assert member_stream.get_data(as_text=True) == "data: allowed\n\n"
    assert personal_detail_blocked.status_code == 404


def test_api_v1_team_viewers_cannot_run_commands_or_mutate_project_links(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    owner_token = _token(client)
    operator_token = _token(client)
    viewer_token = _token(client)
    team_resp = client.post(
        "/session/teams",
        headers={"X-Session-ID": owner_token},
        json={"name": "API Capability Operators " + uuid.uuid4().hex[:8], "display_name": "API owner"},
    )
    team_id = json.loads(team_resp.data)["team"]["id"]
    operator_invite = client.post(
        f"/session/teams/{team_id}/invites",
        headers={"X-Session-ID": owner_token},
        json={"role": "operator", "label": "API capability operator"},
    )
    viewer_invite = client.post(
        f"/session/teams/{team_id}/invites",
        headers={"X-Session-ID": owner_token},
        json={"role": "viewer", "label": "API capability viewer"},
    )
    assert client.post(
        "/session/teams/join",
        headers={"X-Session-ID": operator_token},
        json={"code": json.loads(operator_invite.data)["invite"]["code"], "display_name": "Operator"},
    ).status_code == 201
    assert client.post(
        "/session/teams/join",
        headers={"X-Session-ID": viewer_token},
        json={"code": json.loads(viewer_invite.data)["invite"]["code"], "display_name": "Viewer"},
    ).status_code == 201

    project_resp = client.post(
        "/projects",
        headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
        json={"name": "API Capability Review"},
    )
    project_id = json.loads(project_resp.data)["project"]["id"]
    run_id = _seed_run(
        owner_token,
        run_id="api-team-capability-run",
        command="httpx capability.example",
        output="team output",
        team_id=team_id,
    )
    monkeypatch.setattr(api_blueprint, "broker_available", lambda: True)
    monkeypatch.setattr(
        api_blueprint,
        "_start_brokered_run_service",
        mock.Mock(side_effect=AssertionError("viewer should be blocked before API run start")),
    )
    monkeypatch.setattr(
        api_blueprint,
        "active_runs_for_session",
        lambda *_args, **_kwargs: [{"run_id": "api-team-capability-active"}],
    )
    monkeypatch.setattr(api_blueprint, "pid_for_session", lambda *_args, **_kwargs: 1234)
    monkeypatch.setattr(
        api_blueprint,
        "_signal_process_group",
        mock.Mock(side_effect=AssertionError("viewer should be blocked before API run cancel")),
    )

    viewer_run = client.post(
        "/api/v1/runs",
        json={"command": "echo blocked"},
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
    )
    viewer_link = client.post(
        f"/api/v1/runs/{run_id}/projects/{project_id}",
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
    )
    viewer_cancel = client.post(
        "/api/v1/runs/api-team-capability-active/cancel",
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
    )
    operator_link = client.post(
        f"/api/v1/runs/{run_id}/projects/{project_id}",
        headers={**_headers(operator_token), "X-Team-ID": team_id},
    )

    assert team_resp.status_code == 201
    assert project_resp.status_code == 201
    assert viewer_run.status_code == 403
    assert json.loads(viewer_run.data)["error"]["code"] == "team_forbidden"
    assert viewer_link.status_code == 403
    assert json.loads(viewer_link.data)["error"]["code"] == "team_forbidden"
    assert viewer_cancel.status_code == 403
    assert json.loads(viewer_cancel.data)["error"]["code"] == "team_forbidden"
    assert operator_link.status_code == 201
    assert json.loads(operator_link.data)["link"]["entity_id"] == run_id


def test_api_v1_team_routes_manage_members_invites_and_recovery():
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    owner_token = _token(client)
    operator_token = _token(client)

    with mock.patch.object(api_blueprint.log, "info") as mock_info, \
         mock.patch.object(api_blueprint.log, "warning") as mock_warning:
        created = client.post(
            "/api/v1/teams",
            headers=_headers(owner_token),
            json={"name": "API Team " + uuid.uuid4().hex[:8], "display_name": "API owner"},
        )
        payload = json.loads(created.data)
        team_id = payload["team"]["id"]
        recovery_code = payload["recovery_code"]

        listed = client.get("/api/v1/teams", headers=_headers(owner_token))
        detail = client.get(f"/api/v1/teams/{team_id}", headers=_headers(owner_token))
        invite = client.post(
            f"/api/v1/teams/{team_id}/invites",
            headers=_headers(owner_token),
            json={"role": "operator", "label": "API operator"},
        )
        invite_payload = json.loads(invite.data)["invite"]
        joined = client.post(
            "/api/v1/teams/join",
            headers=_headers(operator_token),
            json={"code": invite_payload["code"], "display_name": "API operator"},
        )
        operator_member = next(
            item for item in json.loads(joined.data)["members"]
            if item["display_name"] == "API operator"
        )
        denied_owner_invite = client.post(
            f"/api/v1/teams/{team_id}/invites",
            headers=_headers(operator_token),
            json={"role": "owner"},
        )
        promoted = client.patch(
            f"/api/v1/teams/{team_id}/members/{operator_member['id']}",
            headers=_headers(owner_token),
            json={"role": "admin"},
        )
        revoked = client.delete(
            f"/api/v1/teams/{team_id}/invites/{invite_payload['id']}",
            headers=_headers(owner_token),
        )
        rotated = client.post(f"/api/v1/teams/{team_id}/recovery/rotate", headers=_headers(owner_token))
        rotated_code = json.loads(rotated.data)["recovery_code"]
        recovery_token = _token(client)
        recovered = client.post(
            "/api/v1/teams/recovery/redeem",
            headers=_headers(recovery_token),
            json={"code": rotated_code, "display_name": "Recovered owner"},
        )
        recovered_members = json.loads(recovered.data)["members"]
        recovered_owner = next(item for item in recovered_members if item["display_name"] == "Recovered owner")
        removed = client.delete(
            f"/api/v1/teams/{team_id}/members/{operator_member['id']}",
            headers=_headers(owner_token),
        )
        archived = client.patch(
            f"/api/v1/teams/{team_id}",
            headers=_headers(owner_token),
            json={"status": "archived"},
        )
        reactivated = client.patch(
            f"/api/v1/teams/{team_id}",
            headers=_headers(owner_token),
            json={"status": "active"},
        )
        left = client.post(f"/api/v1/teams/{team_id}/leave", headers=_headers(recovery_token))

    assert created.status_code == 201
    assert payload["team"]["member"]["role"] == "owner"
    assert "archive_team" in payload["team"]["member"]["capabilities"]
    assert recovery_code.startswith("trec_")
    assert listed.status_code == 200
    assert json.loads(listed.data)["teams"][0]["id"] == team_id
    assert detail.status_code == 200
    detail_payload = json.loads(detail.data)
    assert detail_payload["members"][0]["role"] == "owner"
    assert "manage_invites" in detail_payload["members"][0]["capabilities"]
    assert invite.status_code == 201
    assert invite_payload["code"].startswith("tinv_")
    assert joined.status_code == 201
    assert denied_owner_invite.status_code == 403
    assert json.loads(denied_owner_invite.data)["error"]["code"] == "team_forbidden"
    assert promoted.status_code == 200
    assert json.loads(promoted.data)["member"]["role"] == "admin"
    assert revoked.status_code == 200
    assert json.loads(revoked.data)["removed"] is True
    assert rotated.status_code == 200
    assert json.loads(rotated.data)["recovery_code"].startswith("trec_")
    assert recovered.status_code == 200
    assert recovered_owner["role"] == "owner"
    assert removed.status_code == 200
    assert json.loads(removed.data)["removed"] is True
    assert archived.status_code == 200
    assert json.loads(archived.data)["team"]["status"] == "archived"
    assert reactivated.status_code == 200
    assert json.loads(reactivated.data)["team"]["status"] == "active"
    assert left.status_code == 200
    assert json.loads(left.data)["removed"] is True
    team_actions = [
        call.kwargs["extra"]
        for call in mock_info.call_args_list
        if call.args and call.args[0] == "TEAM_ACTION"
    ]
    assert [event["action"] for event in team_actions] == [
        "create",
        "invite_create",
        "invite_redeem",
        "member_update",
        "invite_revoke",
        "recovery_rotate",
        "recovery_redeem",
        "member_remove",
        "update",
        "update",
        "leave",
    ]
    assert {event["source"] for event in team_actions} == {"api_v1"}
    assert team_actions[0]["team_id"] == team_id
    assert team_actions[0]["actor_member_id"] == payload["team"]["member"]["id"]
    assert team_actions[0]["actor_role"] == "owner"
    assert team_actions[3]["actor_member_id"] == payload["team"]["member"]["id"]
    assert team_actions[3]["target_member_id"] == operator_member["id"]
    assert team_actions[4]["target_invite_id"] == invite_payload["id"]
    audit_rows = _audit_event_rows(target_id=team_id)
    assert [row["event_type"] for row in audit_rows] == [
        "team.create",
        "team.invite",
        "team.join",
        "team.role_change",
        "team.revoke",
        "team.recovery_rotate",
        "team.recovery_redeem",
        "team.member_remove",
        "team.archive",
        "team.reactivate",
        "team.leave",
    ]
    assert {row["target_type"] for row in audit_rows} == {"team"}
    assert {row["details"]["source"] for row in audit_rows} == {"api_v1"}
    assert audit_rows[2]["details"]["kind"] == "invite"
    assert audit_rows[3]["details"] == {
        "source": "api_v1",
        "target_member_id": operator_member["id"],
        "from_role": "operator",
        "to_role": "admin",
    }
    assert audit_rows[6]["details"]["kind"] == "recovery"
    assert audit_rows[6]["details"]["target_member_id"] == recovered_owner["id"]
    assert audit_rows[7]["details"]["target_member_id"] == operator_member["id"]
    assert audit_rows[8]["details"]["status"] == "archived"
    assert audit_rows[9]["details"]["status"] == "active"
    assert audit_rows[10]["details"]["target_member_id"] == recovered_owner["id"]
    audit_rows_json = json.dumps(audit_rows)
    assert recovery_code not in audit_rows_json
    assert rotated_code not in audit_rows_json
    assert invite_payload["code"] not in audit_rows_json
    rejected = [
        call.kwargs["extra"]
        for call in mock_warning.call_args_list
        if call.args and call.args[0] == "TEAM_ACTION_REJECTED"
    ]
    assert [event["action"] for event in rejected] == ["invite_create"]
    assert rejected[0]["reason"] == "team_forbidden"
    assert rejected[0]["actor_role"] == "operator"

    with mock.patch.object(api_blueprint.log, "error") as mock_error, mock.patch(
        "services.teams.storage.rotate_team_recovery_code",
        side_effect=RuntimeError("recovery unavailable"),
    ):
        failed = client.post(
            "/api/v1/teams",
            headers=_headers(owner_token),
            json={"name": "API Team Rollback " + uuid.uuid4().hex[:8], "display_name": "API owner"},
        )
    assert failed.status_code == 500
    assert json.loads(failed.data)["error"]["code"] == "team_route_failed"
    assert mock_error.call_args.args[0] == "TEAM_ACTION_FAILED"
    assert mock_error.call_args.kwargs["exc_info"] is True
    error_extra = mock_error.call_args.kwargs["extra"]
    assert error_extra["action"] == "create"
    assert error_extra["status"] == 500
    assert team_actions[-1]["result"] == "ok"

    rollback_name = "API Rollback Team " + uuid.uuid4().hex[:8]
    rollback_slug = rollback_name.lower().replace(" ", "-")
    with mock.patch(
        "services.teams.storage.rotate_team_recovery_code",
        side_effect=api_blueprint.TeamError("recovery unavailable"),
    ):
        failed_create = client.post(
            "/api/v1/teams",
            headers=_headers(owner_token),
            json={"name": rollback_name, "display_name": "API owner"},
        )
    with sqlite3.connect(DB_PATH) as conn:
        team_count = conn.execute(
            "SELECT COUNT(*) FROM teams WHERE slug = ?",
            (rollback_slug,),
        ).fetchone()[0]
        member_count = conn.execute(
            "SELECT COUNT(*) FROM team_members WHERE team_id IN "
            "(SELECT id FROM teams WHERE slug = ?)",
            (rollback_slug,),
        ).fetchone()[0]
    assert failed_create.status_code == 400
    assert json.loads(failed_create.data)["error"]["code"] == "invalid_team_request"
    assert team_count == 0
    assert member_count == 0


def test_api_v1_archived_team_rejects_invite_and_recovery_redeem():
    client = get_client()
    owner_token = _token(client)
    invited_token = _token(client)
    recovery_token = _token(client)

    created = client.post(
        "/api/v1/teams",
        headers=_headers(owner_token),
        json={"name": "Archived API Team " + uuid.uuid4().hex[:8], "display_name": "API owner"},
    )
    payload = json.loads(created.data)
    team_id = payload["team"]["id"]
    recovery_code = payload["recovery_code"]
    invite = client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=_headers(owner_token),
        json={"role": "operator", "label": "Archived API operator"},
    )
    invite_code = json.loads(invite.data)["invite"]["code"]
    archived = client.patch(
        f"/api/v1/teams/{team_id}",
        headers=_headers(owner_token),
        json={"status": "archived"},
    )

    invited_join = client.post(
        "/api/v1/teams/join",
        headers=_headers(invited_token),
        json={"code": invite_code, "display_name": "Late API operator"},
    )
    recovery_join = client.post(
        "/api/v1/teams/recovery/redeem",
        headers=_headers(recovery_token),
        json={"code": recovery_code, "display_name": "Late API owner"},
    )
    scoped_run = client.post(
        "/api/v1/runs",
        headers={**_headers(owner_token), "X-Team-ID": team_id},
        json={"command": "echo archived"},
    )
    blocked_invite = client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=_headers(owner_token),
        json={"role": "operator", "label": "Blocked archived API invite"},
    )
    blocked_recovery_rotate = client.post(
        f"/api/v1/teams/{team_id}/recovery/rotate",
        headers=_headers(owner_token),
    )

    assert created.status_code == 201
    assert invite.status_code == 201
    assert archived.status_code == 200
    assert scoped_run.status_code == 409
    assert json.loads(scoped_run.data)["error"]["code"] == "team_archived"
    assert "archived" in json.loads(scoped_run.data)["error"]["message"]
    assert blocked_invite.status_code == 409
    assert json.loads(blocked_invite.data)["error"]["code"] == "team_archived"
    assert "archived" in json.loads(blocked_invite.data)["error"]["message"]
    assert blocked_recovery_rotate.status_code == 409
    assert json.loads(blocked_recovery_rotate.data)["error"]["code"] == "team_archived"
    assert "archived" in json.loads(blocked_recovery_rotate.data)["error"]["message"]
    assert invited_join.status_code == 409
    assert json.loads(invited_join.data)["error"]["code"] == "team_archived"
    assert "archived" in json.loads(invited_join.data)["error"]["message"]
    assert recovery_join.status_code == 409
    assert json.loads(recovery_join.data)["error"]["code"] == "team_archived"
    assert "archived" in json.loads(recovery_join.data)["error"]["message"]


def test_api_v1_team_project_readers_include_cross_member_entities_and_findings():
    client = get_client()
    owner_token = _token(client)
    operator_token = _token(client)
    team_resp = client.post(
        "/session/teams",
        headers={"X-Session-ID": owner_token},
        json={"name": "API Cross Project " + uuid.uuid4().hex[:8], "display_name": "API owner"},
    )
    team_id = json.loads(team_resp.data)["team"]["id"]
    invite_resp = client.post(
        f"/session/teams/{team_id}/invites",
        headers={"X-Session-ID": owner_token},
        json={"role": "operator", "label": "API cross operator"},
    )
    join_resp = client.post(
        "/session/teams/join",
        headers={"X-Session-ID": operator_token},
        json={"code": json.loads(invite_resp.data)["invite"]["code"], "display_name": "API operator"},
    )
    project_resp = client.post(
        "/projects",
        headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
        json={"name": "API Cross Member Project"},
    )
    project_id = json.loads(project_resp.data)["project"]["id"]
    suffix = uuid.uuid4().hex[:12]
    run_id = "api-team-cross-project-run-" + suffix
    entity_id = "ent_api_team_cross_" + suffix
    finding_id = "fnd_api_team_cross_" + suffix
    seen_at = "2026-05-28T14:30:00+00:00"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
            "output_preview, output_line_count, output_search_text) "
            "VALUES (?, ?, ?, 'external', 'httpx api-cross.example', ?, ?, 0, '[]', 0, '')",
            (run_id, owner_token, team_id, seen_at, seen_at),
        )
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
            "VALUES (?, ?, 'domain', 'api-cross.example', ?, ?, ?, ?)",
            (entity_id, owner_token, "sig_" + entity_id, seen_at, seen_at, seen_at),
        )
        conn.execute(
            "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
            "VALUES (?, ?, ?, ?, 1)",
            (entity_id, run_id, seen_at, seen_at),
        )
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
            "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created) "
            "VALUES (?, ?, ?, ?, ?, ?, 'high', 'finding', 'httpx', ?, ?, ?, ?, 1, 'new', ?, ?, ?)",
            (
                finding_id,
                owner_token,
                run_id,
                entity_id,
                entity_id,
                "sig_" + finding_id,
                run_id,
                run_id,
                seen_at,
                seen_at,
                "API cross-member finding",
                "API cross-member finding",
                seen_at,
            ),
        )
        conn.execute(
            "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
            "VALUES (?, ?, 1, 'API cross-member finding', ?)",
            (finding_id, run_id, seen_at),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'manual', ?)",
            ("plr_api_team_cross_" + suffix, project_id, run_id, seen_at),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', ?)",
            ("ple_api_team_cross_" + suffix, project_id, entity_id, seen_at),
        )
        conn.commit()

    headers = {**_headers(operator_token), "X-Team-ID": team_id}
    projects = client.get("/api/v1/projects?limit=20", headers=headers)
    entities = client.get(f"/api/v1/projects/{project_id}/entities?entity_type=domain", headers=headers)
    findings = client.get(f"/api/v1/projects/{project_id}/findings", headers=headers)
    personal_projects = client.get("/api/v1/projects?limit=20", headers=_headers(operator_token))

    assert team_resp.status_code == 201
    assert join_resp.status_code == 201
    assert project_resp.status_code == 201
    assert projects.status_code == 200
    project_payload = next(item for item in json.loads(projects.data)["projects"] if item["id"] == project_id)
    assert project_payload["counts"]["entities"] == 1
    assert project_payload["counts"]["findings"] == 1
    assert project_payload["finding_summary"]["severities"] == {"high": 1}
    assert entities.status_code == 200
    assert [item["id"] for item in json.loads(entities.data)["entities"]] == [entity_id]
    assert findings.status_code == 200
    assert [item["id"] for item in json.loads(findings.data)["findings"]] == [finding_id]
    assert json.loads(personal_projects.data)["projects"] == []


def test_api_v1_history_detail_output_and_cross_session_404():
    import blueprints.history as history_blueprint
    from services.runs.structured_summary import replace_run_output_summary

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(token, output=["line one", "line two", "line three"])
    with sqlite3.connect(DB_PATH) as conn:
        structured_preview = [
            {"text": "line one", "cls": "", "tsC": "", "tsE": "", "kind": "info", "role": "body"},
            {
                "text": "line two",
                "cls": "",
                "tsC": "",
                "tsE": "",
                "kind": "error",
                "role": "body",
                "signals": ["findings"],
                "entities": [{"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"}],
            },
            {
                "text": "line three",
                "cls": "",
                "tsC": "",
                "tsE": "",
                "kind": "warn",
                "role": "body",
                "entities": [{"type": "url", "value": "https://darklab.sh", "canonical_value": "https://darklab.sh"}],
            },
        ]
        conn.execute(
            "UPDATE runs SET output_preview = ?, output_search_text = ? WHERE id = ?",
            (
                json.dumps(structured_preview),
                "line one\nline two\nline three",
                run_id,
            ),
        )
        replace_run_output_summary(conn, run_id, structured_preview)
        domain_entity_id = "ent_" + uuid.uuid4().hex[:16]
        url_entity_id = "ent_" + uuid.uuid4().hex[:16]
        for entity_id, entity_type, canonical_value in (
            (domain_entity_id, "domain", "darklab.sh"),
            (url_entity_id, "url", "https://darklab.sh"),
        ):
            conn.execute(
                "INSERT INTO entities "
                "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                "VALUES (?, ?, ?, ?, ?, '2026-05-19T00:00:00+00:00', "
                "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00')",
                (entity_id, token, entity_type, canonical_value, "sig_" + entity_id),
            )
            conn.execute(
                "INSERT INTO entity_run_links "
                "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                "VALUES (?, ?, '2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00', 1)",
                (entity_id, run_id),
            )
        conn.execute(
            "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
            "VALUES (?, ?, 'run', ?, 'baseline', 'manual', '2026-05-19T00:00:00+00:00')",
            ("lbl_" + uuid.uuid4().hex[:16], token, run_id),
        )
        conn.execute(
            "INSERT INTO entity_notes (id, session_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, ?, 'run', ?, 'private note', '2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00')",
            ("note_" + uuid.uuid4().hex[:16], token, run_id),
        )
        conn.commit()

    detail = client.get(f"/api/v1/history/{run_id}", headers=_headers(token))
    output = client.get(f"/api/v1/history/{run_id}/output", headers=_headers(token))
    output_json = client.get(f"/api/v1/history/{run_id}/output?format=json", headers=_headers(token))
    output_range = client.get(f"/api/v1/runs/{run_id}/output?range=2-3&format=json", headers=_headers(token))
    output_structured = client.get(
        f"/api/v1/runs/{run_id}/output?kind=error&entity=darklab.sh&format=json",
        headers=_headers(token),
    )
    output_entity_type = client.get(
        f"/api/v1/runs/{run_id}/output?entity_type=url&not_kind=info&format=json",
        headers=_headers(token),
    )
    structured_history = client.get("/api/v1/history?q=signal:findings", headers=_headers(token))
    structured_entity_history = client.get("/api/v1/history?q=entity_type:url", headers=_headers(token))
    structured_search = client.get("/api/v1/history/search?q=signal:findings", headers=_headers(token))
    structured_type_search = client.get(
        "/api/v1/history/search?q=kind%21%3Dinfo&entity_type=url",
        headers=_headers(token),
    )
    with mock.patch.object(
        history_blueprint,
        "load_run_output_events_for_run",
        side_effect=AssertionError("summary-backed history filters should not load transcript events"),
    ):
        browser_entity_history = client.get("/history?q=entity_type:url", headers={"X-Session-ID": token})
        browser_kind_history = client.get("/history?q=kind:error", headers={"X-Session-ID": token})
    invalid_range = client.get(f"/api/v1/runs/{run_id}/output?range=3-2", headers=_headers(token))
    cross_session = client.get(f"/api/v1/history/{run_id}", headers=_headers(other_token))

    assert detail.status_code == 200
    detail_run = json.loads(detail.data)["run"]
    assert detail_run["id"] == run_id
    assert detail_run["label_count"] == 1
    assert detail_run["note_count"] == 1
    assert output.status_code == 200
    assert "line one" in output.get_data(as_text=True)
    assert json.loads(output_json.data)["lines"] == ["line one", "line two", "line three"]
    assert json.loads(output_range.data)["lines"] == ["line two", "line three"]
    assert json.loads(output_range.data)["range"] == {"start": 2, "end": 3, "returned": 2}
    assert json.loads(output_structured.data)["lines"] == ["line two"]
    assert json.loads(output_structured.data)["entries"][0]["kind"] == "error"
    assert json.loads(output_entity_type.data)["lines"] == ["line three"]
    assert [item["id"] for item in json.loads(structured_history.data)["runs"]] == [run_id]
    assert [item["id"] for item in json.loads(structured_entity_history.data)["runs"]] == [run_id]
    assert [item["id"] for item in json.loads(browser_entity_history.data)["runs"]] == [run_id]
    assert [item["id"] for item in json.loads(browser_kind_history.data)["runs"]] == [run_id]
    structured_matches = json.loads(structured_search.data)["matches"]
    assert [(item["line_number"], item["kind"], item["signals"]) for item in structured_matches] == [(2, "error", ["findings"])]
    assert [item["line_number"] for item in json.loads(structured_type_search.data)["matches"]] == [3]
    assert invalid_range.status_code == 400
    assert json.loads(invalid_range.data)["error"]["code"] == "invalid_range"
    assert cross_session.status_code == 404


def test_api_v1_ai_summary_routes_are_token_scoped(monkeypatch):
    from services.ai import assists as ai_assists

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(
        token,
        command="nmap -sV darklab.sh",
        output=[
            "Starting scan for darklab.sh with enough context for a summary.",
            "443/tcp open https and 80/tcp open http were detected.",
            "Inspect TLS and response headers next if the operator wants more detail.",
        ],
    )
    guard_run_id = _seed_run(
        token,
        run_id="api_ai_guard_" + uuid.uuid4().hex[:8],
        command="nmap darklab.sh",
        output=[
            "Starting scan for darklab.sh with enough useful context for route guards.",
            "443/tcp open https and 80/tcp open http were detected.",
            "Inspect TLS and response headers next if the operator wants more detail.",
        ],
    )
    no_context_run_id = _seed_run(
        token,
        run_id="api_ai_empty_" + uuid.uuid4().hex[:8],
        command="true",
        output="ok",
    )

    monkeypatch.setitem(config.CFG, "ai_enabled", True)
    monkeypatch.setitem(config.CFG, "ai_feature_summary", True)
    monkeypatch.setitem(config.CFG, "ai_feature_next_commands", True)
    monkeypatch.setitem(config.CFG, "ai_model", "llama3.1:8b")
    monkeypatch.setitem(config.CFG, "ai_max_input_chars", 8000)
    monkeypatch.setitem(config.CFG, "ai_max_queue_depth", 1000)
    monkeypatch.setitem(config.CFG, "ai_rate_limit_per_session_hour", 1)
    monkeypatch.setitem(config.CFG, "ai_rate_limit_global_per_minute", 20)
    monkeypatch.setitem(config.CFG, "diagnostics_allowed_cidrs", ["127.0.0.1/32"])
    monkeypatch.setitem(config.CFG, "share_redaction_enabled", False)
    monkeypatch.setattr(process, "redis_client", process._FakeRedisClient())

    queued = client.post(f"/api/v1/runs/{run_id}/ai-summary", json={}, headers=_headers(token))
    suggested = client.post(f"/api/v1/runs/{run_id}/ai-next-commands", json={}, headers=_headers(token))
    listed = client.get(f"/api/v1/runs/{run_id}/ai-assists", headers=_headers(token))
    cross = client.post(f"/api/v1/runs/{run_id}/ai-summary", json={}, headers=_headers(other_token))
    invalid_body = client.post(f"/api/v1/runs/{guard_run_id}/ai-summary", json=[], headers=_headers(token))

    base_guard_cfg = {
        "ai_enabled": True,
        "ai_feature_summary": True,
        "ai_feature_next_commands": True,
        "ai_model": "llama3.1:8b",
        "ai_max_input_chars": 8000,
        "ai_max_queue_depth": 1000,
        "ai_rate_limit_per_session_hour": 20,
        "ai_rate_limit_global_per_minute": 20,
        "diagnostics_allowed_cidrs": [],
        "share_redaction_enabled": False,
    }
    guard_cases = []
    for cfg_patch, path, expected_status, expected_error in (
        ({"ai_enabled": False}, f"/api/v1/runs/{guard_run_id}/ai-summary", 403, "ai_disabled"),
        ({"ai_feature_summary": False}, f"/api/v1/runs/{guard_run_id}/ai-summary", 403, "ai_feature_disabled"),
        (
            {"ai_feature_next_commands": False},
            f"/api/v1/runs/{guard_run_id}/ai-next-commands",
            403,
            "ai_feature_disabled",
        ),
    ):
        with mock.patch.dict(config.CFG, {**base_guard_cfg, **cfg_patch}, clear=False), \
             mock.patch.object(process, "redis_client", process._FakeRedisClient()):
            guard_cases.append((expected_status, expected_error, client.post(path, json={}, headers=_headers(token))))
    busy_lock = mock.MagicMock()
    busy_lock.__enter__.return_value = False
    busy_lock.__exit__.return_value = False
    with mock.patch.dict(config.CFG, base_guard_cfg, clear=False), \
         mock.patch.object(process, "redis_client", process._FakeRedisClient()), \
         mock.patch.object(ai_assists, "enqueue_lock", return_value=busy_lock):
        guard_cases.append((429, "ai_busy", client.post(
            f"/api/v1/runs/{guard_run_id}/ai-summary",
            json={},
            headers=_headers(token),
        )))
    with mock.patch.dict(config.CFG, base_guard_cfg, clear=False), \
         mock.patch.object(process, "redis_client", None):
        guard_cases.append((503, "ai_unavailable", client.post(
            f"/api/v1/runs/{guard_run_id}/ai-summary",
            json={},
            headers=_headers(token),
        )))
    with mock.patch.dict(config.CFG, {**base_guard_cfg, "ai_rate_limit_per_session_hour": 1}, clear=False), \
         mock.patch.object(process, "redis_client", process._FakeRedisClient()):
        rate_first = client.post(f"/api/v1/runs/{guard_run_id}/ai-summary", json={}, headers=_headers(token))
        rate_limited = client.post(f"/api/v1/runs/{guard_run_id}/ai-summary", json={}, headers=_headers(token))
    with mock.patch.dict(config.CFG, base_guard_cfg, clear=False), \
         mock.patch.object(process, "redis_client", process._FakeRedisClient()), \
         mock.patch.object(ai_assists, "build_run_context", return_value=mock.Mock(useful=False)):
        no_context = client.post(f"/api/v1/runs/{no_context_run_id}/ai-summary", json={}, headers=_headers(token))

    queued_payload = json.loads(queued.data)
    suggested_payload = json.loads(suggested.data)
    listed_payload = json.loads(listed.data)
    assert queued.status_code == 202
    assert queued_payload["assist"]["status"] == "queued"
    assert queued_payload["assist"]["variant"] == "summary"
    assert suggested.status_code == 202
    assert suggested_payload["assist"]["status"] == "queued"
    assert suggested_payload["assist"]["variant"] == "next_commands"
    assert listed.status_code == 200
    assert {assist["id"] for assist in listed_payload["assists"]} == {
        queued_payload["assist"]["id"],
        suggested_payload["assist"]["id"],
    }
    assert cross.status_code == 404
    assert json.loads(cross.data)["error"]["code"] == "not_found"
    assert invalid_body.status_code == 400
    assert json.loads(invalid_body.data)["error"]["code"] == "invalid_body"
    for expected_status, expected_error, response in guard_cases:
        assert response.status_code == expected_status
        assert json.loads(response.data)["error"]["code"] == expected_error
    assert rate_first.status_code == 202
    assert rate_limited.status_code == 429
    assert json.loads(rate_limited.data)["error"]["code"] == "ai_rate_limited"
    assert no_context.status_code == 422
    assert json.loads(no_context.data)["error"]["code"] == "ai_no_context"
    assert _ai_assist_count_for_run(no_context_run_id) == 0
    assert _ai_assist_count_for_run(guard_run_id) == 1


def test_api_v1_ai_assists_honor_team_scope(monkeypatch):
    client = get_client()
    owner_token = _token(client)
    viewer_token = _token(client)
    team_resp = client.post(
        "/session/teams",
        headers={"X-Session-ID": owner_token},
        json={"name": "API AI Operators " + uuid.uuid4().hex[:8], "display_name": "API owner"},
    )
    team_id = json.loads(team_resp.data)["team"]["id"]
    invite_resp = client.post(
        f"/session/teams/{team_id}/invites",
        headers={"X-Session-ID": owner_token},
        json={"role": "viewer", "label": "API AI viewer"},
    )
    join_resp = client.post(
        "/session/teams/join",
        headers={"X-Session-ID": viewer_token},
        json={"code": json.loads(invite_resp.data)["invite"]["code"], "display_name": "API viewer"},
    )
    run_id = _seed_run(
        owner_token,
        run_id="api-team-ai-assist-" + uuid.uuid4().hex[:8],
        command="nmap -sV darklab.sh",
        output=[
            "Starting scan for darklab.sh with enough context for a team summary.",
            "443/tcp open https and 80/tcp open http were detected.",
            "Inspect TLS and response headers next if the operator wants more detail.",
        ],
        team_id=team_id,
    )

    monkeypatch.setitem(config.CFG, "ai_enabled", True)
    monkeypatch.setitem(config.CFG, "ai_feature_summary", True)
    monkeypatch.setitem(config.CFG, "ai_feature_next_commands", True)
    monkeypatch.setitem(config.CFG, "ai_model", "llama3.1:8b")
    monkeypatch.setitem(config.CFG, "ai_max_input_chars", 8000)
    monkeypatch.setitem(config.CFG, "ai_rate_limit_per_session_hour", 20)
    monkeypatch.setitem(config.CFG, "ai_rate_limit_global_per_minute", 20)
    monkeypatch.setitem(config.CFG, "ai_max_queue_depth", 1000)
    monkeypatch.setitem(config.CFG, "share_redaction_enabled", False)
    monkeypatch.setattr(process, "redis_client", process._FakeRedisClient())

    queued = client.post(
        f"/api/v1/runs/{run_id}/ai-summary",
        json={},
        headers={**_headers(owner_token), "X-Team-ID": team_id},
    )
    listed = client.get(
        f"/api/v1/runs/{run_id}/ai-assists",
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
    )
    viewer_summary = client.post(
        f"/api/v1/runs/{run_id}/ai-summary",
        json={},
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
    )
    viewer_next = client.post(
        f"/api/v1/runs/{run_id}/ai-next-commands",
        json={},
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
    )
    personal_blocked = client.get(f"/api/v1/runs/{run_id}/ai-assists", headers=_headers(owner_token))

    queued_payload = json.loads(queued.data)
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT session_id, team_id FROM ai_run_assists WHERE id = ?",
            (queued_payload["assist"]["id"],),
        ).fetchone()

    assert team_resp.status_code == 201
    assert join_resp.status_code == 201
    assert queued.status_code == 202
    assert row == (owner_token, team_id)
    assert listed.status_code == 200
    assert [item["id"] for item in json.loads(listed.data)["assists"]] == [queued_payload["assist"]["id"]]
    for response in (viewer_summary, viewer_next):
        assert response.status_code == 403
        assert json.loads(response.data)["error"]["code"] == "team_forbidden"
    assert personal_blocked.status_code == 404
    assert json.loads(personal_blocked.data)["error"]["code"] == "not_found"


def test_api_v1_artifact_list_and_download_are_token_scoped(monkeypatch, tmp_path):
    from services.teams.scope import team_owner_context
    from services.workspace.files import ensure_session_workspace, resolve_owner_workspace_path

    client = get_client()
    token = _token(client)
    member_token = _token(client)
    other_token = _token(client)
    team_resp = client.post(
        "/session/teams",
        headers={"X-Session-ID": token},
        json={"name": "API Artifact Operators " + uuid.uuid4().hex[:8], "display_name": "Artifact owner"},
    )
    team_id = json.loads(team_resp.data)["team"]["id"]
    invite = client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=_headers(token),
        json={"role": "operator", "label": "Artifact teammate"},
    )
    join = client.post(
        "/api/v1/teams/join",
        headers=_headers(member_token),
        json={"code": json.loads(invite.data)["invite"]["code"], "display_name": "Artifact teammate"},
    )
    run_id = _seed_run(token, command="echo artifact", output="artifact")
    team_run_id = _seed_run(
        token,
        run_id="api_team_artifact_" + uuid.uuid4().hex[:8],
        command="echo team artifact",
        output="team artifact",
        team_id=team_id,
    )
    artifact_id = "rfa_" + uuid.uuid4().hex[:16]
    team_artifact_id = "rfa_" + uuid.uuid4().hex[:16]
    monkeypatch.setitem(shell_app.CFG, "workspace_enabled", True)
    monkeypatch.setitem(shell_app.CFG, "workspace_backend", "tmpfs")
    monkeypatch.setitem(shell_app.CFG, "workspace_root", str(tmp_path))
    monkeypatch.setitem(shell_app.CFG, "workspace_quota_mb", 1)
    monkeypatch.setitem(shell_app.CFG, "workspace_max_file_mb", 1)
    monkeypatch.setitem(shell_app.CFG, "workspace_max_files", 10)
    workspace_dir = ensure_session_workspace(token, shell_app.CFG)
    (workspace_dir / "reports").mkdir()
    (workspace_dir / "reports" / "artifact.txt").write_text("artifact body", encoding="utf-8")
    (workspace_dir / "reports" / "team-artifact.txt").write_text("personal shadow body", encoding="utf-8")
    team_artifact_path = resolve_owner_workspace_path(
        team_owner_context(team_id, actor_session_id=token),
        "reports/team-artifact.txt",
        shell_app.CFG,
        ensure_parent=True,
    )
    team_artifact_path.write_text("team artifact body", encoding="utf-8")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
            "VALUES (?, ?, ?, 'reports/artifact.txt', 'artifact.txt', 'output', 13, 'test', "
            "'2026-05-19T00:00:01+00:00')",
            (artifact_id, token, run_id),
        )
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
            "VALUES (?, ?, ?, 'reports/team-artifact.txt', 'team-artifact.txt', 'output', 18, 'test', "
            "'2026-05-19T00:00:02+00:00')",
            (team_artifact_id, token, team_run_id),
        )
        conn.commit()

    owner_list = client.get(f"/api/v1/history/{run_id}/artifacts", headers=_headers(token))
    cross_list = client.get(f"/api/v1/history/{run_id}/artifacts", headers=_headers(other_token))
    team_list = client.get(
        f"/api/v1/history/{team_run_id}/artifacts",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    team_scope_personal_list = client.get(
        f"/api/v1/history/{run_id}/artifacts",
        headers={**_headers(token), "X-Team-ID": team_id},
    )
    owner_download = client.get(f"/api/v1/history/{run_id}/artifacts/{artifact_id}", headers=_headers(token))
    cross_download = client.get(f"/api/v1/history/{run_id}/artifacts/{artifact_id}", headers=_headers(other_token))
    team_download = client.get(
        f"/api/v1/history/{team_run_id}/artifacts/{team_artifact_id}",
        headers={**_headers(member_token), "X-Team-ID": team_id},
    )
    team_scope_personal_download = client.get(
        f"/api/v1/history/{run_id}/artifacts/{artifact_id}",
        headers={**_headers(token), "X-Team-ID": team_id},
    )
    personal_scope_team_download = client.get(
        f"/api/v1/history/{team_run_id}/artifacts/{team_artifact_id}",
        headers=_headers(token),
    )

    assert team_resp.status_code == 201
    assert join.status_code == 201
    assert owner_list.status_code == 200
    assert json.loads(owner_list.data)["artifacts"][0]["id"] == artifact_id
    assert cross_list.status_code == 404
    assert team_list.status_code == 200
    assert json.loads(team_list.data)["artifacts"][0]["id"] == team_artifact_id
    assert team_scope_personal_list.status_code == 404
    assert owner_download.status_code == 200
    assert owner_download.data == b"artifact body"
    assert cross_download.status_code == 404
    assert team_download.status_code == 200
    assert team_download.data == b"team artifact body"
    assert team_scope_personal_download.status_code == 404
    assert personal_scope_team_download.status_code == 404


def test_api_v1_artifact_download_rejects_cross_run_artifact_id():
    client = get_client()
    token = _token(client)
    run_id = _seed_run(token, command="echo first", output="first")
    other_run_id = "api_run_other_" + uuid.uuid4().hex[:8]
    artifact_id = "rfa_" + uuid.uuid4().hex[:16]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, session_id, run_kind, command, started, finished, exit_code, output, output_preview, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated, output_search_text) "
            "VALUES (?, ?, 'external', 'echo second', '2026-05-19T00:00:00+00:00', "
            "'2026-05-19T00:00:01+00:00', 0, '', '[]', 0, 0, 0, 0, '')",
            (other_run_id, token),
        )
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
            "VALUES (?, ?, ?, 'reports/second.txt', 'second.txt', 'output', 12, 'test', '2026-05-19T00:00:01+00:00')",
            (artifact_id, token, other_run_id),
        )
        conn.commit()

    resp = client.get(f"/api/v1/history/{run_id}/artifacts/{artifact_id}", headers=_headers(token))

    assert resp.status_code == 404
    assert json.loads(resp.data)["error"]["code"] == "not_found"


def test_api_v1_project_readers_are_token_scoped():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="Scoped API Project")
    run_id = _seed_run(token, command="echo project api", output="project api")
    entity_id = "ent_" + uuid.uuid4().hex[:16]
    finding_id = "fnd_" + uuid.uuid4().hex[:16]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO evidence_packages "
            "(id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated) "
            "VALUES (?, ?, ?, 'API Package', '', 'redacted', 0, '{}', 'draft', "
            "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00')",
            ("pkg_" + uuid.uuid4().hex[:16], token, project["id"]),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'manual', '2026-05-19T00:00:00+00:00')",
            ("plr_" + uuid.uuid4().hex[:16], project["id"], run_id),
        )
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, occurrence_count, created) "
            "VALUES (?, ?, 'domain', 'api.darklab.sh', ?, "
            "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00', 2, '2026-05-19T00:00:00+00:00')",
            (entity_id, token, "sig_" + uuid.uuid4().hex),
        )
        conn.execute(
            "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
            "VALUES (?, ?, '2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00', 2)",
            (entity_id, run_id),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', '2026-05-19T00:00:00+00:00')",
            ("ple_" + uuid.uuid4().hex[:16], project["id"], entity_id),
        )
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
            "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created) "
            "VALUES (?, ?, ?, ?, 'api.darklab.sh', ?, 'medium', 'finding', 'nmap', ?, ?, "
            "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:01+00:00', 1, 'new', "
            "'API finding', 'open port', '2026-05-19T00:00:01+00:00')",
            (finding_id, token, run_id, entity_id, "sig_" + uuid.uuid4().hex, run_id, run_id),
        )
        conn.execute(
            "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
            "VALUES (?, ?, 2, 'open port', '2026-05-19T00:00:01+00:00')",
            (finding_id, run_id),
        )
        conn.commit()

    owner_project = client.get(f"/api/v1/projects/{project['id']}", headers=_headers(token))
    owner_findings = client.get(f"/api/v1/projects/{project['id']}/findings", headers=_headers(token))
    owner_runs = client.get(f"/api/v1/projects/{project['id']}/runs", headers=_headers(token))
    owner_entities = client.get(f"/api/v1/projects/{project['id']}/entities?entity_type=domain", headers=_headers(token))
    owner_packages = client.get(f"/api/v1/projects/{project['id']}/packages", headers=_headers(token))
    atlas_summary_resp = client.get("/api/v1/atlas", headers=_headers(token))
    atlas_runs = client.get("/api/v1/atlas/runs", headers=_headers(token))
    atlas_entities = client.get("/api/v1/atlas/entities?entity_type=domain&q=api", headers=_headers(token))
    atlas_entity = client.get(f"/api/v1/atlas/entities/{entity_id}", headers=_headers(token))
    atlas_findings = client.get("/api/v1/atlas/findings?q=finding&review_state=new", headers=_headers(token))
    atlas_finding = client.get(f"/api/v1/atlas/findings/{finding_id}", headers=_headers(token))
    cross_project = client.get(f"/api/v1/projects/{project['id']}", headers=_headers(other_token))
    cross_findings = client.get(f"/api/v1/projects/{project['id']}/findings", headers=_headers(other_token))
    cross_runs = client.get(f"/api/v1/projects/{project['id']}/runs", headers=_headers(other_token))
    cross_entities = client.get(f"/api/v1/projects/{project['id']}/entities", headers=_headers(other_token))
    cross_packages = client.get(f"/api/v1/projects/{project['id']}/packages", headers=_headers(other_token))
    cross_atlas_entity = client.get(f"/api/v1/atlas/entities/{entity_id}", headers=_headers(other_token))
    cross_atlas_finding = client.get(f"/api/v1/atlas/findings/{finding_id}", headers=_headers(other_token))

    assert owner_project.status_code == 200
    assert json.loads(owner_project.data)["project"]["id"] == project["id"]
    assert owner_findings.status_code == 200
    assert json.loads(owner_findings.data)["findings"][0]["id"] == finding_id
    assert owner_runs.status_code == 200
    assert json.loads(owner_runs.data)["runs"][0]["id"] == run_id
    assert owner_entities.status_code == 200
    assert json.loads(owner_entities.data)["entities"][0]["id"] == entity_id
    assert json.loads(owner_entities.data)["counts_by_type"] == {"domain": 1}
    assert owner_packages.status_code == 200
    assert json.loads(owner_packages.data)["total"] == 1
    assert atlas_summary_resp.status_code == 200
    assert json.loads(atlas_summary_resp.data)["counts"]["domain"] >= 1
    assert atlas_runs.status_code == 200
    assert json.loads(atlas_runs.data)["runs"][0]["id"] == run_id
    assert atlas_entities.status_code == 200
    assert json.loads(atlas_entities.data)["entities"][0]["id"] == entity_id
    assert atlas_entity.status_code == 200
    assert json.loads(atlas_entity.data)["entity"]["id"] == entity_id
    assert atlas_findings.status_code == 200
    assert json.loads(atlas_findings.data)["findings"][0]["id"] == finding_id
    assert atlas_finding.status_code == 200
    assert json.loads(atlas_finding.data)["occurrences"][0]["run_id"] == run_id
    assert cross_project.status_code == 404
    assert cross_findings.status_code == 404
    assert cross_runs.status_code == 404
    assert cross_entities.status_code == 404
    assert cross_packages.status_code == 404
    assert cross_atlas_entity.status_code == 404
    assert cross_atlas_finding.status_code == 404


def test_api_v1_run_start_uses_broker_and_streams_ndjson(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    monkeypatch.setitem(shell_app.CFG, "run_broker_require_redis", False)

    start = client.post("/api/v1/runs", json={"command": "help"}, headers=_headers(token))
    run_id = json.loads(start.data)["id"]
    stream = client.get(f"/api/v1/runs/{run_id}/stream?format=ndjson", headers=_headers(token))

    assert start.status_code == 202
    start_data = json.loads(start.data)
    assert start_data["status"] == "succeeded"
    assert start_data["stream_url"] == f"/api/v1/runs/{run_id}/stream"
    assert stream.status_code == 200
    events = [json.loads(line) for line in stream.get_data(as_text=True).splitlines() if line]
    assert events[0] == {"type": "schema", "event": "schema", "v": 1, "kind": "line_event"}
    assert any(
        event.get("type") == "output"
        and event.get("v") == 1
        and event.get("kind")
        and event.get("role")
        for event in events
    )
    assert any(event.get("type") == "exit" and event.get("event_id") for event in events)

    def broken_stream():
        yield 'id: 1-0\nevent: output\ndata: {"type":"output","text":"before"}\n\n'
        raise RuntimeError("stream broke")

    with mock.patch("blueprints.api_v1.stream_run_events", return_value=broken_stream()), \
         mock.patch.object(api_blueprint.log, "error") as mock_error:
        broken = client.get(f"/api/v1/runs/{run_id}/stream?format=ndjson", headers=_headers(token))
        broken_events = [json.loads(line) for line in broken.get_data(as_text=True).splitlines() if line]
        assert broken_events[-1]["code"] == "stream_error"
        assert mock_error.call_args.args[0] == "API_RUN_STREAM_ERROR"
        assert mock_error.call_args.kwargs["exc_info"] is True
        stream_extra = mock_error.call_args.kwargs["extra"]
    assert stream_extra["run_id"] == run_id
    assert stream_extra["team_id"] == ""
    assert stream_extra["format"] == "ndjson"


def test_api_v1_sse_stream_emits_idle_heartbeat(monkeypatch):
    import services.runs.broker as run_broker

    class FakeStore:
        def wait_after(self, run_id, after_id, timeout):
            assert run_id == "run_idle"
            assert after_id == "1-0"
            assert timeout >= 1
            return []

    monkeypatch.setattr(run_broker, "_store", lambda: FakeStore())

    stream = run_broker.stream_run_events("run_idle", after_id="1-0")
    try:
        schema = next(stream)
        assert schema.startswith("event: schema\n")
        assert '"type": "schema"' in schema
        assert next(stream) == ": heartbeat\n\n"
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


def test_api_v1_ndjson_stream_adapts_sse_heartbeat_comments():
    import blueprints.api_v1 as api_blueprint

    assert list(api_blueprint._ndjson_from_sse_chunks([": heartbeat\n\n"])) == ['{"type":"heartbeat"}\n']


def test_api_v1_ndjson_stream_preserves_sse_event_name():
    import blueprints.api_v1 as api_blueprint

    chunks = [
        'id: 7-0\nevent: output\ndata: {"type":"output","text":"hello"}\n\n',
        'id: 8-0\nevent: output_batch\ndata: {"type":"output_batch","lines":[{"text":"batched"}]}\n\n',
    ]

    assert list(api_blueprint._ndjson_from_sse_chunks(chunks)) == [
        '{"type":"output","text":"hello","event":"output","event_id":"7-0"}\n',
        '{"type":"output_batch","lines":[{"text":"batched"}],"event":"output_batch","event_id":"8-0"}\n',
    ]


def test_api_v1_run_start_reports_broker_unavailable(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    monkeypatch.setattr(api_blueprint, "broker_available", lambda: False)
    monkeypatch.setattr(api_blueprint, "broker_unavailable_reason", lambda: "redis unavailable")

    resp = client.post("/api/v1/runs", json={"command": "help"}, headers=_headers(token))
    data = json.loads(resp.data)

    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"
    assert data["error"]["code"] == "broker_unavailable"
    assert data["error"]["message"] == "redis unavailable"


def test_api_v1_run_start_rejects_archived_project_link(monkeypatch):
    client = get_client()
    token = _token(client)
    monkeypatch.setitem(shell_app.CFG, "run_broker_require_redis", False)
    project_resp = client.post("/projects", json={"name": "Archived API"}, headers={"X-Session-ID": token})
    project = json.loads(project_resp.data)["project"]
    client.put(f"/projects/{project['id']}", json={"status": "archived"}, headers={"X-Session-ID": token})

    resp = client.post(
        "/api/v1/runs",
        json={"command": "help", "project_id": project["id"]},
        headers=_headers(token),
    )
    data = json.loads(resp.data)

    assert resp.status_code == 409
    assert data["error"]["code"] == "archived_project"


def test_api_v1_run_start_rejects_invalid_body_and_unknown_project(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    monkeypatch.setattr(api_blueprint, "broker_available", lambda: True)

    invalid = client.post(
        "/api/v1/runs",
        data="[]",
        content_type="application/json",
        headers=_headers(token),
    )
    unknown_project = client.post(
        "/api/v1/runs",
        json={"command": "help", "project_id": "prj_missing"},
        headers=_headers(token),
    )

    assert invalid.status_code == 400
    assert json.loads(invalid.data)["error"]["code"] == "invalid_body"
    assert unknown_project.status_code == 404
    assert json.loads(unknown_project.data)["error"]["code"] == "not_found"


def test_api_v1_run_start_rejects_project_links_for_builtin_missing_and_interactive(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="Run Mode API Project")
    monkeypatch.setattr(api_blueprint, "broker_available", lambda: True)

    builtin = client.post(
        "/api/v1/runs",
        json={"command": "help", "project_id": project["id"]},
        headers=_headers(token),
    )
    interactive = client.post(
        "/api/v1/runs",
        json={"command": "mtr --interactive darklab.sh"},
        headers=_headers(token),
    )
    monkeypatch.setattr(
        api_blueprint,
        "interactive_pty_spec_for_command",
        lambda _command: {"trigger_flag": "--interactive"},
    )
    monkeypatch.setattr(
        api_blueprint,
        "_prepare_command_input",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            api_blueprint._RunPreparationError("later validation", status_code=418)
        ),
    )
    interactive_prefix = client.post(
        "/api/v1/runs",
        json={"command": "mtr --interactive-output darklab.sh"},
        headers=_headers(token),
    )

    monkeypatch.setattr(
        api_blueprint,
        "_prepare_command_input",
        lambda *_args, **_kwargs: SimpleNamespace(
            execution_command="missingtool darklab.sh",
            variable_notice=None,
            postfilter=None,
        ),
    )
    monkeypatch.setattr(api_blueprint, "resolve_builtin_command", lambda _command: None)
    monkeypatch.setattr(
        api_blueprint,
        "_prepare_real_command",
        lambda *_args, **_kwargs: SimpleNamespace(missing_runtime="missingtool"),
    )
    missing_runtime = client.post(
        "/api/v1/runs",
        json={"command": "missingtool darklab.sh", "project_id": project["id"]},
        headers=_headers(token),
    )

    assert builtin.status_code == 409
    assert json.loads(builtin.data)["error"]["code"] == "project_link_not_supported"
    assert interactive.status_code == 409
    assert json.loads(interactive.data)["error"]["code"] == "interactive_pty_not_supported"
    assert interactive_prefix.status_code == 418
    assert json.loads(interactive_prefix.data)["error"]["code"] == "command_rejected"
    assert missing_runtime.status_code == 409
    assert json.loads(missing_runtime.data)["error"]["code"] == "project_link_not_supported"


def test_api_v1_run_start_rewrites_workspace_root_output_paths(monkeypatch, tmp_path):
    import blueprints.api_v1 as api_blueprint
    import blueprints.run as run_blueprint

    client = get_client()
    token = _token(client)
    seen = {}

    monkeypatch.setitem(shell_app.CFG, "run_broker_require_redis", False)
    monkeypatch.setitem(shell_app.CFG, "workspace_enabled", True)
    monkeypatch.setitem(shell_app.CFG, "workspace_backend", "tmpfs")
    monkeypatch.setitem(shell_app.CFG, "workspace_root", str(tmp_path))
    monkeypatch.setitem(shell_app.CFG, "workspace_quota_mb", 1)
    monkeypatch.setitem(shell_app.CFG, "workspace_max_file_mb", 1)
    monkeypatch.setitem(shell_app.CFG, "workspace_max_files", 10)
    monkeypatch.setitem(shell_app.CFG, "workspace_inactivity_ttl_hours", 1)

    def fake_start(_original_command, _session_id, _client_ip, prepared_real):
        seen["command"] = prepared_real.command
        seen["writes"] = prepared_real.validation.workspace_writes
        return SimpleNamespace(
            run_id="api_workspace_run",
            run_started="2026-05-19T00:00:00+00:00",
            proc=object(),
            capture=object(),
            signal_classifier=object(),
            workspace_path_filter=object(),
        )

    monkeypatch.setattr(api_blueprint, "_start_real_command_process", fake_start)
    monkeypatch.setattr(api_blueprint, "_brokered_real_run_worker", lambda **_kwargs: None)
    monkeypatch.setattr(run_blueprint, "runtime_missing_command_name", lambda _command: None)

    resp = client.post(
        "/api/v1/runs",
        json={"command": "nmap -sV -p 1-1000 ip.darklab.sh -o /test_nmap_output.txt"},
        headers=_headers(token),
    )

    assert resp.status_code == 202
    assert seen["writes"] == ["test_nmap_output.txt"]
    assert str(tmp_path) in seen["command"]
    assert " -o /test_nmap_output.txt" not in seen["command"]


def test_api_v1_run_stream_and_cancel_are_token_scoped(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(token, command="sleep 30", output="")
    completed_run_id = "api_wait_done_" + uuid.uuid4().hex[:8]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
            "VALUES (?, ?, 'external', 'echo done', '2026-05-19T00:00:00+00:00', "
            "'2026-05-19T00:00:01+00:00', 7, '[]', 0)",
            (completed_run_id, token),
        )
        conn.commit()
    killed = {}

    monkeypatch.setattr(
        api_blueprint,
        "active_runs_for_session",
        lambda session_id, **_kwargs: [{"run_id": run_id, "command": "sleep 30"}] if session_id == token else [],
    )
    monkeypatch.setattr(
        api_blueprint,
        "pid_for_session",
        lambda requested_run_id, session_id: 4321 if requested_run_id == run_id and session_id == token else None,
    )
    monkeypatch.setattr(api_blueprint, "publish_run_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_blueprint, "_ensure_scanner_process_group_current", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_blueprint, "_signal_process_group", lambda pid: killed.update({"pid": pid}))

    owner_active = client.get("/api/v1/runs", headers=_headers(token))
    cross_active = client.get("/api/v1/runs", headers=_headers(other_token))
    cross_stream = client.get(f"/api/v1/runs/{run_id}/stream", headers=_headers(other_token))
    completed_wait = client.post(f"/api/v1/runs/{completed_run_id}/wait?timeout=0", headers=_headers(token))
    running_wait = client.post(f"/api/v1/runs/{run_id}/wait?timeout=0", headers=_headers(token))
    cross_wait = client.post(f"/api/v1/runs/{run_id}/wait?timeout=0", headers=_headers(other_token))
    owner_cancel = client.post(f"/api/v1/runs/{run_id}/cancel", headers=_headers(token))
    cross_cancel = client.post(f"/api/v1/runs/{run_id}/cancel", headers=_headers(other_token))

    assert owner_active.status_code == 200
    assert json.loads(owner_active.data)["runs"][0]["id"] == run_id
    assert json.loads(owner_active.data)["runs"][0]["status"] == "running"
    assert json.loads(cross_active.data) == {"runs": [], "total": 0}
    assert cross_stream.status_code == 404
    assert completed_wait.status_code == 200
    assert json.loads(completed_wait.data)["run"]["exit_code"] == 7
    assert running_wait.status_code == 408
    assert json.loads(running_wait.data)["error"]["code"] == "wait_timeout"
    assert cross_wait.status_code == 404
    assert owner_cancel.status_code == 200
    assert json.loads(owner_cancel.data) == {"killed": True, "id": run_id}
    assert killed["pid"] == 4321
    assert cross_cancel.status_code == 404


def test_api_v1_cancel_skips_signal_when_scanner_pid_start_time_changed(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    run_id = "api_cancel_reused_" + uuid.uuid4().hex[:8]
    published = []

    monkeypatch.setattr(
        api_blueprint,
        "active_runs_for_session",
        lambda session_id, **_kwargs: [{"run_id": run_id, "command": "sleep 30"}] if session_id == token else [],
    )
    monkeypatch.setattr(
        api_blueprint,
        "pid_for_session",
        lambda requested_run_id, session_id: 4321 if requested_run_id == run_id and session_id == token else None,
    )
    monkeypatch.setattr(api_blueprint, "publish_run_event", lambda *args, **_kwargs: published.append(args))
    monkeypatch.setattr(
        api_blueprint,
        "_ensure_scanner_process_group_current",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ProcessLookupError("stale pid")),
    )
    signal_process_group = mock.Mock()
    monkeypatch.setattr(api_blueprint, "_signal_process_group", signal_process_group)

    resp = client.post(f"/api/v1/runs/{run_id}/cancel", headers=_headers(token))

    assert resp.status_code == 200
    assert json.loads(resp.data) == {"killed": True, "id": run_id}
    assert published == [(run_id, "killed", {"api": True})]
    signal_process_group.assert_not_called()


def test_api_v1_explicit_project_link_uses_finalized_run_path(monkeypatch):
    import blueprints.api_v1 as api_blueprint
    from blueprints.run import _save_completed_run
    from services.runs.kinds import RUN_KIND_EXTERNAL

    class FakeCapture:
        preview_lines = []
        preview_truncated = False
        output_line_count = 0
        full_output_available = False
        full_output_truncated = False
        artifact_rel_path = ""
        full_output_bytes = 0

        def finalize(self):
            return None

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    audit_events = []
    monkeypatch.setattr(
        api_blueprint.log,
        "info",
        lambda event, *args, **kwargs: audit_events.append((event, kwargs.get("extra", {}))),
    )
    project_resp = client.post("/projects", json={"name": "API Project"}, headers={"X-Session-ID": token})
    project = json.loads(project_resp.data)["project"]
    run_id = "api_project_link_run_" + uuid.uuid4().hex[:8]
    route_run_id = _seed_run(token, command="echo route link", output="route link")

    link = _save_completed_run(
        run_id,
        token,
        "",
        "echo linked",
        "2026-05-19T00:00:00+00:00",
        "2026-05-19T00:00:01+00:00",
        0,
        FakeCapture(),
        link_active_project=False,
        link_project_id=project["id"],
        run_kind=RUN_KIND_EXTERNAL,
    )

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT source FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
            (project["id"], run_id),
        ).fetchone()

    assert link["project_id"] == project["id"]
    assert row[0] == "manual"

    route_link = client.post(f"/api/v1/runs/{route_run_id}/projects/{project['id']}", headers=_headers(token))
    cross_link = client.post(f"/api/v1/runs/{route_run_id}/projects/{project['id']}", headers=_headers(other_token))
    route_unlink = client.delete(f"/api/v1/runs/{route_run_id}/projects/{project['id']}", headers=_headers(token))
    route_unlink_again = client.delete(f"/api/v1/runs/{route_run_id}/projects/{project['id']}", headers=_headers(token))
    client.put(f"/projects/{project['id']}", json={"status": "archived"}, headers={"X-Session-ID": token})
    archived_link = client.post(f"/api/v1/runs/{route_run_id}/projects/{project['id']}", headers=_headers(token))

    assert route_link.status_code == 201
    assert json.loads(route_link.data)["link"]["entity_id"] == route_run_id
    assert cross_link.status_code == 404
    assert route_unlink.status_code == 200
    assert route_unlink_again.status_code == 404
    assert archived_link.status_code == 409
    assert json.loads(archived_link.data)["error"]["code"] == "archived_project"
    assert (
        "API_PROJECT_RUN_LINKED",
        {
            "ip": "127.0.0.1",
            "session": token[:8] + "********",
            "run_id": route_run_id,
            "project_id": project["id"],
            "link_source": "manual",
        },
    ) in audit_events
    assert (
        "API_PROJECT_RUN_UNLINKED",
        {
            "ip": "127.0.0.1",
            "session": token[:8] + "********",
            "run_id": route_run_id,
            "project_id": project["id"],
        },
    ) in audit_events


def test_api_v1_schedules_crud_run_now_and_fire_audit_are_token_scoped(monkeypatch):
    import blueprints.api_v1 as api_blueprint
    from services.scheduler import dispatch

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    monkeypatch.setattr(api_blueprint, "validate_schedule_command", lambda command, *_args, **_kwargs: command.strip())
    monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda _schedule: "run_api_schedule")

    create = client.post(
        "/api/v1/schedules",
        headers=_headers(token),
        json={
            "command": "echo scheduled api",
            "cadence_preset": "hourly",
            "label": "API Schedule",
            "timezone": "UTC",
        },
    )
    schedule = json.loads(create.data)["schedule"]

    assert create.status_code == 201
    assert schedule["command_text"] == "echo scheduled api"
    assert schedule["cadence_preset"] == "hourly"
    assert schedule["enabled"] is True
    assert "session_token" not in schedule

    listed = json.loads(client.get("/api/v1/schedules?limit=10&offset=0", headers=_headers(token)).data)
    other_listed = json.loads(client.get("/api/v1/schedules", headers=_headers(other_token)).data)
    detail_payload = json.loads(client.get(f"/api/v1/schedules/{schedule['id']}", headers=_headers(token)).data)
    detail = detail_payload["schedule"]
    cross_detail = client.get(f"/api/v1/schedules/{schedule['id']}", headers=_headers(other_token))
    cross_patch = client.patch(
        f"/api/v1/schedules/{schedule['id']}",
        headers=_headers(other_token),
        json={"enabled": False},
    )
    cross_run_now = client.post(f"/api/v1/schedules/{schedule['id']}/run-now", headers=_headers(other_token))
    cross_fires = client.get(f"/api/v1/schedules/{schedule['id']}/fires", headers=_headers(other_token))
    cross_delete = client.delete(f"/api/v1/schedules/{schedule['id']}", headers=_headers(other_token))
    patched = json.loads(
        client.patch(
            f"/api/v1/schedules/{schedule['id']}",
            headers=_headers(token),
            json={"enabled": False, "label": "Paused API Schedule"},
        ).data
    )["schedule"]
    fired = json.loads(client.post(f"/api/v1/schedules/{schedule['id']}/run-now", headers=_headers(token)).data)
    fires = json.loads(client.get(f"/api/v1/schedules/{schedule['id']}/fires", headers=_headers(token)).data)
    deleted = json.loads(client.delete(f"/api/v1/schedules/{schedule['id']}", headers=_headers(token)).data)
    deleted_detail = client.get(f"/api/v1/schedules/{schedule['id']}", headers=_headers(token))

    assert listed["total"] == 1
    assert listed["schedules"][0]["id"] == schedule["id"]
    assert other_listed["schedules"] == []
    assert detail["label"] == "API Schedule"
    assert len(detail_payload["next_fires"]) == 3
    assert all(str(value).endswith("+00:00") for value in detail_payload["next_fires"])
    assert cross_detail.status_code == 404
    assert json.loads(cross_detail.data)["error"]["code"] == "not_found"
    assert cross_patch.status_code == 404
    assert cross_run_now.status_code == 404
    assert cross_fires.status_code == 404
    assert cross_delete.status_code == 404
    assert patched["enabled"] is False
    assert patched["label"] == "Paused API Schedule"
    assert fired["status"] == "fired"
    assert fired["schedule"]["last_run_at"]
    assert fires["total"] == 1
    assert fires["fires"][0]["status"] == "fired"
    assert deleted == {"removed": True}
    assert deleted_detail.status_code == 404
    audit_rows = _audit_event_rows(target_id=schedule["id"])
    assert [row["event_type"] for row in audit_rows] == [
        "schedule.create",
        "schedule.update",
        "schedule.run_now",
        "schedule.delete",
    ]
    assert {row["target_type"] for row in audit_rows} == {"schedule"}
    assert {row["details"]["source"] for row in audit_rows} == {"api_v1"}
    assert audit_rows[1]["details"]["changed_fields"] == ["enabled", "label"]
    assert audit_rows[2]["details"]["run_id"] == "run_api_schedule"
    assert audit_rows[3]["details"]["deleted_count"] == 1
    assert "echo scheduled api" not in json.dumps(audit_rows)

    team_owner = _token(client)
    team_viewer = _token(client)
    team_id = _create_api_team(client, team_owner, name="API Schedule Operators")
    _add_api_team_member(client, team_owner, team_viewer, team_id, role="viewer")
    owner_headers = _team_headers(team_owner, team_id)
    viewer_headers = _team_headers(team_viewer, team_id)
    team_created = client.post(
        "/api/v1/schedules",
        headers=owner_headers,
        json={"command": "echo team schedule", "cadence_preset": "hourly", "timezone": "UTC"},
    )
    team_schedule = json.loads(team_created.data)["schedule"]
    team_fired = client.post(f"/api/v1/schedules/{team_schedule['id']}/run-now", headers=owner_headers)
    viewer_list = json.loads(client.get("/api/v1/schedules", headers=viewer_headers).data)
    viewer_detail = client.get(f"/api/v1/schedules/{team_schedule['id']}", headers=viewer_headers)
    viewer_fires = client.get(f"/api/v1/schedules/{team_schedule['id']}/fires", headers=viewer_headers)
    viewer_create = client.post(
        "/api/v1/schedules",
        headers=viewer_headers,
        json={"command": "echo viewer schedule", "cadence_preset": "hourly"},
    )
    viewer_patch = client.patch(f"/api/v1/schedules/{team_schedule['id']}", headers=viewer_headers, json={"enabled": False})
    viewer_run_now = client.post(f"/api/v1/schedules/{team_schedule['id']}/run-now", headers=viewer_headers)
    viewer_delete = client.delete(f"/api/v1/schedules/{team_schedule['id']}", headers=viewer_headers)
    team_deleted = client.delete(f"/api/v1/schedules/{team_schedule['id']}", headers=owner_headers)

    assert team_created.status_code == 201
    assert team_schedule["team_id"] == team_id
    assert team_fired.status_code == 200
    assert viewer_list["total"] == 1
    assert viewer_list["schedules"][0]["id"] == team_schedule["id"]
    assert viewer_detail.status_code == 200
    assert json.loads(viewer_detail.data)["schedule"]["id"] == team_schedule["id"]
    assert viewer_fires.status_code == 200
    assert json.loads(viewer_fires.data)["fires"][0]["team_id"] == team_id
    for response in (viewer_create, viewer_patch, viewer_run_now, viewer_delete):
        assert response.status_code == 403
        assert json.loads(response.data)["error"]["code"] == "team_forbidden"
    assert json.loads(team_deleted.data) == {"removed": True}
    team_audit_rows = _audit_event_rows(target_id=team_schedule["id"])
    assert [row["event_type"] for row in team_audit_rows] == [
        "schedule.create",
        "schedule.run_now",
        "schedule.delete",
    ]
    assert {row["details"]["source"] for row in team_audit_rows} == {"api_v1"}


def test_api_v1_schedules_reject_invalid_body_and_disallowed_command(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)

    def reject_command(*_args, **_kwargs):
        raise api_blueprint.ScheduleCommandValidationError("command is not allowed")

    monkeypatch.setattr(api_blueprint, "validate_schedule_command", reject_command)

    invalid_body = client.post(
        "/api/v1/schedules",
        headers=_headers(token),
        data="[]",
        content_type="application/json",
    )
    disallowed = client.post(
        "/api/v1/schedules",
        headers=_headers(token),
        json={"command": "nmap darklab.sh", "cadence_preset": "daily"},
    )

    assert invalid_body.status_code == 400
    assert json.loads(invalid_body.data)["error"]["code"] == "invalid_body"
    assert disallowed.status_code == 400
    assert json.loads(disallowed.data)["error"]["code"] == "invalid_command"


def test_api_v1_schedule_create_normalizes_string_false_enabled(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    monkeypatch.setattr(api_blueprint, "validate_schedule_command", lambda command, *_args, **_kwargs: command.strip())

    create = client.post(
        "/api/v1/schedules",
        headers=_headers(token),
        json={
            "command": "echo disabled",
            "cadence_preset": "hourly",
            "enabled": "false",
        },
    )

    assert create.status_code == 201
    assert json.loads(create.data)["schedule"]["enabled"] is False


def test_api_v1_watchers_crud_run_now_accept_and_fire_audit_are_token_scoped(monkeypatch):
    import blueprints.api_v1 as api_blueprint
    from services.scheduler import dispatch

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    baseline_run_id = _seed_run(token, command="nmap -sV darklab.sh", output="22/tcp open ssh")
    monkeypatch.setattr(api_blueprint, "validate_schedule_command", lambda command, *_args, **_kwargs: command.strip())
    monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda _schedule: "run_api_watcher")

    create = client.post(
        "/api/v1/watchers",
        headers=_headers(token),
        json={
            "baseline_run_id": baseline_run_id,
            "cadence_preset": "hourly",
            "label": "API Watcher",
            "timezone": "UTC",
            "options": {"suppress_removals": True, "notify_metadata_changes": False},
        },
    )
    watcher = json.loads(create.data)["watcher"]

    assert create.status_code == 201
    assert watcher["command_text"] == "nmap -sV darklab.sh"
    assert watcher["baseline_run_id"] == baseline_run_id
    assert watcher["state"] == "ok"
    assert watcher["options"]["suppress_removals"] is True
    assert watcher["schedule"]["owner_kind"] == "watcher"
    assert "session_token" not in watcher

    listed = json.loads(client.get("/api/v1/watchers?limit=10&offset=0", headers=_headers(token)).data)
    other_listed = json.loads(client.get("/api/v1/watchers", headers=_headers(other_token)).data)
    detail = json.loads(client.get(f"/api/v1/watchers/{watcher['id']}", headers=_headers(token)).data)["watcher"]
    cross_detail = client.get(f"/api/v1/watchers/{watcher['id']}", headers=_headers(other_token))
    cross_patch = client.patch(
        f"/api/v1/watchers/{watcher['id']}",
        headers=_headers(other_token),
        json={"state": "paused"},
    )
    cross_run_now = client.post(f"/api/v1/watchers/{watcher['id']}/run-now", headers=_headers(other_token))
    cross_fires = client.get(f"/api/v1/watchers/{watcher['id']}/fires", headers=_headers(other_token))
    cross_accept = client.post(f"/api/v1/watchers/{watcher['id']}/accept-baseline", headers=_headers(other_token))
    cross_delete = client.delete(f"/api/v1/watchers/{watcher['id']}", headers=_headers(other_token))
    paused = json.loads(
        client.patch(
            f"/api/v1/watchers/{watcher['id']}",
            headers=_headers(token),
            json={"state": "paused", "reason": "operator check", "label": "Paused API Watcher"},
        ).data
    )["watcher"]
    resumed = json.loads(
        client.patch(
            f"/api/v1/watchers/{watcher['id']}",
            headers=_headers(token),
            json={"state": "ok"},
        ).data
    )["watcher"]
    fired = json.loads(client.post(f"/api/v1/watchers/{watcher['id']}/run-now", headers=_headers(token)).data)
    fires = json.loads(client.get(f"/api/v1/watchers/{watcher['id']}/fires", headers=_headers(token)).data)
    accepted = json.loads(
        client.post(
            f"/api/v1/watchers/{watcher['id']}/accept-baseline",
            headers=_headers(token),
            json={"run_id": "run_api_watcher"},
        ).data
    )["watcher"]
    deleted = json.loads(client.delete(f"/api/v1/watchers/{watcher['id']}", headers=_headers(token)).data)
    deleted_detail = client.get(f"/api/v1/watchers/{watcher['id']}", headers=_headers(token))

    assert listed["total"] == 1
    assert listed["watchers"][0]["id"] == watcher["id"]
    assert other_listed["watchers"] == []
    assert detail["label"] == "API Watcher"
    assert cross_detail.status_code == 404
    assert json.loads(cross_detail.data)["error"]["code"] == "not_found"
    assert cross_patch.status_code == 404
    assert cross_run_now.status_code == 404
    assert cross_fires.status_code == 404
    assert cross_accept.status_code == 404
    assert cross_delete.status_code == 404
    assert paused["state"] == "paused"
    assert paused["label"] == "Paused API Watcher"
    assert paused["schedule"]["enabled"] is False
    assert resumed["state"] == "ok"
    assert resumed["schedule"]["enabled"] is True
    assert fired["status"] == "fired"
    assert fired["watcher"]["last_run_id"] == "run_api_watcher"
    assert fires["total"] == 1
    assert fires["fires"][0]["run_id"] == "run_api_watcher"
    assert accepted["baseline_run_id"] == "run_api_watcher"
    assert deleted == {"removed": True}
    assert deleted_detail.status_code == 404
    audit_rows = _audit_event_rows(target_id=watcher["id"])
    assert [row["event_type"] for row in audit_rows] == [
        "watcher.create",
        "watcher.pause",
        "watcher.resume",
        "watcher.run_now",
        "watcher.accept_baseline",
        "watcher.delete",
    ]
    assert {row["target_type"] for row in audit_rows} == {"watcher"}
    assert {row["details"]["source"] for row in audit_rows} == {"api_v1"}
    assert audit_rows[0]["details"]["baseline_run_id"] == baseline_run_id
    assert audit_rows[1]["details"]["reason"] == "operator check"
    assert audit_rows[3]["details"]["run_id"] == "run_api_watcher"
    assert audit_rows[4]["details"]["baseline_run_id"] == "run_api_watcher"
    assert audit_rows[5]["details"]["deleted_count"] == 1
    assert "nmap -sV darklab.sh" not in json.dumps(audit_rows)

    team_owner = _token(client)
    team_viewer = _token(client)
    team_id = _create_api_team(client, team_owner, name="API Watcher Operators")
    _add_api_team_member(client, team_owner, team_viewer, team_id, role="viewer")
    team_baseline_run_id = _seed_run(
        team_owner,
        run_id="api_watcher_team_baseline_" + team_id[-8:],
        team_id=team_id,
        command="nmap -sV darklab.sh",
        output="443/tcp open https",
    )
    monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda _schedule: "run_api_team_watcher")
    owner_headers = _team_headers(team_owner, team_id)
    viewer_headers = _team_headers(team_viewer, team_id)
    team_created = client.post(
        "/api/v1/watchers",
        headers=owner_headers,
        json={"baseline_run_id": team_baseline_run_id, "cadence_preset": "hourly", "label": "Team API Watcher"},
    )
    team_watcher = json.loads(team_created.data)["watcher"]
    team_fired = client.post(f"/api/v1/watchers/{team_watcher['id']}/run-now", headers=owner_headers)
    viewer_list = json.loads(client.get("/api/v1/watchers", headers=viewer_headers).data)
    viewer_detail = client.get(f"/api/v1/watchers/{team_watcher['id']}", headers=viewer_headers)
    viewer_fires = client.get(f"/api/v1/watchers/{team_watcher['id']}/fires", headers=viewer_headers)
    viewer_create = client.post(
        "/api/v1/watchers",
        headers=viewer_headers,
        json={"baseline_run_id": team_baseline_run_id, "cadence_preset": "hourly"},
    )
    viewer_patch = client.patch(f"/api/v1/watchers/{team_watcher['id']}", headers=viewer_headers, json={"state": "paused"})
    viewer_run_now = client.post(f"/api/v1/watchers/{team_watcher['id']}/run-now", headers=viewer_headers)
    viewer_accept = client.post(f"/api/v1/watchers/{team_watcher['id']}/accept-baseline", headers=viewer_headers)
    viewer_delete = client.delete(f"/api/v1/watchers/{team_watcher['id']}", headers=viewer_headers)
    team_deleted = client.delete(f"/api/v1/watchers/{team_watcher['id']}", headers=owner_headers)

    assert team_created.status_code == 201
    assert team_watcher["team_id"] == team_id
    assert team_watcher["schedule"]["team_id"] == team_id
    assert team_fired.status_code == 200
    assert viewer_list["total"] == 1
    assert viewer_list["watchers"][0]["id"] == team_watcher["id"]
    assert viewer_detail.status_code == 200
    assert json.loads(viewer_detail.data)["watcher"]["id"] == team_watcher["id"]
    assert viewer_fires.status_code == 200
    assert json.loads(viewer_fires.data)["fires"][0]["team_id"] == team_id
    for response in (viewer_create, viewer_patch, viewer_run_now, viewer_accept, viewer_delete):
        assert response.status_code == 403
        assert json.loads(response.data)["error"]["code"] == "team_forbidden"
    assert json.loads(team_deleted.data) == {"removed": True}
    team_audit_rows = _audit_event_rows(target_id=team_watcher["id"])
    assert [row["event_type"] for row in team_audit_rows] == [
        "watcher.create",
        "watcher.run_now",
        "watcher.delete",
    ]
    assert {row["details"]["source"] for row in team_audit_rows} == {"api_v1"}


def test_api_v1_watchers_reject_invalid_body_disallowed_command_and_bad_baseline(monkeypatch):
    import blueprints.api_v1 as api_blueprint

    client = get_client()
    token = _token(client)
    baseline_run_id = _seed_run(token, command="nmap darklab.sh")

    def reject_command(*_args, **_kwargs):
        raise api_blueprint.ScheduleCommandValidationError("command is not allowed")

    monkeypatch.setattr(api_blueprint, "validate_schedule_command", reject_command)

    invalid_body = client.post(
        "/api/v1/watchers",
        headers=_headers(token),
        data="[]",
        content_type="application/json",
    )
    missing_baseline = client.post(
        "/api/v1/watchers",
        headers=_headers(token),
        json={"baseline_run_id": "missing", "cadence_preset": "hourly"},
    )
    first_run = client.post(
        "/api/v1/watchers",
        headers=_headers(token),
        json={"baseline_mode": "first_run", "cadence_preset": "hourly", "command": "nmap darklab.sh"},
    )
    disallowed = client.post(
        "/api/v1/watchers",
        headers=_headers(token),
        json={"baseline_run_id": baseline_run_id, "cadence_preset": "hourly", "command": "nmap darklab.sh"},
    )

    assert invalid_body.status_code == 400
    assert json.loads(invalid_body.data)["error"]["code"] == "invalid_body"
    assert missing_baseline.status_code == 404
    assert json.loads(missing_baseline.data)["error"]["code"] == "not_found"
    assert first_run.status_code == 400
    assert json.loads(first_run.data)["error"]["code"] == "invalid_command"
    assert disallowed.status_code == 400
    assert json.loads(disallowed.data)["error"]["code"] == "invalid_command"


def test_api_v1_openapi_route_matches_checked_in_contract():
    client = get_client()
    live = json.loads(client.get("/api/v1/openapi.json").data)
    checked_in = json.loads((ROOT_DIR / "docs" / "api-v1-openapi.json").read_text(encoding="utf-8"))

    assert live == checked_in


def test_api_v1_notification_channels_crud_masks_secrets_and_lists_events(monkeypatch):
    from services.notifications.models import ChannelResult
    from services.secrets import vault as secrets_vault
    import services.notifications.channels.webhook as webhook_channel

    client = get_client()
    token = _token(client)
    sent_payloads = []
    monkeypatch.setitem(config.CFG, "app_name", "darklab_shell")
    monkeypatch.setenv("SECRETS_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    secrets_vault.reset_master_key_cache_for_tests()

    def fake_post_json(_url, payload, _config, *, label, **_kwargs):
        sent_payloads.append((label, payload))
        return ChannelResult.success()

    monkeypatch.setattr(webhook_channel, "post_json", fake_post_json)

    kind_contract_resp = client.get("/api/v1/notification-channel-kinds", headers=_headers(token))
    kind_contract = json.loads(kind_contract_resp.data)
    create = client.post(
        "/api/v1/notification-channels",
        headers=_headers(token),
        json={
            "kind": "webhook",
            "label": "Ops Hook",
            "triggers": ["run_complete"],
            "secret_values": {"url": "https://hooks.example.test/darklab"},
            "config": {"timeout_seconds": "5"},
        },
    )
    created = json.loads(create.data)["channel"]

    assert kind_contract_resp.status_code == 200
    webhook_kind = next(item for item in kind_contract["kinds"] if item["kind"] == "webhook")
    assert webhook_kind["secret_fields"] == [{"name": "url", "label": "Webhook URL"}]
    telegram_kind = next(item for item in kind_contract["kinds"] if item["kind"] == "telegram")
    assert telegram_kind["secret_fields"] == [{"name": "bot_token", "label": "Bot token"}]
    assert {"value": "run_complete", "label": "Run complete"} in kind_contract["triggers"]
    assert create.status_code == 201
    assert created["kind"] == "webhook"
    assert created["secret_fields"] == [{"name": "url", "configured": True}]
    assert "hooks.example" not in json.dumps(created)

    listed = json.loads(client.get("/api/v1/notification-channels", headers=_headers(token)).data)
    assert [channel["id"] for channel in listed["channels"]] == [created["id"]]
    assert "hooks.example" not in json.dumps(listed)

    tested = client.post(f"/api/v1/notification-channels/{created['id']}/test", headers=_headers(token))
    test_payload = json.loads(tested.data)

    assert tested.status_code == 200
    assert test_payload["queued"] == 1
    assert test_payload["events"] == [{"event_id": test_payload["event_ids"][0], "status": "sent", "last_error": ""}]
    assert sent_payloads[0][0] == "webhook"
    assert sent_payloads[0][1]["trigger"] == "test"
    assert sent_payloads[0][1]["app_name"] == "darklab_shell"
    assert sent_payloads[0][1]["message"] == "darklab_shell test notification"
    assert sent_payloads[0][1]["channel_id"] == created["id"]

    events = json.loads(
        client.get(
            f"/api/v1/notification-events?channel_id={created['id']}&trigger=test&status=sent",
            headers=_headers(token),
        ).data
    )
    assert events["total"] == 1
    assert events["events"][0]["id"] == test_payload["event_ids"][0]
    assert events["events"][0]["payload"]["message"] == "darklab_shell test notification"

    updated = json.loads(
        client.patch(
            f"/api/v1/notification-channels/{created['id']}",
            headers=_headers(token),
            json={"label": "Muted Hook", "muted": True},
        ).data
    )["channel"]
    assert updated["label"] == "Muted Hook"
    assert updated["muted"] is True

    muted_tested = client.post(f"/api/v1/notification-channels/{created['id']}/test", headers=_headers(token))
    muted_test_payload = json.loads(muted_tested.data)

    assert muted_tested.status_code == 200
    assert muted_test_payload["queued"] == 1
    assert muted_test_payload["events"] == [
        {"event_id": muted_test_payload["event_ids"][0], "status": "sent", "last_error": ""}
    ]
    assert sent_payloads[-1][1]["trigger"] == "test"
    assert sent_payloads[-1][1]["channel_id"] == created["id"]

    deleted = json.loads(client.delete(f"/api/v1/notification-channels/{created['id']}", headers=_headers(token)).data)
    assert deleted == {"removed": True}


def test_api_v1_notification_channels_are_token_scoped(monkeypatch):
    from services.secrets import vault as secrets_vault

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    monkeypatch.setenv("SECRETS_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    secrets_vault.reset_master_key_cache_for_tests()
    create = client.post(
        "/api/v1/notification-channels",
        headers=_headers(token),
        json={"kind": "webhook", "secret_values": {"url": "https://hooks.example.test/scoped"}},
    )
    channel_id = json.loads(create.data)["channel"]["id"]

    other_list = json.loads(client.get("/api/v1/notification-channels", headers=_headers(other_token)).data)
    other_delete = client.delete(f"/api/v1/notification-channels/{channel_id}", headers=_headers(other_token))

    assert other_list == {"channels": []}
    assert other_delete.status_code == 404
    assert json.loads(other_delete.data)["error"]["code"] == "not_found"


def test_api_v1_notification_channels_honor_team_scope(monkeypatch):
    from services.notifications import dispatcher
    from services.notifications.models import TRIGGER_RUN_COMPLETE
    from services.secrets import vault as secrets_vault

    client = get_client()
    owner_token = _token(client)
    viewer_token = _token(client)
    monkeypatch.setenv("SECRETS_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    secrets_vault.reset_master_key_cache_for_tests()
    team_resp = client.post(
        "/session/teams",
        headers={"X-Session-ID": owner_token},
        json={"name": "API Notification Operators " + uuid.uuid4().hex[:8], "display_name": "API owner"},
    )
    team_id = json.loads(team_resp.data)["team"]["id"]
    invite_resp = client.post(
        f"/session/teams/{team_id}/invites",
        headers={"X-Session-ID": owner_token},
        json={"role": "viewer", "label": "API notification viewer"},
    )
    join_resp = client.post(
        "/session/teams/join",
        headers={"X-Session-ID": viewer_token},
        json={"code": json.loads(invite_resp.data)["invite"]["code"], "display_name": "API viewer"},
    )
    create_resp = client.post(
        "/api/v1/notification-channels",
        headers={**_headers(owner_token), "X-Team-ID": team_id},
        json={"kind": "webhook", "secret_values": {"url": "https://hooks.example.test/team"}},
    )
    channel = json.loads(create_resp.data)["channel"]
    viewer_create = client.post(
        "/api/v1/notification-channels",
        headers={**_headers(viewer_token), "X-Team-ID": team_id},
        json={"kind": "webhook", "secret_values": {"url": "https://hooks.example.test/blocked"}},
    )
    event_ids = dispatcher.enqueue(
        TRIGGER_RUN_COMPLETE,
        {"run_id": "api-team-notification"},
        owner_token,
        run_id="api-team-notification",
        team_id=team_id,
    )

    team_list = client.get("/api/v1/notification-channels", headers={**_headers(viewer_token), "X-Team-ID": team_id})
    personal_list = client.get("/api/v1/notification-channels", headers=_headers(owner_token))
    team_events = client.get("/api/v1/notification-events", headers={**_headers(viewer_token), "X-Team-ID": team_id})

    assert team_resp.status_code == 201
    assert join_resp.status_code == 201
    assert create_resp.status_code == 201
    assert channel["team_id"] == team_id
    assert viewer_create.status_code == 403
    assert json.loads(viewer_create.data)["error"]["code"] == "team_forbidden"
    assert [item["id"] for item in json.loads(team_list.data)["channels"]] == [channel["id"]]
    assert json.loads(personal_list.data)["channels"] == []
    events = json.loads(team_events.data)["events"]
    assert [item["id"] for item in events] == event_ids
    assert events[0]["team_id"] == team_id


def test_api_v1_notification_channel_rejections_are_logged():
    import blueprints.api_v1 as api_v1

    client = get_client()
    token = _token(client)
    with mock.patch.object(api_v1.log, "warning") as log_warning:
        resp = client.post(
            "/api/v1/notification-channels",
            headers=_headers(token),
            json={"kind": "bogus"},
        )

    assert resp.status_code == 400
    assert json.loads(resp.data)["error"]["code"] == "invalid_kind"
    log_warning.assert_any_call(
        "API_NOTIFICATION_CHANNEL_REJECTED",
        extra={
            "ip": "127.0.0.1",
            "session": "tok_" + token[4:8] + "********",
            "code": "invalid_kind",
            "status": 400,
            "route": "/api/v1/notification-channels",
            "method": "POST",
        },
    )


def test_darklab_cli_notify_commands_use_secret_file_and_event_reader(monkeypatch, capsys, tmp_path):
    cli_main = import_module("darklab_cli.__main__")
    secret_file = tmp_path / "webhook.json"
    secret_file.write_text('{"url": "https://hooks.example.test/cli"}', encoding="utf-8")
    calls = []

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/notification-channel-kinds" and method == "GET":
                return {
                    "kinds": [
                        {
                            "kind": "webhook",
                            "label": "Webhook",
                            "secret_fields": [{"name": "url", "label": "Webhook URL"}],
                            "config_fields": [{"name": "timeout_seconds", "label": "Timeout seconds", "optional": True}],
                        }
                    ],
                    "triggers": [{"value": "run_complete", "label": "Run complete"}],
                }
            if path == "/notification-channels" and method == "POST":
                assert body == {
                    "kind": "webhook",
                    "label": "CLI Hook",
                    "triggers": ["run_complete"],
                    "config": {"timeout_seconds": "5"},
                    "secret_values": {"url": "https://hooks.example.test/cli"},
                }
                return {"channel": {"id": "ntc_cli", "kind": "webhook", "muted": False, "label": "CLI Hook"}}
            if path == "/notification-channels" and method == "GET":
                return {"channels": [{"id": "ntc_cli", "kind": "webhook", "muted": False, "label": "CLI Hook"}]}
            if path == "/notification-channels/ntc_cli" and method == "PATCH":
                if body == {"label": "Updated Hook", "triggers": ["run_complete", "watcher_changed"]}:
                    return {"channel": {"id": "ntc_cli", "kind": "webhook", "muted": False, "label": "Updated Hook"}}
                if body == {"muted": True}:
                    return {"channel": {"id": "ntc_cli", "kind": "webhook", "muted": True, "label": "Updated Hook"}}
                if body == {"muted": False}:
                    return {"channel": {"id": "ntc_cli", "kind": "webhook", "muted": False, "label": "Updated Hook"}}
                raise cli_main.DarklabCliError(f"unexpected patch body: {body}")
            if path == "/notification-channels/ntc_cli/test":
                return {"queued": 1, "event_ids": ["nte_cli"]}
            if path == "/notification-events":
                assert params == {
                    "status": "sent",
                    "channel_id": "ntc_cli",
                    "trigger": "test",
                    "limit": 10,
                    "offset": 0,
                }
                return {
                    "events": [
                        {
                            "created": "2026-05-19T00:00:00+00:00",
                            "id": "nte_cli",
                            "status": "sent",
                            "trigger": "test",
                            "channel_id": "ntc_cli",
                            "run_id": "",
                        }
                    ]
                }
            if path == "/notification-channels/ntc_cli":
                return {"removed": True}
            raise cli_main.DarklabCliError("not_found: missing")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert "--secret " not in cli_main._parser()._subparsers._group_actions[0].choices["notify"].format_help()
    assert cli_main.main([
        "notify",
        "create",
        "webhook",
        "--label",
        "CLI Hook",
        "--trigger",
        "run_complete",
        "--config",
        "timeout_seconds=5",
        "--secret-file",
        str(secret_file),
        "--format",
        "json",
    ]) == 0
    create_output = capsys.readouterr().out
    assert json.loads(create_output)["channel"] == {
        "id": "ntc_cli",
        "kind": "webhook",
        "muted": False,
        "label": "CLI Hook",
    }
    assert cli_main.main(["notify", "list"]) == 0
    list_output = capsys.readouterr().out
    assert "ID       KIND     MUTED  LABEL" in list_output
    assert "CLI Hook" in list_output
    assert cli_main.main([
        "notify",
        "update",
        "ntc_cli",
        "--label",
        "Updated Hook",
        "--trigger",
        "run_complete",
        "--trigger",
        "watcher_changed",
    ]) == 0
    assert "Updated Hook" in capsys.readouterr().out
    assert cli_main.main(["notify", "mute", "ntc_cli"]) == 0
    assert "yes" in capsys.readouterr().out
    assert cli_main.main(["notify", "unmute", "ntc_cli"]) == 0
    assert "no" in capsys.readouterr().out
    assert cli_main.main(["notify", "test", "ntc_cli"]) == 0
    assert "nte_cli" in capsys.readouterr().out
    assert cli_main.main([
        "notify",
        "events",
        "--channel",
        "ntc_cli",
        "--trigger",
        "test",
        "--status",
        "sent",
        "--limit",
        "10",
    ]) == 0
    events_output = capsys.readouterr().out
    assert "CREATED" in events_output
    assert "nte_cli" in events_output
    assert cli_main.main(["notify", "delete", "ntc_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True

    assert [call[1] for call in calls] == [
        "/notification-channel-kinds",
        "/notification-channels",
        "/notification-channels",
        "/notification-channels/ntc_cli",
        "/notification-channels/ntc_cli",
        "/notification-channels/ntc_cli",
        "/notification-channels/ntc_cli/test",
        "/notification-events",
        "/notification-channels/ntc_cli",
    ]


def test_darklab_cli_team_commands_manage_api_teams(monkeypatch, capsys, tmp_path):
    cli_main = import_module("darklab_cli.__main__")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def request(self, method, path, *, params=None, body=None, stream=False):
            del params, stream
            if path == "/teams" and method == "GET":
                return {
                    "teams": [{
                        "id": "team_cli",
                        "name": "CLI Team",
                        "slug": "cli-team",
                        "status": "active",
                        "member": {"id": "tmem_owner", "role": "owner", "display_name": "Owner", "joined_at": ""},
                    }]
                }
            if path == "/teams" and method == "POST":
                assert body == {"name": "CLI Team", "slug": "cli-team", "display_name": "Owner"}
                return {
                    "team": {
                        "id": "team_cli",
                        "name": "CLI Team",
                        "slug": "cli-team",
                        "status": "active",
                        "member": {"role": "owner"},
                    },
                    "recovery_code": "trec_cli",
                }
            if path == "/teams/team_cli":
                return {
                    "team": {
                        "id": "team_cli",
                        "name": "CLI Team",
                        "slug": "cli-team",
                        "status": "active",
                        "member": {"role": "owner"},
                    },
                    "members": [{"id": "tmem_owner", "role": "owner", "status": "active", "display_name": "Owner"}],
                    "invites": [],
                    "recovery_codes": [],
                }
            if path == "/teams/team_cli/invites" and method == "POST":
                assert body == {"role": "operator", "label": "Ops", "expires_at": None, "max_uses": 1}
                return {
                    "invite": {
                        "id": "tinv_cli",
                        "team_id": "team_cli",
                        "role": "operator",
                        "label": "Ops",
                        "code": "tinv_code",
                    }
                }
            if path == "/teams/team_cli/invites/tinv_cli" and method == "DELETE":
                return {"removed": True}
            if path == "/teams/join" and method == "POST":
                assert body == {"code": "tinv_code", "display_name": "Operator"}
                return {
                    "team": {
                        "id": "team_cli",
                        "name": "CLI Team",
                        "slug": "cli-team",
                        "status": "active",
                        "member": {"role": "operator"},
                    },
                    "members": [{"id": "tmem_operator", "role": "operator", "status": "active", "display_name": "Operator"}],
                    "invites": [],
                    "recovery_codes": [],
                }
            if path == "/teams/team_cli/members/tmem_operator" and method == "PATCH":
                assert body == {"role": "admin"}
                return {"member": {"id": "tmem_operator", "role": "admin", "status": "active", "display_name": "Operator"}}
            if path == "/teams/team_cli/recovery/rotate" and method == "POST":
                return {"recovery_code": "trec_rotated", "recovery": {"id": "trec_cli", "team_id": "team_cli"}}
            if path == "/teams/team_cli/leave" and method == "POST":
                return {"removed": True}
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["team", "create", "CLI Team", "--slug", "cli-team", "--display-name", "Owner"]) == 0
    assert "recovery code: trec_cli" in capsys.readouterr().out
    assert cli_main.main(["team", "list"]) == 0
    assert "CLI Team" in capsys.readouterr().out
    assert cli_main.main(["team", "switch", "cli-team"]) == 0
    assert "team: team_cli" in capsys.readouterr().out
    config_path = tmp_path / ".config" / "darklab" / "config.toml"
    assert 'team = "team_cli"' in config_path.read_text(encoding="utf-8")
    assert cli_main.main(["team", "switch", "missing-team"]) == 1
    assert "team not found: missing-team" in capsys.readouterr().err
    assert 'team = "team_cli"' in config_path.read_text(encoding="utf-8")
    assert cli_main.main(["team", "info", "team_cli"]) == 0
    assert "Owner" in capsys.readouterr().out
    assert cli_main.main(["team", "invite", "create", "team_cli", "--role", "operator", "--label", "Ops"]) == 0
    assert "code: tinv_code" in capsys.readouterr().out
    assert cli_main.main(["team", "join", "tinv_code", "--display-name", "Operator"]) == 0
    assert "Operator" in capsys.readouterr().out
    assert cli_main.main(["team", "member", "update", "team_cli", "tmem_operator", "--role", "admin"]) == 0
    assert "admin" in capsys.readouterr().out
    assert cli_main.main(["team", "recovery", "rotate", "team_cli"]) == 0
    assert "trec_rotated" in capsys.readouterr().out
    assert cli_main.main(["team", "invite", "revoke", "team_cli", "tinv_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True
    assert cli_main.main(["team", "leave", "team_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True


def test_darklab_cli_schedule_commands_manage_api_schedules(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    schedule = {
        "id": "sch_cli",
        "enabled": True,
        "cron_expr": "0 * * * *",
        "cadence_preset": "hourly",
        "timezone": "UTC",
        "next_run_at": "2026-05-20T00:00:00+00:00",
        "last_run_at": "",
        "last_run_id": "",
        "consecutive_failures": 0,
        "label": "Hourly Echo",
        "paused_reason": "",
        "last_error": "",
        "created": "2026-05-19T23:00:00+00:00",
        "updated": "2026-05-19T23:30:00+00:00",
        "command_text": "echo 'hello world' 'semi;colon'",
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/schedules" and method == "POST":
                assert body == {
                    "command": "echo 'hello world' 'semi;colon'",
                    "cron_expr": None,
                    "cadence_preset": "hourly",
                    "label": "Hourly Echo",
                    "timezone": None,
                }
                return {"schedule": schedule}
            if path == "/schedules" and method == "GET":
                assert params == {"limit": 10, "offset": 0}
                return {"schedules": [schedule], "total": 1, "limit": 10, "offset": 0, "has_more": False}
            if path == "/schedules/sch_cli" and method == "GET":
                return {
                    "schedule": schedule,
                    "next_fires": [
                        "2026-05-20T00:00:00+00:00",
                        "2026-05-20T01:00:00+00:00",
                        "2026-05-20T02:00:00+00:00",
                    ],
                }
            if path == "/schedules/sch_cli" and method == "PATCH":
                assert body is not None
                updated = {**schedule, "enabled": bool(body["enabled"])}
                return {"schedule": updated}
            if path == "/schedules/sch_cli/run-now":
                return {
                    "status": "fired",
                    "fired_at": "2026-05-20T00:00:00+00:00",
                    "schedule": {**schedule, "last_run_at": "2026-05-20T00:00:00+00:00"},
                }
            if path == "/schedules/sch_cli/fires":
                assert params == {"limit": 5, "offset": 0}
                return {
                    "fires": [{
                        "fired_at": "2026-05-20T00:00:00+00:00",
                        "status": "fired",
                        "run_id": "",
                        "reason": "dispatch pending run integration",
                    }]
                }
            if path == "/schedules/sch_cli" and method == "DELETE":
                return {"removed": True}
            raise cli_main.DarklabCliError("not_found: missing")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main([
        "schedule",
        "create",
        "--every",
        "hourly",
        "--label",
        "Hourly Echo",
        "--",
        "echo",
        "hello world",
        "semi;colon",
    ]) == 0
    assert "sch_cli" in capsys.readouterr().out
    assert cli_main.main(["schedule", "create", "--every", "hourly", "echo", "missing separator"]) == 1
    assert "needs -- before the command" in capsys.readouterr().err
    assert cli_main.main(["schedule", "list", "--limit", "10"]) == 0
    list_output = capsys.readouterr().out
    assert "ENABLED" in list_output
    assert "Hourly Echo" in list_output
    assert cli_main.main(["schedule", "info", "sch_cli"]) == 0
    info_output = capsys.readouterr().out
    assert "Schedule" in info_output
    assert "Cadence" in info_output
    assert "Recent Fires" in info_output
    assert "2026-05-20 01:00:00 UTC" in info_output
    assert "echo 'hello world' 'semi;colon'" in info_output
    assert cli_main.main(["schedule", "pause", "sch_cli"]) == 0
    assert "no" in capsys.readouterr().out
    assert cli_main.main(["schedule", "resume", "sch_cli"]) == 0
    assert "yes" in capsys.readouterr().out
    assert cli_main.main(["schedule", "run", "sch_cli"]) == 0
    assert "fire: fired" in capsys.readouterr().out
    assert cli_main.main(["schedule", "fires", "sch_cli", "--limit", "5"]) == 0
    assert "dispatch pending run integration" in capsys.readouterr().out
    assert cli_main.main(["schedule", "delete", "sch_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True

    assert [call[1] for call in calls] == [
        "/schedules",
        "/schedules",
        "/schedules/sch_cli",
        "/schedules/sch_cli/fires",
        "/schedules/sch_cli",
        "/schedules/sch_cli",
        "/schedules/sch_cli/run-now",
        "/schedules/sch_cli/fires",
        "/schedules/sch_cli",
    ]


def test_darklab_cli_watch_commands_manage_api_watchers(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    watcher = {
        "id": "wtr_cli",
        "state": "ok",
        "state_reason": "",
        "baseline_run_id": "run_base",
        "last_run_id": "",
        "last_diff_summary": {
            "added_line_count": 1,
            "removed_line_count": 0,
        },
        "label": "Hourly Watch",
        "command_text": "nmap -sV darklab.sh",
        "options": {"suppress_removals": True, "notify_metadata_changes": False},
        "consecutive_no_change": 2,
        "consecutive_changed": 1,
        "consecutive_failures": 0,
        "created": "2026-05-19T23:00:00+00:00",
        "updated": "2026-05-19T23:30:00+00:00",
        "schedule": {
            "id": "sch_wtr_cli",
            "enabled": True,
            "cron_expr": "0 * * * *",
            "cadence_preset": "hourly",
            "timezone": "UTC",
            "next_run_at": "2026-05-20T01:00:00+00:00",
        },
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/watchers" and method == "POST":
                assert body is not None
                if body.get("baseline_mode") == "first_run":
                    assert body["baseline_run_id"] == ""
                    assert body["command"] == "nmap darklab.sh"
                    return {"watcher": {**watcher, "baseline_run_id": "", "state_reason": "pending_baseline"}}
                expected_body = {
                    "baseline_mode": "existing_run",
                    "baseline_run_id": "run_base",
                    "cron_expr": None,
                    "cadence_preset": "hourly",
                    "label": "Hourly Watch",
                    "timezone": None,
                    "enabled": True,
                    "options": {
                        "suppress_removals": bool(body.get("command")),
                        "notify_metadata_changes": False,
                    },
                }
                if body.get("command"):
                    expected_body["command"] = "nmap -sV darklab.sh"
                assert body == expected_body
                return {"watcher": watcher}
            if path == "/watchers" and method == "GET":
                assert params == {"limit": 10, "offset": 0}
                return {"watchers": [watcher], "total": 1, "limit": 10, "offset": 0, "has_more": False}
            if path == "/watchers/wtr_cli" and method == "GET":
                return {"watcher": watcher}
            if path == "/watchers/wtr_cli" and method == "PATCH":
                assert body is not None
                state = "paused" if body.get("state") == "paused" else "ok"
                return {"watcher": {**watcher, "state": state}}
            if path == "/watchers/wtr_cli/run-now":
                return {
                    "status": "fired",
                    "fired_at": "2026-05-20T00:00:00+00:00",
                    "watcher": {**watcher, "last_run_id": "run_fire"},
                }
            if path == "/watchers/wtr_cli/fires":
                assert params == {"limit": 5, "offset": 0}
                return {
                    "fires": [{
                        "created": "2026-05-20T00:00:00+00:00",
                        "diff_kind": "textual",
                        "state_at_fire": "changed",
                        "run_id": "run_fire",
                    }]
                }
            if path == "/watchers/wtr_cli/accept-baseline":
                assert body == {"run_id": "run_fire"}
                return {"watcher": {**watcher, "baseline_run_id": "run_fire"}}
            if path == "/watchers/wtr_cli" and method == "DELETE":
                return {"removed": True}
            raise cli_main.DarklabCliError("not_found: missing")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main([
        "watch",
        "create",
        "run_base",
        "--every",
        "hourly",
        "--label",
        "Hourly Watch",
        "--suppress-removals",
        "--",
        "nmap",
        "-sV",
        "darklab.sh",
    ]) == 0
    assert "wtr_cli" in capsys.readouterr().out
    assert cli_main.main(["watch", "create", "run_base", "--every", "hourly", "--label", "Hourly Watch"]) == 0
    assert "wtr_cli" in capsys.readouterr().out
    assert cli_main.main(["watch", "create", "--first-run", "--every", "hourly", "--", "nmap", "darklab.sh"]) == 0
    assert "wtr_cli" in capsys.readouterr().out
    monkeypatch.setattr(
        sys,
        "argv",
        ["darklab", "watch", "create", "--first-run", "--every", "hourly", "--", "nmap", "darklab.sh"],
    )
    assert cli_main.main() == 0
    assert "wtr_cli" in capsys.readouterr().out
    assert cli_main.main(["watch", "create", "run_base", "--every", "hourly", "--"]) == 1
    assert "needs a command after --" in capsys.readouterr().err
    assert cli_main.main(["watch", "list", "--limit", "10"]) == 0
    list_output = capsys.readouterr().out
    assert "STATE" in list_output
    assert "Hourly Watch" in list_output
    assert cli_main.main(["watch", "info", "wtr_cli"]) == 0
    info_output = capsys.readouterr().out
    assert "Watcher" in info_output
    assert "Baseline" in info_output
    assert "Cadence" in info_output
    assert "Health" in info_output
    assert "Recent Fires" in info_output
    assert "2026-05-20 00:00:00 UTC" in info_output
    assert "nmap -sV darklab.sh" in info_output
    assert "suppress-removals" in info_output
    assert cli_main.main(["watch", "pause", "wtr_cli"]) == 0
    assert "paused" in capsys.readouterr().out
    assert cli_main.main(["watch", "resume", "wtr_cli"]) == 0
    assert "ok" in capsys.readouterr().out
    assert cli_main.main(["watch", "run", "wtr_cli"]) == 0
    assert "fire: fired" in capsys.readouterr().out
    assert cli_main.main(["watch", "fires", "wtr_cli", "--limit", "5"]) == 0
    assert "textual" in capsys.readouterr().out
    assert cli_main.main(["watch", "accept", "wtr_cli", "--run-id", "run_fire"]) == 0
    assert "run_fire" in capsys.readouterr().out
    assert cli_main.main(["watch", "delete", "wtr_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True

    assert [call[1] for call in calls] == [
        "/watchers",
        "/watchers",
        "/watchers",
        "/watchers",
        "/watchers",
        "/watchers/wtr_cli",
        "/watchers/wtr_cli/fires",
        "/watchers/wtr_cli",
        "/watchers/wtr_cli",
        "/watchers/wtr_cli/run-now",
        "/watchers/wtr_cli/fires",
        "/watchers/wtr_cli/accept-baseline",
        "/watchers/wtr_cli",
    ]


def test_api_v1_openapi_generator_snapshot_is_current():
    from services.api_v1.openapi import openapi_spec

    checked_in = (ROOT_DIR / "docs" / "api-v1-openapi.json").read_text(encoding="utf-8")
    generated = json.dumps(openapi_spec(), indent=2, sort_keys=True) + "\n"

    assert generated == checked_in


def test_api_v1_openapi_contract_describes_public_shapes():
    from services.api_v1.openapi import openapi_spec

    spec = openapi_spec()
    schemas = spec["components"]["schemas"]
    assert {
        "ActiveRunList",
        "ApiError",
        "AtlasEntity",
        "AtlasEntityDetail",
        "AtlasEntityPage",
        "AtlasFinding",
        "AtlasFindingDetail",
        "AtlasFindingPage",
        "AtlasRunList",
        "AtlasSourceRun",
        "AtlasSummary",
        "ArtifactSummary",
        "EvidencePackage",
        "Health",
        "HistorySearchMatch",
        "HistorySearchPage",
        "NdjsonStream",
            "NotificationChannel",
            "NotificationChannelCreateRequest",
            "NotificationChannelKind",
            "NotificationChannelKindField",
            "NotificationChannelKindList",
            "NotificationChannelList",
            "NotificationChannelResponse",
            "NotificationChannelUpdateRequest",
            "NotificationEvent",
            "NotificationEventPage",
            "NotificationSecretField",
            "NotificationTriggerOption",
        "NotificationTestResponse",
        "Project",
        "ProjectCounts",
        "ProjectEntity",
        "ProjectEntityPage",
        "ProjectFinding",
        "ProjectFindingPage",
        "ProjectLink",
        "ProjectRunLinkResponse",
        "ProjectRun",
        "ProjectRunPage",
        "RunOutput",
        "RunPage",
        "RunStartRequest",
        "RunStreamEntity",
        "RunStarted",
        "Schedule",
        "ScheduleCreateRequest",
        "ScheduleFire",
        "ScheduleFirePage",
        "SchedulePage",
        "ScheduleResponse",
        "ScheduleRunNowResponse",
        "ScheduleUpdateRequest",
        "Team",
        "TeamCreateRequest",
        "TeamCreateResponse",
        "TeamDetail",
        "TeamInvite",
        "TeamInviteCreateRequest",
        "TeamInviteResponse",
        "TeamJoinRequest",
        "TeamList",
        "TeamMember",
        "TeamMemberResponse",
        "TeamMemberUpdateRequest",
        "TeamMembership",
        "TeamRecoveryCode",
        "TeamRecoveryRotateResponse",
        "Watcher",
        "WatcherAcceptBaselineRequest",
        "WatcherCreateRequest",
        "WatcherDiffSummary",
        "WatcherFire",
        "WatcherFirePage",
        "WatcherOptions",
        "WatcherPage",
        "WatcherResponse",
        "WatcherRunNowResponse",
        "WatcherUpdateRequest",
    }.issubset(schemas)
    assert spec["paths"]["/runs"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RunStartRequest"
    }
    assert spec["paths"]["/runs"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ActiveRunList"
    }
    assert spec["paths"]["/runs/{run_id}/stream"]["get"]["responses"]["200"]["content"]["application/x-ndjson"]["schema"] == {
        "$ref": "#/components/schemas/NdjsonStream"
    }
    assert spec["paths"]["/teams"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TeamList"
    }
    assert spec["paths"]["/teams"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/TeamCreateRequest"
    }
    assert spec["paths"]["/teams/{team_id}/invites"]["post"]["responses"]["403"]["description"] == (
        "Role lacks required team capability"
    )
    assert spec["paths"]["/teams/{team_id}/members/{member_id}"]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/TeamMemberUpdateRequest"}
    assert "capabilities" in schemas["TeamMembership"]["required"]
    assert schemas["TeamMembership"]["properties"]["capabilities"]["items"] == {"type": "string"}
    assert "capabilities" in schemas["TeamMember"]["required"]
    assert schemas["TeamMember"]["properties"]["capabilities"]["items"] == {"type": "string"}
    stream_schema = schemas["RunStreamEvent"]
    assert {
        "tsC",
        "tsE",
        "line_index",
        "command_root",
        "target",
        "entities",
    }.issubset(stream_schema["properties"])
    assert stream_schema["properties"]["entities"]["items"] == {"$ref": "#/components/schemas/RunStreamEntity"}
    assert {
        "type",
        "value",
        "canonical_value",
        "confidence",
        "source_line",
        "start",
        "end",
    }.issubset(schemas["RunStreamEntity"]["properties"])
    assert schemas["ProjectFindingPage"]["properties"]["findings"]["items"] == {"$ref": "#/components/schemas/ProjectFinding"}
    assert schemas["ProjectRunPage"]["properties"]["runs"]["items"] == {"$ref": "#/components/schemas/ProjectRun"}
    assert schemas["ProjectEntityPage"]["properties"]["entities"]["items"] == {"$ref": "#/components/schemas/ProjectEntity"}
    assert schemas["AtlasEntityPage"]["properties"]["entities"]["items"] == {"$ref": "#/components/schemas/AtlasEntity"}
    assert schemas["AtlasFindingPage"]["properties"]["findings"]["items"] == {"$ref": "#/components/schemas/AtlasFinding"}
    assert schemas["PackagePage"]["properties"]["packages"]["items"] == {"$ref": "#/components/schemas/EvidencePackage"}
    assert schemas["SchedulePage"]["properties"]["schedules"]["items"] == {"$ref": "#/components/schemas/Schedule"}
    assert schemas["ScheduleFirePage"]["properties"]["fires"]["items"] == {"$ref": "#/components/schemas/ScheduleFire"}
    assert schemas["ScheduleResponse"]["properties"]["next_fires"]["items"] == {"type": "string"}
    assert schemas["WatcherPage"]["properties"]["watchers"]["items"] == {"$ref": "#/components/schemas/Watcher"}
    assert schemas["WatcherFirePage"]["properties"]["fires"]["items"] == {"$ref": "#/components/schemas/WatcherFire"}
    schedule_schema = schemas["Schedule"]
    schedule_payload_fields = {field.name for field in fields(Schedule)} - {"session_token"}
    assert set(schedule_schema["properties"]) == schedule_payload_fields
    assert schedule_schema["additionalProperties"] is False
    assert schedule_schema["properties"]["cadence_preset"]["enum"] == list(CADENCE_PRESETS)
    assert spec["paths"]["/schedules"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ScheduleCreateRequest"
    }
    schedule_patch_schema = spec["paths"]["/schedules/{schedule_id}"]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert schedule_patch_schema == {"$ref": "#/components/schemas/ScheduleUpdateRequest"}
    schedule_fire_params = {param["name"] for param in spec["paths"]["/schedules/{schedule_id}/fires"]["get"]["parameters"]}
    assert {"schedule_id", "limit", "offset"}.issubset(schedule_fire_params)
    watcher_schema = schemas["Watcher"]
    watcher_payload_fields = {field.name for field in fields(Watcher)} - {"session_token"}
    assert set(watcher_schema["properties"]) == watcher_payload_fields | {"schedule"}
    assert watcher_schema["additionalProperties"] is False
    assert set(schemas["WatcherOptions"]["properties"]) == set(WATCHER_OPTION_DEFAULTS)
    watcher_fire_schema = schemas["WatcherFire"]
    assert set(watcher_fire_schema["properties"]) == {field.name for field in fields(WatcherFire)}
    assert spec["paths"]["/watchers"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WatcherCreateRequest"
    }
    watcher_patch_schema = spec["paths"]["/watchers/{watcher_id}"]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert watcher_patch_schema == {"$ref": "#/components/schemas/WatcherUpdateRequest"}
    watcher_fire_params = {param["name"] for param in spec["paths"]["/watchers/{watcher_id}/fires"]["get"]["parameters"]}
    assert {"watcher_id", "limit", "offset"}.issubset(watcher_fire_params)
    assert {"id", "run_id", "workspace_path", "display_name", "file_status"}.issubset(
        set(schemas["ArtifactSummary"]["required"])
    )
    history_params = {param["name"]: param for param in spec["paths"]["/history"]["get"]["parameters"]}
    assert {"q", "project_id", "run_kind", "limit", "offset"}.issubset(history_params)
    assert history_params["since"]["schema"]["format"] == "date-time"
    assert history_params["until"]["schema"]["format"] == "date-time"
    history_search_params = {param["name"]: param for param in spec["paths"]["/history/search"]["get"]["parameters"]}
    assert {"q", "context", "project_id", "since", "until", "limit", "offset"}.issubset(history_search_params)
    assert history_search_params["q"]["required"] is True
    assert schemas["HistorySearchPage"]["properties"]["matches"]["items"] == {"$ref": "#/components/schemas/HistorySearchMatch"}
    atlas_summary_params = {param["name"] for param in spec["paths"]["/atlas"]["get"]["parameters"]}
    assert {"project_id", "run_id", "orphan_filter", "suppression_filter"}.issubset(atlas_summary_params)
    atlas_entity_params = {param["name"] for param in spec["paths"]["/atlas/entities"]["get"]["parameters"]}
    assert {"entity_type", "q", "project_id", "run_id", "orphan_filter", "suppression_filter", "limit", "offset"}.issubset(
        atlas_entity_params
    )
    atlas_finding_params = {param["name"] for param in spec["paths"]["/atlas/findings"]["get"]["parameters"]}
    assert {"q", "project_id", "run_id", "review_state", "orphan_filter", "suppression_filter", "limit", "offset"}.issubset(
        atlas_finding_params
    )
    project_finding_params = {param["name"] for param in spec["paths"]["/projects/{project_id}/findings"]["get"]["parameters"]}
    assert {
        "command_root",
        "limit",
        "offset",
        "orphan_filter",
        "review_state",
        "run_id",
        "scope",
        "severity",
        "target_id",
    }.issubset(project_finding_params)
    project_entity_params = {param["name"] for param in spec["paths"]["/projects/{project_id}/entities"]["get"]["parameters"]}
    assert {"entity_type", "run_id", "target_id", "limit", "offset"}.issubset(project_entity_params)
    run_output_params = {param["name"] for param in spec["paths"]["/runs/{run_id}/output"]["get"]["parameters"]}
    assert {"format", "range"}.issubset(run_output_params)
    assert spec["paths"]["/runs/{run_id}/wait"]["post"]["responses"]["408"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiError"
    }
    project_link_schema = spec["paths"]["/runs/{run_id}/projects/{project_id}"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"]
    assert project_link_schema == {"$ref": "#/components/schemas/ProjectRunLinkResponse"}
    assert spec["paths"]["/notification-channels"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NotificationChannelCreateRequest"
    }
    notification_patch_schema = spec["paths"]["/notification-channels/{channel_id}"]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert notification_patch_schema == {"$ref": "#/components/schemas/NotificationChannelUpdateRequest"}
    assert schemas["NotificationChannelCreateRequest"]["required"] == ["kind"]
    assert "required" not in schemas["NotificationChannelUpdateRequest"]
    assert schemas["NotificationChannelCreateRequest"]["properties"]["secret_values"]["writeOnly"] is True
    assert schemas["NotificationChannelList"]["properties"]["channels"]["items"] == {
        "$ref": "#/components/schemas/NotificationChannel"
    }
    assert spec["paths"]["/notification-channel-kinds"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/NotificationChannelKindList"
    }
    assert schemas["NotificationChannelKindList"]["properties"]["kinds"]["items"] == {
        "$ref": "#/components/schemas/NotificationChannelKind"
    }
    assert schemas["NotificationChannelKind"]["properties"]["secret_fields"]["items"] == {
        "$ref": "#/components/schemas/NotificationChannelKindField"
    }
    assert schemas["NotificationEventPage"]["properties"]["events"]["items"] == {"$ref": "#/components/schemas/NotificationEvent"}
    notification_event_params = {param["name"] for param in spec["paths"]["/notification-events"]["get"]["parameters"]}
    assert {"channel_id", "trigger", "status", "limit", "offset"}.issubset(notification_event_params)
    assert set(spec["paths"]["/runs"]["post"]["responses"]) == {"202", "400", "401", "409", "429", "503"}
    for path, operations in spec["paths"].items():
        for operation in operations.values():
            assert "429" in operation["responses"]
            if path not in {"/health", "/openapi.json"}:
                assert "401" in operation["responses"]


def test_api_v1_whoami_last_seen_is_current_auth_timestamp(monkeypatch):
    import services.api_v1.auth as api_auth

    client = get_client()
    token = _token(client)

    monkeypatch.setattr(api_auth, "_now", lambda: "2026-05-19 01:00:00")
    first = json.loads(client.get("/api/v1/whoami", headers=_headers(token)).data)
    monkeypatch.setattr(api_auth, "_now", lambda: "2026-05-19 01:00:01")
    second = json.loads(client.get("/api/v1/whoami", headers=_headers(token)).data)

    assert first["last_seen_at"] == "2026-05-19 01:00:00"
    assert second["last_seen_at"] == "2026-05-19 01:00:01"
    with sqlite3.connect(DB_PATH) as conn:
        stored = conn.execute("SELECT last_seen_at FROM session_tokens WHERE token = ?", (token,)).fetchone()
    assert stored[0] == "2026-05-19 01:00:01"


def test_darklab_cli_sse_parser_reads_events():
    iter_sse_events = import_module("darklab_cli.client").iter_sse_events

    class FakeResponse:
        def __iter__(self):
            yield b"id: 1-0\n"
            yield b'data: {"type":"output","text":"ok"}\n'
            yield b"\n"

    assert list(iter_sse_events(FakeResponse())) == [
        {"type": "output", "text": "ok", "event_id": "1-0"}
    ]


def test_darklab_cli_config_flags_win_over_environment(monkeypatch):
    from argparse import Namespace

    load_config = import_module("darklab_cli.client").load_config

    monkeypatch.setenv("DARKLAB_API_URL", "http://env.example")
    monkeypatch.setenv("DARKLAB_TOKEN", "tok_env")
    monkeypatch.setenv("DARKLAB_TEAM", "team_env")

    config = load_config(Namespace(api_url="http://flag.example/", token="tok_flag", team="team_flag", timeout=2))

    assert config.api_url == "http://flag.example"
    assert config.token == "tok_flag"
    assert config.team == "team_flag"
    assert config.timeout == 2


def test_darklab_cli_team_member_update_requires_a_change(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, *_args, **_kwargs):
            raise AssertionError("CLI should reject empty member updates before making a request")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["team", "member", "update", "team_cli", "tmem_cli"]) == 1
    assert "team member update needs --role or --display-name" in capsys.readouterr().err


def test_darklab_cli_team_mutation_errors_surface(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    failures = {
        ("POST", "/teams/team_cli/invites"): "invite forbidden",
        ("POST", "/teams/team_cli/recovery/rotate"): "recovery forbidden",
        ("PATCH", "/teams/team_cli/members/tmem_cli"): "member update forbidden",
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, stream=False):
            del params, body, stream
            message = failures.get((method, path))
            if message:
                raise cli_main.DarklabCliError(message)
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    cases = (
        (["team", "invite", "create", "team_cli"], "invite forbidden"),
        (["team", "recovery", "rotate", "team_cli"], "recovery forbidden"),
        (["team", "member", "update", "team_cli", "tmem_cli", "--role", "admin"], "member update forbidden"),
    )
    for argv, message in cases:
        assert cli_main.main(argv) == 1
        assert message in capsys.readouterr().err


def test_darklab_cli_team_json_and_ndjson_shapes_are_stable(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    team = {
        "id": "team_cli",
        "name": "CLI Team",
        "slug": "cli-team",
        "status": "active",
        "member": {"id": "tmem_owner", "role": "owner", "display_name": "Owner"},
    }
    detail = {
        "team": team,
        "members": [{"id": "tmem_owner", "role": "owner", "status": "active", "display_name": "Owner"}],
        "invites": [{"id": "tinv_cli", "role": "operator", "label": "Ops"}],
        "recovery_codes": [{"id": "trec_cli", "created_at": "2026-05-28T00:00:00Z"}],
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, stream=False):
            del params, body, stream
            if method == "GET" and path == "/teams":
                return {"teams": [team], "total": 1}
            if method == "GET" and path == "/teams/team_cli":
                return detail
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["team", "list", "--format", "ndjson"]) == 0
    team_row = json.loads(capsys.readouterr().out)
    assert team_row["id"] == "team_cli"
    assert team_row["role"] == "owner"
    assert "teams" not in team_row

    assert cli_main.main(["team", "members", "team_cli", "--format", "ndjson"]) == 0
    member_row = json.loads(capsys.readouterr().out)
    assert member_row == {"id": "tmem_owner", "role": "owner", "status": "active", "display_name": "Owner"}

    assert cli_main.main(["team", "info", "team_cli", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["team"]["id"] == "team_cli"
    assert payload["members"][0]["id"] == "tmem_owner"
    assert payload["invites"][0]["id"] == "tinv_cli"


def test_darklab_cli_applies_team_scope_to_non_team_commands(monkeypatch, capsys, tmp_path):
    cli_main = import_module("darklab_cli.__main__")
    seen: list[tuple[str, str, str]] = []

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def request(self, method, path, *, params=None, body=None, stream=False):
            del params, body, stream
            seen.append((self.config.team, method, path))
            if method == "POST" and path == "/runs":
                return {"id": "run_cli", "status": "started", "stream_url": "/runs/run_cli/stream"}
            if method == "GET" and path == "/history":
                return {"runs": [], "total": 0, "limit": 50, "offset": 0, "has_more": False}
            if method == "GET" and path == "/watchers":
                return {"watchers": [], "total": 0, "limit": 50, "offset": 0, "has_more": False}
            if method == "GET" and path == "/notification-channels":
                return {"channels": []}
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["--team", "team_flag", "run", "echo hi", "--no-follow", "--format", "json"]) == 0
    json.loads(capsys.readouterr().out)

    monkeypatch.setenv("DARKLAB_TEAM", "team_env")
    assert cli_main.main(["history", "--format", "json"]) == 0
    json.loads(capsys.readouterr().out)

    monkeypatch.delenv("DARKLAB_TEAM")
    config_path = tmp_path / ".config" / "darklab" / "config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('team = "team_saved"\n', encoding="utf-8")
    assert cli_main.main(["watch", "list", "--format", "json"]) == 0
    json.loads(capsys.readouterr().out)

    assert cli_main.main(["--team", "team_notify", "notify", "list", "--format", "json"]) == 0
    json.loads(capsys.readouterr().out)

    assert seen == [
        ("team_flag", "POST", "/runs"),
        ("team_env", "GET", "/history"),
        ("team_saved", "GET", "/watchers"),
        ("team_notify", "GET", "/notification-channels"),
    ]


def test_darklab_cli_client_builds_authenticated_api_urls():
    client_module = import_module("darklab_cli.client")
    DarklabClient = client_module.DarklabClient
    DarklabConfig = client_module.DarklabConfig

    client = DarklabClient(DarklabConfig("http://example.test/base", "tok_123", 30))

    assert client._url("/history", {"q": "dark lab", "limit": 5}) == (
        "http://example.test/base/api/v1/history?q=dark+lab&limit=5"
    )


def test_darklab_cli_client_sends_bearer_header_and_formats_http_errors(monkeypatch):
    from email.message import Message
    import io
    import urllib.error

    client_module = import_module("darklab_cli.client")
    DarklabClient = client_module.DarklabClient
    DarklabCliError = client_module.DarklabCliError
    DarklabConfig = client_module.DarklabConfig
    seen = {}

    class FakeResponse:
        headers = {"Content-Type": "application/json"}

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, *, timeout):
        seen["authorization"] = req.get_header("Authorization")
        seen["team"] = req.get_header("X-team-id")
        seen["timeout"] = timeout
        if req.full_url.endswith("/missing"):
            raise urllib.error.HTTPError(
                req.full_url,
                404,
                "Not Found",
                Message(),
                io.BytesIO(b'{"error":{"code":"not_found","message":"missing"}}'),
            )
        return FakeResponse()

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)
    client = DarklabClient(DarklabConfig("http://example.test", "tok_cli", 2, team="team_cli"))

    assert client.request("GET", "/whoami") == {"ok": True}
    assert seen == {"authorization": "Bearer tok_cli", "team": "team_cli", "timeout": 2}
    try:
        client.request("GET", "/missing")
    except DarklabCliError as exc:
        assert str(exc) == "not_found: missing"
    else:
        raise AssertionError("expected HTTP error to fail")


def test_darklab_cli_config_preserves_http_scheme_and_port():
    from argparse import Namespace

    client_module = import_module("darklab_cli.client")
    DarklabClient = client_module.DarklabClient
    load_config = client_module.load_config

    config = load_config(Namespace(api_url="http://192.168.1.3:9999/", token="tok_flag", timeout=2))
    client = DarklabClient(config)

    assert config.api_url == "http://192.168.1.3:9999"
    assert client._url("/whoami") == "http://192.168.1.3:9999/api/v1/whoami"


def test_darklab_cli_config_file_uses_toml(monkeypatch, tmp_path):
    from argparse import Namespace

    load_config = import_module("darklab_cli.client").load_config
    config_dir = tmp_path / ".config" / "darklab"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        """
api_url = "http://config.example:9999" # inline comments are TOML
token = "tok_config"
team = "team_config"
timeout = 2.5
ignored = "value"

[nested]
ignored = true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    config = load_config(Namespace(api_url=None, token=None, timeout=None))

    assert config.api_url == "http://config.example:9999"
    assert config.token == "tok_config"
    assert config.team == "team_config"
    assert config.timeout == 2.5


def test_darklab_cli_config_save_enforces_owner_only_permissions(monkeypatch, tmp_path):
    client_module = import_module("darklab_cli.client")
    save_config_value = client_module.save_config_value
    path = tmp_path / ".config" / "darklab" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(
        '# local darklab settings\n'
        'token = "tok_existing" # keep this comment\n'
        'unknown = "preserved"\n'
        '\n'
        '[nested]\n'
        'ignored = true\n',
        encoding="utf-8",
    )
    path.chmod(0o644)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    save_config_value("team", "team_cli")
    saved = path.read_text(encoding="utf-8")

    assert '# local darklab settings\n' in saved
    assert 'token = "tok_existing" # keep this comment\n' in saved
    assert 'unknown = "preserved"\n' in saved
    assert 'team = "team_cli"\n[nested]\nignored = true\n' in saved
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_darklab_cli_config_requires_explicit_http_scheme():
    from argparse import Namespace

    client_module = import_module("darklab_cli.client")
    DarklabCliError = client_module.DarklabCliError
    load_config = client_module.load_config

    try:
        load_config(Namespace(api_url="192.168.1.3:9999", token="tok_flag", timeout=2))
    except DarklabCliError as exc:
        assert "http:// or https://" in str(exc)
    else:
        raise AssertionError("expected invalid api_url to fail")


def test_darklab_cli_run_requires_no_follow_for_json_start_payload(monkeypatch, capsys):
    main = import_module("darklab_cli.__main__").main
    calls = []

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, body=None, **_kwargs):
            calls.append((method, path, body))
            assert method == "POST"
            assert path == "/runs"
            assert body == {"command": "echo ok", "project_id": None}
            return {"id": "run_cli_json", "status": "running"}

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr("darklab_cli.__main__.DarklabClient", FakeClient)

    assert main(["run", "echo ok", "--format", "json"]) == 1
    assert "--no-follow --format json" in capsys.readouterr().err
    assert calls == []

    assert main(["run", "echo ok", "--no-follow", "--format", "ndjson"]) == 1
    assert "--format ndjson is stream-only" in capsys.readouterr().err
    assert calls == []

    assert main(["run", "echo ok", "--no-follow", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "run_cli_json"
    assert calls == [("POST", "/runs", {"command": "echo ok", "project_id": None})]


def test_darklab_cli_entrypoint_smoke_covers_readers_streams_and_errors(monkeypatch, capsys, tmp_path):
    cli_main = import_module("darklab_cli.__main__")
    help_text = cli_main._parser().format_help()
    assert "active            List active runs for the current token." in help_text
    assert "completion        Print or install shell completion for bash, zsh, or" in help_text
    assert "fish." in help_text
    assert "download          Download one artifact by id." in help_text
    assert "commands:" not in help_text
    assert cli_main.main(["completion", "bash"]) == 0
    bash_completion = capsys.readouterr().out
    assert "complete -F _darklab_completion darklab" in bash_completion
    assert "active artifacts atlas cancel completion download grep history notify" in bash_completion
    assert "atlas) _darklab_comp_words 'entities entity finding findings runs summary'" in bash_completion
    assert "team:invite) _darklab_word_in \"$word\" 'create revoke'" in bash_completion
    invite_create_completion = (
        "team:invite:create) _darklab_comp_words '--expires-at --format --help --label --max-uses --role -h'"
    )
    assert invite_create_completion in bash_completion
    assert "run:--format) _darklab_comp_words 'text json ndjson'; return ;;" in bash_completion
    assert "team:invite:create:--role) _darklab_comp_words 'owner admin operator viewer'; return ;;" in bash_completion
    assert "notify:create) _darklab_comp_words 'webhook slack discord telegram pushover email'" in bash_completion
    assert cli_main.main(["completion", "zsh"]) == 0
    zsh_completion = capsys.readouterr().out
    assert "#compdef darklab" in zsh_completion
    assert "team:invite) _darklab_word_in \"$word\" 'create revoke'" in zsh_completion
    assert "team:invite:create) _darklab_comp_words '--expires-at --format --help --label --max-uses --role -h'" in zsh_completion
    assert "compdef _darklab darklab" in zsh_completion
    assert cli_main.main(["completion", "fish"]) == 0
    fish_completion = capsys.readouterr().out
    assert "complete -c darklab -f -n '__fish_use_subcommand'" in fish_completion
    assert "-a 'webhook slack discord telegram pushover email'" in fish_completion
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert cli_main.main(["completion", "install"]) == 0
    install_output = capsys.readouterr().out
    bash_completion_path = tmp_path / "data" / "bash-completion" / "completions" / "darklab"
    assert f"Installed bash completion to {bash_completion_path}" in install_output
    assert "complete -F _darklab_completion darklab" in bash_completion_path.read_text(encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    assert cli_main.main(["completion", "install", "--shell", "fish"]) == 0
    fish_completion_path = tmp_path / "config" / "fish" / "completions" / "darklab.fish"
    assert f"Installed fish completion to {fish_completion_path}" in capsys.readouterr().out
    assert "complete -c darklab -f" in fish_completion_path.read_text(encoding="utf-8")

    class FakeResponse:
        def __iter__(self):
            yield b'{"type":"schema","event":"schema","v":1,"kind":"line_event"}\n'
            yield b'{"type":"output","event":"output","text":"ok","v":1,"kind":"info","role":"body","event_id":"1-0"}\n'
            yield b'{"type":"exit","code":0,"event_id":"2-0"}\n'

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, stream=False):
            if path == "/whoami":
                return {"token_created": "2026-05-19 00:00:00", "last_seen_at": "2026-05-19 00:00:01"}
            if path == "/projects":
                return {
                    "projects": [{"id": "prj_cli", "name": "CLI Project", "status": "active"}],
                    "has_more": False,
                }
            if path == "/history":
                return {
                    "runs": [
                        {
                            "id": "run_cli",
                            "status": "succeeded",
                            "exit_code": 0,
                            "finished": "2026-05-19T00:00:02+00:00",
                            "command": "echo ok",
                        },
                        {
                            "id": "run_old",
                            "status": "succeeded",
                            "exit_code": 0,
                            "finished": "2026-05-19T00:00:01+00:00",
                            "command": "date",
                        },
                    ],
                }
            if path == "/history/search":
                assert params == {
                    "project_id": None,
                    "since": None,
                    "until": None,
                    "limit": 50,
                    "offset": 0,
                    "q": "needle",
                    "context": 1,
                }
                return {
                    "matches": [
                        {
                            "run_id": "run_cli",
                            "command": "echo needle",
                            "line_number": 2,
                            "line": "needle here",
                            "context_before": ["before"],
                            "context_after": ["after"],
                        }
                    ],
                    "total": 1,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False,
                    "query": "needle",
                    "context": 1,
                }
            if path == "/runs/run_cli/output":
                assert params == {"format": "text", "range": None}
                return "ok\n"
            if path == "/runs/run_cli/stream" and stream:
                assert params == {"format": "ndjson", "after": "1-0"}
                return FakeResponse()
            if path == "/runs" and method == "GET":
                return {
                    "runs": [
                        {
                            "id": "run_active",
                            "started": "2026-05-19T00:00:03+00:00",
                            "status": "running",
                            "run_kind": "external",
                            "command": "sleep 30",
                        }
                    ],
                    "total": 1,
                }
            if path == "/runs" and method == "POST":
                if body == {"command": "echo linked", "project_id": "prj_cli"}:
                    return {"id": "run_wait", "status": "running"}
                assert body == {"command": "echo ok", "project_id": None}
                return {"id": "run_cli", "status": "running"}
            if path == "/runs/run_wait/wait":
                assert params == {"timeout": None}
                return {"run": {"id": "run_wait", "status": "succeeded", "exit_code": 0, "command": "echo linked"}}
            if path == "/projects/prj_cli/runs":
                return {"runs": [{"id": "run_cli", "started": "2026-05-19T00:00:00+00:00", "exit_code": 0, "command": "echo ok"}]}
            if path == "/runs/run_cli/projects/prj_cli" and method == "POST":
                return {"ok": True, "link": {"project_id": "prj_cli", "entity_id": "run_cli", "entity_type": "run"}}
            if path == "/runs/run_cli/projects/prj_cli" and method == "DELETE":
                return {"ok": True}
            if path == "/projects/prj_cli/entities":
                assert params == {"limit": 50, "offset": 0, "entity_type": "domain"}
                return {"entities": [{"id": "ent_cli", "type": "domain", "value": "darklab.sh"}]}
            if path == "/atlas":
                assert params == {
                    "q": None,
                    "project_id": None,
                    "run_id": None,
                    "entity_type": None,
                    "orphan_filter": "hide",
                    "suppression_filter": "hide",
                }
                return {"total": 1, "findings": 1, "counts": {"domain": 1}}
            if path == "/atlas/runs":
                assert params == {"q": None, "run_id": None, "limit": 30}
                return {"runs": [{"id": "run_cli", "entity_count": 1, "finding_count": 1, "command": "echo ok"}]}
            if path == "/atlas/entities":
                assert params == {
                    "q": None,
                    "project_id": None,
                    "run_id": None,
                    "entity_type": "domain",
                    "orphan_filter": "hide",
                    "suppression_filter": "hide",
                    "limit": 50,
                    "offset": 0,
                }
                return {"entities": [{"id": "ent_cli", "type": "domain", "occurrence_count": 2, "canonical_value": "darklab.sh"}]}
            if path == "/atlas/entities/ent_cli":
                return {"entity": {"id": "ent_cli", "type": "domain", "occurrence_count": 2, "canonical_value": "darklab.sh"}}
            if path == "/atlas/findings":
                assert params == {
                    "q": None,
                    "project_id": None,
                    "run_id": None,
                    "entity_type": None,
                    "orphan_filter": "hide",
                    "suppression_filter": "hide",
                    "limit": 50,
                    "offset": 0,
                    "review_state": [],
                }
                return {"findings": [{"id": "fnd_cli", "status": "new", "severity": "medium", "title": "Open port"}]}
            if path == "/atlas/findings/fnd_cli":
                return {"finding": {"id": "fnd_cli", "status": "new", "severity": "medium", "title": "Open port"}}
            raise cli_main.DarklabCliError("not_found: missing")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["whoami"]) == 0
    assert "token_created" in capsys.readouterr().out
    assert cli_main.main(["history"]) == 0
    history_lines = capsys.readouterr().out.splitlines()
    assert history_lines[0].startswith("FINISHED")
    assert history_lines[2].startswith("2026-05-19T00:00:01+00:00  run_old")
    assert history_lines[3].startswith("2026-05-19T00:00:02+00:00  run_cli")
    assert cli_main.main(["history", "--format", "ndjson"]) == 0
    ndjson_lines = capsys.readouterr().out.splitlines()
    assert json.loads(ndjson_lines[0])["id"] == "run_old"
    assert json.loads(ndjson_lines[1])["id"] == "run_cli"
    assert cli_main.main(["grep", "needle", "--context", "1"]) == 0
    assert "run_cli:2: needle here" in capsys.readouterr().out
    assert cli_main.main(["output", "run_cli"]) == 0
    assert capsys.readouterr().out == "ok\n"
    assert cli_main.main(["run", "echo ok", "--no-follow", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "run_cli"
    assert cli_main.main(["active"]) == 0
    active_output = capsys.readouterr().out
    assert "STARTED" in active_output
    assert "run_active" in active_output
    assert cli_main.main(["run", "echo linked", "--link-project", "CLI Project", "--wait"]) == 0
    assert "run_wait  succeeded  0  echo linked" in capsys.readouterr().out
    assert cli_main.main(["tail", "run_cli", "--format", "ndjson", "--after", "1-0"]) == 0
    tail_output = capsys.readouterr().out
    assert '"event":"schema"' in tail_output
    assert '"event":"output"' in tail_output
    assert '"event_id":"2-0"' in tail_output
    assert cli_main.main(["project-runs", "prj_cli"]) == 0
    assert "run_cli" in capsys.readouterr().out
    assert cli_main.main(["project-link", "run_cli", "prj_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["link"]["entity_id"] == "run_cli"
    assert cli_main.main(["project-unlink", "run_cli", "prj_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli_main.main(["project-entities", "prj_cli", "--entity-type", "domain"]) == 0
    assert "darklab.sh" in capsys.readouterr().out
    assert cli_main.main(["atlas", "summary"]) == 0
    assert "entities: 1" in capsys.readouterr().out
    assert cli_main.main(["atlas", "runs"]) == 0
    assert "run_cli" in capsys.readouterr().out
    assert cli_main.main(["atlas", "entities", "--entity-type", "domain"]) == 0
    assert "darklab.sh" in capsys.readouterr().out
    assert cli_main.main(["atlas", "entity", "ent_cli"]) == 0
    entity_output = capsys.readouterr().out
    assert "OCCURRENCES" in entity_output
    assert "ent_cli" in entity_output
    assert cli_main.main(["atlas", "findings"]) == 0
    assert "Open port" in capsys.readouterr().out
    assert cli_main.main(["atlas", "finding", "fnd_cli"]) == 0
    finding_output = capsys.readouterr().out
    assert "SEVERITY" in finding_output
    assert "fnd_cli" in finding_output
    assert cli_main.main(["project", "missing"]) == 1
    assert "not_found: missing" in capsys.readouterr().err


def test_darklab_cli_tail_text_does_not_double_space_output(capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeResponse:
        def __iter__(self):
            yield b'id: 1-0\n'
            yield b'data: {"type":"output","text":"row one\\n"}\n'
            yield b'\n'
            yield b'id: 2-0\n'
            yield b'data: {"type":"output","text":"row two\\r\\n"}\n'
            yield b'\n'
            yield b'id: 3-0\n'
            yield b'data: {"type":"output_batch","lines":[{"text":"row three"},{"text":"row four\\n"}]}\n'
            yield b'\n'
            yield b'id: 4-0\n'
            yield b'data: {"type":"exit","code":0}\n'
            yield b'\n'

    class FakeClient:
        def request(self, method, path, *, params=None, stream=False, **_kwargs):
            assert method == "GET"
            assert path == "/runs/run_cli_tail/stream"
            assert params == {"after": ""}
            assert stream is True
            return FakeResponse()

    assert cli_main._tail(FakeClient(), "run_cli_tail", "text") == 0
    assert capsys.readouterr().out == "row one\nrow two\nrow three\nrow four\n"


def test_darklab_cli_tail_handles_keyboard_interrupt(capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeResponse:
        def __iter__(self):
            raise KeyboardInterrupt
            yield b""

    class FakeClient:
        def request(self, method, path, *, params=None, stream=False, **_kwargs):
            assert method == "GET"
            assert path == "/runs/run_cli_interrupt/stream"
            assert params == {"after": ""}
            assert stream is True
            return FakeResponse()

    assert cli_main._tail(FakeClient(), "run_cli_interrupt", "text") == cli_main.STREAM_INTERRUPTED_EXIT_CODE
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "stopped following run run_cli_interrupt\n"


def test_darklab_cli_run_follow_interrupt_reports_run_id(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeResponse:
        def __iter__(self):
            raise KeyboardInterrupt
            yield b""

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, stream=False):
            if path == "/runs" and method == "POST":
                assert body == {"command": "sleep 30", "project_id": None}
                return {"id": "run_cli_follow_interrupt", "status": "running"}
            if path == "/runs/run_cli_follow_interrupt/stream" and method == "GET":
                assert params == {"after": ""}
                assert stream is True
                return FakeResponse()
            raise cli_main.DarklabCliError("unexpected request")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["run", "sleep 30"]) == cli_main.STREAM_INTERRUPTED_EXIT_CODE
    captured = capsys.readouterr()
    assert "run_cli_follow_interrupt" in captured.err
    assert "darklab tail run_cli_follow_interrupt" in captured.err


def test_darklab_cli_tail_text_fails_when_stream_has_no_terminal_event(capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeResponse:
        def __iter__(self):
            yield b'id: 1-0\n'
            yield b'data: {"type":"output","text":"partial row"}\n'
            yield b'\n'

    class FakeClient:
        def request(self, method, path, *, params=None, stream=False, **_kwargs):
            assert method == "GET"
            assert path == "/runs/run_cli_partial/stream"
            assert params == {"after": ""}
            assert stream is True
            return FakeResponse()

    assert cli_main._tail(FakeClient(), "run_cli_partial", "text") == cli_main.STREAM_INCOMPLETE_EXIT_CODE
    captured = capsys.readouterr()
    assert captured.out == "partial row\n"
    assert "terminal event" in captured.err


def test_darklab_cli_tail_ndjson_fails_when_stream_has_no_terminal_event(capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeResponse:
        def __iter__(self):
            yield b'{"type":"output","text":"partial row","event_id":"1-0"}\n'

    class FakeClient:
        def request(self, method, path, *, params=None, stream=False, **_kwargs):
            assert method == "GET"
            assert path == "/runs/run_cli_partial/stream"
            assert params == {"format": "ndjson", "after": ""}
            assert stream is True
            return FakeResponse()

    assert cli_main._tail(FakeClient(), "run_cli_partial", "ndjson") == cli_main.STREAM_INCOMPLETE_EXIT_CODE
    captured = capsys.readouterr()
    assert '"event_id":"1-0"' in captured.out
    assert "terminal event" in captured.err


def test_darklab_cli_download_rejects_unsafe_header_filename(tmp_path):
    cli_main = import_module("darklab_cli.__main__")
    client_module = import_module("darklab_cli.client")
    DarklabCliError = client_module.DarklabCliError
    DarklabClient = client_module.DarklabClient
    DarklabConfig = client_module.DarklabConfig

    download_help = cli_main._parser()._subparsers._group_actions[0].choices["download"].format_help()
    assert "darklab artifacts <run_id>" in download_help

    class FakeResponse:
        headers = {"Content-Disposition": 'attachment; filename="../../target"'}

    class FakeClient(DarklabClient):
        def request(self, *_args, **_kwargs):
            return FakeResponse()

    try:
        FakeClient(DarklabConfig("http://example.test", "tok_123", 30)).download("/history/run/artifacts/artifact", tmp_path)
    except DarklabCliError as exc:
        assert "unsafe path" in str(exc)
    else:
        raise AssertionError("expected unsafe filename to fail")


def test_darklab_cli_download_uses_rfc5987_filename(tmp_path):
    client_module = import_module("darklab_cli.client")
    DarklabClient = client_module.DarklabClient
    DarklabConfig = client_module.DarklabConfig

    class FakeResponse:
        headers = {"Content-Disposition": "attachment; filename*=UTF-8''scan%20report.txt"}
        sent = False

        def read(self, _size):
            if self.sent:
                return b""
            self.sent = True
            return b"report"

    class FakeClient(DarklabClient):
        def request(self, *_args, **_kwargs):
            return FakeResponse()

    target = FakeClient(DarklabConfig("http://example.test", "tok_123", 30)).download(
        "/history/run/artifacts/artifact",
        tmp_path,
    )

    assert target == tmp_path / "scan report.txt"
    assert target.read_bytes() == b"report"


def test_darklab_cli_download_refuses_to_overwrite_existing_file(tmp_path):
    client_module = import_module("darklab_cli.client")
    DarklabCliError = client_module.DarklabCliError
    DarklabClient = client_module.DarklabClient
    DarklabConfig = client_module.DarklabConfig
    target = tmp_path / "artifact.txt"
    target.write_text("existing", encoding="utf-8")

    class FakeResponse:
        headers = {"Content-Disposition": 'attachment; filename="artifact.txt"'}

    class FakeClient(DarklabClient):
        def request(self, *_args, **_kwargs):
            return FakeResponse()

    try:
        FakeClient(DarklabConfig("http://example.test", "tok_123", 30)).download("/history/run/artifacts/artifact", tmp_path)
    except DarklabCliError as exc:
        assert "refusing to overwrite" in str(exc)
    else:
        raise AssertionError("expected existing file to fail")
    assert target.read_text(encoding="utf-8") == "existing"
