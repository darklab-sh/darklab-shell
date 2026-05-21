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


def _insert_completed_run(
    token: str,
    run_id: str,
    *,
    command: str = "nmap -sV darklab.sh",
    finished: str | None = "2026-05-20T00:00:01+00:00",
):
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
            "VALUES (?, ?, 'external', ?, ?, ?, 0, '[]', 0)",
            (
                run_id,
                token,
                command,
                "2026-05-20T00:00:00+00:00",
                finished,
            ),
        )
        conn.commit()


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

        detail = client.get(f"/schedules/{schedule['id']}", headers={"X-Session-ID": token})
        assert detail.status_code == 200
        assert detail.get_json()["schedule"]["id"] == schedule["id"]

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
        assert client.get(f"/schedules/{schedule_id}", headers={"X-Session-ID": other}).status_code == 404
        assert client.get(f"/schedules/{schedule_id}/fires", headers={"X-Session-ID": other}).status_code == 404
        assert other_patch.status_code == 404
        assert other_delete.status_code == 404

    def test_schedule_preview_returns_next_three_fires(self, monkeypatch, tmp_path):
        import blueprints.schedules as schedules_blueprint

        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_preview"
        _register_token(token)

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                return datetime(2026, 5, 20, 12, 15, tzinfo=timezone.utc)

        monkeypatch.setattr(schedules_blueprint, "datetime", FixedDatetime)

        resp = client.get("/schedules/preview?cadence_preset=hourly&tz=UTC", headers={"X-Session-ID": token})

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["cron_expr"] == "0 * * * *"
        assert payload["cadence_preset"] == "hourly"
        assert payload["timezone"] == "UTC"
        assert payload["next_fires"] == [
            "2026-05-20T13:00:00+00:00",
            "2026-05-20T14:00:00+00:00",
            "2026-05-20T15:00:00+00:00",
        ]

        valid_custom = client.get(
            "/schedules/preview?cron=*/5%20*%20*%20*%20*&tz=America/Chicago",
            headers={"X-Session-ID": token},
        )
        invalid_custom = client.get("/schedules/preview?cron=*/4%20*%20*%20*%20*&tz=UTC", headers={"X-Session-ID": token})

        assert valid_custom.status_code == 200
        assert valid_custom.get_json()["timezone"] == "America/Chicago"
        assert invalid_custom.status_code == 400
        assert "every 5 minutes" in invalid_custom.get_json()["message"]

    def test_schedule_preview_requires_durable_session_token(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)

        resp = client.get("/schedules/preview?cadence_preset=hourly&tz=UTC", headers={"X-Session-ID": "anon"})

        assert resp.status_code == 401
        assert resp.get_json()["error"] == "session_token_required"

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

        fires = client.get(f"/schedules/{schedule_id}/fires", headers={"X-Session-ID": token})
        assert fires.status_code == 200
        fires_payload = fires.get_json()
        assert fires_payload["total"] == 1
        assert fires_payload["fires"][0]["schedule_id"] == schedule_id
        assert fires_payload["fires"][0]["status"] == "fired"

    def test_schedule_fire_links_completed_run_in_history(self, monkeypatch, tmp_path):
        from services.scheduler import dispatch

        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_history_link"
        run_id = "run_schedule_history_link"
        _register_token(token)
        monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda _schedule: run_id)
        created = _create_schedule(client, token)
        schedule_id = created.get_json()["schedule"]["id"]

        fired = client.post(f"/schedules/{schedule_id}/run-now", headers={"X-Session-ID": token})
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', ?, ?, ?, 0, '[]', 0)",
                (
                    run_id,
                    token,
                    "ping -c 1 darklab.sh",
                    "2026-05-20T00:00:00+00:00",
                    "2026-05-20T00:00:01+00:00",
                ),
            )
            conn.commit()

        history = client.get("/history?include_total=1", headers={"X-Session-ID": token})
        payload = history.get_json()

        assert fired.status_code == 200
        assert history.status_code == 200
        assert payload["items"][0]["id"] == run_id
        assert payload["items"][0]["scheduled"] is True
        assert payload["items"][0]["schedule_id"] == schedule_id

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

    def test_schedule_create_and_patch_normalize_edge_inputs(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_edges"
        _register_token(token)

        disabled = _create_schedule(client, token, enabled="false", label="  Edge schedule  ", timezone="America/Chicago")
        schedule = disabled.get_json()["schedule"]
        invalid_timezone = _create_schedule(client, token, label="Bad timezone", timezone="Not/A_Timezone")
        blank_patch = client.patch(
            f"/schedules/{schedule['id']}",
            headers={"X-Session-ID": token},
            json={"command": "   "},
        )
        paused_update = client.patch(
            f"/schedules/{schedule['id']}",
            headers={"X-Session-ID": token},
            json={"cadence_preset": "daily", "timezone": "America/Los_Angeles", "label": "  Daily edge  "},
        )

        assert disabled.status_code == 201
        assert schedule["enabled"] is False
        assert schedule["label"] == "Edge schedule"
        assert schedule["timezone"] == "America/Chicago"
        assert invalid_timezone.status_code == 400
        assert invalid_timezone.get_json()["message"] == "timezone must be an IANA timezone name"
        assert blank_patch.status_code == 400
        assert blank_patch.get_json()["message"] == "command is required"
        assert paused_update.status_code == 200
        updated = paused_update.get_json()["schedule"]
        assert updated["enabled"] is False
        assert updated["cadence_preset"] == "daily"
        assert updated["timezone"] == "America/Los_Angeles"
        assert updated["label"] == "Daily edge"

    def test_schedule_fires_pagination_bounds(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_schedule_fire_pages"
        _register_token(token)
        created = _create_schedule(client, token)
        schedule_id = created.get_json()["schedule"]["id"]
        with db_connect() as conn:
            for index in range(3):
                conn.execute(
                    """
                    INSERT INTO schedule_fires (id, schedule_id, owner_kind, owner_id, fired_at, run_id, status, reason)
                    VALUES (?, ?, 'user', '', ?, ?, 'fired', 'started scheduled run')
                    """,
                    (
                        f"scf_page_{index}",
                        schedule_id,
                        f"2026-05-20T00:00:0{index}+00:00",
                        f"run_page_{index}",
                    ),
                )
            conn.commit()

        first = client.get(f"/schedules/{schedule_id}/fires?limit=2&offset=0", headers={"X-Session-ID": token})
        second = client.get(f"/schedules/{schedule_id}/fires?limit=2&offset=2", headers={"X-Session-ID": token})

        assert first.status_code == 200
        first_payload = first.get_json()
        assert first_payload["limit"] == 2
        assert first_payload["offset"] == 0
        assert first_payload["total"] == 3
        assert first_payload["has_more"] is True
        assert [fire["run_id"] for fire in first_payload["fires"]] == ["run_page_2", "run_page_1"]
        assert second.status_code == 200
        second_payload = second.get_json()
        assert second_payload["offset"] == 2
        assert second_payload["has_more"] is False
        assert [fire["run_id"] for fire in second_payload["fires"]] == ["run_page_0"]


class TestWatchersRoutes:
    def test_watcher_routes_crud_and_cascade_owned_schedule(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        owner = "tok_watcher_routes_owner"
        other = "tok_watcher_routes_other"
        _register_token(owner)
        _register_token(other)
        _insert_completed_run(owner, "run_watcher_baseline", command="nmap -sV darklab.sh")

        created = client.post(
            "/watchers",
            headers={"X-Session-ID": owner},
            json={"baseline_run_id": "run_watcher_baseline", "cadence_preset": "hourly", "label": "Nmap drift"},
        )
        watcher = created.get_json()["watcher"]
        other_patch = client.patch(f"/watchers/{watcher['id']}", headers={"X-Session-ID": other}, json={"state": "paused"})
        other_delete = client.delete(f"/watchers/{watcher['id']}", headers={"X-Session-ID": other})
        listed = client.get("/watchers", headers={"X-Session-ID": owner})
        other_listed = client.get("/watchers", headers={"X-Session-ID": other})
        paused = client.patch(f"/watchers/{watcher['id']}", headers={"X-Session-ID": owner}, json={"state": "paused"})
        resumed = client.patch(
            f"/watchers/{watcher['id']}",
            headers={"X-Session-ID": owner},
            json={"state": "ok", "label": "Nmap drift v2"},
        )
        deleted = client.delete(f"/watchers/{watcher['id']}", headers={"X-Session-ID": owner})

        assert created.status_code == 201
        assert watcher["command_text"] == "nmap -sV darklab.sh"
        assert watcher["label"] == "Nmap drift"
        assert watcher["baseline_run_id"] == "run_watcher_baseline"
        assert watcher["schedule"]["owner_kind"] == "watcher"
        assert watcher["schedule"]["cadence_preset"] == "hourly"
        assert "session_token" not in watcher
        assert listed.status_code == 200
        assert [item["id"] for item in listed.get_json()["watchers"]] == [watcher["id"]]
        assert other_listed.get_json()["watchers"] == []
        assert other_patch.status_code == 404
        assert other_delete.status_code == 404
        assert paused.status_code == 200
        assert paused.get_json()["watcher"]["state"] == "paused"
        assert paused.get_json()["watcher"]["schedule"]["enabled"] is False
        assert resumed.status_code == 200
        assert resumed.get_json()["watcher"]["state"] == "ok"
        assert resumed.get_json()["watcher"]["label"] == "Nmap drift v2"
        assert resumed.get_json()["watcher"]["schedule"]["enabled"] is True
        assert deleted.status_code == 200
        assert deleted.get_json()["removed"] is True
        with db_connect() as conn:
            watcher_count = conn.execute("SELECT COUNT(*) AS count FROM watchers WHERE id = ?", (watcher["id"],)).fetchone()
            schedule_count = conn.execute(
                "SELECT COUNT(*) AS count FROM schedules WHERE id = ?",
                (watcher["schedule_id"],),
            ).fetchone()
        assert watcher_count["count"] == 0
        assert schedule_count["count"] == 0

    def test_watcher_create_validates_baseline_visibility_and_completion(self, monkeypatch, tmp_path):
        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        owner = "tok_watcher_baseline_owner"
        other = "tok_watcher_baseline_other"
        _register_token(owner)
        _register_token(other)
        _insert_completed_run(other, "run_other_baseline")
        _insert_completed_run(owner, "run_unfinished_baseline", finished=None)

        missing = client.post(
            "/watchers",
            headers={"X-Session-ID": owner},
            json={"baseline_run_id": "run_other_baseline", "cadence_preset": "hourly"},
        )
        unfinished = client.post(
            "/watchers",
            headers={"X-Session-ID": owner},
            json={"baseline_run_id": "run_unfinished_baseline", "cadence_preset": "hourly"},
        )

        assert missing.status_code == 404
        assert missing.get_json()["error"] == "baseline_run_not_found"
        assert unfinished.status_code == 400
        assert unfinished.get_json()["error"] == "invalid_baseline"
        assert unfinished.get_json()["message"] == "baseline run must be completed"

    def test_watcher_accept_baseline_promotes_latest_fire_and_resets_state(self, monkeypatch, tmp_path):
        from services.watchers import service as watcher_service

        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_watcher_accept"
        _register_token(token)
        _insert_completed_run(token, "run_accept_baseline")
        _insert_completed_run(token, "run_accept_latest")
        created = client.post(
            "/watchers",
            headers={"X-Session-ID": token},
            json={"baseline_run_id": "run_accept_baseline", "cadence_preset": "hourly"},
        )
        watcher_id = created.get_json()["watcher"]["id"]
        with db_connect() as conn:
            watcher = watcher_service.get_watcher(watcher_id, conn=conn)
            assert watcher is not None
            watcher_service.record_watcher_fire(conn, watcher, run_id="run_accept_latest", state_at_fire="changed")
            conn.execute(
                "UPDATE watchers SET state = 'changed', state_reason = 'diff', consecutive_changed = 2 WHERE id = ?",
                (watcher_id,),
            )
            conn.commit()

        accepted = client.post(f"/watchers/{watcher_id}/accept-baseline", headers={"X-Session-ID": token}, json={})

        assert accepted.status_code == 200
        payload = accepted.get_json()["watcher"]
        assert payload["baseline_run_id"] == "run_accept_latest"
        assert payload["state"] == "ok"
        assert payload["state_reason"] == ""
        assert payload["consecutive_changed"] == 0

    def test_watcher_run_now_keeps_same_command_fire_audits_separate(self, monkeypatch, tmp_path):
        from services.scheduler import dispatch

        client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_watcher_run_now"
        _register_token(token)
        _insert_completed_run(token, "run_first_baseline", command="nmap -sV darklab.sh")
        _insert_completed_run(token, "run_second_baseline", command="nmap -sV darklab.sh")
        first = client.post(
            "/watchers",
            headers={"X-Session-ID": token},
            json={"baseline_run_id": "run_first_baseline", "cadence_preset": "hourly"},
        ).get_json()["watcher"]
        second = client.post(
            "/watchers",
            headers={"X-Session-ID": token},
            json={"baseline_run_id": "run_second_baseline", "cadence_preset": "hourly"},
        ).get_json()["watcher"]
        monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda schedule: f"run_fire_{schedule.owner_id[-8:]}")

        fired = client.post(f"/watchers/{first['id']}/run-now", headers={"X-Session-ID": token})
        first_fires = client.get(f"/watchers/{first['id']}/fires", headers={"X-Session-ID": token})
        second_fires = client.get(f"/watchers/{second['id']}/fires", headers={"X-Session-ID": token})

        assert fired.status_code == 200
        assert fired.get_json()["status"] == "fired"
        assert fired.get_json()["watcher"]["state"] == "firing"
        assert first_fires.status_code == 200
        assert first_fires.get_json()["total"] == 1
        assert first_fires.get_json()["fires"][0]["watcher_id"] == first["id"]
        assert second_fires.status_code == 200
        assert second_fires.get_json()["total"] == 0


class TestWatchBuiltin:
    def test_watch_builtin_create_list_info_and_state_changes(self, monkeypatch, tmp_path):
        _client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_watch_builtin"
        baseline_run_id = "run_watch_builtin_baseline"
        _insert_completed_run(token, baseline_run_id, command="nmap -sV darklab.sh")

        lines, exit_code = execute_builtin_command(
            f'watch create {baseline_run_id} --every hourly --label "Nmap drift"',
            token,
        )
        assert exit_code == 0
        assert "watch: created wtr_" in lines[0]["text"]
        with db_connect() as conn:
            row = conn.execute(
                "SELECT w.id, w.schedule_id, w.baseline_run_id, s.owner_kind, s.enabled "
                "FROM watchers w JOIN schedules s ON s.id = w.schedule_id "
                "WHERE w.session_token = ?",
                (token,),
            ).fetchone()
        watcher_id = row["id"]
        assert row["baseline_run_id"] == baseline_run_id
        assert row["owner_kind"] == "watcher"
        assert row["enabled"] == 1

        listed, _ = execute_builtin_command("watch list", token)
        assert any(watcher_id in line["text"] and "Nmap drift" in line["text"] for line in listed)

        info, _ = execute_builtin_command(f"watch info {watcher_id}", token)
        assert any("baseline run" in line["text"] and baseline_run_id in line["text"] for line in info)
        assert any("command" in line["text"] and "nmap -sV darklab.sh" in line["text"] for line in info)

        paused, _ = execute_builtin_command(f"watch pause {watcher_id}", token)
        assert paused[0]["text"] == f"watch: paused {watcher_id}"
        with db_connect() as conn:
            paused_row = conn.execute(
                "SELECT w.state, s.enabled FROM watchers w JOIN schedules s ON s.id = w.schedule_id WHERE w.id = ?",
                (watcher_id,),
            ).fetchone()
        assert paused_row["state"] == "paused"
        assert paused_row["enabled"] == 0

        resumed, _ = execute_builtin_command(f"watch resume {watcher_id}", token)
        assert resumed[0]["text"] == f"watch: resumed {watcher_id}"

        deleted, _ = execute_builtin_command(f"watch delete {watcher_id}", token)
        assert deleted[0]["text"] == f"watch: deleted {watcher_id}"
        schedule_id = row["schedule_id"]
        with db_connect() as conn:
            watcher_count = conn.execute("SELECT COUNT(*) AS count FROM watchers WHERE id = ?", (watcher_id,)).fetchone()
            schedule_count = conn.execute("SELECT COUNT(*) AS count FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        assert watcher_count["count"] == 0
        assert schedule_count["count"] == 0

    def test_watch_builtin_validates_baseline_and_command_policy(self, monkeypatch, tmp_path):
        _client, _db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_watch_builtin_validation"
        _insert_completed_run(token, "run_watch_unfinished", finished=None)
        _insert_completed_run(token, "run_watch_disallowed", command="rm -rf /")

        missing, _ = execute_builtin_command("watch create run_missing --every hourly", token)
        unfinished, _ = execute_builtin_command("watch create run_watch_unfinished --every hourly", token)
        disallowed, _ = execute_builtin_command("watch create run_watch_disallowed --every hourly", token)

        assert missing[0]["text"] == "watch: baseline run not found: run_missing"
        assert unfinished[0]["text"] == "watch: baseline run must be completed"
        assert "Command not allowed" in disallowed[0]["text"]
        with db_connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM watchers WHERE session_token = ?", (token,)).fetchone()
        assert count["count"] == 0

    def test_watch_builtin_run_records_fire_and_accepts_latest_baseline(self, monkeypatch, tmp_path):
        from services.scheduler import dispatch

        _client, db_path = _schedule_client(monkeypatch, tmp_path)
        token = "tok_watch_builtin_run"
        baseline_run_id = "run_watch_fire_baseline"
        _register_token(token)
        _insert_completed_run(token, baseline_run_id)
        monkeypatch.setattr(dispatch, "_launch_user_schedule_run", lambda schedule: f"run_fire_{schedule.owner_id[-8:]}")
        execute_builtin_command(f"watch create {baseline_run_id} --cron \"0 * * * *\"", token)
        with db_connect() as conn:
            watcher_id = conn.execute("SELECT id FROM watchers WHERE session_token = ?", (token,)).fetchone()["id"]

        fired, exit_code = execute_builtin_command(f"watch run {watcher_id}", token)

        assert exit_code == 0
        assert fired[0]["text"] == f"watch: fired {watcher_id}"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT watcher_id, baseline_run_id, state_at_fire FROM watcher_fires WHERE watcher_id = ?",
            (watcher_id,),
        ).fetchone()
        conn.close()
        assert dict(row) == {
            "watcher_id": watcher_id,
            "baseline_run_id": baseline_run_id,
            "state_at_fire": "firing",
        }

        accepted, _ = execute_builtin_command(f"watch accept {watcher_id}", token)

        assert accepted[0]["text"].startswith("watch: accepted baseline run_fire_")
        with db_connect() as conn:
            baseline_row = conn.execute("SELECT baseline_run_id, state FROM watchers WHERE id = ?", (watcher_id,)).fetchone()
        assert baseline_row["baseline_run_id"].startswith("run_fire_")
        assert baseline_row["state"] == "ok"

    def test_watch_builtin_requires_durable_session_token(self, monkeypatch, tmp_path):
        _client, _db_path = _schedule_client(monkeypatch, tmp_path)

        lines, exit_code = execute_builtin_command("watch list", "anonymous-session")

        assert exit_code == 0
        assert lines[0]["text"] == "watch: persistent session token required. Run `session-token generate` first."


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
            conn.execute(
                "UPDATE schedules SET last_error = ?, consecutive_failures = ? WHERE id = ?",
                ("scanner failed", 3, schedule_id),
            )
            conn.commit()
        assert paused_row["enabled"] == 0
        assert paused_row["paused_reason"] == "paused"

        resumed, _ = execute_builtin_command(f"schedule resume {schedule_id}", token)
        assert resumed[0]["text"] == f"schedule: resumed {schedule_id}"
        with db_connect() as conn:
            resumed_row = conn.execute(
                "SELECT enabled, last_error, consecutive_failures FROM schedules WHERE id = ?",
                (schedule_id,),
            ).fetchone()
        assert resumed_row["enabled"] == 1
        assert resumed_row["last_error"] == ""
        assert resumed_row["consecutive_failures"] == 0

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
