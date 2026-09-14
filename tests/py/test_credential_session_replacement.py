# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Credential sign-in replaces only the browser session it authenticates."""

from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from identity_helpers import principal_identity
from services.auth import browser_sessions
from services.auth.browser_sessions import BROWSER_CSRF_COOKIE, BROWSER_SESSION_COOKIE
from services.auth.contracts import timestamp


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "sessions.db")))
    application = make_test_app()
    application.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    application.config["RATELIMIT_ENABLED"] = False
    return application


def _sign_in(client, kind, secret, *, valid_proof=True):
    if kind == "form":
        client.get("/auth/sign-in", base_url="https://localhost")
        nonce = client.get_cookie("darklab_sign_in_nonce", path="/auth/sign-in")
        assert nonce is not None
        return client.post(
            "/auth/sign-in", base_url="https://localhost",
            data={"credential": secret, "sign_in_nonce": nonce.value if valid_proof else "wrong"},
        )
    csrf = client.get_cookie(BROWSER_CSRF_COOKIE)
    return client.post(
        "/auth/credentials/redeem", base_url="https://localhost", json={"secret": secret},
        headers={"X-Darklab-CSRF": csrf.value if csrf is not None and valid_proof else "wrong"},
    )


@pytest.mark.parametrize("remaining_seconds", [30, 3600])
def test_team_cookie_rotations_preserve_absolute_deadline(app, monkeypatch, remaining_seconds):
    identity = principal_identity("Team session owner")
    client = app.test_client()
    assert _sign_in(client, "form", identity.portable_secret).status_code == 302
    original_cookie = _cookie(client)
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(seconds=remaining_seconds)
    authenticated_at = timestamp(now - timedelta(hours=11))
    with database.db_connect() as conn:
        conn.execute(
            "UPDATE browser_sessions SET authenticated_at = ?, absolute_expires_at = ? WHERE principal_id = ?",
            (authenticated_at, timestamp(deadline), identity.principal_id),
        )
        conn.commit()
    cookies = [original_cookie]
    for number in range(2):
        csrf = client.get_cookie(BROWSER_CSRF_COOKIE).value
        response = client.post(
            "/session/teams", base_url="https://localhost",
            headers={"X-Darklab-CSRF": csrf}, json={"name": f"Deadline Team {number}"},
        )
        assert response.status_code == 201
        cookies.append(_cookie(client))
        assert cookies[-1] != cookies[-2]
        for header in response.headers.getlist("Set-Cookie"):
            parsed = SimpleCookie(header)
            for name in (BROWSER_SESSION_COOKIE, BROWSER_CSRF_COOKIE):
                if name in parsed:
                    assert 0 < int(parsed[name]["max-age"]) <= remaining_seconds
        with database.db_connect() as conn:
            row = conn.execute(
                "SELECT authenticated_at, absolute_expires_at FROM browser_sessions "
                "WHERE principal_id = ? AND revoked_at IS NULL", (identity.principal_id,),
            ).fetchone()
        assert row["authenticated_at"] == authenticated_at
        assert row["absolute_expires_at"] == timestamp(deadline)
    # Freeze only session time: requests still use the real resolver and route gate.
    monkeypatch.setattr(browser_sessions, "_active_now", lambda _now: deadline)
    for cookie in cookies:
        replay = app.test_client()
        replay.set_cookie(BROWSER_SESSION_COOKIE, cookie)
        assert replay.get("/auth/principal", base_url="https://localhost").status_code == 401


@pytest.mark.parametrize("kind", ["form", "redeem"])
def test_fresh_credential_sign_in_renews_absolute_deadline(app, kind):
    identity = principal_identity("Fresh session owner")
    client = app.test_client()
    assert _sign_in(client, "form", identity.portable_secret).status_code == 302
    old_deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    with database.db_connect() as conn:
        conn.execute(
            "UPDATE browser_sessions SET authenticated_at = ?, absolute_expires_at = ? WHERE principal_id = ?",
            (timestamp(old_deadline - timedelta(hours=11)), timestamp(old_deadline), identity.principal_id),
        )
        conn.commit()
    started = datetime.now(timezone.utc)
    assert _sign_in(client, kind, identity.portable_secret).status_code == (302 if kind == "form" else 200)
    with database.db_connect() as conn:
        row = conn.execute(
            "SELECT authenticated_at, absolute_expires_at FROM browser_sessions "
            "WHERE principal_id = ? AND revoked_at IS NULL", (identity.principal_id,),
        ).fetchone()
    assert datetime.fromisoformat(row["authenticated_at"]) >= started
    assert datetime.fromisoformat(row["absolute_expires_at"]) >= started + timedelta(hours=12)


def _cookie(client):
    cookie = client.get_cookie(BROWSER_SESSION_COOKIE)
    assert cookie is not None
    return cookie.value


def _assert_principal(client, identity):
    response = client.get("/auth/principal", base_url="https://localhost")
    assert response.status_code == 200
    assert response.json["authentication"]["principal_id"] == identity.principal_id


@pytest.mark.parametrize("kind", ["form", "redeem"])
@pytest.mark.parametrize("switch_account", [False, True])
def test_successful_sign_in_retires_previous_cookie_without_revoking_other_sessions(app, kind, switch_account):
    first = principal_identity("first account")
    second = principal_identity("second account") if switch_account else first
    client = app.test_client()
    other_device = app.test_client()
    assert _sign_in(client, kind, first.portable_secret).status_code == (302 if kind == "form" else 200)
    assert _sign_in(other_device, kind, first.portable_secret).status_code == (302 if kind == "form" else 200)
    previous_cookie = _cookie(client)
    replay = app.test_client()
    replay.set_cookie(BROWSER_SESSION_COOKIE, previous_cookie, secure=True)
    _assert_principal(replay, first)

    response = _sign_in(client, kind, second.portable_secret)
    assert response.status_code == (302 if kind == "form" else 200)
    assert _cookie(client) != previous_cookie
    _assert_principal(client, second)
    rejected = replay.get("/auth/principal", base_url="https://localhost")
    assert rejected.status_code == 401
    assert rejected.json["error"] == "revoked_browser_session"
    _assert_principal(other_device, first)


@pytest.mark.parametrize("kind", ["form", "redeem"])
@pytest.mark.parametrize("failure", ["credential", "proof", "session_creation"])
def test_failed_sign_in_keeps_previous_browser_session(app, monkeypatch, kind, failure):
    from blueprints import auth
    from services.auth.browser_sessions import BrowserSessionError

    first = principal_identity("current account")
    second = principal_identity("new account")
    client = app.test_client()
    assert _sign_in(client, kind, first.portable_secret).status_code == (302 if kind == "form" else 200)
    previous_cookie = _cookie(client)
    if failure == "session_creation":
        def fail_creation(**_kwargs):
            raise BrowserSessionError("test session creation failure")

        monkeypatch.setattr(auth, "create_browser_session", fail_creation)
        with pytest.raises(BrowserSessionError, match="test session creation failure"):
            _sign_in(client, kind, second.portable_secret)
    else:
        secret = "invalid" if failure == "credential" else second.portable_secret
        response = _sign_in(client, kind, secret, valid_proof=failure != "proof")
        assert response.status_code == (200 if kind == "form" else 401 if failure == "credential" else 403)
    assert _cookie(client) == previous_cookie
    _assert_principal(client, first)
