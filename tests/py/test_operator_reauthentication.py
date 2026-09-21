# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime, timedelta, timezone
import logging
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from admin_helpers import operator_db as _operator_db
from core.database_access import get_db_connect
from services.auth import (
    browser_sessions,
    observability,
    oidc,
    oidc_diagnostics,
    operator_access,
    operator_grants,
    operator_reauth,
    resolver,
    storage,
)
from services.auth.contracts import IdentityStorageError, timestamp
from test_oidc_sign_in import (
    ORIGIN,
    LocalProvider,
    _callback,
    _client_cookie,
    _config,
    _start,
)

operator_db = _operator_db


def app_for(monkeypatch, config):
    import config as shell_config
    from core import database

    import app as application
    monkeypatch.setattr(shell_config, "CFG", config)
    monkeypatch.setattr(application, "CFG", config)
    monkeypatch.setattr(database, "CFG", config)
    app = application.create_app(config)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    return app


def create_identity():
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(conn=conn)
        conn.commit()
    return bundle


def source_context(bundle, issued):
    return SimpleNamespace(
        principal_id=bundle.principal.id, browser_session_id=issued.id, authentication_method="browser_cookie",
    )


def credential_setup(operator_db, monkeypatch, profile="token_required"):
    overrides = {"access_profile": profile, "metrics_allowed_cidrs": ["127.0.0.0/8"]}
    if profile == "mixed":
        provider = _config("mixed", provisioning="disabled")
        overrides.update({key: provider[key] for key in (
            "oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_redirect_uri",
        )})
    cfg = operator_db.cfg.with_overrides(overrides)
    app = app_for(monkeypatch, cfg)
    bundle = create_identity()
    operator_grants.set_grant(bundle.principal.id, granted=True)
    issued = browser_sessions.create_browser_session(
        principal_id=bundle.principal.id, credential_id=bundle.credential.metadata.id, absolute_seconds=43200,
    )
    client = app.test_client()
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, issued.cookie_value, domain="shell.example")
    client.set_cookie(browser_sessions.BROWSER_CSRF_COOKIE, issued.csrf_token, domain="shell.example")
    return app, client, bundle, issued


@pytest.mark.parametrize("profile", ["open", "token_required"])
def test_credential_step_up_checks_csrf_identity_and_keeps_absolute_expiry(operator_db, monkeypatch, profile):
    _app, client, bundle, original = credential_setup(operator_db, monkeypatch, profile)
    peer = create_identity()
    page = client.get("/admin/reauth?next=/admin/", base_url=ORIGIN)
    assert page.status_code == 200 and b"Verify operator access" in page.data
    assert page.headers["Cache-Control"] == "private, no-store"
    expired_form = client.post("/admin/reauth", base_url=ORIGIN, data={"credential": bundle.credential.secret})
    assert expired_form.status_code == 403 and expired_form.mimetype == "text/html"
    assert b"This form has expired" in expired_form.data and b"Sign in again" in expired_form.data
    assert original.csrf_token.encode() in expired_form.data
    assert bundle.credential.secret.encode() not in expired_form.data
    wrong = client.post("/admin/reauth", base_url=ORIGIN, data={
        "credential": peer.credential.secret, "csrf_token": original.csrf_token, "next": "/admin/",
    })
    assert wrong.status_code == 400 and peer.credential.secret.encode() not in wrong.data
    signed = client.post("/admin/reauth", base_url=ORIGIN, data={
        "credential": bundle.credential.secret, "csrf_token": original.csrf_token, "next": "//attacker.test",
    })
    assert signed.status_code == 302 and signed.headers["Location"] == "/admin/"
    cookie = _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE)
    replacement = browser_sessions.resolve_browser_session(cookie, idle_seconds=1800, touch=False).session
    assert replacement is not None
    assert replacement.id != original.id
    assert replacement.absolute_expires_at == original.absolute_expires_at
    assert browser_sessions.resolve_browser_session(original.cookie_value, idle_seconds=1800).state == "revoked"


@pytest.mark.parametrize("csrf", ["missing_cookie", "mismatched", "invalid_cookie"])
def test_reauthentication_csrf_errors_render_without_verifying(operator_db, monkeypatch, csrf):
    import blueprints.admin as admin

    _app, client, bundle, original = credential_setup(operator_db, monkeypatch)
    token = original.csrf_token
    if csrf == "missing_cookie":
        client.delete_cookie(browser_sessions.BROWSER_CSRF_COOKIE, domain="shell.example")
    elif csrf == "invalid_cookie":
        token = "unrecognized-token"
        client.set_cookie(browser_sessions.BROWSER_CSRF_COOKIE, token, domain="shell.example")
    else:
        token = "old-form-token"
    monkeypatch.setattr(admin, "redeem_portable_credential", lambda _secret: pytest.fail("CSRF failure verified a credential"))
    response = client.post("/admin/reauth", base_url=ORIGIN, data={
        "credential": bundle.credential.secret, "csrf_token": token, "next": "/audit?event_type=run.start",
    })
    assert response.status_code == 403 and response.mimetype == "text/html"
    assert b"This form has expired" in response.data and b"/audit?event_type=run.start" in response.data
    assert bundle.credential.secret.encode() not in response.data
    assert response.headers["Cache-Control"] == "private, no-store"
    assert _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE) == original.cookie_value


def test_limited_reauthentication_reports_throttling_without_verifying(operator_db, monkeypatch):
    import blueprints.admin as admin
    from services.auth.rate_limit import CredentialRateLimitResult

    _app, client, bundle, original = credential_setup(operator_db, monkeypatch)
    records = []
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    monkeypatch.setattr(observability, "log", SimpleNamespace(
        warning=lambda event, *, extra: records.append((event, extra)), isEnabledFor=lambda _level: False,
    ))
    monkeypatch.setattr(admin, "_redemption_limit", lambda _secret: CredentialRateLimitResult(False, retry_after=20))
    monkeypatch.setattr(admin, "redeem_portable_credential", lambda _secret: pytest.fail("Limited request verified a credential"))
    response = client.post("/admin/reauth", base_url=ORIGIN, data={
        "credential": bundle.credential.secret, "csrf_token": original.csrf_token,
    })
    assert response.status_code == 429 and response.headers["Retry-After"] == "20"
    assert b"Too many attempts" in response.data
    assert len(records) == 1 and records[0][0] == "INSTANCE_OPERATOR_REAUTH_FAILED"
    assert records[0][1]["reason"] == "rate_limited" and records[0][1]["http_status"] == 429
    assert records[0][1]["endpoint"] == "admin.reauthenticate"
    assert records[0][1]["request_id"] != "unknown"


@pytest.mark.parametrize("change", ["grant", "principal", "session", "credential", "absolute", "idle"])
def test_verification_cannot_revive_a_revoked_or_expired_source(operator_db, monkeypatch, change):
    app, _client, bundle, original = credential_setup(operator_db, monkeypatch)
    proof = resolver.redeem_portable_credential(bundle.credential.secret).context
    now = datetime.now(timezone.utc)
    if change == "grant":
        operator_grants.set_grant(bundle.principal.id, granted=False)
    else:
        with get_db_connect()() as conn:
            if change == "principal":
                conn.execute("UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?",
                             (timestamp(now), bundle.principal.id))
            elif change == "credential":
                conn.execute("UPDATE credentials SET revoked_at = ? WHERE id = ?",
                             (timestamp(now), bundle.credential.metadata.id))
            elif change == "session":
                conn.execute("UPDATE browser_sessions SET revoked_at = ? WHERE id = ?", (timestamp(now), original.id))
            elif change == "idle":
                conn.execute("UPDATE browser_sessions SET last_seen_at = ? WHERE id = ?",
                             (timestamp(now - timedelta(hours=1)), original.id))
            conn.commit()
    if change == "absolute":
        now = datetime.fromisoformat(original.absolute_expires_at)
    with pytest.raises(IdentityStorageError):
        operator_reauth.rotate_verified_session(source_context(bundle, original), app.config["DARKLAB_CONFIG"],
                                                credential_context=proof, now=now)
    with get_db_connect()() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM browser_sessions").fetchone()
        assert row is not None
        assert row["count"] == 1


@pytest.mark.parametrize("provider", [False, True])
def test_repeated_rotations_preserve_deadline_at_last_second(operator_db, monkeypatch, provider):
    cfg = operator_db.cfg.with_overrides({"access_profile": "token_required"})
    bundle = create_identity()
    operator_grants.set_grant(bundle.principal.id, granted=True)
    start = datetime.now(timezone.utc).replace(microsecond=0)
    identity_id = "oid_test_operator"
    if provider:
        cfg = _config("mixed").with_overrides({"browser_session_idle_minutes": 60})
        with get_db_connect()() as conn:
            conn.execute("INSERT INTO oidc_identities (id, principal_id, issuer, subject, created_at) VALUES (?, ?, ?, ?, ?)",
                         (identity_id, bundle.principal.id, cfg["oidc_issuer"], "operator_subject", timestamp(start)))
            conn.commit()
    original = browser_sessions.create_browser_session(
        principal_id=bundle.principal.id, credential_id="" if provider else bundle.credential.metadata.id,
        oidc_identity_id=identity_id if provider else "", absolute_seconds=3600, now=start,
    )
    issued = original
    for seconds in (900, 1800, 2700, 3599):
        clock = start + timedelta(seconds=seconds)
        proof = ({"provider_proof": oidc.OIDCProof(cfg["oidc_issuer"], "operator_subject", timestamp(clock))}
                 if provider else {"credential_context": resolver.redeem_portable_credential(bundle.credential.secret).context})
        issued = operator_reauth.rotate_verified_session(source_context(bundle, issued), cfg, now=clock, **proof)
        assert issued.absolute_expires_at == original.absolute_expires_at
    with pytest.raises(IdentityStorageError):
        operator_reauth.rotate_verified_session(source_context(bundle, issued), cfg, now=start + timedelta(seconds=3600), **proof)


def test_expiry_is_evaluated_after_waiting_for_locks(operator_db, monkeypatch):
    app, _client, bundle, original = credential_setup(operator_db, monkeypatch)
    proof = resolver.redeem_portable_credential(bundle.credential.secret).context
    clock = datetime.fromisoformat(original.created_at) + timedelta(seconds=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock
    monkeypatch.setattr(browser_sessions, "datetime", Clock)
    monkeypatch.setattr(operator_reauth, "datetime", Clock)
    lock = operator_grants.lock_principal
    def delayed_lock(conn, principal_id):
        nonlocal clock
        result = lock(conn, principal_id)
        clock = datetime.fromisoformat(original.absolute_expires_at)
        return result
    monkeypatch.setattr(operator_grants, "lock_principal", delayed_lock)
    with pytest.raises(IdentityStorageError):
        operator_reauth.rotate_verified_session(
            source_context(bundle, original), app.config["DARKLAB_CONFIG"], credential_context=proof,
        )


def provider_setup(operator_db, monkeypatch, profile="oidc_required"):
    config = _config(profile).with_overrides({
        "database_backend": operator_db.cfg["database_backend"], "database_url": operator_db.cfg["database_url"],
        "data_dir": operator_db.cfg["data_dir"], "metrics_allowed_cidrs": ["127.0.0.0/8"],
    })
    provider = LocalProvider(monkeypatch)
    app = app_for(monkeypatch, config)
    client = app.test_client()
    assert _callback(client, _start(client, provider)).status_code == 302
    principal_payload = client.get("/auth/principal", base_url=ORIGIN).get_json()
    assert principal_payload is not None
    principal = principal_payload["principal"]["id"]
    operator_grants.set_grant(principal, granted=True)
    csrf = _client_cookie(client, browser_sessions.BROWSER_CSRF_COOKIE)
    response = client.post("/admin/reauth", base_url=ORIGIN, data={"csrf_token": csrf, "next": "/admin/?view=host"})
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["Location"]).query)
    assert query["max_age"] == ["0"] and query["prompt"] == ["login"]
    state = query["state"][0]
    provider.expect(state)
    return app, client, provider, state, principal


@pytest.mark.parametrize("profile", ["open", "mixed", "oidc_required"])
def test_provider_step_up_binds_state_and_preserves_original_deadline_without_strict_cookie(
    operator_db, monkeypatch, profile,
):
    _app, client, _provider, state, principal = provider_setup(operator_db, monkeypatch, profile)
    old_cookie = _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE)
    old = browser_sessions.resolve_browser_session(old_cookie, idle_seconds=1800, touch=False).session
    assert old is not None
    client.delete_cookie(browser_sessions.BROWSER_SESSION_COOKIE, domain="shell.example")
    result = _callback(client, state)
    assert result.status_code == 302 and result.headers["Location"] == "/admin/?view=host"
    new = browser_sessions.resolve_browser_session(_client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE),
                                                    idle_seconds=1800, touch=False).session
    assert new is not None
    assert new.principal_id == principal and new.absolute_expires_at == old.absolute_expires_at
    assert new.id != old.id
    assert browser_sessions.resolve_browser_session(old_cookie, idle_seconds=1800).state == "revoked"


@pytest.mark.parametrize("provider_session", [False, True])
def test_profile_changes_preserve_browser_ownership_and_enforce_permitted_methods(
    operator_db, monkeypatch, provider_session,
):
    if provider_session:
        app, client, _provider, state, _principal = provider_setup(operator_db, monkeypatch, "open")
        assert _callback(client, state).status_code == 302
    else:
        app, client, _bundle, _issued = credential_setup(operator_db, monkeypatch, "mixed")
    original = client.get("/auth/principal", base_url=ORIGIN).json["principal"]
    cookie = _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE)
    csrf = _client_cookie(client, browser_sessions.BROWSER_CSRF_COOKIE)
    for profile in ["mixed", "token_required", "oidc_required", "open"]:
        app.config["DARKLAB_CONFIG"] = app.config["DARKLAB_CONFIG"].with_overrides({
            "access_profile": profile, "oidc_provisioning": "disabled",
        })
        allowed = profile != ("token_required" if provider_session else "oidc_required")
        identity = client.get("/auth/principal", base_url=ORIGIN)
        assert identity.status_code == (200 if allowed else 401)
        if allowed:
            assert identity.json["principal"] == original
            assert client.get("/admin/access", base_url=ORIGIN).status_code == 204
            assert client.post("/session/preferences", base_url=ORIGIN, json={}).status_code == 403
            written = client.post("/session/preferences", base_url=ORIGIN,
                                  headers={"X-Darklab-CSRF": csrf},
                                  json={"preferences": {"pref_prompt_username": "same-owner"}})
            assert written.status_code == 200
        else:
            assert client.get("/admin/access", base_url=ORIGIN).status_code == 404
            assert client.get("/", base_url=ORIGIN).status_code == 302
        assert _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE) == cookie
    saved = client.get("/session/preferences", base_url=ORIGIN).json
    assert saved["preferences"]["pref_prompt_username"] == "same-owner"


def test_inflight_provider_sign_in_cannot_override_new_token_required_policy(operator_db, monkeypatch):
    app, client, provider, _state, principal = provider_setup(operator_db, monkeypatch, "open")
    state = _start(client, provider)
    original = _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE)
    app.config["DARKLAB_CONFIG"] = app.config["DARKLAB_CONFIG"].with_overrides({
        "access_profile": "token_required", "oidc_provisioning": "disabled",
    })
    response = _callback(client, state)
    assert response.status_code == 302 and "oidc_error" in response.headers["Location"]
    assert _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE) == original
    assert client.get("/auth/principal", base_url=ORIGIN).status_code == 401
    assert operator_grants.has_grant(principal)


@pytest.mark.parametrize("failure", [
    "missing", "old", "future", "subject", "state", "revoked", "session", "session_without_cookie",
    "profile", "provider", "storage",
])
def test_provider_step_up_rejects_unverified_or_changed_context(operator_db, monkeypatch, failure):
    app, client, provider, state, principal = provider_setup(operator_db, monkeypatch)
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.Logger("operator-step-up-test", logging.WARNING)
    logger.addHandler(handler)
    monkeypatch.setattr(oidc_diagnostics, "log", logger)
    monkeypatch.setattr(observability, "log", logger)
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    if failure == "missing":
        provider.claim_omissions.add("auth_time")
    elif failure == "old":
        provider.claim_overrides["auth_time"] = int(datetime.now(timezone.utc).timestamp()) - 60
    elif failure == "future":
        provider.claim_overrides["auth_time"] = int(datetime.now(timezone.utc).timestamp()) + 300
    elif failure == "subject":
        provider.subject = "another-account"
    elif failure == "state":
        client.delete_cookie(oidc.OIDC_STATE_COOKIE, domain="shell.example", path="/auth/oidc/callback")
    elif failure == "revoked":
        operator_grants.set_grant(principal, granted=False)
    elif failure in {"session", "session_without_cookie"}:
        browser_sessions.revoke_principal_browser_sessions(principal, reason="test")
        if failure == "session_without_cookie":
            client.delete_cookie(browser_sessions.BROWSER_SESSION_COOKIE, domain="shell.example")
    elif failure == "profile":
        app.config["DARKLAB_CONFIG"] = app.config["DARKLAB_CONFIG"].with_overrides(
            {"access_profile": "token_required", "oidc_provisioning": "disabled"}
        )
    elif failure == "provider":
        provider.available = False
    elif failure == "storage":
        def unavailable(*_args, **_kwargs):
            raise IdentityStorageError("private-storage-sentinel")
        monkeypatch.setattr(operator_grants, "lock_principal", unavailable)
    result = _callback(client, state)
    assert result.status_code in (302, 404)
    terminals = [record for record in records if record.msg in {"OIDC_AUTH_FAILED", "OIDC_PROVIDER_FAILED"}]
    if failure != "profile":
        assert len(terminals) == 1
        record = terminals[0]
        assert record.purpose == ("unknown" if failure == "state" else "admin_reauth")
        assert record.levelno == (logging.ERROR if failure in {"provider", "storage"} else logging.WARNING)
        if failure in {"subject", "revoked", "session", "session_without_cookie"}:
            assert record.stage == "identity_binding" and record.reason == "operator_source_unavailable"
        elif failure == "storage":
            assert record.reason == "storage_failed"
        assert record.exc_info is None and record.stack_info is None
        assert "private-storage-sentinel" not in str(record.__dict__)
        assert provider.subject not in str(record.__dict__)
    if failure in {"missing", "old", "future"}:
        query = parse_qs(urlsplit(result.headers["Location"]).query)
        assert query["error"] == ["provider_freshness"]
        assert query["next"] == ["/admin/?view=host"]
        page = client.get(result.headers["Location"], base_url=ORIGIN)
        assert b"requires a signed auth_time" in page.data
        assert b"check the provider configuration" in page.data
    assert not any(value.startswith(browser_sessions.BROWSER_SESSION_COOKIE + "=")
                   for value in result.headers.getlist("Set-Cookie"))
    with get_db_connect()() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM browser_sessions").fetchone()
        assert row is not None
        assert row["count"] == 1
    assert "private" in result.headers["Cache-Control"]


@pytest.mark.parametrize("profile", ["open", "mixed", "oidc_required"])
@pytest.mark.parametrize("proof", ["missing", "stale"])
def test_provider_proof_does_not_change_ordinary_sign_in_recency(operator_db, monkeypatch, profile, proof):
    _app, client, provider, _state, _principal = provider_setup(operator_db, monkeypatch, profile)
    if proof == "missing":
        provider.claim_omissions.add("auth_time")
    else:
        provider.claim_overrides["auth_time"] = int(datetime.now(timezone.utc).timestamp()) - 3600
    assert _callback(client, _start(client, provider)).status_code == 302
    session = browser_sessions.resolve_browser_session(_client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE),
                                                       idle_seconds=1800, touch=False).session
    assert session is not None
    assert datetime.fromisoformat(session.authenticated_at) > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert (session.provider_authenticated_at is None) == (proof == "missing")
    assert client.get("/projects", base_url=ORIGIN).status_code == 200
    inspection = client.get("/admin/settings", base_url=ORIGIN)
    inspection_payload = inspection.json
    assert inspection_payload is not None
    assert inspection.status_code == 401 and inspection_payload["error"] == "reauthentication_required"
    with get_db_connect()() as conn:
        conn.execute("UPDATE browser_sessions SET authenticated_at = ? WHERE id = ?",
                     (timestamp(datetime.now(timezone.utc) - timedelta(minutes=6)), session.id))
        conn.commit()
    stale = client.post("/auth/sessions/revoke-all", base_url=ORIGIN,
                        headers={"X-Darklab-CSRF": _client_cookie(client, browser_sessions.BROWSER_CSRF_COOKIE)})
    assert stale.status_code == 403
    stale_payload = stale.json
    assert stale_payload is not None
    assert stale_payload["error"] == "recent_authentication_required"
    assert _callback(client, _start(client, provider)).status_code == 302
    inspection_payload = client.get("/admin/settings", base_url=ORIGIN).json
    assert inspection_payload is not None
    assert inspection_payload["error"] == "reauthentication_required"
    revoked = client.post("/auth/sessions/revoke-all", base_url=ORIGIN,
                          headers={"X-Darklab-CSRF": _client_cookie(client, browser_sessions.BROWSER_CSRF_COOKIE)})
    revoked_payload = revoked.json
    assert revoked_payload is not None
    assert revoked.status_code == 200 and revoked_payload["revoked_sessions"] >= 1


def test_provider_proof_upgrade_preserves_sessions_without_inventing_freshness(operator_db, monkeypatch):
    from core.database_backend import DatabaseBackend
    from core.migrations.v0088_provider_authentication_time import MIGRATION

    _app, client, _provider, _state, _principal = provider_setup(operator_db, monkeypatch)
    cookie = _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE)
    session = browser_sessions.resolve_browser_session(cookie, idle_seconds=1800, touch=False).session
    assert session is not None
    assert session.provider_authenticated_at
    with get_db_connect()() as conn:
        conn.execute("ALTER TABLE browser_sessions DROP COLUMN provider_authenticated_at")
        before_row = conn.execute("SELECT * FROM browser_sessions WHERE id = ?", (session.id,)).fetchone()
        assert before_row is not None
        before = dict(before_row)
        for statement in MIGRATION.statements_for(DatabaseBackend(operator_db.backend)):
            conn.execute(statement)
        after_row = conn.execute("SELECT * FROM browser_sessions WHERE id = ?", (session.id,)).fetchone()
        assert after_row is not None
        after = dict(after_row)
        conn.commit()
    assert after.pop("provider_authenticated_at") is None
    assert after == before
    resolved = browser_sessions.resolve_browser_session(cookie, idle_seconds=1800, touch=False)
    assert resolved.session is not None
    assert resolved.valid and resolved.session.authenticated_at == session.authenticated_at
    inspection_payload = client.get("/admin/settings", base_url=ORIGIN).json
    assert inspection_payload is not None
    assert inspection_payload["error"] == "reauthentication_required"


def test_team_rotation_preserves_provider_proof_without_refreshing_console_access(operator_db, monkeypatch):
    _app, client, _provider, _state, _principal = provider_setup(operator_db, monkeypatch)
    old = browser_sessions.resolve_browser_session(_client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE),
                                                   idle_seconds=1800, touch=False).session
    assert old is not None
    proof_time = timestamp(datetime.now(timezone.utc) - timedelta(minutes=31))
    with get_db_connect()() as conn:
        conn.execute("UPDATE browser_sessions SET provider_authenticated_at = ? WHERE id = ?", (proof_time, old.id))
        conn.commit()
    for number in range(2):
        response = client.post("/session/teams", base_url=ORIGIN, json={"name": f"Provider Team {number}"},
                               headers={"X-Darklab-CSRF": _client_cookie(client, browser_sessions.BROWSER_CSRF_COOKIE)})
        assert response.status_code == 201
        replacement = browser_sessions.resolve_browser_session(
            _client_cookie(client, browser_sessions.BROWSER_SESSION_COOKIE), idle_seconds=1800, touch=False,
        ).session
        assert replacement is not None
        assert replacement.id != old.id
        assert replacement.authenticated_at == old.authenticated_at
        assert replacement.provider_authenticated_at == proof_time
        assert replacement.absolute_expires_at == old.absolute_expires_at
        inspection = client.get("/admin/settings", base_url=ORIGIN)
        inspection_payload = inspection.json
        assert inspection_payload is not None
        assert inspection.status_code == 401 and inspection_payload["error"] == "reauthentication_required"
        old = replacement


@pytest.mark.parametrize("path,status", [("/admin/", 302), ("/admin/settings", 401), ("/admin/reauth", 302)])
def test_open_anonymous_operator_requests_require_sign_in_without_reading_grants(operator_db, monkeypatch, path, status):
    cfg = operator_db.cfg.with_overrides({"access_profile": "open"})
    app = app_for(monkeypatch, cfg)
    def forbidden(*args, **kwargs):
        pytest.fail("anonymous request read an operator grant")
    monkeypatch.setattr(operator_access, "has_grant", forbidden)
    response = app.test_client().get(path, base_url=ORIGIN)
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "private, no-store"


def test_logout_committed_during_rotation_cannot_be_undone(operator_db, monkeypatch):
    if operator_db.backend != "postgres":
        pytest.skip("row-lock contention is qualified on Postgres")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    app, _client, bundle, original = credential_setup(operator_db, monkeypatch)
    proof = resolver.redeem_portable_credential(bundle.credential.secret).context
    entered = Event()
    lock = browser_sessions.lock_rotation_source
    def notified_lock(*args, **kwargs):
        entered.set()
        return lock(*args, **kwargs)
    monkeypatch.setattr(browser_sessions, "lock_rotation_source", notified_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with get_db_connect()() as conn:
            conn.execute("UPDATE browser_sessions SET revoked_at = ? WHERE id = ?", (timestamp(), original.id))
            future = executor.submit(operator_reauth.rotate_verified_session, source_context(bundle, original),
                                     app.config["DARKLAB_CONFIG"], credential_context=proof)
            assert entered.wait(5)
            conn.commit()
        with pytest.raises(IdentityStorageError):
            future.result(timeout=10)
    with get_db_connect()() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM browser_sessions").fetchone()
        assert row is not None
        assert row["count"] == 1


def test_provider_flow_upgrade_preserves_pending_sign_in_and_link(operator_db):
    from core.database_backend import DatabaseBackend
    from core.migrations.runner import apply_migration
    from core.migrations.v0084_oidc_identities import MIGRATION as old
    from core.migrations.v0087_operator_reauthentication import MIGRATION as upgrade

    bundle = create_identity()
    backend = DatabaseBackend(operator_db.backend)
    now = timestamp(datetime.now(timezone.utc))
    with get_db_connect()() as conn:
        conn.execute("DROP TABLE oidc_auth_flows")
        for statement in old.statements_for(backend):
            if "CREATE TABLE oidc_auth_flows" in statement or "CREATE INDEX idx_oidc_auth_flows_expiry" in statement:
                conn.execute(statement)
        for purpose in ("sign_in", "link"):
            conn.execute(
                "INSERT INTO oidc_auth_flows "
                "(state_digest, nonce, code_verifier, purpose, principal_id, browser_session_id, "
                "next_path, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (purpose.encode(), "nonce", "verifier", purpose, bundle.principal.id if purpose == "link" else None,
                 "browser_source" if purpose == "link" else None, "/admin/", now, now),
            )
        before = [dict(row) for row in conn.execute("SELECT * FROM oidc_auth_flows ORDER BY purpose").fetchall()]
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", ("0087",))
        conn.commit()
        apply_migration(conn, upgrade, backend=backend)
        after = [dict(row) for row in conn.execute("SELECT * FROM oidc_auth_flows ORDER BY purpose").fetchall()]
        assert before == after


@pytest.mark.parametrize("reason,status", [
    ("profile", 404), ("ineligible", 404), ("source_unavailable", 302),
    ("credential_rejected", 400), ("rate_limited", 429),
])
def test_operator_warning_repeats_use_fixed_keys_and_safe_context(monkeypatch, reason, status):
    from flask import Flask

    app = Flask(__name__)
    records = []
    clock = [100.0]
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(observability, "log", SimpleNamespace(
        warning=lambda event, *, extra: records.append((event, extra)), isEnabledFor=lambda _level: False,
    ))

    @app.get("/admin/settings")
    def protected():
        if status == 404:
            return operator_access.hidden_response(reason)
        observability.log_operator_reauthentication_failed(reason)
        return "", status

    client = app.test_client()
    for index in range(100):
        response = client.get(
            f"/admin/settings?search=private-query-{index}",
            environ_overrides={"darklab_request_id": f"request-{index}", "REMOTE_ADDR": "192.0.2.1"},
        )
        assert response.status_code == status
    assert len(records) == 1
    event, fields = records[0]
    assert event == ("INSTANCE_OPERATOR_ACCESS_DENIED" if status == 404 else "INSTANCE_OPERATOR_REAUTH_FAILED")
    assert fields == {"reason": reason, "http_status": status, "request_id": "request-0",
                      "endpoint": "protected", "suppressed_repeat_count": 0}
    clock[0] += 60
    assert client.get("/admin/settings").status_code == status
    assert len(records) == 2 and records[1][1]["suppressed_repeat_count"] == 99
    for index in range(100):
        observability.log_operator_access_denied(f"private-reason-{index}")
        observability.log_operator_reauthentication_failed(f"private-reason-{index}")
    assert len(observability._WARNING_STATE) <= 3
    assert "private-" not in repr(records) + repr(observability._WARNING_STATE)
    assert "192.0.2.1" not in repr(records) + repr(observability._WARNING_STATE)
