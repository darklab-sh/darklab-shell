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
        token = uuid.uuid4().hex
        client.environ_base["HTTP_X_FORWARDED_FOR"] = (
            f"2001:db8:{token[0:4]}:{token[4:8]}:{token[8:12]}:{token[12:16]}:{token[16:20]}:{token[20:24]}"
        )
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
    @staticmethod
    def _local_dt_text(value: str) -> str:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _local_clock_text(value: str) -> str:
        return datetime.fromisoformat(value).astimezone().strftime("%H:%M:%S")

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

    def test_fake_env_returns_web_environment(self):
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
        assert "Web shell helpers:\\n" in body
        assert "banner     Print the configured ASCII banner without replaying welcome.\\n" in body
        assert "clear      Clear the current terminal tab output.\\n" in body
        assert "date       Show the current server time.\\n" in body
        assert "env        Show the web shell environment variables.\\n" in body
        assert "faq        Show configured FAQ entries inside the terminal.\\n" in body
        assert "fortune    Print a short operator-themed one-liner.\\n" in body
        assert "groups     Show the web shell group membership.\\n" in body
        assert "help       Show web shell helpers available in this app.\\n" in body
        assert "history    Show recent commands from this session.\\n" in body
        assert "hostname   Show the instance hostname/app name.\\n" in body
        assert "keys       Show current and planned keyboard shortcuts.\\n" in body
        assert "limits     Show configured runtime and retention limits.\\n" in body
        assert "man <cmd>  Show the real man page for an allowed command.\\n" in body
        assert "last       Show recent completed runs with timestamps and exit codes.\\n" in body
        assert "retention  Show retention and full-output persistence settings.\\n" in body
        assert "status     Summarize the current session and instance settings.\\n" in body
        assert "tty        Show the web terminal device path.\\n" in body
        assert "type <cmd> Describe whether a command is a helper command, real command, or missing.\\n" in body
        assert "uname -a   Describe the web shell environment.\\n" in body
        assert "uptime     Show app uptime since process start.\\n" in body
        assert "version    Show web shell, app, Flask, and Python version details.\\n" in body
        assert "which <cmd> Locate a web helper or real command.\\n" in body
        assert "who        Show the current web shell user/session.\\n" in body
        assert '"type": "exit"' in body

    def test_fake_keys_lists_current_and_planned_shortcuts(self):
        client = get_client()

        resp = client.post("/run", json={"command": "keys"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Current shortcuts:\\n" in body
        assert "Alt+T" in body
        assert "Option+Shift+C" in body
        assert "Ctrl+U" in body
        assert "Planned shortcuts:\\n" in body
        assert "browser Command shortcuts remain environment-dependent" in body
        assert '"type": "exit"' in body

    def test_fake_banner_renders_ascii_art(self):
        client = get_client()

        with mock.patch("fake_commands.load_ascii_art", return_value="line one\nline two"):
            resp = client.post("/run", json={"command": "banner"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "line one\\n" in body
        assert "line two\\n" in body
        assert '"type": "exit"' in body

    def test_fake_which_and_type_describe_commands(self):
        client = get_client()

        with mock.patch("fake_commands.resolve_runtime_command", return_value="/usr/bin/curl"):
            which_resp = client.post("/run", json={"command": "which curl"})
            which_body = which_resp.get_data(as_text=True)
            type_resp = client.post("/run", json={"command": "type history"})
            type_body = type_resp.get_data(as_text=True)

        assert which_resp.status_code == 200
        assert "/usr/bin/curl\\n" in which_body
        assert type_resp.status_code == 200
        assert "history is a helper command\\n" in type_body

    def test_fake_limits_and_status_show_configuration(self):
        client = get_client()

        with mock.patch("fake_commands.CFG", {**shell_app.CFG, "max_tabs": 4, "permalink_retention_days": 365}):
            limits_resp = client.post("/run", json={"command": "limits"}, headers={"X-Session-ID": "sess-limits"})
            limits_body = limits_resp.get_data(as_text=True)
            status_resp = client.post("/run", json={"command": "status"}, headers={"X-Session-ID": "sess-limits"})
            status_body = status_resp.get_data(as_text=True)

        assert limits_resp.status_code == 200
        assert "live preview lines" in limits_body
        assert f"{shell_app.CFG['max_output_lines']}\\n" in limits_body
        assert status_resp.status_code == 200
        assert "session" in status_body
        assert "sess-limits\\n" in status_body
        assert "tab limit" in status_body
        assert "4\\n" in status_body
        assert "retention" in status_body
        assert "365\\n" in status_body

    def test_fake_last_lists_recent_completed_runs(self):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-last-1", "sess-last", "ping darklab.sh", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "run-last-2", "sess-last", "dig darklab.sh A",
                    "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 1, "[]",
                )
            )
            conn.commit()

        resp = client.post("/run", json={"command": "last"}, headers={"X-Session-ID": "sess-last"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert f"{self._local_dt_text('2026-01-01T00:00:05+00:00')}  [1]  dig darklab.sh A\\n" in body
        assert f"{self._local_dt_text('2026-01-01T00:00:00+00:00')}  [0]  ping darklab.sh\\n" in body

    def test_fake_who_tty_groups_and_version_render_shell_identity(self):
        client = get_client()

        who_resp = client.post("/run", json={"command": "who"}, headers={"X-Session-ID": "sess-who"})
        who_body = who_resp.get_data(as_text=True)
        tty_resp = client.post("/run", json={"command": "tty"})
        tty_body = tty_resp.get_data(as_text=True)
        groups_resp = client.post("/run", json={"command": "groups"})
        groups_body = groups_resp.get_data(as_text=True)
        version_resp = client.post("/run", json={"command": "version"})
        version_body = version_resp.get_data(as_text=True)

        assert who_resp.status_code == 200
        assert "shell.darklab.sh  pts/web  sess-who\\n" in who_body
        assert tty_resp.status_code == 200
        assert "/dev/pts/web\\n" in tty_body
        assert groups_resp.status_code == 200
        assert "shell.darklab.sh operators\\n" in groups_body
        assert version_resp.status_code == 200
        assert "shell.darklab.sh web shell\\n" in version_body
        assert f"App {shell_app.APP_VERSION}\\n" in version_body
        assert "Flask " in version_body
        assert "Python " in version_body

    def test_fake_faq_renders_builtin_and_configured_entries(self):
        client = get_client()

        with mock.patch("fake_commands.load_all_faq", return_value=[
            {"question": "Built-in question?", "answer": "Built-in answer."},
            {"question": "What is this?", "answer": "A synthetic shell."},
            {"question": "How do I stop a command?", "answer": "Use Kill."},
        ]):
            resp = client.post("/run", json={"command": "faq"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Configured FAQ entries:\\n" in body
        assert "Q: Built-in question?\\n" in body
        assert "A: Built-in answer.\\n" in body
        assert "Q: What is this?\\n" in body
        assert "A: A synthetic shell.\\n" in body
        assert "Q: How do I stop a command?\\n" in body
        assert "A: Use Kill.\\n" in body

    def test_fake_retention_reports_preview_and_full_output_policy(self):
        client = get_client()

        with mock.patch("fake_commands.CFG", {
            **shell_app.CFG,
            "permalink_retention_days": 365,
            "persist_full_run_output": True,
            "full_output_max_bytes": 5242880,
        }):
            resp = client.post("/run", json={"command": "retention"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Retention policy:\\n" in body
        assert "run preview retention  365 days\\n" in body
        assert "full output save       yes\\n" in body
        assert "full output max        5242880 bytes\\n" in body

    def test_fake_fortune_returns_configured_line(self):
        client = get_client()

        with mock.patch("fake_commands.random.choice", return_value="Trust the output, not the hunch."):
            resp = client.post("/run", json={"command": "fortune"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Trust the output, not the hunch.\\n" in body

    def test_fake_sudo_reports_web_shell_restriction(self):
        client = get_client()

        resp = client.post("/run", json={"command": "sudo ping darklab.sh"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "sudo: 'ping darklab.sh' is not happening today.\\n" in body

    def test_fake_reboot_reports_web_shell_restriction(self):
        client = get_client()

        resp = client.post("/run", json={"command": "reboot"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "reboot: bold choice.\\n" in body
        assert "If this web shell could reboot the host, we would both have bigger problems.\\n" in body

    def test_fake_rm_root_refuses_exact_root_delete_pattern(self):
        client = get_client()

        resp = client.post("/run", json={"command": "rm -fr /"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "rm: nice try.\\n" in body
        assert "Even this web shell has standards.\\n" in body

    def test_fake_date_hostname_and_uptime_render_shell_style_information(self):
        client = get_client()

        date_resp = client.post("/run", json={"command": "date"})
        date_body = date_resp.get_data(as_text=True)
        host_resp = client.post("/run", json={"command": "hostname"})
        host_body = host_resp.get_data(as_text=True)
        uptime_resp = client.post("/run", json={"command": "uptime"})
        uptime_body = uptime_resp.get_data(as_text=True)

        assert date_resp.status_code == 200
        assert '"type": "output"' in date_body
        assert host_resp.status_code == 200
        assert "shell.darklab.sh\\n" in host_body
        assert uptime_resp.status_code == 200
        assert "up " in uptime_body

    def test_fake_man_renders_real_page_for_allowed_topic(self):
        client = get_client()

        fake_proc = mock.Mock(returncode=0, stdout="NAME\ncurl - transfer a URL\n", stderr="")
        with mock.patch("fake_commands.runtime_missing_command_name", side_effect=[None, None]), \
             mock.patch("fake_commands.resolve_runtime_command", return_value="/usr/bin/man"), \
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
             mock.patch("fake_commands.resolve_runtime_command", return_value="/usr/bin/man"), \
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
             mock.patch("fake_commands.resolve_runtime_command", return_value="/usr/bin/man"), \
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

    def test_fake_man_for_helper_topic_returns_web_shell_help(self):
        client = get_client()

        resp = client.post("/run", json={"command": "man history"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Web shell helpers:\\n" in body
        assert "history    Show recent commands from this session.\\n" in body

    def test_fake_man_for_keys_topic_returns_web_shell_help(self):
        client = get_client()

        resp = client.post("/run", json={"command": "man keys"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "Web shell helpers:\\n" in body
        assert "keys       Show current and planned keyboard shortcuts.\\n" in body
        assert '"type": "exit"' in body

    def test_fake_history_lists_recent_session_commands(self):
        client = get_client()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-h1", "sess-history", "ping darklab.sh", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-h2", "sess-history", "dig darklab.sh A", "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 0, "[]")
            )
            conn.commit()

        resp = client.post("/run", json={"command": "history"}, headers={"X-Session-ID": "sess-history"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "1  ping darklab.sh\\n" in body
        assert "2  dig darklab.sh A\\n" in body
        assert '"type": "exit"' in body

    def test_fake_pwd_returns_synthetic_path(self):
        client = get_client()

        resp = client.post("/run", json={"command": "pwd"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "/app/shell.darklab.sh/bin\\n" in body
        assert '"type": "exit"' in body

    def test_fake_uname_a_returns_web_shell_environment(self):
        client = get_client()

        resp = client.post("/run", json={"command": "uname -a"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "shell.darklab.sh Linux web-terminal x86_64 app-runtime\\n" in body
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
                ("run-1", "sess-ps", "ping darklab.sh", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00", 0, "[]")
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("run-2", "sess-ps", "dig darklab.sh A", "2026-01-01T00:00:05+00:00", "2026-01-01T00:00:06+00:00", 0, "[]")
            )
            conn.commit()

        resp = client.post("/run", json={"command": "ps aux"}, headers={"X-Session-ID": "sess-ps"})
        body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "PID TTY      EXIT START    END      CMD\\n" in body
        assert " 9000 pts/0    -    -        -        ps aux\\n" in body
        assert (
            f"pts/0    0    {self._local_clock_text('2026-01-01T00:00:05+00:00')} "
            f"{self._local_clock_text('2026-01-01T00:00:06+00:00')} dig darklab.sh A\\n"
        ) in body
        assert (
            f"pts/0    0    {self._local_clock_text('2026-01-01T00:00:00+00:00')} "
            f"{self._local_clock_text('2026-01-01T00:00:03+00:00')} ping darklab.sh\\n"
        ) in body
        assert '"type": "exit"' in body

    def test_run_reports_missing_allowlisted_command_without_spawning(self):
        client = get_client()

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.rewrite_command", return_value=("nmap -sV darklab.sh", None)), \
             mock.patch("app.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("app.subprocess.Popen") as popen:
            resp = client.post("/run", json={"command": "nmap -sV darklab.sh"}, headers={"X-Session-ID": "sess-missing"})
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert "Command is not installed on this instance: nmap\\n" in body
        assert '"type": "exit"' in body
        popen.assert_not_called()

        hist = client.get("/history", headers={"X-Session-ID": "sess-missing"})
        data = json.loads(hist.data)
        assert [r["command"] for r in data["runs"]] == ["nmap -sV darklab.sh"]

    def test_run_checks_missing_binary_after_rewrite(self):
        client = get_client()
        client.environ_base["HTTP_X_FORWARDED_FOR"] = "2001:db8:ffff:eeee:dddd:cccc:bbbb:aaaa"

        with mock.patch("app.is_command_allowed", return_value=(True, "")), \
             mock.patch("app.rewrite_command", return_value=("nmap --privileged -sV darklab.sh", None)), \
             mock.patch("app.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("app.subprocess.Popen") as popen:
            resp = client.post("/run", json={"command": "nmap -sV darklab.sh"})
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
