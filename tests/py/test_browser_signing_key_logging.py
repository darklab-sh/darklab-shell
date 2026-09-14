# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Signing-key faults remain distinct from ordinary invalid browser cookies."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from core.database_access import get_db_connect
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import principal_identity
from services.auth import browser_sessions, observability
from services.auth.resolver import public_lookup_id_from_headers
from services.secrets.vault import encrypt_secret


@pytest.fixture
def signing_context(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "signing.db")))
    monkeypatch.setattr(observability, "_SIGNING_KEY_ERROR_STATE", {})
    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
    app.config["RATELIMIT_ENABLED"] = False
    identity = principal_identity("signing-key diagnostics")
    issued = browser_sessions.create_browser_session(
        principal_id=identity.principal_id,
        credential_id=public_lookup_id_from_headers(identity.browser_headers()), absolute_seconds=3600,
    )
    client = app.test_client()
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, issued.cookie_value, secure=True)
    assert client.get("/projects", base_url="https://localhost").status_code == 200
    records = []
    handler = logging.Handler()
    handler.setLevel(logging.ERROR)
    handler.emit = records.append
    logger = logging.Logger("signing-key-test", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(observability, "log", logger)
    return SimpleNamespace(client=client, identity=identity, issued=issued, records=records)


@pytest.mark.parametrize("fault,reason", [
    ("missing", "missing_key"),
    ("wrapper", "unsupported_wrapper"),
    ("ciphertext", "decryption_failed"),
    ("encoding", "invalid_key"),
    ("length", "invalid_key"),
])
def test_stored_signing_fault_is_coalesced_and_keeps_the_generic_client_response(signing_context, monkeypatch, fault, reason):
    ctx = signing_context
    clock = [100.0]
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    version = ctx.issued.signing_key_version
    private_values = [
        ctx.issued.id, ctx.issued.cookie_value, ctx.issued.csrf_token,
        ctx.identity.principal_id, ctx.identity.portable_secret,
    ]
    with get_db_connect()() as conn:
        if fault == "missing":
            # Model an inconsistent restore that left a session without its key.
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM browser_session_signing_keys WHERE version = ?", (version,))
        elif fault == "wrapper":
            conn.execute("PRAGMA ignore_check_constraints = ON")
            conn.execute("UPDATE browser_session_signing_keys SET wrap_algorithm = ?", ("private-unsupported-wrapper",))
        elif fault == "ciphertext":
            conn.execute("UPDATE browser_session_signing_keys SET wrapped_key = ?", (b"private-corrupt-key-canary" * 3,))
        else:
            plaintext = "private-invalid-key-canary" * 3 if fault == "encoding" else base64.b64encode(b"x" * 31).decode()
            wrapped, nonce = encrypt_secret(plaintext, associated_data=browser_sessions._associated_data(version))
            private_values.extend([plaintext, wrapped.hex(), nonce.hex()])
            conn.execute("UPDATE browser_session_signing_keys SET wrapped_key = ?, wrap_nonce = ?", (wrapped, nonce))
        conn.commit()
    for _ in range(3):
        response = ctx.client.get("/projects", base_url="https://localhost")
        assert response.status_code == 401
        assert response.get_json()["error"] == "unknown_browser_session"
        assert "key" not in response.get_json()["message"]
    assert len(ctx.records) == 1
    record = ctx.records[0]
    assert record.msg == "BROWSER_SESSION_SIGNING_KEY_UNAVAILABLE" and record.levelno == logging.ERROR
    assert record.key_version == version and record.reason == reason
    assert record.error_type == "BrowserSessionSigningKeyError"
    assert set(_extra_fields(record)) == {"key_version", "reason", "error_type", "suppressed_repeat_count"}
    assert record.exc_info and record.exc_info[1].__suppress_context__
    gelf = json.loads(GELFFormatter().format(record))
    assert gelf["_key_version"] == version and gelf["_reason"] == reason
    rendered = _TextFormatter().format(record) + json.dumps(gelf)
    assert "browser_sessions.py:load_signing_key:" in rendered
    for private in private_values + ["private-corrupt-key-canary", "private-unsupported-wrapper"]:
        assert private not in rendered
    clock[0] += 60
    assert ctx.client.get("/projects", base_url="https://localhost").status_code == 401
    assert len(ctx.records) == 2 and ctx.records[-1].suppressed_repeat_count == 2


def test_decryption_exception_chain_is_private_and_repaired_key_works(signing_context, monkeypatch):
    ctx = signing_context

    def broken_decryption(*_args, **_kwargs):
        try:
            raise ValueError("private-decryption-cause")
        except ValueError as cause:
            raise RuntimeError("private-decryption-message") from cause

    with monkeypatch.context() as patch:
        patch.setattr(browser_sessions, "decrypt_secret", broken_decryption)
        assert ctx.client.get("/projects", base_url="https://localhost").status_code == 401
    assert len(ctx.records) == 1 and ctx.records[0].reason == "decryption_failed"
    rendered = _TextFormatter().format(ctx.records[0]) + GELFFormatter().format(ctx.records[0])
    assert "private-decryption" not in rendered and "raise BrowserSessionSigningKeyError" not in rendered
    assert ctx.client.get("/projects", base_url="https://localhost").status_code == 200
    assert len(ctx.records) == 1


@pytest.mark.parametrize("case", ["malformed", "unknown_session", "wrong_versions", "wrong_signature"])
def test_invalid_cookies_do_not_create_signing_key_incident_state(signing_context, monkeypatch, case):
    ctx = signing_context
    load = Mock(wraps=browser_sessions.load_signing_key)
    monkeypatch.setattr(browser_sessions, "load_signing_key", load)
    version = ctx.issued.signing_key_version
    if case == "malformed":
        cookies = ["private-malformed-cookie"]
    elif case == "unknown_session":
        cookies = [f"dlbs_v1_bws_{'0' * 32}_{version}_{'x' * 43}"]
    elif case == "wrong_versions":
        cookies = [f"dlbs_v1_{ctx.issued.id}_{version + index}_{'x' * 43}" for index in range(1, 101)]
    else:
        cookies = [f"dlbs_v1_{ctx.issued.id}_{version}_{'x' * 43}"]
    for cookie in cookies:
        result = browser_sessions.resolve_browser_session(cookie, idle_seconds=1800)
        assert not result.valid
    assert load.call_count == (1 if case == "wrong_signature" else 0)
    assert ctx.records == [] and observability._SIGNING_KEY_ERROR_STATE == {}


def test_signing_key_incident_sampling_is_thread_safe_and_bounded(signing_context, monkeypatch):
    ctx = signing_context
    clock = [100.0]
    monkeypatch.setattr(observability, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    exc = browser_sessions.BrowserSessionSigningKeyError("missing_key", "private-key-failure")

    def emit(_index):
        observability.log_browser_signing_key_unavailable(1, exc, reason="missing_key")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(emit, range(100)))
    assert len(ctx.records) == 1
    clock[0] += 60
    emit(0)
    assert ctx.records[-1].suppressed_repeat_count == 99
    observability.log_browser_signing_key_unavailable(2, exc, reason="missing_key")
    assert ctx.records[-1].key_version == 2
    observability.log_browser_signing_key_unavailable(2, exc, reason="decryption_failed")
    assert ctx.records[-1].reason == "decryption_failed"
    for version in range(3, 103):
        observability.log_browser_signing_key_unavailable(version, exc, reason="private-untrusted-reason")
    assert len(observability._SIGNING_KEY_ERROR_STATE) == observability._SIGNING_KEY_ERROR_MAX_KEYS
    assert ctx.records[-1].reason == "invalid_key"
    assert "private-" not in "".join(GELFFormatter().format(record) for record in ctx.records)
