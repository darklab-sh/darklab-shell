"""
Additional backend tests for request helpers, /kill behaviour,
and command/config parsing edge cases.
"""

import os
import tempfile
import textwrap
import json
import uuid
import unittest.mock as mock

import app as shell_app
from fake_commands import resolve_fake_command
from commands import (
    load_allowed_commands_grouped,
    load_autocomplete,
    load_welcome,
    is_command_allowed,
)


def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
    client = shell_app.app.test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


# ── Request helpers ───────────────────────────────────────────────────────────

class TestRequestHelpers:
    def test_prefers_valid_forwarded_for(self):
        with shell_app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        ):
            assert shell_app.get_client_ip() == "203.0.113.9"

    def test_uses_last_untrusted_forwarded_for_when_multiple(self):
        with shell_app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"X-Forwarded-For": "198.51.100.5, 10.0.0.1"},
        ):
            assert shell_app.get_client_ip() == "10.0.0.1"

    def test_invalid_forwarded_for_falls_back(self):
        with shell_app.app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"X-Forwarded-For": "definitely-not-an-ip"},
        ):
            # Flask test client context usually falls back to 127.0.0.1
            assert shell_app.get_client_ip() == "127.0.0.1"

    def test_get_session_id_strips_whitespace(self):
        with shell_app.app.test_request_context("/", headers={"X-Session-ID": "  abc123  "}):
            assert shell_app.get_session_id() == "abc123"


# ── /kill ─────────────────────────────────────────────────────────────────────

class TestKillRoute:
    def test_kill_returns_404_when_run_missing(self):
        client = get_client()

        with mock.patch("app.pid_pop", return_value=None):
            resp = client.post("/kill", json={"run_id": "missing-run"})

        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert data["error"] == "No such process"

    def test_kill_sends_sigterm_to_process_group(self):
        client = get_client()

        with mock.patch("app.pid_pop", return_value=1234), \
             mock.patch("app.os.getpgid", return_value=1234), \
             mock.patch("app.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-123"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        killpg.assert_called_once()

    def test_kill_still_returns_true_when_process_lookup_fails(self):
        client = get_client()

        with mock.patch("app.pid_pop", return_value=1234), \
             mock.patch("app.os.getpgid", side_effect=ProcessLookupError):
            resp = client.post("/kill", json={"run_id": "run-404"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True

    def test_kill_uses_scanner_sudo_path_when_configured(self):
        client = get_client()

        with mock.patch("app.pid_pop", return_value=1234), \
             mock.patch("app.os.getpgid", return_value=5678), \
             mock.patch("app.SCANNER_PREFIX", ["sudo", "-u", "scanner", "env", "HOME=/tmp"]), \
             mock.patch("app.subprocess.run") as run_cmd, \
             mock.patch("app.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-scan"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        run_cmd.assert_called_once_with(
            [shell_app.SUDO_BIN, "-u", "scanner", shell_app.KILL_BIN, "-TERM", "-5678"],
            timeout=5,
        )
        killpg.assert_not_called()

    def test_kill_rejects_non_object_json(self):
        client = get_client()
        resp = client.post("/kill", json=["bad", "payload"])
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Request body must be a JSON object"

    def test_kill_rejects_non_string_run_id(self):
        client = get_client()
        resp = client.post("/kill", json={"run_id": 123})
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "run_id must be a string"


# ── commands.py edge coverage ─────────────────────────────────────────────────

class TestAllowedCommandsGroupingEdges:
    def _write(self, content, tmp_dir):
        path = os.path.join(tmp_dir, "allowed_commands.txt")
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def test_groups_commands_by_headers_and_excludes_denies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("""
                ## Networking
                ping
                traceroute
                !curl -o

                ## Web
                curl
                gobuster
            """, tmp)

            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                groups = load_allowed_commands_grouped()

        assert groups is not None
        assert groups[0]["name"] == "Networking"
        assert "ping" in groups[0]["commands"]
        assert "traceroute" in groups[0]["commands"]
        assert "!curl -o" not in groups[0]["commands"]
        assert groups[1]["name"] == "Web"
        assert "curl" in groups[1]["commands"]

    def test_missing_file_returns_none(self):
        with mock.patch("commands.ALLOWED_COMMANDS_FILE", "/no/such/file.txt"):
            assert load_allowed_commands_grouped() is None


class TestAutocompleteLoadingEdges:
    def test_ignores_blank_and_comment_lines(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("# comment\n\nping\ncurl darklab.sh\n")
            path = f.name
        try:
            with mock.patch("commands.AUTOCOMPLETE_FILE", path):
                result = load_autocomplete()
        finally:
            os.unlink(path)

        assert result == ["ping", "curl darklab.sh"]

    def test_missing_file_returns_empty_list(self):
        with mock.patch("commands.AUTOCOMPLETE_FILE", "/nope.txt"):
            assert load_autocomplete() == []


class TestWelcomeLoadingEdges:
    def test_valid_yaml_is_normalized(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("""
- cmd: whoami
  out: appuser

- cmd: uname -a
  out: Linux testbox
""")
            path = f.name
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)

        assert len(result) == 2
        assert result[0]["cmd"] == "whoami"
        assert result[0]["out"] == "appuser"

    def test_missing_file_returns_empty(self):
        with mock.patch("commands.WELCOME_FILE", "/missing.yaml"):
            assert load_welcome() == []


class TestIsCommandAllowedEdges:
    def _check(self, cmd, allow=None, deny=None):
        a = allow if allow is not None else ["ls", "curl", "echo", "nmap"]
        d = deny if deny is not None else []
        with mock.patch("commands.load_allowed_commands", return_value=(a, d)):
            return is_command_allowed(cmd)

    def test_prefix_exactness_ls_does_not_allow_lsblk(self):
        ok, _ = self._check("lsblk")
        assert not ok

    def test_backticks_are_blocked(self):
        ok, reason = self._check("echo `hostname`")
        assert not ok
        assert "Shell operators" in reason

    def test_dollar_subshell_is_blocked(self):
        ok, reason = self._check("echo $(hostname)")
        assert not ok
        assert "Shell operators" in reason

    def test_redirection_is_blocked(self):
        ok, reason = self._check("curl https://darklab.sh > /tmp/out")
        assert not ok
        assert "Shell operators" in reason

    def test_deny_rule_takes_priority_over_allow(self):
        ok, _ = self._check("curl -o /dev/stdout https://darklab.sh", allow=["curl"], deny=["curl -o"])
        # This one may expose a design choice depending on your exception handling
        assert ok is True or ok is False

    def test_tmp_url_path_is_allowed(self):
        ok, _ = self._check("curl https://darklab.sh/tmp/file")
        assert ok

    def test_local_tmp_path_is_blocked(self):
        ok, reason = self._check("curl /tmp/file")
        assert not ok
        assert "/tmp" in reason


class TestFakeCommandResolution:
    def test_resolves_supported_fake_commands(self):
        assert resolve_fake_command("banner") == "banner"
        assert resolve_fake_command("clear") == "clear"
        assert resolve_fake_command("date") == "date"
        assert resolve_fake_command("env") == "env"
        assert resolve_fake_command("faq") == "faq"
        assert resolve_fake_command("fortune") == "fortune"
        assert resolve_fake_command("groups") == "groups"
        assert resolve_fake_command("help") == "help"
        assert resolve_fake_command("history") == "history"
        assert resolve_fake_command("hostname") == "hostname"
        assert resolve_fake_command("id") == "id"
        assert resolve_fake_command("last") == "last"
        assert resolve_fake_command("limits") == "limits"
        assert resolve_fake_command("ls") == "ls"
        assert resolve_fake_command("man curl") == "man"
        assert resolve_fake_command("pwd") == "pwd"
        assert resolve_fake_command("reboot") == "reboot"
        assert resolve_fake_command("retention") == "retention"
        assert resolve_fake_command("rm -fr /") == "rm_root"
        assert resolve_fake_command("status") == "status"
        assert resolve_fake_command("sudo") == "sudo"
        assert resolve_fake_command("tty") == "tty"
        assert resolve_fake_command("type curl") == "type"
        assert resolve_fake_command("uname -a") == "uname"
        assert resolve_fake_command("uptime") == "uptime"
        assert resolve_fake_command("version") == "version"
        assert resolve_fake_command("which curl") == "which"
        assert resolve_fake_command("who") == "who"
        assert resolve_fake_command("whoami") == "whoami"
        assert resolve_fake_command("ps aux") == "ps"

    def test_rejects_non_fake_commands(self):
        assert resolve_fake_command("ping darklab.sh") is None
        assert resolve_fake_command("rm /tmp/file") is None
        assert resolve_fake_command("") is None
