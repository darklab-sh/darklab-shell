import json
import sqlite3
import sys
import uuid
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import app as shell_app
from core.database import DB_PATH


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


def _seed_run(session_id, *, command="echo api", output="ok"):
    run_id = "api_run_" + session_id[-8:]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs "
            "(id, session_id, run_kind, command, started, finished, exit_code, output, output_preview, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated, output_search_text) "
            "VALUES (?, ?, 'external', ?, '2026-05-19T00:00:00+00:00', "
            "'2026-05-19T00:00:01+00:00', 0, '', ?, 0, 1, 0, 0, ?)",
            (
                run_id,
                session_id,
                command,
                json.dumps([{"text": output, "cls": "", "tsC": "", "tsE": ""}]),
                output,
            ),
        )
        conn.commit()
    return run_id


def _create_project(client, token, *, name="API Project"):
    resp = client.post("/projects", json={"name": name}, headers={"X-Session-ID": token})
    assert resp.status_code == 201
    return json.loads(resp.data)["project"]


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


def test_api_v1_history_is_token_scoped_and_uses_page_envelope():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(token, command="echo api scoped", output="api scoped output")
    _seed_run(other_token, command="echo other", output="other output")

    resp = client.get("/api/v1/history?limit=10&offset=0&q=scoped", headers=_headers(token))
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert data["total"] >= 1
    assert any(item["id"] == run_id for item in data["runs"])
    assert all(item["command"] != "echo other" for item in data["runs"])

    valid_since = client.get("/api/v1/history?since=2026-05-19T00:00:00Z", headers=_headers(token))
    invalid_since = client.get("/api/v1/history?since=last-week", headers=_headers(token))
    invalid_until = client.get("/api/v1/history?until=tomorrow", headers=_headers(token))

    assert valid_since.status_code == 200
    assert invalid_since.status_code == 400
    assert invalid_until.status_code == 400
    assert json.loads(invalid_since.data)["error"]["code"] == "invalid_since"
    assert json.loads(invalid_until.data)["error"]["code"] == "invalid_until"


def test_api_v1_history_detail_output_and_cross_session_404():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(token, output="line one")
    with sqlite3.connect(DB_PATH) as conn:
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
    cross_session = client.get(f"/api/v1/history/{run_id}", headers=_headers(other_token))

    assert detail.status_code == 200
    detail_run = json.loads(detail.data)["run"]
    assert detail_run["id"] == run_id
    assert detail_run["label_count"] == 1
    assert detail_run["note_count"] == 1
    assert output.status_code == 200
    assert "line one" in output.get_data(as_text=True)
    assert json.loads(output_json.data)["lines"] == ["line one"]
    assert cross_session.status_code == 404


def test_api_v1_artifact_list_and_download_are_token_scoped(monkeypatch, tmp_path):
    from services.workspace.files import ensure_session_workspace

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    run_id = _seed_run(token, command="echo artifact", output="artifact")
    artifact_id = "rfa_" + uuid.uuid4().hex[:16]
    monkeypatch.setitem(shell_app.CFG, "workspace_enabled", True)
    monkeypatch.setitem(shell_app.CFG, "workspace_backend", "tmpfs")
    monkeypatch.setitem(shell_app.CFG, "workspace_root", str(tmp_path))
    monkeypatch.setitem(shell_app.CFG, "workspace_quota_mb", 1)
    monkeypatch.setitem(shell_app.CFG, "workspace_max_file_mb", 1)
    monkeypatch.setitem(shell_app.CFG, "workspace_max_files", 10)
    workspace_dir = ensure_session_workspace(token, shell_app.CFG)
    (workspace_dir / "reports").mkdir()
    (workspace_dir / "reports" / "artifact.txt").write_text("artifact body", encoding="utf-8")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
            "VALUES (?, ?, ?, 'reports/artifact.txt', 'artifact.txt', 'output', 13, 'test', "
            "'2026-05-19T00:00:01+00:00')",
            (artifact_id, token, run_id),
        )
        conn.commit()

    owner_list = client.get(f"/api/v1/history/{run_id}/artifacts", headers=_headers(token))
    cross_list = client.get(f"/api/v1/history/{run_id}/artifacts", headers=_headers(other_token))
    owner_download = client.get(f"/api/v1/history/{run_id}/artifacts/{artifact_id}", headers=_headers(token))
    cross_download = client.get(f"/api/v1/history/{run_id}/artifacts/{artifact_id}", headers=_headers(other_token))

    assert owner_list.status_code == 200
    assert json.loads(owner_list.data)["artifacts"][0]["id"] == artifact_id
    assert cross_list.status_code == 404
    assert owner_download.status_code == 200
    assert owner_download.data == b"artifact body"
    assert cross_download.status_code == 404


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
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO evidence_packages "
            "(id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated) "
            "VALUES (?, ?, ?, 'API Package', '', 'redacted', 0, '{}', 'draft', "
            "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00')",
            ("pkg_" + uuid.uuid4().hex[:16], token, project["id"]),
        )
        conn.commit()

    owner_project = client.get(f"/api/v1/projects/{project['id']}", headers=_headers(token))
    owner_findings = client.get(f"/api/v1/projects/{project['id']}/findings", headers=_headers(token))
    owner_packages = client.get(f"/api/v1/projects/{project['id']}/packages", headers=_headers(token))
    cross_project = client.get(f"/api/v1/projects/{project['id']}", headers=_headers(other_token))
    cross_findings = client.get(f"/api/v1/projects/{project['id']}/findings", headers=_headers(other_token))
    cross_packages = client.get(f"/api/v1/projects/{project['id']}/packages", headers=_headers(other_token))

    assert owner_project.status_code == 200
    assert json.loads(owner_project.data)["project"]["id"] == project["id"]
    assert owner_findings.status_code == 200
    assert json.loads(owner_findings.data)["findings"] == []
    assert owner_packages.status_code == 200
    assert json.loads(owner_packages.data)["total"] == 1
    assert cross_project.status_code == 404
    assert cross_findings.status_code == 404
    assert cross_packages.status_code == 404


def test_api_v1_run_start_uses_broker_and_streams_ndjson(monkeypatch):
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
    assert any(event.get("type") == "exit" and event.get("event_id") for event in events)


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
        assert next(stream) == ": heartbeat\n\n"
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


def test_api_v1_ndjson_stream_adapts_sse_heartbeat_comments():
    import blueprints.api_v1 as api_blueprint

    assert list(api_blueprint._ndjson_from_sse_chunks([": heartbeat\n\n"])) == ['{"type":"heartbeat"}\n']


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
    killed = {}

    monkeypatch.setattr(
        api_blueprint,
        "active_runs_for_session",
        lambda session_id: [{"run_id": run_id, "command": "sleep 30"}] if session_id == token else [],
    )
    monkeypatch.setattr(
        api_blueprint,
        "pid_pop_for_session",
        lambda requested_run_id, session_id: 4321 if requested_run_id == run_id and session_id == token else None,
    )
    monkeypatch.setattr(api_blueprint, "publish_run_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_blueprint.os, "killpg", lambda pid, sig: killed.update({"pid": pid, "sig": sig}))

    cross_stream = client.get(f"/api/v1/runs/{run_id}/stream", headers=_headers(other_token))
    owner_cancel = client.post(f"/api/v1/runs/{run_id}/cancel", headers=_headers(token))
    cross_cancel = client.post(f"/api/v1/runs/{run_id}/cancel", headers=_headers(other_token))

    assert cross_stream.status_code == 404
    assert owner_cancel.status_code == 200
    assert json.loads(owner_cancel.data) == {"killed": True, "id": run_id}
    assert killed["pid"] == 4321
    assert cross_cancel.status_code == 404


def test_api_v1_explicit_project_link_uses_finalized_run_path():
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
    project_resp = client.post("/projects", json={"name": "API Project"}, headers={"X-Session-ID": token})
    project = json.loads(project_resp.data)["project"]
    run_id = "api_project_link_run_" + uuid.uuid4().hex[:8]

    link = _save_completed_run(
        run_id,
        token,
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


def test_api_v1_openapi_route_matches_checked_in_contract():
    client = get_client()
    live = json.loads(client.get("/api/v1/openapi.json").data)
    checked_in = json.loads((ROOT_DIR / "docs" / "api-v1-openapi.json").read_text(encoding="utf-8"))

    assert live == checked_in


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
        "ApiError",
        "ArtifactSummary",
        "EvidencePackage",
        "Health",
        "NdjsonStream",
        "Project",
        "ProjectCounts",
        "ProjectFinding",
        "ProjectFindingPage",
        "RunOutput",
        "RunPage",
        "RunStartRequest",
        "RunStarted",
    }.issubset(schemas)
    assert spec["paths"]["/runs"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RunStartRequest"
    }
    assert spec["paths"]["/runs/{run_id}/stream"]["get"]["responses"]["200"]["content"]["application/x-ndjson"]["schema"] == {
        "$ref": "#/components/schemas/NdjsonStream"
    }
    assert schemas["ProjectFindingPage"]["properties"]["findings"]["items"] == {"$ref": "#/components/schemas/ProjectFinding"}
    assert schemas["PackagePage"]["properties"]["packages"]["items"] == {"$ref": "#/components/schemas/EvidencePackage"}
    assert {"id", "run_id", "workspace_path", "display_name", "file_status"}.issubset(
        set(schemas["ArtifactSummary"]["required"])
    )
    history_params = {param["name"]: param for param in spec["paths"]["/history"]["get"]["parameters"]}
    assert {"q", "project_id", "run_kind", "limit", "offset"}.issubset(history_params)
    assert history_params["since"]["schema"]["format"] == "date-time"
    assert history_params["until"]["schema"]["format"] == "date-time"
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

    config = load_config(Namespace(api_url="http://flag.example/", token="tok_flag", timeout=2))

    assert config.api_url == "http://flag.example"
    assert config.token == "tok_flag"
    assert config.timeout == 2


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
    client = DarklabClient(DarklabConfig("http://example.test", "tok_cli", 2))

    assert client.request("GET", "/whoami") == {"ok": True}
    assert seen == {"authorization": "Bearer tok_cli", "timeout": 2}
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
    assert config.timeout == 2.5


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


def test_darklab_cli_entrypoint_smoke_covers_readers_streams_and_errors(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeResponse:
        def __iter__(self):
            yield b'{"type":"output","text":"ok","event_id":"1-0"}\n'
            yield b'{"type":"exit","code":0,"event_id":"2-0"}\n'

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, stream=False):
            if path == "/whoami":
                return {"token_created": "2026-05-19 00:00:00", "last_seen_at": "2026-05-19 00:00:01"}
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
            if path == "/history/run_cli/output":
                return "ok\n"
            if path == "/runs/run_cli/stream" and stream:
                assert params == {"format": "ndjson", "after": "1-0"}
                return FakeResponse()
            if path == "/runs" and method == "POST":
                assert body == {"command": "echo ok", "project_id": None}
                return {"id": "run_cli", "status": "running"}
            raise cli_main.DarklabCliError("not_found: missing")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["whoami"]) == 0
    assert "token_created" in capsys.readouterr().out
    assert cli_main.main(["history"]) == 0
    history_lines = capsys.readouterr().out.splitlines()
    assert history_lines[0].startswith("2026-05-19T00:00:01+00:00  run_old")
    assert history_lines[1].startswith("2026-05-19T00:00:02+00:00  run_cli")
    assert cli_main.main(["history", "--format", "ndjson"]) == 0
    ndjson_lines = capsys.readouterr().out.splitlines()
    assert json.loads(ndjson_lines[0])["id"] == "run_old"
    assert json.loads(ndjson_lines[1])["id"] == "run_cli"
    assert cli_main.main(["output", "run_cli"]) == 0
    assert capsys.readouterr().out == "ok\n"
    assert cli_main.main(["run", "echo ok", "--no-follow", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "run_cli"
    assert cli_main.main(["tail", "run_cli", "--format", "ndjson", "--after", "1-0"]) == 0
    assert '"event_id":"2-0"' in capsys.readouterr().out
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
    assert capsys.readouterr().out == "row one\nrow two\n"


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
