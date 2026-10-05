# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Rejected browser identities don't consume periodic workspace maintenance."""

from datetime import datetime, timedelta, timezone
import json
import logging
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from admin_helpers import operator_db as _cleanup_db
import app as shell
from core.database_access import get_db_connect
from core.logging_setup import GELFFormatter, _TextFormatter
from identity_helpers import anonymous_session_id, browser_identity_headers, principal_identity
from services.auth import browser_sessions, observability, resolver, storage
from services.workspace.files import ensure_session_workspace

cleanup_db = _cleanup_db


@pytest.fixture(params=["open", "token_required"])
def cleanup_app(cleanup_db, request, monkeypatch, tmp_path, caplog):
    cfg = cleanup_db.cfg.with_overrides({
        "access_profile": request.param, "rate_limit_enabled": False,
        "workspace_enabled": True, "workspace_root": str(tmp_path / "workspaces"),
        "workspace_inactivity_ttl_hours": 1,
    })
    monkeypatch.setattr(shell, "CFG", cfg)
    app = shell.create_app(cfg)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(shell, "time", SimpleNamespace(monotonic=lambda: clock.now, perf_counter=time.perf_counter))
    monkeypatch.setattr(shell, "_sqlite_wal_checkpoint_monotonic", lambda: clock.now)
    monkeypatch.setattr(shell, "_last_workspace_cleanup_monotonic", 0.0)
    monkeypatch.setattr(shell, "_last_sqlite_wal_checkpoint_monotonic", 0.0)
    monkeypatch.setattr(observability, "_WARNING_STATE", {})
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record)
    monkeypatch.setattr(shell.log, "handlers", [handler])
    caplog.set_level(logging.DEBUG, logger="shell")
    with app.app_context():
        identity = principal_identity("Cleanup browser")
        credential_id = resolver.public_lookup_id_from_headers(identity.browser_headers())
        session = browser_sessions.create_browser_session(
            principal_id=identity.principal_id, credential_id=credential_id, absolute_seconds=3600,
        )
    records.clear()
    return SimpleNamespace(app=app, cfg=cfg, clock=clock, records=records, session=session,
                           identity=identity, backend=cleanup_db.backend)


def _old_workspace(owner, cfg):
    path = ensure_session_workspace(owner, cfg)
    (path / "saved.txt").write_text("test-owned workspace", encoding="utf-8")
    os.utime(path, (1000, 1000))
    return path


def _render(records):
    return "\n".join(_TextFormatter().format(record) + GELFFormatter().format(record) for record in records)


@pytest.mark.parametrize("state,code", [
    ("idle", "idle_browser_session"), ("expired", "expired_browser_session"),
    ("revoked", "revoked_browser_session"), ("malformed", "malformed_browser_session"),
    ("parent_revoked", "revoked_browser_session"), ("disabled", "revoked_browser_session"),
])
def test_rejected_cookie_leaves_cleanup_due_and_public_probe_healthy(cleanup_app, monkeypatch, state, code):
    case = cleanup_app
    before = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with get_db_connect()() as conn:
        if state in {"idle", "expired", "revoked"}:
            if state == "expired":
                conn.execute("UPDATE browser_sessions SET created_at = ? WHERE id = ?",
                             ((datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), case.session.id))
            column = {"idle": "last_seen_at", "expired": "absolute_expires_at", "revoked": "revoked_at"}[state]
            conn.execute(f"UPDATE browser_sessions SET {column} = ? WHERE id = ?", (before, case.session.id))
        elif state == "parent_revoked":
            conn.execute("UPDATE credentials SET revoked_at = ? WHERE id = ?", (before, case.session.credential_id))
        elif state == "disabled":
            conn.execute("UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?",
                         (before, case.identity.principal_id))
        conn.commit()
    expired = _old_workspace(anonymous_session_id("cleanup-expired"), case.cfg)
    cleanup = Mock(wraps=shell.cleanup_inactive_workspaces)
    checkpoint = Mock(wraps=shell._maybe_checkpoint_sqlite_wal)
    resolve = Mock(wraps=resolver.resolve_authentication)
    monkeypatch.setattr(shell, "cleanup_inactive_workspaces", cleanup)
    monkeypatch.setattr(shell, "_maybe_checkpoint_sqlite_wal", checkpoint)
    monkeypatch.setattr(resolver, "resolve_authentication", resolve)
    client = case.app.test_client()
    cookie = "private-malformed-cookie-canary" if state == "malformed" else case.session.cookie_value
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, cookie)
    for now in (1000.0, 1301.0):
        case.clock.now = now
        assert client.get("/health?probe=private-query-canary").status_code == 200
        assert expired.exists()
        assert shell._last_workspace_cleanup_monotonic == 0
    cleanup.assert_not_called()
    assert checkpoint.call_count == 2
    assert shell._last_sqlite_wal_checkpoint_monotonic == (1301 if case.backend == "sqlite" else 0)
    assert resolve.call_count == 2  # One resolution per request, including maintenance.
    assert not any(record.levelno >= logging.WARNING for record in case.records)

    protected = client.get("/session/preferences")
    assert protected.status_code == 401
    assert protected.get_json()["error"] == code
    assert shell._last_workspace_cleanup_monotonic == 0
    warnings = [record for record in case.records if record.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].msg == "CREDENTIAL_AUTHENTICATION_REJECTED"
    assert warnings[0].levelno == logging.WARNING and warnings[0].exc_info is None
    assert json.loads(GELFFormatter().format(warnings[0]))["level"] == 4

    client.delete_cookie(browser_sessions.BROWSER_SESSION_COOKIE)
    assert client.get("/health").status_code == 200
    cleanup.assert_called_once_with(case.cfg, skip_session_id="")
    assert shell._last_workspace_cleanup_monotonic == 1301
    assert not expired.exists()
    rendered = _render(case.records)
    for secret in (cookie, case.session.csrf_token, case.identity.portable_secret, "private-query-canary"):
        assert secret not in rendered
    assert "WORKSPACE_CLEANUP_ERROR" not in rendered
    completed = [record for record in case.records if record.msg == "WORKSPACE_CLEANUP"]
    assert len(completed) == 1 and completed[0].removed == 1
    assert completed[0].levelno == logging.INFO and completed[0].exc_info is None
    assert json.loads(GELFFormatter().format(completed[0]))["level"] == 6


@pytest.mark.parametrize("kind", ["anonymous", "browser", "attached_browser", "missing"])
def test_cleanup_preserves_request_owner_and_obeys_interval(cleanup_app, monkeypatch, kind):
    case = cleanup_app
    client = case.app.test_client()
    owner = ""
    headers = {}
    if kind == "anonymous":
        owner = anonymous_session_id("cleanup-current")
        headers = browser_identity_headers(owner)
    elif kind == "browser":
        owner = case.identity.personal_workspace_id
        client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, case.session.cookie_value)
    elif kind == "attached_browser":
        with case.app.app_context():
            bundle = storage.create_principal_with_credential(anonymous_id=anonymous_session_id("cleanup-kept"))
            session = browser_sessions.create_browser_session(
                principal_id=bundle.principal.id, credential_id=bundle.credential.metadata.id, absolute_seconds=3600,
            )
        owner = bundle.workspace.id
        client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, session.cookie_value)
    with case.app.app_context():
        current = _old_workspace(owner, case.cfg) if owner else None
    if kind in {"anonymous", "attached_browser"}:
        assert current is not None and current.name.startswith("sess_")
    expired = _old_workspace(anonymous_session_id("cleanup-expired"), case.cfg)
    cleanup = Mock(wraps=shell.cleanup_inactive_workspaces)
    monkeypatch.setattr(shell, "cleanup_inactive_workspaces", cleanup)
    assert client.get("/health", headers=headers).status_code == 200
    cleanup.assert_called_once_with(case.cfg, skip_session_id=owner)
    assert not expired.exists()
    assert current is None or (current / "saved.txt").read_text() == "test-owned workspace"
    expired = _old_workspace(anonymous_session_id("cleanup-next"), case.cfg)
    case.clock.now = 1299
    assert client.get("/health", headers=headers).status_code == 200
    assert cleanup.call_count == 1 and expired.exists()
    case.clock.now = 1300
    assert client.get("/health", headers=headers).status_code == 200
    assert cleanup.call_count == 2 and not expired.exists()
    assert current is None or current.exists()


def test_real_cleanup_failure_keeps_error_traceback_and_bounded_retry(cleanup_app, monkeypatch):
    case = cleanup_app
    cleanup = Mock(side_effect=OSError("test cleanup I/O failure"))
    monkeypatch.setattr(shell, "cleanup_inactive_workspaces", cleanup)
    client = case.app.test_client()
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, case.session.cookie_value)
    for now, attempts in ((1000, 1), (1001, 1), (1299, 1), (1300, 2)):
        case.clock.now = now
        assert client.get("/health").status_code == 200
        assert cleanup.call_count == attempts
        assert shell._last_workspace_cleanup_monotonic == (1000 if attempts == 1 else 1300)
    failures = [record for record in case.records if record.levelno >= logging.WARNING]
    assert len(failures) == 2
    for record in failures:
        assert record.msg == "WORKSPACE_CLEANUP_ERROR"
        assert record.levelno == logging.ERROR and record.exc_info[0] is OSError
        payload = json.loads(GELFFormatter().format(record))
        assert payload["level"] == 3 and "OSError" in payload["full_message"]
    rendered = _render(failures)
    assert "Traceback" in rendered
    assert case.session.cookie_value not in rendered
    assert case.identity.portable_secret not in rendered


def test_disabled_cleanup_does_not_claim_interval_or_skip_checkpoint(cleanup_app, monkeypatch):
    case = cleanup_app
    disabled = case.cfg.with_overrides({"workspace_enabled": False})
    monkeypatch.setattr(shell, "CFG", disabled)
    case.app.config["DARKLAB_CONFIG"] = disabled
    cleanup = Mock(side_effect=AssertionError("disabled cleanup ran"))
    checkpoint = Mock(wraps=shell._maybe_checkpoint_sqlite_wal)
    monkeypatch.setattr(shell, "cleanup_inactive_workspaces", cleanup)
    monkeypatch.setattr(shell, "_maybe_checkpoint_sqlite_wal", checkpoint)
    assert case.app.test_client().get("/health").status_code == 200
    cleanup.assert_not_called()
    checkpoint.assert_called_once()
    assert shell._last_workspace_cleanup_monotonic == 0
    assert shell._last_sqlite_wal_checkpoint_monotonic == (1000 if case.backend == "sqlite" else 0)
