# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Live response iteration must stop when its initial authority is revoked."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import pytest

from conftest import copy_pristine_sqlite_database, make_test_app
from core import database
from core.database_access import get_db_connect
from services.auth import browser_sessions, storage, stream_authorization
from services.auth.contracts import timestamp
from services.teams import storage as team_storage
from services.workspace.models import WorkspaceSettings


@pytest.fixture
def stream_identity(tmp_path, monkeypatch):
    path = copy_pristine_sqlite_database(tmp_path / "stream.db")
    monkeypatch.setattr(database, "DB_PATH", str(path))
    app = make_test_app()
    app.config["RATELIMIT_ENABLED"] = False
    settings = WorkspaceSettings(True, "volume", tmp_path / "workspaces", 1024, 1024, 10, 1)
    settings.root.mkdir()
    with get_db_connect()() as conn:
        bundle = storage.create_principal_with_credential(settings=settings, conn=conn)
        conn.execute(
            "INSERT INTO runs (id, personal_workspace_id, command, started) VALUES (?, ?, ?, ?)",
            (bundle.principal.id, bundle.workspace.id, "true", timestamp()),
        )
        conn.commit()
    return app, bundle


_STREAM_CASES = [
    (surface, transport, action)
    for surface, transport in (
        ("browser", "portable"), ("browser", "cookie"),
        ("pty", "portable"), ("pty", "cookie"),
        ("api_sse", "pat"), ("api_ndjson", "pat"),
    )
    for action in ("revoke", "rotate", "expire", "disable", "logout", "revoke_all")
    if transport == "cookie" or action not in {"logout", "revoke_all"}
] + [(surface, "oidc", action) for surface in ("browser", "pty") for action in ("disable", "logout", "revoke_all", "unlink")]


@pytest.mark.parametrize("surface,transport,action", _STREAM_CASES)
def test_stream_revocation_stops_delivery_and_only_terminates_ptys(
    stream_identity, monkeypatch, surface, transport, action,
):
    from blueprints import api_v1, run

    app, bundle = stream_identity
    client = app.test_client()
    credential = bundle.credential
    session = None
    if transport == "pat":
        with get_db_connect()() as conn:
            credential = storage.issue_credential(
                bundle.principal.id, credential_type="pat", scopes={"identity:read", "history:read"}, conn=conn,
            )
            conn.commit()
        headers = {"Authorization": f"Bearer {credential.secret}"}
    elif transport in {"cookie", "oidc"}:
        app.config["DARKLAB_CONFIG"] = {
            **app.config["DARKLAB_CONFIG"], "access_profile": "mixed" if transport == "oidc" else "token_required",
        }
        identity_id = ""
        if transport == "oidc":
            identity_id = "oid_" + bundle.principal.id[4:]
            with get_db_connect()() as conn:
                conn.execute(
                    "INSERT INTO oidc_identities (id, principal_id, issuer, subject, created_at) VALUES (?, ?, ?, ?, ?)",
                    (identity_id, bundle.principal.id, "https://provider.example", bundle.principal.id, timestamp()),
                )
                conn.commit()
        session = browser_sessions.create_browser_session(
            principal_id=bundle.principal.id,
            credential_id="" if identity_id else credential.metadata.id,
            oidc_identity_id=identity_id,
            absolute_seconds=43200,
        )
        client.set_cookie(browser_sessions.BROWSER_SESSION_COOKIE, session.cookie_value)
        client.set_cookie(browser_sessions.BROWSER_CSRF_COOKIE, session.csrf_token)
        headers = {"X-Darklab-CSRF": session.csrf_token}
    else:
        headers = {"X-Darklab-Credential": credential.secret}
    run_id = bundle.principal.id
    closed = []
    clock = [0.0]
    monkeypatch.setattr(stream_authorization, "monotonic", lambda: clock[0])

    def events(*_args, **_kwargs):
        try:
            yield 'data: {"type":"output","text":"before revocation"}\n\n'
            yield ': heartbeat\n\n'
            yield 'data: {"type":"output","text":"must not be delivered"}\n\n'
        finally:
            closed.append(True)

    if surface == "pty":
        monkeypatch.setattr(run, "stream_pty_events", events)
        monkeypatch.setattr(run, "pty_run_belongs_to_session", lambda *_args: True)
        path = f"/pty/runs/{run_id}/stream"
    elif surface.startswith("api"):
        monkeypatch.setattr(api_v1, "stream_run_events", events)
        path = f"/api/v1/runs/{run_id}/stream" + ("?format=ndjson" if surface == "api_ndjson" else "")
    else:
        monkeypatch.setattr(run, "stream_run_events", events)
        path = f"/runs/{run_id}/stream"

    with mock.patch("services.runs.cancellation.request_active_run_cancellation", return_value=True) as cancel:
        response = client.get(path, headers=headers, base_url="https://localhost", buffered=False)
        assert response.status_code == 200
        chunks = iter(response.response)
        assert b"before revocation" in next(chunks)
        with get_db_connect()() as conn:
            last_used = conn.execute(
                "SELECT last_used_at FROM credentials WHERE id = ?", (credential.metadata.id,),
            ).fetchone()[0]
            if session:
                last_seen = conn.execute(
                    "SELECT last_seen_at FROM browser_sessions WHERE id = ?", (session.id,),
                ).fetchone()[0]
            if action == "revoke":
                storage.revoke_credential(bundle.principal.id, credential.metadata.id, allow_lockout=True, conn=conn)
            elif action == "rotate":
                storage.rotate_credential(bundle.principal.id, credential.metadata.id, conn=conn)
            elif action == "expire":
                conn.execute("UPDATE credentials SET expires_at = ? WHERE id = ?", (
                    timestamp(datetime.now(timezone.utc) - timedelta(seconds=1)), credential.metadata.id,
                ))
            elif action == "disable":
                storage.disable_principal(bundle.principal.id, reason="stream test", conn=conn)
            elif action == "unlink":
                conn.execute("DELETE FROM oidc_identities WHERE id = ?", (identity_id,))
            conn.commit()
        if action in {"logout", "revoke_all"}:
            route = "/auth/logout" if action == "logout" else "/auth/sessions/revoke-all"
            logged_out = client.post(route, headers=headers, base_url="https://localhost", json={})
            assert logged_out.status_code in {200, 204}
        clock[0] = 11.0
        remainder = b"".join(chunks).decode()
        response.close()
        assert "must not be delivered" not in remainder
        payloads = [json.loads(line.removeprefix("data: ")) for line in remainder.splitlines() if line.startswith(("data:", "{"))]
        assert [payload["type"] for payload in payloads] == ["error"]
        assert any(reason in remainder for reason in (
            "revoked_credential", "revoked_browser_session", "expired_credential",
            "expired_browser_session", "principal_disabled", "unknown_browser_session",
        ))
        assert closed == [True]
        if surface == "pty":
            cancel.assert_called_once_with(run_id, bundle.workspace.id, team_id="")
        else:
            cancel.assert_not_called()
        with get_db_connect()() as conn:
            assert conn.execute(
                "SELECT last_used_at FROM credentials WHERE id = ?", (credential.metadata.id,),
            ).fetchone()[0] == last_used
            if session:
                assert conn.execute(
                    "SELECT last_seen_at FROM browser_sessions WHERE id = ?", (session.id,),
                ).fetchone()[0] == last_seen


def test_stream_fails_closed_when_authorization_storage_is_unavailable(stream_identity, monkeypatch):
    from blueprints import run

    app, bundle = stream_identity
    monkeypatch.setattr(run, "stream_run_events", lambda *_args, **_kwargs: iter([
        'data: {"type":"output","text":"private"}\n\n',
    ]))
    monkeypatch.setattr(stream_authorization, "stream_rejection", mock.Mock(side_effect=RuntimeError("offline")))
    response = app.test_client().get(
        f"/runs/{bundle.principal.id}/stream", headers={"X-Darklab-Credential": bundle.credential.secret},
    )
    body = response.get_data(as_text=True)
    assert "private" not in body
    assert "authorization_unavailable" in body


@pytest.mark.parametrize("interactive", [False, True])
@pytest.mark.parametrize("change", ["remove", "downgrade", "archive"])
def test_team_stream_rechecks_membership_and_current_control_permission(
    stream_identity, monkeypatch, interactive, change,
):
    from blueprints import run

    app, bundle = stream_identity
    with get_db_connect()() as conn:
        owner = storage.create_principal_with_credential(conn=conn)
        team = team_storage.create_team(conn, name="Stream authority", creator_principal_id=owner.principal.id)
        member = team_storage.add_team_member(conn, team_id=team["id"], principal_id=bundle.principal.id, role="operator")
        conn.execute("UPDATE runs SET team_id = ? WHERE id = ?", (team["id"], bundle.principal.id))
        conn.commit()
    clock = [0.0]
    monkeypatch.setattr(stream_authorization, "monotonic", lambda: clock[0])
    monkeypatch.setattr(run, "pty_run_belongs_to_scope", lambda *_args: True)

    def events(*_args, **_kwargs):
        yield ": heartbeat\n\n"
        yield 'data: {"type":"output","text":"after membership change"}\n\n'

    monkeypatch.setattr(run, "stream_pty_events" if interactive else "stream_run_events", events)
    prefix = "/pty/runs" if interactive else "/runs"
    with mock.patch("services.runs.cancellation.request_active_run_cancellation") as cancel:
        response = app.test_client().get(f"{prefix}/{bundle.principal.id}/stream", headers={
            "X-Darklab-Credential": bundle.credential.secret, "X-Team-ID": team["id"],
        }, buffered=False)
        assert response.status_code == 200
        chunks = iter(response.response)
        next(chunks)
        with get_db_connect()() as conn:
            if change == "remove":
                team_storage.soft_remove_team_member(conn, member["id"])
            elif change == "downgrade":
                team_storage.update_team_member(conn, member["id"], role="viewer")
            else:
                team_storage.update_team_status(conn, team["id"], status="archived")
            conn.commit()
        clock[0] = 11.0
        body = b"".join(chunks).decode()
        response.close()
        if change == "downgrade" and not interactive:
            assert "after membership change" in body
            cancel.assert_not_called()
        else:
            assert "after membership change" not in body
            assert '"type": "error"' in body
            assert cancel.call_count == int(interactive)


def test_stream_rechecks_without_touching_an_idle_browser_session(stream_identity):
    app, bundle = stream_identity
    issued = browser_sessions.create_browser_session(
        principal_id=bundle.principal.id, credential_id=bundle.credential.metadata.id, absolute_seconds=43200,
    )
    with get_db_connect()() as conn:
        row = conn.execute("SELECT * FROM browser_sessions WHERE id = ?", (issued.id,)).fetchone()
        now = datetime.fromisoformat(str(row["last_seen_at"])) + timedelta(seconds=61)
        assert browser_sessions.revalidate_browser_session(
            issued.id, principal_id=bundle.principal.id, credential_id=bundle.credential.metadata.id,
            oidc_identity_id="", idle_seconds=60, now=now, conn=conn,
        ) == "idle_browser_session"
        assert conn.execute(
            "SELECT last_seen_at FROM browser_sessions WHERE id = ?", (issued.id,),
        ).fetchone()[0] == row["last_seen_at"]


def test_broker_poll_is_bounded_and_first_event_close_releases_subscriber(monkeypatch):
    from services.runs import broker
    from services import metrics

    monkeypatch.setattr(broker, "resolve_effective_cfg", lambda: {"run_broker_subscriber_block_seconds": 120})
    monkeypatch.setattr(broker, "replay_run_events", lambda *_args: [])
    store = mock.Mock()
    store.wait_after.side_effect = [[], RuntimeError("finished")]
    monkeypatch.setattr(broker, "_store", lambda: store)
    with mock.patch.object(metrics, "record_broker_subscriber_delta") as subscribers:
        stream = broker.stream_run_events("example")
        next(stream)
        stream.close()
        assert subscribers.call_args_list == [mock.call(1), mock.call(-1)]
    stream = broker.stream_run_events("example")
    next(stream)
    assert next(stream) == ": heartbeat\n\n"
    assert store.wait_after.call_args.kwargs["timeout"] <= 5
    stream.close()


def test_local_and_redis_pty_readers_bound_idle_wait_without_holding_a_lock(monkeypatch):
    from services.pty import service

    class Condition:
        held = False
        waits = []

        def __enter__(self):
            self.held = True

        def __exit__(self, *_args):
            self.held = False

        def wait(self, *, timeout):
            self.waits.append(timeout)

    condition = Condition()
    run = SimpleNamespace(condition=condition, events=[], closed=False)
    monkeypatch.setattr(service, "_pty_heartbeat_seconds", lambda: 120)
    local = service._stream_local_pty_events(run)
    assert "heartbeat" in next(local)
    assert condition.waits == [5]
    assert condition.held is False
    local.close()

    redis = mock.Mock()
    redis.xread.return_value = []
    monkeypatch.setattr(service, "redis_client", redis)
    monkeypatch.setattr(service, "resolve_effective_cfg", lambda: {"run_broker_subscriber_block_seconds": 120})
    monkeypatch.setattr(service, "_load_pty_meta_for_scope", lambda *_args: {"closed": False})
    monkeypatch.setattr(service, "_prune_stale_open_pty", lambda *_args: False)
    remote = service.stream_pty_events("run", "workspace")
    assert "heartbeat" in next(remote)
    assert "heartbeat" in next(remote)
    assert [call.kwargs["block"] for call in redis.xread.call_args_list] == [1, 5000]
    remote.close()


@pytest.mark.parametrize("interactive", [False, True])
def test_revocation_terminates_real_interactive_process_but_keeps_ordinary_work(
    stream_identity, monkeypatch, interactive,
):
    from blueprints import run
    from core import process
    from services.runs import cancellation

    app, bundle = stream_identity
    run_id = bundle.principal.id
    clock = [0.0]
    monkeypatch.setattr(stream_authorization, "monotonic", lambda: clock[0])
    monkeypatch.setattr(process, "redis_client", None)
    monkeypatch.setattr(cancellation, "SCANNER_PREFIX", [])
    monkeypatch.setattr(cancellation, "publish_run_event", lambda *_args: None)

    def events(*_args, **_kwargs):
        yield ': heartbeat\n\n'
        yield ': heartbeat\n\n'

    monkeypatch.setattr(run, "stream_pty_events" if interactive else "stream_run_events", events)
    monkeypatch.setattr(run, "pty_run_belongs_to_session", lambda *_args: True)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    response = None
    try:
        process.pid_register(run_id, child.pid)
        process.active_run_register(run_id, child.pid, bundle.workspace.id, "sleep", timestamp())
        prefix = "/pty/runs" if interactive else "/runs"
        response = app.test_client().get(
            f"{prefix}/{run_id}/stream", headers={"X-Darklab-Credential": bundle.credential.secret}, buffered=False,
        )
        chunks = iter(response.response)
        assert b"heartbeat" in next(chunks)
        with get_db_connect()() as conn:
            storage.revoke_credential(bundle.principal.id, bundle.credential.metadata.id, allow_lockout=True, conn=conn)
            conn.commit()
        clock[0] = 11.0
        assert b"revoked_credential" in b"".join(chunks)
        if interactive:
            assert child.wait(timeout=5) != 0
        else:
            assert child.poll() is None
    finally:
        if response is not None:
            response.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        process.active_run_remove(run_id)
        process.pid_pop(run_id)
