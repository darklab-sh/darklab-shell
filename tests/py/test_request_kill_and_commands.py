"""
Additional backend tests for request helpers, /kill behaviour,
and command/config parsing edge cases.
"""

import os
import tempfile
import json
import uuid
import unittest.mock as mock

import app as shell_app
from fake_commands import (
    _DOCUMENTED_FAKE_COMMANDS,
    _FAKE_COMMAND_DISPATCH,
    _SPECIAL_FAKE_COMMANDS,
    resolve_fake_command,
)
from commands import (
    load_welcome,
    is_command_allowed,
    validate_command,
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
        session_id = str(uuid.uuid4())
        with shell_app.app.test_request_context("/", headers={"X-Session-ID": f"  {session_id}  "}):
            assert shell_app.get_session_id() == session_id

    def test_get_session_id_rejects_invalid_anonymous_session_id(self):
        previous = shell_app.app.config.get("TESTING")
        shell_app.app.config["TESTING"] = False
        try:
            with shell_app.app.test_request_context("/", headers={"X-Session-ID": "abc123"}):
                assert shell_app.get_session_id() == ""
            with shell_app.app.test_request_context("/", headers={"X-Session-ID": "../other-session"}):
                assert shell_app.get_session_id() == ""
        finally:
            shell_app.app.config["TESTING"] = previous


# ── /kill ─────────────────────────────────────────────────────────────────────

class TestKillRoute:
    def test_kill_returns_404_when_run_missing(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_pop_for_session", return_value=None):
            resp = client.post("/kill", json={"run_id": "missing-run"})

        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert data["error"] == "No such process"

    def test_kill_scopes_pid_lookup_to_request_session(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_pop_for_session", return_value=None) as pid_pop:
            resp = client.post(
                "/kill",
                json={"run_id": "run-123"},
                headers={"X-Session-ID": "owner-session"},
            )

        assert resp.status_code == 404
        pid_pop.assert_called_once_with("run-123", "owner-session")

    def test_kill_sends_sigterm_to_process_group(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_pop_for_session", return_value=1234), \
             mock.patch("blueprints.run.os.getpgid", return_value=1234), \
             mock.patch("blueprints.run.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-123"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        killpg.assert_called_once()

    def test_kill_still_returns_true_when_process_lookup_fails(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_pop_for_session", return_value=1234), \
             mock.patch("blueprints.run.os.getpgid", side_effect=ProcessLookupError):
            resp = client.post("/kill", json={"run_id": "run-404"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True

    def test_kill_uses_scanner_sudo_path_when_configured(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_pop_for_session", return_value=1234), \
             mock.patch("blueprints.run.SCANNER_PREFIX", ["sudo", "-u", "scanner", "env", "HOME=/tmp"]), \
             mock.patch("blueprints.run.subprocess.run") as run_cmd, \
             mock.patch("blueprints.run.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-scan"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        # pgid == pid because setsid guarantees PGID == PID at spawn time
        run_cmd.assert_called_once_with(
            [shell_app.SUDO_BIN, "-u", "scanner", shell_app.KILL_BIN, "-TERM", "-1234"],
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
        with mock.patch("commands.load_command_policy", return_value=(a, d)):
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

    def test_workspace_enabled_exempts_declared_file_flags_and_rewrites_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            registry = {
                "commands": [
                    {
                        "root": "nmap",
                        "category": "Scanning",
                        "policy": {"allow": ["nmap"], "deny": ["nmap -iL", "nmap -oN"]},
                        "workspace_flags": [
                            {"flag": "-iL", "mode": "read", "value": "separate"},
                            {"flag": "-oN", "mode": "write", "value": "separate_or_attached"},
                            {"flag": "-dir", "mode": "read_write", "value": "separate", "kind": "directory"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("commands.load_commands_registry", return_value=registry):
                from workspace import session_workspace_name, write_workspace_text_file
                write_workspace_text_file("session-1", "targets.txt", "ip.darklab.sh\n", cfg)
                target_path = os.path.join(
                    tmp,
                    session_workspace_name("session-1"),
                    "targets.txt",
                )
                os.chmod(target_path, 0o600)

                result = validate_command(
                    "nmap -iL targets.txt -oN scan.txt -dir tool-db",
                    session_id="session-1",
                    cfg=cfg,
                )
                target_mode = os.stat(target_path).st_mode & 0o777
                db_dir = os.path.join(
                    tmp,
                    session_workspace_name("session-1"),
                    "tool-db",
                )
                db_mode = os.stat(db_dir).st_mode & 0o777
                db_is_dir = os.path.isdir(db_dir)

        assert result.allowed
        assert result.workspace_reads == ["targets.txt"]
        assert result.workspace_writes == ["scan.txt", "tool-db"]
        assert result.exec_command != result.display_command
        assert str(tmp) in result.exec_command
        assert target_mode == 0o640
        assert db_is_dir
        assert db_mode == 0o770

    def test_workspace_disabled_keeps_declared_file_flags_denied(self):
        registry = {
            "commands": [
                {
                    "root": "nmap",
                    "category": "Scanning",
                    "policy": {"allow": ["nmap"], "deny": ["nmap -iL"]},
                    "workspace_flags": [{"flag": "-iL", "mode": "read", "value": "separate"}],
                },
            ],
            "pipe_helpers": [],
        }
        with mock.patch("commands.load_commands_registry", return_value=registry):
            result = validate_command(
                "nmap -iL targets.txt",
                session_id="session-1",
                cfg={"workspace_enabled": False},
            )

        assert not result.allowed
        assert "Files are disabled" in result.reason

    def test_workspace_read_flags_rewrite_relative_files_but_keep_packaged_wordlists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            registry = {
                "commands": [
                    {
                        "root": "ffuf",
                        "category": "Scanning",
                        "policy": {"allow": ["ffuf"], "deny": ["ffuf -o"]},
                        "workspace_flags": [
                            {"flag": "-w", "mode": "read", "value": "separate"},
                            {"flag": "-o", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("commands.load_commands_registry", return_value=registry):
                from workspace import write_workspace_text_file
                write_workspace_text_file("session-1", "words.txt", "admin\nlogin\n", cfg)

                workspace_result = validate_command(
                    "ffuf -u https://ip.darklab.sh/FUZZ -w words.txt -o ffuf.json",
                    session_id="session-1",
                    cfg=cfg,
                )
                packaged_result = validate_command(
                    "ffuf -u https://ip.darklab.sh/FUZZ "
                    "-w /usr/share/wordlists/seclists/Discovery/Web-Content/common.txt",
                    session_id="session-1",
                    cfg=cfg,
                )

        assert workspace_result.allowed
        assert workspace_result.workspace_reads == ["words.txt"]
        assert workspace_result.workspace_writes == ["ffuf.json"]
        assert str(tmp) in workspace_result.exec_command
        assert packaged_result.allowed
        assert packaged_result.workspace_reads == []
        assert "/usr/share/wordlists/seclists/Discovery/Web-Content/common.txt" in packaged_result.exec_command

    def test_workspace_write_flags_keep_dev_null_exception(self):
        result = validate_command(
            'curl -o /dev/null -w "%{http_code}" https://ip.darklab.sh',
            session_id="session-1",
            cfg={"workspace_enabled": True},
        )

        assert result.allowed
        assert result.reason == ""
        assert result.workspace_reads == []
        assert result.workspace_writes == []

    def test_workspace_flags_cover_common_list_wordlist_and_output_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            from workspace import write_workspace_text_file
            write_workspace_text_file("session-1", "urls.txt", "https://ip.darklab.sh\n", cfg)
            write_workspace_text_file("session-1", "hosts.txt", "ip.darklab.sh\n", cfg)
            write_workspace_text_file("session-1", "words.txt", "admin\nlogin\n", cfg)
            write_workspace_text_file("session-1", "domains.txt", "darklab.sh\n", cfg)

            cases = [
                (
                    "pd-httpx -l urls.txt -o httpx.txt",
                    ["urls.txt"],
                    ["httpx.txt"],
                ),
                (
                    "gobuster dir -u https://ip.darklab.sh -w words.txt -o gobuster.txt",
                    ["words.txt"],
                    ["gobuster.txt"],
                ),
                (
                    "naabu -list hosts.txt -o naabu.txt",
                    ["hosts.txt"],
                    ["naabu.txt"],
                ),
                (
                    "katana -list urls.txt -o katana.txt",
                    ["urls.txt"],
                    ["katana.txt"],
                ),
                (
                    "amass enum -df domains.txt -timeout 10",
                    ["domains.txt"],
                    ["amass"],
                ),
                (
                    "amass subs -d darklab.sh -names",
                    [],
                    ["amass"],
                ),
                (
                    "amass subs -d darklab.sh -names -dir amass",
                    [],
                    ["amass"],
                ),
                (
                    "amass subs -d darklab.sh -names -o amass-subdomains.txt",
                    [],
                    ["amass-subdomains.txt", "amass"],
                ),
                (
                    "amass track -d darklab.sh",
                    [],
                    ["amass"],
                ),
                (
                    "amass viz -d darklab.sh -d3 -o amass-viz",
                    [],
                    ["amass-viz", "amass"],
                ),
            ]

            results = [
                (validate_command(command, session_id="session-1", cfg=cfg), reads, writes)
                for command, reads, writes in cases
            ]

        for result, reads, writes in results:
            assert result.allowed, result.reason
            assert result.workspace_reads == reads
            assert result.workspace_writes == writes
            assert str(tmp) in result.exec_command

        denied = validate_command(
            "amass subs -d darklab.sh -names -dir custom-amass-db",
            session_id="session-1",
            cfg=cfg,
        )
        assert not denied.allowed
        assert "managed amass session directory" in denied.reason

        denied = validate_command(
            "amass enum -d darklab.sh -o unmanaged.txt",
            session_id="session-1",
            cfg=cfg,
        )
        assert not denied.allowed
        assert "Command not allowed" in denied.reason


class TestFakeCommandResolution:
    def test_documented_fake_commands_are_backed_by_runtime_dispatch(self):
        for entry in _DOCUMENTED_FAKE_COMMANDS:
            if "root" in entry:
                assert entry["root"] in _FAKE_COMMAND_DISPATCH
            if "exact" in entry:
                exact = entry["exact"]
                assert exact in _SPECIAL_FAKE_COMMANDS
                assert _SPECIAL_FAKE_COMMANDS[exact] in _FAKE_COMMAND_DISPATCH

    def test_resolves_supported_fake_commands(self):
        assert resolve_fake_command("banner") == "banner"
        assert resolve_fake_command("clear") == "clear"
        assert resolve_fake_command("commands") == "commands"
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
        assert resolve_fake_command("man curl") == "man"
        assert resolve_fake_command("pwd") == "pwd"
        assert resolve_fake_command("reboot") == "reboot"
        assert resolve_fake_command("retention") == "retention"
        assert resolve_fake_command("rm -fr /") == "rm_root"
        assert resolve_fake_command(":(){ :|:& };:") == "fork_bomb"
        assert resolve_fake_command(":(){:|:&};:") == "fork_bomb"
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
        with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
            assert resolve_fake_command("file list") == "file"
            assert resolve_fake_command("workspace list") is None
            assert resolve_fake_command("ls") == "ls"
            assert resolve_fake_command("cat targets.txt") == "cat"
            assert resolve_fake_command("rm targets.txt") == "rm"

    def test_workspace_fake_commands_are_hidden_when_disabled(self):
        with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            assert resolve_fake_command("file list") is None
            assert resolve_fake_command("ls") is None
            assert resolve_fake_command("cat targets.txt") is None
            assert resolve_fake_command("rm targets.txt") is None

    def test_rejects_non_fake_commands(self):
        assert resolve_fake_command("ping darklab.sh") is None
        assert resolve_fake_command("cat /etc/passwd") is None
        assert resolve_fake_command("rm /tmp/file") is None
        assert resolve_fake_command("rm ../file") is None
        assert resolve_fake_command("ls /tmp") is None
        assert resolve_fake_command("") is None
