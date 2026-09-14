# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Signed provider proofs and callback-time account binding stay fail closed."""

from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import copy_pristine_sqlite_database
from core import database
from core.database_access import get_db_connect
from services.auth import browser_sessions, oidc, resolver, storage
from services.auth.browser_sessions import BROWSER_CSRF_COOKIE, BROWSER_SESSION_COOKIE, revoke_browser_session
from services.auth.contracts import timestamp
from test_oidc_sign_in import (
    ISSUER, ORIGIN, LocalProvider, _app, _callback, _client_cookie, _config, _response_cookie,
)


SOURCE_CHANGES = (
    "session_revoked", "credential_revoked", "principal_disabled", "session_expired",
    "session_idle", "credential_expired", "credential_stale", "source_missing",
    "other_principal_binding", "other_subject_binding",
)


def start_link(app, provider, monkeypatch):
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(conn=conn)
        conn.commit()
    client = app.test_client()
    page = client.get("/auth/sign-in", base_url=ORIGIN)
    signed = client.post("/auth/sign-in", base_url=ORIGIN, data={
        "credential": bundle.credential.secret,
        "sign_in_nonce": _response_cookie(page, "darklab_sign_in_nonce"),
    })
    assert signed.status_code == 302
    started = client.post("/auth/oidc/link", base_url=ORIGIN, headers={
        "X-Darklab-CSRF": _client_cookie(client, BROWSER_CSRF_COOKIE),
    })
    assert started.status_code == 200
    query = parse_qs(urlsplit(started.get_json()["authorization_url"]).query)
    assert query["max_age"] == [str(oidc.RECENT_AUTH_SECONDS)]
    state = query["state"][0]
    provider.expect(state)
    clock = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)

    class CallbackClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.astimezone(tz) if tz is not None else clock.replace(tzinfo=None)

    monkeypatch.setattr(resolver, "datetime", CallbackClock)
    monkeypatch.setattr(browser_sessions, "datetime", CallbackClock)
    monkeypatch.setattr(oidc, "_now", lambda: clock)
    provider.claim_overrides = {
        "iat": int(clock.timestamp()), "exp": int(clock.timestamp()) + 600, "auth_time": int(clock.timestamp()),
    }
    with get_db_connect()() as conn:
        session = conn.execute(
            "SELECT id FROM browser_sessions WHERE principal_id = ? AND revoked_at IS NULL", (bundle.principal.id,),
        ).fetchone()
    assert session is not None
    errors = []
    monkeypatch.setattr(
        importlib.import_module("blueprints.auth"), "log_oidc_failure", lambda error, **_kwargs: errors.append(error),
    )
    return SimpleNamespace(
        app=app, client=client, provider=provider, state=state, bundle=bundle,
        session_id=session["id"], clock=clock, errors=errors,
    )


@pytest.fixture
def link(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "oidc-boundaries.db")))
    provider = LocalProvider(monkeypatch)
    return start_link(_app(monkeypatch, _config(profile="mixed", provisioning="disabled")), provider, monkeypatch)


def binding_snapshot():
    queries = {
        "principals": "SELECT id, status FROM principals ORDER BY id",
        "workspaces": "SELECT id, principal_id, storage_key FROM personal_workspaces ORDER BY id",
        "identities": "SELECT id, principal_id, issuer, subject FROM oidc_identities ORDER BY id",
        "sessions": "SELECT id, principal_id, credential_id, oidc_identity_id, revoked_at FROM browser_sessions ORDER BY id",
        "credentials": "SELECT id, principal_id, revoked_at, expires_at FROM credentials ORDER BY id",
    }
    with get_db_connect()() as conn:
        return {key: [dict(row) for row in conn.execute(query).fetchall()] for key, query in queries.items()}


def assert_rejected_callback(link, expected_reason):
    before = binding_snapshot()
    response = _callback(link.client, link.state)
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/sign-in?oidc_error=1"
    assert binding_snapshot() == before
    assert len(link.errors) == 1
    assert link.errors[0].reason == expected_reason
    assert not any(header.startswith(BROWSER_SESSION_COOKIE + "=") for header in response.headers.getlist("Set-Cookie"))


@pytest.mark.parametrize("cookie", ["missing", "mismatch"])
def test_link_callback_requires_the_matching_state_cookie(link, cookie):
    if cookie == "missing":
        link.client.delete_cookie(oidc.OIDC_STATE_COOKIE, domain="shell.example", path="/auth/oidc/callback")
    else:
        link.client.set_cookie(oidc.OIDC_STATE_COOKIE, "x" * 43, domain="shell.example", path="/auth/oidc/callback")
    assert_rejected_callback(link, "flow_expired")
    # A rejected cookie does not authorize a provider exchange.
    assert not any(url.endswith("/certs") for url in link.provider.get_calls)


@pytest.mark.parametrize("remaining", [0, -1])
def test_link_callback_rejects_flow_expiry_at_the_exact_deadline(link, remaining):
    with get_db_connect()() as conn:
        conn.execute("UPDATE oidc_auth_flows SET expires_at = ?", (timestamp(link.clock + timedelta(seconds=remaining)),))
        conn.commit()
    assert_rejected_callback(link, "flow_expired")


@pytest.mark.parametrize("claim,reason", [
    ("azp_missing", "authorized_party_mismatch"), ("azp_wrong", "authorized_party_mismatch"),
    ("iat_future", "issued_at_invalid"), ("subject_number", "subject_invalid"),
    ("subject_long", "subject_invalid"), ("subject_empty", "subject_invalid"), ("provider_missing", "recent_provider_required"),
    ("provider_string", "recent_provider_required"), ("provider_stale", "recent_provider_required"),
    ("provider_future", "recent_provider_required"),
])
def test_signed_link_proofs_reject_invalid_claims_without_changing_bindings(link, claim, reason):
    now = int(link.clock.timestamp())
    changes = {
        "azp_missing": {"aud": ["darklab-test", "other-client"]},
        "azp_wrong": {"aud": ["darklab-test", "other-client"], "azp": "other-client"},
        "iat_future": {"iat": now + 31}, "subject_number": {"sub": 7}, "subject_long": {"sub": "x" * 513},
        "subject_empty": {"sub": ""},
        "provider_missing": {"auth_time": None}, "provider_string": {"auth_time": str(now)},
        "provider_stale": {"auth_time": now - oidc.RECENT_AUTH_SECONDS - 1}, "provider_future": {"auth_time": now + 31},
    }
    link.provider.claim_overrides.update(changes[claim])
    if claim == "provider_missing":
        link.provider.claim_omissions.add("auth_time")
    assert_rejected_callback(link, reason)


@pytest.mark.parametrize("boundary", [
    "provider_oldest", "provider_future_leeway", "iat_leeway", "valid_azp", "subject_limit", "flow_live",
    "credential_recent_limit", "session_one_second", "credential_one_second", "idle_one_second",
])
def test_signed_link_proofs_accept_exact_valid_boundaries(link, boundary):
    now = int(link.clock.timestamp())
    changes = {
        "provider_oldest": {"auth_time": now - oidc.RECENT_AUTH_SECONDS},
        "provider_future_leeway": {"auth_time": now + 30}, "iat_leeway": {"iat": now + 30},
        "valid_azp": {"aud": ["darklab-test", "other-client"], "azp": "darklab-test"},
        "subject_limit": {"sub": "x" * 512}, "flow_live": {},
    }
    link.provider.claim_overrides.update(changes.get(boundary, {}))
    if boundary == "flow_live":
        with get_db_connect()() as conn:
            conn.execute("UPDATE oidc_auth_flows SET expires_at = ?", (timestamp(link.clock + timedelta(seconds=1)),))
            conn.commit()
    with get_db_connect()() as conn:
        if boundary == "credential_recent_limit":
            conn.execute(
                "UPDATE browser_sessions SET authenticated_at = ? WHERE id = ?",
                (timestamp(link.clock - timedelta(seconds=300)), link.session_id),
            )
        elif boundary == "session_one_second":
            conn.execute(
                "UPDATE browser_sessions SET absolute_expires_at = ? WHERE id = ?",
                (timestamp(link.clock + timedelta(seconds=1)), link.session_id),
            )
        elif boundary == "credential_one_second":
            conn.execute(
                "UPDATE credentials SET expires_at = ? WHERE id = ?",
                (timestamp(link.clock + timedelta(seconds=1)), link.bundle.credential.metadata.id),
            )
        elif boundary == "idle_one_second":
            conn.execute(
                "UPDATE browser_sessions SET last_seen_at = ? WHERE id = ?",
                (timestamp(link.clock - timedelta(seconds=1799)), link.session_id),
            )
        conn.commit()
    before = binding_snapshot()
    response = _callback(link.client, link.state)
    assert response.status_code == 302 and response.headers["Location"] == "/"
    after = binding_snapshot()
    assert after["principals"] == before["principals"] and after["workspaces"] == before["workspaces"]
    assert len(after["identities"]) == len(before["identities"]) + 1
    assert after["identities"][-1]["principal_id"] == link.bundle.principal.id
    assert len(after["sessions"]) == len(before["sessions"]) + 1
    assert not link.errors


def assert_source_change_rejected(app, provider, monkeypatch, change):
    link = start_link(app, provider, monkeypatch)
    expected_reason = "recent_credential_required"
    if change == "session_revoked":
        revoke_browser_session(link.session_id)
    elif change == "credential_revoked":
        storage.revoke_credential(link.bundle.principal.id, link.bundle.credential.metadata.id, allow_lockout=True)
    elif change == "principal_disabled":
        storage.disable_principal(link.bundle.principal.id, reason="operator stop")
    elif change in {"other_principal_binding", "other_subject_binding"}:
        with get_db_connect()() as conn:
            other = storage.create_principal_with_credential(conn=conn)
            conn.commit()
        destination = other.principal.id if change == "other_principal_binding" else link.bundle.principal.id
        subject = provider.subject if change == "other_principal_binding" else "different-subject"
        with get_db_connect()() as conn:
            conn.execute(
                "INSERT INTO oidc_identities (id, principal_id, issuer, subject, created_at) VALUES (?, ?, ?, ?, ?)",
                ("oid_" + "a" * 32, destination, ISSUER, subject, timestamp(link.clock)),
            )
            conn.commit()
        expected_reason = "identity_already_linked" if change == "other_principal_binding" else "workspace_already_linked"
    else:
        with get_db_connect()() as conn:
            if change == "session_expired":
                conn.execute(
                    "UPDATE browser_sessions SET absolute_expires_at = ? WHERE id = ?", (timestamp(link.clock), link.session_id),
                )
            elif change == "session_idle":
                conn.execute(
                    "UPDATE browser_sessions SET last_seen_at = ? WHERE id = ?",
                    (timestamp(link.clock - timedelta(minutes=30)), link.session_id),
                )
            elif change == "credential_expired":
                conn.execute(
                    "UPDATE credentials SET expires_at = ? WHERE id = ?",
                    (timestamp(link.clock), link.bundle.credential.metadata.id),
                )
            elif change == "credential_stale":
                conn.execute(
                    "UPDATE browser_sessions SET authenticated_at = ? WHERE id = ?",
                    (timestamp(link.clock - timedelta(seconds=301)), link.session_id),
                )
            elif change == "source_missing":
                conn.execute("DELETE FROM browser_sessions WHERE id = ?", (link.session_id,))
            else:
                raise AssertionError(change)
            conn.commit()
    assert_rejected_callback(link, expected_reason)


@pytest.mark.parametrize("change", SOURCE_CHANGES)
def test_link_rechecks_its_source_and_conflicting_bindings_at_callback(monkeypatch, tmp_path, change):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "oidc-source-change.db")))
    provider = LocalProvider(monkeypatch)
    app = _app(monkeypatch, _config(profile="mixed", provisioning="disabled"))
    assert_source_change_rejected(app, provider, monkeypatch, change)
