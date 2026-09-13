# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser PAT creation and staged rotation retain the credential's authority bounds."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import copy_pristine_sqlite_database, make_test_app
from core import database
from core.database_access import get_db_connect
from services.auth import browser_sessions, storage
from services.auth.contracts import DEFAULT_PAT_SCOPES, PAT_SCOPES
from services.workspace.models import WorkspaceSettings


@pytest.fixture
def issuance_client(tmp_path, monkeypatch):
    path = copy_pristine_sqlite_database(tmp_path / "issuance.db")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    app = make_test_app()
    app.config["RATELIMIT_ENABLED"] = False
    settings = WorkspaceSettings(True, "volume", tmp_path / "workspaces", 1024, 1024, 10, 1)
    settings.root.mkdir()
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(settings=settings, conn=conn)
        conn.commit()
    return app, app.test_client(), bundle, {"X-Darklab-Credential": bundle.credential.secret}


@pytest.mark.parametrize("days", [1, 90, 365])
def test_browser_issues_a_usable_pat_with_the_selected_lifetime(issuance_client, days):
    _, client, _, headers = issuance_client
    policy = client.get("/auth/credentials", headers=headers).get_json()["pat_policy"]
    assert set(policy["scopes"]) == PAT_SCOPES
    assert set(policy["default_scopes"]) == DEFAULT_PAT_SCOPES
    response = client.post("/auth/credentials", headers=headers, json={
        "type": "pat", "label": "CLI", "expires_in_days": days, "scopes": policy["default_scopes"],
    })
    assert response.status_code == 201
    data = response.get_json()
    metadata = data["credential"]
    assert datetime.fromisoformat(metadata["expires_at"]) - datetime.fromisoformat(metadata["created_at"]) == timedelta(days=days)
    token_headers = {"Authorization": f"Bearer {data['secret']}"}
    assert client.get("/api/v1/whoami", headers=token_headers).status_code == 200
    assert client.get("/api/v1/projects", headers=token_headers).status_code == 403
    assert client.get("/projects", headers=token_headers).status_code == 403
    assert data["secret"] not in client.get("/auth/credentials", headers=headers).get_data(as_text=True)


@pytest.mark.parametrize("days", [0, 366, -1, 1.5, True, "90"])
def test_pat_lifetime_rejects_invalid_day_values(issuance_client, days):
    _, client, _, headers = issuance_client
    response = client.post("/auth/credentials", headers=headers, json={"type": "pat", "expires_in_days": days})
    assert response.status_code == 400


@pytest.mark.parametrize("kind", ["portable", "pat"])
@pytest.mark.parametrize("defer", [False, True])
def test_rotation_preserves_label_scopes_and_the_existing_expiry(issuance_client, kind, defer):
    _, client, bundle, headers = issuance_client
    issued = client.post("/auth/credentials", headers=headers, json={"type": kind, "label": "Device"}).get_json()
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    with get_db_connect()() as conn:
        conn.execute("UPDATE credentials SET expires_at = ? WHERE id = ?", (expiry, issued["credential"]["id"]))
        conn.commit()
    response = client.post(f"/auth/credentials/{issued['credential']['id']}/rotate", headers=headers,
                           json={"defer_revocation": defer})
    assert response.status_code == 201
    replacement = response.get_json()
    assert replacement["credential"]["expires_at"] == expiry
    assert replacement["credential"]["label"] == "Device"
    assert replacement["credential"]["scopes"] == issued["credential"]["scopes"]
    old_headers = {"Authorization": f"Bearer {issued['secret']}"} if kind == "pat" else {"X-Darklab-Credential": issued["secret"]}
    assert client.get("/auth/principal", headers=old_headers).status_code == (200 if defer else 401)
    with get_db_connect()() as conn:
        row = conn.execute("SELECT principal_id FROM credentials WHERE id = ?", (replacement["credential"]["id"],)).fetchone()
        assert row["principal_id"] == bundle.principal.id
    if defer:
        revoked = client.post(f"/auth/credentials/{issued['credential']['id']}/revoke", headers=headers, json={})
        assert revoked.status_code == 200
        assert client.get("/auth/principal", headers=old_headers).status_code == 401


def test_preparing_rotation_preserves_the_current_browser_until_explicit_revocation(issuance_client):
    app, client, bundle, _ = issuance_client
    app.config["DARKLAB_CONFIG"] = {**app.config["DARKLAB_CONFIG"], "access_profile": "token_required"}
    session = browser_sessions.create_browser_session(
        principal_id=bundle.principal.id, credential_id=bundle.credential.metadata.id, absolute_seconds=43200,
    )
    client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, session.cookie_value)
    client.set_cookie(browser_sessions.BROWSER_CSRF_COOKIE, session.csrf_token)
    headers = {"X-Darklab-CSRF": session.csrf_token}
    path = f"/auth/credentials/{bundle.credential.metadata.id}"
    prepared = client.post(path + "/rotate", headers=headers, json={"defer_revocation": True})
    assert prepared.status_code == 201
    assert client.get("/auth/principal").status_code == 200
    assert client.post(path + "/revoke", headers=headers, json={}).status_code == 200
    assert client.get("/auth/principal").status_code == 401
