# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OIDC diagnostics retain stage and cause without provider or credential data."""

import importlib
import json
import logging
import sqlite3

import pytest
import requests

from conftest import copy_pristine_sqlite_database
from core import database
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from services.auth import observability, oidc, oidc_cache, oidc_diagnostics
from test_oidc_sign_in import CALLBACK, ISSUER, LocalProvider, ORIGIN, _app, _callback, _config, _Response, _start


@pytest.fixture
def records(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "oidc-logging.db")))
    oidc_cache.reset_provider_cache()
    oidc_cache._cleanup_trust_bundle()
    captured = []
    handler = logging.Handler()
    handler.emit = lambda record: captured.append(record)
    logger = logging.Logger("oidc-diagnostics", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(oidc_diagnostics, "log", logger)
    monkeypatch.setattr(observability, "log", logger)
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    yield captured
    oidc_cache.reset_provider_cache()
    oidc_cache._cleanup_trust_bundle()


def _metadata():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/auth",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/keys",
        "code_challenge_methods_supported": ["S256"],
    }


def _terminals(records):
    return [record for record in records if record.msg in {"OIDC_AUTH_FAILED", "OIDC_PROVIDER_FAILED"}]


def _assert_event(records, *, stage, reason, level, status=None, error_type=None, private=()):
    terminal = _terminals(records)
    assert len(terminal) == 1
    record = terminal[0]
    assert record.stage == stage and record.reason == reason
    assert record.levelno == level
    assert record.http_status == status
    if error_type is not None:
        assert record.error_type == error_type
    assert isinstance(record.duration_ms, (int, float)) and 0 <= record.duration_ms <= 300_000
    assert set(_extra_fields(record)) <= {
        "stage",
        "reason",
        "error_type",
        "http_status",
        "duration_ms",
        "purpose",
        "request_id",
        "endpoint",
        "suppressed_repeat_count",
    }
    for item in records:
        assert item.exc_info is None and not item.stack_info
        rendered = _TextFormatter().format(item) + GELFFormatter().format(item)
        for value in (ISSUER, CALLBACK, "test-secret", "private-canary", *private):
            assert value not in rendered
    assert json.loads(GELFFormatter().format(record))["_stage"] == stage
    return record


@pytest.mark.parametrize(
    "failure,reason,status,error_type",
    [
        ("timeout", "timeout", None, "Timeout"),
        ("tls", "tls_error", None, "SSLError"),
        ("network", "network_error", None, "ConnectionError"),
        ("status", "provider_http_error", 503, "OIDCUnavailable"),
        ("redirect", "provider_http_error", 302, "OIDCUnavailable"),
        ("large", "response_too_large", 200, "OIDCUnavailable"),
        ("json", "invalid_json", 200, "ValueError"),
        ("shape", "invalid_response_shape", 200, "OIDCUnavailable"),
        ("issuer", "issuer_mismatch", 200, "OIDCUnavailable"),
        ("endpoint", "invalid_endpoint", 200, "OIDCUnavailable"),
        ("pkce", "pkce_unsupported", 200, "OIDCUnavailable"),
    ],
)
def test_discovery_failures_keep_safe_cause_and_provider_status(records, monkeypatch, failure, reason, status, error_type):
    def get(*_args, **_kwargs):
        if failure in {"timeout", "tls", "network"}:
            error = {"timeout": requests.Timeout, "tls": requests.exceptions.SSLError, "network": requests.ConnectionError}[
                failure
            ]
            try:
                raise RuntimeError("private-canary inner error")
            except RuntimeError as cause:
                raise error("private-canary provider URL and credentials") from cause
        data = _metadata()
        if failure == "issuer":
            data["issuer"] = "https://private-canary.example"
        if failure == "endpoint":
            data["token_endpoint"] = "https://[private-canary"
        if failure == "pkce":
            data["code_challenge_methods_supported"] = ["plain"]
        response = _Response([] if failure == "shape" else data)
        response.status_code = {"status": 503, "redirect": 302}.get(failure, 200)
        if failure == "large":
            response.content = b"private-canary" * 30_000
        if failure == "json":

            def invalid_json():
                raise ValueError("private-canary response body")

            response.json = invalid_json
        return response

    monkeypatch.setattr(oidc.requests, "get", get)
    with pytest.raises(oidc.OIDCUnavailable) as caught:
        oidc.provider_metadata(_config())
    oidc_diagnostics.log_oidc_failure(caught.value)
    _assert_event(records, stage="discovery", reason=reason, level=logging.ERROR, status=status, error_type=error_type)


@pytest.mark.parametrize("exists,reason", [(False, "ca_bundle_unavailable"), (True, "ca_bundle_invalid")])
def test_invalid_trust_configuration_identifies_the_discovery_stage(records, tmp_path, exists, reason):
    path = tmp_path / "private-canary-ca.pem"
    if exists:
        path.write_text("private-canary invalid certificate")
    config = {**_config(), "oidc_ca_bundle": str(path)}
    with pytest.raises(oidc.OIDCUnavailable) as caught:
        oidc.provider_metadata(config)
    oidc_diagnostics.log_oidc_failure(caught.value)
    _assert_event(records, stage="discovery", reason=reason, level=logging.ERROR)


@pytest.mark.parametrize(
    "status,payload,reason,level",
    [
        (400, {"error": "invalid_grant"}, "code_rejected", logging.WARNING),
        (400, {"error": "access_denied"}, "provider_denied", logging.WARNING),
        (401, {"error": "invalid_client"}, "client_authentication_failed", logging.ERROR),
        (400, {"error": "unauthorized_client"}, "client_not_authorized", logging.ERROR),
        (400, {"error": "temporarily_unavailable"}, "provider_unavailable", logging.ERROR),
        (503, {"error": "server_error"}, "provider_http_error", logging.ERROR),
        (200, "invalid-json", "invalid_json", logging.ERROR),
        (200, {}, "id_token_missing", logging.ERROR),
    ],
)
def test_real_oauth_client_exchange_reports_status_without_response_or_request_data(
    records,
    monkeypatch,
    status,
    payload,
    reason,
    level,
):
    if isinstance(payload, dict):
        payload = {**payload, "error_description": "private-canary client and response details"}

    def send(_session, request, **_kwargs):
        response = requests.Response()
        response.status_code = status
        response.url = "https://private-canary.example/token"
        response.request = request
        response._content = b"private-canary invalid JSON" if payload == "invalid-json" else json.dumps(payload).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    flow = oidc.OIDCFlow("private-canary-state", "private-canary-nonce", "private-canary-proof", "sign_in", "", "", "/")
    with pytest.raises(oidc.OIDCError) as caught:
        oidc._exchange_token(_config(), flow, "private-canary-code", _metadata())
    oidc_diagnostics.log_oidc_failure(caught.value)
    record = _assert_event(records, stage="token_exchange", reason=reason, level=level, status=status)
    assert record.purpose == "sign_in"


@pytest.mark.parametrize("keys", [{"keys": []}, {"keys": [{"kty": "private-canary-invalid"}]}])
def test_unusable_signing_keys_are_dependency_errors(records, monkeypatch, keys):
    monkeypatch.setattr(oidc.requests, "get", lambda *_args, **_kwargs: _Response(keys))
    with pytest.raises(oidc.OIDCUnavailable) as caught:
        oidc._provider_keys(_config(), _metadata())
    oidc_diagnostics.log_oidc_failure(caught.value)
    _assert_event(records, stage="signing_keys", reason="invalid_signing_keys", level=logging.ERROR, status=200)


@pytest.mark.parametrize(
    "claim,reason",
    [
        ({"iss": "private-canary-issuer"}, "issuer_mismatch"),
        ({"aud": "private-canary-audience"}, "audience_mismatch"),
        ({"nonce": "private-canary-nonce"}, "nonce_mismatch"),
        ({"exp": 1}, "token_expired"),
        ({"iat": 9_999_999_999}, "issued_at_invalid"),
    ],
)
def test_signed_token_rejections_keep_the_validation_reason_without_claim_values(records, monkeypatch, claim, reason):
    provider = LocalProvider(monkeypatch)
    provider.nonce, provider.verifier = "private-canary-nonce-expected", "private-canary-proof"
    provider.claim_overrides = claim
    flow = oidc.OIDCFlow("private-canary-state", provider.nonce, provider.verifier, "sign_in", "", "", "/")
    with pytest.raises(oidc.OIDCError) as caught:
        oidc.exchange_code(_config(), flow, "local-code")
    assert not isinstance(caught.value, oidc.OIDCUnavailable)
    oidc_diagnostics.log_oidc_failure(caught.value)
    _assert_event(records, stage="token_validation", reason=reason, level=logging.WARNING, private=(provider.subject,))


@pytest.mark.parametrize(
    "failure,stage,reason,level",
    [
        ("flow_storage", "flow_validation", "storage_failed", logging.ERROR),
        ("binding_storage", "identity_binding", "storage_failed", logging.ERROR),
        ("session_storage", "session_creation", "storage_failed", logging.ERROR),
        ("denied", "provider_authorization", "provider_denied", logging.WARNING),
        ("unapproved", "identity_binding", "provisioning_denied", logging.WARNING),
        ("state", "flow_validation", "flow_expired", logging.WARNING),
    ],
)
def test_callback_failures_emit_one_terminal_record_and_keep_generic_redirects(
    records, monkeypatch, failure, stage, reason, level
):
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config("mixed", "disabled" if failure == "unapproved" else "automatic")).test_client()
    state = _start(client, provider)
    records.clear()

    def unavailable(*_args, **_kwargs):
        raise sqlite3.OperationalError("private-canary database statement and values")

    if failure == "flow_storage":
        monkeypatch.setattr(oidc, "run_transaction", unavailable)
    elif failure == "binding_storage":
        monkeypatch.setattr(oidc, "_create_principal", unavailable)
    elif failure == "session_storage":
        monkeypatch.setattr(importlib.import_module("blueprints.auth"), "create_browser_session", unavailable)
    if failure == "denied":
        response = client.get(f"/auth/oidc/callback?state={state}&error=private-canary-denial", base_url=ORIGIN)
    else:
        response = _callback(client, "private-canary-invalid-state" if failure == "state" else state)
    assert response.status_code == 302 and response.headers["Location"] == "/auth/sign-in?oidc_error=1"
    assert "private-canary" not in response.get_data(as_text=True)
    assert not any(
        "darklab_browser_session=" in header and "Max-Age=0" not in header for header in response.headers.getlist("Set-Cookie")
    )
    _assert_event(records, stage=stage, reason=reason, level=level, private=(state, provider.nonce, provider.verifier))


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR])
def test_successful_sign_in_reports_safe_debug_stage_completion_only_when_enabled(records, monkeypatch, level):
    oidc_diagnostics.log.setLevel(level)
    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    state = _start(client, provider)
    response = _callback(client, state)
    assert response.status_code == 302 and response.headers["Location"] == "/"
    assert not _terminals(records)
    stages = [record for record in records if record.msg == "OIDC_STAGE_COMPLETED"]
    if level != logging.DEBUG:
        assert not stages
        return
    assert {record.stage for record in stages} == {
        "flow_creation",
        "discovery",
        "flow_validation",
        "token_exchange",
        "signing_keys",
        "token_validation",
        "identity_binding",
        "session_creation",
    }
    for record in stages:
        assert record.outcome == "completed" and record.purpose == "sign_in"
        assert 0 <= record.duration_ms <= 300_000 and not record.exc_info
        rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
        for private in (ISSUER, "test-secret", state, provider.nonce, provider.verifier, provider.subject):
            assert private not in rendered


@pytest.mark.parametrize(
    "failure,stage", [("provider", "discovery"), ("flow_storage", "flow_creation"), ("unlink_storage", "identity_binding")]
)
def test_link_and_unlink_failures_emit_one_dependency_record(records, monkeypatch, failure, stage):
    from services.auth import browser_sessions, storage

    provider = LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config("mixed")).test_client()
    bundle = storage.create_principal_with_credential()
    issued = browser_sessions.create_browser_session(
        principal_id=bundle.principal.id,
        credential_id=bundle.credential.metadata.id,
        absolute_seconds=3600,
    )
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, issued.cookie_value, domain="shell.example", secure=True)
    client.set_cookie(browser_sessions.BROWSER_CSRF_COOKIE, issued.csrf_token, domain="shell.example", secure=True)

    def unavailable(*_args, **_kwargs):
        raise sqlite3.OperationalError("private-canary local database failure")

    if failure == "provider":
        provider.available = False
    else:
        monkeypatch.setattr(oidc, "run_transaction", unavailable)
    records.clear()
    path = "/auth/oidc/unlink" if failure == "unlink_storage" else "/auth/oidc/link"
    response = client.post(path, base_url=ORIGIN, headers={"X-Darklab-CSRF": issued.csrf_token})
    assert response.status_code == 503 and response.get_json()["error"] == "oidc_unavailable"
    assert "private-canary" not in response.get_data(as_text=True)
    record = _assert_event(
        records,
        stage=stage,
        reason="network_error" if failure == "provider" else "storage_failed",
        level=logging.ERROR,
        private=(issued.cookie_value, issued.csrf_token, bundle.credential.secret),
    )
    assert record.purpose == ("unlink" if failure == "unlink_storage" else "link")


def test_callback_origin_rejection_is_observable_without_request_values(records, monkeypatch):
    LocalProvider(monkeypatch)
    client = _app(monkeypatch, _config()).test_client()
    response = client.get("/auth/oidc/callback?state=private-canary", base_url="https://wrong.example")
    assert response.status_code == 302 and response.headers["Location"] == "/auth/sign-in?oidc_error=1"
    _assert_event(
        records, stage="callback_validation", reason="callback_origin_mismatch", level=logging.WARNING, private=("wrong.example",)
    )


def test_repeated_invalid_states_use_a_bounded_warning_key(records, monkeypatch):
    from types import SimpleNamespace
    from flask import Flask

    now = [100.0]
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: now[0]))
    app = Flask(__name__)
    for index in range(5):
        with app.test_request_context(f"/auth/oidc/callback?state=private-canary-{index}"):
            with pytest.raises(oidc.OIDCError) as caught:
                oidc.consume_flow(f"private-canary-{index}", "different-cookie")
            oidc_diagnostics.log_oidc_failure(caught.value)
    assert len(_terminals(records)) == 1 and len(observability._WARNING_STATE) == 1
    assert "private-canary" not in repr(observability._WARNING_STATE)
    now[0] += 60
    with app.test_request_context("/auth/oidc/callback"):
        with pytest.raises(oidc.OIDCError) as caught:
            oidc.consume_flow("private-canary-final", "different-cookie")
        oidc_diagnostics.log_oidc_failure(caught.value)
    assert len(_terminals(records)) == 2
    assert _terminals(records)[1].suppressed_repeat_count == 4
