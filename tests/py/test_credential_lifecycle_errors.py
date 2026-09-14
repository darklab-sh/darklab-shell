# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Caught credential-storage faults stay observable without exposing private data."""

import json
import logging

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from core.database_access import get_db_connect
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import anonymous_session_id, principal_identity
from services.auth import lifecycle, observability
from services.auth.browser_sessions import (
    BROWSER_CSRF_COOKIE,
    BROWSER_SESSION_COOKIE,
    create_browser_session,
)
from services.auth.contracts import IdentityStorageError, VerifierKeyError, WorkspaceStorageError, timestamp
from services.auth.resolver import public_lookup_id_from_headers


@pytest.fixture
def lifecycle_app(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "lifecycle.db")))
    app = make_test_app()
    app.config["RATELIMIT_ENABLED"] = False
    return app


@pytest.fixture
def error_records(monkeypatch):
    records = []
    handler = logging.Handler()
    handler.setLevel(logging.ERROR)
    handler.emit = records.append
    logger = logging.Logger("credential-lifecycle-test", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(observability, "log", logger)
    return records


def _assert_safe_failure(response, records, *, operation, reason, error_class, private_values):
    assert response.status_code == 500
    assert response.get_json() == {
        "error": "credential_lifecycle_failed",
        "message": "Credential management is temporarily unavailable. Try again later.",
    }
    assert len(records) == 1
    record = records[0]
    assert record.msg == "CREDENTIAL_LIFECYCLE_FAILED"
    assert record.levelno == logging.ERROR
    assert record.operation == operation and record.reason == reason
    assert record.error_class == error_class and record.http_status == 500
    assert record.request_id
    assert set(_extra_fields(record)) == {"request_id", "operation", "reason", "error_class", "http_status"}
    assert record.exc_info and record.exc_info[1].__suppress_context__
    text = _TextFormatter().format(record)
    gelf = json.loads(GELFFormatter().format(record))
    assert gelf["_reason"] == reason and gelf["_http_status"] == 500
    rendered = text + json.dumps(gelf) + response.get_data(as_text=True)
    assert "Origin frames:" in rendered
    for private in private_values:
        assert private not in rendered


@pytest.mark.parametrize("surface", ["anonymous_upgrade", "browser_issuance"])
@pytest.mark.parametrize("corruption", ["missing_active_root", "corrupt_wrapped_root"])
def test_actual_verifier_faults_return_safe_500_and_roll_back(
    lifecycle_app, error_records, surface, corruption,
):
    identity = principal_identity("lifecycle storage fault")
    credential_id = public_lookup_id_from_headers(identity.browser_headers())
    client = lifecycle_app.test_client()
    private_values = [identity.portable_secret, identity.pat_secret, identity.principal_id, credential_id]
    if surface == "browser_issuance":
        lifecycle_app.config["DARKLAB_CONFIG"] = build_test_config({"access_profile": "token_required"})
        issued = create_browser_session(
            principal_id=identity.principal_id, credential_id=credential_id, absolute_seconds=3600,
        )
        client.set_cookie(BROWSER_SESSION_COOKIE, issued.cookie_value, secure=True)
        client.set_cookie(BROWSER_CSRF_COOKIE, issued.csrf_token, secure=True)
        headers = {"X-Darklab-CSRF": issued.csrf_token}
        private_values.extend([issued.cookie_value, issued.csrf_token])
        path, operation = "/auth/credentials", "create_credential"
    else:
        anonymous = anonymous_session_id("lifecycle fault anonymous")
        headers = {"X-Darklab-Anonymous-ID": anonymous}
        private_values.append(anonymous)
        path, operation = "/auth/principals", "create_principal"

    with get_db_connect()() as conn:
        before = conn.execute(
            "SELECT (SELECT COUNT(*) FROM credentials) AS credentials, "
            "(SELECT COUNT(*) FROM principals) AS principals"
        ).fetchone()
        before = dict(before)
        if corruption == "missing_active_root":
            conn.execute("UPDATE credential_verifier_roots SET state = 'retired', retired_at = ?", (timestamp(),))
        else:
            conn.execute("UPDATE credential_verifier_roots SET wrapped_root = ?", (b"private-wrapped-root-canary" * 3,))
        conn.commit()
    response = client.post(
        path + "?private-query-canary", base_url="https://localhost", headers=headers,
        json={"label": "private-label-canary"},
    )
    _assert_safe_failure(
        response, error_records, operation=operation, reason="verifier_key_unavailable",
        error_class="VerifierKeyError",
        private_values=private_values + ["private-wrapped-root-canary", "private-label-canary", "private-query-canary"],
    )
    with get_db_connect()() as conn:
        after = dict(conn.execute(
            "SELECT (SELECT COUNT(*) FROM credentials) AS credentials, "
            "(SELECT COUNT(*) FROM principals) AS principals"
        ).fetchone())
    assert after == before


@pytest.mark.parametrize("error_type,reason", [
    (IdentityStorageError, "identity_storage_failed"),
    (WorkspaceStorageError, "workspace_storage_unavailable"),
    (VerifierKeyError, "verifier_key_unavailable"),
])
def test_storage_failure_hides_original_message_source_and_exception_chain(
    lifecycle_app, error_records, monkeypatch, error_type, reason,
):
    identity = principal_identity("lifecycle exception privacy")

    def failed_issue(*_args, **_kwargs):
        try:
            raise ValueError("private-inner-exception-canary")
        except ValueError as cause:
            raise error_type("private-outer-exception-canary") from cause

    monkeypatch.setattr(lifecycle, "issue", failed_issue)
    response = lifecycle_app.test_client().post(
        "/auth/credentials", headers=identity.browser_headers(), json={"label": "private-request-label"},
    )
    _assert_safe_failure(
        response, error_records, operation="create_credential", reason=reason,
        error_class=error_type.__name__,
        private_values=["private-inner-exception-canary", "private-outer-exception-canary", "private-request-label"],
    )
    rendered = _TextFormatter().format(error_records[0])
    assert "test_credential_lifecycle_errors.py:failed_issue:" in rendered
    assert "raise error_type" not in rendered


@pytest.mark.parametrize("method,path,payload,status,code", [
    ("POST", "/auth/credentials", [], 400, "invalid_credential_request"),
    ("POST", "/auth/credentials", {"type": "unsupported"}, 400, "invalid_credential_request"),
    ("POST", "/auth/credentials", {"label": "x" * 257}, 400, "invalid_credential_request"),
    ("POST", "/auth/credentials", {"type": "pat", "scopes": ["unsupported"]}, 400, "invalid_credential_request"),
    ("PATCH", "/auth/credentials/{credential_id}", {"label": "name", "expires_at": None}, 400, "invalid_credential_request"),
    ("POST", "/auth/credentials/{credential_id}/rotate", {"defer_revocation": "false"}, 400, "invalid_credential_request"),
    ("POST", "/auth/credentials/{credential_id}/revoke", {}, 409, "last_credential_lockout"),
    ("PATCH", "/auth/credentials/crd_00000000000000000000000000000000", {"label": "name"}, 404, "credential_not_found"),
])
def test_invalid_lifecycle_requests_keep_client_status_without_error_logs(
    lifecycle_app, error_records, method, path, payload, status, code,
):
    identity = principal_identity("lifecycle client validation")
    credential_id = public_lookup_id_from_headers(identity.browser_headers())
    response = lifecycle_app.test_client().open(
        path.format(credential_id=credential_id), method=method,
        headers=identity.browser_headers(), json=payload,
    )
    assert response.status_code == status
    assert response.get_json()["error"] == code
    assert error_records == []
