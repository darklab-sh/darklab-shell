# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Principal disablement must find real processes started by the ordinary routes."""

import os
import signal
import subprocess
import time

import pytest

import config as shell_config
from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database, process
from identity_helpers import principal_identity
from services.auth import lifecycle, storage
from services.runs.contracts import RunStartRejected
from services.teams import storage as team_storage
from services.workflows.execution_owner import execution_owner_context


@pytest.fixture
def running_app(tmp_path, monkeypatch):
    from blueprints import run

    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "active-runs.db")))
    cfg = build_test_config({"run_broker_require_redis": False, "workspace_enabled": False})
    monkeypatch.setattr(shell_config, "CFG", cfg)
    monkeypatch.setattr(run, "CFG", cfg)
    monkeypatch.setattr(process, "redis_client", None)
    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = cfg
    app.config["RATELIMIT_ENABLED"] = False
    # Use a local, network-free command while retaining real spawn, registration,
    # broker output, process-group cancellation, and run finalization.
    monkeypatch.setattr(run, "is_command_allowed", lambda _command: (True, ""))
    spawned = []
    real_popen = subprocess.Popen

    def capture_process(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        spawned.append(child)
        return child

    monkeypatch.setattr(run.subprocess, "Popen", capture_process)
    yield app, spawned
    for child in spawned:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
        child.wait(timeout=5)
    # The real worker finishes persistence before the test database disappears.
    deadline = time.monotonic() + 5
    pids = {child.pid for child in spawned}
    while time.monotonic() < deadline:
        with process._pid_lock:
            active = [row for row in process._active_run_meta.values() if row.get("pid") in pids]
        if not active:
            break
        time.sleep(0.02)
    assert not active, "Test run workers did not finish cleanup"


@pytest.mark.parametrize("surface", ["browser", "api"])
@pytest.mark.parametrize("team", [False, True])
def test_disabling_principal_stops_its_real_route_started_process_only(running_app, surface, team):
    app, spawned = running_app
    identity = principal_identity("Active run owner")
    peer = principal_identity("Other active run owner")
    team_id = ""
    if team:
        with database.db_connect() as conn:
            created = team_storage.create_team(conn, name="Active run Team", creator_principal_id=identity.principal_id)
            team_id = created["id"]
            conn.commit()
    client = app.test_client()
    headers = identity.api_headers(team_id=team_id) if surface == "api" else identity.browser_headers(team_id=team_id)
    path = "/api/v1/runs" if surface == "api" else "/runs"
    started = client.post(path, headers=headers, json={"command": "sleep 30"})
    assert started.status_code == 202
    run_id = started.json["id"] if surface == "api" else started.json["run_id"]
    assert len(spawned) == 1
    child = spawned[0]
    assert child.poll() is None
    assert {row["run_id"] for row in process.active_runs_for_principal(identity.principal_id)} == {run_id}
    with process._pid_lock:
        active = dict(process._active_run_meta[run_id])
    assert active["principal_id"] == identity.principal_id
    credential = storage.list_credentials(identity.principal_id)
    expected_type = "pat" if surface == "api" else "portable"
    expected_id = next(row.id for row in credential if row.credential_type == expected_type)
    assert active["credential_id"] == expected_id
    assert active["team_id"] == team_id

    other = client.post("/runs", headers=peer.browser_headers(), json={"command": "sleep 30"})
    assert other.status_code == 202
    assert len(spawned) == 2
    peer_child = spawned[1]
    # Revoking the credential stops later requests, but ordinary accepted work continues.
    storage.revoke_credential(identity.principal_id, expected_id, allow_lockout=True)
    assert child.poll() is None
    lifecycle.set_principal_enabled(identity.principal_id, enabled=False, reason="Lost device test")
    child.wait(timeout=5)
    assert child.returncode is not None
    assert not process.active_runs_for_principal(identity.principal_id)
    assert peer_child.poll() is None
    assert {row["run_id"] for row in process.active_runs_for_principal(peer.principal_id)} == {other.json["run_id"]}


@pytest.mark.parametrize("team", [False, True])
def test_workflow_launch_owner_keeps_attribution_and_rechecks_current_authority(running_app, team):
    identity = principal_identity("Workflow initiator")
    credential_id = storage.list_credentials(identity.principal_id)[0].id
    execution = {
        "principal_id": identity.principal_id,
        "personal_workspace_id": identity.personal_workspace_id,
        "originating_credential_id": credential_id,
    }
    if team:
        admin = principal_identity("Workflow Team owner")
        with database.db_connect() as conn:
            created = team_storage.create_team(conn, name="Workflow Team", creator_principal_id=admin.principal_id)
            member = team_storage.add_team_member(
                conn, team_id=created["id"], principal_id=identity.principal_id, role="operator",
            )
            conn.commit()
        execution.update(team_id=created["id"], actor_member_id=member["id"])
    owner = execution_owner_context(execution)
    assert owner.actor_principal_id == identity.principal_id
    assert owner.actor_credential_id == credential_id
    assert owner.owner_id == (execution["team_id"] if team else identity.personal_workspace_id)
    storage.revoke_credential(identity.principal_id, credential_id, allow_lockout=True)
    assert execution_owner_context(execution) == owner
    if team:
        with database.db_connect() as conn:
            team_storage.update_team_member(conn, member["id"], role="viewer")
            conn.commit()
        with pytest.raises(RunStartRejected) as denied:
            execution_owner_context(execution)
        assert denied.value.code == "capability_revoked"
    lifecycle.set_principal_enabled(identity.principal_id, enabled=False, reason="Workflow owner disabled")
    with pytest.raises(RunStartRejected) as denied:
        execution_owner_context(execution)
    assert denied.value.code == "principal_disabled"
