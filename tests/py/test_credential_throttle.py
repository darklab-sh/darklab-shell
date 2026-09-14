# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Credential limits reject requests before storage or verifier work."""

import base64

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from identity_helpers import principal_identity
from services.auth import rate_limit, resolver


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
    yield
    rate_limit.reset_auth_rate_limits_for_tests()


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


@pytest.mark.parametrize("kind", ["portable", "pat", "redeem", "form"])
@pytest.mark.parametrize("limit_scope", ["lookup", "ip"])
def test_throttled_routes_skip_verification_even_for_correct_credentials(monkeypatch, kind, limit_scope):
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
            assert response.status_code == (200 if kind == "form" else 401)
        ip = "192.0.2.6"  # The lookup limit also applies from another IP.
    else:
        ip = "192.0.2.5"
        for _ in range(rate_limit.FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE):
            rate_limit.check_failed_redemption(ip, now=now[0])

    def unexpected_verification(*_args, **_kwargs):
        pytest.fail("A throttled request reached the credential database lookup")

    with monkeypatch.context() as patch:
        patch.setattr(resolver, "_resolve_credential", unexpected_verification)
        response = _attempt(client, kind, secret, ip)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "20"
    assert secret.encode() not in response.data
    now[0] += 60
    response = _attempt(client, kind, secret, ip)
    assert response.status_code == (302 if kind == "form" else 200)


def test_ip_limit_precedes_cookie_verification_and_can_be_disabled(monkeypatch):
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
    app.config["RATELIMIT_ENABLED"] = False
    assert client.get("/config", **kwargs).status_code == 200
