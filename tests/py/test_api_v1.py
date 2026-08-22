# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import inspect
import json
import re
import sqlite3
import stat
import sys
import threading
import urllib.request
import uuid
from dataclasses import fields
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import app as shell_app_module
from conftest import make_test_app as _test_app
from conftest import reusable_test_app
import config
import core.process as process
from core.database import DB_PATH
from core.helpers import get_log_session_id
from extensions import limiter
from project_assessment_route_contracts import registered_assessment_mutations
from services.scheduler.models import CADENCE_PRESETS, Schedule
from services.watchers.models import WATCHER_OPTION_DEFAULTS, Watcher, WatcherFire
from werkzeug.serving import make_server


ROOT_DIR = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT_DIR / "tools" / "darklab_cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


def get_client():
    return reusable_test_app(__name__).test_client()


def _assert_openapi_payload(value, schema, components, path="$"):
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return _assert_openapi_payload(value, components[name], components, path)
    if value is None and schema.get("nullable"):
        return
    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                _assert_openapi_payload(value, candidate, components, path)
            except AssertionError:
                continue
            matches += 1
        assert matches == 1, f"{path}: expected exactly one schema match, got {matches}"
        return
    if "allOf" in schema:
        for candidate in schema["allOf"]:
            _assert_openapi_payload(value, candidate, components, path)
    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(value, dict), f"{path}: expected object"
        required = set(schema.get("required", []))
        assert required <= set(value), f"{path}: missing {sorted(required - set(value))}"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(properties), f"{path}: extra {sorted(set(value) - set(properties))}"
        for key, item in value.items():
            if key in properties:
                _assert_openapi_payload(item, properties[key], components, f"{path}.{key}")
    elif expected_type == "array":
        assert isinstance(value, list), f"{path}: expected array"
        for index, item in enumerate(value):
            _assert_openapi_payload(item, schema["items"], components, f"{path}[{index}]")
    elif expected_type == "string":
        assert isinstance(value, str), f"{path}: expected string"
    elif expected_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), f"{path}: expected integer"
    elif expected_type == "boolean":
        assert isinstance(value, bool), f"{path}: expected boolean"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} isn't in {schema['enum']!r}"
    if "pattern" in schema:
        assert isinstance(value, str) and re.fullmatch(schema["pattern"], value), (
            f"{path}: value doesn't match {schema['pattern']}"
        )


class _LiveCliServer:
    def __init__(self) -> None:
        self._server = make_server("127.0.0.1", 0, _test_app(), threaded=True)
        host, port = self._server.server_address[:2]
        self.base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _live_session_token(base_url: str) -> str:
    with urllib.request.urlopen(f"{base_url}/session/token/generate", timeout=5) as resp:  # nosec
        payload = json.loads(resp.read().decode("utf-8"))
    return str(payload["session_token"])


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


def _seed_assessment_target(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:16]
    entity_id = "ent_api_assessment_" + suffix
    run_id = "run_api_assessment_" + suffix
    target = f"assessment-{suffix}.example"
    observed_at = "2026-08-04T12:00:00+00:00"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, team_id, type, canonical_value, signature_hash, "
            "first_seen_at, last_seen_at, created) "
            "VALUES (?, ?, ?, 'domain', ?, ?, ?, ?, ?)",
            (
                entity_id,
                session_id,
                team_id,
                target,
                "sig_" + entity_id,
                observed_at,
                observed_at,
                observed_at,
            ),
        )
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, team_id, run_kind, command, started, finished, "
            "exit_code, output_preview, output_line_count, output_search_text) "
            "VALUES (?, ?, ?, 'external', ?, ?, ?, 0, '[]', 0, '')",
            (
                run_id,
                session_id,
                team_id,
                f"nmap -sV {target}",
                observed_at,
                observed_at,
            ),
        )
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, review_state, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', 'confirmed', ?)",
            ("pl_api_assessment_entity_" + suffix, project_id, entity_id, observed_at),
        )
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, review_state, created) "
            "VALUES (?, ?, 'run', ?, 'manual', 'confirmed', ?)",
            ("pl_api_assessment_run_" + suffix, project_id, run_id, observed_at),
        )
        conn.commit()
    return entity_id, run_id


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
    "api_project_assessments",
    "api_project_assessment",
    "api_project_assessment_delete_preview",
    "api_project_assessment_action_preview",
    "api_project_assessment_oast_correlations",
    "api_project_assessment_oast_correlation",
    "api_project_finding_verification_action_preview",
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
    "api_project_assessment_create": "_request_context(write=True)",
    "api_project_assessment_update": "_request_context(write=True)",
    "api_project_assessment_delete": "_request_context(write=True)",
    "api_project_assessment_check_update": "_request_context()",
    "api_project_assessment_evidence_link": "_request_context()",
    "api_project_assessment_evidence_unlink": "_request_context()",
    "api_project_finding_evidence_link": "Capability.TRIAGE_FINDINGS",
    "api_project_finding_evidence_unlink": "Capability.TRIAGE_FINDINGS",
    "api_project_manual_finding_create": "Capability.TRIAGE_FINDINGS",
    "api_project_manual_finding_update": "Capability.TRIAGE_FINDINGS",
    "api_osv_advisory_lookup": "Capability.TRIAGE_FINDINGS",
    "api_project_assessment_action_launch": "Capability.RUN_COMMANDS",
    "api_assessment_batch_start": "Capability.RUN_COMMANDS",
    "api_assessment_batch_retry": "Capability.RUN_COMMANDS",
    "api_assessment_batch_cancel": "Capability.RUN_COMMANDS",
    "api_project_assessment_oast_correlations": "Capability.RUN_COMMANDS",
    "api_project_assessment_oast_correlation": "Capability.RUN_COMMANDS",
    "api_project_assessment_oast_launch": "Capability.RUN_COMMANDS",
    "api_project_finding_verification_action_launch": "Capability.RUN_COMMANDS",
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
    import blueprints.api_v1_assessment_checks as assessment_checks_blueprint
    import blueprints.api_v1_assessments as assessments_blueprint
    import blueprints.api_v1_http_profiles as http_profiles_blueprint

    for route_name in _API_V1_TEAM_SCOPED_READ_ROUTES:
        source = inspect.getsource(getattr(api_blueprint, route_name))
        assert (
            "_api_request_scope(" in source
            or "_request_context(" in source
        ), route_name

    for route_name, capability_token in _API_V1_TEAM_SCOPED_WRITE_ROUTES.items():
        source = inspect.getsource(getattr(api_blueprint, route_name))
        assert any(token in source for token in (
            "_api_request_scope(",
            "_require_notification_manage_scope(",
            "_request_context(",
        )), route_name
        assert capability_token in source, route_name

    app = reusable_test_app(__name__)
    assessment_contracts = registered_assessment_mutations(
        app,
        route_prefix="/api/v1/projects",
    )
    assert assessment_contracts
    assert limiter.limit_manager.blueprint_limits(app, "api_v1")
    helper_capabilities = {
        "MUTATE_PROJECTS": (
            inspect.getsource(assessments_blueprint._request_context)
            + inspect.getsource(assessment_checks_blueprint._request_context)
        ),
        "MANAGE_SECRETS": inspect.getsource(http_profiles_blueprint._request_context),
    }
    for rule, _method, view, capability in assessment_contracts:
        source = inspect.getsource(view)
        declared = f"Capability.{capability}" in source
        if not declared and capability in helper_capabilities:
            declared = (
                "_request_context(" in source
                and f"Capability.{capability}" in helper_capabilities[capability]
            )
        assert declared, rule.endpoint


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

    with _test_app().test_request_context("/api/v1/whoami", headers=_headers(token)):
        try:
            current_api_session()
        except RuntimeError as exc:
            assert "require_api_auth" in str(exc)
        else:
            raise AssertionError("current_api_session should require the auth decorator cache")


def test_api_v1_osv_lookup_is_explicit_audited_and_privacy_safe(caplog):
    client = get_client()
    token = _token(client)
    package_purl = "pkg:pypi/private-package"
    package_version = "9.8.7-internal"
    provider_result = {
        "source": "osv",
        "outcome": "stored",
        "record_count": 2,
        "exact_version_count": 1,
        "range_count": 1,
    }

    with mock.patch(
        "blueprints.api_v1_osv_lookup.query_external_osv",
        return_value=provider_result,
    ) as lookup:
        response = client.post(
            "/api/v1/advisories/osv/lookup",
            headers=_headers(token),
            json={"purl": package_purl, "version": package_version},
        )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "source": "osv",
        "outcome": "stored",
        "record_count": 2,
    }
    assert lookup.call_args.args[1:] == (package_purl, package_version)
    audit = _audit_event_rows(
        target_id="osv",
        event_type="cve_advisory.refresh",
    )[-1]
    assert audit["target_type"] == "cve_risk_source"
    assert audit["details"] == {
        "origin": "external",
        "outcome": "stored",
        "record_count": 2,
        "source": "osv",
    }
    assert package_purl not in json.dumps(audit)
    assert package_version not in json.dumps(audit)
    assert package_purl not in caplog.text
    assert package_version not in caplog.text


def test_api_v1_osv_lookup_reports_disabled_failure_and_invalid_requests(caplog):
    client = get_client()
    token = _token(client)
    endpoint = "/api/v1/advisories/osv/lookup"
    body = {"purl": "pkg:pypi/requests", "version": "2.30.0"}

    with mock.patch(
        "blueprints.api_v1_osv_lookup.query_external_osv",
        return_value={"source": "osv", "outcome": "disabled"},
    ):
        disabled = client.post(endpoint, headers=_headers(token), json=body)
    with mock.patch(
        "blueprints.api_v1_osv_lookup.query_external_osv",
        return_value={"source": "osv", "outcome": "failed", "error": "URLError"},
    ):
        failed = client.post(endpoint, headers=_headers(token), json=body)
    with mock.patch("blueprints.api_v1_osv_lookup.query_external_osv") as lookup:
        invalid = client.post(
            endpoint,
            headers=_headers(token),
            json={"purl": ["pkg:pypi/requests"], "version": "2.30.0"},
        )
        extra = client.post(
            endpoint,
            headers=_headers(token),
            json={**body, "sbom": {"components": []}},
        )
    invalid_purl = "private-package-without-a-purl"
    invalid_version = "2.30.0-private"
    with mock.patch.dict(
        "config.CFG",
        {"cve_risk": {"osv_advisory_mode": "external"}},
    ), mock.patch(
        "services.cve_risk.osv_external.download_osv_query",
        side_effect=AssertionError("invalid package opened the provider boundary"),
    ):
        malformed = client.post(
            endpoint,
            headers=_headers(token),
            json={"purl": invalid_purl, "version": invalid_version},
        )

    assert disabled.status_code == 409
    assert disabled.get_json()["error"]["code"] == "osv_lookup_disabled"
    assert failed.status_code == 503
    assert failed.get_json()["error"]["code"] == "osv_lookup_failed"
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_osv_lookup"
    assert extra.status_code == 400
    assert extra.get_json()["error"]["code"] == "invalid_osv_lookup"
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "invalid_osv_lookup"
    lookup.assert_not_called()
    assert invalid_purl not in caplog.text
    assert invalid_version not in caplog.text


def test_api_v1_osv_lookup_requires_team_triage_capability():
    client = get_client()
    owner_token = _token(client)
    viewer_token = _token(client)
    operator_token = _token(client)
    team_id = _create_api_team(client, owner_token, name="OSV Lookup Team")
    _add_api_team_member(client, owner_token, viewer_token, team_id, role="viewer")
    _add_api_team_member(client, owner_token, operator_token, team_id, role="operator")
    endpoint = "/api/v1/advisories/osv/lookup"
    body = {"purl": "pkg:pypi/requests", "version": "2.30.0"}
    feed_status = [{
        "source": "epss",
        "status": "stale",
        "origin": "bundled",
        "source_version": "v2026.08.01:2026-08-01",
        "model_version": "v2026.08.01",
        "published_at": "2026-08-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "accepted_at": "2026-08-01T00:00:00Z",
        "age_hours": 504.0,
        "record_count": 100,
        "last_attempt_at": "",
        "last_error": "",
        "source_url": "https://epss.cyentia.com/epss_scores-current.csv.gz",
        "attribution": "FIRST EPSS",
        "terms_url": "https://www.first.org/epss/model",
        "live_refresh_enabled": False,
    }]

    with mock.patch(
        "blueprints.api_v1_cve_risk.get_configured_feed_status",
        return_value=feed_status,
    ) as status_read, mock.patch(
        "blueprints.api_v1_osv_lookup.query_external_osv",
        return_value={"source": "osv", "outcome": "negative_cached", "record_count": 0},
    ) as lookup:
        status_response = client.get(
            "/api/v1/risk/feeds",
            headers=_team_headers(viewer_token, team_id),
        )
        assert status_response.status_code == 200
        assert status_response.get_json() == {"feeds": feed_status, "total": 1}
        status_read.assert_called_once_with()
        viewer = client.post(
            endpoint,
            headers=_team_headers(viewer_token, team_id),
            json=body,
        )
        assert viewer.status_code == 403
        lookup.assert_not_called()
        operator = client.post(
            endpoint,
            headers=_team_headers(operator_token, team_id),
            json=body,
        )

    assert operator.status_code == 200
    assert operator.get_json()["outcome"] == "negative_cached"
    assert lookup.call_count == 1


def test_api_v1_read_routes_use_api_rate_limit(monkeypatch):
    client = get_client()
    token = _token(client)
    remote_addr = f"198.51.100.{int(uuid.uuid4().hex[:2], 16)}"
    monkeypatch.setitem(shell_app_module.CFG, "rate_limit_per_minute", 1)
    monkeypatch.setitem(shell_app_module.CFG, "rate_limit_per_second", 1)

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
    monkeypatch.setitem(shell_app_module.CFG, "rate_limit_per_minute", 1000)
    monkeypatch.setitem(shell_app_module.CFG, "rate_limit_per_second", 1000)
    monkeypatch.setitem(shell_app_module.CFG, "team_read_rate_limit_per_minute", 1)
    monkeypatch.setitem(shell_app_module.CFG, "team_read_rate_limit_per_second", 100)
    monkeypatch.setitem(shell_app_module.CFG, "team_write_rate_limit_per_minute", 1000)

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
    monkeypatch.setitem(shell_app_module.CFG, "rate_limit_per_minute", 1000)
    monkeypatch.setitem(shell_app_module.CFG, "rate_limit_per_second", 1000)
    monkeypatch.setitem(shell_app_module.CFG, "team_read_rate_limit_per_minute", 1000)
    monkeypatch.setitem(shell_app_module.CFG, "team_read_rate_limit_per_second", 1000)
    monkeypatch.setitem(shell_app_module.CFG, "team_write_rate_limit_per_minute", 1)

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
    from services.api_v1.openapi import openapi_spec

    schemas = openapi_spec()["components"]["schemas"]
    _assert_openapi_payload(data["runs"][0], schemas["RunSummary"], schemas)
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
    assert error_extra["http_status"] == 500
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


def test_api_v1_project_assessments_cover_cycle_check_and_evidence_contracts():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="API Assessment Project")
    _entity_id, run_id = _seed_assessment_target(token, project["id"])
    headers = _headers(token)

    created_response = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=headers,
        json={"profile_key": "network", "title": "External network review"},
    )
    assert created_response.status_code == 201
    created = json.loads(created_response.data)
    assessment = created["assessment"]
    assessment_id = assessment["id"]
    service_check = next(
        check for check in created["checks"]["checks"]
        if check["check_key"] == "service_discovery"
    )
    check_id = service_check["id"]
    serialized = json.dumps(created, sort_keys=True)
    assert token not in serialized
    for private_key in (
        "created_by_session_id",
        "updated_by_session_id",
        "state_changed_by_session_id",
        "source_path",
        "local_path",
    ):
        assert private_key not in serialized
    assert created["ok"] is True
    assert assessment["status"] == "active"
    assert assessment["profile_key"] == "network"
    assert created["checks"]["total"] == 3
    assert created["checks"]["has_more"] is False

    listed_response = client.get(
        f"/api/v1/projects/{project['id']}/assessments?status=active&limit=1",
        headers=headers,
    )
    filtered_response = client.get(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}"
        "?state=not_started&policy_level=standard&limit=1&offset=0"
        "&finding_priority=unscored&finding_limit=1&finding_offset=0",
        headers=headers,
    )
    cross_scope = client.get(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(other_token),
    )
    assert listed_response.status_code == 200
    listed = json.loads(listed_response.data)
    assert listed["total"] == 1
    assert listed["assessments"][0]["id"] == assessment_id
    assert {profile["key"] for profile in listed["profiles"]} == {
        "api",
        "combined",
        "network",
        "tls",
        "web",
    }
    assert all(profile["check_count"] > 0 for profile in listed["profiles"])
    assert all("checks" not in profile for profile in listed["profiles"])
    assert filtered_response.status_code == 200
    filtered = json.loads(filtered_response.data)
    assert filtered["checks"]["total"] == 1
    assert filtered["checks"]["checks"][0]["id"] == check_id
    assert sum(item["total_checks"] for item in filtered["target_rollups"]) == 3
    assert filtered["finding_deltas"] == {
        "comparison": {
            "status": "pending",
            "total_checks": 0,
            "comparable_checks": 0,
            "no_baseline_checks": 0,
            "incomparable_checks": 0,
        },
        "rollup": {
            "regressed": 0,
            "new": 0,
            "persistent": 0,
            "not_observed": 0,
            "incomparable": 0,
            "total": 0,
        },
        "items": [],
        "item_limit": 100,
        "truncated": False,
    }
    assert filtered["finding_worklist"] == {
        "items": [],
        "total": 0,
        "limit": 1,
        "offset": 0,
        "has_more": False,
        "priority": "unscored",
        "rollup": {
            "total": 0,
            "kev_listed": 0,
            "epss_scored": 0,
            "cvss_scored": 0,
            "unscored": 0,
        },
        "source_finding_count": 0,
    }
    assert filtered["retest_queue"] == {
        "groups": [],
        "rollup": {
            "ready_to_verify": 0,
            "needs_retest": 0,
            "total_findings": 0,
            "group_count": 0,
            "batch_launchable_groups": 0,
            "individual_only_groups": 0,
        },
        "batch_max_findings": 10,
        "truncated": False,
        "grouping_contract": (
            "Findings share a group only when Project target, Assessment check, action, "
            "and HTTP role/profile are identical. Different values stay individual."
        ),
        "partial_failure_contract": (
            "One shared run is linked to each finding independently after completion; "
            "one failed evidence link doesn't remove successful links."
        ),
        "disposition_contract": (
            "Retest evidence can suggest verified or needs retest, but a person must save "
            "the final finding disposition."
        ),
    }
    assert cross_scope.status_code == 404
    assert json.loads(cross_scope.data)["error"]["code"] == "not_found"

    blocked_response = client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}/checks/{check_id}",
        headers=headers,
        json={"state": "blocked", "reason": "Awaiting approved scan window"},
    )
    assert blocked_response.status_code == 200
    blocked = json.loads(blocked_response.data)
    assert blocked["check"]["state"] == "blocked"
    assert blocked["check"]["state_actor"] == {
        "kind": "session",
        "member_id": "",
    }

    cleared_response = client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}/checks/{check_id}",
        headers=headers,
        json={"state": "not_started"},
    )
    linked_response = client.post(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}/checks/{check_id}/evidence",
        headers=headers,
        json={"evidence_type": "run", "evidence_id": run_id},
    )
    assert cleared_response.status_code == 200
    assert linked_response.status_code == 201
    linked = json.loads(linked_response.data)
    assert linked["evidence"]["evidence_type"] == "run"
    assert linked["evidence"]["evidence_id"] == run_id
    assert linked["check"]["state"] == "covered"

    from services.assessments.nmap_service_evidence_persistence import (
        persist_nmap_xml_service_observations,
    )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        persist_nmap_xml_service_observations(
            conn,
            token,
            """<nmaprun version="7.95"><host><address addr="192.0.2.10" addrtype="ipv4"/>
            <ports><port protocol="tcp" portid="445"><state state="open"/>
            <service name="microsoft-ds"/><script id="smb2-security-mode" output="private output">
            <elem key="message_signing">disabled</elem></script></port></ports></host>
            <runstats><finished time="1786233600"/></runstats></nmaprun>""",
            source_run_id=run_id,
            observed_at="2026-08-09T00:01:00+00:00",
        )
        conn.commit()
    run_evidence_response = client.get(
        f"/api/v1/runs/{run_id}/service-evidence?limit=1&offset=0",
        headers=headers,
    )
    browser_evidence_response = client.get(
        f"/runs/{run_id}/service-evidence?limit=1&offset=0",
        headers={"X-Session-ID": token},
    )
    assessment_evidence_response = client.get(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}",
        headers=headers,
    )
    cross_run_evidence = client.get(
        f"/api/v1/runs/{run_id}/service-evidence",
        headers=_headers(other_token),
    )
    cross_browser_evidence = client.get(
        f"/runs/{run_id}/service-evidence",
        headers={"X-Session-ID": other_token},
    )
    assert run_evidence_response.status_code == 200
    run_evidence = run_evidence_response.get_json()
    assert run_evidence["total"] == 1
    assert run_evidence["observations"][0]["fields"] == [
        {"path": ["message_signing"], "value": "disabled"},
    ]
    assert "private output" not in json.dumps(run_evidence)
    assert browser_evidence_response.status_code == 200
    assert browser_evidence_response.get_json() == run_evidence
    assessment_check = next(
        item for item in assessment_evidence_response.get_json()["checks"]["checks"]
        if item["id"] == check_id
    )
    assert assessment_check["state"] == "covered"
    assert assessment_check["nmap_service_evidence"] == {
        **assessment_check["nmap_service_evidence"],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }
    assert assessment_check["nmap_service_evidence"]["observations"] == run_evidence["observations"]
    assert assessment_check["evidence_previews"] == {
        "evidence": [{
            **assessment_check["evidence_previews"]["evidence"][0],
            "id": linked["evidence"]["id"],
            "evidence_type": "run",
            "evidence_id": run_id,
            "source_state": "available",
            "linked_by": "manual",
        }],
        "total": 1,
        "limit": 3,
        "offset": 0,
        "has_more": False,
    }
    assert assessment_check["manual_evidence"] == {
        "evidence": [{
            **assessment_check["manual_evidence"]["evidence"][0],
            "id": linked["evidence"]["id"],
            "evidence_type": "run",
            "evidence_id": run_id,
            "source_state": "available",
            "linked_by": "manual",
        }],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }
    assert assessment_evidence_response.get_json()["recent_evidence"] == {
        "evidence": [{
            **assessment_evidence_response.get_json()["recent_evidence"]["evidence"][0],
            "id": linked["evidence"]["id"],
            "check_key": "service_discovery",
            "evidence_type": "run",
            "evidence_id": run_id,
            "source_state": "available",
            "linked_by": "manual",
        }],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }
    assert cross_run_evidence.status_code == 404
    assert cross_browser_evidence.status_code == 404

    evidence_link_id = linked["evidence"]["id"]
    unlinked_response = client.delete(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}/checks/{check_id}/"
        f"evidence/{evidence_link_id}",
        headers=headers,
    )
    assert unlinked_response.status_code == 200
    unlinked = json.loads(unlinked_response.data)
    assert unlinked["deleted"]["id"] == evidence_link_id
    assert unlinked["check"]["state"] == "not_started"

    renamed_response = client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}",
        headers=headers,
        json={"title": "Validated network review"},
    )
    completed_response = client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}",
        headers=headers,
        json={"status": "completed"},
    )
    archived_response = client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}",
        headers=headers,
        json={"status": "archived"},
    )
    preview_response = client.get(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}/delete-preview",
        headers=headers,
    )
    deleted_response = client.delete(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}",
        headers=headers,
    )
    assert renamed_response.status_code == 200
    assert json.loads(renamed_response.data)["assessment"]["title"] == "Validated network review"
    assert completed_response.status_code == 200
    assert json.loads(completed_response.data)["assessment"]["status"] == "completed"
    assert archived_response.status_code == 200
    assert json.loads(archived_response.data)["assessment"]["status"] == "archived"
    assert preview_response.status_code == 200
    preview = json.loads(preview_response.data)["preview"]
    assert preview["can_delete"] is True
    assert {
        "finding_check_comparisons",
        "finding_deltas",
        "dependent_comparisons_invalidated",
        "schemathesis_reports",
        "schemathesis_operations",
    }.issubset(preview["will_delete"])
    assert deleted_response.status_code == 200
    assert json.loads(deleted_response.data)["deleted"]["source_records_deleted"] is False

    audit_rows = _audit_event_rows(target_id=assessment_id)
    assert [row["event_type"] for row in audit_rows] == [
        "assessment.create",
        "assessment.update",
        "assessment.complete",
        "assessment.archive",
        "assessment.delete",
    ]
    assert all(row["details"]["source"] == "api_v1" for row in audit_rows)
    check_audits = _audit_event_rows(target_id=check_id)
    assert [row["event_type"] for row in check_audits] == [
        "assessment.check_state_change",
        "assessment.check_state_change",
        "assessment.evidence_link",
        "assessment.evidence_unlink",
    ]
    assert all(row["details"]["source"] == "api_v1" for row in check_audits)

    tls_response = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=headers,
        json={"profile_key": "tls"},
    )
    assert tls_response.status_code == 201
    tls_cycle = tls_response.get_json()
    assert tls_cycle["assessment"]["profile_key"] == "tls"
    assert tls_cycle["checks"]["total"] == 2
    certificate_check = next(
        item
        for item in tls_cycle["checks"]["checks"]
        if item["check_key"] == "certificate_chain"
    )
    tls_action_path = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{tls_cycle['assessment']['id']}/checks/{certificate_check['id']}/"
        "recommended-action"
    )
    tls_preview = client.get(tls_action_path, headers=headers)
    assert tls_preview.status_code == 200
    tls_plan = tls_preview.get_json()["plan"]
    assert tls_plan["action"] == {
        "key": "command:sslyze",
        "kind": "command",
        "id": "sslyze",
    }
    assert tls_plan["display_command"] == (
        f"sslyze --certinfo {certificate_check['target_value']}"
    )
    assert tls_plan["launchable"] is True
    tls_id = tls_cycle["assessment"]["id"]
    assert client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{tls_id}",
        headers=headers,
        json={"status": "completed"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/projects/{project['id']}/assessments/{tls_id}",
        headers=headers,
        json={"status": "archived"},
    ).status_code == 200
    assert client.delete(
        f"/api/v1/projects/{project['id']}/assessments/{tls_id}",
        headers=headers,
    ).status_code == 200

    combined_response = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=headers,
        json={"profile_key": "combined"},
    )
    assert combined_response.status_code == 201
    combined = combined_response.get_json()
    assert combined["assessment"]["profile_key"] == "combined"
    assert combined["checks"]["total"] == 11
    assert {item["check_key"] for item in combined["checks"]["checks"]} == {
        "certificate_chain",
        "content_discovery",
        "dns_inventory",
        "host_reachability",
        "http_profile",
        "intrusive_template_validation",
        "parameter_discovery",
        "service_discovery",
        "subdomain_takeover_confirmation",
        "tls_configuration",
        "vulnerability_templates",
    }


def test_api_v1_project_finding_verification_actions_are_guarded_and_scoped():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="API Verification Launch")
    entity_id, _run_id = _seed_assessment_target(token, project["id"])
    created = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "network", "title": "Verification source"},
    ).get_json()
    check = next(
        item for item in created["checks"]["checks"]
        if item["check_key"] == "service_discovery"
    )
    finding_id = "fnd_verification_action_" + uuid.uuid4().hex[:12]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, entity_id, signature_hash, tool_root, title, raw_line, created) "
            "VALUES (?, ?, ?, ?, 'nmap', 'Service needs verification', "
            "'saved service evidence', '2026-08-05T12:00:00+00:00')",
            (finding_id, token, entity_id, "sig_" + finding_id),
        )
        conn.commit()
    evidence_response = client.post(
        f"/api/v1/projects/{project['id']}/findings/{finding_id}/evidence",
        headers=_headers(token),
        json={"evidence_type": "assessment_check", "evidence_id": check["id"]},
    )
    assert evidence_response.status_code == 201

    path = (
        f"/api/v1/projects/{project['id']}/findings/{finding_id}/"
        f"verification-actions/{check['id']}"
    )
    preview_response = client.get(path, headers=_headers(token))
    cross_scope_response = client.get(path, headers=_headers(other_token))
    browser_preview = client.get(
        path.removeprefix("/api/v1"),
        headers={"X-Session-ID": token},
    )
    assert preview_response.status_code == 200
    assert cross_scope_response.status_code == 404
    plan = preview_response.get_json()["plan"]
    assert browser_preview.status_code == 200
    assert browser_preview.get_json()["plan"] == plan
    assert plan == {
        **plan,
        "project_id": project["id"],
        "finding_id": finding_id,
        "assessment_id": created["assessment"]["id"],
        "check_id": check["id"],
        "check_key": "service_discovery",
        "profile_key": "network",
        "profile_version": "1.0",
        "action": {"key": "command:nmap", "kind": "command", "id": "nmap"},
        "target": {
            "entity_id": entity_id,
            "type": "domain",
            "value": check["target_value"],
        },
        "policy_level": "standard",
        "http_profile": {"name": "", "credential_use": "none"},
        "scope": {
            "kind": "project_target",
            "project_id": project["id"],
            "target_count": 1,
            "fan_out": 1,
        },
        "launchable": True,
        "unavailable_reason": "",
        "requires_confirmation": True,
    }
    assert plan["display_command"].endswith(check["target_value"])
    assert plan["bounds"] == {
        "target_count": 1,
        "fan_out": 1,
        "request_limit": 100,
        "time_limit_seconds": 600,
        "credential_use": "none",
        "summary": (
            "One approved host, the top 100 TCP ports, and a 10-minute host timeout."
        ),
    }
    assert len(plan["plan_digest"]) == 64

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE project_links SET review_state = 'proposed' "
            "WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (project["id"], entity_id),
        )
        conn.commit()
    unavailable = client.get(path, headers=_headers(token)).get_json()["plan"]
    assert unavailable["launchable"] is False
    assert "no longer confirmed" in unavailable["unavailable_reason"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE project_links SET review_state = 'confirmed' "
            "WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
            (project["id"], entity_id),
        )
        conn.commit()

    confirmation_required = client.post(
        path,
        headers=_headers(token),
        json={"confirmed": False, "plan_digest": plan["plan_digest"]},
    )
    stale_plan = client.post(
        path,
        headers=_headers(token),
        json={"confirmed": True, "plan_digest": "0" * 64},
    )
    unsupported = client.post(
        path,
        headers=_headers(token),
        json={
            "confirmed": True,
            "plan_digest": plan["plan_digest"],
            "command": "echo bypass",
        },
    )
    assert confirmation_required.status_code == 409
    assert confirmation_required.get_json()["error"]["code"] == "confirmation_required"
    assert stale_plan.status_code == 409
    assert stale_plan.get_json()["error"]["code"] == "stale_plan"
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"]["code"] == "unsupported_fields"

    started = SimpleNamespace(run_id="run_verification_action", status="running")
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
             "blueprints.api_v1._start_brokered_run_service",
             return_value=started,
         ) as start_run, \
         mock.patch("blueprints.api_v1.log.info") as info_log:
        launched_response = client.post(
            path,
            headers=_headers(token),
            json={"confirmed": True, "plan_digest": plan["plan_digest"]},
        )

    assert launched_response.status_code == 202
    launched = launched_response.get_json()
    assert launched["run"] == {
        **launched["run"],
        "id": "run_verification_action",
        "run_id": "run_verification_action",
        "run_type": "external",
        "status": "running",
        "command": plan["display_command"],
        "stream_url": "/api/v1/runs/run_verification_action/stream",
        "history_url": "/api/v1/history/run_verification_action",
    }
    start_kwargs = start_run.call_args.kwargs
    assert start_kwargs["original_command"] == plan["display_command"]
    assert start_kwargs["display_command"] == plan["display_command"]
    assert start_kwargs["link_project_id"] == project["id"]
    assert start_kwargs["owner_tab_id"] == ""
    assert callable(start_kwargs["run_finalized_hook"])
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code) "
            "VALUES ('run_verification_action', ?, 'external', ?, "
            "'2026-08-05T12:01:00+00:00', '2026-08-05T12:02:00+00:00', 0)",
            (token, plan["display_command"]),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', 'run_verification_action', 'manual', "
            "'2026-08-05T12:02:00+00:00')",
            ("plr_" + uuid.uuid4().hex[:16], project["id"]),
        )
        conn.commit()
    start_kwargs["run_finalized_hook"]("run_verification_action", {
        "active_project_link": {"project_id": project["id"]},
        "finalize_summary": {"persisted": True},
    })
    with sqlite3.connect(DB_PATH) as conn:
        retained = conn.execute(
            "SELECT evidence_type, evidence_id FROM finding_evidence_links "
            "WHERE project_id = ? AND finding_id = ? AND evidence_type = 'retest_run'",
            (project["id"], finding_id),
        ).fetchone()
    assert tuple(retained) == ("retest_run", "run_verification_action")
    launch_log = next(
        call for call in info_log.call_args_list
        if call.args == ("API_PROJECT_VERIFICATION_ACTION_LAUNCHED",)
    )
    launch_log_fields = dict(launch_log.kwargs["extra"])
    assert launch_log_fields.pop("ip")
    assert launch_log_fields == {
        "session": get_log_session_id(token),
        "team_id": "",
        "project_id": project["id"],
        "finding_id": finding_id,
        "assessment_id": created["assessment"]["id"],
        "check_id": check["id"],
        "check_key": "service_discovery",
        "profile_key": "network",
        "profile_version": "1.0",
        "policy_level": "standard",
        "action_kind": "command",
        "action_id": "nmap",
        "run_id": "run_verification_action",
        "source": "api_v1",
    }
    audit = _audit_event_rows(
        target_id=check["id"], event_type="assessment.action_launch"
    )
    assert len(audit) == 1
    assert audit[0]["details"] == {
        "action": "command:nmap",
        "assessment_id": created["assessment"]["id"],
        "check_id": check["id"],
        "check_key": "service_discovery",
        "finding_id": finding_id,
        "policy_level": "standard",
        "profile_key": "network",
        "profile_version": "1.0",
        "project_id": project["id"],
        "run_id": "run_verification_action",
        "source": "api_v1",
    }
    assert check["target_value"] not in json.dumps(audit)
    assert plan["display_command"] not in json.dumps(audit)


def test_api_v1_project_assessment_recommended_actions_are_guarded_and_scoped():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="API Assessment Action")
    entity_id, _run_id = _seed_assessment_target(token, project["id"])
    created = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "network", "title": "Direct action source"},
    ).get_json()
    check = next(
        item for item in created["checks"]["checks"]
        if item["check_key"] == "service_discovery"
    )
    path = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{created['assessment']['id']}/checks/{check['id']}/recommended-action"
    )
    browser_path = path.removeprefix("/api/v1")

    preview_response = client.get(path, headers=_headers(token))
    browser_preview = client.get(
        browser_path,
        headers={"X-Session-ID": token},
    )
    cross_scope = client.get(path, headers=_headers(other_token))
    assert preview_response.status_code == 200
    assert browser_preview.status_code == 200
    assert cross_scope.status_code == 404
    plan = preview_response.get_json()["plan"]
    assert browser_preview.get_json()["plan"] == plan
    assert plan["finding_id"] == ""
    assert plan["project_id"] == project["id"]
    assert plan["assessment_id"] == created["assessment"]["id"]
    assert plan["check_id"] == check["id"]
    assert plan["action"] == {
        "key": "command:nmap",
        "kind": "command",
        "id": "nmap",
    }
    assert plan["target"] == {
        "entity_id": entity_id,
        "type": "domain",
        "value": check["target_value"],
    }
    assert plan["policy_level"] == "standard"
    assert plan["launchable"] is True

    stale = client.post(
        path,
        headers=_headers(token),
        json={"confirmed": True, "plan_digest": "0" * 64},
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "stale_plan"

    browser_started = SimpleNamespace(
        run_id="run_browser_assessment_action",
        status="running",
    )
    with mock.patch("blueprints.run.broker_available", return_value=True), \
         mock.patch(
             "blueprints.run._start_brokered_run_service",
             return_value=browser_started,
         ) as browser_start_run, \
         mock.patch("blueprints.projects.log.info") as browser_info_log:
        browser_launched_response = client.post(
            browser_path,
            headers={"X-Session-ID": token},
            json={"confirmed": True, "plan_digest": plan["plan_digest"]},
        )

    assert browser_launched_response.status_code == 202
    assert browser_launched_response.get_json()["run"]["run_id"] == (
        "run_browser_assessment_action"
    )
    browser_start_kwargs = browser_start_run.call_args.kwargs
    assert browser_start_kwargs["original_command"] == plan["display_command"]
    assert browser_start_kwargs["link_project_id"] == project["id"]
    assert "run_finalized_hook" not in browser_start_kwargs
    assert "output_signal_context" not in browser_start_kwargs
    browser_launch_log = next(
        call for call in browser_info_log.call_args_list
        if call.args == ("PROJECT_ASSESSMENT_ACTION_LAUNCHED",)
    )
    assert check["target_value"] not in json.dumps(
        browser_launch_log.kwargs["extra"]
    )
    assert plan["display_command"] not in json.dumps(
        browser_launch_log.kwargs["extra"]
    )

    started = SimpleNamespace(run_id="run_assessment_action", status="running")
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
             "blueprints.api_v1._start_brokered_run_service",
             return_value=started,
         ) as start_run, \
         mock.patch("blueprints.api_v1.log.info") as info_log:
        launched_response = client.post(
            path,
            headers=_headers(token),
            json={"confirmed": True, "plan_digest": plan["plan_digest"]},
        )

    assert launched_response.status_code == 202
    assert launched_response.get_json()["run"]["run_id"] == "run_assessment_action"
    start_kwargs = start_run.call_args.kwargs
    assert start_kwargs["original_command"] == plan["display_command"]
    assert start_kwargs["display_command"] == plan["display_command"]
    assert start_kwargs["link_project_id"] == project["id"]
    assert "run_finalized_hook" not in start_kwargs
    assert "output_signal_context" not in start_kwargs
    launch_log = next(
        call for call in info_log.call_args_list
        if call.args == ("API_PROJECT_ASSESSMENT_ACTION_LAUNCHED",)
    )
    launch_fields = dict(launch_log.kwargs["extra"])
    assert launch_fields.pop("ip")
    assert launch_fields == {
        "session": get_log_session_id(token),
        "team_id": "",
        "project_id": project["id"],
        "assessment_id": created["assessment"]["id"],
        "check_id": check["id"],
        "check_key": "service_discovery",
        "profile_key": "network",
        "profile_version": "1.0",
        "policy_level": "standard",
        "action_kind": "command",
        "action_id": "nmap",
        "run_id": "run_assessment_action",
        "source": "api_v1",
    }
    audit = _audit_event_rows(
        target_id=check["id"],
        event_type="assessment.action_launch",
    )
    assert len(audit) == 2
    assert {row["details"]["source"] for row in audit} == {"api_v1", "browser"}
    assert all("finding_id" not in row["details"] for row in audit)
    assert check["target_value"] not in json.dumps(audit)
    assert plan["display_command"] not in json.dumps(audit)

    from services.assessments.action_plans import AssessmentActionError

    cleanup = mock.Mock()
    protected = SimpleNamespace(
        execution_command=plan["display_command"],
        trusted_execution_args=(),
        private_values=(),
        cleanup=cleanup,
    )
    launch_error = AssessmentActionError(
        "takeover_template_unavailable",
        "The reviewed takeover template is unavailable.",
        status_code=503,
    )
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
            "services.assessments.run_launch.materialize_http_profile_launch",
             return_value=protected,
         ), \
         mock.patch(
             "services.assessments.run_launch.assessment_run_launch_context",
             side_effect=launch_error,
         ):
        failed_api_launch = client.post(
            path,
            headers=_headers(token),
            json={"confirmed": True, "plan_digest": plan["plan_digest"]},
        )
    assert failed_api_launch.status_code == 503
    assert failed_api_launch.get_json()["error"]["code"] == (
        "takeover_template_unavailable"
    )
    cleanup.assert_called_once_with()

    cleanup.reset_mock()
    with mock.patch("blueprints.run.broker_available", return_value=True), \
         mock.patch(
            "services.assessments.run_launch.materialize_http_profile_launch",
             return_value=protected,
         ), \
         mock.patch(
             "services.assessments.run_launch.assessment_run_launch_context",
             side_effect=launch_error,
         ):
        failed_browser_launch = client.post(
            browser_path,
            headers={"X-Session-ID": token},
            json={"confirmed": True, "plan_digest": plan["plan_digest"]},
        )
    assert failed_browser_launch.status_code == 503
    assert failed_browser_launch.get_json()["code"] == "takeover_template_unavailable"
    cleanup.assert_called_once_with()


def test_api_v1_assessment_action_launch_uses_protected_http_profile_material(
    monkeypatch,
    tmp_path,
):
    from services.assessments import http_profile_execution, http_profile_runtime

    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="Protected HTTP launch")
    _entity_id, _run_id = _seed_assessment_target(token, project["id"])
    assessment = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "web", "title": "Protected web checks"},
    ).get_json()
    check = next(
        item for item in assessment["checks"]["checks"]
        if item["check_key"] == "http_profile"
    )
    secret_value = "protected-profile-value"
    stored = client.post(
        "/session/secrets",
        headers={"X-Session-ID": token},
        json={"name": "ASSESSMENT_HTTP_TOKEN", "value": secret_value},
    )
    assert stored.status_code == 201
    profiles_path = f"/api/v1/projects/{project['id']}/http-profiles"
    profile_response = client.post(
        profiles_path,
        headers=_headers(token),
        json={
            "name": "Authenticated application",
            "role": "user",
            "base_url": f"https://{check['target_value']}",
            "allowed_hosts": [check["target_value"]],
            "headers": [{
                "name": "X-Assessment-Token",
                "secret_name": "ASSESSMENT_HTTP_TOKEN",
            }],
            "rate_limit_per_second": 3,
            "concurrency": 2,
        },
    )
    assert profile_response.status_code == 201
    profile_id = profile_response.get_json()["profile"]["id"]
    action_path = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{assessment['assessment']['id']}/checks/{check['id']}/recommended-action"
    )
    preview = client.get(
        action_path,
        headers=_headers(token),
        query_string={"http_profile_id": profile_id},
    )
    assert preview.status_code == 200
    plan = preview.get_json()["plan"]
    assert plan["http_profile"] == {
        "id": profile_id,
        "name": "Authenticated application",
        "role": "user",
        "credential_use": ["headers"],
        "scope": {
            "allowed_hosts": [check["target_value"]],
            "scope_roots": [f"https://{check['target_value']}"],
            "include_paths": [],
            "exclude_paths": [],
        },
        "enabled": True,
        "revision": 1,
        "rate_limit_per_second": 3,
        "concurrency": 2,
    }
    assert plan["bounds"]["credential_use"] == "protected_http_profile"
    assert plan["display_command"].endswith("-sf [protected]")
    assert secret_value not in preview.get_data(as_text=True)

    monkeypatch.setattr(http_profile_runtime, "_scanner_user_exists", lambda: False)
    monkeypatch.setattr(http_profile_runtime, "resolve_data_dir", lambda _cfg: str(tmp_path))
    started = SimpleNamespace(run_id="run_protected_http", status="running")
    profile_row = mock.Mock(wraps=http_profile_execution._profile_row)
    plan_context = mock.Mock(wraps=http_profile_execution.load_http_profile_plan_context)
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
             "blueprints.api_v1._start_brokered_run_service",
             return_value=started,
         ) as start_run, \
         mock.patch.object(http_profile_execution, "_profile_row", profile_row), \
         mock.patch.object(http_profile_execution, "load_http_profile_plan_context", plan_context), \
         mock.patch(
             "services.assessments.recommended_action_profiles.load_http_profile_plan_context",
             plan_context,
         ), \
         mock.patch("blueprints.api_v1.log.info") as info_log:
        launched = client.post(
            action_path,
            headers=_headers(token),
            json={
                "confirmed": True,
                "http_profile_id": profile_id,
                "plan_digest": plan["plan_digest"],
            },
        )

    assert launched.status_code == 202
    assert plan_context.call_count >= 1
    assert profile_row.call_count == plan_context.call_count
    start_kwargs = start_run.call_args.kwargs
    assert start_kwargs["original_command"].endswith("-rl 3 -threads 2")
    assert "[protected]" not in start_kwargs["original_command"]
    assert secret_value not in start_kwargs["original_command"]
    assert start_kwargs["display_command"] == plan["display_command"]
    assert start_kwargs["trusted_execution_args"][:1] == ("-sf",)
    secret_path = Path(start_kwargs["trusted_execution_args"][1])
    assert secret_path.is_file()
    assert stat.S_IMODE(secret_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
    secret_document = secret_path.read_text(encoding="utf-8")
    assert secret_value in secret_document
    assert check["target_value"] in secret_document
    assert secret_value in start_kwargs["private_values"]
    assert str(secret_path) in start_kwargs["private_values"]
    assert callable(start_kwargs["run_cleanup_hook"])
    serialized_launch = launched.get_data(as_text=True)
    assert secret_value not in serialized_launch
    launch_log = next(
        call for call in info_log.call_args_list
        if call.args == ("API_PROJECT_ASSESSMENT_ACTION_LAUNCHED",)
    )
    assert secret_value not in json.dumps(launch_log.kwargs["extra"])
    assert str(secret_path) not in json.dumps(launch_log.kwargs["extra"])
    audit = _audit_event_rows(
        target_id=check["id"],
        event_type="assessment.action_launch",
    )
    assert audit[-1]["details"]["profile_id"] == profile_id
    assert secret_value not in json.dumps(audit[-1])
    assert str(secret_path) not in json.dumps(audit[-1])
    start_kwargs["run_cleanup_hook"]()
    assert not secret_path.parent.exists()

    with sqlite3.connect(DB_PATH) as conn:
        snapshot_row = conn.execute(
            "SELECT profile_snapshot FROM project_assessments WHERE id = ?",
            (assessment["assessment"]["id"],),
        ).fetchone()
        snapshot = json.loads(snapshot_row[0])
        frozen_check = next(
            item for item in snapshot["checks"] if item["key"] == check["check_key"]
        )
        frozen_check["recommended_action"] = "command:curl"
        conn.execute(
            "UPDATE project_assessments SET profile_snapshot = ? WHERE id = ?",
            (json.dumps(snapshot), assessment["assessment"]["id"]),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET recommended_action_key = 'command:curl' "
            "WHERE id = ?",
            (check["id"],),
        )
        conn.commit()

    curl_preview = client.get(
        action_path,
        headers=_headers(token),
        query_string={"http_profile_id": profile_id},
    )
    assert curl_preview.status_code == 200
    curl_plan = curl_preview.get_json()["plan"]
    assert curl_plan["action"]["id"] == "curl"
    assert curl_plan["display_command"].startswith(
        "curl -q --silent --show-error --head --no-location"
    )
    assert curl_plan["display_command"].endswith("--config [protected]")
    assert curl_plan["bounds"]["request_limit"] == 1
    assert curl_plan["bounds"]["time_limit_seconds"] == 30

    curl_started = SimpleNamespace(run_id="run_protected_curl", status="running")
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
             "blueprints.api_v1._start_brokered_run_service",
             return_value=curl_started,
         ) as curl_start_run:
        curl_launched = client.post(
            action_path,
            headers=_headers(token),
            json={
                "confirmed": True,
                "http_profile_id": profile_id,
                "plan_digest": curl_plan["plan_digest"],
            },
        )

    assert curl_launched.status_code == 202
    curl_start_kwargs = curl_start_run.call_args.kwargs
    assert curl_start_kwargs["original_command"].endswith(
        f"https://{check['target_value']}"
    )
    assert curl_start_kwargs["trusted_execution_args"][:1] == ("--config",)
    curl_config_path = Path(curl_start_kwargs["trusted_execution_args"][1])
    assert curl_config_path.read_text(encoding="utf-8") == (
        f'header = "X-Assessment-Token: {secret_value}"\n'
    )
    assert secret_value in curl_start_kwargs["private_values"]
    assert str(curl_config_path) in curl_start_kwargs["private_values"]
    assert secret_value not in curl_launched.get_data(as_text=True)
    curl_start_kwargs["run_cleanup_hook"]()
    assert not curl_config_path.parent.exists()

    with sqlite3.connect(DB_PATH) as conn:
        snapshot_row = conn.execute(
            "SELECT profile_snapshot FROM project_assessments WHERE id = ?",
            (assessment["assessment"]["id"],),
        ).fetchone()
        snapshot = json.loads(snapshot_row[0])
        frozen_check = next(
            item for item in snapshot["checks"] if item["key"] == check["check_key"]
        )
        frozen_check["recommended_action"] = "command:dalfox"
        conn.execute(
            "UPDATE project_assessments SET profile_snapshot = ? WHERE id = ?",
            (json.dumps(snapshot), assessment["assessment"]["id"]),
        )
        conn.execute(
            "UPDATE project_assessment_checks SET recommended_action_key = 'command:dalfox' "
            "WHERE id = ?",
            (check["id"],),
        )
        conn.commit()

    dalfox_preview = client.get(
        action_path,
        headers=_headers(token),
        query_string={"http_profile_id": profile_id},
    )
    assert dalfox_preview.status_code == 200
    dalfox_plan = dalfox_preview.get_json()["plan"]
    assert dalfox_plan["action"]["id"] == "dalfox"
    assert "--only-discovery --skip-mining-dict --format jsonl" in (
        dalfox_plan["display_command"]
    )
    assert "--scan-timeout 60 --rate-limit 3 --workers 2" in (
        dalfox_plan["display_command"]
    )
    assert dalfox_plan["display_command"].endswith("--config [protected]")
    assert dalfox_plan["bounds"]["time_limit_seconds"] == 60

    dalfox_started = SimpleNamespace(run_id="run_protected_dalfox", status="running")
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
             "blueprints.api_v1._start_brokered_run_service",
             return_value=dalfox_started,
         ) as dalfox_start_run:
        dalfox_launched = client.post(
            action_path,
            headers=_headers(token),
            json={
                "confirmed": True,
                "http_profile_id": profile_id,
                "plan_digest": dalfox_plan["plan_digest"],
            },
        )

    assert dalfox_launched.status_code == 202
    dalfox_start_kwargs = dalfox_start_run.call_args.kwargs
    assert dalfox_start_kwargs["original_command"].endswith("--max-targets-per-host 1")
    assert dalfox_start_kwargs["trusted_execution_args"][:1] == ("--config",)
    dalfox_config_path = Path(dalfox_start_kwargs["trusted_execution_args"][1])
    assert json.loads(dalfox_config_path.read_text(encoding="utf-8")) == {
        "scan": {
            "follow_redirects": False,
            "headers": [f"X-Assessment-Token: {secret_value}"],
        },
    }
    assert secret_value in dalfox_start_kwargs["private_values"]
    assert str(dalfox_config_path) in dalfox_start_kwargs["private_values"]
    assert secret_value not in dalfox_launched.get_data(as_text=True)
    dalfox_start_kwargs["run_cleanup_hook"]()
    assert not dalfox_config_path.parent.exists()

    admin_token = _token(client)
    team_id = _create_api_team(client, token, name="Protected action revocation")
    _add_api_team_member(
        client,
        token,
        admin_token,
        team_id,
        role="admin",
    )
    team_project_response = client.post(
        "/projects",
        headers={"X-Session-ID": token, "X-Team-ID": team_id},
        json={"name": "Revoked protected launch"},
    )
    assert team_project_response.status_code == 201
    team_project_id = team_project_response.get_json()["project"]["id"]
    _seed_assessment_target(token, team_project_id, team_id=team_id)
    team_assessment = client.post(
        f"/api/v1/projects/{team_project_id}/assessments",
        headers=_team_headers(token, team_id),
        json={"profile_key": "web"},
    ).get_json()
    team_check = next(
        item for item in team_assessment["checks"]["checks"]
        if item["check_key"] == "http_profile"
    )
    team_secret = client.post(
        "/session/secrets",
        headers={"X-Session-ID": token, "X-Team-ID": team_id},
        json={"name": "TEAM_ASSESSMENT_TOKEN", "value": "team-protected-value"},
    )
    assert team_secret.status_code == 201
    team_profile_response = client.post(
        f"/api/v1/projects/{team_project_id}/http-profiles",
        headers=_team_headers(admin_token, team_id),
        json={
            "name": "Team administrator",
            "base_url": f"https://{team_check['target_value']}",
            "allowed_hosts": [team_check["target_value"]],
            "headers": [{
                "name": "X-Assessment-Token",
                "secret_name": "TEAM_ASSESSMENT_TOKEN",
            }],
        },
    )
    assert team_profile_response.status_code == 201
    team_profile_id = team_profile_response.get_json()["profile"]["id"]
    team_action_path = (
        f"/api/v1/projects/{team_project_id}/assessments/"
        f"{team_assessment['assessment']['id']}/checks/{team_check['id']}/"
        "recommended-action"
    )
    team_preview = client.get(
        team_action_path,
        headers=_team_headers(admin_token, team_id),
        query_string={"http_profile_id": team_profile_id},
    )
    assert team_preview.status_code == 200
    assert "team-protected-value" not in team_preview.get_data(as_text=True)

    from services.teams.storage import token_hash

    with sqlite3.connect(DB_PATH) as conn:
        admin_member_id = conn.execute(
            "SELECT id FROM team_members WHERE team_id = ? AND session_token_hash = ?",
            (team_id, token_hash(admin_token)),
        ).fetchone()[0]
    demoted = client.patch(
        f"/api/v1/teams/{team_id}/members/{admin_member_id}",
        headers=_headers(token),
        json={"role": "operator"},
    )
    assert demoted.status_code == 200
    assert demoted.get_json()["member"]["role"] == "operator"
    protected_paths_before_launch = set(tmp_path.rglob("*"))
    with mock.patch(
        "blueprints.api_v1_assessment_action_launch.confirm_recommended_action_plan"
    ) as confirm, mock.patch(
        "blueprints.api_v1_assessment_action_launch.materialize_assessment_run_launch"
    ) as materialize:
        revoked_launch = client.post(
            team_action_path,
            headers=_team_headers(admin_token, team_id),
            json={
                "confirmed": True,
                "http_profile_id": team_profile_id,
                "plan_digest": team_preview.get_json()["plan"]["plan_digest"],
            },
        )
    assert revoked_launch.status_code == 403
    assert revoked_launch.get_json()["error"]["code"] == "team_forbidden"
    confirm.assert_not_called()
    materialize.assert_not_called()
    assert set(tmp_path.rglob("*")) == protected_paths_before_launch


def test_api_v1_assessment_schemathesis_action_selects_and_protects_saved_schema():
    from services.assessments.schemathesis_schema import review_local_openapi_json

    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="Saved API contract")
    entity_id, run_id = _seed_assessment_target(token, project["id"])
    target = f"https://api-{uuid.uuid4().hex[:12]}.example/v1"
    artifact_id = "rfa_" + uuid.uuid4().hex[:16]
    content = json.dumps({
        "openapi": "3.1.0",
        "info": {"title": "Saved API", "version": "1"},
        "paths": {
            "/items": {"get": {"responses": {"200": {"description": "OK"}}}},
            "/health": {"head": {"responses": {"200": {"description": "OK"}}}},
        },
    }, separators=(",", ":")).encode()
    reviewed = review_local_openapi_json(
        content,
        source_artifact_id=artifact_id,
        base_url=target,
    )
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE entities SET type = 'url', canonical_value = ?, signature_hash = ? "
            "WHERE id = ?",
            (target, "sig_url_" + uuid.uuid4().hex, entity_id),
        )
        conn.execute(
            "UPDATE runs SET command = ? WHERE id = ?",
            (f"curl -I {target}", run_id),
        )
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, content_sha256, created) VALUES "
            "(?, ?, ?, 'reports/openapi.json', 'openapi.json', 'output', ?, "
            "'test', 'application/json', ?, '2026-08-08T00:00:00+00:00')",
            (artifact_id, token, run_id, len(content), reviewed.source_sha256),
        )
        conn.commit()
    assessment = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "api", "title": "Saved API assessment"},
    ).get_json()
    check = assessment["checks"]["checks"][0]
    action_path = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{assessment['assessment']['id']}/checks/{check['id']}/recommended-action"
    )
    choose = client.get(action_path, headers=_headers(token)).get_json()["plan"]

    assert choose["launchable"] is False
    assert choose["artifact_selection"]["options"][0]["artifact_id"] == artifact_id
    assert choose["artifact_selection"]["selected"] is None

    schema_path = Path("/tmp/private-http-runs/run-0123456789abcdef/schema.json")
    config_path = Path("/tmp/private-http-runs/run-0123456789abcdef/schemathesis.toml")
    report_path = Path("/tmp/private-http-runs/run-0123456789abcdef/events.ndjson")
    cleanup = mock.Mock()
    material = SimpleNamespace(
        schema=reviewed,
        schema_path=schema_path,
        config_path=config_path,
        report_path=report_path,
        private_values=(str(schema_path), str(config_path), str(report_path)),
        read_report=lambda: b"",
        cleanup=cleanup,
    )
    with mock.patch(
        "services.assessments.schemathesis_actions.review_project_openapi_artifact",
        return_value=reviewed,
    ), mock.patch(
        "services.assessments.schemathesis_launch.review_project_openapi_artifact",
        return_value=reviewed,
    ), mock.patch(
        "services.assessments.schemathesis_launch.materialize_reviewed_schemathesis_schema",
        return_value=material,
    ):
        selected_response = client.get(
            action_path,
            headers=_headers(token),
            query_string={"schema_artifact_id": artifact_id},
        )
        plan = selected_response.get_json()["plan"]
        started = SimpleNamespace(run_id="run_api_negative", status="running")
        with mock.patch("blueprints.api_v1.broker_available", return_value=True), mock.patch(
            "blueprints.api_v1._start_brokered_run_service",
            return_value=started,
        ) as start_run:
            launched = client.post(
                action_path,
                headers=_headers(token),
                json={
                    "confirmed": True,
                    "plan_digest": plan["plan_digest"],
                    "schema_artifact_id": artifact_id,
                },
            )

    assert selected_response.status_code == 200
    assert plan["launchable"] is True
    assert plan["artifact_selection"]["selected"]["operation_count"] == 2
    assert plan["display_command"].startswith(
        "schemathesis --config-file [protected-config] run [protected-schema]"
    )
    assert launched.status_code == 202
    start_kwargs = start_run.call_args.kwargs
    assert start_kwargs["original_command"] == "schemathesis --help"
    assert start_kwargs["display_command"] == plan["display_command"]
    assert start_kwargs["private_values"] == (
        str(schema_path), str(config_path), str(report_path),
    )
    assert start_kwargs["reviewed_execution"].execution_command.startswith(
        f"schemathesis --config-file {config_path} run {schema_path}"
    )
    assert callable(start_kwargs["run_cleanup_hook"])
    audit = _audit_event_rows(
        target_id=check["id"],
        event_type="assessment.action_launch",
    )[-1]
    assert audit["details"]["schema_artifact_id"] == artifact_id
    assert audit["details"]["schema_operation_count"] == 2
    assert str(schema_path) not in json.dumps(audit)
    start_kwargs["run_cleanup_hook"]()
    cleanup.assert_called_once_with()


def test_api_v1_intrusive_nuclei_action_requires_gate_and_fresh_confirmation(
    monkeypatch,
):
    from services.assessments import action_plan_nuclei, nuclei_takeover_launch
    from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
    from services.runs.signal_context import RunOutputSignalContext

    snapshot = NucleiTemplateCacheSnapshot(
        "ready", "v10.4.3", "sha256:" + ("b" * 64), 11997,
    )
    monkeypatch.setattr(
        action_plan_nuclei, "managed_nuclei_template_snapshot", lambda: snapshot,
    )
    monkeypatch.setattr(
        nuclei_takeover_launch, "managed_nuclei_template_snapshot", lambda: snapshot,
    )
    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="Intrusive Nuclei action")
    _entity_id, _run_id = _seed_assessment_target(token, project["id"])
    assessment = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "web", "title": "Intrusive template review"},
    ).get_json()
    check = next(
        item for item in assessment["checks"]["checks"]
        if item["check_key"] == "intrusive_template_validation"
    )
    action_path = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{assessment['assessment']['id']}/checks/{check['id']}/recommended-action"
    )

    disabled = client.get(action_path, headers=_headers(token)).get_json()["plan"]
    assert disabled["launchable"] is False
    assert "operator opt-in" in disabled["unavailable_reason"]

    monkeypatch.setitem(config.CFG, "assessment_intrusive_actions_enabled", True)
    preview = client.get(action_path, headers=_headers(token))
    plan = preview.get_json()["plan"]
    assert preview.status_code == 200
    assert plan["launchable"] is True
    assert plan["policy_level"] == "intrusive"
    assert plan["nuclei_profile"]["key"] == "intrusive"
    assert "-headless -system-chrome -headless-options --no-sandbox -dast" in (
        plan["display_command"]
    )

    monkeypatch.setitem(config.CFG, "assessment_intrusive_actions_enabled", False)
    stale = client.post(
        action_path,
        headers=_headers(token),
        json={"confirmed": True, "plan_digest": plan["plan_digest"]},
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "stale_plan"

    monkeypatch.setitem(config.CFG, "assessment_intrusive_actions_enabled", True)
    refreshed_plan = client.get(
        action_path, headers=_headers(token),
    ).get_json()["plan"]
    started = SimpleNamespace(run_id="run_intrusive_nuclei", status="running")
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), mock.patch(
        "blueprints.api_v1._start_brokered_run_service",
        return_value=started,
    ) as start_run:
        launched = client.post(
            action_path,
            headers=_headers(token),
            json={
                "confirmed": True,
                "plan_digest": refreshed_plan["plan_digest"],
            },
        )

    assert launched.status_code == 202
    assert start_run.call_args.kwargs["output_signal_context"] == RunOutputSignalContext(
        nuclei_template_snapshot=snapshot,
    )


def test_assessment_oast_preview_reservation_and_status_are_private_and_scoped(
    monkeypatch,
    tmp_path,
):
    from services.assessments.dalfox_oast_actions import DalfoxParameterOptions
    from services.assessments.dalfox_parameter_evidence import (
        ReviewedDalfoxParameterEvidence,
    )
    from services.assessments.dalfox_parameter_observations import (
        DALFOX_DISCOVERY_PARSER_VERSION,
        dalfox_parameter_observation_id,
    )
    from services.connectors.oast_config import OastConnectorSettings

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="Private OAST review")
    entity_id, source_run_id = _seed_assessment_target(token, project["id"])
    target = f"https://oast-{uuid.uuid4().hex[:12]}.example.test/search?q=one"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE entities SET type = 'url', canonical_value = ?, signature_hash = ? "
            "WHERE id = ?",
            (target, "sig_oast_" + uuid.uuid4().hex, entity_id),
        )
        conn.commit()
    created = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "web", "title": "Private OAST review"},
    ).get_json()
    check = next(
        item for item in created["checks"]["checks"]
        if item["check_key"] == "blind_xss_validation"
    )
    observation_id = dalfox_parameter_observation_id(
        source_run_id,
        target,
        "Query",
        "q",
    )
    evidence = ReviewedDalfoxParameterEvidence(
        source_run_id=source_run_id,
        observation_id=observation_id,
        target=target,
        parameter="q",
        location="Query",
        tool_version="2.12.0",
        parser_version=DALFOX_DISCOVERY_PARSER_VERSION,
    )
    monkeypatch.setattr(
        "services.assessments.dalfox_oast_actions."
        "list_project_dalfox_parameter_options",
        lambda *_args, **_kwargs: DalfoxParameterOptions((evidence,)),
    )
    monkeypatch.setitem(config.CFG, "data_dir", str(tmp_path))
    monkeypatch.setitem(config.CFG, "assessment_intrusive_actions_enabled", True)
    monkeypatch.setitem(config.CFG, "oast_connector", {
        "enabled": True,
        "base_url": "https://private-oast.internal.example",
        "token_secret_id": "DARKLAB_PRIVATE_OAST_TOKEN",
        "allowed_domain": "callbacks.example.test",
        "tls_verify": True,
        "callback_retention_seconds": 3600,
        "privacy_acknowledged": True,
    })
    check_base = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{created['assessment']['id']}/checks/{check['id']}"
    )
    action_path = check_base + "/recommended-action"
    correlation_path = check_base + "/oast-correlations"
    selection = {
        "source_run_id": source_run_id,
        "parameter_observation_id": observation_id,
    }

    with mock.patch(
        "services.connectors.oast_config.resolve_oast_token"
    ) as resolve_token, mock.patch(
        "services.connectors.oast_provider_transport.register_oast_provider_session"
    ) as register_provider:
        preview = client.get(
            action_path,
            headers=_headers(token),
            query_string=selection,
        )
        plan = preview.get_json()["plan"]
        with mock.patch(
            "blueprints.api_v1._start_brokered_run_service"
        ) as start_run:
            blocked_launch = client.post(
                action_path,
                headers=_headers(token),
                json={
                    **selection,
                    "confirmed": True,
                    "plan_digest": plan["plan_digest"],
                },
            )
        stale_reservation = client.post(
            correlation_path,
            headers=_headers(token),
            json={
                **selection,
                "confirmed": True,
                "plan_digest": "0" * 64,
            },
        )
        reserved = client.post(
            correlation_path,
            headers=_headers(token),
            json={
                **selection,
                "confirmed": True,
                "plan_digest": plan["plan_digest"],
            },
        )
        listed = client.get(correlation_path, headers=_headers(token))
        browser_listed = client.get(
            correlation_path.removeprefix("/api/v1"),
            headers={"X-Session-ID": token},
        )

    assert preview.status_code == 200
    assert plan["profile_version"] == "1.6"
    assert plan["action"] == {
        "key": "oast_private_callback",
        "kind": "",
        "id": "",
    }
    assert plan["launchable"] is False
    assert plan["oast"] == {
        "preparable": True,
        "callback_url": "https://[private-oast-callback]",
        "reservation_window_seconds": 900,
    }
    assert "--blind 'https://[private-oast-callback]'" in plan["display_command"]
    assert "private-oast.internal.example" not in preview.get_data(as_text=True)
    assert "DARKLAB_PRIVATE_OAST_TOKEN" not in preview.get_data(as_text=True)
    assert blocked_launch.status_code == 409
    assert blocked_launch.get_json()["error"]["code"] == "action_unavailable"
    assert stale_reservation.status_code == 409
    assert stale_reservation.get_json()["error"]["code"] == "stale_plan"
    start_run.assert_not_called()

    assert reserved.status_code == 202, reserved.get_json()
    correlation = reserved.get_json()["correlation"]
    assert correlation["status"] == "reserved"
    assert correlation["run_id"] == ""
    assert correlation["provider_ready"] is False
    assert correlation["callback_url"] == "https://[private-oast-callback]"
    assert {
        "session_id",
        "team_id",
        "callback_label",
        "allowed_domain",
        "service_origin_sha256",
        "actor_member_id",
        "actor_role",
        "error_detail",
    }.isdisjoint(correlation)
    assert listed.get_json()["correlations"] == [correlation]
    assert browser_listed.get_json()["correlations"] == [correlation]
    assert resolve_token.call_count == 0
    assert register_provider.call_count == 0

    exact_path = correlation_path + f"/{correlation['id']}"
    launch_path = exact_path + "/launch"
    launch_body = {
        **selection,
        "confirmed": True,
        "plan_digest": plan["plan_digest"],
    }
    with mock.patch(
        "services.assessments.assessment_oast_launch_confirmation."
        "oast_connector_settings",
        return_value=OastConnectorSettings(
            enabled=True,
            base_url="https://private-oast.internal.example",
            token_secret_id="DARKLAB_PRIVATE_OAST_TOKEN",
            allowed_domain="changed.example.test",
            tls_verify=True,
            callback_retention_seconds=3600,
            privacy_acknowledged=True,
        ),
    ):
        scope_changed_launch = client.post(
            launch_path,
            headers=_headers(token),
            json=launch_body,
        )
    assert scope_changed_launch.status_code == 409
    assert scope_changed_launch.get_json()["error"]["code"] == (
        "oast_provider_scope_changed"
    )
    with mock.patch(
        "blueprints.api_v1._start_brokered_run_service"
    ) as start_run:
        not_ready_launch = client.post(
            launch_path,
            headers=_headers(token),
            json=launch_body,
        )
    assert not_ready_launch.status_code == 409
    assert not_ready_launch.get_json()["error"]["code"] == (
        "oast_provider_not_ready"
    )
    start_run.assert_not_called()

    launched_run_id = str(uuid.uuid4())

    def _start_ready_oast(**kwargs):
        assert kwargs["display_command"] == plan["display_command"]
        assert "callbacks.example.test" not in kwargs["original_command"]
        reviewed_command = kwargs["reviewed_execution"].execution_command
        assert "callbacks.example.test" in reviewed_command
        assert kwargs["output_signal_context"].dalfox_oast_validation is True
        assert any(
            value.endswith(".callbacks.example.test")
            for value in kwargs["private_values"]
        )
        kwargs["run_created_hook"](launched_run_id, None)
        return SimpleNamespace(run_id=launched_run_id, status="running")

    with mock.patch(
        "services.connectors.oast_readiness.oast_provider_session_is_staged",
        return_value=True,
    ), mock.patch(
        "services.assessments.assessment_oast_run_launch."
        "resolve_project_dalfox_parameter_evidence",
        return_value=evidence,
    ), mock.patch(
        "blueprints.api_v1.broker_available",
        return_value=True,
    ), mock.patch(
        "blueprints.api_v1._start_brokered_run_service",
        side_effect=_start_ready_oast,
    ) as start_run:
        ready = client.get(exact_path, headers=_headers(token))
        ready_list = client.get(correlation_path, headers=_headers(token))
        launched = client.post(
            launch_path,
            headers=_headers(token),
            json=launch_body,
        )
        repeated_launch = client.post(
            launch_path,
            headers=_headers(token),
            json=launch_body,
        )
    ready_correlation = ready.get_json()["correlation"]
    assert ready_correlation["provider_ready"] is True
    assert ready_correlation["callback_url"].startswith("https://")
    assert ready_correlation["callback_url"].endswith(".callbacks.example.test")
    assert ready_list.get_json()["correlations"][0]["callback_url"] == (
        "https://[private-oast-callback]"
    )
    assert launched.status_code == 202, launched.get_json()
    assert launched.get_json()["correlation_id"] == correlation["id"]
    assert launched.get_json()["run"]["run_id"] == launched_run_id
    assert launched.get_json()["run"]["command"] == plan["display_command"]
    assert "callbacks.example.test" not in launched.get_data(as_text=True)
    assert repeated_launch.status_code == 409
    assert repeated_launch.get_json()["error"]["code"] == (
        "oast_correlation_unavailable"
    )
    assert start_run.call_count == 1
    active = client.get(exact_path, headers=_headers(token)).get_json()["correlation"]
    assert active["status"] == "active"
    assert active["run_id"] == launched_run_id
    assert client.get(exact_path, headers=_headers(other_token)).status_code == 404
    assert client.get(correlation_path, headers=_headers(other_token)).status_code == 404
    assert client.get(
        exact_path.replace(check["id"], "ach_wrong_oast_scope"),
        headers=_headers(token),
    ).status_code == 404
    audit = _audit_event_rows(
        target_id=check["id"],
        event_type="assessment.oast_reserve",
    )
    assert len(audit) == 1
    assert audit[0]["details"] == {
        "action": "oast_private_callback",
        "assessment_id": created["assessment"]["id"],
        "check_id": check["id"],
        "correlation_id": correlation["id"],
        "project_id": project["id"],
        "source": "api_v1",
        "status": "reserved",
    }
    launch_audit = _audit_event_rows(
        target_id=check["id"],
        event_type="assessment.action_launch",
    )
    assert len(launch_audit) == 1
    assert launch_audit[0]["details"] == {
        "action": "oast_private_callback",
        "assessment_id": created["assessment"]["id"],
        "check_id": check["id"],
        "check_key": "blind_xss_validation",
        "correlation_id": correlation["id"],
        "parameter_observation_id": observation_id,
        "parameter_source_run_id": source_run_id,
        "policy_level": "intrusive",
        "profile_key": "web",
        "profile_version": "1.6",
        "project_id": project["id"],
        "run_id": launched_run_id,
        "source": "api_v1",
    }
    assert "callback_url" not in json.dumps(audit)
    assert "callback_url" not in json.dumps(launch_audit)
    assert "private-oast.internal.example" not in json.dumps(audit)
    assert "private-oast.internal.example" not in json.dumps(launch_audit)


def test_assessment_zap_routes_review_queue_scope_and_cancel(
    caplog,
    monkeypatch,
    tmp_path,
):
    from services.assessments import zap_connector

    caplog.set_level("INFO", logger="shell")
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="External ZAP review")
    _seed_assessment_target(token, project["id"])
    created = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "web", "title": "ZAP connector review"},
    ).get_json()
    check = created["checks"]["checks"][0]
    suffix = uuid.uuid4().hex[:16]
    target_id = "ent_api_zap_" + suffix
    host = f"zap-{suffix}.example.test"
    target_url = f"https://{host}/app"
    observed_at = "2026-08-09T18:00:00+00:00"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, type, canonical_value, signature_hash, "
            "first_seen_at, last_seen_at, created) "
            "VALUES (?, ?, 'url', ?, ?, ?, ?, ?)",
            (
                target_id,
                token,
                target_url,
                "sig_" + target_id,
                observed_at,
                observed_at,
                observed_at,
            ),
        )
        conn.execute(
            "INSERT INTO project_links "
            "(id, project_id, entity_type, entity_id, source, review_state, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', 'confirmed', ?)",
            ("pl_api_zap_" + suffix, project["id"], target_id, observed_at),
        )
        conn.commit()
    profile_response = client.post(
        f"/api/v1/projects/{project['id']}/http-profiles",
        headers=_headers(token),
        json={
            "name": "Anonymous ZAP scope",
            "base_url": target_url,
            "allowed_hosts": [host],
            "scope_roots": [target_url],
            "exclude_paths": ["/app/logout"],
            "rate_limit_per_second": 2,
            "concurrency": 1,
        },
    )
    assert profile_response.status_code == 201
    profile_id = profile_response.get_json()["profile"]["id"]
    monkeypatch.setitem(config.CFG, "data_dir", str(tmp_path))
    monkeypatch.setitem(config.CFG, "zap_connector", {
        "enabled": True,
        "base_url": "http://zap:8080",
        "api_key_secret_id": "DARKLAB_ZAP_API_KEY",
        "tls_verify": True,
        "allowed_target_cidrs": ["203.0.113.0/24"],
        "scope_policy_url": "https://zap-policy.example.test/v1/zap-scope/review",
        "scope_policy_token_secret_id": "DARKLAB_ZAP_SCOPE_TOKEN",
        "scope_policy_id": "assessment-egress-v1",
        "egress_proxy_host": "zap-egress.example.test",
        "egress_proxy_port": 8080,
        "max_concurrent_jobs": 1,
        "job_timeout_seconds": 900,
        "max_report_bytes": 1048576,
    })
    original_review = zap_connector.review_zap_target
    monkeypatch.setattr(
        zap_connector,
        "review_zap_target",
        lambda url, settings: original_review(
            url,
            settings,
            resolve_addresses=lambda _host: ["203.0.113.10"],
        ),
    )
    from services.connectors.zap_scope_policy import (
        ReviewedZapScopePolicy,
        ZapScopePolicyError,
        allowed_target_cidrs_sha256,
    )

    def successful_scope_review(settings, hosts):
        return ReviewedZapScopePolicy(
            policy_id=settings.scope_policy_id,
            allowed_target_cidrs_sha256=allowed_target_cidrs_sha256(settings),
            egress_proxy_host=settings.egress_proxy_host,
            egress_proxy_port=settings.egress_proxy_port,
            scanner_addresses=tuple((host, ("203.0.113.10",)) for host in hosts),
        )

    base = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{created['assessment']['id']}/checks/{check['id']}"
    )
    selection = {
        "http_profile_id": profile_id,
        "target_entity_ids": [target_id],
        "policy_level": "safe",
        "scope_exclusions": ["/app/private"],
    }
    monkeypatch.setattr(
        zap_connector,
        "review_zap_scope_policy",
        mock.Mock(side_effect=ZapScopePolicyError(
            "zap_scanner_target_out_of_scope",
            "ZAP scanner-side DNS resolved a target outside the allowed networks",
        )),
    )
    split_horizon = client.post(
        base + "/zap-plan",
        headers=_headers(token),
        json=selection,
    )
    assert split_horizon.status_code == 400
    assert split_horizon.get_json()["error"]["code"] == "zap_scanner_target_out_of_scope"
    monkeypatch.setattr(
        zap_connector,
        "review_zap_scope_policy",
        successful_scope_review,
    )
    preview_response = client.post(
        base + "/zap-plan",
        headers=_headers(token),
        json=selection,
    )
    assert preview_response.status_code == 200
    plan = preview_response.get_json()["plan"]
    assert plan["summary"]["targets"] == [target_url]
    assert plan["summary"]["policy_level"] == "safe"
    assert plan["summary"]["authentication_role"] == "anonymous"
    assert plan["summary"]["exclusion_rule_count"] == 2
    assert "activeScan" not in plan["summary"]["job_types"]
    assert "progressToStdout: false" in plan["plan_yaml"]
    assert len(plan["plan_digest"]) == len(plan["plan_sha256"]) == 64
    assert "DARKLAB_ZAP_API_KEY" not in preview_response.get_data(as_text=True)
    assert "http://zap:8080" not in preview_response.get_data(as_text=True)

    browser_preview = client.post(
        base.removeprefix("/api/v1") + "/zap-plan",
        headers={"X-Session-ID": token},
        json=selection,
    )
    assert browser_preview.status_code == 200
    assert browser_preview.get_json()["plan"] == plan
    stale = client.post(
        base + "/zap-jobs",
        headers=_headers(token),
        json={**selection, "confirmed": True, "plan_digest": "0" * 64},
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "stale_plan"

    queued = client.post(
        base + "/zap-jobs",
        headers=_headers(token),
        json={**selection, "confirmed": True, "plan_digest": plan["plan_digest"]},
    )
    assert queued.status_code == 202
    job = queued.get_json()["job"]
    assert job["status"] == "queued"
    assert job["cancelable"] is True
    assert job["plan_summary"] == plan["summary"]
    assert {
        "session_id", "team_id", "actor_member_id", "actor_role", "import_source_id",
    }.isdisjoint(job)
    listed = client.get(base + "/zap-jobs", headers=_headers(token))
    assert listed.status_code == 200
    assert listed.get_json()["jobs"] == [job]
    browser_listed = client.get(
        base.removeprefix("/api/v1") + "/zap-jobs",
        headers={"X-Session-ID": token},
    )
    assert browser_listed.status_code == 200
    assert browser_listed.get_json()["jobs"] == [job]
    assert client.get(base + "/zap-jobs", headers=_headers(other_token)).status_code == 404
    job_path = base + f"/zap-jobs/{job['id']}"
    assert client.get(job_path, headers=_headers(token)).get_json()["job"] == job
    assert client.get(job_path, headers=_headers(other_token)).status_code == 404
    assert client.get(
        job_path.replace(check["id"], "ach_wrong_scope"),
        headers=_headers(token),
    ).status_code == 404

    canceled = client.delete(job_path, headers=_headers(token))
    assert canceled.status_code == 200
    canceled_job = canceled.get_json()["job"]
    assert canceled_job["status"] == "canceled"
    assert canceled_job["cancelable"] is False
    cancel_record = next(
        record
        for record in caplog.records
        if record.message == "API_PROJECT_ASSESSMENT_ZAP_JOB_CANCEL_REQUESTED"
    )
    assert cancel_record.job_status == "canceled"
    assert not hasattr(cancel_record, "status")
    second_cancel = client.delete(job_path, headers=_headers(token))
    assert second_cancel.status_code == 409
    assert second_cancel.get_json()["error"]["code"] == "zap_job_not_cancelable"

    browser_base = base.removeprefix("/api/v1")
    browser_queued = client.post(
        browser_base + "/zap-jobs",
        headers={"X-Session-ID": token},
        json={**selection, "confirmed": True, "plan_digest": plan["plan_digest"]},
    )
    assert browser_queued.status_code == 202
    browser_job = browser_queued.get_json()["job"]
    browser_canceled = client.delete(
        browser_base + f"/zap-jobs/{browser_job['id']}",
        headers={"X-Session-ID": token},
    )
    assert browser_canceled.status_code == 200
    browser_cancel_record = next(
        record
        for record in caplog.records
        if record.message == "PROJECT_ASSESSMENT_ZAP_JOB_CANCEL_REQUESTED"
    )
    assert browser_cancel_record.job_status == "canceled"
    assert not hasattr(browser_cancel_record, "status")
    audit_rows = _audit_event_rows(target_id=check["id"])
    assert [row["event_type"] for row in audit_rows] == [
        "assessment.zap_job_submit",
        "assessment.zap_job_cancel",
        "assessment.zap_job_submit",
        "assessment.zap_job_cancel",
    ]
    assert {row["details"]["job_id"] for row in audit_rows} == {
        job["id"],
        browser_job["id"],
    }
    assert all("target" not in row["details"] for row in audit_rows)


def test_api_v1_assessment_takeover_action_uses_only_reviewed_template_context():
    from services.assessments.nuclei_takeover_templates import reviewed_nuclei_takeover_launch
    from services.runs.signal_context import RunOutputSignalContext

    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="Reviewed takeover action")
    _entity_id, _run_id = _seed_assessment_target(token, project["id"])
    assessment = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=_headers(token),
        json={"profile_key": "web", "title": "Takeover confirmation"},
    ).get_json()
    check = next(
        item
        for item in assessment["checks"]["checks"]
        if item["check_key"] == "subdomain_takeover_confirmation"
    )
    action_path = (
        f"/api/v1/projects/{project['id']}/assessments/"
        f"{assessment['assessment']['id']}/checks/{check['id']}/recommended-action"
    )
    preview = client.get(action_path, headers=_headers(token))
    assert preview.status_code == 200
    plan = preview.get_json()["plan"]
    assert plan["profile_version"] == "1.6"
    assert plan["policy_level"] == "safe"
    assert plan["target"]["type"] == "domain"
    assert plan["bounds"] == {
        "target_count": 1,
        "fan_out": 1,
        "request_limit": 1,
        "time_limit_seconds": 30,
        "credential_use": "none",
        "summary": (
            "One approved domain and one app-owned reviewed provider fingerprint; one "
            "request, no redirects, no resource claim, and no takeover action."
        ),
    }
    assert plan["display_command"].endswith(
        "-t [reviewed-takeover-template] -jsonl -dr -ni"
    )
    assert "-severity" not in plan["display_command"]

    started = SimpleNamespace(run_id="run_reviewed_takeover", status="running")
    with mock.patch("blueprints.api_v1.broker_available", return_value=True), \
         mock.patch(
             "blueprints.api_v1._start_brokered_run_service",
             return_value=started,
         ) as start_run:
        launched = client.post(
            action_path,
            headers=_headers(token),
            json={"confirmed": True, "plan_digest": plan["plan_digest"]},
        )

    assert launched.status_code == 202
    start_kwargs = start_run.call_args.kwargs
    reviewed = reviewed_nuclei_takeover_launch()
    assert start_kwargs["display_command"] == plan["display_command"]
    assert start_kwargs["original_command"].endswith("-retries 0 -silent")
    assert "[reviewed-takeover-template]" not in start_kwargs["original_command"]
    assert "-severity" not in start_kwargs["original_command"]
    assert start_kwargs["trusted_execution_args"] == reviewed.trusted_execution_args
    assert start_kwargs["output_signal_context"] == RunOutputSignalContext(
        nuclei_takeover_template=reviewed.template,
    )


def test_api_v1_project_finding_evidence_is_typed_scoped_and_audited():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="API Finding Evidence")
    run_id = _seed_run(
        token,
        run_id="run_finding_evidence_" + uuid.uuid4().hex[:12],
        command="nuclei -u https://evidence.example",
        output=["first", "vulnerable response", "last"],
    )
    retest_run_id = _seed_run(
        token,
        run_id="run_finding_retest_" + uuid.uuid4().hex[:12],
        command="nuclei -u https://evidence.example",
        output=["retest complete"],
    )
    incomparable_run_id = _seed_run(
        token,
        run_id="run_finding_other_" + uuid.uuid4().hex[:12],
        command="nmap -sV unrelated.example",
        output=["unrelated scan"],
    )
    linked = client.post(
        f"/api/v1/runs/{run_id}/projects/{project['id']}",
        headers=_headers(token),
    )
    for candidate_id in (retest_run_id, incomparable_run_id):
        response = client.post(
            f"/api/v1/runs/{candidate_id}/projects/{project['id']}",
            headers=_headers(token),
        )
        assert response.status_code == 201
    target_response = client.post(
        f"/projects/{project['id']}/targets",
        headers={"X-Session-ID": token},
        json={"type": "domain", "value": "evidence.example"},
    )
    target_id = target_response.get_json()["target"]["id"]
    finding_id = "fnd_evidence_" + uuid.uuid4().hex[:12]
    text_artifact_id = "rfa_evidence_text_" + uuid.uuid4().hex[:8]
    screenshot_id = "rfa_evidence_image_" + uuid.uuid4().hex[:8]
    assessment_id = "asm_evidence_" + uuid.uuid4().hex[:8]
    check_id = "ach_evidence_" + uuid.uuid4().hex[:8]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, run_id, first_run_id, last_run_id, signature_hash, "
            "tool_root, title, raw_line, line_number, created) "
            "VALUES (?, ?, ?, ?, ?, ?, 'nuclei', 'Saved evidence finding', "
            "'vulnerable response', 1, '2026-08-05T00:00:00+00:00')",
            (finding_id, token, run_id, run_id, run_id, "sig_" + finding_id),
        )
        conn.execute(
            "INSERT INTO run_output_artifacts "
            "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
            "VALUES (?, 'evidence/output.txt.gz', 'gzip', 32, 3, 0, "
            "'2026-08-05T00:00:01+00:00')",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, created) VALUES "
            "(?, ?, ?, 'evidence/notes.txt', 'notes.txt', 'output', 16, 'test', "
            "'text/plain', '2026-08-05T00:00:02+00:00'), "
            "(?, ?, ?, 'evidence/screenshot.png', 'screenshot.png', 'screenshot', 24, "
            "'test', 'image/png', '2026-08-05T00:00:03+00:00')",
            (text_artifact_id, token, run_id, screenshot_id, token, run_id),
        )
        conn.execute(
            "INSERT INTO project_assessments "
            "(id, session_id, project_id, title, profile_key, profile_version, profile_snapshot, "
            "status, started_at, created_at, updated_at) VALUES "
            "(?, ?, ?, 'Evidence cycle', 'network', '1', ?, 'active', "
            "'2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00', "
            "'2026-08-05T00:00:00+00:00')",
            (
                assessment_id,
                token,
                project["id"],
                json.dumps({
                    "checks": [{
                        "key": "manual-evidence",
                        "evidence_rules": [{
                            "evidence_types": ["run"],
                            "command_roots": ["nuclei"],
                            "workflow_actions": [],
                            "structured_output_kinds": [],
                            "target_match": "host_or_descendant",
                            "completion": "succeeded",
                            "compatible_versions": ["*"],
                            "negative_evidence": True,
                        }],
                    }],
                }),
            ),
        )
        conn.execute(
            "INSERT INTO project_assessment_checks "
            "(id, assessment_id, category, check_key, target_entity_id, target_type, target_value, "
            "target_value_hash, created_at, updated_at) VALUES "
            "(?, ?, 'validation', 'manual-evidence', ?, 'domain', 'evidence.example', ?, "
            "'2026-08-05T00:00:00+00:00', '2026-08-05T00:00:00+00:00')",
            (check_id, assessment_id, target_id, "hash_" + uuid.uuid4().hex),
        )
        conn.commit()

    route = f"/api/v1/projects/{project['id']}/findings/{finding_id}/evidence"
    created_response = client.post(
        route,
        headers=_headers(token),
        json={
            "evidence_type": "run_line",
            "evidence_id": run_id,
            "line_number": 1,
            "snippet": "vulnerable response",
        },
    )
    duplicate_response = client.post(
        route,
        headers=_headers(token),
        json={
            "evidence_type": "run_line",
            "evidence_id": run_id,
            "line_number": 1,
            "snippet": "replacement text is ignored for an existing identity",
        },
    )
    listed_response = client.get(route, headers=_headers(token))
    cross_scope = client.get(route, headers=_headers(other_token))
    invalid_line = client.post(
        route,
        headers=_headers(token),
        json={"evidence_type": "run_line", "evidence_id": run_id, "line_number": 99},
    )
    invalid_screenshot = client.post(
        route,
        headers=_headers(token),
        json={"evidence_type": "screenshot", "evidence_id": text_artifact_id},
    )

    assert linked.status_code == 201
    assert target_response.status_code == 201
    assert created_response.status_code == 201
    created = created_response.get_json()
    assert created["created"] is True
    assert created["evidence"] == {
        "id": created["evidence"]["id"],
        "project_id": project["id"],
        "finding_id": finding_id,
        "evidence_type": "run_line",
        "evidence_id": run_id,
        "run_id": run_id,
        "line_number": 1,
        "snippet": "vulnerable response",
        "label": "nuclei line 2",
        "observed_at": "2026-05-19T00:00:01+00:00",
        "source_state": "available",
        "created_by_member_id": "",
        "created_at": created["evidence"]["created_at"],
    }
    assert duplicate_response.status_code == 200
    assert duplicate_response.get_json()["created"] is False
    assert listed_response.status_code == 200
    assert listed_response.get_json()["evidence"] == [created["evidence"]]
    assert cross_scope.status_code == 404
    assert invalid_line.status_code == 400
    assert invalid_screenshot.status_code == 400

    package_response = client.post(
        f"/projects/{project['id']}/packages",
        headers={"X-Session-ID": token},
        json={
            "name": "Typed finding evidence",
            "selection": {"finding_ids": [finding_id]},
        },
    )
    assert package_response.status_code == 201
    package_finding = package_response.get_json()["package"]["manifest"]["findings"][0]
    assert package_finding["evidence_links"] == [created["evidence"]]

    evidence_link_id = created["evidence"]["id"]
    deleted_response = client.delete(
        f"{route}/{evidence_link_id}",
        headers=_headers(token),
    )
    assert deleted_response.status_code == 200
    assert client.get(route, headers=_headers(token)).get_json()["evidence"] == []

    evidence_sources = [
        ("run", run_id),
        ("run_artifact", run_id),
        ("workspace_file", text_artifact_id),
        ("screenshot", screenshot_id),
        ("atlas_entity", target_id),
        ("project_target", target_id),
        ("assessment_check", check_id),
        ("retest_run", retest_run_id),
    ]
    with mock.patch.dict(config.CFG, {
        "max_finding_evidence_links_per_owner": 0,
        "max_finding_evidence_links_per_finding": 0,
    }):
        unlimited_responses = [
            client.post(
                route,
                headers=_headers(token),
                json={"evidence_type": evidence_type, "evidence_id": evidence_id},
            )
            for evidence_type, evidence_id in evidence_sources
        ]
    assert [response.status_code for response in unlimited_responses] == [201] * 8
    evidence_page = client.get(route, headers=_headers(token)).get_json()
    assert {item["evidence_type"] for item in evidence_page["evidence"]} == {
        evidence_type for evidence_type, _evidence_id in evidence_sources
    }
    assert evidence_page["total"] == 8
    verification = evidence_page["verification"]
    assert verification["baseline_run_id"] == run_id
    assert verification["origin_checks"][0]["check_id"] == check_id
    assert verification["origin_checks"][0]["profile_version_state"] == "changed"
    assert verification["retest_runs"][0]["id"] == retest_run_id
    assert verification["retest_runs"][0]["compatibility"]["state"] == "compatible"
    assert verification["retest_runs"][0]["compatibility"] == {
        **verification["retest_runs"][0]["compatibility"],
        "matched_check_id": check_id,
        "matched_rule_key": "",
        "supports_negative_evidence": True,
    }
    assert verification["suggestion"] == {
        "available": True,
        "verification_status": "verified",
        "reason": verification["suggestion"]["reason"],
        "run_id": retest_run_id,
        "evidence_link_id": verification["retest_runs"][0]["evidence_link_id"],
        "matched_check_id": check_id,
        "matched_rule_key": "",
    }
    assert "not observed again" in verification["suggestion"]["reason"]
    assert verification["retest_runs"][0]["comparison"] == {
        "available": True,
        "left_run_id": run_id,
        "right_run_id": retest_run_id,
    }
    candidate_by_id = {
        item["id"]: item for item in verification["candidate_runs"]
    }
    assert candidate_by_id[incomparable_run_id]["compatibility"]["state"] == "incomparable"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO findings_occurrences "
            "(finding_id, run_id, line_number, snippet, seen_at) VALUES "
            "(?, ?, 0, 'vulnerable response', '2026-08-05T00:05:00+00:00')",
            (finding_id, retest_run_id),
        )
        conn.commit()
    evidence_page = client.get(route, headers=_headers(token)).get_json()
    repeated = evidence_page["verification"]["suggestion"]
    assert repeated["verification_status"] == "needs_retest"
    assert "observed" in repeated["reason"]
    browser_route = f"/projects/{project['id']}/findings/{finding_id}/evidence"
    browser_page = client.get(browser_route, headers={"X-Session-ID": token})
    assert browser_page.status_code == 200
    assert browser_page.get_json() == evidence_page
    browser_duplicate = client.post(
        browser_route,
        headers={"X-Session-ID": token},
        json={"evidence_type": "run", "evidence_id": run_id},
    )
    assert browser_duplicate.status_code == 200
    assert browser_duplicate.get_json()["created"] is False
    with mock.patch.dict(config.CFG, {
        "max_finding_evidence_links_per_owner": 0,
        "max_finding_evidence_links_per_finding": 8,
    }):
        quota_response = client.post(
            route,
            headers=_headers(token),
            json={
                "evidence_type": "run_line",
                "evidence_id": run_id,
                "line_number": 0,
            },
        )
    assert quota_response.status_code == 409
    assert quota_response.get_json()["error"]["code"] == "quota_exceeded"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM run_file_artifacts WHERE id = ?", (screenshot_id,))
        conn.commit()
    unavailable_page = client.get(route, headers=_headers(token)).get_json()
    unavailable_screenshot = next(
        item for item in unavailable_page["evidence"] if item["evidence_type"] == "screenshot"
    )
    assert unavailable_screenshot["source_state"] == "unavailable"
    assert unavailable_screenshot["evidence_id"] == screenshot_id

    audit_rows = _audit_event_rows(target_id=finding_id)
    assert [row["event_type"] for row in audit_rows] == [
        "finding.evidence_link",
        "finding.evidence_unlink",
    ] + ["finding.evidence_link"] * 8
    assert all(row["details"]["source"] == "api_v1" for row in audit_rows)


def test_api_v1_manual_findings_keep_stable_identity_and_owner_scope():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="API Manual Findings")
    target_id, _run_id = _seed_assessment_target(token, project["id"])
    route = f"/api/v1/projects/{project['id']}/findings"

    created_response = client.post(
        route,
        headers=_headers(token),
        json={
            "target_id": target_id,
            "title": "Exposed administrative console",
            "severity": "medium",
            "cve_ids": ["CVE-2026-12345"],
        },
    )

    assert created_response.status_code == 201
    created = created_response.get_json()["finding"]
    assert created["origin"] == "manual"
    assert created["validation_method"] == "manual_assessment"
    assert created["manual_revision"] == 1
    assert created["risk"]["cve_id"] == "CVE-2026-12345"
    assert "manual_created_by_session_id" not in created
    observation_id = created["observation_id"]
    remediation_id = created["remediation_id"]

    invalid_boolean = client.post(
        route,
        headers=_headers(token),
        json={
            "target_id": target_id,
            "title": "Invalid duplicate override",
            "severity": "low",
            "allow_duplicate": "false",
        },
    )
    empty_update = client.patch(
        f"{route}/{created['id']}",
        headers=_headers(token),
        json={"expected_revision": 1},
    )
    updated_response = client.patch(
        f"{route}/{created['id']}",
        headers=_headers(token),
        json={"expected_revision": 1, "severity": "high"},
    )
    cross_scope = client.patch(
        f"{route}/{created['id']}",
        headers=_headers(other_token),
        json={"expected_revision": 2, "severity": "low"},
    )

    assert invalid_boolean.status_code == 400
    assert empty_update.status_code == 400
    assert updated_response.status_code == 200
    updated = updated_response.get_json()["finding"]
    assert updated["manual_revision"] == 2
    assert updated["severity"] == "high"
    assert updated["observation_id"] == observation_id
    assert updated["remediation_id"] == remediation_id
    assert cross_scope.status_code == 404

    audit_rows = _audit_event_rows(target_id=created["id"])
    assert [row["event_type"] for row in audit_rows] == [
        "finding.manual_create",
        "finding.manual_update",
    ]
    assert all(row["details"]["source"] == "api_v1" for row in audit_rows)
    assert "Exposed administrative console" not in json.dumps(audit_rows)


def test_api_v1_project_assessments_enforce_team_capabilities_and_actor_context():
    from services.teams.storage import token_hash

    client = get_client()
    owner_token = _token(client)
    viewer_token = _token(client)
    operator_token = _token(client)
    admin_token = _token(client)
    outsider_token = _token(client)
    team_id = _create_api_team(client, owner_token, name="Assessment API Team")
    _add_api_team_member(
        client,
        owner_token,
        viewer_token,
        team_id,
        role="viewer",
    )
    _add_api_team_member(
        client,
        owner_token,
        operator_token,
        team_id,
        role="operator",
    )
    _add_api_team_member(
        client,
        owner_token,
        admin_token,
        team_id,
        role="admin",
    )
    project_response = client.post(
        "/projects",
        headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
        json={"name": "Team API Assessment Project"},
    )
    assert project_response.status_code == 201
    project_id = json.loads(project_response.data)["project"]["id"]
    _entity_id, evidence_run_id = _seed_assessment_target(
        owner_token, project_id, team_id=team_id
    )
    finding_id = "fnd_team_evidence_" + uuid.uuid4().hex[:12]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, team_id, run_id, first_run_id, last_run_id, "
            "signature_hash, title, created) VALUES (?, ?, ?, ?, ?, ?, ?, "
            "'Team evidence finding', '2026-08-04T12:00:00+00:00')",
            (
                finding_id,
                owner_token,
                team_id,
                evidence_run_id,
                evidence_run_id,
                evidence_run_id,
                "sig_" + finding_id,
            ),
        )
        conn.commit()
    owner_headers = _team_headers(owner_token, team_id)
    viewer_headers = _team_headers(viewer_token, team_id)
    operator_headers = _team_headers(operator_token, team_id)
    admin_headers = _team_headers(admin_token, team_id)
    outsider_headers = _team_headers(outsider_token, team_id)
    browser_viewer_headers = {
        "X-Session-ID": viewer_token,
        "X-Team-ID": team_id,
    }
    browser_operator_headers = {
        "X-Session-ID": operator_token,
        "X-Team-ID": team_id,
    }
    browser_outsider_headers = {
        "X-Session-ID": outsider_token,
        "X-Team-ID": team_id,
    }

    created_response = client.post(
        f"/api/v1/projects/{project_id}/assessments",
        headers=owner_headers,
        json={"profile_key": "network"},
    )
    assert created_response.status_code == 201
    created = json.loads(created_response.data)
    assessment_id = created["assessment"]["id"]
    check_id = created["checks"]["checks"][0]["id"]
    target_value = created["checks"]["checks"][0]["target_value"]
    assessment_route = f"/api/v1/projects/{project_id}/assessments/{assessment_id}"
    browser_assessment_route = f"/projects/{project_id}/assessments/{assessment_id}"
    viewer_list = client.get(
        f"/api/v1/projects/{project_id}/assessments",
        headers=viewer_headers,
    )
    browser_viewer_list = client.get(
        f"/projects/{project_id}/assessments",
        headers=browser_viewer_headers,
    )
    with mock.patch(
        "blueprints.api_v1_assessments.update_assessment_cycle"
    ) as api_update, mock.patch(
        "blueprints.projects_assessments.update_assessment_cycle"
    ) as browser_update:
        viewer_update = client.patch(
            assessment_route,
            headers=viewer_headers,
            json={"title": "Viewer cannot edit"},
        )
        browser_viewer_update = client.patch(
            browser_assessment_route,
            headers=browser_viewer_headers,
            json={"title": "Viewer cannot edit"},
        )
    api_update.assert_not_called()
    browser_update.assert_not_called()
    viewer_check_update = client.patch(
        f"/api/v1/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}",
        headers=viewer_headers,
        json={"state": "skipped", "reason": "Viewer cannot decide this"},
    )
    oast_route = (
        f"/api/v1/projects/{project_id}/assessments/{assessment_id}/checks/"
        f"{check_id}/oast-correlations"
    )
    viewer_oast_reserve = client.post(
        oast_route,
        headers=viewer_headers,
        json={},
    )
    viewer_oast_exact = client.get(
        oast_route + "/ocr_" + "0" * 32,
        headers=viewer_headers,
    )
    viewer_oast_launch = client.post(
        oast_route + "/ocr_" + "0" * 32 + "/launch",
        headers=viewer_headers,
        json={},
    )
    action_route = (
        f"/api/v1/projects/{project_id}/assessments/{assessment_id}/checks/"
        f"{check_id}/recommended-action"
    )
    browser_action_route = action_route.removeprefix("/api/v1")
    with mock.patch(
        "blueprints.api_v1_assessment_action_launch.confirm_recommended_action_plan"
    ) as api_confirm, mock.patch(
        "blueprints.projects_assessment_action_launch.confirm_recommended_action_plan"
    ) as browser_confirm:
        viewer_action_launch = client.post(
            action_route,
            headers=viewer_headers,
            json={"confirmed": True, "plan_digest": "not-authorized"},
        )
        browser_viewer_action_launch = client.post(
            browser_action_route,
            headers=browser_viewer_headers,
            json={"confirmed": True, "plan_digest": "not-authorized"},
        )
    api_confirm.assert_not_called()
    browser_confirm.assert_not_called()
    finding_evidence_route = (
        f"/api/v1/projects/{project_id}/findings/{finding_id}/evidence"
    )
    viewer_evidence_list = client.get(finding_evidence_route, headers=viewer_headers)
    viewer_evidence_write = client.post(
        finding_evidence_route,
        headers=viewer_headers,
        json={"evidence_type": "run", "evidence_id": evidence_run_id},
    )
    assert viewer_list.status_code == 200
    assert browser_viewer_list.status_code == 200
    assert json.loads(viewer_list.data)["assessments"][0]["id"] == assessment_id
    assert viewer_evidence_list.status_code == 200
    viewer_evidence = viewer_evidence_list.get_json()
    assert viewer_evidence["evidence"] == []
    assert viewer_evidence["total"] == 0
    assert viewer_evidence["verification"]["baseline_run_id"] == evidence_run_id
    for response in (
        viewer_update,
        browser_viewer_update,
        viewer_check_update,
        viewer_evidence_write,
        viewer_oast_reserve,
        viewer_oast_exact,
        viewer_oast_launch,
        viewer_action_launch,
        browser_viewer_action_launch,
    ):
        assert response.status_code == 403
        payload = json.loads(response.data)
        error = payload.get("error")
        code = payload.get("code") or (
            error.get("code") if isinstance(error, dict) else error
        )
        assert code == "team_forbidden"

    operator_update = client.patch(
        browser_assessment_route,
        headers=browser_operator_headers,
        json={"title": "Operator-reviewed cycle"},
    )
    assert operator_update.status_code == 200
    operator_check_update = client.patch(
        f"/api/v1/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}",
        headers=operator_headers,
        json={"state": "skipped", "reason": "Approved scope exclusion"},
    )
    assert operator_check_update.status_code == 200

    profiles_route = f"/api/v1/projects/{project_id}/http-profiles"
    profile_payload = {
        "name": "Team application",
        "base_url": f"https://{target_value}",
        "allowed_hosts": [target_value],
    }
    operator_profile_create = client.post(
        profiles_route,
        headers=operator_headers,
        json=profile_payload,
    )
    admin_profile_create = client.post(
        profiles_route,
        headers=admin_headers,
        json=profile_payload,
    )
    assert operator_profile_create.status_code == 403
    assert operator_profile_create.get_json()["error"]["code"] == "team_forbidden"
    assert admin_profile_create.status_code == 201

    owner_evidence_write = client.post(
        finding_evidence_route,
        headers=owner_headers,
        json={"evidence_type": "run", "evidence_id": evidence_run_id},
    )
    assert owner_evidence_write.status_code == 201
    actor = json.loads(operator_check_update.data)["check"]["state_actor"]
    with sqlite3.connect(DB_PATH) as conn:
        operator_member_id = conn.execute(
            "SELECT id FROM team_members WHERE team_id = ? AND session_token_hash = ?",
            (team_id, token_hash(operator_token)),
        ).fetchone()[0]
        owner_member_id = conn.execute(
            "SELECT id FROM team_members WHERE team_id = ? AND session_token_hash = ?",
            (team_id, token_hash(owner_token)),
        ).fetchone()[0]
    assert actor == {"kind": "team_member", "member_id": operator_member_id}
    assert (
        owner_evidence_write.get_json()["evidence"]["created_by_member_id"]
        == owner_member_id
    )
    assert client.get(
        finding_evidence_route,
        headers=viewer_headers,
    ).get_json()["total"] == 1

    outsider_api_read = client.get(assessment_route, headers=outsider_headers)
    outsider_browser_read = client.get(
        browser_assessment_route,
        headers=browser_outsider_headers,
    )
    assert outsider_api_read.status_code == 403
    assert outsider_api_read.get_json()["error"]["code"] == "team_forbidden"
    assert outsider_browser_read.status_code == 403
    assert outsider_browser_read.get_json()["error"] == "team_forbidden"

    assert client.patch(
        assessment_route,
        headers=owner_headers,
        json={"status": "completed"},
    ).status_code == 200
    assert client.patch(
        assessment_route,
        headers=owner_headers,
        json={"status": "archived"},
    ).status_code == 200
    archived_api_list = client.get(
        f"/api/v1/projects/{project_id}/assessments",
        headers=viewer_headers,
        query_string={"include_archived": 1},
    )
    archived_browser_read = client.get(
        browser_assessment_route,
        headers=browser_viewer_headers,
    )
    assert archived_api_list.status_code == 200
    assert archived_api_list.get_json()["assessments"][0]["status"] == "archived"
    assert archived_browser_read.status_code == 200
    archived_mutation = client.patch(
        assessment_route,
        headers=operator_headers,
        json={"title": "Archived cycles are immutable"},
    )
    assert archived_mutation.status_code == 409


def test_api_v1_project_http_profiles_are_scoped_redacted_and_reference_only(monkeypatch):
    from services.assessments import http_profiles as http_profile_service

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="HTTP Profile API Project")
    target = "api-http-profile.example.com"
    target_response = client.post(
        f"/projects/{project['id']}/targets",
        headers={"X-Session-ID": token},
        json={"type": "domain", "value": target},
    )
    assert target_response.status_code == 201
    secret_value = "do-not-return-this-token"
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO secrets "
            "(session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at) "
            "VALUES (?, 'HTTP_PROFILE_TOKEN', ?, ?, '[]', ?, ?)",
            (
                token,
                b"ciphertext",
                b"nonce",
                "2026-08-06T00:00:00+00:00",
                "2026-08-06T00:00:00+00:00",
            ),
        )
        conn.commit()

    route = f"/api/v1/projects/{project['id']}/http-profiles"
    create_response = client.post(
        route,
        headers=_headers(token),
        json={
            "name": "Administrator session",
            "role": "administrator",
            "base_url": f"https://{target}/admin",
            "scope_roots": [f"https://{target}/admin"],
            "allowed_hosts": [target],
            "headers": [
                {"name": "X-Assessment-Token", "secret_name": "HTTP_PROFILE_TOKEN"}
            ],
            "secret_refs": {"bearer_token": "HTTP_PROFILE_TOKEN"},
            "token_capture_rules": [
                {
                    "name": "session-cookie",
                    "source": "cookie",
                    "selector": "session",
                    "target": "cookie",
                    "target_name": "session",
                }
            ],
            "include_paths": ["/admin"],
            "exclude_paths": ["/admin/logout"],
            "rate_limit_per_second": 4,
            "concurrency": 2,
        },
    )
    assert create_response.status_code == 201
    created = create_response.get_json()["profile"]
    profile_id = created["id"]
    assert created["protected_references_visible"] is True
    assert created["secret_refs"] == {
        "bearer_token": {"name": "HTTP_PROFILE_TOKEN", "available": True}
    }
    assert created["headers"] == [{
        "name": "X-Assessment-Token",
        "secret_name": "HTTP_PROFILE_TOKEN",
        "available": True,
    }]
    assert secret_value not in create_response.get_data(as_text=True)

    available_files = {"client/cert.pem", "client/key.pem"}

    def _workspace_path_info(_owner, path):
        if path not in available_files:
            raise http_profile_service.WorkspaceError("missing")
        return {"kind": "file"}

    monkeypatch.setattr(
        http_profile_service,
        "owner_workspace_path_info",
        _workspace_path_info,
    )
    file_profile_response = client.post(
        route,
        headers=_headers(token),
        json={
            "name": "Client certificate",
            "base_url": f"https://{target}",
            "file_refs": {
                "client_certificate": "client/cert.pem",
                "client_key": "client/key.pem",
            },
        },
    )
    missing_file_response = client.post(
        route,
        headers=_headers(token),
        json={
            "name": "Missing Files reference",
            "base_url": f"https://{target}",
            "file_refs": {
                "client_certificate": "client/missing-cert.pem",
                "client_key": "client/missing-key.pem",
            },
        },
    )
    assert file_profile_response.status_code == 201
    assert file_profile_response.get_json()["profile"]["file_refs"] == {
        "client_certificate": "client/cert.pem",
        "client_key": "client/key.pem",
    }
    assert missing_file_response.status_code == 400

    duplicate = client.post(
        route,
        headers=_headers(token),
        json={"name": "administrator SESSION", "base_url": f"https://{target}"},
    )
    missing_secret = client.post(
        route,
        headers=_headers(token),
        json={
            "name": "Missing reference",
            "base_url": f"https://{target}",
            "secret_refs": {"cookie": "MISSING_PROFILE_SECRET"},
        },
    )
    outside_scope = client.post(
        route,
        headers=_headers(token),
        json={
            "name": "Outside scope",
            "base_url": "https://outside.example.com",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "http_profile_conflict"
    assert missing_secret.status_code == 400
    assert outside_scope.status_code == 400

    list_response = client.get(route, headers=_headers(token))
    detail_route = f"{route}/{profile_id}"
    cross_scope = client.get(detail_route, headers=_headers(other_token))
    stale_update = client.patch(
        detail_route,
        headers=_headers(token),
        json={"revision": created["revision"] + 1, "enabled": False},
    )
    update_response = client.patch(
        detail_route,
        headers=_headers(token),
        json={"revision": created["revision"], "enabled": False},
    )
    assert list_response.status_code == 200
    assert list_response.get_json()["profiles"][0]["id"] == profile_id
    assert cross_scope.status_code == 404
    assert stale_update.status_code == 409
    assert update_response.status_code == 200
    assert update_response.get_json()["profile"]["enabled"] is False

    audit_rows = _audit_event_rows(target_id=profile_id)
    assert [row["event_type"] for row in audit_rows] == [
        "http_profile.create",
        "http_profile.update",
    ]
    serialized_audit = json.dumps(audit_rows)
    assert "HTTP_PROFILE_TOKEN" not in serialized_audit
    assert target not in serialized_audit
    assert "session-cookie" not in serialized_audit

    team_owner = _token(client)
    team_viewer = _token(client)
    team_id = _create_api_team(client, team_owner, name="HTTP Profile API Team")
    _add_api_team_member(client, team_owner, team_viewer, team_id, role="viewer")
    owner_headers = _team_headers(team_owner, team_id)
    viewer_headers = _team_headers(team_viewer, team_id)
    team_project_response = client.post(
        "/projects",
        headers={"X-Session-ID": team_owner, "X-Team-ID": team_id},
        json={"name": "Team HTTP Profiles"},
    )
    assert team_project_response.status_code == 201
    team_project_id = team_project_response.get_json()["project"]["id"]
    team_target = "team-http-profile.example.com"
    team_target_response = client.post(
        f"/projects/{team_project_id}/targets",
        headers={"X-Session-ID": team_owner, "X-Team-ID": team_id},
        json={"type": "domain", "value": team_target},
    )
    assert team_target_response.status_code == 201
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO secrets "
            "(session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at) "
            "VALUES (?, 'TEAM_HTTP_TOKEN', ?, ?, '[]', ?, ?)",
            (
                team_id,
                b"ciphertext",
                b"nonce",
                "2026-08-06T00:00:00+00:00",
                "2026-08-06T00:00:00+00:00",
            ),
        )
        conn.commit()
    team_route = f"/api/v1/projects/{team_project_id}/http-profiles"
    team_create = client.post(
        team_route,
        headers=owner_headers,
        json={
            "name": "Team user",
            "role": "user",
            "base_url": f"https://{team_target}",
            "secret_refs": {"cookie": "TEAM_HTTP_TOKEN"},
        },
    )
    assert team_create.status_code == 201
    team_profile_id = team_create.get_json()["profile"]["id"]
    viewer_list = client.get(team_route, headers=viewer_headers)
    viewer_profile = viewer_list.get_json()["profiles"][0]
    assert viewer_profile["id"] == team_profile_id
    assert viewer_profile["protected_references_visible"] is False
    for protected_field in (
        "headers",
        "secret_refs",
        "file_refs",
        "proxy_url",
        "token_capture_rules",
    ):
        assert protected_field not in viewer_profile
    viewer_create = client.post(
        team_route,
        headers=viewer_headers,
        json={"name": "Forbidden", "base_url": f"https://{team_target}"},
    )
    assert viewer_create.status_code == 403
    assert viewer_create.get_json()["error"]["code"] == "team_forbidden"
    team_assessment = client.post(
        f"/api/v1/projects/{team_project_id}/assessments",
        headers=owner_headers,
        json={"profile_key": "web", "title": "Team protected web checks"},
    ).get_json()
    team_http_check = next(
        item for item in team_assessment["checks"]["checks"]
        if item["check_key"] == "http_profile"
    )
    team_action_path = (
        f"/api/v1/projects/{team_project_id}/assessments/"
        f"{team_assessment['assessment']['id']}/checks/{team_http_check['id']}/"
        "recommended-action"
    )
    owner_profile_preview = client.get(
        team_action_path,
        headers=owner_headers,
        query_string={"http_profile_id": team_profile_id},
    )
    viewer_profile_preview = client.get(
        team_action_path,
        headers=viewer_headers,
        query_string={"http_profile_id": team_profile_id},
    )
    assert owner_profile_preview.status_code == 200
    assert owner_profile_preview.get_json()["plan"]["http_profile"]["id"] == team_profile_id
    assert viewer_profile_preview.status_code == 403
    assert viewer_profile_preview.get_json()["error"]["code"] == "team_forbidden"

    delete_response = client.delete(detail_route, headers=_headers(token))
    assert delete_response.get_json() == {"ok": True, "removed": True}
    deleted_audit = _audit_event_rows(target_id=profile_id)[-1]
    assert deleted_audit["event_type"] == "http_profile.delete"
    assert deleted_audit["details"]["deleted_count"] == 1

def test_api_v1_project_assessment_errors_use_the_public_error_shape():
    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="API Assessment Errors")
    _seed_assessment_target(token, project["id"])
    headers = _headers(token)

    missing_profile = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=headers,
        json={},
    )
    unsupported = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=headers,
        json={"profile_key": "network", "private_path": "/tmp/profile.yaml"},
    )
    invalid_body = client.post(
        f"/api/v1/projects/{project['id']}/assessments",
        headers=headers,
        json=["network"],
    )
    for response, code in (
        (missing_profile, "invalid_assessment"),
        (unsupported, "invalid_assessment"),
        (invalid_body, "invalid_body"),
    ):
        assert response.status_code == 400
        payload = json.loads(response.data)
        assert payload["error"]["code"] == code
        assert isinstance(payload["error"]["message"], str)


def test_api_v1_history_detail_output_and_cross_session_404():
    from services.history import queries as history_queries
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
        history_queries,
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


def test_api_v1_output_fallback_preserves_api_log_event_and_metadata():
    from services.history import api_queries as history_api_queries
    from services.runs import output_store

    client = get_client()
    token = _token(client)
    run_id = _seed_run(token, output=["preview fallback line"])
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE runs SET full_output_available = 1, full_output_truncated = 0 WHERE id = ?",
            (run_id,),
        )
        conn.execute(
            "INSERT INTO run_output_artifacts "
            "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
            "VALUES (?, ?, 'gzip', 12, 1, 0, '2026-05-19T00:00:01+00:00')",
            (run_id, "missing/api-output-artifact.txt.gz"),
        )
        conn.commit()

    with mock.patch.object(output_store.log, "warning") as warning_log:
        output_json = client.get(f"/api/v1/history/{run_id}/output?format=json", headers=_headers(token))

    assert output_json.status_code == 200
    payload = json.loads(output_json.data)
    assert payload["lines"] == ["preview fallback line"]
    assert payload["preview"] is True
    assert payload["full_output_available"] is True
    assert [call.args[0] for call in warning_log.call_args_list] == ["API_FULL_OUTPUT_LOAD_FAILED"]

    run = {
        "id": run_id,
        "session_id": token,
        "full_output_available": True,
        "rel_path": "missing/api-output-artifact.txt.gz",
        "output_preview": json.dumps([{"text": "preview fallback line", "cls": "", "tsC": "", "tsE": ""}]),
    }
    with mock.patch.object(output_store.log, "warning") as helper_warning_log:
        events = history_api_queries.run_output_events(run)

    assert [event.text for event in events] == ["preview fallback line"]
    assert run["_output_source"] == "preview"
    assert run["_output_fallback"] is True
    assert [call.args[0] for call in helper_warning_log.call_args_list] == ["API_FULL_OUTPUT_LOAD_FAILED"]


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
    monkeypatch.setitem(shell_app_module.CFG, "workspace_enabled", True)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_backend", "tmpfs")
    monkeypatch.setitem(shell_app_module.CFG, "workspace_root", str(tmp_path))
    monkeypatch.setitem(shell_app_module.CFG, "workspace_quota_mb", 1)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_max_file_mb", 1)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_max_files", 10)
    workspace_dir = ensure_session_workspace(token, shell_app_module.CFG)
    (workspace_dir / "reports").mkdir()
    (workspace_dir / "reports" / "artifact.txt").write_text("artifact body", encoding="utf-8")
    (workspace_dir / "reports" / "team-artifact.txt").write_text("personal shadow body", encoding="utf-8")
    team_artifact_path = resolve_owner_workspace_path(
        team_owner_context(team_id, actor_session_id=token),
        "reports/team-artifact.txt",
        shell_app_module.CFG,
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


def test_api_v1_exact_atlas_lookup_is_authenticated_and_owner_scoped():
    import blueprints.api_v1 as api_blueprint
    from services.atlas.materializer import upsert_entity
    from services.intel import cache as intel_cache
    from services.intel import lookup as intel_lookup

    client = get_client()
    token = _token(client)
    other_token = _token(client)
    foreign_project = _create_project(
        client,
        other_token,
        name="Foreign API Lookup " + uuid.uuid4().hex[:8],
    )
    team_response = client.post(
        "/session/teams",
        headers={"X-Session-ID": token},
        json={"name": "API Lookup " + uuid.uuid4().hex[:8], "display_name": "Lookup owner"},
    )
    team_id = json.loads(team_response.data)["team"]["id"]
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        personal_id = upsert_entity(
            conn,
            token,
            "domain",
            "personal-lookup.example",
            seen_at="2026-08-02T00:00:00+00:00",
        )
        team_entity_id = upsert_entity(
            conn,
            token,
            "ip",
            "2001:db8::42",
            team_id=team_id,
            seen_at="2026-08-02T00:00:01+00:00",
        )
        conn.commit()

    private_lookup_value = "PERSONAL-LOOKUP.Example."
    with mock.patch.object(api_blueprint.log, "info") as lookup_info:
        personal_response = client.post(
            "/api/v1/atlas/lookup",
            headers=_headers(token),
            json={"mode": "hostname", "value": private_lookup_value},
        )
    api_private_lookup_value = (
        "https://missing-api.example/private/path?token=api-super-secret#fragment"
    )
    protected_tables = (
        "entities",
        "project_links",
        "runs",
        "entity_intel_snapshots",
        "audit_events",
    )
    with sqlite3.connect(DB_PATH) as conn:
        before_private_lookup = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # nosec
            for table in protected_tables
        }
    with (
        mock.patch.object(api_blueprint.log, "debug") as private_lookup_debug,
        mock.patch.object(api_blueprint.log, "info") as private_lookup_info,
        mock.patch.object(api_blueprint.log, "warning") as private_lookup_warning,
        mock.patch.object(api_blueprint.log, "error") as private_lookup_error,
        mock.patch.object(
            intel_cache,
            "get_cached_response",
            side_effect=AssertionError("API Quick Lookup must not read cached Intel responses"),
        ) as cached_response,
        mock.patch.object(
            intel_cache,
            "get_quota_exhausted",
            side_effect=AssertionError("API Quick Lookup must not read cached Intel quota state"),
        ) as cached_quota,
        mock.patch.object(
            intel_lookup,
            "lookup_entity",
            side_effect=AssertionError("API Quick Lookup must not contact Intel providers"),
        ) as provider_lookup,
    ):
        private_response = client.post(
            "/api/v1/atlas/lookup",
            headers=_headers(token),
            json={"value": api_private_lookup_value},
        )
    with sqlite3.connect(DB_PATH) as conn:
        after_private_lookup = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # nosec
            for table in protected_tables
        }
    cross_response = client.post(
        "/api/v1/atlas/lookup",
        headers=_headers(other_token),
        json={"value": "personal-lookup.example"},
    )
    team_headers = {**_headers(token), "X-Team-ID": team_id}
    team_response = client.post(
        "/api/v1/atlas/lookup",
        headers=team_headers,
        json={"mode": "auto", "value": "2001:0db8::0042"},
    )
    team_from_personal_response = client.post(
        "/api/v1/atlas/lookup",
        headers=_headers(token),
        json={"value": "2001:db8::42"},
    )
    with mock.patch.object(api_blueprint.log, "debug") as lookup_debug:
        invalid_response = client.post(
            "/api/v1/atlas/lookup",
            headers=_headers(token),
            json={"mode": "port", "value": "personal-lookup.example:443"},
        )
        invalid_body_response = client.post(
            "/api/v1/atlas/lookup",
            headers=_headers(token),
            json=["personal-lookup.example"],
        )
        unknown_field_response = client.post(
            "/api/v1/atlas/lookup",
            headers=_headers(token),
            json={"value": "personal-lookup.example", "refresh": True},
        )
    with mock.patch.object(api_blueprint.log, "warning") as lookup_warning:
        foreign_project_response = client.post(
            "/api/v1/atlas/lookup",
            headers=_headers(token),
            json={"value": "personal-lookup.example", "project_id": foreign_project["id"]},
        )
    unauthenticated_response = client.post(
        "/api/v1/atlas/lookup",
        json={"value": "personal-lookup.example"},
    )

    assert personal_response.status_code == 200
    personal = json.loads(personal_response.data)
    assert personal["match_state"] == "found"
    assert personal["detail"]["entity"]["id"] == personal_id
    lookup_completed = next(
        call for call in lookup_info.call_args_list
        if call.args == ("API_ATLAS_LOOKUP_COMPLETED",)
    )
    lookup_fields = lookup_completed.kwargs["extra"]
    assert lookup_fields["surface"] == "api_v1"
    assert lookup_fields["requested_type"] == "hostname"
    assert lookup_fields["detected_type"] == "domain"
    assert lookup_fields["match_state"] == "found"
    assert lookup_fields["scope_kind"] == "personal"
    assert lookup_fields["project_scoped"] is False
    assert lookup_fields["candidate_count"] == 0
    assert lookup_fields["candidates_truncated"] is False
    assert lookup_fields["parent_candidate"] is False
    assert lookup_fields["detail_loaded"] is True
    assert lookup_fields["request_id"]
    assert isinstance(lookup_fields["duration_ms"], int)
    assert private_lookup_value not in repr(lookup_info.call_args_list)
    assert "canonical_value" not in lookup_fields
    assert private_response.status_code == 200
    assert json.loads(private_response.data)["match_state"] == "not_found"
    private_lookup_logs = repr({
        "debug": private_lookup_debug.call_args_list,
        "info": private_lookup_info.call_args_list,
        "warning": private_lookup_warning.call_args_list,
        "error": private_lookup_error.call_args_list,
    })
    assert api_private_lookup_value not in private_lookup_logs
    assert before_private_lookup == after_private_lookup
    cached_response.assert_not_called()
    cached_quota.assert_not_called()
    provider_lookup.assert_not_called()
    assert cross_response.status_code == 200
    assert json.loads(cross_response.data)["match_state"] == "not_found"
    assert team_response.status_code == 200
    team_lookup = json.loads(team_response.data)
    assert team_lookup["match_state"] == "found"
    assert team_lookup["detail"]["entity"]["id"] == team_entity_id
    assert team_lookup["detail"]["scope"]["owner_kind"] == "team"
    assert team_from_personal_response.status_code == 200
    assert json.loads(team_from_personal_response.data)["match_state"] == "not_found"
    assert invalid_response.status_code == 400
    assert json.loads(invalid_response.data)["error"]["code"] == "invalid_lookup_type"
    assert invalid_body_response.status_code == 400
    assert json.loads(invalid_body_response.data)["error"]["code"] == "invalid_body"
    assert unknown_field_response.status_code == 400
    assert json.loads(unknown_field_response.data)["error"]["code"] == "invalid_request"
    assert foreign_project_response.status_code == 400
    assert json.loads(foreign_project_response.data)["error"]["code"] == "invalid_project"
    rejected_reasons = {
        call.kwargs["extra"]["reason"]
        for call in lookup_debug.call_args_list
        if call.args == ("ATLAS_LOOKUP_REJECTED",)
    }
    assert rejected_reasons == {"invalid_lookup_type", "invalid_body", "invalid_request"}
    rejected_warning = next(
        call for call in lookup_warning.call_args_list
        if call.args == ("ATLAS_LOOKUP_REJECTED",)
    )
    assert rejected_warning.kwargs["extra"]["surface"] == "api_v1"
    assert rejected_warning.kwargs["extra"]["reason"] == "invalid_project"
    assert rejected_warning.kwargs["extra"]["project_id"] == foreign_project["id"]
    assert unauthenticated_response.status_code == 401
    assert json.loads(unauthenticated_response.data)["error"]["code"] == "missing_token"


def test_api_v1_project_readers_are_token_scoped():
    client = get_client()
    token = _token(client)
    other_token = _token(client)
    project = _create_project(client, token, name="Scoped API Project")
    run_id = _seed_run(token, command="echo project api", output="project api")
    entity_id = "ent_" + uuid.uuid4().hex[:16]
    port_entity_id = "ent_" + uuid.uuid4().hex[:16]
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
            "INSERT INTO entities "
            "(id, session_id, type, canonical_value, signature_hash, host_entity_id, attributes_json, "
            "first_seen_at, last_seen_at, occurrence_count, created) "
            "VALUES (?, ?, 'port', 'api.darklab.sh:443/tcp', ?, ?, ?, "
            "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00', 1, '2026-05-19T00:00:00+00:00')",
            (port_entity_id, token, "sig_" + uuid.uuid4().hex, entity_id, json.dumps({"service": "https"})),
        )
        conn.execute(
            "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
            "VALUES (?, ?, '2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00', 1)",
            (port_entity_id, run_id),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', '2026-05-19T00:00:00+00:00')",
            ("ple_" + uuid.uuid4().hex[:16], project["id"], entity_id),
        )
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'atlas_entity', ?, 'manual', '2026-05-19T00:00:00+00:00')",
            ("ple_" + uuid.uuid4().hex[:16], project["id"], port_entity_id),
        )
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
            "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, "
            "summary, impact, reproduction_steps, confidence, cve_ids_json, cwe_ids_json, cvss_vector, "
            "cvss_score, references_json, created) "
            "VALUES (?, ?, ?, ?, 'api.darklab.sh', ?, 'medium', 'finding', 'nmap', ?, ?, "
            "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:01+00:00', 1, 'new', "
            "'API finding', 'open port', ?, ?, ?, 'high', ?, ?, ?, 9.8, ?, "
            "'2026-05-19T00:00:01+00:00')",
            (
                finding_id,
                token,
                run_id,
                port_entity_id,
                "sig_" + uuid.uuid4().hex,
                run_id,
                run_id,
                "An exposed administrative service was observed.",
                "An unauthenticated user could reach a privileged endpoint.",
                "Open the endpoint and confirm that it responds without credentials.",
                json.dumps(["CVE-2026-12345", "not-a-cve", "CVE-2026-12345"]),
                json.dumps(["CWE-306", "CWE-invalid", "CWE-306"]),
                "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                json.dumps([
                    "https://example.com/advisories/CVE-2026-12345",
                    "javascript:alert(1)",
                    "https://user:secret@example.com/private",
                    "https://example.com\\@evil.test/advisory",
                ]),
            ),
        )
        conn.execute(
            "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
            "VALUES (?, ?, 2, 'open port', '2026-05-19T00:00:01+00:00')",
            (finding_id, run_id),
        )
        conn.execute(
            "INSERT INTO scan_target_observations "
            "(session_id, team_id, run_id, entity_id, entity_type, canonical_value, scan_kind, "
            "command_root, observed_at, port_entity_count, created) "
            "VALUES (?, '', ?, ?, 'domain', 'api.darklab.sh', 'port_scan', 'nmap', "
            "'2026-05-19T00:00:01+00:00', 1, '2026-05-19T00:00:01+00:00')",
            (token, run_id, entity_id),
        )
        conn.commit()

    triage_save = client.put(
        f"/findings/{finding_id}/triage",
        json={
            "remediation": "Restrict the administrative service and require authentication.",
            "verification_status": "ready_to_verify",
        },
        headers={"X-Session-ID": token},
    )
    owner_project = client.get(f"/api/v1/projects/{project['id']}", headers=_headers(token))
    owner_findings = client.get(
        f"/api/v1/projects/{project['id']}/findings?q=unauthenticated",
        headers=_headers(token),
    )
    owner_runs = client.get(f"/api/v1/projects/{project['id']}/runs", headers=_headers(token))
    owner_entities = client.get(f"/api/v1/projects/{project['id']}/entities?entity_type=domain", headers=_headers(token))
    owner_port_entities = client.get(f"/api/v1/projects/{project['id']}/entities?entity_type=port", headers=_headers(token))
    owner_packages = client.get(f"/api/v1/projects/{project['id']}/packages", headers=_headers(token))
    atlas_summary_resp = client.get("/api/v1/atlas", headers=_headers(token))
    atlas_runs = client.get("/api/v1/atlas/runs", headers=_headers(token))
    atlas_entities = client.get("/api/v1/atlas/entities?entity_type=domain&q=api", headers=_headers(token))
    atlas_port_entities = client.get("/api/v1/atlas/entities?entity_type=port&q=443", headers=_headers(token))
    atlas_entity = client.get(f"/api/v1/atlas/entities/{entity_id}", headers=_headers(token))
    atlas_related_port_findings = client.get(
        f"/api/v1/atlas/entities/{entity_id}?finding_bucket=related_ports",
        headers=_headers(token),
    )
    atlas_invalid_finding_bucket = client.get(
        f"/api/v1/atlas/entities/{entity_id}?finding_bucket=descendants",
        headers=_headers(token),
    )
    project_atlas_entity = client.get(
        f"/api/v1/atlas/entities/{entity_id}?project_id={project['id']}",
        headers=_headers(token),
    )
    atlas_port_entity = client.get(f"/api/v1/atlas/entities/{port_entity_id}", headers=_headers(token))
    atlas_findings = client.get(
        "/api/v1/atlas/findings?q=unauthenticated&review_state=new",
        headers=_headers(token),
    )
    atlas_finding = client.get(f"/api/v1/atlas/findings/{finding_id}", headers=_headers(token))
    cross_project = client.get(f"/api/v1/projects/{project['id']}", headers=_headers(other_token))
    cross_findings = client.get(f"/api/v1/projects/{project['id']}/findings", headers=_headers(other_token))
    cross_runs = client.get(f"/api/v1/projects/{project['id']}/runs", headers=_headers(other_token))
    cross_entities = client.get(f"/api/v1/projects/{project['id']}/entities", headers=_headers(other_token))
    cross_packages = client.get(f"/api/v1/projects/{project['id']}/packages", headers=_headers(other_token))
    cross_atlas_entity = client.get(f"/api/v1/atlas/entities/{entity_id}", headers=_headers(other_token))
    cross_atlas_finding = client.get(f"/api/v1/atlas/findings/{finding_id}", headers=_headers(other_token))

    assert triage_save.status_code == 200
    assert owner_project.status_code == 200
    assert json.loads(owner_project.data)["project"]["id"] == project["id"]
    assert owner_findings.status_code == 200
    owner_finding_payload = json.loads(owner_findings.data)["findings"][0]
    assert owner_finding_payload["id"] == finding_id
    assert owner_finding_payload["origin"] == "run"
    assert owner_finding_payload["validation_method"] == "captured_observation"
    expected_details = {
        "summary": "An exposed administrative service was observed.",
        "impact": "An unauthenticated user could reach a privileged endpoint.",
        "reproduction_steps": "Open the endpoint and confirm that it responds without credentials.",
        "confidence": "high",
        "cve_ids": ["CVE-2026-12345"],
        "cwe_ids": ["CWE-306"],
        "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cvss_score": 9.8,
        "references": ["https://example.com/advisories/CVE-2026-12345"],
    }
    assert {key: owner_finding_payload[key] for key in expected_details} == expected_details
    assert owner_finding_payload["observation_id"].startswith("obs_")
    assert owner_finding_payload["remediation_id"].startswith("rmd_")
    remediation_updated_at = owner_finding_payload["observation_references"][0][
        "remediation_updated_at"
    ]
    assert remediation_updated_at
    assert owner_finding_payload["observation_references"] == [{
        "observation_id": owner_finding_payload["observation_id"],
        "remediation_id": owner_finding_payload["remediation_id"],
        "remediation_group_id": owner_finding_payload["remediation_id"],
        "remediation_group_merged": False,
        "remediation_group_member_count": 1,
        "identity_kind": "vulnerability",
        "vulnerability_id": "CVE-2026-12345",
        "rule_identity": owner_finding_payload["observation_references"][0]["rule_identity"],
        "affected_subject": f"entity:{port_entity_id}",
        "review_state": "new",
        "review_state_source": "remediation_group",
        "disposition_updated_at": remediation_updated_at,
        "has_remediation": True,
        "remediation_preview": "Restrict the administrative service and require authentication.",
        "remediation_source": "remediation_group",
        "remediation_updated_at": remediation_updated_at,
        "validation_method": "captured_observation",
    }]
    assert owner_finding_payload["triage"] == {
        "verification_status": "ready_to_verify",
        "has_remediation": True,
        "has_verification_steps": False,
        "has_verification_notes": False,
        "remediation_preview": "Restrict the administrative service and require authentication.",
        "verification_steps_preview": "",
        "remediation_id": owner_finding_payload["remediation_id"],
        "remediation_group_id": owner_finding_payload["remediation_id"],
        "remediation_group_merged": False,
        "remediation_group_member_count": 1,
        "remediation_source": "remediation_group",
        "remediation_updated_at": remediation_updated_at,
        "verification_disposition": None,
    }
    assert owner_runs.status_code == 200
    assert json.loads(owner_runs.data)["runs"][0]["id"] == run_id
    assert owner_entities.status_code == 200
    assert json.loads(owner_entities.data)["entities"][0]["id"] == entity_id
    assert json.loads(owner_entities.data)["counts_by_type"] == {"domain": 1, "port": 1}
    assert owner_port_entities.status_code == 200
    owner_port_payload = json.loads(owner_port_entities.data)
    assert owner_port_payload["entities"][0]["id"] == port_entity_id
    assert owner_port_payload["entities"][0]["type"] == "port"
    assert owner_port_payload["entities"][0]["host_entity_id"] == entity_id
    assert owner_port_payload["entities"][0]["attributes"] == {"service": "https"}
    assert owner_packages.status_code == 200
    assert json.loads(owner_packages.data)["total"] == 1
    assert atlas_summary_resp.status_code == 200
    assert json.loads(atlas_summary_resp.data)["counts"]["domain"] >= 1
    assert atlas_runs.status_code == 200
    assert json.loads(atlas_runs.data)["runs"][0]["id"] == run_id
    assert atlas_entities.status_code == 200
    assert json.loads(atlas_entities.data)["entities"][0]["id"] == entity_id
    assert atlas_port_entities.status_code == 200
    atlas_port_payload = json.loads(atlas_port_entities.data)
    assert atlas_port_payload["entities"][0]["id"] == port_entity_id
    assert atlas_port_payload["entities"][0]["type"] == "port"
    assert atlas_port_payload["entities"][0]["host_entity_id"] == entity_id
    assert atlas_port_payload["entities"][0]["attributes"] == {"service": "https"}
    assert atlas_entity.status_code == 200
    atlas_entity_payload = json.loads(atlas_entity.data)
    assert atlas_entity_payload["entity"]["id"] == entity_id
    assert atlas_entity_payload["related_ports"][0]["id"] == port_entity_id
    assert atlas_entity_payload["finding_summary"]["direct"]["total"] == 0
    assert atlas_entity_payload["finding_summary"]["related_ports"]["total"] == 1
    assert atlas_entity_payload["finding_summary"]["related_ports"]["by_severity"]["medium"] == 1
    assert atlas_entity_payload["finding_summary"]["combined"]["total"] == 1
    assert atlas_related_port_findings.status_code == 200
    atlas_related_port_payload = json.loads(atlas_related_port_findings.data)
    assert [finding["id"] for finding in atlas_related_port_payload["findings"]] == [finding_id]
    assert atlas_related_port_payload["findings"][0]["origin"] == "run"
    assert atlas_related_port_payload["findings"][0]["validation_method"] == "captured_observation"
    assert {
        key: atlas_related_port_payload["findings"][0][key]
        for key in expected_details
    } == expected_details
    assert atlas_related_port_payload["detail_limits"]["findings"] == {
        "bucket": "related_ports",
        "limit": 50,
        "offset": 0,
        "shown": 1,
        "total": 1,
        "has_more": False,
    }
    assert atlas_invalid_finding_bucket.status_code == 400
    assert json.loads(atlas_invalid_finding_bucket.data)["error"]["code"] == "invalid_request"
    assert atlas_entity_payload["overview"]["observed"]["app_evidence"]["coverage_state"] == "app_ports_found"
    assert atlas_entity_payload["overview"]["observed"]["app_evidence"]["app_port_count"] == 1
    assert atlas_entity_payload["overview"]["observed"]["project_monitoring"]["applicable"] is False
    assert atlas_entity_payload["overview"]["observed"]["project_monitoring"]["state"] == "not_applicable"
    assert atlas_entity_payload["overview"]["observed"]["app_ports"] == [{
        "port": 443,
        "proto": "tcp",
        "service": "https",
        "version": "",
        "banner_available": False,
        "occurrence_count": 1,
        "last_seen_at": "2026-05-19T00:00:00+00:00",
        "source_run_count": 1,
        "service_evidence_state": "identified",
        "assessment_actions": [{
            "key": "https_profile",
            "label": "Review HTTPS surface",
            "rationale": "The service identified an HTTPS endpoint.",
            "command": "command:httpx",
            "policy_level": "standard",
            "target_types": ["domain", "ip", "url"],
            "required_features": ["confirmed_project_target", "httpx"],
            "expected_evidence": [
                "atlas_service_entity", "http_metadata", "tls_metadata",
            ],
            "unsupported_conditions": [
                "ambiguous_service", "conflicting_service_evidence", "port_only_inference",
            ],
        }],
    }]
    assert atlas_entity_payload["overview"]["observed"]["app_services"] == ["https"]
    assert atlas_entity_payload["overview"]["observed"]["app_ports_truncated"] is False
    assert atlas_entity_payload["overview"]["finding_summary"] == atlas_entity_payload["finding_summary"]
    assert atlas_entity_payload["overview"]["intel"] == {
        "status": "none",
        "freshness": "not_available",
        "snapshot_count": 0,
        "provider_count": 0,
        "providers_with_data": [],
        "last_refresh_at": "",
        "highlight_count": 0,
        "highlights": [],
        "provider_ports": [],
        "provider_services": [],
        "certificate": {
            "status": "unknown",
            "expires_at": "",
            "days_until_expiry": None,
            "last_checked_at": "",
        },
        "port_provenance": {
            "app": atlas_entity_payload["overview"]["observed"]["app_ports"],
            "provider": [],
            "divergence": {
                "app_only": [443],
                "provider_only": [],
                "has_drift": False,
            },
        },
        "summary": atlas_entity_payload["intel_summary"],
    }
    assert project_atlas_entity.status_code == 200
    project_atlas_payload = json.loads(project_atlas_entity.data)
    assert project_atlas_payload["scope"] == {
        "kind": "project",
        "owner_kind": "personal",
        "project_id": project["id"],
        "team_id": "",
    }
    assert project_atlas_payload["related_ports"][0]["open_hint"] == {
        "entity_id": port_entity_id,
        "project_id": project["id"],
    }
    assert project_atlas_payload["finding_summary"]["combined"]["total"] == 1
    assert project_atlas_payload["overview"]["observed"]["app_evidence"]["scan_run_count"] == 1
    assert project_atlas_payload["overview"]["observed"]["app_evidence"]["project_entity_port_count"] == 1
    assert project_atlas_payload["overview"]["observed"]["project_monitoring"]["applicable"] is True
    assert project_atlas_payload["overview"]["observed"]["project_monitoring"]["project_id"] == project["id"]
    assert project_atlas_payload["overview"]["observed"]["project_monitoring"]["state"] == "not_monitored"
    assert project_atlas_payload["overview"]["observed"]["app_ports"] == atlas_entity_payload["overview"]["observed"]["app_ports"]
    assert atlas_port_entity.status_code == 200
    atlas_port_detail = json.loads(atlas_port_entity.data)
    assert atlas_port_detail["parent_host"]["id"] == entity_id
    assert atlas_port_detail["finding_summary"]["direct"]["total"] == 1
    assert atlas_port_detail["finding_summary"]["related_ports"]["applicable"] is False
    assert atlas_port_detail["overview"]["observed"]["app_evidence"]["host_entity_id"] == entity_id
    assert atlas_port_detail["overview"]["observed"]["app_evidence"]["coverage_state"] == "app_ports_found"
    assert atlas_findings.status_code == 200
    atlas_finding_row = json.loads(atlas_findings.data)["findings"][0]
    assert atlas_finding_row["id"] == finding_id
    assert atlas_finding_row["origin"] == "run"
    assert atlas_finding_row["validation_method"] == "captured_observation"
    assert {key: atlas_finding_row[key] for key in expected_details} == expected_details
    assert atlas_finding_row["triage"]["remediation_preview"] == (
        "Restrict the administrative service and require authentication."
    )
    assert atlas_finding.status_code == 200
    atlas_finding_payload = json.loads(atlas_finding.data)
    assert atlas_finding_payload["finding"]["origin"] == "run"
    assert atlas_finding_payload["finding"]["validation_method"] == "captured_observation"
    assert atlas_finding_payload["finding"]["observation_id"] == owner_finding_payload["observation_id"]
    assert atlas_finding_payload["finding"]["remediation_id"] == owner_finding_payload["remediation_id"]
    assert {
        key: atlas_finding_payload["finding"][key]
        for key in expected_details
    } == expected_details
    assert atlas_finding_payload["occurrences"][0]["run_id"] == run_id
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
    monkeypatch.setitem(shell_app_module.CFG, "run_broker_require_redis", False)

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

    public_started = SimpleNamespace(
        run_id="run-public-context",
        status="running",
        cmd_type="real",
    )
    with mock.patch.object(
        api_blueprint,
        "_start_brokered_run_service",
        return_value=public_started,
    ) as public_start:
        public_response = client.post(
            "/api/v1/runs",
            json={
                "command": "echo public",
                "output_signal_context": {"nuclei_takeover_template": "caller-made"},
            },
            headers=_headers(token),
        )
    assert public_response.status_code == 202
    assert "output_signal_context" not in public_start.call_args.kwargs

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
    monkeypatch.setitem(shell_app_module.CFG, "run_broker_require_redis", False)
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

    monkeypatch.setitem(shell_app_module.CFG, "run_broker_require_redis", False)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_enabled", True)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_backend", "tmpfs")
    monkeypatch.setitem(shell_app_module.CFG, "workspace_root", str(tmp_path))
    monkeypatch.setitem(shell_app_module.CFG, "workspace_quota_mb", 1)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_max_file_mb", 1)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_max_files", 10)
    monkeypatch.setitem(shell_app_module.CFG, "workspace_inactivity_ttl_hours", 1)

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

    assert link is not None
    assert row is not None
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
    launched_run_id = "run_api_watcher_" + uuid.uuid4().hex[:8]
    monkeypatch.setattr(api_blueprint, "validate_schedule_command", lambda command, *_args, **_kwargs: command.strip())
    monkeypatch.setattr(
        dispatch,
        "_launch_user_schedule_run",
        lambda _schedule, **_kwargs: launched_run_id,
    )

    create = client.post(
        "/api/v1/watchers",
        headers=_headers(token),
        json={
            "baseline_run_id": baseline_run_id,
            "cadence_preset": "hourly",
            "label": "API Watcher",
            "timezone": "UTC",
            "options": {"suppress_removals": True, "notify_metadata_changes": False},
            "policy": {
                "ignore_line_patterns": ["timing jitter"],
                "alert_after_repeated_changes": 2,
                "alert_signal_classes": ["ports"],
            },
        },
    )
    watcher = json.loads(create.data)["watcher"]

    assert create.status_code == 201
    assert watcher["command_text"] == "nmap -sV darklab.sh"
    assert watcher["baseline_run_id"] == baseline_run_id
    assert watcher["state"] == "ok"
    assert watcher["options"]["suppress_removals"] is True
    assert watcher["policy"]["alert_after_repeated_changes"] == 2
    assert watcher["policy"]["alert_signal_classes"] == ["ports"]
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
    _seed_run(
        token,
        run_id=launched_run_id,
        command="nmap -sV darklab.sh",
        output="22/tcp open ssh\n443/tcp open https",
    )
    accepted = json.loads(
        client.post(
            f"/api/v1/watchers/{watcher['id']}/accept-baseline",
            headers=_headers(token),
            json={"run_id": launched_run_id},
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
    assert fired["watcher"]["last_run_id"] == launched_run_id
    assert fires["total"] == 1
    assert fires["fires"][0]["run_id"] == launched_run_id
    assert accepted["baseline_run_id"] == launched_run_id
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
    assert audit_rows[3]["details"]["run_id"] == launched_run_id
    assert audit_rows[4]["details"]["baseline_run_id"] == launched_run_id
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
    monkeypatch.setattr(
        dispatch,
        "_launch_user_schedule_run",
        lambda _schedule, **_kwargs: "run_api_team_watcher",
    )
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
            "http_status": 400,
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
        "project_id": "prj_cli",
        "baseline_run_id": "run_base",
        "last_run_id": "",
        "last_diff_summary": {
            "added_line_count": 1,
            "removed_line_count": 0,
        },
        "label": "Hourly Watch",
        "command_text": "nmap -sV darklab.sh",
        "options": {"suppress_removals": True, "notify_metadata_changes": False},
        "policy": {
            "ignore_line_patterns": ["^Host is up"],
            "alert_after_repeated_changes": 2,
            "alert_signal_classes": ["ports"],
        },
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
                    "project_id": body.get("project_id"),
                    "timezone": None,
                    "enabled": True,
                    "options": {
                        "suppress_removals": bool(body.get("command")),
                        "notify_metadata_changes": False,
                    },
                    "policy": body.get("policy"),
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
                if "project_id" in body:
                    return {"watcher": {**watcher, "project_id": body["project_id"]}}
                if "policy" in body:
                    assert body["policy"] == {
                        "ignore_line_patterns": ["^Host is up", "^RTT jitter"],
                        "alert_after_repeated_changes": 3,
                        "alert_signal_classes": ["findings", "ports"],
                    }
                    return {"watcher": {**watcher, "policy": body["policy"]}}
                if body.get("resume") is True:
                    return {"watcher": {**watcher, "state": "ok"}}
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
                        "fire_kind": "changed",
                        "state_reason": "diff_detected",
                        "ack_state": "new",
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
        "--project",
        "prj_cli",
        "--suppress-removals",
        "--ignore-line-pattern",
        "^Host is up",
        "--alert-after-repeated-changes",
        "2",
        "--alert-signal-class",
        "ports",
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
    assert "prj_cli" in info_output
    assert "2026-05-20 00:00:00 UTC" in info_output
    assert "diff_detected" in info_output
    assert "new" in info_output
    assert "nmap -sV darklab.sh" in info_output
    assert "suppress-removals" in info_output
    assert "ignore-line-patterns: ^Host is up" in info_output
    assert "alert-after-repeated-changes: 2" in info_output
    assert "alert-signal-classes: ports" in info_output
    assert cli_main.main(["watch", "pause", "wtr_cli"]) == 0
    assert "paused" in capsys.readouterr().out
    assert cli_main.main(["watch", "resume", "wtr_cli"]) == 0
    assert "ok" in capsys.readouterr().out
    assert cli_main.main(["watch", "run", "wtr_cli"]) == 0
    assert "fire: fired" in capsys.readouterr().out
    assert cli_main.main(["watch", "fires", "wtr_cli", "--limit", "5"]) == 0
    fires_output = capsys.readouterr().out
    assert "textual" in fires_output
    assert "changed" in fires_output
    assert "diff_detected" in fires_output
    assert "new" in fires_output
    assert cli_main.main(["watch", "accept", "wtr_cli", "--run-id", "run_fire"]) == 0
    assert "run_fire" in capsys.readouterr().out
    assert cli_main.main(["watch", "set-project", "wtr_cli", "--clear"]) == 0
    assert "wtr_cli" in capsys.readouterr().out
    assert cli_main.main([
        "watch",
        "set-policy",
        "wtr_cli",
        "--ignore-line-pattern",
        "^Host is up",
        "--ignore-line-pattern",
        "^RTT jitter",
        "--alert-after-repeated-changes",
        "3",
        "--alert-signal-class",
        "findings",
        "--alert-signal-class",
        "ports",
    ]) == 0
    assert "wtr_cli" in capsys.readouterr().out
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
        "/watchers/wtr_cli",
        "/watchers/wtr_cli",
        "/watchers/wtr_cli",
    ]


def test_api_v1_openapi_generator_snapshot_is_current():
    from services.api_v1.openapi import openapi_spec

    checked_in = (ROOT_DIR / "docs" / "api-v1-openapi.json").read_text(encoding="utf-8")
    generated = json.dumps(openapi_spec(), indent=2, sort_keys=True) + "\n"

    assert generated == checked_in


def test_probe_openapi_schemas_validate_real_api_payloads(monkeypatch):
    from services.api_v1.openapi import openapi_spec
    from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
    from services.nuclei.template_health import NucleiTemplateHealth

    client = get_client()
    token = _token(client)
    project = _create_project(client, token, name="Probe OpenAPI")
    entity_id, _run_id = _seed_assessment_target(token, project["id"])
    with sqlite3.connect(DB_PATH) as conn:
        target_value = conn.execute(
            "SELECT canonical_value FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()[0]
    snapshot = NucleiTemplateCacheSnapshot(
        "ready", "v10.4.3", "sha256:" + "a" * 64, 12,
    )
    monkeypatch.setattr(
        "services.assessments.probe_runtime.template_cache.managed_nuclei_template_snapshot",
        lambda: snapshot,
    )
    monkeypatch.setattr(
        "services.assessments.probe_runtime.template_health.managed_nuclei_template_health",
        lambda **_kwargs: NucleiTemplateHealth(
            "ready", snapshot, "passed", "v3.4.10"
        ),
    )
    monkeypatch.setattr(
        "services.assessments.probe_runtime.resolve_runtime_command",
        lambda command: f"/usr/bin/{command}",
    )
    headers = _headers(token)
    base = f"/api/v1/projects/{project['id']}/probes"
    catalog = client.get(base, headers=headers).get_json()
    resolved = client.post(
        f"{base}/targets/resolve",
        headers=headers,
        json={"target_value": target_value},
    ).get_json()
    plan_response = client.post(
        f"{base}/plan",
        headers=headers,
        json={"action_id": "ping", "entity_id": entity_id},
    ).get_json()
    plan = plan_response["plan"]
    monkeypatch.setattr(
        "blueprints.api_v1._start_brokered_run_service",
        lambda **_kwargs: SimpleNamespace(run_id="run_probe_openapi", status="queued"),
    )
    monkeypatch.setattr("blueprints.api_v1.broker_available", lambda: True)
    launched = client.post(
        f"{base}/run",
        headers=headers,
        json={
            "action_id": "ping", "entity_id": entity_id,
            "confirmed": True, "plan_digest": plan["plan_digest"],
        },
    ).get_json()
    monkeypatch.setattr(
        "services.assessments.probe_runtime.resolve_runtime_command",
        lambda _command: "",
    )
    unavailable = client.post(
        f"{base}/plan",
        headers=headers,
        json={"action_id": "ping", "entity_id": entity_id},
    ).get_json()

    spec = openapi_spec()
    schemas = spec["components"]["schemas"]
    assert schemas["ProbeCatalog"]["properties"]["actions"]["items"] == {
        "$ref": "#/components/schemas/ProbeCatalogAction"
    }
    assert schemas["ProbePlan"]["properties"]["bounds"] == {
        "$ref": "#/components/schemas/ProbeBounds"
    }
    assert schemas["ProbeRunResponse"]["properties"]["run"] == {
        "$ref": "#/components/schemas/ProbeStartedRun"
    }
    for schema_name in (
        "ProbeCatalogAction", "ProbeServiceRecommendation", "ProbeTarget",
        "ProbeHttpScope", "ProbeBounds", "ProbeStartedRun",
    ):
        assert schemas[schema_name]["required"]
        assert schemas[schema_name]["additionalProperties"] is False
    for payload, schema_name in (
        (catalog, "ProbeCatalogResponse"),
        (resolved, "ProbeTargetResolveResponse"),
        (plan_response, "ProbePlanResponse"),
        (unavailable, "ProbePlanResponse"),
        (launched, "ProbeRunResponse"),
    ):
        _assert_openapi_payload(payload, schemas[schema_name], schemas)

    paths = spec["paths"]
    plan_examples = paths["/projects/{project_id}/probes/plan"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    for example in plan_examples.values():
        _assert_openapi_payload(example["value"], schemas["ProbePlanResponse"], schemas)
    stable_error = paths["/projects/{project_id}/probes/run"]["post"]["responses"]["409"][
        "content"
    ]["application/json"]["example"]
    _assert_openapi_payload(stable_error, schemas["ApiError"], schemas)


def test_api_v1_openapi_contract_describes_public_shapes():
    from services.api_v1.openapi import openapi_spec

    spec = openapi_spec()
    schemas = spec["components"]["schemas"]
    assert {
        "ActiveRunList",
        "ApiError",
        "AtlasEntity",
        "AtlasEntityDetail",
        "AtlasEntityLookupCandidate",
        "AtlasEntityLookupParentCandidate",
        "AtlasEntityLookupRequest",
        "AtlasEntityLookupResponse",
        "AtlasEntityPage",
        "AtlasFinding",
        "AtlasFindingDetail",
        "AtlasFindingPage",
        "AtlasRunList",
        "AtlasSourceRun",
        "AtlasSummary",
        "ArtifactSummary",
        "CveRiskFeedStatus",
        "CveRiskFeedStatusList",
        "EvidencePackage",
        "Health",
        "HistorySearchMatch",
        "HistorySearchPage",
        "NdjsonStream",
        "OsvLookupRequest",
        "OsvLookupResponse",
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
        "WatcherPolicy",
        "WatcherResponse",
        "WatcherRunNowResponse",
        "WatcherUpdateRequest",
    }.issubset(schemas)
    assert spec["paths"]["/runs"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RunStartRequest"
    }
    osv_lookup = spec["paths"]["/advisories/osv/lookup"]["post"]
    assert osv_lookup["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/OsvLookupRequest"
    }
    assert osv_lookup["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/OsvLookupResponse"
    }
    assert "supplied PURL and version" in osv_lookup["description"]
    assert schemas["OsvLookupRequest"]["required"] == ["purl", "version"]
    assert schemas["OsvLookupRequest"]["additionalProperties"] is False
    risk_feeds = spec["paths"]["/risk/feeds"]["get"]
    assert risk_feeds["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CveRiskFeedStatusList"
    }
    assert "never refreshes a feed" in risk_feeds["description"]
    assert schemas["CveRiskFeedStatus"]["properties"]["status"]["enum"] == [
        "unavailable", "current", "stale", "failed",
    ]
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
    assert "assessment_finding_changes" in schemas["ProjectFindingPage"]["required"]
    assert schemas["ProjectFindingPage"]["properties"]["assessment_finding_changes"] == {
        "nullable": True,
        "allOf": [{"$ref": "#/components/schemas/AssessmentFindingChangesHandoff"}],
    }
    assert schemas["ProjectRunPage"]["properties"]["runs"]["items"] == {"$ref": "#/components/schemas/ProjectRun"}
    assert schemas["ProjectEntityPage"]["properties"]["entities"]["items"] == {"$ref": "#/components/schemas/ProjectEntity"}
    assert schemas["AtlasEntityPage"]["properties"]["entities"]["items"] == {"$ref": "#/components/schemas/AtlasEntity"}
    assert schemas["AtlasFindingPage"]["properties"]["findings"]["items"] == {"$ref": "#/components/schemas/AtlasFinding"}
    assert schemas["AtlasFinding"]["properties"]["origin"]["enum"] == ["run", "import", "manual"]
    assert schemas["ProjectFinding"]["properties"]["validation_method"]["enum"] == [
        "captured_observation",
        "active_confirmation",
        "version_inference",
        "imported_assertion",
        "manual_assessment",
    ]
    finding_detail_fields = {
        "summary",
        "impact",
        "reproduction_steps",
        "confidence",
        "cve_ids",
        "cwe_ids",
        "cvss_vector",
        "cvss_score",
        "references",
    }
    for schema_name in ("AtlasFinding", "ProjectFinding"):
        assert finding_detail_fields.issubset(schemas[schema_name]["required"])
        assert finding_detail_fields.issubset(schemas[schema_name]["properties"])
        assert {
            "rule_identity",
            "observation_id",
            "remediation_id",
            "remediation_group_id",
            "remediation_group_merged",
            "remediation_group_member_count",
            "observation_references",
            "remediation_groups",
        }.issubset(schemas[schema_name]["required"])
    assert schemas["FindingObservationReference"]["properties"]["identity_kind"]["enum"] == [
        "vulnerability",
        "rule",
    ]
    assert schemas["ProjectFinding"]["properties"]["confidence"]["enum"] == [
        "unknown",
        "low",
        "medium",
        "high",
    ]
    assert schemas["AtlasFinding"]["properties"]["references"]["maxItems"] == 50
    assert schemas["AtlasFinding"]["properties"]["cvss_score"] == {
        "type": "number",
        "minimum": 0,
        "maximum": 10,
        "nullable": True,
    }
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
    atlas_entity_params = {param["name"]: param for param in spec["paths"]["/atlas/entities"]["get"]["parameters"]}
    assert {"entity_type", "q", "project_id", "run_id", "orphan_filter", "suppression_filter", "limit", "offset"}.issubset(
        atlas_entity_params
    )
    assert "port" in atlas_entity_params["entity_type"]["schema"]["enum"]
    assert spec["paths"]["/atlas/lookup"]["post"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AtlasEntityLookupRequest"
    }
    assert spec["paths"]["/atlas/lookup"]["post"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AtlasEntityLookupResponse"}
    assert schemas["AtlasEntityLookupRequest"]["required"] == ["value"]
    assert schemas["AtlasEntityLookupRequest"]["additionalProperties"] is False
    assert schemas["AtlasEntityLookupRequest"]["properties"]["value"]["minLength"] == 1
    assert "2,048 UTF-8 bytes" in schemas["AtlasEntityLookupRequest"]["properties"]["value"]["description"]
    assert "http:// or https://" in schemas["AtlasEntityLookupRequest"]["properties"]["mode"]["description"]
    assert schemas["AtlasEntityLookupResponse"]["properties"]["detail"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/AtlasEntityDetail"},
            {"type": "null"},
        ]
    }
    assert schemas["AtlasEntityLookupResponse"]["properties"]["match_state"]["enum"] == [
        "found",
        "not_found",
        "ambiguous",
    ]
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
    project_entity_params = {
        param["name"]: param for param in spec["paths"]["/projects/{project_id}/entities"]["get"]["parameters"]
    }
    assert {"entity_type", "run_id", "target_id", "limit", "offset"}.issubset(project_entity_params)
    assert "port" in project_entity_params["entity_type"]["schema"]["enum"]
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


def test_api_v1_openapi_contract_describes_project_assessments():
    from services.api_v1.openapi import openapi_spec

    spec = openapi_spec()
    schemas = spec["components"]["schemas"]
    paths = spec["paths"]
    assessment_path = "/projects/{project_id}/assessments/{assessment_id}"
    batch_preview_path = assessment_path + "/batch-previews"
    batch_preview_read_path = "/assessment-batch-previews/{preview_id}"
    batch_preview_items_path = batch_preview_read_path + "/items"
    batch_list_path = "/projects/{project_id}/assessment-batches"
    batch_start_path = assessment_path + "/assessment-batches"
    batch_cancel_path = (
        "/projects/{project_id}/assessment-batches/{batch_id}/cancel"
    )
    batch_retry_preview_path = (
        "/projects/{project_id}/assessment-batches/{batch_id}/retry-previews"
    )
    batch_retry_path = "/projects/{project_id}/assessment-batches/{batch_id}/retry"
    batch_path = "/assessment-batches/{batch_id}"
    batch_items_path = batch_path + "/items"
    batch_events_path = batch_path + "/events"
    check_path = assessment_path + "/checks/{check_id}"
    action_path = check_path + "/recommended-action"
    zap_plan_path = check_path + "/zap-plan"
    zap_jobs_path = check_path + "/zap-jobs"
    zap_job_path = zap_jobs_path + "/{job_id}"
    oast_correlations_path = check_path + "/oast-correlations"
    oast_correlation_path = oast_correlations_path + "/{correlation_id}"
    oast_launch_path = oast_correlation_path + "/launch"
    evidence_path = check_path + "/evidence"
    evidence_link_path = evidence_path + "/{evidence_link_id}"
    run_evidence_path = "/runs/{run_id}/service-evidence"

    assert set(paths["/projects/{project_id}/assessments"]) == {"get", "post"}
    assert set(paths[assessment_path]) == {"get", "patch", "delete"}
    assert set(paths[batch_preview_path]) == {"post"}
    assert set(paths[batch_preview_read_path]) == {"get"}
    assert set(paths[batch_preview_items_path]) == {"get"}
    assert set(paths[batch_list_path]) == {"get"}
    assert set(paths[batch_start_path]) == {"post"}
    assert set(paths[batch_cancel_path]) == {"post"}
    assert set(paths[batch_retry_preview_path]) == {"post"}
    assert set(paths[batch_retry_path]) == {"post"}
    assert set(paths[batch_path]) == {"get"}
    assert set(paths[batch_items_path]) == {"get"}
    assert set(paths[batch_events_path]) == {"get"}
    assert set(paths[check_path]) == {"patch"}
    assert set(paths[action_path]) == {"get", "post"}
    assert set(paths[zap_plan_path]) == {"post"}
    assert set(paths[zap_jobs_path]) == {"get", "post"}
    assert set(paths[zap_job_path]) == {"get", "delete"}
    assert set(paths[oast_correlations_path]) == {"get", "post"}
    assert set(paths[oast_correlation_path]) == {"get"}
    assert set(paths[oast_launch_path]) == {"post"}
    assert set(paths[evidence_path]) == {"post"}
    assert set(paths[evidence_link_path]) == {"delete"}
    assert set(paths[run_evidence_path]) == {"get"}
    assert paths["/projects/{project_id}/assessments"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentCreateRequest"}
    assert paths["/projects/{project_id}/assessments"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AssessmentCyclePage"
    }
    assert schemas["AssessmentCyclePage"]["properties"]["profiles"]["items"] == {
        "$ref": "#/components/schemas/AssessmentProfileSummary"
    }
    assert schemas["AssessmentProfileSummary"]["additionalProperties"] is False
    batch_request = schemas["AssessmentBatchPreviewSelection"]
    assert batch_request["additionalProperties"] is False
    assert batch_request["properties"]["item_limit"]["maximum"] == 512
    assert batch_request["properties"]["max_parallel"]["maximum"] == 8
    assert batch_request["properties"]["max_owner_parallel"]["maximum"] == 32
    assert batch_request["properties"]["max_instance_parallel"]["maximum"] == 64
    assert "source_batch_id" in schemas["AssessmentBatchPreview"]["required"]
    assert schemas["AssessmentBatchPreview"]["properties"]["source_batch_id"] == {
        "type": "string"
    }
    assert schemas["AssessmentBatchPreviewSummary"]["properties"][
        "source_retry_eligible_item_count"
    ] == {"type": "integer", "minimum": 0}
    assert paths[batch_preview_path]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentBatchPreviewResponse"}
    assert schemas["AssessmentBatchPreviewItemPage"]["properties"]["items"][
        "maxItems"
    ] == 100
    assert schemas["AssessmentBatchProgress"]["properties"]["skipped"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert paths[batch_list_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentBatchList"}
    assert schemas["AssessmentBatchStartRequest"]["additionalProperties"] is False
    assert schemas["AssessmentBatchStartRequest"]["properties"]["confirmed"] == {
        "type": "boolean",
        "enum": [True],
    }
    assert paths[batch_start_path]["post"]["responses"]["202"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentBatchStartResponse"}
    assert paths[batch_cancel_path]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentBatchCancelResponse"}
    assert paths[batch_retry_preview_path]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentBatchPreviewResponse"}
    assert paths[batch_retry_path]["post"]["responses"]["202"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentBatchStartResponse"}
    assert schemas["AssessmentBatchItemPage"]["properties"]["items"][
        "maxItems"
    ] == 100
    assert schemas["AssessmentBatchEventPage"]["properties"]["events"][
        "maxItems"
    ] == 100
    assert paths[assessment_path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AssessmentDetail"}
    assert paths[evidence_path]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AssessmentEvidenceLinkResponse"}
    assert paths[action_path]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AssessmentActionPreview"}
    action_preview_params = {
        parameter["name"]: parameter
        for parameter in paths[action_path]["get"]["parameters"]
    }
    assert "http_profile_id" in action_preview_params
    assert "source_run_id" in action_preview_params
    assert "parameter_observation_id" in action_preview_params
    assert "schema_artifact_id" in action_preview_params
    assert paths[action_path]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AssessmentActionLaunchRequest"}
    assert schemas["AssessmentActionPlan"]["properties"]["oast"] == {
        "$ref": "#/components/schemas/AssessmentOastPlanState"
    }
    assert paths[oast_correlations_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentOastReserveRequest"}
    assert paths[oast_correlations_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {
        "$ref": "#/components/schemas/AssessmentOastCorrelationListResponse"
    }
    assert paths[oast_correlation_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {
        "$ref": "#/components/schemas/AssessmentOastCorrelationResponse"
    }
    assert schemas["AssessmentOastReserveRequest"]["required"] == [
        "confirmed",
        "plan_digest",
        "source_run_id",
        "parameter_observation_id",
    ]
    assert schemas["AssessmentOastCorrelation"]["properties"]["callback_url"] == {
        "type": "string"
    }
    assert paths[zap_plan_path]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/AssessmentZapPlanRequest"}
    assert paths[zap_jobs_path]["post"]["responses"]["202"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentZapJobResponse"}
    assert paths[zap_jobs_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AssessmentZapJobListResponse"}
    assert schemas["AssessmentZapPlanRequest"]["additionalProperties"] is False
    assert schemas["AssessmentZapPlanRequest"]["properties"]["target_entity_ids"][
        "maxItems"
    ] == 8
    assert schemas["AssessmentZapSubmitRequest"]["properties"]["confirmed"] == {
        "type": "boolean",
        "enum": [True],
    }
    assert schemas["AssessmentZapJob"]["properties"]["status"]["enum"] == [
        "queued",
        "submitting",
        "running",
        "cancel_requested",
        "downloading",
        "ready",
        "imported",
        "canceled",
        "failed",
        "expired",
    ]
    assert "http_profile_id" in schemas["AssessmentActionLaunchRequest"]["properties"]
    assert "source_run_id" in schemas["AssessmentActionLaunchRequest"]["properties"]
    assert "parameter_observation_id" in schemas["AssessmentActionLaunchRequest"]["properties"]
    assert "schema_artifact_id" in schemas["AssessmentActionLaunchRequest"]["properties"]
    assert "evidence_selection" in schemas["AssessmentActionPlan"]["properties"]
    assert "artifact_selection" in schemas["AssessmentActionPlan"]["properties"]
    assert schemas["AssessmentActionPlan"]["properties"]["nuclei_profile"] == {
        "$ref": "#/components/schemas/AssessmentNucleiTemplateProfile",
    }
    assert schemas["AssessmentNucleiTemplateProfile"]["additionalProperties"] is False
    assert schemas["AssessmentNucleiTemplateProfile"]["properties"]["update_policy"] == {
        "type": "string",
        "enum": ["explicit_only"],
    }
    assert schemas["AssessmentNucleiTemplateProfile"]["properties"]["template_snapshot"] == {
        "$ref": "#/components/schemas/AssessmentNucleiTemplateSnapshot",
    }
    assert schemas["AssessmentNucleiTemplateSnapshot"]["properties"]["content_digest"] == {
        "type": "string",
        "pattern": "^(?:sha256:[a-f0-9]{64})?$",
    }
    assert schemas["AssessmentNucleiTemplateSnapshot"]["properties"]["refreshed_at"] == {
        "type": "string",
        "format": "date-time",
    }
    assert schemas["AssessmentBatchPreviewSummary"]["properties"]["nuclei_preflight"] == {
        "$ref": "#/components/schemas/AssessmentBatchNucleiPreflight",
    }
    assert schemas["AssessmentBatchNucleiPreflight"]["properties"]["state"]["enum"] == [
        "ready",
        "stale",
        "missing",
        "oversized",
        "invalid",
        "unreadable",
        "maintenance",
        "incompatible",
        "unavailable",
    ]
    assert "nuclei_snapshot_confirmed" in schemas["AssessmentBatchStartRequest"]["properties"]
    assert schemas["AssessmentOpenApiArtifactSelection"]["properties"]["options"][
        "maxItems"
    ] == 64
    assert schemas["FindingVerificationActionPlan"]["properties"]["bounds"]["properties"][
        "credential_use"
    ]["enum"] == ["none", "protected_http_profile"]

    detail_params = {
        parameter["name"]
        for parameter in paths[assessment_path]["get"]["parameters"]
    }
    assert {
        "project_id",
        "assessment_id",
        "category",
        "state",
        "target_type",
        "policy_level",
        "evidence_state",
        "finding_priority",
        "finding_limit",
        "finding_offset",
        "limit",
        "offset",
    } == detail_params
    assert schemas["AssessmentManualStateRequest"]["properties"]["state"]["enum"] == [
        "not_started",
        "blocked",
        "skipped",
        "not_applicable",
    ]
    assert schemas["AssessmentCheck"]["properties"]["state"]["enum"] == [
        "not_started",
        "running",
        "covered",
        "needs_review",
        "blocked",
        "failed",
        "skipped",
        "not_applicable",
    ]
    assert schemas["AssessmentCheck"]["properties"]["nmap_service_evidence"] == {
        "$ref": "#/components/schemas/NmapServiceEvidencePage",
    }
    assert schemas["AssessmentCheck"]["properties"]["manual_evidence"] == {
        "$ref": "#/components/schemas/AssessmentEvidencePage",
    }
    assert schemas["AssessmentCheck"]["properties"]["evidence_previews"] == {
        "$ref": "#/components/schemas/AssessmentEvidencePage",
    }
    assert schemas["AssessmentEvidencePage"]["properties"]["evidence"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/AssessmentEvidence"},
    }
    assert paths[run_evidence_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/NmapServiceEvidencePage"}
    assert schemas["NmapServiceObservation"]["properties"]["classification"]["enum"] == [
        "informational",
    ]
    assert "finding_deltas" in schemas["AssessmentDetail"]["required"]
    assert "finding_worklist" in schemas["AssessmentDetail"]["required"]
    assert "retest_queue" in schemas["AssessmentDetail"]["required"]
    assert "target_rollups" in schemas["AssessmentDetail"]["required"]
    assert "recent_evidence" in schemas["AssessmentDetail"]["required"]
    assert schemas["AssessmentDetail"]["properties"]["recent_evidence"] == {
        "$ref": "#/components/schemas/AssessmentEvidencePage",
    }
    assert schemas["AssessmentDetail"]["properties"]["target_rollups"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/AssessmentTargetRollup"},
    }
    assert schemas["AssessmentTargetRollup"]["properties"]["total_checks"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert schemas["AssessmentDetail"]["properties"]["finding_deltas"] == {
        "$ref": "#/components/schemas/AssessmentFindingDeltaPage"
    }
    assert schemas["AssessmentDetail"]["properties"]["finding_worklist"] == {
        "$ref": "#/components/schemas/AssessmentFindingWorklistPage"
    }
    assert schemas["AssessmentDetail"]["properties"]["retest_queue"] == {
        "$ref": "#/components/schemas/AssessmentRetestQueue"
    }
    assert schemas["AssessmentRetestQueue"]["properties"]["groups"] == {
        "type": "array",
        "maxItems": 50,
        "items": {"$ref": "#/components/schemas/AssessmentRetestGroup"},
    }
    assert schemas["AssessmentRetestBatch"]["properties"]["max_findings"] == {
        "type": "integer",
        "minimum": 2,
        "maximum": 10,
    }
    assert schemas["AssessmentFindingWorklistPage"]["properties"]["items"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/AssessmentFindingWorklistItem"},
    }
    assert schemas["AssessmentFindingDelta"]["properties"]["state"]["enum"] == [
        "new",
        "persistent",
        "not_observed",
        "regressed",
        "incomparable",
    ]
    assert schemas["AssessmentFindingDeltaPage"]["properties"]["items"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/AssessmentFindingDelta"},
    }
    assert schemas["AssessmentDeletionPreview"]["properties"]["will_delete"] == {
        "$ref": "#/components/schemas/AssessmentDeletionCounts"
    }
    assert {
        "finding_check_comparisons",
        "finding_deltas",
        "dependent_comparisons_invalidated",
        "schemathesis_reports",
        "schemathesis_operations",
    }.issubset(schemas["AssessmentDeletionCounts"]["required"])
    assessment_contract = json.dumps({
        key: value
        for key, value in schemas.items()
        if key.startswith("Assessment")
    })
    for private_field in (
        "created_by_session_id",
        "updated_by_session_id",
        "state_changed_by_session_id",
        "source_path",
        "local_path",
        "secret_reference",
        "workspace_path",
        "command_variables",
    ):
        assert private_field not in assessment_contract
    for path in (
        "/projects/{project_id}/assessments",
        assessment_path,
        assessment_path + "/delete-preview",
        check_path,
        action_path,
        evidence_path,
        evidence_link_path,
    ):
        for operation in paths[path].values():
            assert {"401", "429"}.issubset(operation["responses"])


def test_api_v1_openapi_contract_describes_guarded_verification_actions():
    from services.api_v1.openapi import openapi_spec

    spec = openapi_spec()
    schemas = spec["components"]["schemas"]
    path = (
        "/projects/{project_id}/findings/{finding_id}/"
        "verification-actions/{check_id}"
    )
    operations = spec["paths"][path]

    assert set(operations) == {"get", "post"}
    assert operations["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/FindingVerificationActionPreview"}
    assert operations["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/FindingVerificationActionLaunchRequest"}
    assert operations["post"]["responses"]["202"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/FindingVerificationActionLaunchResponse"}
    assert set(operations["post"]["responses"]) == {
        "202", "400", "401", "403", "404", "409", "429", "500", "503",
    }
    request_schema = schemas["FindingVerificationActionLaunchRequest"]
    assert request_schema["required"] == ["confirmed", "plan_digest"]
    assert request_schema["additionalProperties"] is False
    assert set(request_schema["properties"]) == {
        "confirmed", "plan_digest", "workspace_cwd",
    }
    assert request_schema["properties"]["confirmed"] == {
        "type": "boolean",
        "enum": [True],
    }
    plan_schema = schemas["FindingVerificationActionPlan"]
    assert {
        "action", "target", "policy_level", "http_profile", "scope", "bounds",
        "display_command", "launchable", "requires_confirmation", "plan_digest",
    }.issubset(plan_schema["required"])
    assert plan_schema["additionalProperties"] is False


def test_api_v1_openapi_contract_describes_manual_finding_mutations():
    from services.api_v1.openapi import openapi_spec

    spec = openapi_spec()
    schemas = spec["components"]["schemas"]
    paths = spec["paths"]
    collection_path = "/projects/{project_id}/findings"
    item_path = collection_path + "/{finding_id}"

    assert paths[collection_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ManualFindingCreateRequest"}
    assert paths[item_path]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ManualFindingUpdateRequest"}
    assert paths[collection_path]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ManualFindingMutationResponse"}
    assert paths[item_path]["patch"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ManualFindingMutationResponse"}

    create_schema = schemas["ManualFindingCreateRequest"]
    update_schema = schemas["ManualFindingUpdateRequest"]
    assert create_schema["required"] == ["target_id", "title", "severity"]
    assert create_schema["additionalProperties"] is False
    assert create_schema["properties"]["evidence"]["maxItems"] == 20
    assert create_schema["properties"]["allow_duplicate"]["type"] == "boolean"
    assert update_schema["required"] == ["expected_revision"]
    assert update_schema["additionalProperties"] is False
    assert update_schema["properties"]["expected_revision"] == {
        "type": "integer",
        "minimum": 0,
    }

    public_finding = schemas["ProjectFinding"]
    assert {
        "manual_revision",
        "manual_created_by_member_id",
        "manual_updated_by_member_id",
        "manual_updated_at",
    }.issubset(public_finding["required"])
    manual_contract = json.dumps({
        name: schema
        for name, schema in schemas.items()
        if name.startswith("ManualFinding") or name == "ProjectFinding"
    })
    assert "manual_created_by_session_id" not in manual_contract
    assert "manual_updated_by_session_id" not in manual_contract


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
            if method == "POST" and path == "/projects/prj_cli/assessments":
                return {"ok": True, "assessment": {"id": "asmt_team"}}
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

    assert cli_main.main([
        "--team", "team_assessment", "assessment", "create", "prj_cli", "network",
        "--format", "json",
    ]) == 0
    json.loads(capsys.readouterr().out)

    assert seen == [
        ("team_flag", "POST", "/runs"),
        ("team_env", "GET", "/history"),
        ("team_saved", "GET", "/watchers"),
        ("team_notify", "GET", "/notification-channels"),
        ("team_assessment", "POST", "/projects/prj_cli/assessments"),
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
                io.BytesIO(
                    b'{"error":{"code":"not_found","message":"missing",'
                    b'"details":{"batch_ids":["wfx_cli"]}}}'
                ),
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
        assert exc.message == "not_found: missing"
        assert exc.status == 404
        assert exc.code == "not_found"
        assert exc.details == {"batch_ids": ["wfx_cli"]}
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


def test_darklab_cli_probe_commands_preview_and_confirm_through_api_v1(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    plan = {
        "project_id": "prj_probe",
        "action": {"id": "ping", "label": "Ping"},
        "target": {"entity_id": "ent_probe", "type": "domain", "value": "probe.example"},
        "policy_level": "safe",
        "bounds": {"summary": "Four probes against one approved host."},
        "expected_evidence": ["run"],
        "availability": {"available": True, "code": "", "reason": ""},
        "launchable": True,
        "launch_authorization": {
            "authorized": True,
            "required_capabilities": ["run_commands"],
            "missing_capabilities": [],
            "reason": "",
        },
        "display_command": "ping -c 4 probe.example",
        "plan_digest": "a" * 64,
    }
    protected_plan = {
        **plan,
        "action": {"id": "httpx", "label": "HTTPx"},
        "bounds": {
            "summary": "One protected HTTP request.",
            "credential_use": "protected_http_profile",
        },
        "http_profile": {
            "id": "hpr_cli", "name": "User session", "role": "user", "revision": 1,
            "scope": {
                "allowed_hosts": ["probe.example"],
                "scope_roots": ["https://probe.example/app"],
                "include_paths": ["/app"],
                "exclude_paths": ["/app/private"],
            },
        },
        "display_command": "httpx -u https://probe.example -sf [protected]",
        "plan_digest": "b" * 64,
    }
    unavailable_plan = {
        **plan,
        "action": {"id": "dnsrecon", "label": "DNSRecon"},
        "availability": {
            "available": False,
            "code": "feature_unavailable",
            "reason": "Required probe features aren't available.",
        },
        "feature_gates": ["dnsrecon"],
        "launchable": False,
        "display_command": "",
        "plan_digest": "c" * 64,
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if method == "GET" and path == "/projects":
                assert params == {"limit": 100, "offset": 0}
                return {
                    "projects": [{
                        "id": "prj_probe",
                        "slug": "probe-project",
                        "name": "Probe Project",
                        "status": "active",
                    }],
                    "has_more": False,
                }
            if method == "GET" and path == "/projects/prj_probe/probes":
                actions = [
                    {
                        "id": "ping", "label": "Ping", "policy_level": "safe",
                        "target_types": ["domain", "ip"],
                        "availability": {"available": True},
                    },
                    {
                        "id": "dnsrecon", "label": "DNSRecon", "policy_level": "safe",
                        "target_types": ["domain"],
                        "availability": {"available": True},
                    },
                    {
                        "id": "httpx", "label": "HTTPx", "policy_level": "safe",
                        "target_types": ["domain", "ip", "url"],
                        "availability": {"available": True},
                    },
                    {
                        "id": "sqlmap", "label": "SQLmap", "policy_level": "standard",
                        "target_types": ["url"],
                        "exclusions": ["destructive_sql"],
                        "availability": {"available": True},
                    },
                ]
                target_type = str((params or {}).get("target_type") or "")
                if target_type:
                    actions = [
                        action for action in actions
                        if target_type in action["target_types"]
                    ]
                service = str((params or {}).get("service") or "")
                return {
                    "catalog": {
                        "actions": actions,
                        "nmap_profiles": [{"key": "safe"}],
                        "nuclei_profiles": [{
                            "key": "intrusive",
                            "availability": {
                                "available": False,
                                "reason": "Intrusive probe actions aren't enabled.",
                            },
                        }],
                        "service_recommendations": ([{
                            "action_id": "nmap",
                            "nmap_profile": "smb",
                            "target_types": ["domain", "ip"],
                            "label": "Review SMB services",
                            "rationale": "Confirm the discovered SMB surface.",
                        }] if service == "microsoft-ds" else []),
                        "exclusions": ["zap", "oast_allocation"],
                    },
                }
            if method == "POST" and path.endswith("/targets/resolve"):
                assert body == {"target_value": "probe.example"}
                return {"target": plan["target"]}
            if method == "POST" and path.endswith("/plan"):
                if body and body.get("http_profile_id"):
                    assert body == {
                        "action_id": "httpx", "entity_id": "ent_probe",
                        "http_profile_id": "User session", "nuclei_profile": "safe",
                    }
                    return {"plan": protected_plan}
                if body and body.get("action_id") == "dnsrecon":
                    assert body == {
                        "action_id": "dnsrecon", "entity_id": "ent_probe",
                        "nuclei_profile": "safe",
                    }
                    return {"plan": unavailable_plan}
                assert body == {
                    "action_id": "ping", "entity_id": "ent_probe", "nuclei_profile": "safe",
                }
                return {"plan": plan}
            if method == "POST" and path.endswith("/run"):
                if body and body.get("http_profile_id"):
                    assert body == {
                        "action_id": "httpx", "entity_id": "ent_probe",
                        "http_profile_id": "User session", "nuclei_profile": "safe",
                        "confirmed": True, "plan_digest": "b" * 64,
                    }
                    return {
                        "plan": protected_plan,
                        "project_id": "prj_probe",
                        "run": {
                            "id": "run_protected_probe", "status": "queued",
                            "command": protected_plan["display_command"],
                            "history_url": "/api/v1/history/run_protected_probe",
                        },
                    }
                assert body == {
                    "action_id": "ping", "entity_id": "ent_probe", "nuclei_profile": "safe",
                    "confirmed": True, "plan_digest": "a" * 64,
                }
                return {
                    "plan": plan,
                    "project_id": "prj_probe",
                    "run": {
                        "id": "run_probe", "status": "queued",
                        "command": plan["display_command"],
                        "history_url": "/api/v1/history/run_probe",
                    },
                }
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_probe_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main(["probe", "list", "--project", "probe-project"]) == 0
    assert "Ping" in capsys.readouterr().out
    assert calls[-2][1:] == (
        "/projects", {"limit": 100, "offset": 0}, None,
    )

    assert cli_main.main([
        "probe", "list", "--project", "prj_probe", "--target-type", "ip",
    ]) == 0
    ip_output = capsys.readouterr().out
    assert "Ping" in ip_output
    assert "HTTPx" in ip_output
    assert "DNSRecon" not in ip_output
    assert "SQLmap" not in ip_output
    assert calls[-1][2] == {"service": None, "target_type": "ip"}

    assert cli_main.main([
        "probe", "list", "--project", "prj_probe", "--service", "microsoft-ds",
        "--target-type", "ip",
    ]) == 0
    service_output = capsys.readouterr().out
    assert "Service recommendations:" in service_output
    assert "nmap" in service_output
    assert "smb" in service_output
    assert "Confirm the discovered SMB surface." in service_output
    assert "Intrusive probe actions aren't enabled." in service_output
    assert "Excluded from probes: zap,oast_allocation" in service_output
    assert calls[-1][2] == {"service": "microsoft-ds", "target_type": "ip"}

    assert cli_main.main([
        "probe", "list", "--project", "prj_probe", "--target-type", "url",
        "--format", "json",
    ]) == 0
    url_payload = json.loads(capsys.readouterr().out)
    assert {action["id"] for action in url_payload["catalog"]["actions"]} == {
        "httpx", "sqlmap",
    }
    assert calls[-1][2] == {"service": None, "target_type": "url"}

    assert cli_main.main([
        "probe", "plan", "ping", "probe.example", "--project", "prj_probe",
    ]) == 0
    preview_output = capsys.readouterr().out
    assert "ping -c 4 probe.example" in preview_output
    assert f"Approval digest: {'a' * 12}" in preview_output
    assert "a" * 64 not in preview_output

    assert cli_main.main([
        "probe", "plan", "dnsrecon", "probe.example", "--project", "prj_probe",
    ]) == 0
    unavailable_output = capsys.readouterr().out
    assert "Required probe features aren't available." in unavailable_output
    assert "Missing features: dnsrecon" in unavailable_output

    assert cli_main.main([
        "probe", "run", "ping", "--entity-id", "ent_probe", "--project", "prj_probe",
    ]) == 0
    assert "Preview only" in capsys.readouterr().out

    assert cli_main.main([
        "probe", "run", "ping", "--entity-id", "ent_probe", "--project", "prj_probe",
        "--confirm",
    ]) == 0
    confirmed_output = capsys.readouterr().out
    assert confirmed_output.index("ping -c 4 probe.example") < confirmed_output.index("run_probe")
    assert "Follow this run with: darklab tail run_probe" in confirmed_output

    assert cli_main.main([
        "probe", "run", "ping", "--entity-id", "ent_probe", "--project", "prj_probe",
        "--confirm", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["run"]["id"] == "run_probe"
    assert [call[1].rsplit("/", 1)[-1] for call in calls[-2:]] == ["plan", "run"]

    assert cli_main.main([
        "probe", "plan", "httpx", "--entity-id", "ent_probe",
        "--project", "prj_probe", "--http-profile", "User session",
    ]) == 0
    protected_output = capsys.readouterr().out
    assert "[protected]" in protected_output
    assert "HTTP profile: User session (user)" in protected_output
    assert "HTTP scope: hosts probe.example; roots https://probe.example/app" in protected_output

    assert cli_main.main([
        "probe", "run", "httpx", "--entity-id", "ent_probe",
        "--project", "prj_probe", "--http-profile", "User session",
        "--confirm", "--format", "json",
    ]) == 0
    protected_launch_output = capsys.readouterr().out
    protected_payload = json.loads(protected_launch_output)
    assert protected_payload["run"]["id"] == "run_protected_probe"
    assert protected_payload["run"]["command"].endswith("-sf [protected]")
    assert [call[1].rsplit("/", 1)[-1] for call in calls[-2:]] == ["plan", "run"]
    assert "trusted_execution_args" not in protected_launch_output
    assert "private_values" not in protected_launch_output
    assert "trusted_execution_args" not in json.dumps(calls, default=str)
    assert "private_values" not in json.dumps(calls, default=str)

    plan["launch_authorization"] = {
        "authorized": False,
        "required_capabilities": ["run_commands"],
        "missing_capabilities": ["run_commands"],
        "reason": "Your Team role doesn't allow probe launches in this scope.",
    }
    denied_call_count = len(calls)
    assert cli_main.main([
        "probe", "run", "ping", "--entity-id", "ent_probe", "--project", "prj_probe",
        "--confirm",
    ]) == 1
    assert "doesn't allow probe launches" in capsys.readouterr().err
    assert [call[1].rsplit("/", 1)[-1] for call in calls[denied_call_count:]] == ["plan"]


def test_darklab_cli_probe_requires_exactly_one_target_selector(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, *_args, **_kwargs):
            raise AssertionError("invalid target selectors must fail before an API request")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_probe_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)
    assert cli_main.main([
        "probe", "plan", "ping", "probe.example", "--entity-id", "ent_probe",
        "--project", "prj_probe",
    ]) == 1
    assert "either TARGET or --entity-id" in capsys.readouterr().err


def test_darklab_cli_assessment_commands_use_stable_api_contract(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    assessment = {
        "id": "asmt_cli",
        "status": "active",
        "profile_key": "network",
        "profile_version": "1",
        "title": "External assessment",
    }
    check = {
        "id": "asmc_cli",
        "state": "not_started",
        "state_source": "derived",
        "state_reason": "",
        "policy_level": "safe",
        "category": "discovery",
        "target_type": "domain",
        "target_value": "darklab.sh",
        "check_key": "network.port_discovery",
    }
    profile_summaries = [
        {
            "key": key,
            "version": "1.0",
            "label": label,
            "purpose": f"Run the maintained {label.lower()}.",
            "target_types": target_types,
            "check_count": check_count,
        }
        for key, label, target_types, check_count in (
            ("network", "Network assessment", ["domain", "ip"], 3),
            ("web", "Web assessment", ["domain", "ip", "url"], 9),
            ("api", "API assessment", ["url"], 1),
            ("tls", "TLS assessment", ["domain", "ip"], 2),
            ("combined", "Combined assessment", ["domain", "ip", "url"], 15),
        )
    ]

    class FakeClient:
        def __init__(self, config):
            self.team = config.team

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/projects" and method == "GET":
                return {
                    "projects": [{
                        "id": "prj_cli", "slug": "assessment-project", "status": "active",
                    }],
                    "has_more": False,
                }
            if path == "/projects/prj_cli/assessments" and method == "GET":
                return {
                    "assessments": [] if (params or {}).get("status") == "completed" else [assessment],
                    "total": 0 if (params or {}).get("status") == "completed" else 1,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False,
                    "profiles": profile_summaries,
                }
            if path == "/projects/prj_cli/assessments" and method == "POST":
                if self.team == "team_viewer":
                    raise cli_main.DarklabCliError(
                        "team_forbidden: denied",
                        status=403,
                        code="team_forbidden",
                    )
                created_assessment = {
                    **assessment,
                    "id": "asmt_created",
                    "profile_key": str((body or {}).get("profile_key") or ""),
                    "title": str((body or {}).get("title") or ""),
                }
                return {"ok": True, "assessment": created_assessment}
            if method == "PATCH" and "/checks/" not in path and path.startswith(
                "/projects/prj_cli/assessments/"
            ):
                assessment_id = path.rsplit("/", 1)[-1]
                if assessment_id == "asmt_pending":
                    raise cli_main.DarklabCliError(
                        "assessment_batch_cancellation_pending: pending",
                        status=409,
                        code="assessment_batch_cancellation_pending",
                        details={"batch_id": "abx_one", "batch_ids": ["abx_one", "abx_two"]},
                    )
                return {
                    "ok": True,
                    "assessment": {
                        **assessment,
                        "id": assessment_id,
                        "status": str((body or {}).get("status") or ""),
                    },
                }
            if path.endswith("/delete-preview") and method == "GET":
                assessment_id = path.split("/")[-2]
                can_delete = assessment_id != "asmt_active"
                return {
                    "preview": {
                        "assessment": {
                            **assessment,
                            "id": assessment_id,
                            "status": "archived" if can_delete else "active",
                        },
                        "can_delete": can_delete,
                        "requires_archived": True,
                        "will_delete": {
                            "assessments": 1,
                            "checks": 3,
                            "evidence_links": 2,
                            "available_evidence_links": 2,
                            "unavailable_evidence_links": 0,
                            "evidence_links_by_type": {"run": 2},
                            "schemathesis_reports": 0,
                            "schemathesis_operations": 0,
                            "reconciliation_observations": 0,
                            "reconciliation_matches": 0,
                        },
                        "source_records_deleted": False,
                    },
                }
            if path == "/projects/prj_cli/assessments/asmt_archived" and method == "DELETE":
                return {
                    "ok": True,
                    "deleted": {
                        "assessment": {
                            **assessment,
                            "id": "asmt_archived",
                            "status": "archived",
                        },
                        "can_delete": True,
                        "requires_archived": True,
                        "will_delete": {"assessments": 1, "checks": 3},
                        "source_records_deleted": False,
                    },
                }
            if path == "/projects/prj_cli/assessments/asmt_cli" and method == "GET":
                return {
                    "assessment": assessment,
                    "rollup": {
                        "applicable_checks": 1,
                        "covered_checks": 0,
                        "checks_awaiting_review": 0,
                        "untested_checks": 1,
                    },
                    "category_rollups": [],
                    "checks": {
                        "checks": [check],
                        "total": 1,
                        "limit": 50,
                        "offset": 0,
                        "has_more": False,
                    },
                }
            if path == "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli" and method == "PATCH":
                state = str((body or {}).get("state") or "")
                reason = str((body or {}).get("reason") or "")
                return {
                    "ok": True,
                    "check": {
                        **check,
                        "state": "not_started" if state == "not_started" else state,
                        "state_source": "derived" if state == "not_started" else "manual",
                        "state_reason": reason,
                    },
                }
            if path == (
                "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/"
                "recommended-action"
            ):
                plan = {
                    "action": {"key": "command:nmap", "kind": "command", "id": "nmap"},
                    "target": {"type": "domain", "value": "darklab.sh"},
                    "policy_level": "standard",
                    "http_profile": {"name": "", "credential_use": "none"},
                    "display_command": "nmap --top-ports 100 darklab.sh",
                    "launchable": True,
                    "unavailable_reason": "",
                    "plan_digest": "a" * 64,
                }
                if method == "GET":
                    return {"plan": plan}
                if method == "POST":
                    return {
                        "plan": plan,
                        "run": {
                            "id": "run_cli_verification",
                            "status": "running",
                            "command": plan["display_command"],
                        },
                    }
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    try:
        cli_main.main(["assessment", "create", "--help"])
    except SystemExit as help_exit:
        assert help_exit.code == 0
    else:
        raise AssertionError("assessment create help did not exit")
    lifecycle_help = capsys.readouterr().out
    assert "PROFILE_KEY" in lifecycle_help
    assert "--title" in lifecycle_help
    assert "profile-version" not in lifecycle_help

    assert cli_main.main([
        "assessment", "create", "assessment-project", "combined",
        "--title", "CLI assessment",
    ]) == 0
    assert "asmt_created" in capsys.readouterr().out
    assert calls[-2:] == [
        ("GET", "/projects", {"limit": 100, "offset": 0}, None),
        (
            "POST",
            "/projects/prj_cli/assessments",
            None,
            {"profile_key": "combined", "title": "CLI assessment"},
        ),
    ]

    assert cli_main.main([
        "assessment", "create", "prj_cli", "network", "--format", "json",
    ]) == 0
    created_payload = json.loads(capsys.readouterr().out)
    assert created_payload["assessment"]["profile_key"] == "network"
    assert calls[-1] == (
        "POST", "/projects/prj_cli/assessments", None, {"profile_key": "network"},
    )

    assert cli_main.main([
        "assessment", "complete", "prj_cli", "asmt_cli", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["assessment"]["status"] == "completed"
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli",
        None,
        {"status": "completed"},
    )

    assert cli_main.main([
        "assessment", "archive", "prj_cli", "asmt_cli",
    ]) == 0
    assert "archived" in capsys.readouterr().out
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli",
        None,
        {"status": "archived"},
    )

    call_count = len(calls)
    assert cli_main.main([
        "assessment", "delete", "prj_cli", "asmt_archived",
    ]) == 0
    preview_output = capsys.readouterr().out
    assert "Assessment deletion preview" in preview_output
    assert "Source records preserved: yes" in preview_output
    assert "Preview only. Re-run with --confirm" in preview_output
    assert calls[call_count:] == [(
        "GET",
        "/projects/prj_cli/assessments/asmt_archived/delete-preview",
        None,
        None,
    )]

    call_count = len(calls)
    assert cli_main.main([
        "assessment", "delete", "prj_cli", "asmt_archived", "--confirm",
        "--format", "json",
    ]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["deleted"]["assessment"]["id"] == "asmt_archived"
    assert json.loads(captured.err)["preview"]["source_records_deleted"] is False
    assert calls[call_count:] == [
        (
            "GET",
            "/projects/prj_cli/assessments/asmt_archived/delete-preview",
            None,
            None,
        ),
        ("DELETE", "/projects/prj_cli/assessments/asmt_archived", None, None),
    ]

    call_count = len(calls)
    assert cli_main.main([
        "assessment", "delete", "prj_cli", "asmt_active", "--confirm",
    ]) == 1
    active_delete = capsys.readouterr()
    assert "archive this assessment first" in active_delete.out
    assert "must be archived" in active_delete.err
    assert calls[call_count:] == [(
        "GET",
        "/projects/prj_cli/assessments/asmt_active/delete-preview",
        None,
        None,
    )]

    assert cli_main.main([
        "assessment", "complete", "prj_cli", "asmt_pending",
    ]) == 1
    pending_error = capsys.readouterr().err
    assert "abx_one, abx_two" in pending_error
    assert "reach a terminal state" in pending_error
    assert "retry assessment complete" in pending_error

    assert cli_main.main([
        "--team", "team_viewer", "assessment", "create", "prj_cli", "network",
    ]) == 1
    permission_error = capsys.readouterr().err
    assert "MUTATE_PROJECTS capability" in permission_error

    assert cli_main.main([
        "assessment",
        "list",
        "assessment-project",
        "--status",
        "archived",
    ]) == 0
    assert "asmt_cli" in capsys.readouterr().out
    assert calls[-2:] == [
        ("GET", "/projects", {"limit": 100, "offset": 0}, None),
        (
            "GET",
            "/projects/prj_cli/assessments",
            {"limit": 50, "offset": 0, "status": "archived", "include_archived": True},
            None,
        ),
    ]

    assert cli_main.main([
        "assessment",
        "list",
        "prj_cli",
        "--format",
        "json",
    ]) == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert [profile["key"] for profile in list_payload["profiles"]] == [
        "network",
        "web",
        "api",
        "tls",
        "combined",
    ]

    assert cli_main.main([
        "assessment", "list", "prj_cli", "--status", "completed",
    ]) == 0
    assert capsys.readouterr().out == "No results.\n"

    assert cli_main.main(["assessment", "show", "prj_cli", "asmt_cli"]) == 0
    show_output = capsys.readouterr().out
    assert "External assessment" in show_output
    assert "APPLICABLE CHECKS" in show_output
    assert calls[-1] == ("GET", "/projects/prj_cli/assessments/asmt_cli", None, None)

    assert cli_main.main([
        "assessment",
        "checks",
        "prj_cli",
        "asmt_cli",
        "--state",
        "not_started",
        "--policy-level",
        "safe",
        "--evidence-state",
        "none",
        "--target-type",
        "domain",
        "--category",
        "discovery",
    ]) == 0
    checks_output = capsys.readouterr().out
    assert "asmc_cli" in checks_output
    assert "darklab.sh" in checks_output
    assert calls[-1] == (
        "GET",
        "/projects/prj_cli/assessments/asmt_cli",
        {
            "limit": 50,
            "offset": 0,
            "category": "discovery",
            "state": "not_started",
            "target_type": "domain",
            "policy_level": "safe",
            "evidence_state": "none",
        },
        None,
    )

    assert cli_main.main([
        "assessment",
        "set-state",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "blocked",
        "--reason",
        "Waiting for authorization",
    ]) == 0
    assert "Waiting for authorization" in capsys.readouterr().out
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli",
        None,
        {"state": "blocked", "reason": "Waiting for authorization"},
    )

    assert cli_main.main([
        "assessment",
        "clear-state",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "--format",
        "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["check"]["state_source"] == "derived"
    assert calls[-1] == (
        "PATCH",
        "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli",
        None,
        {"state": "not_started", "reason": ""},
    )

    assert cli_main.main([
        "assessment",
        "start-action",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
    ]) == 0
    preview_output = capsys.readouterr().out
    assert "command:nmap" in preview_output
    assert "Preview only. Re-run with --confirm" in preview_output
    assert calls[-1] == (
        "GET",
        "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/recommended-action",
        None,
        None,
    )

    assert cli_main.main([
        "assessment",
        "start-action",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "--confirm",
    ]) == 0
    confirmed_output = capsys.readouterr().out
    assert confirmed_output.index("command:nmap") < confirmed_output.index("run_cli_verification")

    call_count = len(calls)
    assert cli_main.main([
        "assessment",
        "start-action",
        "prj_cli",
        "asmt_cli",
        "asmc_cli",
        "--http-profile-id",
        "htp_cli",
        "--source-run-id",
        "run_cli_source",
        "--parameter-observation-id",
        "dpx_cli",
        "--schema-artifact-id",
        "art_cli_schema",
        "--confirm",
        "--workspace-cwd",
        "evidence",
        "--format",
        "json",
    ]) == 0
    launched = json.loads(capsys.readouterr().out)
    assert launched["run"]["id"] == "run_cli_verification"
    assert calls[call_count:] == [
        (
            "GET",
            "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/recommended-action",
            {
                "http_profile_id": "htp_cli",
                "source_run_id": "run_cli_source",
                "parameter_observation_id": "dpx_cli",
                "schema_artifact_id": "art_cli_schema",
            },
            None,
        ),
        (
            "POST",
            "/projects/prj_cli/assessments/asmt_cli/checks/asmc_cli/recommended-action",
            None,
            {
                "confirmed": True,
                "plan_digest": "a" * 64,
                "http_profile_id": "htp_cli",
                "source_run_id": "run_cli_source",
                "parameter_observation_id": "dpx_cli",
                "schema_artifact_id": "art_cli_schema",
                "workspace_cwd": "evidence",
            },
        ),
    ]


def test_darklab_cli_assessment_batch_commands_preserve_preview_and_cursor_contracts(
    monkeypatch,
    capsys,
):
    cli_main = import_module("darklab_cli.__main__")
    calls = []
    digest = "b" * 64
    preview = {
        "schema_version": 1,
        "preview_id": "abp_cli",
        "project_id": "prj_cli",
        "assessment_id": "asmt_cli",
        "source_batch_id": "",
        "profile": {"key": "network", "version": "1"},
        "selection": {"include_standard": False, "item_limit": 128},
        "summary": {
            "selected_target_count": 1,
            "estimated_min_seconds": 10,
            "estimated_max_seconds": 60,
            "potential_covered_check_count": 2,
            "requires_standard_confirmation": False,
            "reason_counts": {"not_applicable": 1},
        },
        "plan_digest": digest,
        "candidate_item_count": 1,
        "selected_item_count": 1,
        "potential_covered_check_count": 2,
        "safe_item_count": 1,
        "standard_item_count": 0,
        "concurrency": {"batch": 8, "target": 1, "owner": 16, "instance": 32},
        "expires_at": "2026-08-17 12:15:00",
        "created": "2026-08-17 12:00:00",
    }
    item = {
        "item_index": 0,
        "execution_key": "c" * 64,
        "selected": True,
        "policy_level": "safe",
        "action": {"key": "command:nmap", "id": "nmap"},
        "target": {"entity_id": "ent_cli", "type": "ip", "value": "192.0.2.10"},
        "profile_identity": {"kind": "nmap", "id": "safe"},
        "bounds": {"summary": "One approved target."},
        "display_command": "nmap -sV 192.0.2.10",
        "public_plan_digest": "d" * 64,
        "public_plan": {},
        "duration_bound_seconds": 60,
        "check_mappings": [{"check_id": "asmc_cli"}],
    }
    progress = {
        "total": 1,
        "pending": 0,
        "launching": 0,
        "running": 0,
        "succeeded": 1,
        "failed": 0,
        "unavailable": 0,
        "canceled": 0,
        "skipped": 0,
        "could_not_cancel": 0,
        "settled": 1,
        "status": "completed",
    }
    batch = {
        "schema_version": 1,
        "batch_id": "wfx_cli",
        "assessment_id": "asmt_cli",
        "project_id": "prj_cli",
        "preview_id": "abp_cli",
        "preview_digest": digest,
        "source_batch_id": "",
        "status": "completed",
        "item_count": 1,
        "chunk_count": 1,
        "concurrency": {"batch": 8, "target": 1, "owner": 16, "instance": 32},
        "progress": progress,
        "next_event_sequence": 3,
        "created": "2026-08-17 12:00:00",
        "updated": "2026-08-17 12:01:00",
        "finished": "2026-08-17 12:01:00",
        "failure_code": "",
    }
    retry_preview = {
        **preview,
        "preview_id": "abp_retry_cli",
        "source_batch_id": "wfx_cli",
        "summary": {
            **preview["summary"],
            "source_item_count": 1,
            "source_retry_eligible_item_count": 1,
            "source_succeeded_item_count": 0,
        },
    }
    retry_batch = {
        **batch,
        "batch_id": "wfx_retry_cli",
        "preview_id": "abp_retry_cli",
        "source_batch_id": "wfx_cli",
        "status": "running",
        "progress": {
            **progress,
            "pending": 1,
            "succeeded": 0,
            "settled": 0,
            "status": "running",
        },
        "finished": "",
    }
    event = {
        "batch_id": "wfx_cli",
        "sequence": 2,
        "event_type": "parent_completed",
        "chunk_index": None,
        "item_ordinal": None,
        "status": "completed",
        "reason_code": "",
        "run_id": "",
        "source_batch_id": "",
        "retry_batch_id": "",
        "details": {"succeeded": 1},
        "created": "2026-08-17 12:01:00",
    }

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, body=None, **_kwargs):
            calls.append((method, path, params, body))
            if path == "/projects":
                return {
                    "projects": [{"id": "prj_cli", "slug": "assessment-project", "status": "active"}],
                    "has_more": False,
                }
            if path.endswith("/batch-previews") and method == "POST":
                include_standard = bool((body or {}).get("include_standard"))
                if include_standard:
                    return {
                        "preview": {
                            **preview,
                            "selection": {**preview["selection"], "include_standard": True},
                            "standard_item_count": 1,
                            "summary": {
                                **preview["summary"],
                                "requires_standard_confirmation": True,
                            },
                        }
                    }
                return {"preview": preview}
            if path == "/projects/prj_cli/assessment-batches/wfx_cli/retry-previews":
                include_standard = bool((body or {}).get("include_standard"))
                if include_standard:
                    return {
                        "preview": {
                            **retry_preview,
                            "selection": {
                                **retry_preview["selection"],
                                "include_standard": True,
                            },
                            "standard_item_count": 1,
                            "summary": {
                                **retry_preview["summary"],
                                "requires_standard_confirmation": True,
                            },
                        }
                    }
                return {"preview": retry_preview}
            if path == "/assessment-batch-previews/abp_cli/items":
                return {
                    "schema_version": 1,
                    "preview_id": "abp_cli",
                    "items": [item],
                    "next_cursor": None,
                }
            if path == "/assessment-batch-previews/abp_retry_cli/items":
                return {
                    "schema_version": 1,
                    "preview_id": "abp_retry_cli",
                    "items": [item],
                    "next_cursor": None,
                }
            if path.endswith("/assessment-batches") and method == "POST":
                return {"batch": batch, "launch": {"status": "completed", "launched": 1}}
            if path == "/projects/prj_cli/assessment-batches":
                return {
                    "schema_version": 1,
                    "batches": [batch],
                    "next_cursor": "next_cli",
                    "has_more": True,
                }
            if path == "/assessment-batches/wfx_cli":
                return {"batch": batch}
            if path == "/projects/prj_cli/assessment-batches/wfx_cli/retry":
                return {
                    "batch": retry_batch,
                    "launch": {"status": "running", "launched": 1},
                }
            if path == "/assessment-batches/wfx_cli/items":
                return {
                    "schema_version": 1,
                    "batch_id": "wfx_cli",
                    "items": [{
                        "item_index": 0,
                        "status": "succeeded",
                        "attempt": 1,
                        "action_id": "nmap",
                        "target": item["target"],
                        "run_id": "run_cli",
                        "reason_code": "",
                    }],
                    "next_cursor": None,
                    "has_more": False,
                }
            if path == "/assessment-batches/wfx_cli/events":
                return {
                    "schema_version": 1,
                    "batch_id": "wfx_cli",
                    "events": [event],
                    "next_cursor": None,
                    "has_more": False,
                }
            if path == "/projects/prj_cli/assessment-batches/wfx_cli/cancel":
                return {"batch": {**batch, "status": "canceled"}, "signal_failures": 0}
            raise cli_main.DarklabCliError(f"unexpected request: {method} {path}")

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)

    assert cli_main.main([
        "assessment", "batch", "plan", "assessment-project", "asmt_cli",
        "--target", "ent_cli", "--category", "discovery",
    ]) == 0
    plan_output = capsys.readouterr().out
    assert "Assessment batch preview: abp_cli" in plan_output
    assert "nmap -sV 192.0.2.10" in plan_output
    assert calls[-2:] == [
        (
            "POST",
            "/projects/prj_cli/assessments/asmt_cli/batch-previews",
            None,
            {
                "target_entity_ids": ["ent_cli"],
                "excluded_target_entity_ids": [],
                "categories": ["discovery"],
                "excluded_categories": [],
                "include_standard": False,
                "item_limit": 128,
                "max_parallel": 8,
                "max_owner_parallel": 16,
                "max_instance_parallel": 32,
            },
        ),
        (
            "GET",
            "/assessment-batch-previews/abp_cli/items",
            {"cursor": 0, "limit": 100},
            None,
        ),
    ]

    assert cli_main.main([
        "assessment", "batch", "start", "prj_cli", "asmt_cli",
        "--include-standard", "--confirm",
    ]) == 1
    assert "add --confirm-standard" in capsys.readouterr().err
    assert not any(call[0] == "POST" and call[1].endswith("/assessment-batches") for call in calls)

    assert cli_main.main([
        "assessment", "batch", "start", "prj_cli", "asmt_cli",
        "--include-standard", "--confirm", "--confirm-standard", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["batch"]["batch_id"] == "wfx_cli"
    assert calls[-1] == (
        "POST",
        "/projects/prj_cli/assessments/asmt_cli/assessment-batches",
        None,
        {
            "preview_id": "abp_cli",
            "plan_digest": digest,
            "confirmed": True,
            "standard_confirmed": True,
        },
    )

    assert cli_main.main([
        "assessment", "batch", "list", "assessment-project", "--limit", "1",
    ]) == 0
    assert "wfx_cli" in capsys.readouterr().out
    assert calls[-1] == (
        "GET",
        "/projects/prj_cli/assessment-batches",
        {"assessment_id": None, "cursor": None, "limit": 1},
        None,
    )

    assert cli_main.main([
        "assessment", "batch", "show", "wfx_cli", "--items", "--events",
        "--item-cursor", "0", "--event-cursor", "1",
    ]) == 0
    show_output = capsys.readouterr().out
    assert "run_cli" in show_output
    assert "parent_completed" in show_output
    assert calls[-2:] == [
        ("GET", "/assessment-batches/wfx_cli/items", {"cursor": 0, "limit": 100}, None),
        ("GET", "/assessment-batches/wfx_cli/events", {"cursor": 1, "limit": 100}, None),
    ]

    assert cli_main.main(["assessment", "batch", "follow", "wfx_cli", "--cursor", "1"]) == 0
    follow_output = capsys.readouterr().out
    assert "[2]" in follow_output
    assert "Final status:" in follow_output

    assert cli_main.main(["assessment", "batch", "cancel", "wfx_cli"]) == 0
    assert "Preview only" in capsys.readouterr().out
    assert cli_main.main([
        "assessment", "batch", "cancel", "wfx_cli", "--confirm", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["batch"]["status"] == "canceled"
    assert calls[-1] == (
        "POST",
        "/projects/prj_cli/assessment-batches/wfx_cli/cancel",
        None,
        {},
    )

    retry_call_count = len(calls)
    assert cli_main.main([
        "assessment", "batch", "retry", "wfx_cli",
    ]) == 0
    retry_output = capsys.readouterr().out
    assert "Retry of: wfx_cli" in retry_output
    assert "Preview only" in retry_output
    assert calls[retry_call_count:] == [
        ("GET", "/assessment-batches/wfx_cli", None, None),
        (
            "POST",
            "/projects/prj_cli/assessment-batches/wfx_cli/retry-previews",
            None,
            {
                "target_entity_ids": [],
                "excluded_target_entity_ids": [],
                "categories": [],
                "excluded_categories": [],
                "include_standard": False,
                "item_limit": 128,
                "max_parallel": 8,
                "max_owner_parallel": 16,
                "max_instance_parallel": 32,
            },
        ),
        (
            "GET",
            "/assessment-batch-previews/abp_retry_cli/items",
            {"cursor": 0, "limit": 100},
            None,
        ),
    ]

    assert cli_main.main([
        "assessment", "batch", "retry", "wfx_cli",
        "--include-standard", "--confirm",
    ]) == 1
    assert "add --confirm-standard" in capsys.readouterr().err

    assert cli_main.main([
        "assessment", "batch", "retry", "wfx_cli",
        "--include-standard", "--confirm", "--confirm-standard", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["batch"]["batch_id"] == "wfx_retry_cli"
    assert calls[-1] == (
        "POST",
        "/projects/prj_cli/assessment-batches/wfx_cli/retry",
        None,
        {
            "preview_id": "abp_retry_cli",
            "plan_digest": digest,
            "confirmed": True,
            "standard_confirmed": True,
        },
    )


def test_darklab_cli_assessment_batch_follow_reports_resumable_interrupt(
    monkeypatch,
    capsys,
):
    cli_main = import_module("darklab_cli.__main__")
    batch_reads = import_module("darklab_cli.commands.assessment_batch_reads")

    class FakeClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, **_kwargs):
            if path.endswith("/events"):
                return {
                    "events": [{
                        "sequence": 7,
                        "event_type": "item_started",
                        "created": "2026-08-17 12:00:00",
                        "status": "running",
                    }],
                    "has_more": False,
                    "next_cursor": None,
                }
            return {"batch": {"batch_id": "wfx_running", "status": "running"}}

    monkeypatch.setenv("DARKLAB_TOKEN", "tok_cli")
    monkeypatch.setattr(cli_main, "DarklabClient", FakeClient)
    monkeypatch.setattr(batch_reads.time, "sleep", lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))

    assert cli_main.main([
        "assessment", "batch", "follow", "wfx_running", "--cursor", "5",
    ]) == 130
    captured = capsys.readouterr()
    assert "[7]" in captured.out
    assert "--cursor 7" in captured.err
    assert batch_reads._terminal_exit_code({
        "status": "completed", "progress": {"succeeded": 2},
    }) == 0
    assert batch_reads._terminal_exit_code({
        "status": "completed", "progress": {"succeeded": 1, "failed": 1},
    }) == batch_reads.BATCH_PARTIAL_EXIT_CODE
    assert batch_reads._terminal_exit_code({
        "status": "canceled", "progress": {"canceled": 1},
    }) == batch_reads.BATCH_CANCELED_EXIT_CODE
    assert batch_reads._terminal_exit_code({"status": "failed"}) == 1

    class BrokenClient:
        def __init__(self, _config):
            pass

        def request(self, method, path, *, params=None, **_kwargs):
            return {"events": "not-a-page"}

    monkeypatch.setattr(cli_main, "DarklabClient", BrokenClient)
    assert cli_main.main([
        "assessment", "batch", "follow", "wfx_broken",
    ]) == 1
    assert "invalid event page" in capsys.readouterr().err


def test_darklab_cli_entrypoint_smoke_covers_readers_streams_and_errors(monkeypatch, capsys, tmp_path):
    cli_main = import_module("darklab_cli.__main__")
    osv_requests = []
    help_text = cli_main._parser().format_help()
    assert "active            List active runs for the current token." in help_text
    assert "completion        Print or install shell completion for bash, zsh, or" in help_text
    assert "fish." in help_text
    assert "download          Download one artifact by id." in help_text
    assert "advisory          Run explicit advisory lookups; ordinary reads never" in help_text
    assert "evidence          Read and manage typed evidence without copying" in help_text
    assert "risk              Read configured CVE risk feed state without starting" in help_text
    assert "commands:" not in help_text
    assert cli_main.main(["completion", "bash"]) == 0
    bash_completion = capsys.readouterr().out
    assert "complete -F _darklab_completion darklab" in bash_completion
    assert "active advisory artifacts assessment atlas cancel completion download evidence grep history notify" in bash_completion
    assert (
        "assessment) _darklab_comp_words 'archive batch checks clear-state complete "
        "create delete list set-state show start-action'"
    ) in bash_completion
    assert "assessment:create:--format) _darklab_comp_words 'text json'; return ;;" in bash_completion
    assert "advisory) _darklab_comp_words osv" in bash_completion
    assert "advisory:osv) _darklab_comp_words '--format --help -h'" in bash_completion
    assert "advisory:osv:--format) _darklab_comp_words 'text json'; return ;;" in bash_completion
    assert "evidence) _darklab_comp_words services" in bash_completion
    assert "risk) _darklab_comp_words status" in bash_completion
    assert "assessment:batch) _darklab_comp_words 'cancel follow list plan retry show start'" in bash_completion
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
            if path == "/advisories/osv/lookup":
                assert method == "POST"
                assert params is None
                assert stream is False
                assert isinstance(body, dict)
                assert set(body) == {"purl", "version"}
                osv_requests.append(body)
                error_code = {
                    "pkg:pypi/forbidden": ("team_forbidden", 403),
                    "pkg:pypi/disabled": ("osv_lookup_disabled", 409),
                    "pkg:pypi/provider-failure": ("osv_lookup_failed", 503),
                }.get(body["purl"])
                if error_code:
                    code, status = error_code
                    raise cli_main.DarklabCliError(
                        f"{code}: rejected",
                        status=status,
                        code=code,
                    )
                return {
                    "ok": True,
                    "source": "osv",
                    "outcome": "negative_cached",
                    "record_count": 0,
                }
            if path == "/whoami":
                return {"token_created": "2026-05-19 00:00:00", "last_seen_at": "2026-05-19 00:00:01"}
            if path == "/projects":
                return {
                    "projects": [{"id": "prj_cli", "name": "CLI Project", "status": "active"}],
                    "has_more": False,
                }
            if path == "/history":
                if params and params.get("run_kind"):
                    assert params == {
                        "project_id": None,
                        "since": None,
                        "until": None,
                        "limit": 50,
                        "offset": 0,
                        "run_kind": "external",
                    }
                    return {
                        "runs": [{
                            "id": "run_external",
                            "status": "succeeded",
                            "exit_code": 0,
                            "finished": "2026-05-19T00:00:03+00:00",
                            "command": "nmap darklab.sh",
                        }],
                    }
                assert params == {
                    "project_id": None,
                    "since": None,
                    "until": None,
                    "limit": 50,
                    "offset": 0,
                }
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
            if path == "/runs/run_cli/service-evidence":
                assert params == {"limit": 25, "offset": 5}
                return {
                    "observations": [{
                        "id": "nse_cli",
                        "target": "104.161.46.133:443/tcp",
                        "service": "https",
                        "script_id": "ssl-cert",
                        "evidence_kind": "certificate",
                        "fields": [{"path": ["subject", "common_name"], "value": "darklab.sh"}],
                        "observed_at": "2026-05-19T00:00:04+00:00",
                    }],
                    "total": 1,
                    "limit": 25,
                    "offset": 5,
                    "has_more": False,
                }
            if path == "/runs/run_empty/service-evidence":
                assert params == {"limit": 50, "offset": 0}
                return {
                    "observations": [],
                    "total": 0,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False,
                }
            if path == "/risk/feeds":
                assert method == "GET"
                assert params is None
                return {
                    "feeds": [
                        {
                            "source": "epss",
                            "status": "stale",
                            "origin": "bundled",
                            "source_version": "v-old:2020-01-01",
                            "model_version": "v-old",
                            "published_at": "2020-01-01T00:00:00Z",
                            "retrieved_at": "2020-01-01T00:00:00Z",
                            "accepted_at": "2020-01-01T00:00:00Z",
                            "age_hours": 58000.0,
                            "record_count": 1,
                            "last_attempt_at": "",
                            "last_error": "",
                            "source_url": "https://epss.cyentia.com/epss_scores-current.csv.gz",
                            "attribution": "FIRST EPSS",
                            "terms_url": "https://www.first.org/epss/model",
                            "live_refresh_enabled": False,
                        },
                        {
                            "source": "kev",
                            "status": "unavailable",
                            "origin": "unavailable",
                            "source_version": "",
                            "model_version": "",
                            "published_at": "",
                            "retrieved_at": "",
                            "accepted_at": "",
                            "age_hours": None,
                            "record_count": 0,
                            "last_attempt_at": "",
                            "last_error": "",
                            "source_url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
                            "attribution": "CISA KEV",
                            "terms_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                            "live_refresh_enabled": False,
                        },
                    ],
                    "total": 2,
                }
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
    assert cli_main.main(["history", "--type", "runs_external"]) == 0
    assert "run_external" in capsys.readouterr().out
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
    assert cli_main.main([
        "evidence", "services", "run_cli", "--limit", "25", "--offset", "5",
    ]) == 0
    service_evidence = capsys.readouterr().out
    assert "104.161.46.133:443/tcp" in service_evidence
    assert "ssl-cert" in service_evidence
    assert cli_main.main([
        "evidence", "services", "run_cli", "--limit", "25", "--offset", "5",
        "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["observations"][0]["id"] == "nse_cli"
    assert cli_main.main([
        "evidence", "services", "run_cli", "--limit", "25", "--offset", "5",
        "--format", "ndjson",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "nse_cli"
    assert cli_main.main(["evidence", "services", "run_empty"]) == 0
    assert capsys.readouterr().out == "No service evidence.\n"
    assert cli_main.main(["evidence", "services", "run_cli", "--limit", "101"]) == 1
    assert "limit must be between 1 and 100" in capsys.readouterr().err
    assert cli_main.main(["risk", "status"]) == 0
    risk_status = capsys.readouterr().out
    assert "stale" in risk_status
    assert "unavailable" in risk_status
    assert cli_main.main(["risk", "status", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 2
    assert cli_main.main(["risk", "status", "--format", "ndjson"]) == 0
    assert [json.loads(line)["source"] for line in capsys.readouterr().out.splitlines()] == [
        "epss", "kev",
    ]
    assert osv_requests == []
    assert cli_main.main([
        "advisory", "osv", "pkg:pypi/requests", "2.30.0",
    ]) == 0
    advisory_output = capsys.readouterr().out
    assert "outcome: negative_cached" in advisory_output
    assert "record_count: 0" in advisory_output
    assert osv_requests[-1] == {
        "purl": "pkg:pypi/requests",
        "version": "2.30.0",
    }
    assert cli_main.main([
        "advisory", "osv", "pkg:pypi/requests", "2.30.0", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "outcome": "negative_cached",
        "record_count": 0,
        "source": "osv",
    }
    request_count = len(osv_requests)
    assert cli_main.main(["advisory", "osv", "", "2.30.0"]) == 1
    assert "PURL must not be empty" in capsys.readouterr().err
    assert cli_main.main(["advisory", "osv", "pkg:pypi/requests", ""]) == 1
    assert "VERSION must not be empty" in capsys.readouterr().err
    assert len(osv_requests) == request_count
    for purl, message in (
        ("pkg:pypi/forbidden", "requires the TRIAGE_FINDINGS capability"),
        ("pkg:pypi/disabled", "Set cve_risk.osv_advisory_mode to external"),
        ("pkg:pypi/provider-failure", "Check outbound access and provider availability"),
    ):
        assert cli_main.main(["advisory", "osv", purl, "2.30.0"]) == 1
        assert message in capsys.readouterr().err
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


def test_darklab_cli_live_server_smoke_covers_real_http_auth_and_history(monkeypatch, capsys):
    cli_main = import_module("darklab_cli.__main__")
    server = _LiveCliServer()
    server.start()
    try:
        token = _live_session_token(server.base_url)
        run_id = _seed_run(
            token,
            run_id=f"live_cli_{uuid.uuid4().hex[:12]}",
            command="echo live-cli",
            output="live cli ok",
        )

        monkeypatch.setenv("DARKLAB_API_URL", server.base_url)
        monkeypatch.setenv("DARKLAB_TOKEN", token)
        monkeypatch.delenv("DARKLAB_TEAM", raising=False)

        assert cli_main.main(["whoami", "--format", "json"]) == 0
        whoami = json.loads(capsys.readouterr().out)
        assert whoami["token_created"]
        assert whoami["last_seen_at"]

        assert cli_main.main(["history", "--type", "external", "--format", "json"]) == 0
        history = json.loads(capsys.readouterr().out)
        assert any(run["id"] == run_id and run["command"] == "echo live-cli" for run in history["runs"])

        assert cli_main.main(["output", run_id]) == 0
        assert capsys.readouterr().out == "live cli ok\n"

        assert cli_main.main(["show", f"missing_{run_id}"]) == 1
        assert "not_found: Run not found." in capsys.readouterr().err
    finally:
        server.stop()


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
