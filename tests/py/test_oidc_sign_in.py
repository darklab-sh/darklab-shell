# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Deterministic local OIDC provider; no external IdP or network dependency."""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import build_test_config
from core.database_access import get_db_connect
from flask.testing import FlaskClient
from joserfc import jwk, jwt
from services.auth import lifecycle, oidc, oidc_cache, storage
from services.auth.browser_sessions import (
    BROWSER_CSRF_COOKIE,
    BROWSER_SESSION_COOKIE,
    resolve_browser_session,
)
from services.auth.contracts import timestamp

ISSUER = "https://idp.example/realms/test"
ORIGIN = "https://shell.example"
CALLBACK = f"{ORIGIN}/auth/oidc/callback"


class _Response:
    status_code = 200

    def __init__(self, data):
        self.data = data
        self.content = b"{}"

    def json(self):
        return self.data


class LocalProvider:
    def __init__(self, monkeypatch):
        oidc_cache.reset_provider_cache()
        self.private_key = jwk.RSAKey.generate_key(2048, private=True, auto_kid=True)
        self.subject = "local-subject-1"
        self.signing_key = self.private_key
        self.nonce = ""
        self.verifier = ""
        self.claim_overrides = {}
        self.claim_omissions = set()
        self.available = True
        self.get_calls = []
        metadata = {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
            "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
            "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
            "code_challenge_methods_supported": ["S256"],
        }

        def get(url, **kwargs):
            self.get_calls.append(url)
            assert kwargs["allow_redirects"] is False
            assert kwargs["verify"] is True
            if not self.available:
                raise oidc.requests.ConnectionError("offline")
            if url.endswith("/.well-known/openid-configuration"):
                return _Response(metadata)
            if url == metadata["jwks_uri"]:
                return _Response({"keys": [self.private_key.as_dict(private=False)]})
            raise AssertionError(url)

        def fetch_token(_client, url, **kwargs):
            if not self.available:
                raise oidc.requests.ConnectionError("offline")
            assert url == metadata["token_endpoint"]
            assert kwargs["code"] == "local-code"
            assert kwargs["code_verifier"] == self.verifier
            assert kwargs["redirect_uri"] == CALLBACK
            assert kwargs["allow_redirects"] is False
            now = int(time.time())
            claims = {
                "iss": ISSUER,
                "sub": self.subject,
                "aud": "darklab-test",
                "exp": now + 300,
                "iat": now,
                "auth_time": now,
                "nonce": self.nonce,
                **self.claim_overrides,
            }
            for claim in self.claim_omissions:
                claims.pop(claim, None)
            return {"id_token": jwt.encode({"alg": "RS256", "kid": self.signing_key.kid}, claims, self.signing_key)}

        monkeypatch.setattr(oidc.requests, "get", get)
        monkeypatch.setattr(oidc.OAuth2Session, "fetch_token", fetch_token)

    def expect(self, state):
        with get_db_connect()() as conn:
            row = conn.execute(
                "SELECT nonce, code_verifier FROM oidc_auth_flows WHERE state_digest = ?",
                (hashlib.sha256(state.encode()).digest(),),
            ).fetchone()
            assert row is not None
            self.nonce = str(row["nonce"])
            self.verifier = str(row["code_verifier"])


def _config(profile="oidc_required", provisioning="automatic", subjects=None):
    return build_test_config({
        "access_profile": profile,
        "oidc_issuer": ISSUER,
        "oidc_client_id": "darklab-test",
        "oidc_client_secret": "test-secret",
        "oidc_redirect_uri": CALLBACK,
        "oidc_scopes": ["openid"],
        "oidc_provisioning": provisioning,
        "oidc_allowed_subjects": subjects or [],
        "asset_bundle_mode": "source",
    })


def _app(monkeypatch, config):
    import config as shell_config
    from core import database as shell_database

    import app as application_module

    monkeypatch.setattr(shell_config, "CFG", config)
    monkeypatch.setattr(application_module, "CFG", config)
    shell_database.db_init()
    app = application_module.create_app(config)
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    return app


def _start(client, provider):
    response = client.get("/auth/oidc/start", base_url=ORIGIN)
    assert response.status_code == 302
    destination = urlsplit(response.headers["Location"])
    query = parse_qs(destination.query)
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [CALLBACK]
    assert query["nonce"]
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    provider.expect(state)
    expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(provider.verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected_challenge]
    return state


def _callback(client, state, *, code="local-code"):
    return client.get(
        f"/auth/oidc/callback?state={state}&code={code}", base_url=ORIGIN,
    )


def _response_cookie(response, name):
    for value in response.headers.getlist("Set-Cookie"):
        parsed = SimpleCookie()
        parsed.load(value)
        if name in parsed:
            return parsed[name].value
    raise AssertionError(f"missing {name} cookie")


def _client_cookie(client: FlaskClient, name: str) -> str:
    cookie = client.get_cookie(name, domain="shell.example")
    assert cookie is not None, f"missing {name} cookie"
    return cookie.value


def test_oidc_profile_config_requires_valid_provider_and_policy():
    assert _config()["access_profile"] == "oidc_required"
    assert _config("mixed")["access_profile"] == "mixed"
    assert _config(provisioning="allowlist", subjects=["local-subject-1"])["oidc_allowed_subjects"] == ["local-subject-1"]
    with pytest.raises(RuntimeError, match="oidc_allowed_subjects"):
        _config(provisioning="allowlist")
    with pytest.raises(RuntimeError, match="HTTPS"):
        build_test_config({
            "access_profile": "oidc_required", "oidc_issuer": "http://idp.example",
            "oidc_client_id": "x", "oidc_client_secret": "y", "oidc_redirect_uri": CALLBACK,
        })
    with pytest.raises(RuntimeError, match="provisioning requires"):
        _config(profile="token_required", provisioning="automatic")


def test_oidc_sign_in_provisions_provider_only_principal_and_replays_fail(monkeypatch):
    config = _config()
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, config).test_client()
    assert client.get("/", base_url=ORIGIN).status_code == 302
    page = client.get("/auth/sign-in", base_url=ORIGIN)
    assert b"Continue with identity provider" in page.data
    assert b"restricted-credential" not in page.data
    state = _start(client, provider)
    signed_in = _callback(client, state)
    assert signed_in.status_code == 302
    assert signed_in.headers["Location"] == "/"
    assert BROWSER_SESSION_COOKIE in signed_in.headers.getlist("Set-Cookie")[0]
    principal = client.get("/auth/principal", base_url=ORIGIN).get_json()
    assert principal["authentication"]["credential_type"] == "oidc"
    assert principal["authentication"]["credential_id"] == ""
    with get_db_connect()() as conn:
        row = conn.execute("SELECT * FROM oidc_identities WHERE principal_id = ?", (principal["principal"]["id"],)).fetchone()
        assert row["issuer"] == ISSUER
        assert row["subject"] == provider.subject
        assert conn.execute("SELECT COUNT(*) FROM credentials WHERE principal_id = ?", (row["principal_id"],)).fetchone()[0] == 0
    assert client.get("/", base_url=ORIGIN).status_code == 200
    replay = _callback(client, state)
    assert replay.status_code == 302
    assert "oidc_error" in replay.headers["Location"]
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    assert client.post("/auth/logout", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf}).status_code == 204
    assert client.get("/", base_url=ORIGIN).status_code == 302


def test_oidc_sign_in_rotates_an_existing_browser_session(monkeypatch):
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    first_state = _start(client, provider)
    assert _callback(client, first_state).status_code == 302
    with get_db_connect()() as conn:
        first_session_id = conn.execute(
            "SELECT id FROM browser_sessions WHERE revoked_at IS NULL"
        ).fetchone()[0]
    second_state = _start(client, provider)
    assert _callback(client, second_state).status_code == 302
    with get_db_connect()() as conn:
        old_session = conn.execute(
            "SELECT revoked_at FROM browser_sessions WHERE id = ?", (first_session_id,)
        ).fetchone()
        assert old_session[0] is not None
        assert conn.execute(
            "SELECT COUNT(*) FROM browser_sessions WHERE revoked_at IS NULL"
        ).fetchone()[0] == 1


def test_oidc_revoke_all_requires_recent_sign_in(monkeypatch):
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    assert _callback(client, _start(client, provider)).status_code == 302
    stale = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    with get_db_connect()() as conn:
        conn.execute("UPDATE browser_sessions SET authenticated_at = ?", (stale,))
        conn.commit()
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    refused = client.post(
        "/auth/sessions/revoke-all", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf},
    )
    assert refused.status_code == 403
    assert refused.get_json()["error"] == "recent_authentication_required"
    assert client.get("/", base_url=ORIGIN).status_code == 200

    assert _callback(client, _start(client, provider)).status_code == 302
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    revoked = client.post(
        "/auth/sessions/revoke-all", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf},
    )
    assert revoked.status_code == 200
    assert revoked.get_json()["revoked_sessions"] >= 1
    assert client.get("/", base_url=ORIGIN).status_code == 302


@pytest.mark.parametrize("claim", [
    {"iss": "https://wrong.example"},
    {"aud": "wrong-client"},
    {"exp": 0},
    {"nonce": "wrong-nonce"},
])
def test_oidc_rejects_invalid_id_token_claims(monkeypatch, claim):
    provider = LocalProvider(monkeypatch)
    provider.claim_overrides = claim
    client = _app(monkeypatch, _config()).test_client()
    state = _start(client, provider)
    response = _callback(client, state)
    assert "oidc_error" in response.headers["Location"]
    assert client.get("/", base_url=ORIGIN).status_code == 302


def test_oidc_rejects_wrong_signature_and_callback_origin(monkeypatch):
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    state = _start(client, provider)
    wrong_origin = client.get(
        f"/auth/oidc/callback?state={state}&code=local-code", base_url="https://other.example",
    )
    assert "oidc_error" in wrong_origin.headers["Location"]
    provider.signing_key = jwk.RSAKey.generate_key(2048, private=True)
    state = _start(client, provider)
    assert "oidc_error" in _callback(client, state).headers["Location"]
    assert client.get("/", base_url=ORIGIN).status_code == 302


def test_oidc_disabled_provisioning_and_provider_outage_fail_closed(monkeypatch):
    provider = LocalProvider(monkeypatch)
    provider.subject = "disabled-new-subject"
    client = _app(monkeypatch, _config(provisioning="disabled")).test_client()
    state = _start(client, provider)
    assert "oidc_error" in _callback(client, state).headers["Location"]
    provider.available = False
    oidc_cache.reset_provider_cache()
    assert "oidc_error" in client.get("/auth/oidc/start", base_url=ORIGIN).headers["Location"]
    assert client.get("/", base_url=ORIGIN).status_code == 302


def test_existing_oidc_session_survives_temporary_provider_outage(monkeypatch):
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    state = _start(client, provider)
    assert _callback(client, state).status_code == 302
    provider.available = False
    assert client.get("/", base_url=ORIGIN).status_code == 200
    oidc_cache.reset_provider_cache()
    assert "oidc_error" in client.get("/auth/oidc/start", base_url=ORIGIN).headers["Location"]
    assert client.get("/", base_url=ORIGIN).status_code == 200


def test_operator_recovery_of_provider_only_workspace_revokes_provider_sessions(monkeypatch):
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    state = _start(client, provider)
    assert _callback(client, state).status_code == 302
    principal_id = client.get("/auth/principal", base_url=ORIGIN).get_json()["principal"]["id"]
    replacement = lifecycle.operator_recover(principal_id)
    assert replacement.metadata.credential_type == "portable"
    assert client.get("/", base_url=ORIGIN).status_code == 302
    assert client.post("/auth/sign-in", base_url=ORIGIN, data={
        "credential": replacement.secret,
    }).status_code == 404
    assert client.post("/auth/credentials/redeem", base_url=ORIGIN, json={
        "credential": replacement.secret,
    }).status_code == 403
    with get_db_connect()() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM browser_sessions WHERE principal_id = ? AND revoked_at IS NULL",
            (principal_id,),
        ).fetchone()[0] == 0


def test_oidc_allowlist_provisions_only_selected_subject(monkeypatch):
    provider = LocalProvider(monkeypatch)
    provider.subject = "not-selected"
    client = _app(monkeypatch, _config(provisioning="allowlist", subjects=["selected"])).test_client()
    state = _start(client, provider)
    assert "oidc_error" in _callback(client, state).headers["Location"]
    provider.subject = "selected"
    state = _start(client, provider)
    assert _callback(client, state).headers["Location"] == "/"


def test_oidc_link_requires_recent_credential_and_unlink_revokes_all_sessions(monkeypatch):
    config = _config(profile="mixed", provisioning="disabled")
    provider = LocalProvider(monkeypatch)
    provider.subject = "link-subject"
    app = _app(monkeypatch, config)
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(conn=conn)
        conn.commit()
    client = app.test_client()
    page = client.get("/auth/sign-in", base_url=ORIGIN)
    nonce = _response_cookie(page, "darklab_sign_in_nonce")
    signed = client.post("/auth/sign-in", base_url=ORIGIN, data={"credential": bundle.credential.secret, "sign_in_nonce": nonce})
    assert signed.status_code == 302
    original_cookie = _client_cookie(client, BROWSER_SESSION_COOKIE)
    deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE browser_sessions SET absolute_expires_at = ? WHERE principal_id = ?",
            (timestamp(deadline), bundle.principal.id),
        )
        authenticated_at = conn.execute(
            "SELECT authenticated_at FROM browser_sessions WHERE principal_id = ? AND revoked_at IS NULL",
            (bundle.principal.id,),
        ).fetchone()["authenticated_at"]
        conn.commit()
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    assert client.post("/auth/oidc/link", base_url=ORIGIN).status_code == 403
    start = client.post("/auth/oidc/link", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf})
    assert start.status_code == 200
    state = parse_qs(urlsplit(start.get_json()["authorization_url"]).query)["state"][0]
    provider.expect(state)
    linked = _callback(client, state)
    assert linked.headers["Location"] == "/"
    for header in linked.headers.getlist("Set-Cookie"):
        cookies = SimpleCookie(header)
        for name in (BROWSER_SESSION_COOKIE, BROWSER_CSRF_COOKIE):
            if name in cookies:
                assert 0 < int(cookies[name]["max-age"]) <= 30
    with get_db_connect()() as conn:
        replacement = conn.execute(
            "SELECT authenticated_at, absolute_expires_at FROM browser_sessions "
            "WHERE principal_id = ? AND revoked_at IS NULL", (bundle.principal.id,),
        ).fetchone()
    assert replacement["authenticated_at"] == authenticated_at
    assert replacement["absolute_expires_at"] == timestamp(deadline)
    for cookie in (original_cookie, _client_cookie(client, BROWSER_SESSION_COOKIE)):
        assert not resolve_browser_session(cookie, idle_seconds=1800, now=deadline, touch=False).valid
    principal = client.get("/auth/principal", base_url=ORIGIN).get_json()
    assert principal["principal"]["id"] == bundle.principal.id
    assert principal["authentication"]["credential_type"] == "portable"
    assert client.get("/auth/oidc/identity", base_url=ORIGIN).get_json()["linked"] is True
    # The link keeps the credential-backed session; unlink still requires that
    # original credential authentication to be recent and revokes every session.
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    result = client.post("/auth/oidc/unlink", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf})
    assert result.get_json() == {"sessions_revoked": True, "unlinked": True}
    assert client.get("/", base_url=ORIGIN).status_code == 302


def test_fresh_oidc_sign_in_renews_absolute_deadline(monkeypatch):
    provider = LocalProvider(monkeypatch)
    provider.subject = "fresh-oidc-deadline"
    app = _app(monkeypatch, _config())
    client = app.test_client()
    assert _callback(client, _start(client, provider)).status_code == 302
    principal_id = client.get("/auth/principal", base_url=ORIGIN).get_json()["principal"]["id"]
    original_cookie = _client_cookie(client, BROWSER_SESSION_COOKIE)
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE browser_sessions SET absolute_expires_at = ? WHERE principal_id = ?",
            (timestamp(datetime.now(timezone.utc) + timedelta(seconds=30)), principal_id),
        )
        conn.commit()
    started = datetime.now(timezone.utc)
    assert _callback(client, _start(client, provider)).status_code == 302
    with get_db_connect()() as conn:
        replacement = conn.execute(
            "SELECT authenticated_at, absolute_expires_at FROM browser_sessions "
            "WHERE principal_id = ? AND revoked_at IS NULL", (principal_id,),
        ).fetchone()
    assert datetime.fromisoformat(replacement["authenticated_at"]) >= started
    assert datetime.fromisoformat(replacement["absolute_expires_at"]) >= started + timedelta(hours=12)
    assert not resolve_browser_session(original_cookie, idle_seconds=1800, touch=False).valid


@pytest.mark.parametrize("profile", ["mixed", "token_required", "oidc_required"])
def test_credential_reauthentication_selects_the_permitted_sign_in_method(monkeypatch, profile):
    config = _config(profile=profile, provisioning="disabled" if profile == "token_required" else "automatic")
    client = _app(monkeypatch, config).test_client()
    response = client.get("/auth/sign-in?force=credential&next=%2F%3Foptions%3Daccess", base_url=ORIGIN)
    assert response.status_code == 200
    assert (b"Continue with identity provider" in response.data) == (profile == "oidc_required")
    if profile != "oidc_required":
        assert b'name="force" value="credential"' in response.data
        assert b'name="next" value="/?options=access"' in response.data
        nonce = _response_cookie(response, "darklab_sign_in_nonce")
        failed = client.post("/auth/sign-in", base_url=ORIGIN, data={
            "credential": "invalid", "sign_in_nonce": nonce,
            "force": "credential", "next": "/?options=access",
        })
        assert b"Continue with identity provider" not in failed.data
        assert b'name="force" value="credential"' in failed.data
    else:
        assert b"restricted-credential" not in response.data


def test_link_recency_is_visible_and_credential_reauthentication_restores_access(monkeypatch):
    provider = LocalProvider(monkeypatch)
    provider.subject = "reauth-link-subject"
    client = _app(monkeypatch, _config(profile="mixed")).test_client()
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(conn=conn)
        conn.commit()

    def credential_sign_in():
        page = client.get("/auth/sign-in?force=credential&next=%2F%3Foptions%3Daccess", base_url=ORIGIN)
        return client.post("/auth/sign-in", base_url=ORIGIN, data={
            "credential": bundle.credential.secret,
            "sign_in_nonce": _response_cookie(page, "darklab_sign_in_nonce"),
            "force": "credential", "next": "/?options=access",
        })

    assert credential_sign_in().headers["Location"] == "/?options=access"
    assert client.get("/auth/principal", base_url=ORIGIN).get_json()["authentication"]["recent_credential_session"] is True
    stale = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
    with get_db_connect()() as conn:
        conn.execute("UPDATE browser_sessions SET authenticated_at = ?", (stale,))
        conn.commit()
    assert client.get("/auth/principal", base_url=ORIGIN).get_json()["authentication"]["recent_credential_session"] is False
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    for action in ("link", "unlink"):
        response = client.post(f"/auth/oidc/{action}", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf})
        assert response.status_code == 403
        assert response.get_json()["error"] == "recent_credential_required"
    assert credential_sign_in().headers["Location"] == "/?options=access"
    assert client.get("/auth/principal", base_url=ORIGIN).get_json()["authentication"]["recent_credential_session"] is True
    csrf = _client_cookie(client, BROWSER_CSRF_COOKIE)
    malformed = client.post("/auth/oidc/link", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf}, json=["invalid"])
    assert malformed.status_code == 400
    start = client.post("/auth/oidc/link", base_url=ORIGIN, headers={"X-Darklab-CSRF": csrf}, json={"next": "/?options=access"})
    assert start.status_code == 200
    state = parse_qs(urlsplit(start.get_json()["authorization_url"]).query)["state"][0]
    provider.expect(state)
    assert _callback(client, state).headers["Location"] == "/?options=access"


@pytest.mark.parametrize("profile", ["mixed", "oidc_required"])
@pytest.mark.parametrize("defer", [False, True])
def test_provider_only_issuance_policy_rejects_unusable_browser_credentials(monkeypatch, profile, defer):
    provider = LocalProvider(monkeypatch)
    provider.subject = f"issuance-{profile}-{defer}"
    client = _app(monkeypatch, _config(profile=profile)).test_client()
    assert _callback(client, _start(client, provider)).status_code == 302
    principal_id = client.get("/auth/principal", base_url=ORIGIN).get_json()["principal"]["id"]
    csrf = {"X-Darklab-CSRF": _client_cookie(client, BROWSER_CSRF_COOKIE)}
    policy = client.get("/auth/credentials", base_url=ORIGIN).get_json()
    assert policy["portable_credentials_enabled"] is (profile == "mixed")
    recovery = lifecycle.operator_issue(principal_id, credential_type="portable", label="Operator recovery")
    for payload in ({}, {"type": "portable"}):
        issued = client.post("/auth/credentials", base_url=ORIGIN, headers=csrf, json=payload)
        assert issued.status_code == (201 if profile == "mixed" else 403)
        if profile == "oidc_required":
            assert "Browser credentials are disabled" in issued.get_json()["message"]
            assert "secret" not in issued.get_json()
    rotated = client.post(f"/auth/credentials/{recovery.metadata.id}/rotate", base_url=ORIGIN,
                          headers=csrf, json={"defer_revocation": defer})
    assert rotated.status_code == (201 if profile == "mixed" else 403)
    if profile == "oidc_required":
        remaining = client.get("/auth/credentials", base_url=ORIGIN).get_json()["credentials"]
        assert len(remaining) == 1
        assert remaining[0]["id"] == recovery.metadata.id
        assert remaining[0]["revoked_at"] is None
    pat = client.post("/auth/credentials", base_url=ORIGIN, headers=csrf,
                      json={"type": "pat", "scopes": ["identity:read"]})
    assert pat.status_code == 201
    replacement = client.post(f"/auth/credentials/{pat.get_json()['credential']['id']}/rotate",
                              base_url=ORIGIN, headers=csrf, json={"defer_revocation": defer})
    assert replacement.status_code == 201
    bearer = {"Authorization": f"Bearer {replacement.get_json()['secret']}"}
    api_client = client.application.test_client(use_cookies=False)
    assert api_client.get("/api/v1/whoami", base_url=ORIGIN, headers=bearer).status_code == 200
