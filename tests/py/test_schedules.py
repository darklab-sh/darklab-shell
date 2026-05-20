"""Scheduled-run route tests."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import unittest.mock as mock

import app as shell_app
from core.database import db_init, db_connect
from services.commands.builtins import execute_builtin_command


def get_client():
    shell_app.app.config["TESTING"] = True
    return shell_app.app.test_client()


def _schedule_client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "schedules.db")
    lock_path = str(tmp_path / "schedules.lock")
    monkeypatch.setattr("core.database.DB_PATH", db_path)
    monkeypatch.setattr("core.database.DB_INIT_LOCK_PATH", lock_path)
    monkeypatch.setattr("core.database.CFG", {
        "permalink_retention_days": 0,
        "scheduler": {
            "default_timezone": "UTC",
            "max_per_session": 32,
            "max_catchup_window_seconds": 3600,
            "tick_seconds": 5,
        },
    })
    db_init()
    return get_client(), db_path


def _register_token(token: str):
    with db_connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
            (token, datetime.now(timezone.utc).isoformat(), ""),
        )
        conn.commit()


def _create_schedule(client, token: str, **payload):
    body = {
        "command": "ping -c 1 darklab.sh",
        "cadence_preset": "hourly",
        "label": "Hourly ping",
        **payload,
    }
    return client.post("/schedules", headers={"X-Session-ID": token}, json=body)


class TestSchedulesRoutes:
    def test_schedule_crud_for_current_session(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_routes"
        _register_token(token)

        created = _create_schedule(client, token)
        assert created.status_code == 201
        schedule = created.get_json()["schedule"]
        assert schedule["command_text"] == "ping -c 1 darklab.sh"
        assert "session_token" not in schedule
        assert schedule["cron_expr"] == "0 * * * *"
        assert schedule["cadence_preset"] == "hourly"
        assert schedule["enabled"] is True

        listed = client.get("/schedules", headers={"X-Session-ID": token})
        assert listed.status_code == 200
        assert [item["id"] for item in listed.get_json()["schedules"]] == [schedule["id"]]

        updated = client.patch(
            f"/schedules/{schedule['id']}",
            headers={"X-Session-ID": token},
            json={"enabled": False, "label": "Paused ping"},
        )
        assert updated.status_code == 200
        assert updated.get_json()["schedule"]["enabled"] is False
        assert updated.get_json()["schedule"]["label"] == "Paused ping"

        deleted = client.delete(f"/schedules/{schedule['id']}", headers={"X-Session-ID": token})
        assert deleted.status_code == 200
        assert deleted.get_json()["removed"] is True
        listed_after_delete = client.get("/schedules", headers={"X-Session-ID": token})
        assert listed_after_delete.get_json()["schedules"] == []

    def test_schedule_routes_hide_cross_session_rows(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        owner = "tok_schedule_owner"
        other = "tok_schedule_other"
        _register_token(owner)
        _register_token(other)
        created = _create_schedule(client, owner)
        schedule_id = created.get_json()["schedule"]["id"]

        other_list = client.get("/schedules", headers={"X-Session-ID": other})
        other_patch = client.patch(f"/schedules/{schedule_id}", headers={"X-Session-ID": other}, json={"enabled": False})
        other_delete = client.delete(f"/schedules/{schedule_id}", headers={"X-Session-ID": other})

        assert other_list.status_code == 200
        assert other_list.get_json()["schedules"] == []
        assert other_patch.status_code == 404
        assert other_delete.status_code == 404

    def test_schedule_create_rejects_disallowed_command(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_reject_create"
        _register_token(token)

        resp = _create_schedule(client, token, command="rm -rf /")

        assert resp.status_code == 400
        assert resp.get_json()["error"] == "invalid_schedule"
        assert "Command not allowed" in resp.get_json()["message"]

    def test_schedule_patch_revalidates_changed_command(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_reject_patch"
        _register_token(token)
        created = _create_schedule(client, token)
        schedule_id = created.get_json()["schedule"]["id"]

        resp = client.patch(
            f"/schedules/{schedule_id}",
            headers={"X-Session-ID": token},
            json={"command": "rm -rf /"},
        )

        assert resp.status_code == 400
        assert resp.get_json()["error"] == "invalid_schedule"
        assert "Command not allowed" in resp.get_json()["message"]

    def test_schedule_run_now_records_fire_without_scheduler_process(self, monkeypatch, tmp_path):
        from services.scheduler import dispatch

        client, db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_run_now"
        _register_token(token)
        monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda _schedule: "run_schedule_now")
        created = _create_schedule(client, token)
        schedule_id = created.get_json()["schedule"]["id"]

        resp = client.post(f"/schedules/{schedule_id}/run-now", headers={"X-Session-ID": token})

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "fired"
        assert payload["schedule"]["last_run_at"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT schedule_id, status, reason FROM schedule_fires WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
        conn.close()
        assert dict(row) == {
            "schedule_id": schedule_id,
            "status": "fired",
            "reason": "started scheduled run",
        }

    def test_schedule_create_enforces_session_cap(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_cap"
        _register_token(token)
        with mock.patch.dict("core.database.CFG", {
            "permalink_retention_days": 0,
            "scheduler": {
                "default_timezone": "UTC",
                "max_per_session": 1,
                "max_catchup_window_seconds": 3600,
                "tick_seconds": 5,
            },
        }):
            first = _create_schedule(client, token)
            second = _create_schedule(client, token, label="Too many")

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.get_json()["message"] == "schedule quota exceeded for this session"


class TestScheduleBuiltin:
    def test_schedule_builtin_create_list_info_and_state_changes(self, monkeypatch, tmp_path):
        _client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_builtin"

        lines, exit_code = execute_builtin_command(
            "schedule create --every hourly -- ping -c 1 darklab.sh",
            token,
        )
        assert exit_code == 0
        assert "schedule: created sch_" in lines[0]["text"]
        with db_connect() as conn:
            row = conn.execute("SELECT id, enabled FROM schedules WHERE session_token = ?", (token,)).fetchone()
        schedule_id = row["id"]
        assert row["enabled"] == 1

        listed, _ = execute_builtin_command("schedule list", token)
        assert any(schedule_id in line["text"] and "ping -c 1 darklab.sh" in line["text"] for line in listed)

        info, _ = execute_builtin_command(f"schedule info {schedule_id}", token)
        assert any("command" in line["text"] and "ping -c 1 darklab.sh" in line["text"] for line in info)

        paused, _ = execute_builtin_command(f"schedule pause {schedule_id}", token)
        assert paused[0]["text"] == f"schedule: paused {schedule_id}"
        with db_connect() as conn:
            paused_row = conn.execute("SELECT enabled, paused_reason FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        assert paused_row["enabled"] == 0
        assert paused_row["paused_reason"] == "paused"

        resumed, _ = execute_builtin_command(f"schedule resume {schedule_id}", token)
        assert resumed[0]["text"] == f"schedule: resumed {schedule_id}"
        with db_connect() as conn:
            resumed_row = conn.execute("SELECT enabled FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        assert resumed_row["enabled"] == 1

        deleted, _ = execute_builtin_command(f"schedule delete {schedule_id}", token)
        assert deleted[0]["text"] == f"schedule: deleted {schedule_id}"
        with db_connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        assert count["count"] == 0

    def test_schedule_builtin_rejects_disallowed_command(self, monkeypatch, tmp_path):
        _client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_builtin_reject"

        lines, exit_code = execute_builtin_command("schedule create --every hourly -- rm -rf /", token)

        assert exit_code == 0
        assert "Command not allowed" in lines[0]["text"]
        with db_connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM schedules WHERE session_token = ?", (token,)).fetchone()
        assert count["count"] == 0

    def test_schedule_builtin_run_records_fire(self, monkeypatch, tmp_path):
        from services.scheduler import dispatch

        _client, db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_builtin_run"
        _register_token(token)
        monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda _schedule: "run_builtin_schedule")
        execute_builtin_command("schedule create --cron \"0 * * * *\" -- ping -c 1 darklab.sh", token)
        with db_connect() as conn:
            schedule_id = conn.execute("SELECT id FROM schedules WHERE session_token = ?", (token,)).fetchone()["id"]

        lines, exit_code = execute_builtin_command(f"schedule run {schedule_id}", token)

        assert exit_code == 0
        assert lines[0]["text"] == f"schedule: fired {schedule_id}"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT schedule_id, status, reason FROM schedule_fires WHERE schedule_id = ?",
            (schedule_id,),
        ).fetchone()
        conn.close()
        assert dict(row) == {
            "schedule_id": schedule_id,
            "status": "fired",
            "reason": "started scheduled run",
        }

    def test_schedule_builtin_requires_durable_session_token(self, monkeypatch, tmp_path):
        _client, _db_path = _schedule_client(monkeypatch, tmp_path)

        lines, exit_code = execute_builtin_command("schedule list", "anonymous-session")

        assert exit_code == 0
        assert lines[0]["text"] == "schedule: persistent session token required. Run `session-token generate` first."
