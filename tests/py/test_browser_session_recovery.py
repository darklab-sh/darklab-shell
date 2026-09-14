# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Logout recovery for stale restricted-browser cookies keeps its CSRF boundary."""

from datetime import datetime, timedelta, timezone

import pytest
from conftest import copy_pristine_sqlite_database, make_test_app
from core import database
from core.database_access import get_db_connect
from services.auth import browser_sessions, storage
from services.workspace.models import WorkspaceSettings


@pytest.fixture
def browser_identity(tmp_path, monkeypatch):
    path = copy_pristine_sqlite_database(tmp_path / "recovery.db")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    app = make_test_app()
    app.config["RATELIMIT_ENABLED"] = False
    app.config["DARKLAB_CONFIG"] = {**app.config["DARKLAB_CONFIG"], "access_profile": "token_required"}
    settings = WorkspaceSettings(True, "volume", tmp_path / "workspaces", 1024, 1024, 10, 1)
    settings.root.mkdir()
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(settings=settings, conn=conn)
        conn.commit()
    session = browser_sessions.create_browser_session(
        principal_id=bundle.principal.id, credential_id=bundle.credential.metadata.id, absolute_seconds=43200,
    )
    client = app.test_client()
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, session.cookie_value)
    client.set_cookie(browser_sessions.BROWSER_CSRF_COOKIE, session.csrf_token)
    return client, bundle, session


@pytest.mark.parametrize("state", ["revoked", "expired", "idle", "parent_revoked", "malformed", "absent"])
def test_stale_session_logout_clears_both_cookies_only_from_same_origin(browser_identity, state):
    client, bundle, session = browser_identity
    before = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with get_db_connect()() as conn:
        if state in {"revoked", "expired", "idle"}:
            if state == "expired":
                conn.execute("UPDATE browser_sessions SET created_at = ? WHERE id = ?",
                             ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), session.id))
            column = {"revoked": "revoked_at", "expired": "absolute_expires_at", "idle": "last_seen_at"}[state]
            conn.execute(f"UPDATE browser_sessions SET {column} = ? WHERE id = ?", (before, session.id))
        elif state == "parent_revoked":
            conn.execute("UPDATE credentials SET revoked_at = ? WHERE id = ?", (before, bundle.credential.metadata.id))
        conn.commit()
    if state == "malformed":
        client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, "invalid-cookie")
    if state == "absent":
        client.delete_cookie(browser_sessions.BROWSER_SESSION_COOKIE)
    assert client.get("/projects", base_url="https://localhost").status_code == 401
    for origin in (None, "https://attacker.example", "null", "https://localhost.attacker.example"):
        response = client.post("/auth/logout", base_url="https://localhost", headers={"Origin": origin} if origin else {})
        assert response.status_code == 403
        assert not response.headers.getlist("Set-Cookie")
    response = client.post("/auth/logout", base_url="https://localhost", headers={"Origin": "https://localhost"})
    assert response.status_code == 204
    assert "no-store" in response.headers["Cache-Control"]
    assert client.get_cookie(browser_sessions.BROWSER_SESSION_COOKIE) is None
    assert client.get_cookie(browser_sessions.BROWSER_CSRF_COOKIE) is None
    assert client.get("/", base_url="https://localhost").status_code == 302


def test_valid_session_logout_still_requires_session_csrf(browser_identity):
    client, _, session = browser_identity
    assert client.post("/auth/logout", headers={"Origin": "http://localhost"}).status_code == 403
    assert client.get("/projects").status_code == 200
    response = client.post("/auth/logout", headers={"X-Darklab-CSRF": session.csrf_token})
    assert response.status_code == 204
    resolved = browser_sessions.resolve_browser_session(session.cookie_value, idle_seconds=1800, touch=False)
    assert resolved.error_code == "revoked_browser_session"
