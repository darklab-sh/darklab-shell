"""
Higher-value route coverage focused on streaming /run behaviour,
history isolation, and share JSON roundtrips.

These tests are intentionally closer to "real bug finding" than
the lighter smoke tests in test_routes.py.
"""

import gzip
import json
import os
import uuid
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import pytest

import app as shell_app
import database as shell_db
from database import db_connect
from run_output_store import RUN_OUTPUT_DIR, ensure_run_output_dir


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

    def test_fake_ls_streams_allowed_commands_and_persists_history(self):
        client = get_client()

        with mock.patch("fake_commands.load_allowed_commands_grouped", return_value=[
            {"name": "Networking", "commands": ["ping", "dig"]},
        ]):
            resp = client.post("/run", json={"command": "ls"}, headers={"X-Session-ID": "sess-fake-ls"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "output"' in body
        assert "[Networking]\\n" in body
        assert "ping\\n" in body
        assert "dig\\n" in body
        assert '"type": "exit"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-fake-ls"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["ls"]

    def test_fake_clear_emits_clear_event_and_persists_history(self):
        client = get_client()

        resp = client.post("/run", json={"command": "clear"}, headers={"X-Session-ID": "sess-clear"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert '"type": "clear"' in body
        assert '"type": "exit"' in body

        hist = client.get("/history", headers={"X-Session-ID": "sess-clear"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["clear"]

    def test_fake_env_returns_synthetic_environment(self):
        client = get_client()

        resp = client.post("/run", json={"command": "env"}, headers={"X-Session-ID": "sess-env"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "APP_NAME=shell.darklab.sh\\n" in body
        assert "SESSION_ID=sess-env\\n" in body
        assert "SHELL=/shell.darklab.sh\\n" in body
        assert "TERM=xterm-256color\\n" in body
        assert '"type": "exit"' in body

    def test_fake_help_lists_available_helpers(self):
        client = get_client()

        resp = client.post("/run", json={"command": "help"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Synthetic shell helpers:\\n" in body
        assert "clear      Clear the current terminal tab output.\\n" in body
        assert "env        Show the synthetic shell environment variables.\\n" in body
        assert "help       Show synthetic shell helpers available in this app.\\n" in body
        assert "history    Show recent commands from this session.\\n" in body
        assert "man <cmd>  Show the real man page for an allowed command.\\n" in body
        assert "uname -a   Describe the synthetic shell environment.\\n" in body
        assert '"type": "exit"' in body

    def test_fake_man_renders_real_page_for_allowed_topic(self):
        client = get_client()

        fake_proc = mock.Mock(returncode=0, stdout="NAME\ncurl - transfer a URL\n", stderr="")
        with mock.patch("fake_commands.runtime_missing_command_name", side_effect=[None, None]), \
             mock.patch("fake_commands.subprocess.run", return_value=fake_proc):
            resp = client.post("/run", json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "NAME\\n" in body
        assert "curl - transfer a URL\\n" in body
        assert '"type": "exit"' in body

    def test_fake_man_does_not_clip_to_max_output_lines(self):
        client = get_client()
        man_text = "\n".join(f"line {index}" for index in range(1, 6)) + "\n"
        fake_proc = mock.Mock(returncode=0, stdout=man_text, stderr="")
        with mock.patch("fake_commands.runtime_missing_command_name", side_effect=[None, None]), \
             mock.patch("fake_commands.subprocess.run", return_value=fake_proc), \
             mock.patch("fake_commands.CFG", {**shell_app.CFG, "max_output_lines": 2}):
            resp = client.post("/run", json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "line 5\\n" in body
        assert "man page clipped" not in body
        assert '"type": "exit"' in body

    def test_fake_man_reports_when_helper_binary_is_unavailable(self):
        client = get_client()

        with mock.patch("fake_commands.runtime_missing_command_name", return_value="man"):
            resp = client.post("/run", json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Command is not installed on this instance: man\\n" in body
        assert '"type": "exit"' in body

    def test_fake_man_reports_when_allowlisted_topic_is_missing(self):
        client = get_client()

        with mock.patch("fake_commands.runtime_missing_command_name", side_effect=[None, "curl"]), \
             mock.patch("fake_commands.subprocess.run") as run_cmd:
            resp = client.post("/run", json={"command": "man curl"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Command is not installed on this instance: curl\\n" in body
        assert '"type": "exit"' in body
        run_cmd.assert_not_called()

    def test_fake_man_rejects_topics_outside_allowlist(self):
        client = get_client()

        resp = client.post("/run", json={"command": "man rm"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "man is only available for allowed commands. Topic not allowed: rm\\n" in body
        assert '"type": "exit"' in body

    def test_fake_man_for_synthetic_topic_returns_synthetic_help(self):
        client = get_client()

        resp = client.post("/run", json={"command": "man history"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Synthetic shell helpers:\\n" in body
        assert "history    Show recent commands from this session.\\n" in body
        assert '"type": "exit"' in body

    def test_fake_history_lists_recent_session_commands(self):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-h1", "sess-history", "ping example.com", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-h2", "sess-history", "dig example.com A", "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 0, "[]")
            )
            conn.commit()

        resp = client.post("/run", json={"command": "history"}, headers={"X-Session-ID": "sess-history"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "1  ping example.com\\n" in body
        assert "2  dig example.com A\\n" in body
        assert '"type": "exit"' in body

    def test_fake_pwd_returns_synthetic_path(self):
        client = get_client()

        resp = client.post("/run", json={"command": "pwd"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "/shell.darklab.sh\\n" in body
        assert '"type": "exit"' in body

    def test_fake_uname_a_returns_synthetic_environment(self):
        client = get_client()

        resp = client.post("/run", json={"command": "uname -a"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "shell.darklab.sh Linux synthetic-web-terminal x86_64 app-runtime\\n" in body
        assert '"type": "exit"' in body

    def test_fake_id_returns_synthetic_identity(self):
        client = get_client()

        resp = client.post("/run", json={"command": "id"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "uid=1000(shell.darklab.sh) gid=1000(shell.darklab.sh) groups=1000(shell.darklab.sh)\\n" in body
        assert '"type": "exit"' in body

    def test_fake_whoami_streams_project_description(self):
        client = get_client()

        resp = client.post("/run", json={"command": "whoami"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "shell.darklab.sh\\n" in body
        assert "README: https://gitlab.com/darklab.sh/shell.darklab.sh\\n" in body
        assert '"type": "exit"' in body

    def test_fake_ps_lists_recent_session_commands(self):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-1", "sess-ps", "ping example.com", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-2", "sess-ps", "dig example.com A", "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 0, "[]")
            )
            conn.commit()

        resp = client.post("/run", json={"command": "ps aux"}, headers={"X-Session-ID": "sess-ps"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "PID TTY          TIME CMD\\n" in body
        assert "ping example.com\\n" in body
        assert "dig example.com A\\n" in body
        assert '"type": "exit"' in body

    def test_run_reports_missing_allowlisted_command_without_spawning(self):
        client = get_client()

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.rewrite_command", return_value=("nmap -sV example.com", None)), \
             mock.patch("app.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("app.subprocess.Popen") as popen:
            resp = client.post("/run", json={"command": "nmap -sV example.com"}, headers={"X-Session-ID": "sess-missing"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert "Command is not installed on this instance: nmap\\n" in body
        assert '"type": "exit"' in body
        popen.assert_not_called()

        hist = client.get("/history", headers={"X-Session-ID": "sess-missing"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["nmap -sV example.com"]

    def test_run_checks_missing_binary_after_rewrite(self):
        client = get_client()

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.rewrite_command", return_value=("nmap --privileged -sV example.com", None)), \
             mock.patch("app.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("app.subprocess.Popen") as popen:
            resp = client.post("/run", json={"command": "nmap -sV example.com"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Command is not installed on this instance: nmap\\n" in body
        assert '"type": "exit"' in body
        popen.assert_not_called()


class TestRunOutputArtifacts:
    def _insert_run_with_artifact(self, run_id, session_id="sess-artifact"):
        ensure_run_output_dir()
        artifact_path = os.path.join(RUN_OUTPUT_DIR, f"{run_id}.txt.gz")
        with gzip.open(artifact_path, "wt", encoding="utf-8") as handle:
            handle.write("line 1\nline 2\n")

        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, output_preview, preview_truncated, "
                "output_line_count, full_output_available, full_output_truncated) "
                "VALUES (?, ?, ?, datetime('now'), ?, 1, 2, 1, 0)",
                (run_id, session_id, "nmap -sV 10.0.0.1", json.dumps(["line 2"])),
            )
            conn.execute(
                "INSERT INTO run_output_artifacts (run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, 'gzip', 14, 2, 0, datetime('now'))",
                (run_id, f"{run_id}.txt.gz"),
            )
            conn.commit()
        return artifact_path

    def test_delete_run_removes_output_artifact(self):
        client = get_client()
        artifact_path = self._insert_run_with_artifact("artifact-delete-run", session_id="sess-delete-artifact")
        assert os.path.exists(artifact_path)

        resp = client.delete("/history/artifact-delete-run", headers={"X-Session-ID": "sess-delete-artifact"})

        assert resp.status_code == 200
        assert not os.path.exists(artifact_path)
        with db_connect() as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM run_output_artifacts WHERE run_id = ?",
                    ("artifact-delete-run",),
                ).fetchone()
                is None
            )

    def test_clear_history_removes_output_artifacts_for_session(self):
        client = get_client()
        artifact_a = self._insert_run_with_artifact("artifact-clear-a", session_id="sess-clear-artifact")
        artifact_b = self._insert_run_with_artifact("artifact-clear-b", session_id="sess-clear-artifact")
        assert os.path.exists(artifact_a)
        assert os.path.exists(artifact_b)

        resp = client.delete("/history", headers={"X-Session-ID": "sess-clear-artifact"})

        assert resp.status_code == 200
        assert not os.path.exists(artifact_a)
        assert not os.path.exists(artifact_b)
        with db_connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM run_output_artifacts").fetchone()[0] == 0


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
