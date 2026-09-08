# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading
import uuid

import pytest

from core.database_backend import DatabaseBackend
from core.database_access import get_db_connect
from core.helpers import LEGACY_SESSION_ADAPTER_REMOVAL_ITEM
from core.migrations import v0078_principal_credential_persistence, v0079_credential_scopes
from services.auth import storage
from services.auth.contracts import LastCredentialLockout, PAT_DEFAULT_EXPIRY_DAYS
from services.auth.rate_limit import (
    ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR,
    FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE,
    FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE,
    check_anonymous_issuance,
    check_failed_redemption,
    reset_auth_rate_limits_for_tests,
)
from services.auth.resolver import (
    AnonymousContext,
    AuthenticatedContext,
    AuthenticationState,
    resolve_authentication,
)
from services.secrets.vault import reset_master_key_cache_for_tests
from services.teams.contracts import TeamError
from services.teams.scope import (
    anonymous_owner_context,
    owner_context_for_scope,
    owner_context_from_authentication,
    personal_owner_context,
)
from services.workspace.models import WorkspaceSettings


def _schema(conn) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    for migration in (
        v0078_principal_credential_persistence.MIGRATION,
        v0079_credential_scopes.MIGRATION,
    ):
        for statement in migration.statements_for(DatabaseBackend.SQLITE):
            conn.execute(statement)


@pytest.fixture
def auth_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_master_key_cache_for_tests()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _schema(conn)
    yield conn
    conn.close()
    reset_master_key_cache_for_tests()


def _settings(tmp_path) -> WorkspaceSettings:
    root = tmp_path / "workspaces"
    root.mkdir(exist_ok=True)
    return WorkspaceSettings(True, "volume", root, 1024, 1024, 10, 1)


def _unknown_secret(kind: str = "portable") -> str:
    encoded = base64.urlsafe_b64encode(b"x" * 32).rstrip(b"=").decode("ascii")
    if kind == "pat":
        return f"dlp_v1_pat_{'f' * 32}_{encoded}"
    return f"dlc_v1_crd_{'f' * 32}_{encoded}"


def test_resolver_distinguishes_every_principal_credential_state(auth_db, tmp_path):
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    bundle = storage.create_principal_with_credential(settings=_settings(tmp_path), conn=auth_db)

    missing = resolve_authentication({}, conn=auth_db, now=now)
    assert missing.state == AuthenticationState.NO_CREDENTIAL
    assert missing.context is None

    anonymous_id = str(uuid.uuid4())
    anonymous = resolve_authentication({"X-Darklab-Anonymous-ID": anonymous_id}, conn=auth_db, now=now)
    assert anonymous.state == AuthenticationState.NO_CREDENTIAL
    assert anonymous.context == AnonymousContext(anonymous_id)

    malformed = resolve_authentication({"X-Darklab-Credential": "dlc_v1_bad"}, conn=auth_db, now=now)
    assert malformed.state == AuthenticationState.MALFORMED_CREDENTIAL
    assert malformed.context is None
    assert resolve_authentication(
        {"X-Session-ID": ""},
        conn=auth_db,
        now=now,
    ).state == AuthenticationState.MALFORMED_CREDENTIAL
    assert resolve_authentication(
        {"Authorization": ""},
        conn=auth_db,
        now=now,
    ).state == AuthenticationState.MALFORMED_CREDENTIAL
    assert resolve_authentication(
        {
            "X-Darklab-Anonymous-ID": str(uuid.uuid4()),
            "X-Darklab-Credential": bundle.credential.secret,
        },
        conn=auth_db,
        now=now,
    ).error_code == "multiple_credentials"

    unknown = resolve_authentication({"X-Darklab-Credential": _unknown_secret()}, conn=auth_db, now=now)
    assert unknown.state == AuthenticationState.UNKNOWN_CREDENTIAL

    valid = resolve_authentication(
        {"X-Darklab-Credential": bundle.credential.secret},
        conn=auth_db,
        now=now,
    )
    assert valid.state == AuthenticationState.VALID
    assert isinstance(valid.context, AuthenticatedContext)
    assert valid.context.principal_id == bundle.principal.id
    assert valid.context.personal_workspace_id == bundle.workspace.id

    expired_issued = storage.issue_credential(
        bundle.principal.id,
        expires_at=now - timedelta(seconds=1),
        created_by_credential_id=bundle.credential.metadata.id,
        conn=auth_db,
    )
    expired = resolve_authentication(
        {"X-Darklab-Credential": expired_issued.secret},
        conn=auth_db,
        now=now,
    )
    assert expired.state == AuthenticationState.EXPIRED_CREDENTIAL

    revoked_issued = storage.issue_credential(
        bundle.principal.id,
        created_by_credential_id=bundle.credential.metadata.id,
        conn=auth_db,
    )
    storage.revoke_credential(bundle.principal.id, revoked_issued.metadata.id, conn=auth_db)
    revoked = resolve_authentication(
        {"X-Darklab-Credential": revoked_issued.secret},
        conn=auth_db,
        now=now,
    )
    assert revoked.state == AuthenticationState.REVOKED_CREDENTIAL

    storage.disable_principal(bundle.principal.id, reason="test", conn=auth_db)
    disabled = resolve_authentication(
        {"X-Darklab-Credential": bundle.credential.secret},
        conn=auth_db,
        now=now,
    )
    assert disabled.state == AuthenticationState.DISABLED_PRINCIPAL


def test_resolver_skips_last_used_write_inside_bounded_interval(auth_db, tmp_path):
    now = datetime.now(timezone.utc)
    bundle = storage.create_principal_with_credential(settings=_settings(tmp_path), conn=auth_db)
    headers = {"X-Darklab-Credential": bundle.credential.secret}

    first = resolve_authentication(headers, conn=auth_db, now=now)
    assert first.state == AuthenticationState.VALID

    statements: list[str] = []
    auth_db.set_trace_callback(statements.append)
    try:
        second = resolve_authentication(headers, conn=auth_db, now=now + timedelta(seconds=1))
    finally:
        auth_db.set_trace_callback(None)

    assert second.state == AuthenticationState.VALID
    assert not any("UPDATE credentials SET last_used_at" in statement for statement in statements)


def test_pat_is_typed_scoped_expiring_and_bearer_only(auth_db, tmp_path):
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    bundle = storage.create_principal_with_credential(settings=_settings(tmp_path), conn=auth_db)
    pat = storage.issue_credential(
        bundle.principal.id,
        credential_type="pat",
        created_by_credential_id=bundle.credential.metadata.id,
        now=now,
        conn=auth_db,
    )
    result = resolve_authentication({"Authorization": f"Bearer {pat.secret}"}, conn=auth_db, now=now)
    assert result.state == AuthenticationState.VALID
    assert isinstance(result.context, AuthenticatedContext)
    assert result.context.credential_type == "pat"
    assert result.context.capabilities == frozenset({"identity:read", "history:read", "runs:execute"})
    assert datetime.fromisoformat(pat.metadata.expires_at or "") == now + timedelta(days=PAT_DEFAULT_EXPIRY_DAYS)
    wrong_transport = resolve_authentication({"X-Darklab-Credential": pat.secret}, conn=auth_db, now=now)
    assert wrong_transport.state == AuthenticationState.MALFORMED_CREDENTIAL


@pytest.mark.parametrize("owner_id", ["", "anonymous", "../bad", "../other-session", "not-a-uuid"])
def test_owner_context_rejects_missing_shared_or_invalid_personal_owner(owner_id):
    with pytest.raises(TeamError):
        personal_owner_context(owner_id)
    with pytest.raises(TeamError):
        owner_context_for_scope(owner_id)


def test_owner_context_accepts_only_typed_success(auth_db):
    anonymous_id = str(uuid.uuid4())
    result = resolve_authentication({"X-Darklab-Anonymous-ID": anonymous_id}, conn=auth_db)
    assert anonymous_owner_context(anonymous_id).owner_id == anonymous_id
    assert owner_context_from_authentication(result).owner_id == anonymous_id
    failure = resolve_authentication({"X-Darklab-Credential": _unknown_secret()}, conn=auth_db)
    with pytest.raises(TeamError, match="Failed authentication"):
        owner_context_from_authentication(failure)


def test_failed_redemption_limit_is_bounded_by_ip_and_lookup_id():
    reset_auth_rate_limits_for_tests()
    for attempt in range(FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE + 1):
        result = check_failed_redemption("192.0.2.7", now=1_000.0)
        assert result.allowed is (attempt < FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE)
    reset_auth_rate_limits_for_tests()
    for attempt in range(FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE + 1):
        result = check_failed_redemption(
            f"192.0.2.{attempt + 1}",
            "crd_" + "a" * 32,
            now=1_000.0,
        )
        assert result.allowed is (attempt < FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE)
    reset_auth_rate_limits_for_tests()
    for attempt in range(ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR + 1):
        result = check_anonymous_issuance("192.0.2.8", now=1_000.0)
        assert result.allowed is (attempt < ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR)
    reset_auth_rate_limits_for_tests()


def test_concurrent_revocations_cannot_remove_both_portable_credentials(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_master_key_cache_for_tests()
    path = tmp_path / "auth.db"

    def connect():
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    with connect() as conn:
        _schema(conn)
        bundle = storage.create_principal_with_credential(settings=_settings(tmp_path), conn=conn)
        second = storage.issue_credential(
            bundle.principal.id,
            created_by_credential_id=bundle.credential.metadata.id,
            conn=conn,
        )
        conn.commit()

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def revoke(credential_id: str) -> None:
        barrier.wait()
        try:
            storage.revoke_credential(bundle.principal.id, credential_id, connect=connect)
            outcomes.append("revoked")
        except LastCredentialLockout:
            outcomes.append("protected")

    threads = [
        threading.Thread(target=revoke, args=(bundle.credential.metadata.id,)),
        threading.Thread(target=revoke, args=(second.metadata.id,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(outcomes) == ["protected", "revoked"]
    with connect() as conn:
        usable = conn.execute(
            "SELECT COUNT(*) FROM credentials WHERE principal_id = ? "
            "AND credential_type = 'portable' AND revoked_at IS NULL",
            (bundle.principal.id,),
        ).fetchone()[0]
    assert usable == 1
    reset_master_key_cache_for_tests()


def test_expiry_change_cannot_immediately_disable_final_portable_credential(auth_db, tmp_path):
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    bundle = storage.create_principal_with_credential(settings=_settings(tmp_path), conn=auth_db)
    with pytest.raises(LastCredentialLockout):
        storage.set_credential_expiry(
            bundle.principal.id,
            bundle.credential.metadata.id,
            now - timedelta(seconds=1),
            now=now,
            conn=auth_db,
        )

    expired = storage.issue_credential(
        bundle.principal.id,
        expires_at=now - timedelta(seconds=1),
        created_by_credential_id=bundle.credential.metadata.id,
        now=now,
        conn=auth_db,
    )
    storage.revoke_credential(
        bundle.principal.id,
        expired.metadata.id,
        now=now,
        conn=auth_db,
    )


def test_auth_routes_reveal_new_secrets_once_and_fail_closed(anonymous_identity_factory):
    from conftest import make_test_app

    flask_app = make_test_app()
    flask_app.config["RATELIMIT_ENABLED"] = False
    client = flask_app.test_client()
    anonymous = anonymous_identity_factory("principal-auth-upgrade")
    response = client.post("/auth/upgrade", headers=anonymous.headers, json={"label": "Laptop"})
    assert response.status_code == 201
    secret = response.get_json()["secret"]
    assert secret.startswith("dlc_v1_crd_")
    assert response.headers["Cache-Control"] == "no-store"

    headers = {"X-Darklab-Credential": secret}
    listed = client.get("/auth/credentials", headers=headers)
    assert listed.status_code == 200
    assert secret not in listed.get_data(as_text=True)
    created = client.post(
        "/auth/credentials",
        headers=headers,
        json={"type": "pat", "label": "CLI", "scopes": ["identity:read", "projects:read"]},
    )
    assert created.status_code == 201
    pat_secret = created.get_json()["secret"]
    assert pat_secret.startswith("dlp_v1_pat_")
    assert pat_secret not in client.get("/auth/credentials", headers=headers).get_data(as_text=True)
    pat_context = client.get(
        "/auth/context",
        headers={"Authorization": f"Bearer {pat_secret}"},
    )
    assert pat_context.status_code == 200
    assert pat_context.get_json()["authentication"]["capabilities"] == [
        "identity:read",
        "projects:read",
    ]
    pending_api_cutover = client.get(
        "/api/v1/whoami",
        headers={"Authorization": f"Bearer {pat_secret}"},
    )
    assert pending_api_cutover.status_code == 409
    assert pending_api_cutover.get_json()["error"]["code"] == "principal_cutover_pending"
    redeemed = client.post("/auth/redeem", json={"secret": secret})
    assert redeemed.status_code == 200
    assert secret not in redeemed.get_data(as_text=True)

    pending_cutover = client.get("/history", headers=headers)
    assert pending_cutover.status_code == 409
    assert pending_cutover.get_json()["error"] == "principal_cutover_pending"
    assert LEGACY_SESSION_ADAPTER_REMOVAL_ITEM == 11

    unknown = _unknown_secret()
    rejected = client.get("/history", headers={"X-Darklab-Credential": unknown})
    assert rejected.status_code == 401
    assert rejected.get_json()["error"] == "unknown_credential"
    with get_db_connect()() as conn:
        failure = conn.execute(
            "SELECT details FROM audit_events WHERE event_type = ? ORDER BY created DESC LIMIT 1",
            ("credential.authentication_failure",),
        ).fetchone()
    assert failure is not None
    assert unknown not in str(failure["details"])


def test_credential_lifecycle_routes_rotate_revoke_and_prevent_accidental_lockout(
    anonymous_identity_factory,
):
    from conftest import make_test_app

    flask_app = make_test_app()
    flask_app.config["RATELIMIT_ENABLED"] = False
    client = flask_app.test_client()
    anonymous = anonymous_identity_factory("principal-auth-lifecycle")
    upgraded = client.post("/auth/upgrade", headers=anonymous.headers, json={"label": "First"})
    first = upgraded.get_json()
    first_headers = {"X-Darklab-Credential": first["secret"]}
    first_id = first["credential"]["id"]

    created = client.post(
        "/auth/credentials",
        headers=first_headers,
        json={"type": "portable", "label": "Second"},
    )
    assert created.status_code == 201
    second = created.get_json()
    second_id = second["credential"]["id"]
    updated = client.patch(
        f"/auth/credentials/{second_id}",
        headers=first_headers,
        json={"label": "Travel laptop"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["credential"]["label"] == "Travel laptop"
    expiring = client.patch(
        f"/auth/credentials/{second_id}",
        headers=first_headers,
        json={"expires_at": "2027-01-01T00:00:00+00:00"},
    )
    assert expiring.status_code == 200
    assert expiring.get_json()["credential"]["expires_at"] == "2027-01-01T00:00:00+00:00"

    rotated = client.post(
        f"/auth/credentials/{second_id}/rotate",
        headers=first_headers,
        json={},
    )
    assert rotated.status_code == 201
    replacement = rotated.get_json()
    replacement_headers = {"X-Darklab-Credential": replacement["secret"]}
    assert client.get("/auth/context", headers=replacement_headers).status_code == 200
    assert client.get(
        "/auth/context",
        headers={"X-Darklab-Credential": second["secret"]},
    ).get_json()["error"] == "revoked_credential"

    assert client.post(
        f"/auth/credentials/{first_id}/revoke",
        headers=replacement_headers,
        json={"reason": "retired"},
    ).status_code == 200
    replacement_id = replacement["credential"]["id"]
    protected = client.post(
        f"/auth/credentials/{replacement_id}/revoke",
        headers=replacement_headers,
        json={"reason": "mistake"},
    )
    assert protected.status_code == 409
    assert protected.get_json()["error"] == "last_credential_lockout"
    assert client.get("/auth/context", headers=replacement_headers).status_code == 200
    with get_db_connect()() as conn:
        audit_rows = conn.execute(
            "SELECT event_type, target_id, details FROM audit_events "
            "WHERE event_type LIKE 'principal.%' OR event_type LIKE 'credential.%'"
        ).fetchall()
    event_types = {str(row["event_type"]) for row in audit_rows}
    assert {
        "principal.create",
        "credential.create",
        "credential.label",
        "credential.expiry",
        "credential.rotate",
        "credential.revoke",
    }.issubset(event_types)
    serialized_audit = json.dumps([dict(row) for row in audit_rows], default=str)
    assert first["secret"] not in serialized_audit
    assert second["secret"] not in serialized_audit
    assert replacement["secret"] not in serialized_audit


def test_pat_can_revoke_itself_without_affecting_portable_access(anonymous_identity_factory):
    from conftest import make_test_app

    flask_app = make_test_app()
    flask_app.config["RATELIMIT_ENABLED"] = False
    client = flask_app.test_client()
    upgraded = client.post(
        "/auth/upgrade",
        headers=anonymous_identity_factory("principal-auth-pat-revoke").headers,
        json={},
    ).get_json()
    portable_headers = {"X-Darklab-Credential": upgraded["secret"]}
    created = client.post(
        "/auth/credentials",
        headers=portable_headers,
        json={"type": "pat"},
    ).get_json()
    pat_headers = {"Authorization": f"Bearer {created['secret']}"}
    revoked = client.post(
        f"/auth/credentials/{created['credential']['id']}/revoke",
        headers=pat_headers,
        json={"reason": "finished"},
    )
    assert revoked.status_code == 200
    assert client.get("/auth/context", headers=pat_headers).status_code == 401
    assert client.get("/auth/context", headers=portable_headers).status_code == 200


def test_pat_scopes_are_enforced_on_identity_routes(anonymous_identity_factory):
    from conftest import make_test_app

    flask_app = make_test_app()
    flask_app.config["RATELIMIT_ENABLED"] = False
    client = flask_app.test_client()
    upgraded = client.post(
        "/auth/upgrade",
        headers=anonymous_identity_factory("principal-auth-pat-scope").headers,
        json={},
    ).get_json()
    portable_headers = {"X-Darklab-Credential": upgraded["secret"]}
    created = client.post(
        "/auth/credentials",
        headers=portable_headers,
        json={"type": "pat", "scopes": ["history:read"]},
    ).get_json()
    pat_headers = {"Authorization": f"Bearer {created['secret']}"}

    context = client.get("/auth/context", headers=pat_headers)
    assert context.status_code == 403
    assert context.get_json()["error"] == "credential_forbidden"
    credentials = client.get("/auth/credentials", headers=pat_headers)
    assert credentials.status_code == 403
    assert credentials.get_json()["error"] == "credential_forbidden"


def test_secret_bearing_auth_routes_are_post_only():
    from conftest import make_test_app
    from blueprints.auth import SECRET_BEARING_ENDPOINTS

    flask_app = make_test_app()
    methods = {
        rule.endpoint: rule.methods
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint in SECRET_BEARING_ENDPOINTS
    }
    assert methods.keys() == SECRET_BEARING_ENDPOINTS
    assert all(route_methods == {"OPTIONS", "POST"} for route_methods in methods.values())
