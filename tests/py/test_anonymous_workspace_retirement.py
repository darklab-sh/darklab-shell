# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Keeping a workspace retires its old anonymous Files access paths."""

import pytest

import config as shell_config
from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from identity_helpers import anonymous_session_id
from services.auth import resolver, storage
from services.auth.workspace_storage import anonymous_workspace_storage_key
from services.teams.scope import anonymous_owner_context
from services.workspace.models import WorkspacePermissionDenied
from services.workspace.paths import owner_workspace_dir


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "retirement.db")))
    cfg = build_test_config({
        "workspace_enabled": True, "workspace_backend": "volume", "workspace_root": str(tmp_path / "files"),
    })
    monkeypatch.setattr(shell_config, "CFG", cfg)
    application = make_test_app()
    application.config["DARKLAB_CONFIG"] = cfg
    application.config["RATELIMIT_ENABLED"] = False
    return application


@pytest.mark.parametrize("lifecycle", ["active", "rotated", "revoked", "disabled"])
def test_kept_workspace_rejects_old_anonymous_requests_and_download_tickets(app, lifecycle):
    assert_kept_workspace_retirement(app, lifecycle)


def assert_kept_workspace_retirement(app, lifecycle):
    """Run the same Files and recovery contract on SQLite and PostgreSQL."""
    client = app.test_client()
    anonymous = anonymous_session_id()
    old_headers = {"X-Darklab-Anonymous-ID": anonymous}
    old_owner = anonymous_owner_context(anonymous)
    assert client.post("/workspace/files", headers=old_headers, json={"path": "private.txt", "text": "before"}).status_code == 200
    ticket = client.post("/workspace/files/download-ticket", headers=old_headers, json={"path": "private.txt"})
    assert ticket.status_code == 200
    assert client.get(ticket.json["url"]).data == b"before"
    old_path = owner_workspace_dir(old_owner)

    kept = client.post("/auth/principals", headers=old_headers, json={"label": "Kept workspace"})
    assert kept.status_code == 201
    principal_id, credential_id = kept.json["principal"]["id"], kept.json["credential"]["id"]
    secret = kept.json["secret"]
    headers = {"X-Darklab-Credential": secret}
    written = client.post("/workspace/files", headers=headers, json={"path": "private.txt", "text": "after keeping"})
    assert written.status_code == 200
    assert old_path.name == anonymous_workspace_storage_key(anonymous)
    assert (old_path / "private.txt").read_text() == "after keeping"

    if lifecycle == "rotated":
        secret = storage.rotate_credential(principal_id, credential_id).secret
    elif lifecycle == "revoked":
        secret = storage.issue_credential(principal_id, label="Backup").secret
        storage.revoke_credential(principal_id, credential_id)
    elif lifecycle == "disabled":
        storage.disable_principal(principal_id, reason="test disablement")

    for method, path, body in (
        ("GET", "/workspace/files", None),
        ("GET", "/workspace/files/read?path=private.txt", None),
        ("GET", "/workspace/files/download?path=private.txt", None),
        ("POST", "/workspace/files", {"path": "private.txt", "text": "overwritten"}),
        ("DELETE", "/workspace/files?path=private.txt", None),
        ("POST", "/workspace/files/download-ticket", {"path": "private.txt"}),
        ("POST", "/auth/principals", {}),
    ):
        response = client.open(path, method=method, headers=old_headers, json=body)
        assert response.status_code == 401
        assert response.json["error"] == "anonymous_workspace_attached"
    assert client.get(ticket.json["url"]).status_code == 403
    with pytest.raises(WorkspacePermissionDenied, match="workspace was kept"):
        owner_workspace_dir(old_owner)
    assert (old_path / "private.txt").read_text() == "after keeping"

    if lifecycle == "disabled":
        assert client.get("/workspace/files", headers={"X-Darklab-Credential": secret}).status_code == 401
        storage.enable_principal(principal_id)
    response = client.get("/workspace/files/read?path=private.txt", headers={"X-Darklab-Credential": secret})
    assert response.status_code == 200
    assert response.json["text"] == "after keeping"
    assert client.get("/workspace/files", headers=old_headers).status_code == 401

    # A restored browser can prove its saved credential while still holding the retired UUID.
    assert client.post("/auth/credentials/redeem", headers=old_headers, json={"secret": "invalid"}).status_code == 401
    recovered = client.post("/auth/credentials/redeem", headers=old_headers, json={"secret": secret})
    assert recovered.status_code == 200
    assert recovered.json["authentication"]["principal_id"] == principal_id


def test_failed_attachment_does_not_retire_the_anonymous_workspace(app, monkeypatch):
    client = app.test_client()
    anonymous = anonymous_session_id()
    headers = {"X-Darklab-Anonymous-ID": anonymous}
    assert client.post("/workspace/files", headers=headers, json={"path": "file.txt", "text": "retained"}).status_code == 200

    def fail_attachment(_conn, **_kwargs):
        raise RuntimeError("injected attachment failure")

    monkeypatch.setattr(storage, "attach_personal_ownership", fail_attachment)
    with pytest.raises(RuntimeError, match="injected attachment failure"):
        client.post("/auth/principals", headers=headers, json={})
    assert not resolver.resolve_authentication(headers).failed
    assert client.get("/workspace/files/read?path=file.txt", headers=headers).json["text"] == "retained"
    assert client.post("/workspace/files", headers=headers, json={"path": "file.txt", "text": "still usable"}).status_code == 200


def test_anonymous_identity_fails_closed_if_attachment_storage_cannot_be_checked(app):
    def unavailable():
        raise RuntimeError("attachment storage unavailable")

    with pytest.raises(RuntimeError, match="attachment storage unavailable"):
        resolver.resolve_authentication({"X-Darklab-Anonymous-ID": anonymous_session_id()}, connect=unavailable)


def test_retired_anonymous_requests_do_not_exhaust_credential_recovery_allowance(app, monkeypatch):
    import core.process as process_state
    from services.auth import rate_limit

    rate_limit.reset_auth_rate_limits_for_tests()
    monkeypatch.setattr(process_state, "redis_client", None)
    app.config["RATELIMIT_ENABLED"] = True
    anonymous = anonymous_session_id()
    bundle = storage.create_principal_with_credential(anonymous_id=anonymous)
    client = app.test_client()
    headers = {"X-Darklab-Anonymous-ID": anonymous}
    try:
        for _ in range(40):
            assert client.get("/projects", headers=headers).status_code == 401
        restored = client.post("/auth/credentials/redeem", headers=headers, json={"secret": bundle.credential.secret})
        assert restored.status_code == 200
        assert restored.json["authentication"]["principal_id"] == bundle.principal.id
    finally:
        rate_limit.reset_auth_rate_limits_for_tests()
