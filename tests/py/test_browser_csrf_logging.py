# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""CSRF diagnostics classify rejections without recording either token."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import principal_identity
from services.auth import access_profile, observability
from services.auth.browser_sessions import BROWSER_CSRF_COOKIE, BROWSER_SESSION_COOKIE, create_browser_session
from services.auth.resolver import public_lookup_id_from_headers


@pytest.fixture
def csrf_context(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "csrf.db")))
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    app.config["RATELIMIT_ENABLED"] = False
    identity = principal_identity("CSRF diagnostics")
    issued = create_browser_session(
        principal_id=identity.principal_id,
        credential_id=public_lookup_id_from_headers(identity.browser_headers()), absolute_seconds=3600,
    )
    client = app.test_client()
    client.set_cookie(BROWSER_SESSION_COOKIE, issued.cookie_value, secure=True)
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.Logger("csrf-diagnostics-test", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(observability, "log", logger)
    verify = Mock(wraps=access_profile.verify_csrf_token)
    monkeypatch.setattr(access_profile, "verify_csrf_token", verify)
    return SimpleNamespace(
        app=app, client=client, identity=identity, issued=issued, records=records, verify=verify, logger=logger,
    )


def _csrf_records(ctx):
    return [record for record in ctx.records if record.msg == "BROWSER_CSRF_REJECTED"]


@pytest.mark.parametrize("reason", ["missing_cookie", "missing_header", "token_mismatch", "stored_token_invalid"])
def test_cookie_csrf_rejections_have_one_safe_reason_and_skip_unneeded_verification(csrf_context, reason):
    ctx = csrf_context
    cookie = ctx.issued.csrf_token
    header = cookie
    if reason == "missing_cookie":
        cookie = ""
    elif reason == "missing_header":
        header = ""
    elif reason == "token_mismatch":
        header = "private-mismatched-token-canary"
    else:
        cookie = header = "x" * 43
    if cookie:
        ctx.client.set_cookie(BROWSER_CSRF_COOKIE, cookie, secure=True)
    response = ctx.client.post(
        "/session/preferences?private-query-canary", base_url="https://localhost",
        headers={"X-Darklab-CSRF": header}, json={"preferences": {}},
    )
    assert response.status_code == 403 and response.get_json()["error"] == "csrf_validation_failed"
    records = _csrf_records(ctx)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING and record.reason == reason and record.http_status == 403
    assert record.request_id != "unknown" and record.endpoint != "unknown"
    assert set(_extra_fields(record)) == {"request_id", "endpoint", "reason", "http_status", "suppressed_repeat_count"}
    assert ctx.verify.call_count == (1 if reason == "stored_token_invalid" else 0)
    gelf = json.loads(GELFFormatter().format(record))
    assert gelf["_reason"] == reason
    rendered = _TextFormatter().format(record) + json.dumps(gelf)
    for private in (
        ctx.issued.id, ctx.issued.cookie_value, ctx.issued.csrf_token, ctx.identity.principal_id,
        ctx.identity.portable_secret, "private-query-canary", "private-mismatched-token-canary", "x" * 43,
    ):
        assert private not in rendered


@pytest.mark.parametrize("case", ["valid_cookie_post", "safe_get", "portable_header"])
def test_valid_and_exempt_requests_do_not_emit_csrf_rejections(csrf_context, case):
    ctx = csrf_context
    if case == "safe_get":
        response = ctx.client.get("/projects", base_url="https://localhost")
    elif case == "portable_header":
        ctx.client.delete_cookie(BROWSER_SESSION_COOKIE)
        response = ctx.client.post(
            "/session/preferences", base_url="https://localhost", headers=ctx.identity.browser_headers(),
            json={"preferences": {}},
        )
    else:
        ctx.client.set_cookie(BROWSER_CSRF_COOKIE, ctx.issued.csrf_token, secure=True)
        response = ctx.client.post(
            "/session/preferences", base_url="https://localhost", headers={"X-Darklab-CSRF": ctx.issued.csrf_token},
            json={"preferences": {}},
        )
    assert response.status_code == 200
    assert _csrf_records(ctx) == []
    assert ctx.verify.call_count == (1 if case == "valid_cookie_post" else 0)


def test_csrf_warning_repeats_are_bounded_by_fixed_reason(csrf_context, monkeypatch):
    ctx = csrf_context
    clock = [100.0]
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    for _ in range(3):
        assert ctx.client.post("/session/preferences", base_url="https://localhost", json={}).status_code == 403
    assert len(_csrf_records(ctx)) == 1
    clock[0] += 60
    assert ctx.client.post("/session/preferences", base_url="https://localhost", json={}).status_code == 403
    assert _csrf_records(ctx)[-1].suppressed_repeat_count == 2
    for index in range(100):
        observability.log_browser_csrf_rejected(f"private-untrusted-reason-{index}")
    assert len(observability._WARNING_STATE) == 2
    assert _csrf_records(ctx)[-1].reason == "invalid_csrf"
    assert "private-untrusted" not in "".join(GELFFormatter().format(record) for record in _csrf_records(ctx))


@pytest.mark.parametrize("case", ["missing_cookie", "missing_nonce", "mismatched_nonce"])
@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO])
def test_expired_sign_in_form_is_debug_only_and_does_not_verify_credentials(csrf_context, monkeypatch, case, level):
    from blueprints import auth as auth_routes

    ctx = csrf_context
    ctx.logger.setLevel(level)
    client = ctx.app.test_client()
    assert client.get("/auth/sign-in", base_url="https://localhost").status_code == 200
    cookie = client.get_cookie("darklab_sign_in_nonce", path="/auth/sign-in")
    assert cookie is not None
    nonce = cookie.value
    if case == "missing_cookie":
        client.delete_cookie("darklab_sign_in_nonce", path="/auth/sign-in")
    elif case == "missing_nonce":
        nonce = ""
    else:
        nonce = "private-mismatched-form-nonce"
    redeem = Mock(side_effect=AssertionError("expired form reached credential verifier"))
    monkeypatch.setattr(auth_routes, "redeem_portable_credential", redeem)
    response = client.post(
        "/auth/sign-in", base_url="https://localhost",
        data={"sign_in_nonce": nonce, "credential": "private-submitted-credential"},
    )
    assert response.status_code == 200
    assert "The sign-in page expired" in response.get_data(as_text=True)
    redeem.assert_not_called()
    records = [record for record in ctx.records if record.msg == "BROWSER_SIGN_IN_FORM_REJECTED"]
    assert len(records) == (1 if level == logging.DEBUG else 0)
    assert not any(record.levelno >= logging.WARNING for record in ctx.records)
    if records:
        record = records[0]
        assert record.reason == "invalid_nonce" and record.http_status == 200
        assert set(_extra_fields(record)) == {"request_id", "endpoint", "reason", "http_status"}
        rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
        for private in (cookie.value, "private-mismatched-form-nonce", "private-submitted-credential"):
            assert private not in rendered
