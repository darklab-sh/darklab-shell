# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
from datetime import datetime, timedelta, timezone

import pytest

from admin_helpers import operator_db as _operator_db
from config_builder import build_config
from config_inspection import DERIVED_SUMMARIES, diagnostic_values
from core.database_access import get_db_connect
from services.auth import browser_sessions, operator_grants
from services.auth.contracts import timestamp
from test_operator_reauthentication import ORIGIN, credential_setup

operator_db = _operator_db


def install_snapshot(monkeypatch, *, pid=123, name="Worker one"):
    from services import operator_console

    built = build_config(
        [
            (
                "local YAML",
                {
                    "app_name": name,
                    "ai_base_url": "https://PRIVATE_AI_ENDPOINT.test",
                    "share_redaction_rules": [{"pattern": "PRIVATE_RULE", "replacement": "PRIVATE_REPLACE"}],
                },
            )
        ]
    )
    snapshot = {
        "values": built.config.model_dump(),
        "provenance": built.provenance,
        "warnings": built.warnings,
        "process_id": pid,
        "load_pid": pid,
        "loaded_at": "2026-09-19T00:00:00+00:00",
        "app_version": "test",
    }
    snapshot["values"]["oidc_allowed_subjects"] = ["PRIVATE_SUBJECT"]
    snapshot["values"]["ai_api_key"] = "PRIVATE_SECRET"
    monkeypatch.setattr(operator_console, "get_loaded_config_snapshot", lambda: snapshot)
    return snapshot


def test_settings_only_disclose_reviewed_values_and_audit_the_actor(operator_db, monkeypatch):
    app, client, bundle, original = credential_setup(operator_db, monkeypatch)
    install_snapshot(monkeypatch)
    page = client.get("/admin/", base_url=ORIGIN)
    assert page.status_code == 200 and b"Serving web worker" in page.data
    response = client.get("/admin/settings?path=/etc/passwd&search=PRIVATE_SEARCH", base_url=ORIGIN)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["schema_version"] == 1
    assert payload["observation"]["process_id"] == 123
    assert "serving web worker" in payload["observation"]["kind"]
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    for marker in (
        "PRIVATE_RULE",
        "PRIVATE_REPLACE",
        "PRIVATE_SUBJECT",
        "PRIVATE_AI_ENDPOINT",
        "PRIVATE_SECRET",
        "PRIVATE_SEARCH",
    ):
        assert marker not in response.get_data(as_text=True) + page.get_data(as_text=True)
    rows = {row["key"]: row for row in payload["settings"]}
    assert rows["share_redaction_rules"]["effective"]["value"] == 1
    assert rows["oidc_allowed_subjects"]["effective"]["value"] == 1
    assert rows["ai_base_url"]["effective"]["value"] is True
    assert rows["ai_api_key"]["effective"]["mode"] == "withheld"
    assert all(row["value"] is None for row in payload["host_settings"])
    with get_db_connect()() as conn:
        event = conn.execute(
            "SELECT actor_principal_id, details FROM audit_events WHERE event_type = ?", ("instance_operator.view",)
        ).fetchone()
    assert event["actor_principal_id"] == bundle.principal.id and "PRIVATE_" not in json.dumps(event["details"])
    route_methods = {rule.rule: rule.methods for rule in app.url_map.iter_rules() if rule.endpoint.startswith("admin.")}
    assert route_methods["/admin/"] == route_methods["/admin/settings"] == {"GET", "HEAD", "OPTIONS"}
    assert route_methods["/admin/reauth"] == {"GET", "HEAD", "OPTIONS", "POST"}
    for path in ("/admin/", "/admin/settings"):
        assert client.post(path, base_url=ORIGIN, headers={"X-Darklab-CSRF": original.csrf_token}).status_code == 405


@pytest.mark.parametrize(
    "cause",
    [
        "missing_grant",
        "revoked_grant",
        "revoked_session",
        "disabled",
        "anonymous",
        "direct_credential",
        "pat",
        "team_owner",
        "stale",
        "idle",
    ],
)
def test_console_authorization_and_navigation(operator_db, monkeypatch, cause):
    app, client, bundle, issued = credential_setup(operator_db, monkeypatch)
    install_snapshot(monkeypatch)
    assert b'data-action="admin"' in client.get("/", base_url=ORIGIN).data
    headers = {}
    if cause in {"missing_grant", "team_owner"}:
        with get_db_connect()() as conn:
            conn.execute("DELETE FROM instance_operator_grants WHERE principal_id = ?", (bundle.principal.id,))
            if cause == "team_owner":
                from services.teams.storage import create_team

                create_team(conn, name="Operator team", creator_principal_id=bundle.principal.id)
            conn.commit()
    elif cause == "revoked_session":
        browser_sessions.revoke_browser_session(issued.id, reason="test")
    elif cause == "revoked_grant":
        operator_grants.set_grant(bundle.principal.id, granted=False)
    elif cause in {"anonymous", "direct_credential", "pat"}:
        client.delete_cookie(browser_sessions.BROWSER_SESSION_COOKIE, domain="shell.example")
        if cause == "direct_credential":
            headers["X-Darklab-Credential"] = bundle.credential.secret
        elif cause == "pat":
            from services.auth.storage import issue_credential

            with get_db_connect()() as conn:
                token = issue_credential(
                    conn=conn,
                    principal_id=bundle.principal.id,
                    credential_type="pat",
                    scopes=["identity:read"],
                    expires_in_days=1,
                )
                conn.commit()
            headers["Authorization"] = "Bearer " + token.secret
    else:
        with get_db_connect()() as conn:
            old = timestamp(datetime.now(timezone.utc) - timedelta(hours=2))
            if cause == "disabled":
                conn.execute(
                    "UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?", (old, bundle.principal.id)
                )
            elif cause == "stale":
                conn.execute("UPDATE browser_sessions SET authenticated_at = ? WHERE id = ?", (old, issued.id))
            else:
                conn.execute("UPDATE browser_sessions SET last_seen_at = ? WHERE id = ?", (old, issued.id))
            conn.commit()
    response = client.get("/admin/settings", headers=headers, base_url=ORIGIN)
    assert response.status_code == (
        404 if cause in {"missing_grant", "revoked_grant", "revoked_session", "team_owner", "disabled"} else 401
    )
    assert "settings" not in (response.get_json(silent=True) or {})
    assert response.headers["Cache-Control"] == "private, no-store"
    if cause == "stale":
        assert response.get_json()["error"] == "reauthentication_required"
        assert b'data-action="admin"' in client.get("/", base_url=ORIGIN).data
    else:
        assert b'data-action="admin"' not in client.get("/", headers=headers, base_url=ORIGIN).data
    if response.status_code == 401 and cause != "stale":
        assert response.get_json()["error"] == "sign_in_required"
        assert response.get_json()["destination"].startswith("/auth/sign-in?next=")


def test_each_response_identifies_its_own_snapshot(operator_db, monkeypatch):
    _app, client, _bundle, _issued = credential_setup(operator_db, monkeypatch)
    first = install_snapshot(monkeypatch, pid=101, name="First worker")
    monkeypatch.setenv("APP_NAME", "Later host edit")
    response = client.get("/admin/settings", base_url=ORIGIN).get_json()
    assert next(row for row in response["settings"] if row["key"] == "app_name")["effective"]["value"] == "First worker"
    assert first["values"]["app_name"] == "First worker"
    install_snapshot(monkeypatch, pid=202, name="Second worker")
    response = client.get("/admin/settings", base_url=ORIGIN).get_json()
    assert response["observation"]["process_id"] == 202
    assert next(row for row in response["settings"] if row["key"] == "app_name")["effective"]["value"] == "Second worker"
    assert "applied" not in response["observation"]


def test_diagnostics_keeps_existing_config_disclosure():
    from blueprints.assets import _DIAG_CONFIG_GROUPS

    cfg = build_config(
        [
            (
                "local YAML",
                {
                    "trusted_proxy_cidrs": ["10.1.0.0/16"],
                    "max_tabs": 13,
                    "ai_base_url": "https://PRIVATE_ENDPOINT.test",
                    "ai_model": "model-test",
                    "share_redaction_rules": [{"pattern": "PRIVATE_PATTERN", "replacement": "PRIVATE_REPLACE"}],
                },
            )
        ]
    ).config
    before = {}
    for _group, keys in _DIAG_CONFIG_GROUPS:
        for key in keys:
            source, kind = DERIVED_SUMMARIES.get(key, (key, ""))
            before[key] = len(cfg[source]) if kind == "count" else bool(cfg[source]) if kind == "presence" else cfg[key]
    after, truncated = diagnostic_values(before, cfg)
    assert after == before and truncated == []
    assert "PRIVATE_" not in json.dumps(after)


@pytest.mark.parametrize(
    "peer,forwarded,allowed",
    [
        ("10.0.0.8", "192.0.2.9", True),
        ("10.0.0.8", "203.0.113.9", False),
        ("203.0.113.9", "192.0.2.9", False),
    ],
)
def test_operator_network_uses_only_trusted_forwarding(operator_db, monkeypatch, peer, forwarded, allowed):
    from test_operator_reauthentication import app_for

    _app, _client, _bundle, issued = credential_setup(operator_db, monkeypatch)
    cfg = operator_db.cfg.with_overrides(
        {
            "access_profile": "token_required",
            "diagnostics_allowed_cidrs": ["192.0.2.0/24"],
            "trusted_proxy_cidrs": ["10.0.0.0/24"],
        }
    )
    app = app_for(monkeypatch, cfg)
    client = app.test_client()
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, issued.cookie_value, domain="shell.example")
    install_snapshot(monkeypatch)
    for path in ("/admin/", "/admin/settings", "/admin/reauth"):
        response = client.get(
            path, base_url=ORIGIN, headers={"X-Forwarded-For": forwarded}, environ_overrides={"REMOTE_ADDR": peer}
        )
        assert response.status_code == (200 if allowed else 404)
        assert response.headers["Cache-Control"] == "private, no-store"
