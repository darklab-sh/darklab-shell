# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Credential limits reject requests before storage or verifier work."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from types import SimpleNamespace

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import principal_identity
from services.auth import observability, rate_limit, resolver


class FakeRedis:
    def __init__(self):
        self.values = {}

    def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, _key, _seconds):
        return True

    def get(self, key):
        return self.values.get(key)


class UnavailableRedis:
    def get(self, _key):
        raise ConnectionError("test Redis unavailable")

    def incr(self, _key):
        raise ConnectionError("test Redis unavailable")


@pytest.fixture(autouse=True)
def reset_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "throttle.db")))
    rate_limit.reset_auth_rate_limits_for_tests()
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    yield
    rate_limit.reset_auth_rate_limits_for_tests()


@pytest.fixture
def warning_records(monkeypatch):
    records = []
    handler = logging.Handler()
    handler.setLevel(logging.WARNING)
    handler.emit = lambda record: records.append(record)
    logger = logging.Logger("auth-warning-test", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(observability, "log", logger)
    return records


@pytest.mark.parametrize("backend", ["local", "redis", "unavailable"])
def test_precheck_reads_both_limits_without_counting_successes(backend):
    redis = {"local": None, "redis": FakeRedis, "unavailable": UnavailableRedis}[backend]
    redis = redis() if redis is not None else None
    now = 1_000.0
    for _ in range(100):
        assert rate_limit.check_credential_redemption("192.0.2.1", "lookup", now=now, redis_client=redis).allowed
    for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE):
        rate_limit.check_failed_redemption("192.0.2.1", "lookup", now=now, redis_client=redis)
    assert not rate_limit.check_credential_redemption("192.0.2.2", "lookup", now=now, redis_client=redis).allowed
    assert rate_limit.check_credential_redemption("192.0.2.1", "different", now=now, redis_client=redis).allowed
    for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE):
        rate_limit.check_failed_redemption("192.0.2.3", now=now, redis_client=redis)
    denied = rate_limit.check_credential_redemption("192.0.2.3", "fresh", now=now, redis_client=redis)
    assert not denied.allowed and denied.retry_after == 20
    assert rate_limit.check_credential_redemption("192.0.2.3", now=now + 60, redis_client=redis).allowed
    assert rate_limit.check_credential_redemption("192.0.2.2", "lookup", now=now, enabled=False).allowed


def _attempt(client, kind, secret, ip="192.0.2.5"):
    kwargs = {"base_url": "https://localhost", "environ_overrides": {"REMOTE_ADDR": ip}}
    if kind.startswith("operator-"):
        path = {"operator-settings": "/admin/settings", "operator-diag": "/diag", "operator-audit": "/audit/export"}[kind]
        return client.get(path, headers={"X-Darklab-Credential": secret}, **kwargs)
    if kind == "portable":
        return client.get("/config", headers={"X-Darklab-Credential": secret}, **kwargs)
    if kind == "pat":
        return client.get("/api/v1/projects", headers={"Authorization": f"Bearer {secret}"}, **kwargs)
    if kind == "redeem":
        return client.post("/auth/credentials/redeem", json={"secret": secret}, **kwargs)
    client.get("/auth/sign-in", **kwargs)
    nonce = client.get_cookie("darklab_sign_in_nonce", path="/auth/sign-in")
    assert nonce is not None
    return client.post("/auth/sign-in", data={"credential": secret, "sign_in_nonce": nonce.value}, **kwargs)


@pytest.mark.parametrize("kind", ["portable", "pat", "redeem", "form", "operator-settings", "operator-diag", "operator-audit"])
@pytest.mark.parametrize("limit_scope", ["lookup", "ip"])
def test_throttled_routes_skip_verification_even_for_correct_credentials(monkeypatch, kind, limit_scope, warning_records):
    import core.process as process_state

    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    app.config["RATELIMIT_ENABLED"] = True
    monkeypatch.setattr(process_state, "redis_client", None)
    identity = principal_identity("throttle")
    secret = identity.pat_secret if kind == "pat" else identity.portable_secret
    # Keep the public lookup id intact and replace only the verifier input.
    parts = secret.split("_", 4)
    invalid = "_".join(parts[:4]) + "_" + base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode()
    assert resolver.public_lookup_id_from_headers({"X-Darklab-Credential": invalid})
    now = [1_000.0]
    monkeypatch.setattr(rate_limit.time, "time", lambda: now[0])
    client = app.test_client()
    if limit_scope == "lookup":
        for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE):
            response = _attempt(client, kind, invalid)
            assert response.status_code == (404 if kind.startswith("operator-") else 200 if kind == "form" else 401)
        ip = "192.0.2.6"  # The lookup limit also applies from another IP.
    else:
        ip = "192.0.2.5"
        for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE):
            if kind.startswith("operator-"):
                # Invalid values without a lookup id must fill the shared IP budget too.
                assert _attempt(client, kind, "malformed", ip).status_code == 404
            else:
                rate_limit.check_failed_redemption(ip, now=now[0])

    def unexpected_verification(*_args, **_kwargs):
        pytest.fail("A throttled request reached the credential database lookup")

    with monkeypatch.context() as patch:
        patch.setattr(resolver, "_resolve_credential", unexpected_verification)
        response = _attempt(client, kind, secret, ip)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "20"
    assert secret.encode() not in response.data
    warnings = [record for record in warning_records if record.msg == "CREDENTIAL_RATE_LIMITED"]
    assert len(warnings) == 1
    assert warnings[0].policy == f"failed_credential_{limit_scope}"
    assert warnings[0].http_status == 429 and warnings[0].retry_after == 20
    assert warnings[0].endpoint != "unknown" and warnings[0].request_id != "unknown"
    assert warnings[0].levelno == logging.WARNING
    assert secret not in GELFFormatter().format(warnings[0])
    if kind.startswith("operator-"):
        assert response.headers["Cache-Control"] == "private, no-store"
        # Operator failures also protect ordinary routes that use the same credential budget.
        assert _attempt(client, "portable", secret, ip).status_code == 429
    now[0] += 60
    response = _attempt(client, kind, secret, ip)
    assert response.status_code == (404 if kind.startswith("operator-") else 302 if kind == "form" else 200)


@pytest.mark.parametrize("profile", ["open", "token_required"])
@pytest.mark.parametrize("path", ["/admin/unknown", "/diag/unknown", "/audit/unknown"])
def test_operator_denials_consume_the_shared_http_budget(monkeypatch, profile, path):
    import app as application
    import core.process as process_state
    from core import http_rate_limit

    cfg = build_test_config({
        "access_profile": profile, "rate_limit_enabled": True,
        "http_rate_limit_per_minute": 2, "http_rate_limit_per_second": 0,
    })
    monkeypatch.setattr(application, "CFG", cfg)
    monkeypatch.setattr(process_state, "redis_client", None)
    monkeypatch.setattr(http_rate_limit, "_LOCAL_COUNTERS", {})
    clock = SimpleNamespace(time=lambda: 1_000.0)
    monkeypatch.setattr(http_rate_limit, "time", clock)
    app = application.create_app(cfg)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=True)
    client = app.test_client()
    for _ in range(2):
        response = client.get(path, base_url="https://localhost")
        assert response.status_code == 302
        assert "/auth/sign-in?next=" in response.headers["Location"]
    with monkeypatch.context() as patch:
        patch.setattr(
            resolver, "resolve_authentication", lambda *_args, **_kwargs: pytest.fail("Throttled request resolved identity")
        )
        denied = client.get(path, base_url="https://localhost")
        assert denied.status_code == 429
        assert denied.headers["Cache-Control"] == "private, no-store"
        assert client.get("/config", base_url="https://localhost").status_code == 429


def test_ip_limit_precedes_cookie_verification_and_can_be_disabled(monkeypatch, warning_records):
    import core.process as process_state
    from services.auth import browser_sessions

    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    app.config["RATELIMIT_ENABLED"] = True
    monkeypatch.setattr(process_state, "redis_client", None)
    identity = principal_identity("cookie throttle")
    client = app.test_client()
    assert _attempt(client, "form", identity.portable_secret).status_code == 302
    monkeypatch.setattr(rate_limit.time, "time", lambda: 1_000.0)
    for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE):
        rate_limit.check_failed_redemption("192.0.2.5")

    def unexpected_verification(*_args, **_kwargs):
        pytest.fail("A throttled request verified a browser session")

    kwargs = {"base_url": "https://localhost", "environ_overrides": {"REMOTE_ADDR": "192.0.2.5"}}
    with monkeypatch.context() as patch:
        patch.setattr(browser_sessions, "resolve_browser_session", unexpected_verification)
        response = client.get("/config", **kwargs)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "20"
    assert len(warning_records) == 1
    assert warning_records[0].policy == "failed_credential_ip"
    app.config["RATELIMIT_ENABLED"] = False
    assert client.get("/config", **kwargs).status_code == 200


@pytest.mark.parametrize("kind", ["portable", "pat", "redeem", "form"])
def test_failed_credentials_emit_one_safe_warning_per_reason(monkeypatch, kind, warning_records):
    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    app.config["RATELIMIT_ENABLED"] = False
    client = app.test_client()
    clock = [100.0]
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    secret = "private-submitted-credential-canary"
    response = None
    for _ in range(3):
        response = _attempt(client, kind, secret)
        assert response.status_code == (200 if kind == "form" else 401)
    assert response is not None
    assert len(warning_records) == 1
    first = warning_records[0]
    assert first.msg == "CREDENTIAL_AUTHENTICATION_REJECTED" and first.levelno == logging.WARNING
    assert first.reason == "malformed_credential"
    assert first.http_status == response.status_code
    assert set(_extra_fields(first)) == {
        "request_id", "endpoint", "reason", "http_status", "suppressed_repeat_count",
    }
    assert first.request_id != "unknown" and first.endpoint != "unknown"
    gelf = json.loads(GELFFormatter().format(first))
    assert gelf["_reason"] == first.reason and gelf["_http_status"] == response.status_code
    assert secret not in _TextFormatter().format(first) + json.dumps(gelf)
    clock[0] += 60
    _attempt(client, kind, secret)
    assert len(warning_records) == 2 and warning_records[1].suppressed_repeat_count == 2


@pytest.mark.parametrize("kind", ["portable", "pat", "redeem", "form"])
def test_post_verification_limit_rejection_is_logged(monkeypatch, kind, warning_records):
    import blueprints.auth as auth_routes
    import core.process as process_state

    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    app.config["RATELIMIT_ENABLED"] = True
    monkeypatch.setattr(process_state, "redis_client", None)
    monkeypatch.setattr(rate_limit.time, "time", lambda: 1_000.0)
    for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE):
        rate_limit.check_failed_redemption("192.0.2.5")
    # Another in-flight request can exhaust the bucket after the precheck.
    def allowed(*_args, **_kwargs):
        return rate_limit.CredentialRateLimitResult(True)
    monkeypatch.setattr(rate_limit, "check_credential_redemption", allowed)
    monkeypatch.setattr(auth_routes, "check_credential_redemption", allowed)
    response = _attempt(app.test_client(), kind, "private-malformed-credential")
    assert response.status_code == 429
    assert len(warning_records) == 1
    assert warning_records[0].msg == "CREDENTIAL_RATE_LIMITED"
    assert warning_records[0].policy == "failed_credential_ip"


def test_anonymous_issuance_limit_is_logged_without_identity(monkeypatch, warning_records):
    import core.process as process_state
    from identity_helpers import anonymous_session_id

    app = make_test_app()
    app.config["RATELIMIT_ENABLED"] = True
    monkeypatch.setattr(process_state, "redis_client", None)
    for _ in range(rate_limit.ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR):
        rate_limit.check_anonymous_issuance("192.0.2.20")
    anonymous = anonymous_session_id("limited issuance")
    response = app.test_client().post(
        "/auth/principals", json={"label": "private-label-canary"},
        headers={"X-Darklab-Anonymous-ID": anonymous}, environ_overrides={"REMOTE_ADDR": "192.0.2.20"},
    )
    assert response.status_code == 429
    assert len(warning_records) == 1 and warning_records[0].policy == "anonymous_issuance_ip"
    assert anonymous not in GELFFormatter().format(warning_records[0])
    assert "private-label-canary" not in GELFFormatter().format(warning_records[0])


def test_warning_sampling_is_thread_safe_bounded_and_deduplicates_request_boundaries(monkeypatch, warning_records):
    clock = [100.0]
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: observability.log_authentication_rejected("revoked_credential"), range(100)))
    assert len(warning_records) == 1
    clock[0] += 60
    observability.log_authentication_rejected("revoked_credential")
    assert warning_records[-1].suppressed_repeat_count == 99
    for n in range(100):
        observability.log_authentication_rejected(f"untrusted-submitted-reason-{n}")
    assert len(observability._WARNING_STATE) == 2
    assert "untrusted" not in "".join(GELFFormatter().format(record) for record in warning_records)
    app = make_test_app()
    with app.test_request_context("/config?private-query-canary"):
        observability.log_authentication_rejected("unknown_browser_session")
        observability.log_authentication_rejected("unknown_browser_session")
    clock[0] += 60
    observability.log_authentication_rejected("unknown_browser_session")
    assert warning_records[-1].suppressed_repeat_count == 0
