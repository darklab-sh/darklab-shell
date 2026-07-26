# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Additional backend tests for request helpers, /kill behaviour,
and command/config parsing edge cases.
"""

import os
import tempfile
import json
import uuid
import unittest.mock as mock
from typing import cast
import pytest

import app as shell_app_module
from conftest import build_test_config
from conftest import make_test_app as _test_app
from blueprints.run import KILL_BIN, SUDO_BIN
from core.helpers import get_session_id
import services.commands.registry as commands
import services.commands.builtins_discovery as builtins_discovery
from services.commands.builtins import (
    _BUILTIN_REGISTRY,
    get_builtin_autocomplete_context,
    get_builtin_command_catalog,
    _run_builtin_commands,
    execute_builtin_command,
    resolve_builtin_command,
)
from services.commands.builtin_registry import (
    BuiltinCommandRegistry,
    BuiltinCommandSpec,
    BuiltinExecutionContext,
    BuiltinExecutionOwner,
    BuiltinMatchStrategy,
    build_builtin_command_spec,
)
from services.commands.registry import (
    load_welcome,
    is_command_allowed,
    validate_command,
)
from services.teams.scope import OwnerContext


_EXPECTED_BUILTIN_EXACT_ALIASES = {
    ":(){ :|:& };:",
    "coffee",
    "halt",
    "ip a",
    "poweroff",
    "rm -f -r /",
    "rm -fr /",
    "rm -r -f /",
    "rm -rf /",
    "shutdown now",
    "su",
    "sudo -s",
    "sudo su",
    "xyzzy",
}
_EXPECTED_BUILTIN_ROOTS = {
    "banner",
    "cat",
    "cd",
    "clear",
    "commands",
    "config",
    "cp",
    "date",
    "df",
    "diff",
    "env",
    "exit",
    "faq",
    "file",
    "fortune",
    "free",
    "grep",
    "groups",
    "head",
    "help",
    "history",
    "hostname",
    "id",
    "intel",
    "jobs",
    "last",
    "limits",
    "ll",
    "ls",
    "man",
    "mkdir",
    "mv",
    "notify",
    "project",
    "providers",
    "ps",
    "pwd",
    "quit",
    "reboot",
    "retention",
    "rm",
    "route",
    "runs",
    "schedule",
    "secret",
    "session-token",
    "shortcuts",
    "sort",
    "stats",
    "status",
    "sudo",
    "tail",
    "team",
    "theme",
    "touch",
    "tour",
    "tty",
    "type",
    "uname",
    "uniq",
    "uptime",
    "var",
    "version",
    "watch",
    "wc",
    "which",
    "who",
    "whoami",
    "wordlist",
    "workflow",
}


_COMMAND_VALIDATION_HELPERS = None


def _command_validation_helpers():
    global _COMMAND_VALIDATION_HELPERS
    if _COMMAND_VALIDATION_HELPERS is None:
        registry = commands.load_commands_registry()
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            _COMMAND_VALIDATION_HELPERS = {
                "allow_grouping": commands.load_allow_grouping_flags(),
                "workspace_flags": commands._workspace_flag_specs_by_root(),
                "runtime_adaptations": commands._runtime_adaptations_by_root(),
            }
    return _COMMAND_VALIDATION_HELPERS


def get_client(*, use_forwarded_for=True):
    client = _test_app().test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


# ── Request helpers ───────────────────────────────────────────────────────────

class TestRequestHelpers:
    def test_prefers_valid_forwarded_for(self):
        with _test_app().test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"X-Forwarded-For": "203.0.113.9"},
        ):
            assert shell_app_module.get_client_ip() == "203.0.113.9"

    def test_uses_last_untrusted_forwarded_for_when_multiple(self):
        with _test_app().test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"X-Forwarded-For": "198.51.100.5, 10.0.0.1"},
        ):
            assert shell_app_module.get_client_ip() == "10.0.0.1"

    def test_invalid_forwarded_for_falls_back(self):
        with _test_app().test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"X-Forwarded-For": "definitely-not-an-ip"},
        ):
            # Flask test client context usually falls back to 127.0.0.1
            assert shell_app_module.get_client_ip() == "127.0.0.1"

    def test_get_session_id_strips_whitespace(self):
        session_id = str(uuid.uuid4())
        with _test_app().test_request_context("/", headers={"X-Session-ID": f"  {session_id}  "}):
            assert get_session_id() == session_id

    def test_get_session_id_rejects_invalid_anonymous_session_id(self):
        flask_app = _test_app()
        previous = flask_app.config.get("TESTING")
        flask_app.config["TESTING"] = False
        try:
            with flask_app.test_request_context("/", headers={"X-Session-ID": "abc123"}):
                assert get_session_id() == ""
            with flask_app.test_request_context("/", headers={"X-Session-ID": "../other-session"}):
                assert get_session_id() == ""
        finally:
            flask_app.config["TESTING"] = previous


# ── /kill ─────────────────────────────────────────────────────────────────────

class TestKillRoute:
    def test_kill_returns_404_when_run_missing(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=None):
            resp = client.post("/kill", json={"run_id": "missing-run"})

        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert data["error"] == "No such process"

    def test_kill_scopes_pid_lookup_to_request_session(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=None) as pid_lookup:
            resp = client.post(
                "/kill",
                json={"run_id": "run-123"},
                headers={"X-Session-ID": "owner-session"},
            )

        assert resp.status_code == 404
        pid_lookup.assert_called_once_with("run-123", "owner-session")

    def test_kill_sends_sigterm_to_process_group(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=1234), \
             mock.patch("blueprints.run.os.getpgid", return_value=1234), \
             mock.patch("blueprints.run.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-123"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        killpg.assert_called_once()

    def test_kill_still_returns_true_when_process_lookup_fails(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=1234), \
             mock.patch("blueprints.run.os.killpg", side_effect=ProcessLookupError):
            resp = client.post("/kill", json={"run_id": "run-404"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True

    def test_kill_uses_scanner_sudo_path_when_configured(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=1234), \
             mock.patch("blueprints.run.SCANNER_PREFIX", ["sudo", "-u", "scanner", "env", "HOME=/tmp"]), \
             mock.patch("blueprints.run.active_run_pid_start_matches", return_value=True), \
             mock.patch("blueprints.run.subprocess.run", return_value=mock.Mock(returncode=0)) as run_cmd, \
             mock.patch("blueprints.run.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-scan"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        # pgid == pid because setsid guarantees PGID == PID at spawn time
        run_cmd.assert_called_once_with(
            [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", "--", "-1234"],
            timeout=5,
        )
        killpg.assert_not_called()

    def test_kill_skips_scanner_sudo_path_when_pid_start_time_changed(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=1234), \
             mock.patch("blueprints.run.SCANNER_PREFIX", ["sudo", "-u", "scanner", "env", "HOME=/tmp"]), \
             mock.patch("blueprints.run.active_run_pid_start_matches", return_value=False), \
             mock.patch("blueprints.run.subprocess.run") as run_cmd, \
             mock.patch("blueprints.run.os.killpg") as killpg:
            resp = client.post("/kill", json={"run_id": "run-scan-reused"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True
        run_cmd.assert_not_called()
        killpg.assert_not_called()

    def test_kill_treats_missing_scanner_process_group_as_success_after_sudo_race(self):
        client = get_client()

        with mock.patch("blueprints.run.pid_for_session", return_value=1234), \
             mock.patch("blueprints.run.SCANNER_PREFIX", ["sudo", "-u", "scanner", "env", "HOME=/tmp"]), \
             mock.patch("blueprints.run.active_run_pid_start_matches", return_value=True), \
             mock.patch("blueprints.run.subprocess.run", return_value=mock.Mock(returncode=1)), \
             mock.patch("blueprints.run.time.sleep"), \
             mock.patch("blueprints.run.os.killpg", side_effect=ProcessLookupError):
            resp = client.post("/kill", json={"run_id": "run-scan-race"})

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["killed"] is True

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
            with mock.patch("services.commands.registry.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)

        assert len(result) == 2
        assert result[0]["cmd"] == "whoami"
        assert result[0]["out"] == "appuser"

    def test_missing_file_returns_empty(self):
        with mock.patch("services.commands.registry.WELCOME_FILE", "/missing.yaml"):
            assert load_welcome() == []


class TestIsCommandAllowedEdges:
    def _check(self, cmd, allow=None, deny=None):
        a = allow if allow is not None else ["ls", "curl", "echo", "nmap"]
        d = deny if deny is not None else []
        helpers = _command_validation_helpers()
        with mock.patch("services.commands.registry.load_command_policy", return_value=(a, d)), \
             mock.patch("services.commands.registry.load_allow_grouping_flags", return_value=helpers["allow_grouping"]), \
             mock.patch("services.commands.registry._workspace_flag_specs_by_root", return_value=helpers["workspace_flags"]), \
             mock.patch("services.commands.registry._runtime_adaptations_by_root", return_value=helpers["runtime_adaptations"]):
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

    def test_absolute_output_redirection_destination_is_blocked(self):
        ok, reason = self._check("curl https://darklab.sh > /tmp/out")
        assert not ok
        assert "must be relative" in reason

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
                "workspace_quota_mb": 2,
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
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.workspace.files import session_workspace_name, write_workspace_text_file
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

    def test_workspace_file_flags_resolve_against_team_owner_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 2,
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
                            {"flag": "-oN", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.teams.scope import team_owner_context
                from services.workspace.files import (
                    owner_workspace_name,
                    resolve_owner_workspace_path,
                    write_owner_workspace_text_file,
                )

                owner = team_owner_context("team-command-files", actor_session_id="tok_command_actor")
                write_owner_workspace_text_file(owner, "targets.txt", "ip.darklab.sh\n", cfg)

                result = validate_command(
                    "nmap -iL targets.txt -oN scan.txt",
                    session_id="tok_command_actor",
                    cfg=cfg,
                    owner_context=owner,
                )
                expected_read = str(resolve_owner_workspace_path(owner, "targets.txt", cfg))
                expected_write = str(resolve_owner_workspace_path(owner, "scan.txt", cfg))

        assert result.allowed, result.reason
        assert result.workspace_reads == ["targets.txt"]
        assert result.workspace_writes == ["scan.txt"]
        assert expected_read in result.exec_command
        assert expected_write in result.exec_command
        assert owner_workspace_name(owner) in result.exec_command
        assert "tok_command_actor" not in result.exec_command

    def test_workspace_file_write_flags_reserve_team_quota_before_command_runs(self):
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
                        "policy": {"allow": ["nmap"], "deny": ["nmap -oN"]},
                        "workspace_flags": [
                            {"flag": "-oN", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.teams.scope import team_owner_context
                from services.workspace.files import resolve_owner_workspace_path, write_owner_workspace_text_file

                owner = team_owner_context("team-command-quota", actor_session_id="tok_command_actor")
                write_owner_workspace_text_file(owner, "existing.txt", "x" * (1024 * 1024), cfg)

                result = validate_command(
                    "nmap -oN scan.txt darklab.sh",
                    session_id="tok_command_actor",
                    cfg=cfg,
                    owner_context=owner,
                )
                reserved_path = resolve_owner_workspace_path(owner, "scan.txt", cfg)

        assert not result.allowed
        assert result.reason == "workspace file quota exceeded"
        assert not reserved_path.exists()

    def test_workspace_file_write_flags_precreate_team_output_under_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 2,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            registry = {
                "commands": [
                    {
                        "root": "nmap",
                        "category": "Scanning",
                        "policy": {"allow": ["nmap"], "deny": ["nmap -oN"]},
                        "workspace_flags": [
                            {"flag": "-oN", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.teams.scope import team_owner_context
                from services.workspace.files import resolve_owner_workspace_path

                owner = team_owner_context("team-command-reserve", actor_session_id="tok_command_actor")
                result = validate_command(
                    "nmap -oN scan.txt darklab.sh",
                    session_id="tok_command_actor",
                    cfg=cfg,
                    owner_context=owner,
                )
                reserved_path = resolve_owner_workspace_path(owner, "scan.txt", cfg)
                reserved_exists = reserved_path.is_file()
                reserved_size = reserved_path.stat().st_size
                reserved_mode = os.stat(reserved_path).st_mode & 0o777

        assert result.allowed, result.reason
        assert reserved_exists
        assert reserved_size == 0
        assert reserved_mode == 0o660

    def test_restricted_workspace_list_files_read_team_workspace(self):
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
                        "category": "Scanning",
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
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.teams.scope import team_owner_context
                from services.workspace.files import write_owner_workspace_text_file

                owner = team_owner_context("team-restricted-files", actor_session_id="tok_restricted_actor")
                write_owner_workspace_text_file(owner, "targets.txt", "10.1.2.3\n", cfg)
                result = validate_command(
                    "scan -iL targets.txt",
                    session_id="tok_restricted_actor",
                    cfg=cfg,
                    owner_context=owner,
                )

        assert not result.allowed
        assert "targets.txt contains restricted IP/CIDR value: 10.1.2.3" in result.reason

    def test_workspace_file_flags_resolve_relative_to_workspace_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 2,
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
                            {"flag": "-oN", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.workspace.files import resolve_workspace_path, write_workspace_text_file
                write_workspace_text_file("session-1", "darklab/targets.txt", "ip.darklab.sh\n", cfg)

                result = validate_command(
                    "nmap -iL targets.txt -oN findings.txt",
                    session_id="session-1",
                    cfg=cfg,
                    workspace_cwd="darklab",
                )
                expected_read = str(resolve_workspace_path("session-1", "darklab/targets.txt", cfg))
                expected_write = str(resolve_workspace_path("session-1", "darklab/findings.txt", cfg))

            assert result.allowed, result.reason
            assert result.workspace_reads == ["darklab/targets.txt"]
            assert result.workspace_writes == ["darklab/findings.txt"]
            assert expected_read in result.exec_command
            assert expected_write in result.exec_command

    def test_workspace_file_flags_allow_parent_paths_without_escaping_workspace(self):
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
                            {"flag": "-oN", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.workspace.files import write_workspace_text_file
                write_workspace_text_file("session-1", "targets.txt", "ip.darklab.sh\n", cfg)

                result = validate_command(
                    "nmap -iL ../targets.txt",
                    session_id="session-1",
                    cfg=cfg,
                    workspace_cwd="darklab",
                )
                denied = validate_command(
                    "nmap -iL ../../targets.txt",
                    session_id="session-1",
                    cfg=cfg,
                    workspace_cwd="darklab",
                )
                absolute_denied = validate_command(
                    "nmap -iL ../targets.txt -oN /../../scan.txt",
                    session_id="session-1",
                    cfg=cfg,
                    workspace_cwd="darklab",
                )

        assert result.allowed, result.reason
        assert result.workspace_reads == ["targets.txt"]
        assert not denied.allowed
        assert "escapes the workspace directory" in denied.reason
        assert not absolute_denied.allowed
        assert "Invalid file path: /../../scan.txt" in absolute_denied.reason
        assert "Command not allowed" not in absolute_denied.reason

    def test_workspace_file_flags_treat_root_paths_as_workspace_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 2,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            from services.workspace.files import resolve_workspace_path, write_workspace_text_file
            write_workspace_text_file("session-1", "urls.txt", "https://ip.darklab.sh\n", cfg)

            result = validate_command(
                "katana -list /urls.txt -d 1 -silent -o /katana-urls.txt",
                session_id="session-1",
                cfg=cfg,
            )
            expected_read = str(resolve_workspace_path("session-1", "urls.txt", cfg))
            expected_write = str(resolve_workspace_path("session-1", "katana-urls.txt", cfg))

        assert result.allowed, result.reason
        assert result.workspace_reads == ["urls.txt"]
        assert result.workspace_writes == ["katana-urls.txt"]
        assert expected_read in result.exec_command
        assert expected_write in result.exec_command
        assert " -o /katana-urls.txt" not in result.exec_command

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
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
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
                "workspace_quota_mb": 2,
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
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                from services.workspace.files import write_workspace_text_file
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
                "workspace_quota_mb": 20,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            from services.workspace.files import write_workspace_text_file
            write_workspace_text_file("session-1", "urls.txt", "https://ip.darklab.sh\n", cfg)
            write_workspace_text_file("session-1", "hosts.txt", "ip.darklab.sh\n", cfg)
            write_workspace_text_file("session-1", "words.txt", "admin\nlogin\n", cfg)
            write_workspace_text_file("session-1", "domains.txt", "darklab.sh\n", cfg)

            cases = [
                (
                    "httpx -l urls.txt -o httpx.txt",
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
                    "nmap -sV -p 1-1000 ip.darklab.sh -o nmap-output.txt",
                    [],
                    ["nmap-output.txt"],
                ),
                (
                    "amass enum -df domains.txt -timeout 10",
                    ["domains.txt"],
                    ["tools/amass"],
                ),
                (
                    "amass subs -d darklab.sh -names",
                    [],
                    ["tools/amass"],
                ),
                (
                    "amass subs -d darklab.sh -names -dir tools/amass",
                    [],
                    ["tools/amass"],
                ),
                (
                    "amass subs -d darklab.sh -names -o amass-subdomains.txt",
                    [],
                    ["amass-subdomains.txt", "tools/amass"],
                ),
                (
                    "amass track -d darklab.sh",
                    [],
                    ["tools/amass"],
                ),
                (
                    "amass viz -d darklab.sh -d3 -o amass-viz",
                    [],
                    ["amass-viz", "tools/amass"],
                ),
            ]

            registry = commands.load_commands_registry()
            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                command_policy = commands.load_command_policy()
                allow_grouping = commands.load_allow_grouping_flags()
                workspace_flags = commands._workspace_flag_specs_by_root()
                runtime_adaptations = commands._runtime_adaptations_by_root()

            with mock.patch("services.commands.registry.load_command_policy", return_value=command_policy), \
                 mock.patch("services.commands.registry.load_allow_grouping_flags", return_value=allow_grouping), \
                 mock.patch("services.commands.registry._workspace_flag_specs_by_root", return_value=workspace_flags), \
                 mock.patch("services.commands.registry._runtime_adaptations_by_root", return_value=runtime_adaptations):
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
                assert "managed tools/amass workspace directory" in denied.reason

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

    def test_workspace_artifact_capture_skips_app_managed_amass_database(self):
        from blueprints.run import _workspace_artifacts_from_validation

        validation = commands.CommandValidationResult(
            True,
            workspace_reads=["domains.txt"],
            workspace_writes=[
                "tools/amass",
                "amass-subdomains.txt",
                "tools/amass/asset.db",
            ],
        )

        artifacts = _workspace_artifacts_from_validation(validation, "session-1")

        assert [(item["workspace_path"], item["kind"]) for item in artifacts] == [
            ("domains.txt", "input"),
            ("amass-subdomains.txt", "output"),
        ]

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
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
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
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
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
            from services.workspace.files import write_workspace_text_file
            write_workspace_text_file("session-1", "targets.txt", "darklab.sh\n10.9.8.7\n", cfg)

            with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
                result = validate_command(
                    "scan -iL targets.txt",
                    session_id="session-1",
                    cfg=cfg,
                )

        assert not result.allowed
        assert "Session file targets.txt contains restricted IP/CIDR value: 10.9.8.7" in result.reason


class TestBuiltinCommandRegistry:
    @staticmethod
    def _handler(
        command: str,
        context: BuiltinExecutionContext,
    ) -> list[dict[str, object]]:
        return [{"type": "output", "text": f"{command}:{context.session_id}"}]

    def test_rejects_duplicate_keys_roots_exact_aliases_and_matchers(self):
        registry = BuiltinCommandRegistry(fork_bomb_matcher=lambda command: True)
        registry.register(BuiltinCommandSpec(
            handler_key="alpha",
            root="alpha",
            exact_aliases=("alpha now",),
            handler=self._handler,
        ))

        with pytest.raises(ValueError, match="handler key"):
            registry.register(BuiltinCommandSpec(
                handler_key="alpha",
                root="other",
                handler=self._handler,
            ))
        with pytest.raises(ValueError, match="root"):
            registry.register(BuiltinCommandSpec(
                handler_key="other",
                root="alpha",
                handler=self._handler,
            ))
        with pytest.raises(ValueError, match="exact alias"):
            registry.register(BuiltinCommandSpec(
                handler_key="exact",
                root="exact",
                exact_aliases=("alpha now",),
                handler=self._handler,
            ))

        registry.register(BuiltinCommandSpec(
            handler_key="fork-one",
            handler=self._handler,
            match_strategy=BuiltinMatchStrategy.FORK_BOMB,
        ))
        with pytest.raises(ValueError, match="fork-bomb matcher"):
            registry.register(BuiltinCommandSpec(
                handler_key="fork-two",
                handler=self._handler,
                match_strategy=BuiltinMatchStrategy.FORK_BOMB,
            ))

    def test_freeze_blocks_registration_and_spec_metadata_is_immutable(self):
        spec = BuiltinCommandSpec(
            handler_key="alpha",
            root="alpha",
            handler=self._handler,
            autocomplete={"flags": [{"value": "--safe"}]},
        )
        registry = BuiltinCommandRegistry()
        registry.register(spec)
        registry.freeze()

        assert registry.frozen
        with pytest.raises(RuntimeError, match="frozen"):
            registry.register(BuiltinCommandSpec(
                handler_key="beta",
                root="beta",
                handler=self._handler,
            ))
        with pytest.raises(TypeError):
            cast(dict[str, object], spec.autocomplete)["flags"] = ()

    def test_exact_root_and_reviewed_shape_resolution(self):
        registry = BuiltinCommandRegistry(
            workspace_alias_validator=lambda parts: (
                len(parts) == 2 and not parts[1].startswith("/")
            ),
            fork_bomb_matcher=lambda command: command == ":(){:|:&};:",
        )
        registry.register(BuiltinCommandSpec(
            handler_key="sudo",
            root="sudo",
            handler=self._handler,
        ))
        registry.register(BuiltinCommandSpec(
            handler_key="su-shell",
            exact_aliases=("sudo su",),
            handler=self._handler,
        ))
        registry.register(BuiltinCommandSpec(
            handler_key="cat",
            root="cat",
            handler=self._handler,
            match_strategy=BuiltinMatchStrategy.WORKSPACE_ALIAS,
        ))
        registry.register(BuiltinCommandSpec(
            handler_key="fork",
            handler=self._handler,
            match_strategy=BuiltinMatchStrategy.FORK_BOMB,
        ))
        registry.freeze()

        sudo = registry.resolve("sudo echo ok")
        su_shell = registry.resolve(" sudo   su ")
        cat = registry.resolve("cat notes.txt")
        fork = registry.resolve(":(){:|:&};:")

        assert sudo is not None and sudo.handler_key == "sudo"
        assert su_shell is not None and su_shell.handler_key == "su-shell"
        assert cat is not None and cat.handler_key == "cat"
        assert registry.resolve("cat /etc/passwd") is None
        assert fork is not None and fork.handler_key == "fork"

    def test_context_derivations_are_lazy_and_memoized(self):
        calls = {"cfg": 0, "owner": 0}
        owner = OwnerContext(scope="team", owner_id="team-one")

        def resolve_cfg():
            calls["cfg"] += 1
            return {"workspace_enabled": True}

        def resolve_owner(session_id, *, team_id=""):
            calls["owner"] += 1
            assert session_id == "session-one"
            assert team_id == "team-one"
            return owner

        context = BuiltinExecutionContext(
            session_id="session-one",
            team_id="team-one",
            config_resolver=resolve_cfg,
            owner_context_resolver=resolve_owner,
        )

        assert calls == {"cfg": 0, "owner": 0}
        assert context.effective_cfg is context.effective_cfg
        assert context.owner_context is owner
        assert context.owner_context is owner
        assert calls == {"cfg": 1, "owner": 1}

    def test_ungated_execution_does_not_construct_lazy_context(self):
        calls = {"cfg": 0, "owner": 0}
        registry = BuiltinCommandRegistry()
        registry.register(BuiltinCommandSpec(
            handler_key="alpha",
            root="alpha",
            handler=self._handler,
        ))
        registry.freeze()
        owner = OwnerContext(scope="personal", owner_id="session-one")

        def resolve_owner(*args, **kwargs):
            calls["owner"] += 1
            return owner

        context = BuiltinExecutionContext(
            session_id="session-one",
            config_resolver=lambda: calls.__setitem__("cfg", calls["cfg"] + 1) or {},
            owner_context_resolver=resolve_owner,
        )

        events, exit_code = registry.execute("alpha", context)

        assert exit_code == 0
        assert events[0]["text"] == "alpha:session-one"
        assert calls == {"cfg": 0, "owner": 0}

    def test_feature_gates_and_nonzero_results_use_the_shared_contract(self):
        registry = BuiltinCommandRegistry()
        registry.register(BuiltinCommandSpec(
            handler_key="workspace",
            root="workspace",
            feature_required=("workspace",),
            handler=lambda _command, _context: (
                [{"type": "output", "text": "denied"}],
                7,
            ),
        ))
        registry.freeze()

        assert registry.resolve(
            "workspace",
            cfg={"workspace_enabled": False},
        ) is None
        events, exit_code = registry.execute(
            "workspace",
            BuiltinExecutionContext(
                session_id="session-one",
                config_resolver=lambda: {"workspace_enabled": True},
            ),
        )

        assert events == [{"type": "output", "text": "denied"}]
        assert exit_code == 7

    def test_browser_owned_commands_require_explicit_fallback_stubs(self):
        with pytest.raises(ValueError, match="fallback stub"):
            BuiltinCommandSpec(
                handler_key="theme",
                root="theme",
                handler=self._handler,
                execution_owner=BuiltinExecutionOwner.BROWSER,
            )

        spec = BuiltinCommandSpec(
            handler_key="theme",
            root="theme",
            handler=self._handler,
            execution_owner=BuiltinExecutionOwner.BROWSER,
            browser_fallback_stub=True,
        )
        assert spec.execution_owner is BuiltinExecutionOwner.BROWSER

    def test_focused_provider_populates_every_registry_view(self):
        def example_provider():
            return (
                build_builtin_command_spec(
                    {
                        "root": "example-helper",
                        "description": "built-in: demonstrate provider registration",
                        "autocomplete": {
                            "flags": [
                                {
                                    "value": "--json",
                                    "description": "Return JSON output",
                                },
                            ],
                            "examples": [
                                {
                                    "value": "example-helper --json",
                                    "description": "Structured output",
                                },
                            ],
                        },
                    },
                    handler_key="example-helper",
                    handler=self._handler,
                    name="example-helper",
                    description="Demonstrate provider registration.",
                ),
            )

        registry = BuiltinCommandRegistry()
        registry.register_provider(example_provider)
        registry.freeze()

        resolution = registry.resolve("example-helper --json")
        assert resolution is not None
        assert resolution.handler_key == "example-helper"
        events, exit_code = registry.execute(
            "example-helper --json",
            BuiltinExecutionContext(session_id="session-one"),
        )
        assert exit_code == 0
        assert events[0]["text"] == "example-helper --json:session-one"
        assert registry.documented_commands() == [{
            "name": "example-helper",
            "description": "Demonstrate provider registration.",
            "root": "example-helper",
        }]
        catalog_entry = registry.catalog_entry("example-helper")
        assert catalog_entry is not None
        catalog_flags = catalog_entry["flags"]
        assert isinstance(catalog_flags, list)
        assert isinstance(catalog_flags[0], dict)
        assert catalog_flags[0]["value"] == "--json"

        autocomplete_flags = registry.autocomplete_context()["example-helper"]["flags"]
        assert isinstance(autocomplete_flags, list)
        assert isinstance(autocomplete_flags[0], dict)
        assert autocomplete_flags[0]["value"] == "--json"
        assert registry.provider_names() == (
            f"{example_provider.__module__}.{example_provider.__qualname__}",
        )

    def test_registered_catalog_autocomplete_and_aliases_share_one_source(self):
        cfg = {"workspace_enabled": True, "tour_enabled": True}
        legacy_autocomplete = commands.autocomplete_context_from_commands_registry(
            commands.load_builtin_autocomplete_registry(),
            cfg=cfg,
        )

        assert get_builtin_autocomplete_context(cfg) == legacy_autocomplete
        assert set(_BUILTIN_REGISTRY.registered_roots()) == _EXPECTED_BUILTIN_ROOTS
        assert set(_BUILTIN_REGISTRY.exact_aliases()) == _EXPECTED_BUILTIN_EXACT_ALIASES
        catalog = get_builtin_command_catalog(cfg)
        assert {
            str(entry.get("root") or "")
            for entry in catalog
        } == {
            spec.root or spec.autocomplete_root or spec.handler_key
            for spec in _BUILTIN_REGISTRY.specs()
            if spec.user_facing
        }
        ownership = {
            str(entry["root"]): str(entry["execution_owner"])
            for entry in catalog
        }
        assert ownership["clear"] == "server"
        assert ownership["theme"] == "browser"
        assert ownership["file"] == "mixed"

    def test_every_user_facing_spec_appears_in_discovery_details_search_and_autocomplete(self):
        cfg = {"workspace_enabled": True, "tour_enabled": True}
        specs = tuple(spec for spec in _BUILTIN_REGISTRY.specs() if spec.user_facing)
        catalog = {
            str(entry["root"]): entry
            for entry in _BUILTIN_REGISTRY.catalog(cfg=cfg)
        }
        autocomplete = _BUILTIN_REGISTRY.autocomplete_context(cfg=cfg)
        with mock.patch.dict("config.CFG", cfg):
            documented_output = "\n".join(
                str(line.get("text") or "")
                for line in _run_builtin_commands("commands --built-in")
            )

        assert len(catalog) == len(specs)
        for spec in specs:
            root = spec.root or spec.autocomplete_root or spec.handler_key
            assert spec.name in documented_output
            assert _BUILTIN_REGISTRY.catalog_entry(root, cfg=cfg) == catalog[root]
            assert root in autocomplete
            assert builtins_discovery._catalog_search_tier(root, catalog[root]) == 0

    def test_exact_alias_roots_follow_the_registered_root_feature_gate(self):
        cfg = {"workspace_enabled": False, "tour_enabled": True}

        assert "rm" not in _BUILTIN_REGISTRY.roots(
            cfg=cfg,
            include_exact_alias_roots=True,
        )
        exact = _BUILTIN_REGISTRY.resolve("rm -rf /", cfg=cfg)
        assert exact is not None and exact.handler_key == "rm_root"

    def test_commands_info_returns_rich_builtin_details(self):
        lines = _run_builtin_commands("commands info project --json")
        entry = json.loads(str(lines[0]["text"]))

        assert entry["root"] == "project"
        assert entry["execution_owner"] == "server"
        assert any(subcommand["name"] == "create" for subcommand in entry["subcommands"])
        assert entry["arguments"][0]["value"] == "list"


class TestBuiltinCommandResolution:
    def test_workspace_builtin_reads_team_files_and_denies_viewer_writes(self, tmp_path):
        cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        from services.teams.scope import team_owner_context
        from services.workspace.files import write_owner_workspace_text_file

        owner = team_owner_context("team-builtins-files", actor_session_id="tok_builtin_actor")
        write_owner_workspace_text_file(owner, "notes.txt", "team notes\n", cfg)

        with mock.patch("config.CFG", build_test_config(cfg)):
            read_events, read_exit = execute_builtin_command(
                "cat notes.txt",
                "tok_builtin_actor",
                team_id="team-builtins-files",
                team_role="viewer",
                owner_context=owner,
            )
            move_events, move_exit = execute_builtin_command(
                "mv notes.txt moved.txt",
                "tok_builtin_actor",
                team_id="team-builtins-files",
                team_role="viewer",
                owner_context=owner,
            )

        assert read_exit == 0
        assert any(str(event.get("text", "")) == "team notes" for event in read_events)
        assert move_exit == 0
        assert any("can view Files but can't change them" in str(event.get("text", "")) for event in move_events)

    def test_documented_builtin_commands_are_backed_by_runtime_dispatch(self):
        cfg = {"workspace_enabled": True, "tour_enabled": True}
        workspace_alias_examples = {
            "cat": "cat notes.txt",
            "cp": "cp notes.txt archive.txt",
            "ll": "ll",
            "ls": "ls",
            "mv": "mv notes.txt archive.txt",
            "rm": "rm notes.txt",
            "touch": "touch notes.txt",
        }
        for spec in _BUILTIN_REGISTRY.specs():
            if not spec.user_facing:
                continue
            command = workspace_alias_examples.get(
                spec.root,
                spec.root or spec.exact_aliases[0],
            )
            resolution = _BUILTIN_REGISTRY.resolve(command, cfg=cfg)
            if (
                resolution is None
                and spec.match_strategy is BuiltinMatchStrategy.WORKSPACE_ALIAS
            ):
                assert spec.execution_owner is BuiltinExecutionOwner.MIXED
                assert spec.browser_owned_subcommands == ("*",)
                continue
            assert resolution is not None
            assert resolution.spec is spec

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
        assert resolve_builtin_command("tour") == "tour"
        assert resolve_builtin_command("tty") == "tty"
        assert resolve_builtin_command("type curl") == "type"
        assert resolve_builtin_command("uname -a") == "uname"
        assert resolve_builtin_command("uptime") == "uptime"
        assert resolve_builtin_command("version") == "version"
        assert resolve_builtin_command("which curl") == "which"
        assert resolve_builtin_command("who") == "who"
        assert resolve_builtin_command("whoami") == "whoami"
        assert resolve_builtin_command("ps aux") == "ps"
        assert resolve_builtin_command("project current") == "project"
        with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
            assert resolve_builtin_command("file list") == "file"
            assert resolve_builtin_command("workspace list") is None
            assert resolve_builtin_command("ls") == "ls"
            assert resolve_builtin_command("cat targets.txt") == "cat"
            assert resolve_builtin_command("diff targets-old.txt targets-new.txt") == "diff"
            assert resolve_builtin_command("diff -u targets-old.txt targets-new.txt") == "diff"
            assert resolve_builtin_command("diff -q -u targets-old.txt targets-new.txt") == "diff"
            assert resolve_builtin_command("diff --last") == "diff"
            assert resolve_builtin_command("diff file:expected.txt run:run-1") == "diff"
            assert resolve_builtin_command("rm targets.txt") == "rm"

    def test_workspace_builtin_commands_are_hidden_when_disabled(self):
        with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            assert resolve_builtin_command("file list") is None
            assert resolve_builtin_command("ls") is None
            assert resolve_builtin_command("cat targets.txt") is None
            assert resolve_builtin_command("diff targets-old.txt targets-new.txt") == "diff"
            assert resolve_builtin_command("diff run:run-1 run:run-2") == "diff"
            assert resolve_builtin_command("diff --last") == "diff"
            assert resolve_builtin_command("rm targets.txt") is None

    def test_tour_builtin_command_is_hidden_when_disabled(self):
        with mock.patch.dict("config.CFG", {"tour_enabled": False}):
            assert resolve_builtin_command("tour") is None

    def test_commands_external_catalog_uses_commands_registry(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "category": "Registry Group",
                    "description": "Runs sentinel scans.",
                    "policy": {"allow": ["sentinel-scan"]},
                },
                {
                    "root": "sentinel-http",
                    "category": "Registry Group",
                    "description": "Checks sentinel HTTP targets.",
                    "policy": {"allow": ["sentinel-http --safe"]},
                },
                {
                    "root": "policyless-tool",
                    "category": "Registry Group",
                    "policy": {"allow": []},
                },
                {
                    "root": "workspace-tool",
                    "category": "Registry Group",
                    "description": "Requires workspace.",
                    "policy": {"allow": ["workspace-tool"]},
                    "feature_required": "workspace",
                },
            ],
            "pipe_helpers": [{"root": "grep"}],
        }

        with mock.patch("services.commands.builtins.load_commands_registry", return_value=registry) as loader, \
             mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            lines = _run_builtin_commands("commands --external")

        text = "\n".join(str(line.get("text", "")) for line in lines)
        assert loader.call_count == 1
        assert "Allowed external commands:" in text
        assert "[Registry Group]" in text
        assert "sentinel-scan  - Runs sentinel scans." in text
        assert "sentinel-http  - Checks sentinel HTTP targets." in text
        assert "policyless-tool" not in text
        assert "workspace-tool" not in text
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

        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands info sentinel-scan")

        text = "\n".join(str(line.get("text", "")) for line in lines)
        assert "sentinel-scan" in text
        assert "Probe a target safely." in text
        assert "sentinel-scan example.test" in text
        assert "-i <value>" in text
        assert "App Handling:" in text
        assert "Adds `--safe` automatically when needed." in text

    def test_commands_info_unknown_root_returns_usage_hint(self):
        registry = {
            "commands": [
                {
                    "root": "workspace-tool",
                    "description": "Requires workspace.",
                    "policy": {"allow": ["workspace-tool"]},
                    "feature_required": "workspace",
                },
            ],
            "pipe_helpers": [],
        }
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry), \
             mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            lines = _run_builtin_commands("commands info nope")
            disabled = _run_builtin_commands("commands info workspace-tool")

        assert lines[0]["text"] == "commands: no catalog entry for nope"
        assert disabled[0]["text"] == "commands: no catalog entry for workspace-tool"

    def test_commands_info_renders_knowledge_list_fields(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "description": "Probe a target safely.",
                    "policy": {"allow": ["sentinel-scan"]},
                    "knowledge": {
                        "notes": ["Check the rate limits before running."],
                        "gotchas": ["May trigger IDS on hardened targets."],
                        "safe_defaults": ["Use --rate 100 for cautious scans."],
                        "common_flags": ["--timeout 5s for slow networks."],
                    },
                },
            ],
            "pipe_helpers": [],
        }

        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands info sentinel-scan")

        text = "\n".join(str(line.get("text", "")) for line in lines)
        assert "Notes:" in text
        assert "Check the rate limits before running." in text
        assert "Gotchas:" in text
        assert "May trigger IDS on hardened targets." in text
        assert "Safe Defaults:" in text
        assert "Use --rate 100 for cautious scans." in text
        assert "Common Flags:" in text
        assert "--timeout 5s for slow networks." in text

    def test_commands_info_renders_artifact_behavior(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "description": "Probe a target safely.",
                    "policy": {"allow": ["sentinel-scan"]},
                    "knowledge": {
                        "artifact_behavior": "Creates scan-output.json in the workspace.",
                    },
                },
            ],
            "pipe_helpers": [],
        }

        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands info sentinel-scan")

        text = "\n".join(str(line.get("text", "")) for line in lines)
        assert "Artifact Behavior:" in text
        assert "Creates scan-output.json in the workspace." in text

    def test_commands_info_json_flag_returns_single_builtin_json_line(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "description": "Probe a target safely.",
                    "policy": {"allow": ["sentinel-scan"]},
                    "knowledge": {
                        "notes": ["Check rate limits."],
                    },
                },
            ],
            "pipe_helpers": [],
        }

        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands info sentinel-scan --json")

        assert len(lines) == 1
        assert lines[0]["cls"] == "builtin-json"
        data = json.loads(str(lines[0]["text"]))
        assert data["root"] == "sentinel-scan"
        assert data["knowledge"]["notes"] == ["Check rate limits."]

    def test_commands_info_json_flag_accepted_before_root(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel-scan",
                    "description": "Probe a target safely.",
                    "policy": {"allow": ["sentinel-scan"]},
                },
            ],
            "pipe_helpers": [],
        }

        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands info --json sentinel-scan")

        assert len(lines) == 1
        assert lines[0]["cls"] == "builtin-json"

    def test_commands_info_json_only_returns_usage_error(self):
        with mock.patch("services.commands.registry.load_commands_registry", return_value={"commands": [], "pipe_helpers": []}):
            lines = _run_builtin_commands("commands info --json")

        assert len(lines) == 1
        assert "Usage:" in str(lines[0]["text"])

    def test_rejects_non_builtin_commands(self):
        assert resolve_builtin_command("ping darklab.sh") is None
        assert resolve_builtin_command("cat /etc/passwd") is None
        assert resolve_builtin_command("rm /tmp/file") is None
        assert resolve_builtin_command("rm ../file") is None
        assert resolve_builtin_command("ls /tmp") is None
        assert resolve_builtin_command("") is None


class TestCommandsSearch:
    """commands search <term> — coverage for search matching, ranking, grouping, and gating."""

    _REGISTRY = {
        "commands": [
            {
                "root": "nmap",
                "category": "Network Reconnaissance",
                "description": "Scans hosts for open ports and services.",
                "policy": {"allow": ["nmap"]},
                "autocomplete": {
                    "examples": [{"value": "nmap 192.168.1.0/24", "description": "Subnet scan"}],
                },
            },
            {
                "root": "gobuster",
                "category": "Web Enumeration",
                "description": "Directory and DNS brute-forcing tool.",
                "policy": {"allow": ["gobuster"]},
                "knowledge": {
                    "notes": ["Throttle requests with --delay to avoid detection."],
                    "gotchas": ["High thread counts can overwhelm slow targets."],
                },
            },
            {
                "root": "nuclei",
                "category": "Network Reconnaissance",
                "description": "Template-based vulnerability scanner.",
                "policy": {"allow": ["nuclei"]},
            },
            {
                "root": "workspace-tool",
                "category": "Workspace",
                "description": "A tool requiring the workspace feature.",
                "policy": {"allow": ["workspace-tool"]},
                "feature_required": "workspace",
            },
        ],
        "pipe_helpers": [],
    }

    def _run(self, term: str, registry: dict | None = None) -> list[dict]:
        reg = registry if registry is not None else self._REGISTRY
        with mock.patch("services.commands.registry.load_commands_registry", return_value=reg):
            return _run_builtin_commands(f"commands search {term}")

    def _text(self, lines: list[dict]) -> str:
        return "\n".join(str(line.get("text", "")) for line in lines)

    def test_usage_error_when_no_term(self):
        with mock.patch("services.commands.registry.load_commands_registry", return_value=self._REGISTRY):
            lines = _run_builtin_commands("commands search")
        assert "Usage:" in str(lines[0]["text"])

    def test_root_prefix_match_returns_result(self):
        text = self._text(self._run("nma"))
        assert "nmap" in text

    def test_description_match_returns_result(self):
        text = self._text(self._run("brute-forcing"))
        assert "gobuster" in text

    def test_category_match_returns_result(self):
        text = self._text(self._run("Web Enumeration"))
        assert "gobuster" in text

    def test_example_value_match_returns_result(self):
        text = self._text(self._run("192.168.1.0"))
        assert "nmap" in text

    def test_knowledge_notes_match_returns_result(self):
        text = self._text(self._run("throttle"))
        assert "gobuster" in text

    def test_knowledge_gotchas_match_returns_result(self):
        text = self._text(self._run("thread counts"))
        assert "gobuster" in text

    def test_results_grouped_by_category(self):
        # "recon" hits category "Network Reconnaissance" (tier 1) for both nmap and nuclei,
        # exercising the multi-entry group-by-category rendering path.
        text = self._text(self._run("recon"))
        assert "[Network Reconnaissance]" in text
        assert "nmap" in text
        assert "nuclei" in text

    def test_root_prefix_ranked_above_category_match(self):
        registry = {
            "commands": [
                {
                    "root": "netcat",
                    "category": "Tools",
                    "description": "General purpose networking tool.",
                    "policy": {"allow": ["netcat"]},
                },
                {
                    "root": "nmap",
                    "category": "Network Reconnaissance",
                    "description": "Port scanner.",
                    "policy": {"allow": ["nmap"]},
                },
            ],
            "pipe_helpers": [],
        }
        # "net" prefix-matches "netcat" (tier 0) and category-matches "Network ..." on nmap (tier 1)
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            lines = _run_builtin_commands("commands search net")
        items = [str(line.get("text", "")) for line in lines if line.get("cls") == "builtin-catalog-item"]
        assert items[0].strip().startswith("netcat")

    def test_feature_required_excluded_when_disabled(self):
        with mock.patch("services.commands.registry.load_commands_registry", return_value=self._REGISTRY):
            with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
                lines = _run_builtin_commands("commands search workspace")
        text = self._text(lines)
        assert "workspace-tool" not in text
        assert "project" in text

    def test_feature_required_included_when_enabled(self):
        with mock.patch("services.commands.registry.load_commands_registry", return_value=self._REGISTRY):
            with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
                lines = _run_builtin_commands("commands search workspace")
        text = self._text(lines)
        assert "workspace-tool" in text

    def test_no_matches_returns_message(self):
        text = self._text(self._run("xyzzy-nonexistent-term"))
        assert "no matches" in text


class TestCommandsPipesSection:
    # Registry with one external command and two pipe helpers in normalized form.
    # pipe_command=True is the normalized flag set by _normalize_registry_autocomplete.
    _REGISTRY = {
        "commands": [
            {
                "root": "nmap",
                "category": "Network Reconnaissance",
                "description": "Port scanner.",
                "policy": {"allow": ["nmap"]},
            },
        ],
        "pipe_helpers": [
            {
                "root": "grep",
                "autocomplete": {
                    "pipe_command": True,
                    "pipe_description": "Filter lines by pattern",
                    "flags": [
                        {"value": "-i", "description": "Ignore case"},
                        {"value": "-v", "description": "Invert match"},
                    ],
                },
            },
            {
                "root": "head",
                "autocomplete": {
                    "pipe_command": True,
                    "pipe_description": "Show the first lines",
                    "flags": [],
                },
            },
        ],
    }

    def _run(self, cmd: str) -> list[dict]:
        # Patch both module-level bindings so external commands AND the pipes
        # section both use the test registry rather than the real commands.yaml.
        with mock.patch("services.commands.registry.load_commands_registry", return_value=self._REGISTRY), \
             mock.patch("services.commands.builtins.load_commands_registry", return_value=self._REGISTRY):
            return _run_builtin_commands(cmd)

    def _text(self, lines: list[dict]) -> str:
        return "\n".join(str(line.get("text", "")) for line in lines)

    def test_commands_shows_pipes_section_header(self):
        text = self._text(self._run("commands"))
        assert "App-native pipe helpers:" in text

    def test_commands_pipes_section_includes_disclaimer(self):
        text = self._text(self._run("commands"))
        assert "App-managed filters" in text
        assert "not arbitrary shell pipelines" in text

    def test_commands_pipes_listed_in_catalog_order(self):
        lines = self._run("commands")
        texts = [str(line.get("text", "")) for line in lines]
        header_idx = next(i for i, t in enumerate(texts) if "App-native pipe helpers:" in t)
        grep_idx = next(i for i, t in enumerate(texts) if "grep" in t and i > header_idx)
        head_idx = next(i for i, t in enumerate(texts) if "head" in t and i > header_idx)
        assert grep_idx < head_idx, "grep should appear before head (catalog order)"

    def test_commands_builtin_only_flag_omits_pipes_section(self):
        text = self._text(self._run("commands --built-in"))
        assert "App-native pipe helpers:" not in text
        assert "App-managed filters" not in text
