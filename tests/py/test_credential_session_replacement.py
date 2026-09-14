# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Credential sign-in replaces only the browser session it authenticates."""

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from identity_helpers import principal_identity
from services.auth.browser_sessions import BROWSER_CSRF_COOKIE, BROWSER_SESSION_COOKIE


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
