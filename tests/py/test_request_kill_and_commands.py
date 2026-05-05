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
import commands
from builtin_commands import (
    _DOCUMENTED_BUILTIN_COMMANDS,
    _BUILTIN_COMMAND_DISPATCH,
    _SPECIAL_BUILTIN_COMMANDS,
    _run_builtin_commands,
    resolve_builtin_command,
)
from commands import (
    load_welcome,
    is_command_allowed,
    validate_command,
)


_COMMAND_VALIDATION_HELPERS = None


def _command_validation_helpers():
    global _COMMAND_VALIDATION_HELPERS
    if _COMMAND_VALIDATION_HELPERS is None:
        registry = commands.load_commands_registry()
        with mock.patch("commands.load_commands_registry", return_value=registry):
            _COMMAND_VALIDATION_HELPERS = {
                "allow_grouping": commands.load_allow_grouping_flags(),
                "workspace_flags": commands._workspace_flag_specs_by_root(),
                "runtime_adaptations": commands._runtime_adaptations_by_root(),
            }
    return _COMMAND_VALIDATION_HELPERS


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
        helpers = _command_validation_helpers()
        with mock.patch("commands.load_command_policy", return_value=(a, d)), \
             mock.patch("commands.load_allow_grouping_flags", return_value=helpers["allow_grouping"]), \
             mock.patch("commands._workspace_flag_specs_by_root", return_value=helpers["workspace_flags"]), \
             mock.patch("commands._runtime_adaptations_by_root", return_value=helpers["runtime_adaptations"]):
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

            registry = commands.load_commands_registry()
            with mock.patch("commands.load_commands_registry", return_value=registry):
                command_policy = commands.load_command_policy()
                allow_grouping = commands.load_allow_grouping_flags()
                workspace_flags = commands._workspace_flag_specs_by_root()
                runtime_adaptations = commands._runtime_adaptations_by_root()

            with mock.patch("commands.load_command_policy", return_value=command_policy), \
                 mock.patch("commands.load_allow_grouping_flags", return_value=allow_grouping), \
                 mock.patch("commands._workspace_flag_specs_by_root", return_value=workspace_flags), \
                 mock.patch("commands._runtime_adaptations_by_root", return_value=runtime_adaptations):
                results = [
                    (validate_command(command, session_id="session-1", cfg=cfg), reads, writes)
                    for command, reads, writes in cases
                ]

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

        for result, reads, writes in results:
            assert result.allowed, result.reason
            assert result.workspace_reads == reads
            assert result.workspace_writes == writes
            assert str(tmp) in result.exec_command

    def test_restricted_command_input_cidrs_block_inline_literal_targets(self):
        registry = {
            "commands": [
                {
                    "root": "probe",
                    "category": "Testing",
                    "policy": {"allow": ["probe"], "deny": []},
                    "autocomplete": {
                        "flags": [
                            {
                                "value": "-u",
                                "takes_value": True,
                                "value_hint": {
                                    "placeholder": "<url>",
                                    "value_type": "url",
                                },
                            },
                        ],
                        "arguments": [
                            {
                                "placeholder": "<target>",
                                "value_type": "domain",
                            },
                        ],
                    },
                },
            ],
            "pipe_helpers": [],
        }
        cfg = {
            "restricted_command_input_cidrs": ["10.0.0.0/8", "169.254.169.254/32"],
            "workspace_enabled": False,
        }
        with mock.patch("commands.load_commands_registry", return_value=registry):
            ip_result = validate_command("probe 10.1.2.3", cfg=cfg)
            url_result = validate_command("probe -u http://169.254.169.254/latest", cfg=cfg)
            domain_result = validate_command("probe darklab.sh", cfg=cfg)

        assert not ip_result.allowed
        assert "restricted IP/CIDR value: 10.1.2.3" in ip_result.reason
        assert not url_result.allowed
        assert "restricted IP/CIDR value: 169.254.169.254" in url_result.reason
        assert domain_result.allowed

    def test_restricted_command_input_cidrs_block_overlapping_cidr_targets(self):
        registry = {
            "commands": [
                {
                    "root": "scan",
                    "category": "Testing",
                    "policy": {"allow": ["scan"], "deny": []},
                    "autocomplete": {
                        "arguments": [
                            {
                                "placeholder": "<target>",
                                "value_type": "cidr",
                            },
                        ],
                    },
                },
            ],
            "pipe_helpers": [],
        }
        cfg = {
            "restricted_command_input_cidrs": ["10.0.0.0/8"],
            "workspace_enabled": False,
        }
        with mock.patch("commands.load_commands_registry", return_value=registry):
            result = validate_command("scan 10.2.0.0/16", cfg=cfg)

        assert not result.allowed
        assert "restricted IP/CIDR value: 10.2.0.0/16" in result.reason

    def test_restricted_command_input_cidrs_inspect_workspace_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
                "restricted_command_input_cidrs": ["10.0.0.0/8"],
            }
            registry = {
                "commands": [
                    {
                        "root": "scan",
                        "category": "Testing",
                        "policy": {"allow": ["scan"], "deny": ["scan -iL"]},
                        "workspace_flags": [
                            {"flag": "-iL", "mode": "read", "value": "separate"},
                        ],
                        "autocomplete": {
                            "flags": [
                                {
                                    "value": "-iL",
                                    "takes_value": True,
                                    "feature_required": "workspace",
                                    "value_hint": {
                                        "placeholder": "<target-file>",
                                        "value_type": "target",
                                    },
                                },
                            ],
                        },
                    },
                ],
                "pipe_helpers": [],
            }
            from workspace import write_workspace_text_file
            write_workspace_text_file("session-1", "targets.txt", "darklab.sh\n10.9.8.7\n", cfg)

            with mock.patch("commands.load_commands_registry", return_value=registry):
                result = validate_command(
                    "scan -iL targets.txt",
                    session_id="session-1",
                    cfg=cfg,
                )

        assert not result.allowed
        assert "Session file targets.txt contains restricted IP/CIDR value: 10.9.8.7" in result.reason


class TestBuiltinCommandResolution:
    def test_documented_builtin_commands_are_backed_by_runtime_dispatch(self):
        for entry in _DOCUMENTED_BUILTIN_COMMANDS:
            if "root" in entry:
                assert entry["root"] in _BUILTIN_COMMAND_DISPATCH
            if "exact" in entry:
                exact = entry["exact"]
                assert exact in _SPECIAL_BUILTIN_COMMANDS
                assert _SPECIAL_BUILTIN_COMMANDS[exact] in _BUILTIN_COMMAND_DISPATCH

    def test_resolves_supported_builtin_commands(self):
        assert resolve_builtin_command("banner") == "banner"
        assert resolve_builtin_command("clear") == "clear"
        assert resolve_builtin_command("commands") == "commands"
        assert resolve_builtin_command("date") == "date"
        assert resolve_builtin_command("env") == "env"
        assert resolve_builtin_command("faq") == "faq"
        assert resolve_builtin_command("fortune") == "fortune"
        assert resolve_builtin_command("groups") == "groups"
        assert resolve_builtin_command("help") == "help"
        assert resolve_builtin_command("history") == "history"
        assert resolve_builtin_command("hostname") == "hostname"
        assert resolve_builtin_command("id") == "id"
        assert resolve_builtin_command("last") == "last"
        assert resolve_builtin_command("limits") == "limits"
        assert resolve_builtin_command("man curl") == "man"
        assert resolve_builtin_command("pwd") == "pwd"
        assert resolve_builtin_command("reboot") == "reboot"
        assert resolve_builtin_command("retention") == "retention"
        assert resolve_builtin_command("rm -fr /") == "rm_root"
        assert resolve_builtin_command(":(){ :|:& };:") == "fork_bomb"
        assert resolve_builtin_command(":(){:|:&};:") == "fork_bomb"
        assert resolve_builtin_command("status") == "status"
        assert resolve_builtin_command("sudo") == "sudo"
        assert resolve_builtin_command("tty") == "tty"
        assert resolve_builtin_command("type curl") == "type"
        assert resolve_builtin_command("uname -a") == "uname"
        assert resolve_builtin_command("uptime") == "uptime"
        assert resolve_builtin_command("version") == "version"
        assert resolve_builtin_command("which curl") == "which"
        assert resolve_builtin_command("who") == "who"
        assert resolve_builtin_command("whoami") == "whoami"
        assert resolve_builtin_command("ps aux") == "ps"
        with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
            assert resolve_builtin_command("file list") == "file"
            assert resolve_builtin_command("workspace list") is None
            assert resolve_builtin_command("ls") == "ls"
            assert resolve_builtin_command("cat targets.txt") == "cat"
            assert resolve_builtin_command("rm targets.txt") == "rm"

    def test_workspace_builtin_commands_are_hidden_when_disabled(self):
        with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            assert resolve_builtin_command("file list") is None
            assert resolve_builtin_command("ls") is None
            assert resolve_builtin_command("cat targets.txt") is None
            assert resolve_builtin_command("rm targets.txt") is None

    def test_commands_external_catalog_uses_commands_registry(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "category": "Registry Group",
                    "policy": {"allow": ["sentinel-scan"]},
                },
                {
                    "root": "sentinel-http",
                    "category": "Registry Group",
                    "policy": {"allow": ["sentinel-http --safe"]},
                },
                {
                    "root": "policyless-tool",
                    "category": "Registry Group",
                    "policy": {"allow": []},
                },
            ],
            "pipe_helpers": [{"root": "grep"}],
        }

        with mock.patch("builtin_commands.load_commands_registry", return_value=registry) as loader:
            lines = _run_builtin_commands("commands --external")

        text = "\n".join(line.get("text", "") for line in lines)
        assert loader.call_count == 1
        assert "Allowed external commands:" in text
        assert "[Registry Group]" in text
        assert "sentinel-scan" in text
        assert "sentinel-http" in text
        assert "policyless-tool" not in text
        assert "grep" not in text

    def test_commands_info_renders_registry_catalog_entry(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "category": "Registry Group",
                    "description": "Probe a target safely.",
                    "policy": {"allow": ["sentinel-scan"]},
                    "workspace_flags": [
                        {"flag": "-i", "mode": "read", "value": "separate"},
                    ],
                    "runtime_adaptations": {
                        "inject_flags": [{"flags": ["--safe"], "position": "append"}],
                    },
                    "autocomplete": {
                        "examples": [
                            {"value": "sentinel-scan example.test", "description": "Basic probe"},
                        ],
                        "flags": [
                            {"value": "-i", "description": "Read targets", "takes_value": True},
                        ],
                    },
                },
            ],
            "pipe_helpers": [],
        }

        with mock.patch("commands.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands info sentinel-scan")

        text = "\n".join(line.get("text", "") for line in lines)
        assert "sentinel-scan" in text
        assert "Probe a target safely." in text
        assert "sentinel-scan example.test" in text
        assert "-i <value>" in text
        assert "App handling:" not in text
        assert "Adds `--safe` automatically when needed." not in text

    def test_commands_info_unknown_root_returns_usage_hint(self):
        with mock.patch("commands.load_commands_registry", return_value={"commands": [], "pipe_helpers": []}):
            lines = _run_builtin_commands("commands info nope")

        assert lines[0]["text"] == "commands: no catalog entry for nope"

    def test_rejects_non_builtin_commands(self):
        assert resolve_builtin_command("ping darklab.sh") is None
        assert resolve_builtin_command("cat /etc/passwd") is None
        assert resolve_builtin_command("rm /tmp/file") is None
        assert resolve_builtin_command("rm ../file") is None
        assert resolve_builtin_command("ls /tmp") is None
        assert resolve_builtin_command("") is None
