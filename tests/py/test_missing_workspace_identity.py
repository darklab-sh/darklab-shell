# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace requests reject missing identity before reaching owner storage."""

from datetime import datetime, timedelta, timezone
import json
import logging
from unittest.mock import Mock

import pytest

from admin_helpers import operator_db as _identity_db
import app as shell
from core.database_access import get_db_connect
from core.helpers import AuthenticationRejected, get_session_id
from core.logging_setup import GELFFormatter, _TextFormatter
from identity_helpers import anonymous_session_id, browser_identity_headers, principal_identity
from services.auth import browser_sessions, observability, resolver

identity_db = _identity_db
READS = ("/session/preferences", "/session/starred", "/projects/active")


@pytest.fixture
def identity_app(identity_db, monkeypatch):
    cfg = identity_db.cfg.with_overrides({"access_profile": "open", "rate_limit_enabled": False})
    monkeypatch.setattr(shell, "CFG", cfg)
    app = shell.create_app(cfg)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    return app


@pytest.mark.parametrize("profile", ["open", "token_required", "oidc_required", "mixed"])
def test_missing_owner_is_rejected_before_workspace_services(identity_app, monkeypatch, profile):
    identity_app.config["DARKLAB_CONFIG"] = identity_app.config["DARKLAB_CONFIG"].with_overrides({
        "access_profile": profile, "oidc_issuer": "https://provider.example",
        "oidc_client_id": "test", "oidc_client_secret": "test-provider-secret",
        "oidc_redirect_uri": "https://shell.example/auth/oidc/callback",
    })
    services = []
    for name in ("blueprints.session.get_preferences", "blueprints.session.list_starred_commands",
                 "blueprints.projects_core.get_active_project"):
        service = Mock(side_effect=AssertionError("missing owner reached storage"))
        monkeypatch.setattr(name, service)
        services.append(service)
    client = identity_app.test_client()
    for path in (*READS, "/projects", "/history", "/atlas", "/session/secrets"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.get_json()["error"] == "credential_required", path
    for service in services:
        service.assert_not_called()
    if profile != "open":
        for suffix in ("", "?json"):
            response = client.get(f"/history/public-run{suffix}")
            assert response.status_code == 401
            assert response.get_json()["error"] == "credential_required"


def test_missing_owner_uses_sampled_safe_authentication_warning(identity_app, monkeypatch):
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)
    logger = logging.getLogger("shell")
    monkeypatch.setattr(logger, "handlers", [handler])
    monkeypatch.setattr(logger, "level", logging.DEBUG)
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    client = identity_app.test_client()
    for path in READS * 2:
        response = client.get(path + "?private-query-canary", headers={"X-Request-ID": "missing-owner-review"})
        assert response.status_code == 401
    warnings = [record for record in records if record.levelno >= logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "CREDENTIAL_AUTHENTICATION_REJECTED"
    assert record.levelno == logging.WARNING and record.exc_info is None
    assert record.reason == "credential_required" and record.http_status == 401
    assert record.request_id == "missing-owner-review"
    assert json.loads(GELFFormatter().format(record))["level"] == 4
    rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
    assert "private-query-canary" not in rendered
    assert not any(record.msg == "UNHANDLED_EXCEPTION" for record in records)


def test_optional_owner_preserves_public_requests_and_rejected_identity(identity_app, monkeypatch):
    resolve = Mock(wraps=resolver.resolve_authentication)
    monkeypatch.setattr(resolver, "resolve_authentication", resolve)
    with identity_app.test_request_context("/health"):
        assert get_session_id(required=False) == ""
        with pytest.raises(AuthenticationRejected) as rejected:
            get_session_id()
        assert rejected.value.code == "credential_required"
        assert resolve.call_count == 1
    with identity_app.test_request_context("/health", headers={"X-Darklab-Credential": "invalid"}):
        with pytest.raises(AuthenticationRejected) as rejected:
            get_session_id(required=False)
        assert rejected.value.code == "malformed_credential"
    client = identity_app.test_client()
    for path in ("/", "/health", "/auth/sign-in", "/config", "/workflows", "/vendor/ansi_up.js"):
        assert client.get(path).status_code == 200, path
    assert client.get("/does-not-exist").status_code == 404


def test_missing_owner_denies_mutations_and_rate_limit_keys(identity_app):
    identity_app.config["RATELIMIT_ENABLED"] = True
    client = identity_app.test_client()
    for path, payload in (
        ("/session/preferences", {}), ("/session/starred", {"command": "help"}),
        ("/projects", {"name": "No owner"}), ("/share", {"content": ["private-share-canary"]}),
        ("/kill", {"run_id": "missing-run"}),
        ("/session/secrets", {"name": "TEST_KEY", "value": "private-secret-canary"}),
    ):
        response = client.post(path, json=payload)
        assert response.status_code == 401, path
        assert response.get_json()["error"] == "credential_required", path
    assert client.get("/session/teams").status_code == 401


def test_public_run_permalink_preserves_optional_identity_and_private_data(identity_app):
    client = identity_app.test_client()
    owner = anonymous_session_id("public-permalink-owner")
    headers = browser_identity_headers(owner)
    output = json.dumps([
        {"text": "Public output", "cls": ""},
        {"text": "private-intel-canary", "cls": "", "command_root": "intel"},
    ])
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs (id, personal_workspace_id, command, started, finished, exit_code, "
            "output, output_preview, output_line_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("public-run", owner, "hostname", "2026-10-04T00:00:00", "2026-10-04T00:00:01",
             0, output, output, 2),
        )
        conn.commit()
    note = client.put("/entities/run/public-run/note", headers=headers, json={"body": "private-note-canary"})
    assert note.status_code == 200
    owned = client.get("/history/public-run?json", headers=headers)
    assert owned.status_code == 200
    assert owned.get_json()["note"]["body"] == "private-note-canary"
    assert "private-intel-canary" in owned.get_data(as_text=True)

    for public_headers in ({}, browser_identity_headers(anonymous_session_id("public-permalink-peer"))):
        for suffix in ("", "?json", "?json&preview=1"):
            response = client.get(f"/history/public-run{suffix}", headers=public_headers)
            assert response.status_code == 200
            body = response.get_data(as_text=True)
            assert "Public output" in body
            assert "private-note-canary" not in body
            assert "private-intel-canary" not in body
            if "json" in suffix:
                assert response.get_json()["note"] is None
        for suffix in ("", "?json"):
            assert client.get(f"/history/missing-run{suffix}", headers=public_headers).status_code == 404
    rejected = client.get("/history/public-run?json", headers={"X-Darklab-Credential": "invalid"})
    assert rejected.status_code == 401
    assert rejected.get_json()["error"] == "malformed_credential"


@pytest.mark.parametrize("state,code", [
    ("malformed", "malformed_browser_session"), ("idle", "idle_browser_session"),
    ("expired", "expired_browser_session"), ("revoked", "revoked_browser_session"),
    ("disabled", "revoked_browser_session"),
])
def test_rejected_cookie_keeps_its_specific_authentication_error(identity_app, state, code):
    identity = principal_identity("missing owner rejection")
    credential_id = resolver.public_lookup_id_from_headers(identity.browser_headers())
    issued = browser_sessions.create_browser_session(
        principal_id=identity.principal_id, credential_id=credential_id, absolute_seconds=3600,
    )
    before = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with get_db_connect()() as conn:
        if state in {"idle", "expired", "revoked"}:
            if state == "expired":
                conn.execute("UPDATE browser_sessions SET created_at = ? WHERE id = ?",
                             ((datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), issued.id))
            column = {"idle": "last_seen_at", "expired": "absolute_expires_at", "revoked": "revoked_at"}[state]
            conn.execute(f"UPDATE browser_sessions SET {column} = ? WHERE id = ?", (before, issued.id))
        elif state == "disabled":
            conn.execute("UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?",
                         (before, identity.principal_id))
        conn.commit()
    client = identity_app.test_client()
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, "invalid" if state == "malformed" else issued.cookie_value)
    for path in (*READS, "/history/public-run", "/history/public-run?json"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.get_json()["error"] == code


@pytest.mark.parametrize("kind", ["anonymous", "principal"])
def test_valid_owner_recovers_saved_state_without_crossing_workspaces(identity_app, kind):
    client = identity_app.test_client()
    headers = (browser_identity_headers(anonymous_session_id("missing-owner-state")) if kind == "anonymous"
               else principal_identity("missing owner state").browser_headers())
    assert client.post("/session/preferences", headers=headers,
                       json={"preferences": {"pref_prompt_username": "saved-owner"}}).status_code == 200
    assert client.post("/session/starred", headers=headers, json={"command": "help"}).status_code == 200
    created = client.post("/projects", headers=headers, json={"name": "Saved owner project"})
    assert created.status_code == 201
    project_id = created.get_json()["project"]["id"]
    assert client.post("/projects/active", headers=headers, json={"project_id": project_id}).status_code == 200
    before = {path: client.get(path, headers=headers).get_json() for path in READS}
    for path in READS:
        assert client.get(path).status_code == 401
        restored = client.get(path, headers=headers)
        assert restored.status_code == 200
        assert restored.get_json() == before[path]
    peer = browser_identity_headers(anonymous_session_id("missing-owner-peer"))
    assert client.get(READS[0], headers=peer).get_json()["preferences"] == {}
    assert client.get(READS[1], headers=peer).get_json()["commands"] == []
    assert client.get(READS[2], headers=peer).get_json()["project"] is None
    assert client.get(f"/projects/{project_id}", headers=peer).status_code == 404
