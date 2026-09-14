# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Authentication diagnostics describe cached outcomes without another lookup."""

import json
import logging
from unittest.mock import Mock

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from core.helpers import get_authentication_result
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import anonymous_session_id, principal_identity
from services.auth import observability, resolver
from services.auth.browser_sessions import BROWSER_SESSION_COOKIE, create_browser_session


@pytest.mark.parametrize("kind,method,state,owner,transports", [
    ("none", "none", "no_credential", "none", "none"),
    ("anonymous", "anonymous_header", "no_credential", "anonymous", "anonymous_header"),
    ("portable", "portable_header", "valid", "personal", "portable_header"),
    ("pat", "pat_bearer", "valid", "personal", "pat_bearer"),
    ("cookie", "browser_cookie", "valid", "personal", "browser_cookie"),
    ("malformed", "rejected", "malformed_credential", "none", "portable_header"),
    ("conflict", "rejected", "malformed_credential", "none", "portable_header,browser_cookie"),
    ("ignored_cookie", "portable_header", "valid", "personal", "portable_header,browser_cookie"),
])
@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO])
def test_cached_resolution_logs_safe_branch_once(tmp_path, monkeypatch, kind, method, state, owner, transports, level):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "debug.db")))
    app = make_test_app()
    restricted = kind != "ignored_cookie"
    app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required" if restricted else "open"})
    app.config["RATELIMIT_ENABLED"] = False
    identity = principal_identity("authentication debug")
    credential_id = resolver.public_lookup_id_from_headers(identity.browser_headers())
    issued = create_browser_session(
        principal_id=identity.principal_id, credential_id=credential_id, absolute_seconds=3600,
    )
    anonymous = anonymous_session_id("authentication debug")
    headers = {}
    if kind == "anonymous":
        headers["X-Darklab-Anonymous-ID"] = anonymous
    if kind in {"portable", "conflict", "ignored_cookie"}:
        headers["X-Darklab-Credential"] = identity.portable_secret
    if kind == "pat":
        headers["Authorization"] = f"Bearer {identity.pat_secret}"
    if kind == "malformed":
        headers["X-Darklab-Credential"] = "private-invalid-credential-canary"
    if kind in {"cookie", "conflict", "ignored_cookie"}:
        headers["Cookie"] = f"{BROWSER_SESSION_COOKIE}={issued.cookie_value}"

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.Logger("auth-debug-test", level)
    logger.addHandler(handler)
    monkeypatch.setattr(observability, "log", logger)
    resolve = Mock(wraps=resolver.resolve_authentication)
    monkeypatch.setattr(resolver, "resolve_authentication", resolve)
    with app.test_request_context(
        "/config?private-query-canary", headers=headers,
        environ_overrides={"darklab_request_id": "auth-debug-request"},
    ):
        result = get_authentication_result()
        assert get_authentication_result() is result
        assert get_authentication_result() is result
    assert resolve.call_count == 1
    assert result.state.value == state
    if level != logging.DEBUG:
        assert records == []
        return
    assert len(records) == 1
    record = records[0]
    assert record.msg == "AUTHENTICATION_RESOLVED" and record.levelno == logging.DEBUG
    assert record.method == method and record.state == state and record.owner_kind == owner
    assert record.supplied_transports == transports
    assert record.browser_cookie_enabled is restricted
    assert record.last_used_write_due is (True if kind in {"portable", "pat", "ignored_cookie"} else None)
    assert record.request_id == "auth-debug-request"
    assert set(_extra_fields(record)) == {
        "request_id", "endpoint", "method", "state", "owner_kind", "supplied_transports",
        "browser_cookie_enabled", "last_used_write_due",
    }
    gelf = json.loads(GELFFormatter().format(record))
    assert gelf["_method"] == method and gelf["_browser_cookie_enabled"] is restricted
    rendered = _TextFormatter().format(record) + json.dumps(gelf)
    for private in (
        identity.principal_id, credential_id, identity.portable_secret, identity.pat_secret,
        issued.cookie_value, anonymous, "private-invalid-credential-canary", "private-query-canary",
    ):
        assert private not in rendered
