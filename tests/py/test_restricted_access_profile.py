# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import importlib.util
import os
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Protocol

import pytest
from conftest import build_test_config
from core.database_access import get_db_connect
from core.database_backend import DatabaseBackend
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations
from services.auth import lifecycle, storage
from services.auth.access_profile import RESTRICTED_PUBLIC_ENDPOINTS
from services.auth.browser_sessions import (
    BROWSER_CSRF_COOKIE,
    BROWSER_SESSION_COOKIE,
    create_browser_session,
    resolve_browser_session,
    rotate_signing_key,
    verify_csrf_token,
)
from services.auth.resolver import (
    AuthenticatedContext,
    AuthenticationState,
    resolve_authentication,
)
from services.secrets.vault import reset_master_key_cache_for_tests
from services.workspace.models import WorkspaceSettings


def _settings(tmp_path) -> WorkspaceSettings:
    root = tmp_path / "restricted-workspaces"
    root.mkdir(exist_ok=True)
    return WorkspaceSettings(True, "volume", root, 1024, 1024, 10, 1)


def _cookie_headers(response) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in response.headers.getlist("Set-Cookie"):
        cookie = SimpleCookie()
        cookie.load(value)
        parsed.update({name: morsel.value for name, morsel in cookie.items()})
    return parsed


class _Cookie(Protocol):
    value: str


class _CookieClient(Protocol):
    def get_cookie(self, key: str, domain: str = "localhost") -> _Cookie | None: ...


def _cookie_value(client: _CookieClient, name: str) -> str:
    cookie = client.get_cookie(name, domain="localhost")
    assert cookie is not None
    return cookie.value


@dataclass(frozen=True)
class _BootstrapCredential:
    secret: str


@dataclass(frozen=True)
class _BootstrapBundle:
    credential: _BootstrapCredential

    def to_safe_dict(self) -> dict[str, object]:
        return {"principal": {"id": "prn_test"}}


def test_access_profile_config_defaults_and_reserves_future_profiles():
    assert build_test_config()["access_profile"] == "open"
    assert build_test_config({"access_profile": "token_required"})["access_profile"] == "token_required"
    for reserved in ("oidc_required", "mixed"):
        with pytest.raises(RuntimeError, match="reserved"):
            build_test_config({"access_profile": reserved})
    with pytest.raises(RuntimeError, match="access_profile"):
        build_test_config({"access_profile": "unknown"})


def test_restricted_public_route_allowlist_is_an_explicit_complete_inventory():
    from conftest import make_test_app

    app = make_test_app()
    actual = {
        (
            rule.endpoint,
            rule.rule,
            tuple(sorted(set(rule.methods or ()) - {"HEAD", "OPTIONS"})),
        )
        for rule in app.url_map.iter_rules()
        if rule.endpoint in RESTRICTED_PUBLIC_ENDPOINTS
    }
    assert actual == {
        ("auth.redeem", "/auth/credentials/redeem", ("POST",)),
        ("auth.sign_in", "/auth/sign-in", ("GET", "POST")),
        ("assets.favicon", "/favicon.ico", ("GET",)),
        ("assets.health", "/health", ("GET",)),
        ("assets.metrics", "/metrics", ("GET",)),
        ("assets.static_build_asset", "/static/build/<path:filename>", ("GET",)),
        ("assets.status", "/status", ("GET",)),
        ("assets.vendor_ansi_up_js", "/vendor/ansi_up.js", ("GET",)),
        ("assets.vendor_fonts", "/vendor/fonts/<path:filename>", ("GET",)),
        ("assets.vendor_jspdf_js", "/vendor/jspdf.umd.min.js", ("GET",)),
        ("assets.vendor_xterm_css", "/vendor/xterm.css", ("GET",)),
        ("assets.vendor_xterm_fit_js", "/vendor/xterm-addon-fit.js", ("GET",)),
        ("assets.vendor_xterm_js", "/vendor/xterm.js", ("GET",)),
        ("static", "/static/<path:filename>", ("GET",)),
    }


def test_browser_sessions_survive_restart_key_rotation_and_enforce_both_expiries(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_master_key_cache_for_tests()
    path = tmp_path / "restricted.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    now = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    with connect() as conn:
        run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
        bundle = storage.create_principal_with_credential(
            settings=_settings(tmp_path),
            conn=conn,
        )
        issued = create_browser_session(
            principal_id=bundle.principal.id,
            credential_id=bundle.credential.metadata.id,
            absolute_seconds=3600,
            now=now,
            conn=conn,
        )
        conn.commit()

    # A new connection models another worker or a restarted web process.
    resolved = resolve_authentication(
        {},
        cookies={BROWSER_SESSION_COOKIE: issued.cookie_value},
        browser_session_idle_seconds=1800,
        touch_last_used=False,
        now=now + timedelta(minutes=5),
        connect=connect,
    )
    assert resolved.state == AuthenticationState.VALID
    assert isinstance(resolved.context, AuthenticatedContext)
    assert resolved.context.authentication_method == "browser_cookie"
    assert resolved.context.browser_session_id == issued.id
    assert verify_csrf_token(issued.id, issued.csrf_token, connect=connect) is True
    assert verify_csrf_token(issued.id, "x" * 43, connect=connect) is False

    assert rotate_signing_key(connect=connect) == 2
    assert resolve_browser_session(
        issued.cookie_value,
        idle_seconds=1800,
        touch=False,
        now=now + timedelta(minutes=10),
        connect=connect,
    ).valid is True
    assert resolve_browser_session(
        issued.cookie_value,
        idle_seconds=1800,
        touch=False,
        now=now + timedelta(minutes=31),
        connect=connect,
    ).error_code == "idle_browser_session"
    assert resolve_browser_session(
        issued.cookie_value,
        idle_seconds=7200,
        touch=False,
        now=now + timedelta(hours=1),
        connect=connect,
    ).error_code == "expired_browser_session"
    reset_master_key_cache_for_tests()


def test_restricted_mode_sign_in_cookie_csrf_logout_and_fail_closed_gate(
    tmp_path,
    monkeypatch,
):
    import config as shell_config
    from core import database as shell_database

    import app as application_module

    restricted = build_test_config({
        "access_profile": "token_required",
        "restricted_public_shares_enabled": False,
        "asset_bundle_mode": "source",
    })
    monkeypatch.setattr(shell_config, "CFG", restricted)
    monkeypatch.setattr(application_module, "CFG", restricted)
    shell_database.db_init()
    reset_master_key_cache_for_tests()
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(
            settings=_settings(tmp_path),
            conn=conn,
        )
        conn.commit()

    app = application_module.create_app(restricted)
    app.config["TESTING"] = True
    app.config["RATELIMIT_ENABLED"] = False
    client = app.test_client()
    origin = "https://localhost"

    root = client.get("/", base_url=origin)
    assert root.status_code == 302
    assert "/auth/sign-in" in root.headers["Location"]
    assert client.get("/config", base_url=origin).status_code == 401
    assert client.get("/health", base_url=origin).status_code == 200
    disabled_share = client.post(
        "/share",
        base_url=origin,
        headers={"X-Darklab-Credential": bundle.credential.secret},
        json={"label": "Restricted share", "content": ["restricted share line"]},
    )
    assert disabled_share.status_code == 403
    restricted["restricted_public_shares_enabled"] = True
    created_share = client.post(
        "/share",
        base_url=origin,
        headers={"X-Darklab-Credential": bundle.credential.secret},
        json={"label": "Restricted share", "content": ["restricted share line"]},
    )
    assert created_share.status_code == 200
    share_path = created_share.get_json()["url"]
    restricted["restricted_public_shares_enabled"] = False
    assert client.get(share_path, base_url=origin).status_code == 404
    restricted["restricted_public_shares_enabled"] = True
    assert client.get(share_path, base_url=origin).status_code == 200
    restricted["restricted_public_shares_enabled"] = False
    anonymous_issue = client.post(
        "/auth/principals",
        base_url=origin,
        headers={"X-Darklab-Anonymous-ID": "59d67a8d-e960-4353-9fab-739597f1d262"},
        json={},
    )
    assert anonymous_issue.status_code == 401

    sign_in = client.get("/auth/sign-in", base_url=origin)
    assert sign_in.status_code == 200
    assert b"restricted-credential" in sign_in.data
    assert b"shell_bootstrap" not in sign_in.data
    cookies = _cookie_headers(sign_in)
    nonce = cookies["darklab_sign_in_nonce"]
    authenticated = client.post(
        "/auth/sign-in",
        base_url=origin,
        data={
            "credential": bundle.credential.secret,
            "sign_in_nonce": nonce,
            "next": "/",
        },
    )
    assert authenticated.status_code == 302
    assert bundle.credential.secret.encode() not in authenticated.data
    set_cookies = authenticated.headers.getlist("Set-Cookie")
    session_cookie = next(item for item in set_cookies if item.startswith(BROWSER_SESSION_COOKIE + "="))
    assert "Secure" in session_cookie
    assert "HttpOnly" in session_cookie
    assert "SameSite=Strict" in session_cookie
    csrf_cookie = next(item for item in set_cookies if item.startswith(BROWSER_CSRF_COOKIE + "="))
    assert "HttpOnly" not in csrf_cookie

    principal = client.get("/auth/principal", base_url=origin)
    assert principal.status_code == 200
    assert principal.get_json()["authentication"]["browser_session"] is True
    reauthentication_page = client.get("/auth/sign-in", base_url=origin)
    reauthentication_nonce = _cookie_headers(reauthentication_page)["darklab_sign_in_nonce"]
    assert client.post(
        "/auth/sign-in",
        base_url=origin,
        data={
            "credential": bundle.credential.secret,
            "sign_in_nonce": reauthentication_nonce,
            "next": "/",
        },
    ).status_code == 302
    old_session_cookie = _cookie_value(client, BROWSER_SESSION_COOKIE)
    with get_db_connect()() as conn:
        old_session_id = conn.execute(
            "SELECT id FROM browser_sessions WHERE principal_id = ? AND revoked_at IS NULL",
            (bundle.principal.id,),
        ).fetchone()[0]
    assert client.post("/auth/sessions/revoke-all", base_url=origin).status_code == 403
    csrf = _cookie_value(client, BROWSER_CSRF_COOKIE)
    created_team = client.post(
        "/session/teams",
        base_url=origin,
        headers={"X-Darklab-CSRF": csrf},
        json={"name": "Restricted operators", "display_name": "Operator"},
    )
    assert created_team.status_code == 201
    assert _cookie_value(client, BROWSER_SESSION_COOKIE) != old_session_cookie
    assert resolve_browser_session(
        old_session_cookie,
        idle_seconds=1800,
        touch=False,
    ).error_code == "revoked_browser_session"
    with get_db_connect()() as conn:
        reason = conn.execute(
            "SELECT revocation_reason FROM browser_sessions WHERE id = ?",
            (old_session_id,),
        ).fetchone()[0]
    assert reason == "session rotation"

    csrf = _cookie_value(client, BROWSER_CSRF_COOKIE)
    logged_out = client.post(
        "/auth/logout",
        base_url=origin,
        headers={"X-Darklab-CSRF": csrf},
    )
    assert logged_out.status_code == 204
    assert client.get("/", base_url=origin).status_code == 302

    sign_in = client.get("/auth/sign-in", base_url=origin)
    nonce = _cookie_headers(sign_in)["darklab_sign_in_nonce"]
    assert client.post(
        "/auth/sign-in",
        base_url=origin,
        data={
            "credential": bundle.credential.secret,
            "sign_in_nonce": nonce,
            "next": "/",
        },
    ).status_code == 302
    csrf = _cookie_value(client, BROWSER_CSRF_COOKIE)
    revoked = client.post(
        "/auth/sessions/revoke-all",
        base_url=origin,
        headers={"X-Darklab-CSRF": csrf},
    )
    assert revoked.status_code == 200
    assert revoked.get_json()["revoked_sessions"] >= 1
    assert client.get("/", base_url=origin).status_code == 302


def test_operator_bootstrap_is_one_time_and_writes_only_an_owner_file(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_master_key_cache_for_tests()
    path = tmp_path / "bootstrap.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    with connect() as conn:
        run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
    with pytest.raises(RuntimeError, match="credential sink failed"):
        lifecycle.operator_bootstrap(
            settings=_settings(tmp_path),
            credential_sink=lambda _secret: (_ for _ in ()).throw(
                RuntimeError("credential sink failed")
            ),
            connect=connect,
        )
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM principals").fetchone()[0] == 0
    bundle = lifecycle.operator_bootstrap(
        credential_label="Initial restricted operator",
        settings=_settings(tmp_path),
        connect=connect,
    )
    assert bundle.credential.secret.startswith("dlc_v1_crd_")
    with pytest.raises(ValueError, match="only before the first principal"):
        lifecycle.operator_bootstrap(settings=_settings(tmp_path), connect=connect)

    script_path = Path(__file__).resolve().parents[2] / "scripts" / "operations" / "manage_principal_access.py"
    spec = importlib.util.spec_from_file_location("restricted_bootstrap_command_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    destination = tmp_path / "bootstrap-credential.txt"
    command_bundle = _BootstrapBundle(
        credential=_BootstrapCredential(secret="one-time-bootstrap-secret"),
    )
    monkeypatch.setattr(
        module,
        "CFG",
        build_test_config({"access_profile": "token_required"}),
    )
    monkeypatch.setattr(module, "init_database", lambda: None)
    def command_bootstrap(**kwargs):
        kwargs["credential_sink"](command_bundle.credential.secret)
        return command_bundle

    monkeypatch.setattr(module.lifecycle, "operator_bootstrap", command_bootstrap)
    args = module._parser().parse_args(["bootstrap", "--secret-file", str(destination)])
    payload = module.run(args)
    assert destination.read_text(encoding="utf-8") == "one-time-bootstrap-secret\n"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert payload == {
        "principal": {"id": "prn_test"},
        "secret_file": str(destination),
    }
    assert os.path.islink(destination) is False

    failed_destination = tmp_path / "failed-bootstrap-credential.txt"

    def failed_bootstrap(**kwargs):
        kwargs["credential_sink"]("credential-from-failed-transaction")
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(module.lifecycle, "operator_bootstrap", failed_bootstrap)
    failed_args = module._parser().parse_args([
        "bootstrap",
        "--secret-file",
        str(failed_destination),
    ])
    with pytest.raises(RuntimeError, match="database commit failed"):
        module.run(failed_args)
    assert not failed_destination.exists()
    reset_master_key_cache_for_tests()


def test_open_mode_keeps_anonymous_identity_and_does_not_issue_browser_cookies(
    anonymous_identity_factory,
):
    from conftest import make_test_app

    client = make_test_app().test_client()
    anonymous = anonymous_identity_factory("restricted-open-mode")
    client.set_cookie(BROWSER_SESSION_COOKIE, "stale-restricted-session")
    config_response = client.get("/config", headers=anonymous.headers)
    assert config_response.status_code == 200
    assert config_response.get_json()["access_profile"] == "open"
    upgraded = client.post("/auth/principals", headers=anonymous.headers, json={})
    assert upgraded.status_code == 201
    redeemed = client.post(
        "/auth/credentials/redeem",
        json={"secret": upgraded.get_json()["secret"]},
    )
    assert redeemed.status_code == 200
    assert not any(
        header.startswith(BROWSER_SESSION_COOKIE + "=")
        for header in redeemed.headers.getlist("Set-Cookie")
    )
