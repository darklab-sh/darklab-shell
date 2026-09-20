# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from admin_helpers import operator_db as _operator_db
from core.database_access import get_db_connect
from services.auth import operator_access, operator_grants
from services.auth.contracts import IdentityStorageError, timestamp
from test_operator_reauthentication import ORIGIN, credential_setup

operator_db = _operator_db
PATHS = ("/diag", "/diag?format=json", "/diag/audit", "/diag/audit?format=json",
         "/diag/audit/export", "/diag/audit/export?format=json", "/diag/classifier-inspector",
         "/diag/classifier-drift", "/diag/ai-test", "/admin/", "/admin/settings", "/admin/access")


def request(client, path, **kwargs):
    call = client.post if path == "/diag/ai-test" else client.get
    return call(path, base_url=ORIGIN, **kwargs)


@pytest.mark.parametrize("path", PATHS)
def test_every_operator_route_denies_network_only_access(operator_db, monkeypatch, path):
    app, client, bundle, _issued = credential_setup(operator_db, monkeypatch)
    app.config["DARKLAB_CONFIG"] = app.config["DARKLAB_CONFIG"].with_overrides({"metrics_allowed_cidrs": ["127.0.0.0/8"]})
    operator_grants.set_grant(bundle.principal.id, granted=False)
    response = request(client, path)
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("path", PATHS)
def test_every_operator_route_is_unavailable_in_open_profile(operator_db, monkeypatch, path):
    app, client, _bundle, _issued = credential_setup(operator_db, monkeypatch)
    app.config["DARKLAB_CONFIG"] = app.config["DARKLAB_CONFIG"].with_overrides({"access_profile": "open"})
    assert request(client, path).status_code == 404


@pytest.mark.parametrize("path", [p for p in PATHS if p != "/diag/ai-test"])
def test_verified_operator_needs_no_metrics_allowlist(operator_db, monkeypatch, path):
    app, client, _bundle, _issued = credential_setup(operator_db, monkeypatch)
    app.config["DARKLAB_CONFIG"] = app.config["DARKLAB_CONFIG"].with_overrides({
        "metrics_allowed_cidrs": [], "metrics_enabled": False,
    })
    response = request(client, path, environ_overrides={"REMOTE_ADDR": "198.51.100.17"})
    assert response.status_code == (204 if path == "/admin/access" else 200)
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Pragma"] == "no-cache"
    response.get_data()


@pytest.mark.parametrize("path", [
    "/diag?format=json", "/diag/classifier-drift", "/diag/audit?format=json&event_type=project.link",
])
def test_expired_verification_returns_json_with_safe_document_destination(operator_db, monkeypatch, path):
    _app, client, _bundle, issued = credential_setup(operator_db, monkeypatch)
    with get_db_connect()() as conn:
        conn.execute("UPDATE browser_sessions SET authenticated_at = ? WHERE id = ?",
                     (timestamp(datetime.now(timezone.utc) - timedelta(hours=1)), issued.id))
        conn.commit()
    response = request(client, path)
    assert response.status_code == 401 and response.is_json
    payload = response.get_json()
    assert payload["error"] == "reauthentication_required"
    destination = urlsplit(payload["destination"])
    assert destination.path == "/admin/reauth"
    next_path = parse_qs(destination.query)["next"][0]
    assert next_path == ("/diag/audit?event_type=project.link" if "/audit" in path else "/diag")


def test_storage_failure_hides_operator_data(operator_db, monkeypatch):
    _app, client, _bundle, _issued = credential_setup(operator_db, monkeypatch)
    def fail(_principal):
        raise IdentityStorageError("PRIVATE_STORAGE_DETAILS")
    monkeypatch.setattr(operator_access, "has_grant", fail)
    response = request(client, "/diag?format=json")
    assert response.status_code == 503
    assert response.get_json() == {"error": "operator_access_unavailable"}
    assert b"PRIVATE" not in response.data


@pytest.mark.parametrize("format", ["csv", "json"])
def test_export_stops_after_grant_revocation_and_never_logs_completion(operator_db, monkeypatch, caplog, format):
    import blueprints.assets as assets
    caplog.set_level("INFO", logger="shell")
    _app, client, bundle, _issued = credential_setup(operator_db, monkeypatch)
    def pages(*args, **kwargs):
        yield {"events": [{"id": "first-safe-row"}], "truncated": False}
        operator_grants.set_grant(bundle.principal.id, granted=False)
        yield {"events": [{"id": "must-not-escape"}], "truncated": False}
    monkeypatch.setattr(assets, "iter_event_pages", pages)
    response = request(client, "/diag/audit/export?format=" + format, buffered=False)
    emitted = []
    with pytest.raises(operator_access.OperatorAccessLost):
        for chunk in response.response:
            emitted.append(chunk)
    assert b"first-safe-row" in b"".join(emitted)
    assert b"must-not-escape" not in b"".join(emitted)
    assert not any(record.message == "DIAG_AUDIT_EXPORTED" for record in caplog.records)
    interrupted = [record for record in caplog.records if record.message == "DIAG_AUDIT_EXPORT_INTERRUPTED"]
    assert len(interrupted) == 1 and interrupted[0].principal_id == bundle.principal.id
    assert interrupted[0].format == format and interrupted[0].reason == "access_lost"


def test_ai_probe_requires_csrf_and_current_grant(operator_db, monkeypatch):
    from blueprints import assets
    _app, client, bundle, issued = credential_setup(operator_db, monkeypatch)
    calls = []
    monkeypatch.setattr(assets, "ai_run_test_prompt", lambda: calls.append(1))
    assert request(client, "/diag/ai-test").status_code == 403
    operator_grants.set_grant(bundle.principal.id, granted=False)
    assert request(client, "/diag/ai-test", headers={"X-Darklab-CSRF": issued.csrf_token}).status_code == 404
    assert calls == []


def test_operator_probe_limit_is_shared_by_identity_and_fails_closed(monkeypatch):
    from core import process
    from services.ai.coordination import AICoordinationUnavailable, check_operator_test_rate_limit
    from conftest import build_test_config
    cfg = build_test_config({"ai_rate_limit_global_per_minute": 2})
    redis = process._FakeRedisClient()
    assert check_operator_test_rate_limit("operator-one", cfg=cfg, redis_client=redis).allowed
    assert not check_operator_test_rate_limit("operator-one", cfg=cfg, redis_client=redis).allowed
    assert check_operator_test_rate_limit("operator-two", cfg=cfg, redis_client=redis).allowed
    denied = check_operator_test_rate_limit("operator-three", cfg=cfg, redis_client=redis)
    assert not denied.allowed and "busy" in denied.message
    def unavailable(*args, **kwargs):
        raise ConnectionError("private")
    monkeypatch.setattr(redis, "set", unavailable)
    with pytest.raises(AICoordinationUnavailable, match="AI coordination is unavailable"):
        check_operator_test_rate_limit("operator-four", cfg=cfg, redis_client=redis)


def test_metrics_scrapes_are_independent_of_operator_identity(operator_db, monkeypatch):
    import config
    from services.auth.browser_sessions import BROWSER_SESSION_COOKIE
    from services import metrics
    _app, client, _bundle, _issued = credential_setup(operator_db, monkeypatch)
    monkeypatch.setattr(metrics, "render_latest_metrics", lambda: b"# independent scrape\n")
    monkeypatch.setitem(config.CFG, "metrics_allowed_cidrs", [])
    monkeypatch.setitem(config.CFG, "metrics_enabled", True)
    assert request(client, "/diag?format=json").status_code == 200
    assert request(client, "/metrics").status_code == 404
    client.delete_cookie(BROWSER_SESSION_COOKIE, domain="shell.example")
    monkeypatch.setitem(config.CFG, "metrics_allowed_cidrs", ["198.51.100.0/24"])
    monkeypatch.setitem(config.CFG, "trusted_proxy_cidrs", ["127.0.0.1/32"])
    response = request(client, "/metrics", headers={"X-Forwarded-For": "198.51.100.10"})
    assert response.status_code == 200 and response.data == b"# independent scrape\n"
    monkeypatch.setitem(config.CFG, "trusted_proxy_cidrs", [])
    assert request(client, "/metrics", headers={"X-Forwarded-For": "198.51.100.10"}).status_code == 404


@pytest.mark.parametrize("value,expected", [
    ("https://elsewhere.test/diag/audit", "/admin/"),
    ("//elsewhere.test/diag", "/admin/"),
    ("/diag/ai-test?prompt=PRIVATE", "/diag"),
    ("/diag/classifier-inspector?classifier_line=PRIVATE", "/diag"),
    ("/diag/audit/export?format=json&actor=Example&offset=50&next=https://elsewhere.test", "/diag/audit?actor=Example&offset=50"),
])
def test_operator_return_paths_never_replay_probes_or_leave_site(value, expected):
    assert operator_access.return_path(value) == expected
