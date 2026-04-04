"""
Higher-value route coverage focused on streaming /run behaviour,
history isolation, and share JSON roundtrips.

These tests are intentionally closer to "real bug finding" than
the lighter smoke tests in test_routes.py.
"""

import json
import uuid
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import pytest

import app as shell_app
import database as shell_db
from database import db_connect


def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
    client = shell_app.app.test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


@pytest.fixture(autouse=True)
def isolated_history_db(monkeypatch, tmp_path):
    monkeypatch.setattr(shell_db, "DB_PATH", str(tmp_path / "history.db"))
    shell_db.db_init()


# ── Helpers ──────────────────────────────────────────────────────────────────

class _FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else ""

    def close(self):
        pass


class _FakeProc:
    def __init__(self, lines=None, pid=4321, returncode=0):
        self.pid = pid
        self.returncode = returncode
        self.stdout = _FakeStdout(lines or [])
        self._poll_calls = 0

    def wait(self):
        return self.returncode

    def poll(self):
        # Behave like a still-running proc until stdout is exhausted
        self._poll_calls += 1
        if getattr(self.stdout, "_lines", []):
            return None
        return self.returncode


# ── /run streaming ────────────────────────────────────────────────────────────

class TestRunStreaming:
    def test_run_emits_started_notice_output_and_exit(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n", "world\n", ""])

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.rewrite_command", return_value=("echo hello", "rewritten for safety")), \
             mock.patch("app.subprocess.Popen", return_value=fake_proc), \
             mock.patch("app.pid_register"), \
             mock.patch("app.pid_pop"), \
             mock.patch("app.select.select", side_effect=[
                 ([fake_proc.stdout], [], []),
                 ([fake_proc.stdout], [], []),
                 ([fake_proc.stdout], [], []),
             ]):
            resp = client.post("/run", json={"command": "echo hello"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "notice"' in body
        assert '"type": "output"' in body
        assert '"type": "exit"' in body
        assert "hello\\n" in body
        assert "world\\n" in body

    def test_run_returns_500_when_spawn_fails(self):
        client = get_client()

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.subprocess.Popen", side_effect=OSError("boom")):
            resp = client.post("/run", json={"command": "echo hi"})

        assert resp.status_code == 500
        data = json.loads(resp.data)
        assert "error" in data
        assert "boom" in data["error"]

    def test_run_emits_heartbeat_when_silent(self):
        client = get_client()
        fake_proc = _FakeProc(lines=[""])

        # First select() timeout => heartbeat, second => EOF break
        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.subprocess.Popen", return_value=fake_proc), \
             mock.patch("app.pid_register"), \
             mock.patch("app.pid_pop"), \
             mock.patch("app.select.select", side_effect=[
                 ([], [], []),                  # heartbeat branch
                 ([fake_proc.stdout], [], []),  # then EOF
             ]), \
             mock.patch("app.CFG", {**shell_app.CFG, "heartbeat_interval_seconds": 0}):
            resp = client.post("/run", json={"command": "sleep 1"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert ": heartbeat" in body
        assert '"type": "started"' in body
        assert '"type": "exit"' in body

    def test_run_persists_completed_run_to_history(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["saved line\n", ""])

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.subprocess.Popen", return_value=fake_proc), \
             mock.patch("app.pid_register"), \
             mock.patch("app.pid_pop"), \
             mock.patch("app.select.select", side_effect=[
                 ([fake_proc.stdout], [], []),
                 ([fake_proc.stdout], [], []),
             ]):
            resp = client.post("/run", json={"command": "echo saved"}, headers={"X-Session-ID": "sess-save"})
            _ = resp.get_data(as_text=True)

        hist = client.get("/history", headers={"X-Session-ID": "sess-save"})
        data = json.loads(hist.data)
        cmds = [r["command"] for r in data["runs"]]
        assert "echo saved" in cmds

    def test_run_emits_timeout_notice_when_command_exceeds_limit(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["still running\n"], returncode=-15)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        finish = start + timedelta(seconds=2)

        class _FakeDateTime:
            _now_values = iter([start, finish, finish])

            @staticmethod
            def now(_tz=None):
                return next(_FakeDateTime._now_values)

            @staticmethod
            def fromisoformat(value):
                return datetime.fromisoformat(value)

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.subprocess.Popen", return_value=fake_proc), \
             mock.patch("app.pid_register"), \
             mock.patch("app.pid_pop"), \
             mock.patch("app.datetime", _FakeDateTime), \
             mock.patch("app.os.getpgid", return_value=4321), \
             mock.patch("app.os.killpg") as killpg, \
             mock.patch("app.CFG", {**shell_app.CFG, "command_timeout_seconds": 1}):
            resp = client.post("/run", json={"command": "sleep forever"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "[timeout] Command exceeded 1s limit and was killed." in body
        assert '"type": "notice"' in body
        assert '"type": "exit"' in body
        killpg.assert_called_once_with(4321, shell_app.signal.SIGTERM)

    def test_run_still_exits_when_history_save_fails(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["saved line\n", ""])

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.subprocess.Popen", return_value=fake_proc), \
             mock.patch("app.pid_register"), \
             mock.patch("app.pid_pop"), \
             mock.patch("app.select.select", side_effect=[
                 ([fake_proc.stdout], [], []),
                 ([fake_proc.stdout], [], []),
             ]), \
             mock.patch("app.db_connect", side_effect=Exception("db write failed")):
            resp = client.post("/run", json={"command": "echo saved"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "output"' in body
        assert '"type": "exit"' in body


# ── /history isolation ────────────────────────────────────────────────────────

class TestHistoryIsolation:
    def test_history_only_returns_runs_for_current_session(self):
        client = get_client()
        run_a = f"hist-a-{uuid.uuid4()}"
        run_b = f"hist-b-{uuid.uuid4()}"

        try:
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
                    (run_a, "session-a", "echo A", 0, "[]")
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
                    (run_b, "session-b", "echo B", 0, "[]")
                )
                conn.commit()

            resp = client.get("/history", headers={"X-Session-ID": "session-a"})
            data = json.loads(resp.data)
            commands = [r["command"] for r in data["runs"]]

            assert "echo A" in commands
            assert "echo B" not in commands
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id IN (?, ?)", (run_a, run_b))
                conn.commit()

    def test_delete_run_only_deletes_for_matching_session(self):
        client = get_client()
        run_id = f"owned-run-{uuid.uuid4()}"

        try:
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
                    (run_id, "owner-session", "echo owner", 0, "[]")
                )
                conn.commit()

            # Wrong session should not delete
            resp = client.delete(f"/history/{run_id}", headers={"X-Session-ID": "other-session"})
            assert resp.status_code == 200

            with db_connect() as conn:
                row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            assert row is not None

            # Correct session should delete
            resp = client.delete(f"/history/{run_id}", headers={"X-Session-ID": "owner-session"})
            assert resp.status_code == 200

            with db_connect() as conn:
                row = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            assert row is None
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()


# ── /share ────────────────────────────────────────────────────────────────────

class TestShareRoundTrip:
    def test_share_json_roundtrip_preserves_structured_content(self):
        client = get_client()
        payload = {
            "label": "test snapshot",
            "content": [
                {"text": "$ echo hi", "cls": "cmd"},
                {"text": "hi", "cls": "out"},
                {"text": "done", "cls": "notice"},
            ],
        }

        resp = client.post("/share", json=payload, headers={"X-Session-ID": "share-session"})
        assert resp.status_code == 200
        created = json.loads(resp.data)
        assert "id" in created

        fetch = client.get(f"/share/{created['id']}?json")
        assert fetch.status_code == 200
        data = json.loads(fetch.data)

        assert data["label"] == "test snapshot"
        assert data["content"] == payload["content"]
        assert data["session_id"] == "share-session"
