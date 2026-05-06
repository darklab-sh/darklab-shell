"""
Tests for pure utility functions across the app modules:
  - split_chained_commands      (commands.py)
  - command registry loading    (commands.py)
  - load_faq                    (commands.py)
  - _is_denied edge cases       (commands.py)
  - is_command_allowed path-blocking edge cases (commands.py)
  - rewrite_command case-insensitivity          (commands.py)
  - pid_register / pid_pop in-process mode      (process.py)
  - _format_retention                           (permalinks.py)
  - run-output artifact capture/read helpers    (run_output_store.py)
Run with: pytest tests/ (from the repo root)
"""

import errno
import gzip
import importlib.util
import json
import os
import random
import re
import shlex
import sqlite3
import subprocess
import tempfile
import textwrap
import unittest.mock as mock
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
import yaml
import process
import pty_service
import run_broker
import database
import app as shell_app
import config as app_config
import commands  # noqa: F401 — used as mock.patch("commands.X") target
import builtin_commands
import session_variables
import workspace as workspace_module
import wordlists
from commands import (
    split_chained_commands, load_all_faq, load_all_workflows, load_faq,
    load_welcome, load_ascii_art, load_ascii_mobile_art, load_welcome_hints,
    load_mobile_welcome_hints, autocomplete_context_from_commands_registry,
    load_autocomplete_context_from_commands_registry, load_command_policy, load_container_smoke_test_commands,
    load_allow_grouping_flags, load_commands_registry, load_workflows,
    interactive_pty_specs_from_registry,
    command_catalog_entry, command_catalog_from_registry, is_command_allowed, rewrite_command,
)
from permalinks import _format_retention, _expiry_note, _permalink_error_page, _normalize_permalink_lines, _prompt_echo_text
from output_signals import OutputSignalClassifier, classify_line, command_root, extract_target
from run_output_store import RunOutputCapture, RUN_OUTPUT_DIR, load_full_output_entries, load_full_output_lines
from workspace import (
    InvalidWorkspacePath, WorkspaceDisabled, WorkspacePermissionDenied, WorkspaceQuotaExceeded,
    cleanup_inactive_workspaces, create_workspace_directory, delete_workspace_file, delete_workspace_path,
    expand_workspace_path_pattern,
    ensure_session_workspace, list_workspace_directories, list_workspace_files,
    prepare_workspace_directory_for_command, prepare_workspace_file_for_command, read_workspace_text_file, resolve_workspace_path,
    session_workspace_name, workspace_usage,
    touch_session_workspace, workspace_path_info, write_workspace_text_file, WORKSPACE_COMMAND_WRITE_FILE_MODE,
    WORKSPACE_DIR_MODE, WORKSPACE_FILE_MODE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_HISTORY_PATH = REPO_ROOT / "scripts" / "seed_history.py"


def _load_seed_history_module():
    spec = importlib.util.spec_from_file_location("seed_history", SEED_HISTORY_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── split_chained_commands ────────────────────────────────────────────────────

class TestSplitChainedCommands:
    def test_plain_command_returns_one_element(self):
        parts = split_chained_commands("ping google.com")
        assert parts == ["ping google.com"]

    def test_pipe(self):
        parts = split_chained_commands("nmap 10.0.0.1 | grep open")
        assert len(parts) == 2

    def test_double_ampersand(self):
        parts = split_chained_commands("dig google.com && id")
        assert len(parts) == 2

    def test_double_pipe(self):
        parts = split_chained_commands("false || id")
        assert len(parts) == 2

    def test_semicolon(self):
        parts = split_chained_commands("echo a; echo b")
        assert len(parts) == 2

    def test_backtick(self):
        parts = split_chained_commands("ping `hostname`")
        assert len(parts) == 2

    def test_dollar_subshell(self):
        parts = split_chained_commands("ping $(hostname)")
        assert len(parts) == 2

    def test_redirect_out(self):
        parts = split_chained_commands("nmap -sV 10.0.0.1 > /tmp/out")
        assert len(parts) == 2

    def test_redirect_append(self):
        parts = split_chained_commands("nmap -sV 10.0.0.1 >> /tmp/out")
        assert len(parts) == 2

    def test_redirect_in(self):
        parts = split_chained_commands("curl darklab.sh < /etc/hosts")
        assert len(parts) == 2

    def test_empty_parts_stripped(self):
        # Splitting "a | " should not produce an empty trailing element
        parts = split_chained_commands("a | ")
        assert all(p for p in parts)

    def test_empty_string_returns_empty_list(self):
        assert split_chained_commands("") == []


class TestLoadConfig:
    def test_local_config_overrides_base_config_without_replacing_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "config.yaml")
            local_path = os.path.join(tmp, "config.local.yaml")
            with open(base_path, "w") as f:
                f.write(textwrap.dedent(
                    """
                    app_name: base-shell
                    prompt_username: base
                    prompt_domain: local
                    default_theme: base-theme.yaml
                    output_preview_max_mb: 2MB
                    full_output_max_mb: 7MB
                    rate_limit_per_minute: 30
                    """
                ))
            with open(local_path, "w") as f:
                f.write(textwrap.dedent(
                    """
                    app_name: local-shell
                    prompt_username: local
                    rate_limit_per_minute: 99
                    """
                ))
            cfg = app_config.load_config(tmp)

        assert cfg["app_name"] == "local-shell"
        assert cfg["prompt_username"] == "local"
        assert cfg["prompt_domain"] == "local"
        assert cfg["default_theme"] == "base-theme.yaml"
        assert cfg["output_preview_max_mb"] == 2
        assert cfg["output_preview_max_bytes"] == 2 * 1024 * 1024
        assert cfg["full_output_max_mb"] == 7
        assert cfg["full_output_max_bytes"] == 7 * 1024 * 1024
        assert cfg["rate_limit_per_minute"] == 99
        assert cfg["trusted_proxy_cidrs"] == ["127.0.0.1/32", "::1/128"]
        assert cfg["data_dir"] == ""
        assert cfg["workspace_enabled"] is False
        assert cfg["workspace_backend"] == "tmpfs"
        assert cfg["workspace_quota_mb"] == 50
        assert cfg["workspace_max_file_mb"] == 5
        assert cfg["workspace_max_files"] == 100
        assert cfg["workspace_inactivity_ttl_hours"] == 1

    def test_share_redaction_enabled_defaults_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "config.yaml"), "w") as f:
                f.write("app_name: test-shell\n")
            cfg = app_config.load_config(tmp)
        assert cfg["share_redaction_enabled"] is True

    def test_get_share_redaction_rules_includes_builtins_and_custom_rules_when_enabled(self):
        rules = app_config.get_share_redaction_rules({
            "share_redaction_enabled": True,
            "share_redaction_rules": [
                {"label": "custom", "pattern": "internal", "replacement": "[custom]"},
            ],
        })
        labels = [rule["label"] for rule in rules]
        assert "bearer token" in labels
        assert "email address" in labels
        assert labels[-1] == "custom"

    def test_get_share_redaction_rules_returns_empty_when_disabled(self):
        rules = app_config.get_share_redaction_rules({
            "share_redaction_enabled": False,
            "share_redaction_rules": [
                {"label": "custom", "pattern": "internal", "replacement": "[custom]"},
            ],
        })
        assert rules == []

    def test_resolve_data_dir_prefers_app_data_dir_environment_override(self):
        with tempfile.TemporaryDirectory() as env_dir, tempfile.TemporaryDirectory() as cfg_dir:
            with mock.patch.dict(os.environ, {"APP_DATA_DIR": env_dir}):
                assert app_config.resolve_data_dir({"data_dir": cfg_dir}) == env_dir

    def test_resolve_data_dir_uses_configured_data_dir_when_environment_is_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("APP_DATA_DIR", None)
                assert app_config.resolve_data_dir({"data_dir": tmp}) == tmp

    def test_resolve_data_dir_falls_back_to_tmp_when_data_is_not_writable(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APP_DATA_DIR", None)
            with mock.patch.object(app_config, "_is_writable_directory", side_effect=lambda path: path == "/tmp"):
                assert app_config.resolve_data_dir({"data_dir": ""}) == "/tmp"

    def test_resolve_data_dir_rejects_unwritable_configured_data_dir(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APP_DATA_DIR", None)
            with mock.patch.object(app_config, "_is_writable_directory", return_value=False):
                try:
                    app_config.resolve_data_dir({"data_dir": "/not-writable"})
                    assert False, "expected unwritable configured data_dir to fail"
                except RuntimeError as exc:
                    assert "data_dir is not writable: /not-writable" in str(exc)

    def test_workspace_root_env_warning_only_logs_on_mismatch(self):
        with mock.patch.object(shell_app.log, "warning") as warning:
            shell_app._warn_workspace_root_config_drift(
                {"workspace_root": "/tmp/workspaces"},
                {"WORKSPACE_ROOT": "/tmp/workspaces"},
            )
            warning.assert_not_called()

        with mock.patch.object(shell_app.log, "warning") as warning:
            shell_app._warn_workspace_root_config_drift(
                {"workspace_root": "/tmp/app-workspaces"},
                {"WORKSPACE_ROOT": "/tmp/env-workspaces"},
            )

        warning.assert_called_once()
        args, kwargs = warning.call_args
        assert args == ("WORKSPACE_ROOT_MISMATCH",)
        assert kwargs["extra"]["workspace_root_env"].endswith("/tmp/env-workspaces")
        assert kwargs["extra"]["workspace_root_config"].endswith("/tmp/app-workspaces")


class TestSessionWorkspace:
    def _cfg(self, root, **overrides):
        cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(root),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        cfg.update(overrides)
        return cfg

    def test_disabled_workspace_rejects_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp, workspace_enabled=False)
            try:
                ensure_session_workspace("session-1", cfg)
                assert False, "expected disabled workspace to reject operations"
            except WorkspaceDisabled:
                pass

    def test_session_workspace_uses_hashed_session_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            path = ensure_session_workspace("tok_secret_value", cfg)

            assert path.name == session_workspace_name("tok_secret_value")
            assert "tok_secret_value" not in str(path)
            assert path.exists()
            mode = path.stat().st_mode & 0o7777
            assert WORKSPACE_DIR_MODE == 0o3730
            assert mode & 0o1730 == 0o1730
            assert not mode & 0o004

    def test_session_workspace_logs_chmod_failures_without_blocking_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            with mock.patch("workspace.os.chmod", side_effect=OSError("chmod blocked")):
                with mock.patch.object(workspace_module.log, "warning") as warning:
                    path = ensure_session_workspace("session-1", cfg)

            assert path.exists()
            warning.assert_called_once()
            args = warning.call_args.args
            assert args[0] == "WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s"
            assert args[1] == path
            assert args[2] == WORKSPACE_DIR_MODE

    def test_write_read_list_delete_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)

            written = write_workspace_text_file("session-1", "targets.txt", "darklab.sh\n", cfg)
            assert written == {"path": "targets.txt", "size": 11}
            written_path = resolve_workspace_path("session-1", "targets.txt", cfg)
            assert (written_path.stat().st_mode & 0o777) == WORKSPACE_FILE_MODE
            assert not written_path.stat().st_mode & 0o007
            assert read_workspace_text_file("session-1", "targets.txt", cfg) == "darklab.sh\n"
            assert list_workspace_files("session-1", cfg)[0]["path"] == "targets.txt"
            assert workspace_usage("session-1", cfg).bytes_used == 11

            delete_workspace_file("session-1", "targets.txt", cfg)
            assert list_workspace_files("session-1", cfg) == []

    def test_prepare_workspace_file_for_command_uses_limited_write_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            write_workspace_text_file("session-1", "output.txt", "old\n", cfg)
            path = resolve_workspace_path("session-1", "output.txt", cfg)

            prepare_workspace_file_for_command(path, mode="write")

            assert (path.stat().st_mode & 0o777) == WORKSPACE_COMMAND_WRITE_FILE_MODE
            assert not path.stat().st_mode & 0o007

    def test_prepare_workspace_directory_for_command_does_not_temporarily_widen_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "amass"
            path.mkdir()

            with mock.patch("workspace.shutil.which", return_value="/usr/bin/sudo"), \
                    mock.patch("workspace.pwd.getpwnam", return_value=object()), \
                    mock.patch("workspace.subprocess.run") as run:
                prepare_workspace_directory_for_command(path, mode="read_write")

            commands = [call.args[0] for call in run.call_args_list]
            assert commands == [
                ["/usr/bin/sudo", "-u", "scanner", "-g", "appuser", "chmod", "3770", str(path)],
            ]

    def test_list_repairs_command_created_workspace_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            root = ensure_session_workspace("session-1", cfg)
            command_dir = root / "subfinder"
            command_dir.mkdir()
            command_file = command_dir / "provider-config.yaml"
            command_file.write_text("sources: []\n")
            os.chmod(command_dir, 0o2700)
            os.chmod(command_file, 0o600)

            with mock.patch("workspace._scanner_uid", return_value=command_dir.stat().st_uid):
                assert list_workspace_files("session-1", cfg)[0]["path"] == "subfinder/provider-config.yaml"
                assert list_workspace_directories("session-1", cfg)[0]["path"] == "subfinder"
                assert read_workspace_text_file("session-1", "subfinder/provider-config.yaml", cfg) == "sources: []\n"
                assert command_dir.stat().st_mode & 0o070 == 0o070
                assert not command_dir.stat().st_mode & 0o007
                assert (command_file.stat().st_mode & 0o777) == WORKSPACE_FILE_MODE

    def test_read_workspace_permission_denied_is_not_raw_os_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            write_workspace_text_file("session-1", "provider-config.yaml", "sources: []\n", cfg)

            with mock.patch("workspace.os.open", side_effect=PermissionError(errno.EACCES, "denied")):
                with pytest.raises(WorkspacePermissionDenied):
                    read_workspace_text_file("session-1", "provider-config.yaml", cfg)

    def test_delete_workspace_file_falls_back_to_scanner_owner_for_nested_command_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            write_workspace_text_file("session-1", "nmap-dot/amass.dot", "digraph {}\n", cfg)
            path = resolve_workspace_path("session-1", "nmap-dot/amass.dot", cfg)

            with mock.patch("workspace.Path.unlink", side_effect=PermissionError), \
                    mock.patch("workspace.shutil.which", return_value="/usr/bin/sudo"), \
                    mock.patch("workspace.pwd.getpwnam", return_value=object()), \
                    mock.patch("workspace.subprocess.run") as run:
                delete_workspace_file("session-1", "nmap-dot/amass.dot", cfg)

            run.assert_called_once_with(
                ["/usr/bin/sudo", "-u", "scanner", "-g", "appuser", "rm", "--", str(path)],
                check=True,
                stdout=mock.ANY,
                stderr=mock.ANY,
                timeout=5,
            )

    def test_workspace_path_info_and_delete_remove_folders_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            create_workspace_directory("session-1", "reports/empty", cfg)
            write_workspace_text_file("session-1", "reports/one.txt", "1", cfg)
            write_workspace_text_file("session-1", "reports/nested/two.txt", "2", cfg)

            assert workspace_path_info("session-1", "reports", cfg) == {
                "path": "reports",
                "kind": "directory",
                "file_count": 2,
            }

            result = delete_workspace_path("session-1", "reports", cfg)

            assert result.kind == "directory"
            assert result.file_count == 2
            assert result.path == "reports"
            assert list_workspace_files("session-1", cfg) == []
            assert list_workspace_directories("session-1", cfg) == []

    def test_create_and_list_empty_directories_without_file_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)

            created = create_workspace_directory("session-1", "reports/empty", cfg)

            assert created == {"path": "reports/empty"}
            assert {item["path"] for item in list_workspace_directories("session-1", cfg)} == {
                "reports",
                "reports/empty",
            }
            assert list_workspace_files("session-1", cfg) == []
            assert workspace_usage("session-1", cfg).file_count == 0

    def test_workspace_glob_pattern_matches_one_path_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            create_workspace_directory("session-1", "darklab", cfg)
            create_workspace_directory("session-1", "reports/darklab-nested", cfg)
            write_workspace_text_file("session-1", "darklab-a.txt", "1", cfg)
            write_workspace_text_file("session-1", "darklab-b.txt", "2", cfg)
            write_workspace_text_file("session-1", "reports/darklab-c.txt", "3", cfg)

            matches = expand_workspace_path_pattern("session-1", "darklab-*", cfg)

            assert [(item.path, item.kind) for item in matches] == [
                ("darklab-a.txt", "file"),
                ("darklab-b.txt", "file"),
            ]

    def test_rejects_absolute_traversal_and_backslash_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            for bad_path in ["/etc/passwd", "../escape", "safe/../../escape", "safe\\.txt"]:
                try:
                    resolve_workspace_path("session-1", bad_path, cfg, ensure_parent=True)
                    assert False, f"expected invalid path rejection for {bad_path}"
                except InvalidWorkspacePath:
                    pass

    def test_allows_hidden_files_that_are_listed_by_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            hidden = resolve_workspace_path("session-1", ".config/amass.txt", cfg, ensure_parent=True)

            assert hidden.name == "amass.txt"
            assert hidden.parent.name == ".config"

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            root = ensure_session_workspace("session-1", cfg)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (root / "link").symlink_to(outside, target_is_directory=True)

            try:
                resolve_workspace_path("session-1", "link/file.txt", cfg)
                assert False, "expected symlink path rejection"
            except InvalidWorkspacePath:
                pass

    def test_rejects_final_component_symlink_swaps(self):
        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("final-component no-follow open is not supported on this platform")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp)
            outside = Path(tmp) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            real_resolve = workspace_module.resolve_workspace_path

            def swap_final_component(session_id, relative_path, active_cfg=None, *, ensure_parent=False):
                path = real_resolve(session_id, relative_path, active_cfg, ensure_parent=ensure_parent)
                if path.exists() or path.is_symlink():
                    path.unlink()
                path.symlink_to(outside)
                return path

            operations = [
                lambda: read_workspace_text_file("session-1", "target.txt", cfg),
                lambda: workspace_module.open_workspace_file_for_download("session-1", "target.txt", cfg),
                lambda: write_workspace_text_file("session-1", "target.txt", "replacement\n", cfg),
                lambda: delete_workspace_file("session-1", "target.txt", cfg),
                lambda: workspace_path_info("session-1", "target.txt", cfg),
            ]
            workspace_root = ensure_session_workspace("session-1", cfg)
            for operation in operations:
                target = workspace_root / "target.txt"
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.write_text("inside\n", encoding="utf-8")
                with mock.patch("workspace.resolve_workspace_path", side_effect=swap_final_component):
                    with pytest.raises(InvalidWorkspacePath):
                        operation()
                assert outside.read_text(encoding="utf-8") == "outside\n"

    def test_enforces_file_size_quota_and_file_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(
                tmp,
                workspace_quota_mb=0,
                workspace_max_file_mb=0,
                workspace_max_files=1,
            )
            try:
                write_workspace_text_file("session-1", "too-big.txt", "x", cfg)
                assert False, "expected max file size rejection"
            except WorkspaceQuotaExceeded:
                pass

        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp, workspace_max_files=1)
            write_workspace_text_file("session-1", "one.txt", "1", cfg)
            try:
                write_workspace_text_file("session-1", "two.txt", "2", cfg)
                assert False, "expected max file count rejection"
            except WorkspaceQuotaExceeded:
                pass

    def test_cleanup_removes_only_expired_session_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp, workspace_inactivity_ttl_hours=1)
            old_root = ensure_session_workspace("old-session", cfg)
            fresh_root = ensure_session_workspace("fresh-session", cfg)
            unrelated = Path(tmp) / "manual"
            unrelated.mkdir()
            old_ts = 1000
            fresh_ts = 2000
            os.utime(old_root, (old_ts, old_ts))
            os.utime(fresh_root, (fresh_ts, fresh_ts))

            removed = cleanup_inactive_workspaces(cfg, now=4601)

            assert removed == 1
            assert not old_root.exists()
            assert fresh_root.exists()
            assert unrelated.exists()

    def test_cleanup_uses_session_directory_activity_not_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp, workspace_inactivity_ttl_hours=1)
            root = ensure_session_workspace("session-1", cfg)
            file_path = root / "fresh-output.txt"
            file_path.write_text("fresh\n", encoding="utf-8")
            old_ts = 1000
            fresh_ts = 4500
            os.utime(root, (old_ts, old_ts))
            os.utime(file_path, (fresh_ts, fresh_ts))

            removed = cleanup_inactive_workspaces(cfg, now=4601)

            assert removed == 1
            assert not root.exists()

    def test_touch_session_workspace_extends_cleanup_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp, workspace_inactivity_ttl_hours=1)
            root = ensure_session_workspace("session-1", cfg)
            os.utime(root, (1000, 1000))

            touch_session_workspace("session-1", cfg)

            removed = cleanup_inactive_workspaces(cfg, now=4601)

            assert removed == 0
            assert root.exists()

    def test_cleanup_can_skip_current_session_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._cfg(tmp, workspace_inactivity_ttl_hours=1)
            current_root = ensure_session_workspace("current-session", cfg)
            old_root = ensure_session_workspace("old-session", cfg)
            os.utime(current_root, (1000, 1000))
            os.utime(old_root, (1000, 1000))

            removed = cleanup_inactive_workspaces(cfg, now=4601, skip_session_id="current-session")

            assert removed == 1
            assert current_root.exists()
            assert not old_root.exists()


class TestEntrypointWorkspaceRepair:
    def test_workspace_repair_targets_children_inside_session_directories(self):
        entrypoint = (REPO_ROOT / "entrypoint.sh").read_text()

        assert "chown -R appuser:appuser \"$WORKSPACE_ROOT\"" not in entrypoint
        assert "chown appuser:appuser \"$WORKSPACE_ROOT\"" in entrypoint
        assert "-exec chown appuser:appuser {} \\;" in entrypoint
        assert "find \"$WORKSPACE_ROOT\" -mindepth 2 -exec chown scanner:appuser" not in entrypoint
        assert "find \"$session_dir\" -mindepth 1 -exec chown scanner:appuser" in entrypoint
        assert "find \"$session_dir\" -mindepth 1 -type d -exec chmod 3770" in entrypoint
        assert "find \"$session_dir\" -mindepth 1 -type f -exec chmod 640" in entrypoint


class TestDerivedCommandRegistry:
    def test_commands_registry_loader_normalizes_policy_and_autocomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commands.yaml"
            path.write_text(textwrap.dedent("""
            version: 1
            commands:
              - root: PING
                category: Network
                policy:
                  allow:
                    - PING
                    - ping
                  deny:
                    - ping -f
                workspace_flags:
                  - flag: -iL
                    mode: read
                    value: separate
                    format: text
                  - flag: -oN
                    mode: write
                    value: separate_or_attached
                    format: text
                  - flag: ""
                    mode: write
                runtime_adaptations:
                  inject_flags:
                    - flags:
                        - -sT
                      position: prepend
                      unless_any:
                        - -h
                      unless_any_regex:
                        - "^-s[A-Z]"
                    - flags:
                        - env
                        - XDG_CONFIG_HOME={session_workspace}
                      position: command_prefix
                      requires_workspace: true
                  managed_workspace_directory:
                    flag: -dir
                    directory: ping-db
                    subcommands:
                      - stats
                    reject_message: ping stats uses the managed ping-db session directory.
                  environment:
                    - name: XDG_CONFIG_HOME
                      value: "{managed_workspace_parent}"
                      managed_directory_flag: -dir
                interactive:
                  mode: pty
                  trigger_flag: --live
                  default_rows: 33
                  default_cols: 132
                  max_runtime_seconds: 321
                  allow_input: false
                  requires_args: true
                autocomplete:
                  flags:
                    - value: -c
                      description: Count
                      takes_value: true
                      suggest:
                        - value: "4"
                          description: Four probes
                    - value: -v
                      description: Verbose
                      allow_grouping: true
                    - value: -d
                      description: Target domain
                      takes_value: true
                      value_type: domain
                    - value: -w
                      description: DNS wordlist
                      takes_value: true
                      value_type: wordlist
                      wordlist_category: dns
                  subcommands:
                    stats:
                      description: Show ping stats
                      flags:
                        - value: --json
                          description: JSON output
                      examples:
                        - value: ping stats --json
                          description: Export stats
                  examples:
                    - value: ping -c 4 darklab.sh
                      description: Send four probes
            pipe_helpers:
              - root: grep
                autocomplete:
                  pipe:
                    enabled: true
                    description: Filter lines
                  flags:
                    - value: -i
                      description: Ignore case
            """))
            with mock.patch("commands.COMMANDS_REGISTRY_FILE", str(path)):
                registry = load_commands_registry()

        ping = registry["commands"][0]
        assert ping["root"] == "ping"
        assert ping["category"] == "Network"
        assert ping["policy"]["allow"] == ["ping"]
        assert ping["policy"]["deny"] == ["ping -f"]
        assert ping["allow_grouping_flags"] == ["-v"]
        assert ping["workspace_flags"] == [
            {"flag": "-iL", "mode": "read", "value": "separate", "format": "text"},
            {"flag": "-oN", "mode": "write", "value": "separate_or_attached", "format": "text"},
        ]
        assert ping["runtime_adaptations"]["inject_flags"] == [
            {
                "flags": ["-sT"],
                "position": "prepend",
                "unless_any": ["-h"],
                "unless_any_regex": ["^-s[A-Z]"],
            },
            {
                "flags": ["env", "XDG_CONFIG_HOME={session_workspace}"],
                "position": "command_prefix",
                "unless_any": [],
                "unless_any_regex": [],
                "requires_workspace": True,
            },
        ]
        assert ping["runtime_adaptations"]["managed_workspace_directory"]["flag"] == "-dir"
        assert ping["runtime_adaptations"]["managed_workspace_directory"]["directory"] == "ping-db"
        assert ping["runtime_adaptations"]["environment"] == [{
            "name": "XDG_CONFIG_HOME",
            "value": "{managed_workspace_parent}",
            "managed_directory_flag": "-dir",
        }]
        assert ping["interactive"] == {
            "mode": "pty",
            "trigger_flag": "--live",
            "default_rows": 33,
            "default_cols": 132,
            "max_runtime_seconds": 321,
            "allow_input": False,
            "requires_args": True,
        }
        assert interactive_pty_specs_from_registry(registry) == [{
            "root": "ping",
            "trigger_flag": "--live",
            "default_rows": 33,
            "default_cols": 132,
            "max_runtime_seconds": 321,
            "allow_input": False,
            "requires_args": True,
        }]
        assert ping["autocomplete"]["flags"][0] == {"value": "-c", "description": "Count"}
        assert ping["autocomplete"]["flags"][1] == {"value": "-v", "description": "Verbose"}
        assert ping["autocomplete"]["flags"][2] == {"value": "-d", "description": "Target domain", "value_type": "domain"}
        assert ping["autocomplete"]["flags"][3] == {
            "value": "-w",
            "description": "DNS wordlist",
            "value_type": "wordlist",
            "wordlist_category": "dns",
        }
        assert ping["autocomplete"]["expects_value"] == ["-c", "-d", "-w"]
        assert ping["autocomplete"]["arg_hints"]["-c"][0]["value"] == "4"
        assert ping["autocomplete"]["arg_hints"]["-d"][0]["value"] == "<domain>"
        assert ping["autocomplete"]["arg_hints"]["-d"][0]["value_type"] == "domain"
        assert ping["autocomplete"]["arg_hints"]["-w"][0]["value"] == "<wordlist>"
        assert ping["autocomplete"]["arg_hints"]["-w"][0]["value_type"] == "wordlist"
        assert ping["autocomplete"]["arg_hints"]["-w"][0]["wordlist_category"] == "dns"
        assert ping["autocomplete"]["arg_hints"]["__positional__"][0]["value"] == "stats"
        assert ping["autocomplete"]["subcommands"]["stats"]["description"] == "Show ping stats"
        assert ping["autocomplete"]["subcommands"]["stats"]["flags"][0]["value"] == "--json"
        assert ping["autocomplete"]["subcommands"]["stats"]["examples"][0]["value"] == "ping stats --json"
        assert ping["autocomplete"]["examples"][0]["value"] == "ping -c 4 darklab.sh"
        grep = registry["pipe_helpers"][0]
        assert grep["root"] == "grep"
        assert grep["autocomplete"]["pipe_command"] is True
        assert grep["autocomplete"]["pipe_description"] == "Filter lines"

    def test_command_catalog_derives_reference_data_from_registry(self):
        registry = {
            "commands": [
                {
                    "root": "sentinel",
                    "category": "Registry Group",
                    "description": "Inspect a target.",
                    "policy": {"allow": ["sentinel"], "deny": ["sentinel --unsafe"]},
                    "workspace_flags": [
                        {"flag": "-i", "mode": "read", "value": "separate"},
                    ],
                    "runtime_adaptations": {
                        "inject_flags": [{"flags": ["--safe"], "position": "append"}],
                    },
                    "autocomplete": {
                        "examples": [{"value": "sentinel darklab.sh"}],
                        "flags": [
                            {"value": "-i", "description": "Input file", "takes_value": True},
                        ],
                        "subcommands": {
                            "scan": {
                                "description": "Run a scan.",
                                "examples": [{"value": "sentinel scan darklab.sh"}],
                                "flags": [{"value": "--json", "description": "Emit JSON"}],
                            },
                        },
                    },
                },
                {
                    "root": "policyless",
                    "policy": {"allow": []},
                    "autocomplete": {},
                },
            ],
            "pipe_helpers": [{"root": "grep"}],
        }

        catalog = command_catalog_from_registry(registry)
        entry = command_catalog_entry("sentinel", registry=registry)
        subcommand = command_catalog_entry("sentinel", "scan", registry=registry)

        assert [item["root"] for item in catalog] == ["sentinel"]
        assert entry is not None
        assert entry["description"] == "Inspect a target."
        entry_flags = entry.get("flags")
        workspace_flags = entry.get("workspace_flags")
        assert isinstance(entry_flags, list)
        assert isinstance(entry_flags[0], dict)
        assert entry_flags[0]["value"] == "-i"
        assert isinstance(workspace_flags, list)
        assert isinstance(workspace_flags[0], dict)
        assert workspace_flags[0]["flag"] == "-i"
        assert entry["runtime_notes"] == ["Adds `--safe` automatically when needed."]
        assert subcommand is not None
        assert subcommand["subcommand"] == "scan"
        subcommand_examples = subcommand.get("examples")
        subcommand_flags = subcommand.get("flags")
        assert isinstance(subcommand_examples, list)
        assert isinstance(subcommand_examples[0], dict)
        assert subcommand_examples[0]["value"] == "sentinel scan darklab.sh"
        assert isinstance(subcommand_flags, list)
        assert isinstance(subcommand_flags[0], dict)
        assert subcommand_flags[0]["value"] == "--json"

    def test_commands_registry_local_overlay_appends_policy_and_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "commands.yaml"
            local_path = Path(tmp) / "commands.local.yaml"
            base_path.write_text(textwrap.dedent("""
            version: 1
            commands:
              - root: ping
                category: Network
                policy:
                  allow:
                    - ping
                  deny: []
                workspace_flags:
                  - flag: -iL
                    mode: read
                    value: separate
                autocomplete:
                  flags:
                    - value: -c
                      description: Count
            pipe_helpers:
              - root: grep
                autocomplete:
                  pipe:
                    enabled: true
                    description: Filter lines
            """))
            local_path.write_text(textwrap.dedent("""
            commands:
              - root: ping
                category: Network Diagnostics
                policy:
                  allow:
                    - ping -c
                  deny:
                    - ping -f
                workspace_flags:
                  - flag: -oN
                    mode: write
                    value: separate_or_attached
                autocomplete:
                  examples:
                    - value: ping -c 4 darklab.sh
                      description: Send four probes
                  subcommands:
                    stats:
                      description: Show ping stats
                      flags:
                        - value: --json
                          description: JSON output
              - root: curl
                category: Network Diagnostics
                policy:
                  allow:
                    - curl
                  deny:
                    - curl -O
                autocomplete:
                  flags:
                    - value: -I
                      description: HEAD request
            pipe_helpers:
              - root: grep
                autocomplete:
                  flags:
                    - value: -i
                      description: Ignore case
            """))
            with mock.patch("commands.COMMANDS_REGISTRY_FILE", str(base_path)):
                registry = load_commands_registry()

        by_root = {entry["root"]: entry for entry in registry["commands"]}
        assert [entry["root"] for entry in registry["commands"]] == ["ping", "curl"]
        assert by_root["ping"]["category"] == "Network Diagnostics"
        assert by_root["ping"]["policy"]["allow"] == ["ping", "ping -c"]
        assert by_root["ping"]["policy"]["deny"] == ["ping -f"]
        assert by_root["ping"]["workspace_flags"] == [
            {"flag": "-iL", "mode": "read", "value": "separate"},
            {"flag": "-oN", "mode": "write", "value": "separate_or_attached"},
        ]
        assert by_root["ping"]["autocomplete"]["flags"][0]["value"] == "-c"
        assert by_root["ping"]["autocomplete"]["examples"][0]["value"] == "ping -c 4 darklab.sh"
        assert by_root["ping"]["autocomplete"]["subcommands"]["stats"]["flags"][0]["value"] == "--json"
        assert by_root["ping"]["autocomplete"]["arg_hints"]["__positional__"][0]["value"] == "stats"
        assert by_root["curl"]["policy"]["deny"] == ["curl -O"]
        grep = registry["pipe_helpers"][0]
        assert grep["autocomplete"]["pipe_command"] is True
        assert grep["autocomplete"]["flags"][0]["value"] == "-i"

    def test_real_registry_amass_uses_subcommand_scoped_autocomplete(self):
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})
        amass = context["amass"]

        assert [item["value"] for item in amass["flags"]] == ["-h"]
        assert [item["value"] for item in amass["arg_hints"]["__positional__"]] == [
            "enum",
            "subs",
            "track",
            "viz",
        ]
        assert "-names" in {item["value"] for item in amass["subcommands"]["subs"]["flags"]}
        assert "-d3" not in {item["value"] for item in amass["subcommands"]["subs"]["flags"]}
        assert "-d3" in {item["value"] for item in amass["subcommands"]["viz"]["flags"]}
        assert "-names" not in {item["value"] for item in amass["subcommands"]["viz"]["flags"]}
        assert amass["subcommands"]["enum"]["arg_hints"]["-d"][0]["value_type"] == "domain"
        assert amass["subcommands"]["subs"]["arg_hints"]["-d"][0]["value_type"] == "domain"
        assert "amass subs -d darklab.sh -show" in {
            item["value"] for item in amass["subcommands"]["subs"]["examples"]
        }
        assert "-df" in amass["subcommands"]["enum"]["workspace_file_flags"]
        assert "-config" in amass["subcommands"]["subs"]["workspace_file_flags"]
        assert "-o" not in amass["subcommands"]["subs"].get("workspace_file_flags", [])

    def test_real_registry_openssl_uses_subcommand_scoped_autocomplete(self):
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})
        openssl = context["openssl"]

        assert [item["value"] for item in openssl["arg_hints"]["__positional__"]] == [
            "s_client",
            "ciphers",
        ]
        s_client_flags = {item["value"] for item in openssl["subcommands"]["s_client"]["flags"]}
        ciphers_flags = {item["value"] for item in openssl["subcommands"]["ciphers"]["flags"]}
        assert "-connect" in s_client_flags
        assert "-CAfile" in s_client_flags
        assert "-stdname" not in s_client_flags
        assert "-stdname" in ciphers_flags
        assert "-connect" not in ciphers_flags
        assert openssl["subcommands"]["s_client"]["workspace_file_flags"] == ["-CAfile"]

    def test_real_registry_gobuster_uses_subcommand_scoped_autocomplete(self):
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})
        gobuster = context["gobuster"]

        assert [item["value"] for item in gobuster["arg_hints"]["__positional__"]] == [
            "dir",
            "dns",
            "vhost",
            "fuzz",
            "s3",
            "gcs",
            "tftp",
        ]
        dir_flags = {item["value"] for item in gobuster["subcommands"]["dir"]["flags"]}
        dns_flags = {item["value"] for item in gobuster["subcommands"]["dns"]["flags"]}
        vhost_flags = {item["value"] for item in gobuster["subcommands"]["vhost"]["flags"]}
        assert "-x" in dir_flags
        assert "--append-domain" not in dir_flags
        assert "-r" in dns_flags
        assert "-x" not in dns_flags
        assert "--append-domain" in vhost_flags
        assert "-d" not in vhost_flags
        assert gobuster["subcommands"]["dir"]["workspace_file_flags"] == ["-w"]
        assert gobuster["subcommands"]["dir"]["arg_hints"]["-w"][0]["value_type"] == "wordlist"
        assert gobuster["subcommands"]["dir"]["arg_hints"]["-w"][0]["wordlist_category"] == "web-content"

    def test_real_registry_wordlist_metadata_covers_known_wordlist_flags(self):
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})

        assert context["dnsrecon"]["arg_hints"]["-D"][0]["wordlist_category"] == "dns"
        assert context["dnsx"]["arg_hints"]["-w"][0]["wordlist_category"] == "dns"
        assert context["fierce"]["arg_hints"]["--subdomain-file"][0]["wordlist_category"] == "dns"
        assert context["dnsenum"]["arg_hints"]["-f"][0]["wordlist_category"] == "dns"
        assert context["ffuf"]["arg_hints"]["-w"][0]["value_type"] == "wordlist"
        assert context["ffuf"]["arg_hints"]["-w"][0]["wordlist_category"] == [
            "web-content",
            "api",
            "fuzzing",
            "dns",
        ]

    def test_real_registry_restricted_input_metadata_covers_known_target_slots(self):
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})

        expectations = [
            ("curl", "__positional__", "url"),
            ("wget", "-i", "url"),
            ("subfinder", "-dL", "domain"),
            ("amass", "enum:-df", "domain"),
            ("amass", "enum:-nf", "host"),
            ("dnsx", "-l", "host"),
            ("pd-httpx", "-l", "url"),
            ("gobuster", "dir:-u", "url"),
            ("gobuster", "tftp:-s", "host"),
            ("ffuf", "-u", "url"),
            ("naabu", "-l", "host"),
            ("katana", "-list", "url"),
            ("wafw00f", "-i", "url"),
            ("masscan", "-iL", "target"),
            ("rustscan", "__positional__", "domain"),
            ("nmap", "-iL", "target"),
            ("testssl", "__positional__", "url"),
            ("wpscan", "--url", "url"),
            ("nuclei", "-l", "target"),
        ]
        for root, trigger, value_type in expectations:
            spec = context[root]
            if ":" in trigger:
                subcommand, trigger = trigger.split(":", 1)
                spec = spec["subcommands"][subcommand]
            assert spec["arg_hints"][trigger][0]["value_type"] == value_type

    def test_autocomplete_context_can_be_derived_from_commands_registry(self):
        context = autocomplete_context_from_commands_registry({
            "commands": [
                {"root": "ping", "autocomplete": {"examples": [{"value": "ping -c 4 darklab.sh"}]}},
                {"root": "empty", "autocomplete": {}},
            ],
            "pipe_helpers": [
                {"root": "grep", "autocomplete": {"pipe_command": True}},
            ],
        })
        assert list(context) == ["ping", "grep"]
        assert context["ping"]["examples"][0]["value"] == "ping -c 4 darklab.sh"
        assert context["grep"]["pipe_command"] is True

    def test_builtin_autocomplete_registry_uses_app_owned_yaml(self):
        context = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})

        assert context["commands"]["flags"][0]["value"] == "--built-in"
        assert context["commands"]["arg_hints"]["__positional__"][0]["value"] == "info"
        assert "info" in context["commands"]["expects_value"]
        assert context["runs"]["flags"][-1]["value"] == "--json"
        assert context["session-token"]["arg_hints"]["set"][0]["value"] == "<token>"
        assert [item["value"] for item in context["var"]["arg_hints"]["__positional__"]] == [
            "list",
            "set",
            "unset",
        ]
        assert context["var"]["close_after"] == {"list": 0, "set": 2, "unset": 1}

    def test_builtin_autocomplete_workspace_roots_follow_feature_flag(self):
        disabled = load_autocomplete_context_from_commands_registry({"workspace_enabled": False})
        enabled = load_autocomplete_context_from_commands_registry({"workspace_enabled": True})

        assert {"file", "cat", "ls", "rm"}.isdisjoint(disabled)
        assert {"file", "cat", "ls", "rm"}.issubset(enabled)
        assert [item["value"] for item in enabled["file"]["arg_hints"]["__positional__"]] == [
            "list <folder>",
            "ls <folder>",
            "show <file>",
            "add <file>",
            "add-dir <folder>",
            "edit <file>",
            "download <file>",
            "move <source> <destination>",
            "delete <file>",
            "help",
        ]
        assert "rm" in enabled["file"]["expects_value"]
        assert "rm" in enabled["file"]["arg_hints"]

    def test_real_registry_commands_have_root_descriptions(self):
        registry = load_commands_registry()

        missing = [
            str(item.get("root") or "<unknown>").strip()
            for item in registry.get("commands", [])
            if not str(item.get("description") or "").strip()
        ]

        assert missing == []

    def test_real_registry_workspace_file_flags_cover_supported_file_io_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": tmp,
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 40,
                "workspace_inactivity_ttl_hours": 1,
            }
            session_id = "registry-workspace-flags"
            for path, text in {
                "urls.txt": "https://ip.darklab.sh\n",
                "tls-targets.txt": "ip.darklab.sh\n",
                "subdomains.txt": "www.darklab.sh\n",
                "domains.txt": "darklab.sh\n",
                "targets.txt": "ip.darklab.sh\n",
                "excluded-hosts.txt": "skip.darklab.sh\n",
                "httpx-config.yaml": "threads: 5\n",
                "katana-config.yaml": "depth: 1\n",
                "katana-field-config.yaml": "rules: []\n",
                "nuclei-config.yaml": "rate-limit: 10\n",
                "nuclei-report-config.yaml": "markdown: {}\n",
                "nuclei-resume.cfg": "resume\n",
                "ports.txt": "80\n443\n",
                "resolvers.txt": "1.1.1.1\n",
                "request.txt": "GET / HTTP/1.1\nHost: ip.darklab.sh\n\n",
                "subfinder-config.yaml": "recursive: false\n",
                "subfinder-provider-config.yaml": "github: []\n",
                "ca.pem": "-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n",
                "nmap-script-args.txt": "http.useragent=darklab\n",
            }.items():
                write_workspace_text_file(session_id, path, text, cfg)

            cases = {
                "wget -i urls.txt -O response.html": (["urls.txt"], ["response.html"]),
                "openssl s_client -connect ip.darklab.sh:443 -CAfile ca.pem": (["ca.pem"], []),
                "sslscan --xml sslscan.xml ip.darklab.sh": ([], ["sslscan.xml"]),
                "sslyze --targets_in tls-targets.txt --json_out sslyze.json": (
                    ["tls-targets.txt"], ["sslyze.json"],
                ),
                "dnsrecon -d darklab.sh -D subdomains.txt -c dnsrecon.csv": (
                    ["subdomains.txt"], ["dnsrecon.csv"],
                ),
                "subfinder -dL domains.txt -o subfinder.txt": (["domains.txt"], ["subfinder.txt"]),
                "subfinder -dL domains.txt -oD subfinder-by-domain": (
                    ["domains.txt"], ["subfinder-by-domain"],
                ),
                "subfinder -d darklab.sh -config subfinder-config.yaml -pc subfinder-provider-config.yaml -rL resolvers.txt": (
                    ["subfinder-config.yaml", "subfinder-provider-config.yaml", "resolvers.txt"], [],
                ),
                "amass enum -df domains.txt -timeout 10": (["domains.txt"], ["amass"]),
                "amass subs -d darklab.sh -names": ([], ["amass"]),
                "amass subs -d darklab.sh -names -dir amass": ([], ["amass"]),
                "amass subs -d darklab.sh -names -o amass-subdomains.txt": (
                    [], ["amass-subdomains.txt", "amass"],
                ),
                "amass track -d darklab.sh": ([], ["amass"]),
                "amass viz -d darklab.sh -d3 -o amass-viz": ([], ["amass-viz", "amass"]),
                "dnsx -l subdomains.txt -o dnsx.txt": (["subdomains.txt"], ["dnsx.txt"]),
                "pd-httpx -rr request.txt -status-code -o httpx-raw.txt": (
                    ["request.txt"], ["httpx-raw.txt"],
                ),
                "pd-httpx -l urls.txt -status-code -sr -srd httpx-responses": (
                    ["urls.txt"], ["httpx-responses"],
                ),
                "pd-httpx -l urls.txt -screenshot -srd httpx-screenshots -config httpx-config.yaml": (
                    ["urls.txt", "httpx-config.yaml"], ["httpx-screenshots"],
                ),
                "wafw00f -i urls.txt -o wafw00f.txt": (["urls.txt"], ["wafw00f.txt"]),
                "masscan -iL targets.txt -oL masscan.txt -p 80": (["targets.txt"], ["masscan.txt"]),
                "testssl --fast --jsonfile testssl.json https://ip.darklab.sh": ([], ["testssl.json"]),
                "nikto -h ip.darklab.sh -o nikto.txt": ([], ["nikto.txt"]),
                "wpscan --url https://ip.darklab.sh -o wpscan.txt": ([], ["wpscan.txt"]),
                "naabu -host ip.darklab.sh -pf ports.txt -ef excluded-hosts.txt -o naabu-results.txt": (
                    ["ports.txt", "excluded-hosts.txt"], ["naabu-results.txt"],
                ),
                (
                    "katana -u https://ip.darklab.sh -config katana-config.yaml "
                    "-flc katana-field-config.yaml -elog katana-errors.log"
                ): (
                    ["katana-config.yaml", "katana-field-config.yaml"], ["katana-errors.log"],
                ),
                "katana -u https://ip.darklab.sh -sr -srd katana-responses": (
                    [], ["katana-responses"],
                ),
                "katana -u https://ip.darklab.sh -sf fqdn -sfd katana-fields": (
                    [], ["katana-fields"],
                ),
                "nuclei -u https://ip.darklab.sh -sresp -srd nuclei-responses": (
                    [], ["nuclei-responses"],
                ),
                "nuclei -u https://ip.darklab.sh -me nuclei-markdown": (
                    [], ["nuclei-markdown"],
                ),
                (
                    "nuclei -u https://ip.darklab.sh -je nuclei-results.json "
                    "-jle nuclei-results.jsonl -se nuclei-results.sarif"
                ): (
                    [], ["nuclei-results.json", "nuclei-results.jsonl", "nuclei-results.sarif"],
                ),
                (
                    "nuclei -u https://ip.darklab.sh -tlog nuclei-trace.log "
                    "-elog nuclei-errors.log -config nuclei-config.yaml "
                    "-rc nuclei-report-config.yaml -resume nuclei-resume.cfg"
                ): (
                    ["nuclei-config.yaml", "nuclei-report-config.yaml", "nuclei-resume.cfg"],
                    ["nuclei-trace.log", "nuclei-errors.log"],
                ),
                "nmap --script http-headers --script-args-file nmap-script-args.txt ip.darklab.sh": (
                    ["nmap-script-args.txt"], [],
                ),
            }

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
                for command, (reads, writes) in cases.items():
                    result = commands.validate_command(command, session_id=session_id, cfg=cfg)
                    assert result.allowed, f"{command!r} should be workspace-allowed: {result.reason}"
                    assert result.workspace_reads == reads
                    assert result.workspace_writes == writes
                    exec_tokens = commands.split_command_argv(result.exec_command)
                    if command.startswith("amass "):
                        assert exec_tokens[0] == "env"
                        assert exec_tokens[1].startswith("XDG_CONFIG_HOME=")
                        assert exec_tokens[2] == "amass"
                        assert "-dir" in exec_tokens
                    for original in reads + writes:
                        if command.startswith("amass ") and original == commands.AMASS_DEFAULT_WORKSPACE_DIR:
                            continue
                        assert original not in exec_tokens

                result = commands.validate_command(
                    "amass subs -d darklab.sh -names -dir custom-amass-db",
                    session_id=session_id,
                    cfg=cfg,
                )
                assert not result.allowed
                assert "managed amass session directory" in result.reason

                result = commands.validate_command(
                    "amass enum -d darklab.sh -o unmanaged.txt",
                    session_id=session_id,
                    cfg=cfg,
                )
                assert not result.allowed
                assert "Command not allowed" in result.reason

    def test_workspace_rewrites_quote_shell_sensitive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "work space;$(subshell)&`tick`"
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": str(workspace_root),
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }
            session_id = "quote-sensitive-paths"
            write_workspace_text_file(session_id, "targets & dollars $.txt", "ip.darklab.sh\n", cfg)

            with _patched_command_validation_helpers():
                result = commands.validate_command(
                    "masscan -iL 'targets & dollars $.txt' -oL 'masscan output $.txt' -p 80",
                    session_id=session_id,
                    cfg=cfg,
                )

            assert result.allowed, result.reason
            assert result.workspace_reads == ["targets & dollars $.txt"]
            assert result.workspace_writes == ["masscan output $.txt"]
            assert ";$(subshell)&`tick`" in result.exec_command
            expected_output_path = resolve_workspace_path(session_id, "masscan output $.txt", cfg)
            assert shlex.quote(str(expected_output_path)) in result.exec_command
            assert commands.split_command_argv(result.exec_command) == [
                "masscan",
                "-iL",
                str(resolve_workspace_path(session_id, "targets & dollars $.txt", cfg)),
                "-oL",
                str(expected_output_path),
                "-p",
                "80",
            ]

    def test_amass_runtime_environment_quotes_rewritten_workspace_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "amass root;$(subshell)&`tick`"
            cfg = {
                "workspace_enabled": True,
                "workspace_backend": "tmpfs",
                "workspace_root": str(workspace_root),
                "workspace_quota_mb": 1,
                "workspace_max_file_mb": 1,
                "workspace_max_files": 10,
                "workspace_inactivity_ttl_hours": 1,
            }

            with _patched_command_validation_helpers():
                result = commands.validate_command(
                    "amass subs -d darklab.sh -names",
                    session_id="amass-quote-sensitive-paths",
                    cfg=cfg,
                )

            assert result.allowed, result.reason
            assert result.exec_command.startswith("env ")
            assert ";$(subshell)&`tick`" in result.exec_command
            tokens = commands.split_command_argv(result.exec_command)
            amass_dir = resolve_workspace_path("amass-quote-sensitive-paths", "amass", cfg, ensure_parent=True)
            assert tokens[:3] == [
                "env",
                f"XDG_CONFIG_HOME={amass_dir.parent}",
                "amass",
            ]
            assert tokens[-2:] == ["-dir", str(amass_dir)]

    def test_autocomplete_context_filters_workspace_feature_hints(self):
        registry = {
            "commands": [
                {
                    "root": "nmap",
                    "autocomplete": {
                        "examples": [
                            {"value": "nmap ip.darklab.sh", "description": "Scan host"},
                            {
                                "value": "nmap -iL targets.txt -oN nmap.txt",
                                "description": "Scan file targets",
                                "feature_required": "workspace",
                            },
                        ],
                        "flags": [
                            {"value": "-sV", "description": "Service detection"},
                            {
                                "value": "-iL",
                                "description": "Read session file",
                                "feature_required": "workspace",
                            },
                        ],
                        "expects_value": ["-iL"],
                        "arg_hints": {
                            "-iL": [{"value": "targets.txt", "description": "Targets file"}],
                        },
                        "subcommands": {
                            "subs": {
                                "flags": [
                                    {"value": "-names", "description": "Print names"},
                                    {
                                        "value": "-o",
                                        "description": "Write session file",
                                        "feature_required": "workspace",
                                    },
                                ],
                                "expects_value": ["-o"],
                                "arg_hints": {
                                    "-o": [{"value": "subs.txt", "description": "Output file"}],
                                },
                                "examples": [
                                    {"value": "nmap subs -names"},
                                    {
                                        "value": "nmap subs -o subs.txt",
                                        "feature_required": "workspace",
                                    },
                                ],
                            },
                        },
                    },
                },
            ],
        }

        disabled = autocomplete_context_from_commands_registry(registry, cfg={"workspace_enabled": False})
        enabled = autocomplete_context_from_commands_registry(registry, cfg={"workspace_enabled": True})

        assert [item["value"] for item in disabled["nmap"]["examples"]] == ["nmap ip.darklab.sh"]
        assert [item["value"] for item in disabled["nmap"]["flags"]] == ["-sV"]
        assert "-iL" not in disabled["nmap"]["expects_value"]
        assert "-iL" not in disabled["nmap"]["arg_hints"]
        assert [item["value"] for item in disabled["nmap"]["subcommands"]["subs"]["flags"]] == ["-names"]
        assert "-o" not in disabled["nmap"]["subcommands"]["subs"]["expects_value"]
        assert "-o" not in disabled["nmap"]["subcommands"]["subs"]["arg_hints"]
        assert [item["value"] for item in disabled["nmap"]["subcommands"]["subs"]["examples"]] == ["nmap subs -names"]
        assert [item["value"] for item in enabled["nmap"]["examples"]] == [
            "nmap ip.darklab.sh",
            "nmap -iL targets.txt -oN nmap.txt",
        ]
        assert [item["value"] for item in enabled["nmap"]["flags"]] == ["-sV", "-iL"]
        assert enabled["nmap"]["arg_hints"]["-iL"][0]["value"] == "targets.txt"
        assert [item["value"] for item in enabled["nmap"]["subcommands"]["subs"]["flags"]] == ["-names", "-o"]
        assert enabled["nmap"]["subcommands"]["subs"]["arg_hints"]["-o"][0]["value"] == "subs.txt"

    def test_command_policy_can_be_derived_from_commands_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commands.yaml"
            path.write_text(
                textwrap.dedent(
                    """
                    version: 1
                    commands:
                    - root: curl
                      policy:
                        allow:
                        - curl
                        deny:
                        - curl -K
                    - root: nmap
                      policy:
                        allow:
                        - nmap
                        deny:
                        - nmap -sU
                    """
                )
            )

            with mock.patch("commands.COMMANDS_REGISTRY_FILE", str(path)):
                allow, deny = load_command_policy()

        assert allow == ["curl", "nmap"]
        assert deny == ["curl -K", "nmap -sU"]

    def test_allow_grouping_flags_can_be_derived_from_commands_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commands.yaml"
            path.write_text(
                textwrap.dedent(
                    """
                    version: 1
                    commands:
                    - root: nc
                      policy:
                        allow:
                        - nc -z
                        deny: []
                      autocomplete:
                        flags:
                        - value: -z
                          allow_grouping: true
                        - value: -v
                          allow_grouping: true
                        - value: -n
                          allow_grouping: true
                        - value: -w
                          allow_grouping: true
                          takes_value: true
                        - value: --help
                          allow_grouping: true
                    """
                )
            )

            with mock.patch("commands.COMMANDS_REGISTRY_FILE", str(path)):
                grouped = load_allow_grouping_flags()

        assert grouped == {"nc": {"-z", "-v", "-n"}}

    def test_allow_grouping_flags_match_short_flag_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "commands.yaml"
            path.write_text(
                textwrap.dedent(
                    """
                    version: 1
                    commands:
                    - root: nc
                      policy:
                        allow:
                        - nc -z
                        deny:
                        - nc -e
                      autocomplete:
                        flags:
                        - value: -z
                          allow_grouping: true
                        - value: -v
                          allow_grouping: true
                        - value: -n
                          allow_grouping: true
                    - root: nmap
                      policy:
                        allow:
                        - nmap -sV
                        deny: []
                      autocomplete:
                        flags:
                        - value: -sV
                          description: Service detection
                    """
                )
            )

            with mock.patch("commands.COMMANDS_REGISTRY_FILE", str(path)):
                assert is_command_allowed("nc -zv darklab.sh 80")[0]
                assert is_command_allowed("nc -vz darklab.sh 80")[0]
                assert is_command_allowed("nc -n -v -z darklab.sh 80")[0]
                assert is_command_allowed("nc -w 3 -z darklab.sh 80")[0]
                assert is_command_allowed("nc -w 3 -vz darklab.sh 80")[0]
                assert not is_command_allowed("nc -nv darklab.sh 80")[0]
                assert not is_command_allowed("nc -zve darklab.sh 80")[0]
                assert not is_command_allowed("nc -w 3 -e /bin/sh -z darklab.sh 80")[0]
                assert is_command_allowed("nmap -sV darklab.sh")[0]
                assert not is_command_allowed("nmap -Vs darklab.sh")[0]


# ── load_faq ──────────────────────────────────────────────────────────────────

class TestLoadFaq:
    def test_missing_file_returns_empty_list(self):
        with mock.patch("commands.FAQ_FILE", "/nonexistent/faq.yaml"):
            result = load_faq()
        assert result == []

    def test_valid_entries_returned(self):
        yaml_content = "- question: What is this?\n  answer: A web shell.\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq()
        finally:
            os.unlink(path)
        assert len(result) == 1
        assert result[0]["question"] == "What is this?"
        assert result[0]["answer"] == "A web shell."

    def test_markdown_style_markup_renders_to_answer_html(self):
        yaml_content = textwrap.dedent(
            """
            - question: Styled entry?
              answer: |
                Use **bold**, *italic*, __underline__, `code`, and [[cmd:ping -c 1 127.0.0.1|ping chip]].

                - first item
                - second item
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq()
        finally:
            os.unlink(path)
        assert len(result) == 1
        html = result[0]["answer_html"]
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html
        assert "<u>underline</u>" in html
        assert "<code>code</code>" in html
        assert 'data-faq-command="ping -c 1 127.0.0.1"' in html
        assert '<ul>' in html and '<li>first item</li>' in html

    def test_entries_missing_answer_filtered_out(self):
        yaml_content = "- question: No answer here.\n- question: Has both.\n  answer: Yes.\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq()
        finally:
            os.unlink(path)
        assert len(result) == 1
        assert result[0]["question"] == "Has both."

    def test_local_overlay_appends_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "faq.yaml")
            local_path = os.path.join(tmp, "faq.local.yaml")
            with open(base_path, "w") as f:
                f.write("- question: Base?\n  answer: Base answer.\n")
            with open(local_path, "w") as f:
                f.write("- question: Local?\n  answer: Local answer.\n")
            with mock.patch("commands.FAQ_FILE", base_path):
                result = load_faq()
        assert [item["question"] for item in result] == ["Base?", "Local?"]

    def test_workspace_feature_entry_hidden_when_workspace_disabled(self):
        yaml_content = textwrap.dedent(
            """
            - question: Always?
              answer: Always answer.
            - question: Files?
              feature: workspace
              answer: Files answer.
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq({"workspace_enabled": False})
        finally:
            os.unlink(path)

        assert [item["question"] for item in result] == ["Always?"]

    def test_workspace_feature_entry_visible_when_workspace_enabled(self):
        yaml_content = textwrap.dedent(
            """
            - question: Always?
              answer: Always answer.
            - question: Files?
              feature: workspace
              answer: Files answer.
            """
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq({"workspace_enabled": True})
        finally:
            os.unlink(path)

        assert [item["question"] for item in result] == ["Always?", "Files?"]


# ── load_theme_registry / load_theme ─────────────────────────────────────────

class TestThemeRegistry:
    _THEME_METADATA_KEYS = {"label", "group", "sort"}
    _RETIRED_THEME_KEYS = {
        "chip_bg",
        "chip_border",
        "chip_text",
        "confirm_modal_bg",
        "dropdown_up_bg",
        "dropdown_up_border",
        "dropdown_up_shadow",
        "form_control_bg",
        "history_load_modal_bg",
        "history_load_modal_border",
        "history_load_modal_shadow",
        "history_panel_shadow",
        "mobile_composer_host_bg",
        "mobile_composer_host_light_bg",
        "mobile_menu_shadow",
        "modal_header_bg",
        "modal_section_bg",
        "panel_alt_bg",
        "tab_active_border",
        "tab_active_shadow",
        "tab_active_text",
        "tab_bg",
        "tab_border",
        "tab_status_ok_bg",
        "tabs_bar_scrollbar_thumb",
        "tabs_bar_scrollbar_thumb_hover",
        "tabs_bar_scrollbar_track",
        "tabs_scroll_btn_bg",
        "tabs_scroll_btn_border",
        "tabs_scroll_btn_text",
        "terminal_actions_bg",
        "terminal_bar_border",
        "window_btn_bg",
        "window_btn_border",
        "window_btn_text",
    }

    def _write_theme(self, root, name, content):
        theme_dir = root / "themes"
        theme_dir.mkdir(parents=True, exist_ok=True)
        path = theme_dir / f"{name}.yaml"
        path.write_text(textwrap.dedent(content))
        return theme_dir, path

    def _shipped_theme_files(self):
        return sorted((REPO_ROOT / "app" / "conf" / "themes").glob("*.yaml"))

    def _load_shipped_theme_yaml(self, path):
        data = yaml.safe_load(path.read_text()) or {}
        assert isinstance(data, dict), f"{path.name} must be a YAML mapping"
        return data

    def test_missing_label_falls_back_to_humanized_filename(self, tmp_path, monkeypatch):
        theme_dir, _ = self._write_theme(
            tmp_path,
            "custom_simple_theme",
            """
            bg: "#123456"
            surface: "#234567"
            """,
        )
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        themes = app_config.load_theme_registry()
        assert len(themes) == 1
        entry = themes[0]
        assert entry["name"] == "custom_simple_theme"
        assert entry["filename"] == "custom_simple_theme.yaml"
        assert entry["label"] == "Custom Simple Theme"

    def test_unknown_keys_are_ignored_but_valid_css_values_survive(self, tmp_path, monkeypatch):
        theme_dir, _ = self._write_theme(
            tmp_path,
            "custom_theme",
            """
            label: "Custom Theme"
            bg: "not-a-real-color"
            surface: "linear-gradient(180deg, #111, #222)"
            extra_key: "should be ignored"
            """,
        )
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        theme = app_config.load_theme("custom_theme")
        assert theme["bg"] == "not-a-real-color"
        assert theme["surface"] == "linear-gradient(180deg, #111, #222)"
        assert "extra_key" not in theme

    def test_malformed_yaml_falls_back_to_defaults_without_crashing(self, tmp_path, monkeypatch):
        theme_dir = tmp_path / "themes"
        theme_dir.mkdir(parents=True, exist_ok=True)
        (theme_dir / "broken_theme.yaml").write_text(
            "label: Broken Theme\nbg: [\n"
        )
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        themes = app_config.load_theme_registry()
        themes_map = {theme["name"]: theme for theme in themes}
        assert "broken_theme" in themes_map
        assert themes_map["broken_theme"]["label"] == "Broken Theme"
        assert app_config.load_theme("broken_theme")["bg"] == app_config._THEME_DEFAULTS["dark"]["bg"]

    def test_single_theme_registry_loads_and_can_be_selected(self, tmp_path, monkeypatch):
        theme_dir, _ = self._write_theme(
            tmp_path,
            "only_theme",
            """
            label: "Only Theme"
            bg: "#101010"
            surface: "#1a1a1a"
            """,
        )
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        themes = app_config.load_theme_registry()
        assert len(themes) == 1
        assert themes[0]["name"] == "only_theme"
        assert themes[0]["label"] == "Only Theme"
        assert app_config.load_theme("only_theme")["bg"] == "#101010"
        assert themes[0]["color_scheme"] == "only dark"

    def test_local_theme_overlay_updates_base_theme_and_is_not_listed_separately(self, tmp_path, monkeypatch):
        theme_dir, _ = self._write_theme(
            tmp_path,
            "base_theme",
            """
            label: "Base Theme"
            bg: "#101010"
            surface: "#1a1a1a"
            """,
        )
        (theme_dir / "base_theme.local.yaml").write_text(textwrap.dedent(
            """
            label: "Base Theme Local"
            bg: "#202020"
            """
        ))
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        themes = app_config.load_theme_registry()
        assert [theme["name"] for theme in themes] == ["base_theme"]
        assert themes[0]["label"] == "Base Theme Local"
        assert app_config.load_theme("base_theme")["bg"] == "#202020"
        assert app_config.load_theme("base_theme")["surface"] == "#1a1a1a"

    def test_light_theme_uses_light_defaults_for_missing_keys(self, tmp_path, monkeypatch):
        theme_dir, _ = self._write_theme(
            tmp_path,
            "light_theme",
            """
            label: "Light Theme"
            color_scheme: light
            bg: "#eef4fa"
            """,
        )
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        theme = app_config.load_theme("light_theme")
        assert theme["bg"] == "#eef4fa"
        assert theme["terminal_bar_bg"] == app_config._THEME_DEFAULTS["light"]["terminal_bar_bg"]
        assert theme["toolbar_button_text"] == app_config._THEME_DEFAULTS["light"]["toolbar_button_text"]

    def test_missing_color_scheme_still_falls_back_to_dark_defaults(self, tmp_path, monkeypatch):
        theme_dir, _ = self._write_theme(
            tmp_path,
            "implicit_dark_theme",
            """
            label: "Implicit Dark"
            bg: "#101010"
            """,
        )
        monkeypatch.setattr(app_config, "_THEME_VARIANT_DIR", theme_dir)

        theme = app_config.load_theme("implicit_dark_theme")
        assert theme["bg"] == "#101010"
        assert theme["terminal_bar_bg"] == app_config._THEME_DEFAULTS["dark"]["terminal_bar_bg"]
        assert theme["toolbar_button_text"] == app_config._THEME_DEFAULTS["dark"]["toolbar_button_text"]

    def test_theme_example_files_match_generated_defaults(self):
        script_path = REPO_ROOT / "scripts" / "generate_theme_examples.py"
        spec = importlib.util.spec_from_file_location("generate_theme_examples", script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        dark_expected = module.generate_theme_example_text("dark")
        light_expected = module.generate_theme_example_text("light")
        dark_actual = (REPO_ROOT / "app" / "conf" / "theme_dark.yaml.example").read_text()
        light_actual = (REPO_ROOT / "app" / "conf" / "theme_light.yaml.example").read_text()

        assert dark_actual == dark_expected, "theme_dark.yaml.example is out of sync; run ./scripts/generate_theme_examples.py"
        assert light_actual == light_expected, "theme_light.yaml.example is out of sync; run ./scripts/generate_theme_examples.py"

    def test_shipped_theme_files_have_complete_matching_key_sets(self):
        required_keys = set(app_config._THEME_DEFAULTS["dark"]) | {"color_scheme"}
        issues = []
        for theme_path in self._shipped_theme_files():
            data = self._load_shipped_theme_yaml(theme_path)
            keys = set(data) - self._THEME_METADATA_KEYS
            missing = sorted(required_keys - keys)
            extra = sorted(keys - required_keys)
            if missing:
                issues.append(f"{theme_path.name} missing keys: {', '.join(missing)}")
            if extra:
                issues.append(f"{theme_path.name} has unknown keys: {', '.join(extra)}")

        assert not issues, "Shipped theme YAML key drift:\n" + "\n".join(issues)

    def test_shipped_themes_do_not_reintroduce_retired_keys(self):
        issues = []
        for theme_path in self._shipped_theme_files():
            data = self._load_shipped_theme_yaml(theme_path)
            retired = sorted(set(data) & self._RETIRED_THEME_KEYS)
            if retired:
                issues.append(f"{theme_path.name}: {', '.join(retired)}")

        assert not issues, "Retired theme keys were reintroduced:\n" + "\n".join(issues)

    def test_theme_key_reference_matches_runtime_order_and_defaults(self):
        theme_doc = (REPO_ROOT / "THEME.md").read_text()
        row_re = re.compile(r"^\| `([^`]+)` \| `([^`]*)` \| `([^`]*)` \| ", re.MULTILINE)
        rows = row_re.findall(theme_doc.split("## Theme Key Reference", 1)[1])
        documented_keys = [key for key, _, _ in rows]
        expected_keys = list(app_config._THEME_CSS_ORDER)

        assert documented_keys == expected_keys, (
            "THEME.md Theme Key Reference drifted from _THEME_CSS_ORDER"
        )

        default_issues = []
        for key, dark_value, light_value in rows:
            expected_dark = str(app_config._THEME_DEFAULTS["dark"][key])
            expected_light = str(app_config._THEME_DEFAULTS["light"][key])
            if dark_value != expected_dark:
                default_issues.append(f"{key}: dark doc={dark_value!r}, expected={expected_dark!r}")
            if light_value != expected_light:
                default_issues.append(f"{key}: light doc={light_value!r}, expected={expected_light!r}")

        assert not default_issues, (
            "THEME.md Theme Key Reference default values drifted:\n"
            + "\n".join(default_issues)
        )

    def test_css_theme_var_references_are_defined_or_explicitly_fallbacked(self):
        known_theme_vars = {
            f"--theme-{key.replace('_', '-')}" for key in app_config._THEME_CSS_ORDER
        }
        var_call_re = re.compile(r"var\((--theme-[\w-]+)([^)]*)\)")
        issues = []

        for css_path in sorted((REPO_ROOT / "app" / "static" / "css").glob("*.css")):
            for line_no, line in enumerate(css_path.read_text().splitlines(), start=1):
                for match in var_call_re.finditer(line):
                    var_name = match.group(1)
                    if var_name in known_theme_vars:
                        continue
                    if "," in match.group(2):
                        continue
                    issues.append(f"{css_path.relative_to(REPO_ROOT)}:{line_no} uses undefined {var_name}")

        assert not issues, "CSS references undefined theme vars without fallbacks:\n" + "\n".join(issues)

    def test_css_color_literals_are_theme_vars_or_var_derived(self):
        color_re = re.compile(r"(#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\bcolor-mix\()")
        issues = []

        for css_path in sorted((REPO_ROOT / "app" / "static" / "css").glob("*.css")):
            for line_no, line in enumerate(css_path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if not color_re.search(stripped):
                    continue
                if stripped.startswith("--"):
                    continue
                if "var(--" in stripped:
                    continue
                issues.append(f"{css_path.relative_to(REPO_ROOT)}:{line_no}: {stripped}")

        assert not issues, (
            "CSS color literals outside token definitions must be var-derived or moved into theme vars:\n"
            + "\n".join(issues)
        )

    def test_darklab_obsidian_matches_dark_defaults_and_example(self):
        dark_example = yaml.safe_load((REPO_ROOT / "app" / "conf" / "theme_dark.yaml.example").read_text()) or {}
        darklab_obsidian = yaml.safe_load(
            (REPO_ROOT / "app" / "conf" / "themes" / "darklab_obsidian.yaml").read_text()
        ) or {}

        metadata_keys = {"label", "group", "sort"}
        darklab_values = {key: value for key, value in darklab_obsidian.items() if key not in metadata_keys}
        dark_defaults = {"color_scheme": "dark", **app_config._THEME_DEFAULTS["dark"]}

        assert darklab_values == dark_defaults, "darklab_obsidian.yaml drifted from the app's default dark theme"
        assert darklab_values == dark_example, "darklab_obsidian.yaml drifted from theme_dark.yaml.example"

    def test_entries_missing_question_filtered_out(self):
        yaml_content = "- answer: No question here.\n- question: Has one.\n  answer: Yes.\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq()
        finally:
            os.unlink(path)
        assert len(result) == 1
        assert result[0]["question"] == "Has one."

    def test_non_list_yaml_returns_empty(self):
        yaml_content = "key: value\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq()
        finally:
            os.unlink(path)
        assert result == []

    def test_theme_color_scheme_marks_light_backgrounds_as_only_light(self):
        assert app_config.theme_color_scheme({"bg": "#eef4fa"}) == "only light"

    def test_theme_color_scheme_marks_dark_backgrounds_as_only_dark(self):
        assert app_config.theme_color_scheme({"bg": "#0d0d0d"}) == "only dark"

    def test_theme_color_scheme_falls_back_when_color_is_not_parseable(self):
        assert app_config.theme_color_scheme({"bg": "linear-gradient(180deg, #111, #222)"}) == "light dark"

    def test_empty_yaml_returns_empty(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_faq()
        finally:
            os.unlink(path)
        assert result == []

    def test_load_all_faq_appends_custom_entries_after_builtin_items(self):
        yaml_content = "- question: Custom question?\n  answer: Custom answer.\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq("darklab_shell", "https://example.invalid/README.md")
        finally:
            os.unlink(path)
        assert result[0]["question"] == "What is this?"
        assert result[-1]["question"] == "Custom question?"
        assert result[-1]["answer"] == "Custom answer."

    def test_load_all_faq_uses_project_readme_in_builtin_answer(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq("darklab_shell", "https://example.invalid/README.md")
        finally:
            os.unlink(path)
        assert "https://example.invalid/README.md" in result[0]["answer"]
        assert "https://example.invalid/README.md" in result[0]["answer_html"]

    def test_load_all_faq_uses_config_project_readme_by_default(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path), mock.patch(
                "config.PROJECT_README",
                "https://example.invalid/config-readme",
            ):
                result = load_all_faq("darklab_shell")
        finally:
            os.unlink(path)
        assert "https://example.invalid/config-readme" in result[0]["answer"]
        assert "https://example.invalid/config-readme" in result[0]["answer_html"]

    def test_load_all_faq_promotes_workspace_builtin_entry_when_enabled(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq(
                    "darklab_shell",
                    "https://example.invalid/README.md",
                    {"workspace_enabled": True},
                )
        finally:
            os.unlink(path)
        questions = [item["question"] for item in result]
        assert questions.index("What are session Files?") == 2
        assert questions.index("What are session Files?") < questions.index("How do I save or share my results?")

    def test_load_all_faq_hides_workspace_builtin_entry_when_disabled(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq(
                    "darklab_shell",
                    "https://example.invalid/README.md",
                    {"workspace_enabled": False},
                )
        finally:
            os.unlink(path)
        questions = [item["question"] for item in result]
        assert "What are session Files?" not in questions

    def test_load_all_faq_clarifies_snapshot_vs_run_permalink(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq("darklab_shell", "https://example.invalid/README.md")
        finally:
            os.unlink(path)
        by_question = {item["question"]: item for item in result}
        share_html = by_question["How do I save or share my results?"]["answer_html"]
        tabs_html = by_question["How do tabs and permalinks work?"]["answer_html"]
        shortcuts_html = by_question["Are there keyboard shortcuts?"]["answer_html"]
        assert "share snapshot" in share_html
        assert "run permalink" in share_html
        assert "/share" in share_html
        assert "/history/&lt;run_id&gt;" in share_html
        assert "share snapshot" in tabs_html
        assert "run permalink" in tabs_html
        # Shortcuts answer is now a pointer to the `?` overlay and the `shortcuts`
        # built-in command (single source of truth, no duplicated shortcut list).
        assert "<code>?</code>" in shortcuts_html
        assert "<code>shortcuts</code>" in shortcuts_html

    def test_load_all_faq_describes_built_in_shell_features(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq("darklab_shell", "https://example.invalid/README.md")
        finally:
            os.unlink(path)
        by_question = {item["question"]: item for item in result}
        built_in_html = by_question["What built-in shell features are supported?"]["answer_html"]
        assert "Built-in commands" in built_in_html
        assert "commands --built-in</code>" in built_in_html
        assert "history</code>" in built_in_html
        assert "command | grep pattern" in built_in_html
        assert "command | head -n 20" in built_in_html
        assert "command | head -20" in built_in_html
        assert "command | tail -n 20" in built_in_html
        assert "command | tail -20" in built_in_html
        assert "command | wc -l" in built_in_html
        assert "command | sort -rn" in built_in_html
        assert "command | uniq -c" in built_in_html
        assert "command | grep pattern | wc -l" in built_in_html
        assert "General shell piping, arbitrary chaining, and redirection are still blocked." in built_in_html


# ── Path blocking edge cases ──────────────────────────────────────────────────

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


@contextmanager
def _patched_command_validation_helpers():
    helpers = _command_validation_helpers()
    with mock.patch("commands.load_allow_grouping_flags", return_value=helpers["allow_grouping"]), \
         mock.patch("commands._workspace_flag_specs_by_root", return_value=helpers["workspace_flags"]), \
         mock.patch("commands._runtime_adaptations_by_root", return_value=helpers["runtime_adaptations"]):
        yield


def _check(cmd, allow=None, deny=None):
    a = allow if allow is not None else ["curl", "nmap", "ls"]
    d = deny if deny is not None else []
    with mock.patch("commands.load_command_policy", return_value=(a, d)), \
         _patched_command_validation_helpers():
        return is_command_allowed(cmd)


class TestPathBlockingEdgeCases:
    def test_tmp_at_end_of_command(self):
        ok, _ = _check("ls /tmp")
        assert not ok

    def test_tmp_with_subdirectory(self):
        ok, _ = _check("curl /tmp/secret.txt")
        assert not ok

    def test_tmp_in_url_path_allowed(self):
        ok, _ = _check("curl https://darklab.sh/tmp/file")
        assert ok

    def test_tmp_in_url_with_port_allowed(self):
        ok, _ = _check("curl https://darklab.sh:8080/tmp/resource")
        assert ok

    def test_data_path_blocked(self):
        ok, _ = _check("curl /data/history.db")
        assert not ok

    def test_data_in_url_path_allowed(self):
        ok, _ = _check("curl https://darklab.sh/data/file")
        assert ok

    def test_tmp_as_scheme_relative_blocked(self):
        # Ensure /tmp/... with no scheme is blocked regardless of position
        ok, _ = _check("nmap -sV /tmp/targets.txt")
        assert not ok


# ── _is_denied: multi-word tool prefix ───────────────────────────────────────

class TestIsDeniedMultiWordTool:
    def test_subcommand_specific_deny(self):
        # "gobuster dir -o" deny should NOT fire for "gobuster dns ..."
        ok, _ = _check("gobuster dns -d darklab.sh", allow=["gobuster"], deny=["gobuster dir -o"])
        assert ok

    def test_subcommand_specific_deny_fires_for_correct_subcommand(self):
        ok, _ = _check("gobuster dir -w wordlist.txt -o /tmp/out", allow=["gobuster"], deny=["gobuster dir -o"])
        assert not ok

    def test_deny_tool_only_no_flag(self):
        # A deny entry with no flag (just the tool name) should block that exact tool
        ok, _ = _check("nc 10.0.0.1 4444", allow=["nc"], deny=["nc"])
        assert not ok

    def test_deny_tool_only_does_not_block_other_tool(self):
        ok, _ = _check("nmap -sV 10.0.0.1", allow=["nmap"], deny=["nc"])
        assert ok

    def test_mtr_interactive_is_reserved_for_pty_route(self):
        ok, reason = _check("mtr --interactive darklab.sh", allow=["mtr"], deny=["mtr --interactive"])
        assert not ok
        assert "Command not allowed" in reason

    def test_ffuf_interactive_is_reserved_for_pty_route(self):
        ok, reason = _check(
            "ffuf --interactive -u https://x/FUZZ -w /list.txt",
            allow=["ffuf"],
            deny=["ffuf --interactive"],
        )
        assert not ok
        assert "Command not allowed" in reason

    def test_masscan_interactive_is_reserved_for_pty_route(self):
        ok, reason = _check(
            "masscan --interactive -p 80 1.2.3.0/24",
            allow=["masscan"],
            deny=["masscan --interactive"],
        )
        assert not ok
        assert "Command not allowed" in reason


# ── rewrite_command: case insensitivity ──────────────────────────────────────

class TestRewriteCaseInsensitive:
    def test_mtr_uppercase(self):
        cmd, notice = rewrite_command("MTR google.com")
        assert "--report-wide" in cmd
        assert notice is not None

    def test_nmap_uppercase(self):
        cmd, _ = rewrite_command("NMAP -sV 10.0.0.1")
        assert "-sT" in cmd
        assert "--privileged" not in cmd

    def test_nuclei_uppercase(self):
        cmd, _ = rewrite_command("NUCLEI -u https://darklab.sh")
        assert "-ud /tmp/nuclei-templates" in cmd


# ── run broker event storage ─────────────────────────────────────────────────

class TestRunBrokerMemoryStore:
    def test_memory_store_replays_events_after_saved_event_id(self):
        store = run_broker._MemoryRunBrokerStore()

        first = store.publish("run-1", "started", {"run_id": "run-1"})
        second = store.publish("run-1", "output", {"text": "hello"})
        third = store.publish("run-1", "exit", {"code": 0})

        all_events = store.events_after("run-1", after_id="0-0", limit=10)
        replayed = store.events_after("run-1", after_id=first.event_id, limit=10)

        assert [event.event_id for event in all_events] == [
            first.event_id,
            second.event_id,
            third.event_id,
        ]
        assert [event.event_id for event in replayed] == [second.event_id, third.event_id]
        assert replayed[0].payload["type"] == "output"
        assert replayed[0].payload["text"] == "hello"

    def test_memory_store_marks_trimmed_replay_with_notice(self):
        store = run_broker._MemoryRunBrokerStore()
        with mock.patch.dict(run_broker.CFG, {"run_broker_max_replay_bytes": 160}):
            store.publish("run-1", "output", {"text": "first-" + ("x" * 120)})
            store.publish("run-1", "output", {"text": "second-" + ("y" * 120)})
            events = store.events_after("run-1", after_id="0-0", limit=10)

        assert events[0].payload["type"] == "notice"
        assert events[0].payload["text"] == run_broker.REPLAY_TRIM_NOTICE
        assert all("first-" not in str(event.payload.get("text", "")) for event in events)
        assert any("second-" in str(event.payload.get("text", "")) for event in events)

    def test_memory_store_uses_max_output_lines_as_replay_event_bound(self):
        store = run_broker._MemoryRunBrokerStore()
        with mock.patch.dict(run_broker.CFG, {"max_output_lines": 2, "run_broker_max_replay_bytes": 0}):
            store.publish("run-1", "started", {"run_id": "run-1"})
            store.publish("run-1", "output", {"text": "line 1"})
            store.publish("run-1", "output", {"text": "line 2"})
            store.publish("run-1", "output", {"text": "line 3"})
            events = store.events_after("run-1", after_id="0-0", limit=10)

        visible_text = [str(event.payload.get("text", "")) for event in events]
        assert events[0].payload["type"] == "notice"
        assert events[0].payload["text"] == run_broker.REPLAY_TRIM_NOTICE
        assert "line 1" not in visible_text
        assert "line 2" in visible_text
        assert "line 3" in visible_text

    def test_trim_notice_sse_does_not_advance_resume_cursor(self):
        notice = run_broker._make_trim_notice_event()
        sse = notice.as_sse()

        assert "id:" not in sse
        assert "event_id" not in sse
        assert run_broker.REPLAY_TRIM_NOTICE in sse
        assert "event_id" not in notice.as_payload()

    def test_memory_store_does_not_replay_trim_notice_after_real_cursor(self):
        store = run_broker._MemoryRunBrokerStore()
        with mock.patch.dict(run_broker.CFG, {"run_broker_max_replay_bytes": 160}):
            store.publish("run-1", "output", {"text": "first-" + ("x" * 120)})
            tail = store.publish("run-1", "output", {"text": "second-" + ("y" * 120)})

        assert store.events_after("run-1", after_id=tail.event_id, limit=10) == []

    def test_bounded_replay_keeps_latest_output_and_terminal_event(self):
        events = [
            run_broker.BrokerEvent("1-0", {"type": "started"}),
            run_broker.BrokerEvent("2-0", {"type": "output", "text": "line 1"}),
            run_broker.BrokerEvent("3-0", {"type": "heartbeat"}),
            run_broker.BrokerEvent("4-0", {"type": "output", "text": "line 2"}),
            run_broker.BrokerEvent("5-0", {"type": "output", "text": "line 3"}),
            run_broker.BrokerEvent("6-0", {"type": "exit", "code": 0}),
        ]

        with mock.patch.dict(run_broker.CFG, {"max_output_lines": 2}):
            bounded = run_broker._bounded_replay_events(events)

        visible_text = [str(event.payload.get("text", "")) for event in bounded]
        assert bounded[0].payload["type"] == "notice"
        assert bounded[0].payload["text"] == run_broker.REPLAY_TRIM_NOTICE
        assert "line 1" not in visible_text
        assert "line 2" in visible_text
        assert "line 3" in visible_text
        assert bounded[-1].payload == {"type": "exit", "code": 0}

    def test_stream_run_events_replays_snapshot_before_waiting_for_live_events(self):
        class FakeStore:
            def __init__(self):
                self.wait_after_id = ""

            def replay(self, run_id):
                assert run_id == "run-1"
                return [run_broker.BrokerEvent("1-0", {"type": "output", "text": "replayed"})]

            def wait_after(self, run_id, after_id, timeout):
                self.wait_after_id = after_id
                return [run_broker.BrokerEvent("2-0", {"type": "exit", "code": 0})]

        store = FakeStore()
        with mock.patch.object(run_broker, "_store", return_value=store):
            events = list(run_broker.stream_run_events("run-1"))

        assert '"text": "replayed"' in events[0]
        assert '"type": "exit"' in events[1]
        assert store.wait_after_id == "1-0"

    def test_stream_run_events_skips_trim_notice_when_resuming_live_tail(self):
        class FakeStore:
            def __init__(self):
                self.wait_after_id = ""

            def replay(self, run_id):
                assert run_id == "run-1"
                return [
                    run_broker._make_trim_notice_event(),
                    run_broker.BrokerEvent("5-0", {"type": "output", "text": "tail"}),
                ]

            def wait_after(self, run_id, after_id, timeout):
                self.wait_after_id = after_id
                return [run_broker.BrokerEvent("6-0", {"type": "exit", "code": 0})]

        store = FakeStore()
        with mock.patch.object(run_broker, "_store", return_value=store):
            events = list(run_broker.stream_run_events("run-1"))

        assert events[0].startswith("data: ")
        assert "id:" not in events[0]
        assert '"text": "tail"' in events[1]
        assert store.wait_after_id == "5-0"

    def test_decode_payload_accepts_redis_bytes_fields(self):
        payload = run_broker._decode_payload({b"payload": b'{"type":"output","text":"hello"}'})

        assert payload == {"type": "output", "text": "hello"}

    def test_redis_store_decodes_bytes_event_ids_and_payloads(self):
        fake_redis = mock.Mock()
        fake_redis.xrange.return_value = [
            (b"1-0", {b"payload": b'{"type":"started"}'}),
            (b"2-0", {b"payload": b'{"type":"output","text":"hello"}'}),
        ]

        with mock.patch.object(run_broker, "redis_client", fake_redis):
            events = run_broker._RedisRunBrokerStore().events_after("run-1", after_id="1-0", limit=10)

        assert [(event.event_id, event.payload) for event in events] == [
            ("2-0", {"type": "output", "text": "hello"}),
        ]

    def test_redis_store_normalizes_invalid_resume_ids(self):
        fake_redis = mock.Mock()
        fake_redis.xrange.return_value = []

        with mock.patch.object(run_broker, "redis_client", fake_redis):
            run_broker._RedisRunBrokerStore().events_after("run-1", after_id="123-trim", limit=10)

        fake_redis.xrange.assert_called_once_with("runstream:run-1", min="0-0", count=10)

    def test_redis_replay_marks_tail_fetch_as_trimmed_when_stream_is_longer(self):
        fake_redis = mock.Mock()
        fake_redis.xrevrange.return_value = [
            (b"3-0", {b"payload": b'{"type":"output","text":"line 3"}'}),
            (b"2-0", {b"payload": b'{"type":"output","text":"line 2"}'}),
        ]
        fake_redis.xlen.return_value = 3

        with mock.patch.object(run_broker, "redis_client", fake_redis), \
             mock.patch.object(run_broker, "_replay_fetch_count", return_value=2):
            events = run_broker._RedisRunBrokerStore().replay("run-1")

        assert events[0].payload["type"] == "notice"
        assert events[0].payload["text"] == run_broker.REPLAY_TRIM_NOTICE
        assert [(event.event_id, event.payload.get("text")) for event in events[1:]] == [
            ("2-0", "line 2"),
            ("3-0", "line 3"),
        ]

    def test_redis_publish_trims_stream_with_replay_derived_maxlen(self):
        fake_redis = mock.Mock()
        fake_redis.xadd.return_value = b"1-0"

        with mock.patch.object(run_broker, "redis_client", fake_redis), \
             mock.patch.object(run_broker, "_redis_stream_maxlen", return_value=1234):
            event = run_broker._RedisRunBrokerStore().publish("run-1", "output", {"text": "hello"})

        assert event.event_id == "1-0"
        fake_redis.xtrim.assert_called_once_with(
            "runstream:run-1",
            maxlen=1234,
            approximate=True,
        )

    def test_broker_requires_redis_when_configured(self):
        with mock.patch.object(run_broker, "redis_client", None), \
             mock.patch.dict(run_broker.CFG, {
                 "run_broker_enabled": True,
                 "run_broker_require_redis": True,
             }):
            assert run_broker.broker_available() is False
            assert run_broker.broker_unavailable_reason() == (
                "Run broker requires Redis, but Redis is not available."
            )

    def test_broker_allows_memory_store_when_redis_is_optional(self):
        with mock.patch.object(run_broker, "redis_client", None), \
             mock.patch.dict(run_broker.CFG, {
                 "run_broker_enabled": True,
                 "run_broker_require_redis": False,
             }):
            assert run_broker.broker_available() is True
            assert run_broker.broker_unavailable_reason() == ""
            assert isinstance(run_broker._store(), run_broker._MemoryRunBrokerStore)


# ── pid_register / pid_pop (in-process mode) ─────────────────────────────────

class TestPidMap:
    def setup_method(self):
        # Ensure we test in-process mode — patch redis_client in the process module
        # directly, since pid_register/pid_pop check process.redis_client at call time.
        self._patcher = mock.patch.object(process, "redis_client", None)
        self._patcher.start()
        with process._pid_lock:
            process._pid_map.clear()

    def teardown_method(self):
        self._patcher.stop()
        with process._pid_lock:
            process._pid_map.clear()

    def test_register_and_pop_returns_pid(self):
        process.pid_register("run-1", 12345)
        result = process.pid_pop("run-1")
        assert result == 12345

    def test_pop_unknown_run_id_returns_none(self):
        result = process.pid_pop("nonexistent-run-id")
        assert result is None

    def test_double_pop_returns_none_second_time(self):
        process.pid_register("run-2", 99999)
        process.pid_pop("run-2")
        result = process.pid_pop("run-2")
        assert result is None

    def test_multiple_runs_isolated(self):
        process.pid_register("run-a", 111)
        process.pid_register("run-b", 222)
        assert process.pid_pop("run-a") == 111
        assert process.pid_pop("run-b") == 222


class TestActiveRunMetadata:
    def setup_method(self):
        self._patcher = mock.patch.object(process, "redis_client", None)
        self._patcher.start()
        with process._pid_lock:
            process._pid_map.clear()
            process._active_run_meta.clear()
            process._session_run_ids.clear()

    def teardown_method(self):
        self._patcher.stop()
        with process._pid_lock:
            process._pid_map.clear()
            process._active_run_meta.clear()
            process._session_run_ids.clear()

    def test_active_runs_for_session_preserves_pid(self):
        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process, "_pid_start_time", return_value=None),
        ):
            process.active_run_register(
                "run-1",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
            )

            assert process.active_runs_for_session("session-1") == [
                {
                    "run_id": "run-1",
                    "pid": 12345,
                    "command": "ping darklab.sh",
                    "started": "2026-01-01T00:00:00Z",
                    "source": "memory",
                    "run_type": "command",
                    "owner_client_id": "",
                    "owner_tab_id": "",
                    "owner_last_seen": None,
                    "owner_age_seconds": None,
                    "owner_stale": True,
                    "has_live_owner": False,
                    "owned_by_this_client": False,
                }
            ]

    def test_active_runs_for_session_reports_owner_liveness_for_client(self):
        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process, "_pid_start_time", return_value=None),
            mock.patch.object(process.time, "time", return_value=1000.0),
        ):
            process.active_run_register(
                "run-owned",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
                owner_client_id="client-1",
                owner_tab_id="tab-1",
            )

        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process.time, "time", return_value=1030.0),
        ):
            owned = process.active_runs_for_session("session-1", client_id="client-1")[0]
            other = process.active_runs_for_session("session-1", client_id="client-2")[0]

        assert owned["owned_by_this_client"] is True
        assert owned["has_live_owner"] is True
        assert owned["owner_stale"] is False
        assert owned["owner_tab_id"] == "tab-1"
        assert other["owned_by_this_client"] is False
        assert other["has_live_owner"] is True

    def test_active_runs_for_session_refreshes_matching_owner_liveness(self):
        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process, "_pid_start_time", return_value=None),
            mock.patch.object(process.time, "time", return_value=1000.0),
        ):
            process.active_run_register(
                "run-owned",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
                owner_client_id="client-1",
                owner_tab_id="tab-1",
            )

        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process.time, "time", return_value=1080.0),
        ):
            owned = process.active_runs_for_session("session-1", client_id="client-1")[0]

        assert owned["owner_last_seen"] == 1080.0
        assert owned["owner_age_seconds"] == 0
        assert owned["owner_stale"] is False
        assert owned["owned_by_this_client"] is True

    def test_active_run_touch_owner_refreshes_liveness(self):
        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process, "_pid_start_time", return_value=None),
            mock.patch.object(process.time, "time", return_value=1000.0),
        ):
            process.active_run_register(
                "run-owned",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
                owner_client_id="client-1",
                owner_tab_id="tab-1",
            )

        with mock.patch.object(process.time, "time", return_value=1100.0):
            assert process.active_run_touch_owner("run-owned", "client-2", "tab-1") is False
            assert process.active_run_touch_owner("run-owned", "client-1", "tab-1") is True

        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process.time, "time", return_value=1101.0),
        ):
            run = process.active_runs_for_session("session-1", client_id="client-1")[0]

        assert run["owner_last_seen"] == 1101.0
        assert run["owner_stale"] is False

    def test_active_run_owner_metadata_remains_provenance_only(self):
        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process, "_pid_start_time", return_value=None),
            mock.patch.object(process.time, "time", return_value=1000.0),
        ):
            process.active_run_register(
                "run-owned",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
                owner_client_id="client-1",
                owner_tab_id="tab-1",
            )

        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process.time, "time", return_value=1101.0),
        ):
            origin = process.active_runs_for_session("session-1", client_id="client-1")[0]
            attached = process.active_runs_for_session("session-1", client_id="client-2")[0]

        assert origin["owned_by_this_client"] is True
        assert attached["owned_by_this_client"] is False
        assert attached["has_live_owner"] is True
        assert attached["owner_client_id"] == "client-1"
        assert attached["owner_tab_id"] == "tab-1"
        assert not hasattr(process, "active_run_set_owner")

    def test_pid_pop_for_session_is_the_active_run_permission_boundary(self):
        with (
            mock.patch.object(process, "_pid_is_alive", return_value=True),
            mock.patch.object(process, "_pid_start_time", return_value=None),
            mock.patch.object(process.time, "time", return_value=1000.0),
        ):
            process.active_run_register(
                "run-owned",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
                owner_client_id="client-1",
                owner_tab_id="tab-1",
            )
            process.pid_register("run-owned", 12345)

        assert process.pid_pop_for_session("run-owned", "session-2") is None
        assert process.pid_pop_for_session("run-owned", "session-1") == 12345

        with process._pid_lock:
            assert "run-owned" not in process._pid_map
            assert "run-owned" not in process._active_run_meta

    def test_active_runs_for_session_prunes_dead_pid(self):
        with mock.patch.object(process, "_pid_start_time", return_value=None):
            process.active_run_register(
                "run-dead",
                23456,
                "session-1",
                "amass enum -active -d darklab.sh",
                "2026-01-01T00:00:00Z",
            )

        with mock.patch.object(process, "_pid_is_alive", return_value=False):
            assert process.active_runs_for_session("session-1") == []

        assert process._active_run_meta == {}
        assert process._session_run_ids == {}

    def test_active_runs_for_session_prunes_redis_pid_reuse(self):
        fake_redis = process._FakeRedisClient()
        with mock.patch.object(process, "redis_client", fake_redis):
            with mock.patch.object(process, "_pid_start_time", return_value="101"):
                process.active_run_register(
                    "run-reused",
                    34567,
                    "session-1",
                    "amass enum -active -d darklab.sh",
                    "2026-01-01T00:00:00Z",
                )
            process.pid_register("run-reused", 34567)

            with (
                mock.patch.object(process, "_pid_is_alive", return_value=True),
                mock.patch.object(process, "_pid_start_time", return_value="202"),
            ):
                assert process.active_runs_for_session("session-1") == []

            assert fake_redis.get("procmeta:run-reused") is None
            assert fake_redis.get("proc:run-reused") is None
            assert fake_redis.smembers("sessionprocs:session-1") == set()

    def test_pid_pop_for_session_requires_matching_session(self):
        with mock.patch.object(process, "_pid_start_time", return_value=None):
            process.pid_register("run-owned", 12345)
            process.active_run_register(
                "run-owned",
                12345,
                "session-1",
                "ping darklab.sh",
                "2026-01-01T00:00:00Z",
            )

        assert process.pid_pop_for_session("run-owned", "session-2") is None
        assert process.pid_pop_for_session("run-owned", "session-1") == 12345
        assert process.pid_pop("run-owned") is None
        assert process.active_runs_for_session("session-1") == []

    def test_active_runs_for_session_prunes_redis_legacy_metadata_on_linux(self):
        fake_redis = process._FakeRedisClient()
        payload = {
            "run_id": "run-legacy",
            "pid": 45678,
            "session_id": "session-1",
            "command": "amass enum -active -d darklab.sh",
            "started": "2026-01-01T00:00:00Z",
        }
        with mock.patch.object(process, "redis_client", fake_redis):
            fake_redis.set("procmeta:run-legacy", process.json.dumps(payload))
            fake_redis.sadd("sessionprocs:session-1", "run-legacy")

            with (
                mock.patch.object(process, "_pid_is_alive", return_value=True),
                mock.patch.object(process, "_pid_start_time", return_value="303"),
            ):
                assert process.active_runs_for_session("session-1") == []

            assert fake_redis.get("procmeta:run-legacy") is None

    def test_active_run_resource_usage_reports_cumulative_cpu_and_memory(self):
        class FakeTimes:
            def __init__(self, user, system):
                self.user = user
                self.system = system

        class FakeMemory:
            def __init__(self, rss):
                self.rss = rss

        class FakeProcess:
            def __init__(self, user, system, rss, children=None):
                self._times = FakeTimes(user, system)
                self._memory = FakeMemory(rss)
                self._children = children or []

            def children(self, recursive=True):
                assert recursive is True
                return self._children

            def cpu_times(self):
                return self._times

            def memory_info(self):
                return self._memory

        root = FakeProcess(1.0, 0.5, 200, [FakeProcess(0.4, 0.1, 100)])
        fake_psutil = mock.Mock()
        fake_psutil.Process.return_value = root

        with mock.patch.object(process, "psutil", fake_psutil):
            usage = process._active_run_resource_usage("run-stats", 12345)

        assert usage == {
            "status": "ok",
            "cpu_seconds": 2.0,
            "memory_bytes": 300,
            "process_count": 2,
        }


class TestInteractivePtyRegistry:
    def test_live_registry_publishes_each_supported_interactive_tool(self):
        specs = {spec["root"]: spec for spec in interactive_pty_specs_from_registry()}
        assert set(specs) == {"mtr", "ffuf", "masscan"}
        for root, expected in (
            ("mtr", {"trigger_flag": "--interactive", "requires_args": True}),
            ("ffuf", {"trigger_flag": "--interactive", "requires_args": True}),
            ("masscan", {"trigger_flag": "--interactive", "requires_args": True}),
        ):
            spec = specs[root]
            assert spec["trigger_flag"] == expected["trigger_flag"]
            assert spec["requires_args"] is expected["requires_args"]
            assert spec["allow_input"] is True
            max_runtime = spec["max_runtime_seconds"]
            assert isinstance(max_runtime, int) and max_runtime > 0


class TestPtyBrokerService:
    def test_pty_broker_is_available_with_redis_even_when_workers_are_not_sticky(self):
        with mock.patch.object(pty_service, "redis_client", object()), \
             mock.patch.object(pty_service, "pty_worker_supported", return_value=False):
            assert pty_service.pty_broker_available() is True

    def test_pty_input_and_resize_queue_through_redis_without_local_run(self):
        fake = process._FakeRedisClient()
        run_id = "pty-run-redis"
        fake.set(
            pty_service._meta_key(run_id),
            json.dumps({
                "run_id": run_id,
                "session_id": "session-1",
                "command": "mtr --interactive darklab.sh",
                "started": "2026-01-01T00:00:00Z",
                "rows": 24,
                "cols": 100,
                "closed": False,
            }),
        )

        with mock.patch.object(pty_service, "redis_client", fake):
            assert pty_service.write_pty_input(run_id, "session-1", "q") == (True, "")
            assert pty_service.resize_pty(run_id, "session-1", 33, 120) == (True, "", 33, 120)
            rows = fake.xread({pty_service._control_key(run_id): "0-0"}, count=10)

        payloads = [
            json.loads(fields["payload"])
            for _key, stream_rows in rows
            for _event_id, fields in stream_rows
        ]
        assert payloads == [
            {"data": "q", "action": "input"},
            {"rows": 33, "cols": 120, "action": "resize"},
        ]

    def test_pty_stream_replays_redis_output_events_for_any_worker(self):
        fake = process._FakeRedisClient()
        run_id = "pty-run-stream"
        fake.set(
            pty_service._meta_key(run_id),
            json.dumps({
                "run_id": run_id,
                "session_id": "session-1",
                "command": "mtr --interactive darklab.sh",
                "started": "2026-01-01T00:00:00Z",
                "rows": 24,
                "cols": 100,
                "closed": False,
            }),
        )

        with mock.patch.object(pty_service, "redis_client", fake):
            pty_service.publish_pty_event(run_id, "output", {"text": "live hop"})
            stream = pty_service.stream_pty_events(run_id, "session-1")
            chunk = next(stream)
            close_stream = getattr(stream, "close", None)
            if callable(close_stream):
                close_stream()

        assert "live hop" in chunk
        assert '"type": "output"' in chunk

    def test_pty_snapshot_loads_distributed_redis_snapshot_without_local_run(self):
        class FakeProc:
            pid = 4242

        class FakeCapture:
            def synthesize_entries(self):
                return [{"text": "plain fallback", "cls": ""}]

            def ansi_snapshot(self):
                return "\x1b[0m\x1b[2J\x1b[Hredis snapshot\x1b[1;1H", False

        fake = process._FakeRedisClient()
        run = pty_service.PtyRun(
            run_id="pty-run-snapshot-redis",
            session_id="session-1",
            command="mtr --interactive darklab.sh",
            argv=["mtr", "darklab.sh"],
            started="2026-01-01T00:00:00Z",
            master_fd=-1,
            proc=cast(subprocess.Popen, FakeProc()),
            rows=24,
            cols=100,
            allow_input=True,
            max_runtime_seconds=900,
            brokered=True,
            terminal_capture=cast(pty_service.PtyTerminalCapture, FakeCapture()),
        )
        run.capture_event_id = "1770000000000-2"

        with mock.patch.object(pty_service, "redis_client", fake):
            pty_service._store_pty_meta(run)
            pty_service._store_pty_snapshot(run, force=True)
            ok, message, snapshot = pty_service.pty_run_snapshot(run.run_id, "session-1")

        assert ok is True
        assert message == ""
        assert snapshot is not None
        assert snapshot["snapshot_format"] == "ansi"
        assert snapshot["ansi_snapshot"].endswith("redis snapshot\x1b[1;1H")
        assert snapshot["after_event_id"] == "1770000000000-2"
        assert snapshot["entries"] == []

    def test_pty_start_cleans_up_if_reader_thread_fails_to_start(self):
        class FakeProc:
            pid = 4242

            def poll(self):
                return None

            def wait(self, timeout=None):  # noqa: ARG002
                return -15

        fake_proc = FakeProc()
        closed = []
        fake_pyte = type("FakePyte", (), {
            "HistoryScreen": lambda *args, **kwargs: object(),
            "Stream": lambda *args, **kwargs: object(),
        })()

        with mock.patch.object(pty_service.pty, "openpty", return_value=(10, 11)), \
             mock.patch.object(pty_service, "pyte", fake_pyte), \
             mock.patch.object(pty_service, "_set_pty_size"), \
             mock.patch.object(pty_service.subprocess, "Popen", return_value=fake_proc), \
             mock.patch.object(pty_service.os, "close", side_effect=lambda fd: closed.append(fd)), \
             mock.patch.object(pty_service.os, "killpg") as killpg, \
             mock.patch.object(pty_service, "pid_register"), \
             mock.patch.object(pty_service, "pid_pop") as pid_pop, \
             mock.patch.object(pty_service, "active_run_register"), \
             mock.patch.object(pty_service, "active_run_remove") as active_run_remove, \
             mock.patch.object(pty_service.threading.Thread, "start", side_effect=RuntimeError("thread failed")):
            with pytest.raises(RuntimeError, match="thread failed"):
                pty_service.start_pty_run(
                    session_id="session-1",
                    client_ip="127.0.0.1",
                    command="mtr --interactive darklab.sh",
                    argv=["mtr", "darklab.sh"],
                )

        killpg.assert_called_once_with(4242, pty_service.signal.SIGTERM)
        assert 10 in closed
        assert 11 in closed
        pid_pop.assert_called_once()
        active_run_remove.assert_called_once()

    def test_pty_start_requires_pyte_for_saved_terminal_capture(self):
        with mock.patch.object(pty_service, "pyte", None), \
             mock.patch.object(pty_service.pty, "openpty") as openpty:
            with pytest.raises(pty_service.PtyDependencyError, match="requires pyte"):
                pty_service.start_pty_run(
                    session_id="session-1",
                    client_ip="127.0.0.1",
                    command="mtr --interactive darklab.sh",
                    argv=["mtr", "darklab.sh"],
                )

        openpty.assert_not_called()

    def test_pty_command_env_inherits_only_vetted_keys(self):
        with mock.patch.dict(pty_service.os.environ, {
            "PATH": "/custom/bin",
            "HOME": "/home/appuser",
            "USER": "appuser",
            "LOGNAME": "appuser",
            "XDG_CONFIG_HOME": "/tmp/config",
            "LANG": "en_US.UTF-8",
            "SECRET_TOKEN": "do-not-pass",
            "LD_PRELOAD": "/tmp/inject.so",
        }, clear=True):
            env = pty_service._command_env()

        assert env["PATH"] == "/custom/bin"
        assert env["HOME"] == "/home/appuser"
        assert env["USER"] == "appuser"
        assert env["LOGNAME"] == "appuser"
        assert env["XDG_CONFIG_HOME"] == "/tmp/config"
        assert env["LANG"] == "en_US.UTF-8"
        assert env["LC_ALL"] == "en_US.UTF-8"
        assert env["TERM"] == "xterm-256color"
        assert "SECRET_TOKEN" not in env
        assert "LD_PRELOAD" not in env

        with mock.patch.dict(pty_service.os.environ, {}, clear=True):
            env = pty_service._command_env()

        assert env["HOME"] == tempfile.gettempdir()


class TestPtyTerminalCapture:
    @staticmethod
    def _fake_pyte(
        scrollback=None,
        final_frame=None,
        *,
        buffer=None,
        cursor=None,
        feed_error=False,
        feed_calls=None,
    ):
        class FakeHistoryScreen:
            def __init__(self, cols, rows, history):  # noqa: ARG002
                self.history = type("FakeHistory", (), {"top": scrollback or []})()
                self.display = final_frame or []
                if buffer is not None:
                    self.buffer = buffer
                cursor_y, cursor_x = cursor or (0, 0)
                self.cursor = type("FakeCursor", (), {"y": cursor_y, "x": cursor_x})()
                self.resized = None

            def resize(self, *, lines, columns):
                self.resized = (lines, columns)

        class FakeStream:
            def __init__(self, screen):
                self.screen = screen

            def feed(self, text):
                # Record-then-raise: even when feed_error is set, the call is
                # recorded first so a future test combining both still observes
                # the input that triggered the failure.
                if feed_calls is not None:
                    feed_calls.append(text)
                if feed_error:
                    raise ValueError("bad escape")

        return type("FakePyte", (), {"HistoryScreen": FakeHistoryScreen, "Stream": FakeStream})()

    def test_terminal_capture_synthesizes_scrollback_and_final_frame(self):
        feed_calls = []
        fake_pyte = self._fake_pyte(
            scrollback=["scrolled line   "],
            final_frame=["visible line   ", "   "],
            feed_calls=feed_calls,
        )
        with mock.patch.object(pty_service, "pyte", fake_pyte):
            capture = pty_service.PtyTerminalCapture(rows=24, cols=100, history_lines=20)
            capture.feed("\x1b[1mbold\x1b[0m")
            capture.resize(30, 120)
            entries = capture.synthesize_entries()

        assert any("bold" in call for call in feed_calls)
        assert entries == [
            {"text": "scrolled line", "cls": ""},
            {"text": "", "cls": "pty-marker"},
            {"text": "visible line", "cls": ""},
        ]

    def test_terminal_capture_builds_ansi_snapshot_with_attrs_and_cursor(self):
        cell = type(
            "FakeCell",
            (),
            {
                "data": "R",
                "fg": "red",
                "bg": "default",
                "bold": True,
                "italics": False,
                "underscore": False,
                "strikethrough": False,
                "reverse": False,
            },
        )()
        fake_pyte = self._fake_pyte(
            scrollback=["older row"],
            buffer={0: {0: cell, 1: "!"}, 1: "plain row"},
            cursor=(1, 2),
        )
        with mock.patch.object(pty_service, "pyte", fake_pyte):
            capture = pty_service.PtyTerminalCapture(rows=2, cols=10, history_lines=20)
            snapshot, truncated = capture.ansi_snapshot()

        assert truncated is False
        assert snapshot.startswith("\x1b[0m\x1b[2J\x1b[H")
        assert "older row" in snapshot
        assert "\x1b[1;31mR\x1b[0m!" in snapshot
        assert "plain row" in snapshot
        assert snapshot.endswith("\x1b[0m\x1b[2;3H")

    def test_terminal_capture_omits_marker_when_only_final_frame_exists(self):
        fake_pyte = self._fake_pyte(final_frame=["mtr final row  ", ""])
        with mock.patch.object(pty_service, "pyte", fake_pyte):
            capture = pty_service.PtyTerminalCapture(rows=24, cols=100, history_lines=20)

        assert capture.synthesize_entries() == [{"text": "mtr final row", "cls": ""}]

    def test_terminal_capture_omits_marker_when_only_scrollback_exists(self):
        fake_pyte = self._fake_pyte(scrollback=["match one  "])
        with mock.patch.object(pty_service, "pyte", fake_pyte):
            capture = pty_service.PtyTerminalCapture(rows=24, cols=100, history_lines=20)

        assert capture.synthesize_entries() == [{"text": "match one", "cls": ""}]

    def test_terminal_capture_persists_notice_when_output_is_empty(self):
        fake_pyte = self._fake_pyte()
        with mock.patch.object(pty_service, "pyte", fake_pyte):
            capture = pty_service.PtyTerminalCapture(rows=24, cols=100, history_lines=20)

        assert capture.synthesize_entries() == [{
            "text": "[interactive PTY exited with no output]",
            "cls": "notice",
        }]

    def test_terminal_capture_falls_back_after_first_feed_error(self):
        fake_pyte = self._fake_pyte(feed_error=True)
        with mock.patch.object(pty_service, "pyte", fake_pyte), \
             mock.patch.object(pty_service.log, "warning") as warning:
            capture = pty_service.PtyTerminalCapture(rows=24, cols=100, history_lines=20)
            capture.feed("\x1b[31mfirst\x1b[0m\n")
            capture.feed("\x1b]0;Window Title\x07second\n")
            capture.feed("\x1bPstatus\x1b\\third\n")

        assert warning.call_count == 1
        assert capture.synthesize_entries() == [
            {"text": "first", "cls": ""},
            {"text": "second", "cls": ""},
            {"text": "third", "cls": ""},
        ]

    def test_terminal_capture_fallback_treats_carriage_return_as_overwrite(self):
        with mock.patch.object(pty_service, "pyte", None):
            capture = pty_service.PtyTerminalCapture(rows=24, cols=100, history_lines=20)
            capture.feed("Discovered open port 443/tcp on 192.168.1.5\r\n")
            capture.feed("rate:  0.00-kpps, 50.00% done, found=1\r")
            capture.feed("rate:  0.00-kpps, 100.00% done, found=2\r")

        assert capture.synthesize_entries() == [
            {"text": "Discovered open port 443/tcp on 192.168.1.5", "cls": ""},
            {"text": "rate:  0.00-kpps, 100.00% done, found=2", "cls": ""},
        ]

    def test_terminal_history_line_limit_is_bounded(self):
        assert pty_service._terminal_history_line_limit(0) == 10000
        assert pty_service._terminal_history_line_limit(10) == 2000
        assert pty_service._terminal_history_line_limit(100000) == 10000


# ── _format_retention ─────────────────────────────────────────────────────────

class TestFormatRetention:
    def test_zero_returns_unlimited(self):
        assert "unlimited" in _format_retention(0)

    def test_365_returns_one_year(self):
        assert _format_retention(365) == "1 year"

    def test_730_returns_two_years(self):
        assert _format_retention(730) == "2 years"

    def test_30_returns_one_month(self):
        assert _format_retention(30) == "1 month"

    def test_60_returns_two_months(self):
        assert _format_retention(60) == "2 months"

    def test_7_returns_days(self):
        assert _format_retention(7) == "7 days"

    def test_1_returns_singular_day(self):
        assert _format_retention(1) == "1 day"

    # Compound cases — arbitrary durations decomposed into years/months/days
    def test_35_days_is_one_month_and_5_days(self):
        assert _format_retention(35) == "1 month and 5 days"

    def test_400_days_is_one_year_one_month_and_5_days(self):
        assert _format_retention(400) == "1 year, 1 month and 5 days"

    def test_366_days_is_one_year_and_1_day(self):
        assert _format_retention(366) == "1 year and 1 day"

    def test_395_days_is_one_year_and_1_month(self):
        assert _format_retention(395) == "1 year and 1 month"

    def test_singular_month_no_s(self):
        assert _format_retention(31) == "1 month and 1 day"


# ── load_welcome ──────────────────────────────────────────────────────────────

class TestWelcomeLoading:
    def _write(self, content):
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_missing_file_returns_empty_list(self):
        with mock.patch("commands.WELCOME_FILE", "/nonexistent/welcome.yaml"):
            result = load_welcome()
        assert result == []

    def test_valid_entry_with_cmd_and_out(self):
        path = self._write("- cmd: ping google.com\n  out: \"64 bytes\"\n")
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)
        assert len(result) == 1
        assert result[0]["cmd"] == "ping google.com"
        assert result[0]["out"] == "64 bytes"
        assert result[0]["group"] == ""
        assert result[0]["featured"] is False

    def test_entry_with_group_and_featured_metadata(self):
        path = self._write("- cmd: dig darklab.sh A\n  out: \"answer\"\n  group: DNS\n  featured: true\n")
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)
        assert result[0]["group"] == "dns"
        assert result[0]["featured"] is True

    def test_entry_without_out_gets_empty_string(self):
        path = self._write("- cmd: ping google.com\n")
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)
        assert result[0]["out"] == ""

    def test_entry_missing_cmd_filtered_out(self):
        path = self._write("- out: \"some output\"\n- cmd: nmap\n  out: \"scan\"\n")
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)
        assert len(result) == 1
        assert result[0]["cmd"] == "nmap"

    def test_out_trailing_whitespace_stripped_but_leading_preserved(self):
        # rstrip (not strip) preserves leading indentation in output blocks
        path = self._write("- cmd: ping\n  out: \"  indented output   \"\n")
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)
        assert result[0]["out"] == "  indented output"

    def test_non_list_yaml_returns_empty(self):
        path = self._write("key: value\n")
        try:
            with mock.patch("commands.WELCOME_FILE", path):
                result = load_welcome()
        finally:
            os.unlink(path)
        assert result == []

    def test_local_overlay_appends_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "welcome.yaml")
            local_path = os.path.join(tmp, "welcome.local.yaml")
            with open(base_path, "w") as f:
                f.write("- cmd: ping\n  out: base\n")
            with open(local_path, "w") as f:
                f.write("- cmd: curl\n  out: local\n")
            with mock.patch("commands.WELCOME_FILE", base_path):
                result = load_welcome()
        assert [item["cmd"] for item in result] == ["ping", "curl"]


# ── load_ascii_art / load_ascii_mobile_art / load_welcome_hints ──────────────

class TestWelcomeAssetLoading:
    def test_missing_ascii_file_returns_empty_string(self):
        with mock.patch("commands.ASCII_FILE", "/nonexistent/ascii.txt"):
            assert load_ascii_art() == ""

    def test_ascii_art_trims_only_trailing_whitespace(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("  banner  \n\n")
            path = f.name
        try:
            with mock.patch("commands.ASCII_FILE", path):
                assert load_ascii_art() == "  banner"
        finally:
            os.unlink(path)

    def test_missing_mobile_ascii_file_returns_empty_string(self):
        with mock.patch("commands.ASCII_MOBILE_FILE", "/nonexistent/ascii_mobile.txt"):
            assert load_ascii_mobile_art() == ""

    def test_mobile_ascii_art_trims_only_trailing_whitespace(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("  mobile banner  \n\n")
            path = f.name
        try:
            with mock.patch("commands.ASCII_MOBILE_FILE", path):
                assert load_ascii_mobile_art() == "  mobile banner"
        finally:
            os.unlink(path)

    def test_ascii_art_local_overlay_replaces_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "ascii.txt")
            local_path = os.path.join(tmp, "ascii.local.txt")
            with open(base_path, "w") as f:
                f.write("base art")
            with open(local_path, "w") as f:
                f.write("local art")
            with mock.patch("commands.ASCII_FILE", base_path):
                assert load_ascii_art() == "local art"

    def test_mobile_ascii_art_local_overlay_replaces_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "ascii_mobile.txt")
            local_path = os.path.join(tmp, "ascii_mobile.local.txt")
            with open(base_path, "w") as f:
                f.write("base mobile art")
            with open(local_path, "w") as f:
                f.write("local mobile art")
            with mock.patch("commands.ASCII_MOBILE_FILE", base_path):
                assert load_ascii_mobile_art() == "local mobile art"

    def test_local_hints_overlay_appends_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "app_hints.txt")
            local_path = os.path.join(tmp, "app_hints.local.txt")
            with open(base_path, "w") as f:
                f.write("Use the history panel.\n")
            with open(local_path, "w") as f:
                f.write("Press Enter to run.\n")
            with mock.patch("commands.APP_HINTS_FILE", base_path):
                assert load_welcome_hints() == ["Use the history panel.", "Press Enter to run."]

    def test_mobile_hints_overlay_appends_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "app_hints_mobile.txt")
            local_path = os.path.join(tmp, "app_hints_mobile.local.txt")
            with open(base_path, "w") as f:
                f.write("Tap the prompt.\n")
            with open(local_path, "w") as f:
                f.write("Use the mobile menu.\n")
            with mock.patch("commands.APP_HINTS_MOBILE_FILE", base_path):
                assert load_mobile_welcome_hints() == ["Tap the prompt.", "Use the mobile menu."]


# ── run_output_store ──────────────────────────────────────────────────────────

class TestOutputSignals:
    def test_command_root_and_target_extraction(self):
        assert command_root("nmap -sV ip.darklab.sh") == "nmap"
        assert extract_target("nuclei -u https://ip.darklab.sh -t http/") == "ip.darklab.sh"
        assert extract_target("nc -zv ip.darklab.sh 443 80") == "ip.darklab.sh"
        assert extract_target("dig @8.8.8.8 darklab.sh A") == "darklab.sh"
        assert extract_target("assetfinder -subs-only darklab.sh") == "darklab.sh"

    def test_classifies_common_findings(self):
        assert classify_line("443/tcp open https", command="nmap ip.darklab.sh") == ["findings"]
        assert classify_line("ip.darklab.sh [107.178.109.44] 80 (http) open", command="nc -zv ip.darklab.sh 80") == ["findings"]
        assert classify_line("darklab.sh has address 104.21.4.35", command="host darklab.sh") == ["findings"]
        assert classify_line("104.21.4.35", command="dig darklab.sh +short") == ["findings"]
        assert classify_line("1 aspmx.l.google.com.", command="dig MX darklab.sh +short") == ["findings"]
        assert classify_line("fw-vx1.darklab.sh", command="assetfinder -subs-only darklab.sh") == ["findings"]
        assert classify_line("darklab.sh", command="assetfinder -subs-only darklab.sh") == ["findings"]
        assert classify_line("104.21.4.35", command="cat ips.txt") == []
        assert classify_line("fw-vx1.darklab.sh", command="cat hosts.txt") == []

    def test_classifies_dns_enumeration_findings_by_command(self):
        assert classify_line("ip.darklab.sh", command="dnsx -d darklab.sh -w dns.txt") == ["findings"]
        assert classify_line("www.darklab.sh", command="dnsx -d darklab.sh -w dns.txt") == ["findings"]
        assert classify_line("[INF] Current dnsx version 1.2.3 (latest)", command="dnsx -d darklab.sh") == []
        assert classify_line("Found: ip.darklab.sh. (107.178.109.44)", command="fierce --domain darklab.sh") == ["findings"]
        assert classify_line(
            "SOA: frank.ns.cloudflare.com. (173.245.59.166)",
            command="fierce --domain darklab.sh",
        ) == ["findings"]
        assert classify_line("104.21.4.0/24", command="dnsenum --noreverse darklab.sh") == ["findings"]
        assert classify_line("[*] DNSSEC is configured for darklab.sh", command="dnsrecon -d darklab.sh -t std") == ["findings"]
        assert classify_line("ip.darklab.sh", command="cat hosts.txt") == []

    def test_classifies_web_enumeration_findings_by_command(self):
        assert classify_line(
            "https://ip.darklab.sh [200] [Nginx]",
            command="pd-httpx -u https://ip.darklab.sh -title -status-code -tech-detect",
        ) == ["findings"]
        assert classify_line(
            "https://p.darklab.sh/js/privatebin.js?2.0.4",
            command="katana -u https://p.darklab.sh",
        ) == [
            "findings",
        ]
        assert classify_line("https://p.darklab.sh/js/'+t+'", command="katana -u https://p.darklab.sh") == []
        assert classify_line(
            "[+] The site https://darklab.sh is behind Cloudflare (Cloudflare Inc.) WAF.",
            command="wafw00f https://darklab.sh",
        ) == ["findings"]
        assert classify_line("[~] Number of requests: 2", command="wafw00f https://darklab.sh") == ["summaries"]

    def test_classifies_web_scanner_findings_by_command(self):
        assert classify_line("+ Target IP:          107.178.109.44", command="nikto -h ip.darklab.sh -p 443 -ssl") == [
            "findings",
        ]
        assert classify_line("+ Server: nginx", command="nikto -h ip.darklab.sh -p 443 -ssl") == ["findings"]
        assert classify_line("+ Start Time:         2026-05-05 20:24:44 (GMT0)", command="nikto -h ip.darklab.sh") == []
        assert classify_line(
            "[+] XML-RPC seems to be enabled: https://churchint.org/xmlrpc.php",
            command="wpscan --url https://churchint.org",
        ) == [
            "findings",
        ]
        assert classify_line("[+] Finished: Tue May  5 20:26:53 2026", command="wpscan --url https://churchint.org") == []
        assert classify_line(
            "[!] No WPScan API Token given, as a result vulnerability data has not been output.",
            command="wpscan --url https://churchint.org",
        ) == [
            "warnings",
        ]

    def test_classifies_tls_scanner_findings_by_command(self):
        assert classify_line("TLS 1.3    offered (OK): final", command="testssl --fast https://ip.darklab.sh") == [
            "findings",
        ]
        assert classify_line("Overall Grade                A+", command="testssl --fast https://ip.darklab.sh") == [
            "findings",
        ]
        assert classify_line("TLSv1.3   enabled", command="sslscan ip.darklab.sh") == ["findings"]
        assert classify_line("Subject:  ip.darklab.sh", command="sslscan ip.darklab.sh") == ["findings"]
        assert classify_line("Common Name:                       ip.darklab.sh", command="sslyze ip.darklab.sh") == [
            "findings",
        ]
        assert classify_line("TLS_FALLBACK_SCSV:                 OK - Supported", command="sslyze ip.darklab.sh") == [
            "findings",
        ]
        assert classify_line("ip.darklab.sh:443: FAILED - Not compliant.", command="sslyze ip.darklab.sh") == [
            "errors",
        ]

    def test_classifies_projectdiscovery_and_port_scanner_findings(self):
        assert classify_line("ip.darklab.sh:443", command="naabu -host ip.darklab.sh -p 80,443") == ["findings"]
        assert classify_line(
            "[INF] Found 2 ports on host ip.darklab.sh (107.178.109.44)",
            command="naabu -host ip.darklab.sh",
        ) == [
            "summaries",
        ]
        assert classify_line("Open 107.178.109.44:443", command="rustscan -a ip.darklab.sh -p 80,443") == [
            "findings",
        ]
        assert classify_line(
            "[waf-detect:nginxgeneric] [http] [info] https://ip.darklab.sh",
            command="nuclei -u https://ip.darklab.sh",
        ) == [
            "findings",
        ]
        assert classify_line(
            "[tls-version] [ssl] [info] ip.darklab.sh:443 [\"tls12\"]",
            command="nuclei -u https://ip.darklab.sh",
        ) == [
            "findings",
        ]
        assert classify_line("[INF] Scan completed in 4m. 21 matches found.", command="nuclei -u https://ip.darklab.sh") == [
            "summaries",
        ]

    def test_signal_matching_uses_ansi_normalized_text(self):
        examples = [
            (
                "https://ip.darklab.sh [200] [Nginx]",
                "pd-httpx -u https://ip.darklab.sh -title -status-code -tech-detect",
                ["findings"],
            ),
            (
                "[+] The site https://darklab.sh is behind Cloudflare (Cloudflare Inc.) WAF.",
                "wafw00f https://darklab.sh",
                ["findings"],
            ),
            (
                "[+] Headers",
                "wpscan --url https://churchint.org",
                ["findings"],
            ),
            (
                "[waf-detect:nginxgeneric] [http] [info] https://ip.darklab.sh",
                "nuclei -u https://ip.darklab.sh",
                ["findings"],
            ),
            (
                "[tls-version] [ssl] [info] ip.darklab.sh:443 [\"tls13\"]",
                "nuclei -u https://ip.darklab.sh",
                ["findings"],
            ),
            (
                "[INF] Scan completed in 4m. 21 matches found.",
                "nuclei -u https://ip.darklab.sh",
                ["summaries"],
            ),
        ]

        for plain_text, command, expected in examples:
            assert classify_line(plain_text, command=command) == expected
            assert classify_line(f"\x1b[32m{plain_text}\x1b[0m", command=command) == expected
            assert classify_line(
                plain_text.replace("[", "[\x1b[36m").replace("]", "\x1b[0m]"),
                command=command,
            ) == expected

    def test_classifies_nuclei_findings_by_command(self):
        nuclei_findings = [
            "[waf-detect:nginxgeneric] [http] [info] https://ip.darklab.sh",
            "[tls-version] [ssl] [info] ip.darklab.sh:443 [\"tls12\"]",
            "[tls-version] [ssl] [info] ip.darklab.sh:443 [\"tls13\"]",
            "[tech-detect:nginx] [http] [info] https://ip.darklab.sh",
            "[cpanel-backup-exclude-exposure] [http] [info] https://ip.darklab.sh/cpbackup-exclude.conf",
            "[http-missing-security-headers:referrer-policy] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:clear-site-data] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:cross-origin-resource-policy] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:missing-content-type] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:x-frame-options] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:x-content-type-options] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:x-permitted-cross-domain-policies] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:cross-origin-embedder-policy] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:cross-origin-opener-policy] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:strict-transport-security] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:content-security-policy] [http] [info] https://ip.darklab.sh",
            "[http-missing-security-headers:permissions-policy] [http] [info] https://ip.darklab.sh",
            "[caa-fingerprint] [dns] [info] ip.darklab.sh",
            "[dns-saas-service-detection] [dns] [info] ip.darklab.sh [\"fw-vx2-vp1.darklab.sh\"]",
            "[ssl-issuer] [ssl] [info] ip.darklab.sh:443 [\"Let's Encrypt\"]",
            "[ssl-dns-names] [ssl] [info] ip.darklab.sh:443 [\"ip.darklab.sh\"]",
        ]

        for line in nuclei_findings:
            assert classify_line(line, command="nuclei -u https://ip.darklab.sh") == ["findings"]

    def test_classifies_warning_error_and_summary_lines(self):
        assert classify_line("warning: retrying request", cls="notice", command="curl https://darklab.sh") == ["warnings"]
        assert classify_line("connection timed out", cls="exit-fail", command="nc -zv ip.darklab.sh 80") == ["errors"]
        assert classify_line(
            "Nmap done: 1 IP address (1 host up) scanned in 1.23 seconds",
            command="nmap ip.darklab.sh",
        ) == ["summaries"]

    def test_workspace_notices_are_not_output_signals(self):
        assert classify_line(
            "[workspace] reading nmap/nmap_input.txt",
            cls="notice",
            command="nmap -iL nmap/nmap_input.txt",
        ) == []
        assert classify_line(
            "[workspace] writing nmap/nmap_results.xml",
            cls="notice",
            command="nmap -oX nmap/nmap_results.xml",
        ) == []

        classifier = OutputSignalClassifier("nmap -iL nmap/nmap_input.txt -oX nmap/nmap_results.xml")
        metadata = classifier.classify_line("[workspace] writing nmap/nmap_results.xml", cls="notice")

        assert metadata["line_index"] == 0
        assert metadata["command_root"] == "nmap"
        assert "signals" not in metadata

    def test_nmap_input_file_sections_update_signal_target(self):
        classifier = OutputSignalClassifier("nmap -iL darklab_inputs.txt -sT")

        first_header = classifier.classify_line("Nmap scan report for ip.darklab.sh (192.168.20.5)")
        first_port = classifier.classify_line("80/tcp   open  http")
        second_header = classifier.classify_line("Nmap scan report for h.darklab.sh (108.79.194.246)")
        second_port = classifier.classify_line("443/tcp  open   https")

        assert first_header["target"] == "ip.darklab.sh"
        assert first_port["target"] == "ip.darklab.sh"
        assert first_port["signals"] == ["findings"]
        assert second_header["target"] == "h.darklab.sh"
        assert second_port["target"] == "h.darklab.sh"
        assert second_port["signals"] == ["findings"]

    def test_user_killed_process_is_not_an_error(self):
        assert classify_line("[killed by user after 2.0s]", cls="exit-fail", command="ping darklab.sh") == []

    def test_builtin_classifier_keeps_metadata_but_omits_signals(self):
        classifier = OutputSignalClassifier("status", cmd_type="builtin")
        metadata = classifier.classify_line("warning: fake status line", cls="notice")

        assert metadata["line_index"] == 0
        assert metadata["command_root"] == "status"
        assert "signals" not in metadata


class TestRunOutputCapture:
    def teardown_method(self):
        if os.path.isdir(RUN_OUTPUT_DIR):
            for name in os.listdir(RUN_OUTPUT_DIR):
                if name.startswith("test-run-output-"):
                    os.unlink(os.path.join(RUN_OUTPUT_DIR, name))

    def test_preview_keeps_only_last_n_lines(self):
        capture = RunOutputCapture("test-run-output-preview", preview_limit=2, persist_full_output=False, full_output_max_bytes=0)
        capture.add_line("one")
        capture.add_line("two")
        capture.add_line("three")
        capture.finalize()

        assert list(capture.preview_lines) == [
            {"text": "two", "cls": "", "tsC": "", "tsE": ""},
            {"text": "three", "cls": "", "tsC": "", "tsE": ""},
        ]
        assert capture.preview_truncated is True
        assert capture.output_line_count == 3

    def test_preview_byte_cap_drops_oldest_lines(self):
        capture = RunOutputCapture(
            "test-run-output-preview-bytes",
            preview_limit=10,
            persist_full_output=False,
            full_output_max_bytes=0,
            preview_max_bytes=150,
        )
        capture.add_line("a" * 20)
        capture.add_line("b" * 20)
        capture.add_line("c" * 20)
        capture.finalize()

        assert list(capture.preview_lines) == [
            {"text": "b" * 20, "cls": "", "tsC": "", "tsE": ""},
            {"text": "c" * 20, "cls": "", "tsC": "", "tsE": ""},
        ]
        assert capture.preview_truncated is True
        assert capture.output_line_count == 3

    def test_preview_byte_cap_truncates_single_huge_line(self):
        capture = RunOutputCapture(
            "test-run-output-preview-huge-line",
            preview_limit=10,
            persist_full_output=False,
            full_output_max_bytes=0,
            preview_max_bytes=120,
        )
        capture.add_line("x" * 1000)
        capture.finalize()

        assert len(capture.preview_lines) == 1
        preview = capture.preview_lines[0]
        assert str(preview["text"]).endswith("[preview line truncated]")
        assert len(json.dumps(list(capture.preview_lines)).encode("utf-8")) <= 122
        assert capture.preview_truncated is True
        assert capture.output_line_count == 1

    def test_full_output_artifact_round_trips_lines(self):
        capture = RunOutputCapture("test-run-output-artifact", preview_limit=2, persist_full_output=True, full_output_max_bytes=0)
        capture.add_line("alpha")
        capture.add_line("beta")
        capture.finalize()

        assert capture.full_output_available is True
        artifact_rel_path = capture.artifact_rel_path
        assert artifact_rel_path is not None
        assert load_full_output_lines(artifact_rel_path) == ["alpha", "beta"]
        assert load_full_output_entries(artifact_rel_path) == [
            {"text": "alpha", "cls": "", "tsC": "", "tsE": ""},
            {"text": "beta", "cls": "", "tsC": "", "tsE": ""},
        ]

    def test_full_output_artifact_round_trips_signal_metadata(self):
        capture = RunOutputCapture("test-run-output-signals", preview_limit=5, persist_full_output=True, full_output_max_bytes=0)
        capture.add_line(
            "443/tcp open https",
            signals=["findings"],
            line_index=0,
            command_root="nmap",
            target="ip.darklab.sh",
        )
        capture.finalize()

        expected = [{
            "text": "443/tcp open https",
            "cls": "",
            "tsC": "",
            "tsE": "",
            "signals": ["findings"],
            "line_index": 0,
            "command_root": "nmap",
            "target": "ip.darklab.sh",
        }]
        assert list(capture.preview_lines) == expected
        assert capture.artifact_rel_path is not None
        assert load_full_output_entries(capture.artifact_rel_path) == expected

    def test_full_output_artifact_respects_byte_cap(self):
        capture = RunOutputCapture("test-run-output-cap", preview_limit=10, persist_full_output=True, full_output_max_bytes=60)
        capture.add_line("1234")
        capture.add_line("5678")
        capture.finalize()

        assert capture.full_output_available is True
        assert capture.full_output_truncated is True
        artifact_rel_path = capture.artifact_rel_path
        assert artifact_rel_path is not None
        assert load_full_output_lines(artifact_rel_path) == ["1234"]

    def test_full_output_artifact_loads_legacy_plain_text_rows(self):
        artifact_rel_path = "test-run-output-legacy.txt.gz"
        path = os.path.join(RUN_OUTPUT_DIR, artifact_rel_path)
        os.makedirs(RUN_OUTPUT_DIR, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write("legacy one\nlegacy two\n")

        assert load_full_output_entries(artifact_rel_path) == [
            {"text": "legacy one", "cls": "", "tsC": "", "tsE": ""},
            {"text": "legacy two", "cls": "", "tsC": "", "tsE": ""},
        ]

    def test_missing_hints_file_returns_empty_list(self):
        with mock.patch("commands.APP_HINTS_FILE", "/nonexistent/app_hints.txt"):
            assert load_welcome_hints() == []

    def test_hints_loader_ignores_blank_lines_and_comments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# comment\n\nUse the history panel.\n  \n# another\nPress Enter to run.\n")
            path = f.name
        try:
            with mock.patch("commands.APP_HINTS_FILE", path):
                assert load_welcome_hints() == ["Use the history panel.", "Press Enter to run."]
        finally:
            os.unlink(path)

    def test_hints_loader_skips_workspace_section_when_disabled(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(
                "[general]\n"
                "Use the history panel.\n"
                "[workspace]\n"
                "Use Files to create targets.txt.\n"
                "[general]\n"
                "Press Enter to run.\n"
            )
            path = f.name
        try:
            with mock.patch("commands.APP_HINTS_FILE", path):
                assert load_welcome_hints({"workspace_enabled": False}) == [
                    "Use the history panel.",
                    "Press Enter to run.",
                ]
                assert load_welcome_hints({"workspace_enabled": True}) == [
                    "Use the history panel.",
                    "Use Files to create targets.txt.",
                    "Press Enter to run.",
                ]
        finally:
            os.unlink(path)


class TestMobileWelcomeHintLoading:
    def test_missing_mobile_hints_file_returns_empty_list(self):
        with mock.patch("commands.APP_HINTS_MOBILE_FILE", "/nonexistent/app_hints_mobile.txt"):
            assert load_mobile_welcome_hints() == []

    def test_mobile_hints_loader_ignores_blank_lines_and_comments(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# comment\n\nTap the prompt.\n  \n# another\nUse the mobile menu.\n")
            path = f.name
        try:
            with mock.patch("commands.APP_HINTS_MOBILE_FILE", path):
                assert load_mobile_welcome_hints() == ["Tap the prompt.", "Use the mobile menu."]
        finally:
            os.unlink(path)

    def test_mobile_hints_loader_skips_workspace_section_when_disabled(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(
                "Tap the prompt.\n"
                "[workspace]\n"
                "Use Files from the mobile menu.\n"
                "[general]\n"
                "Use the mobile menu.\n"
            )
            path = f.name
        try:
            with mock.patch("commands.APP_HINTS_MOBILE_FILE", path):
                assert load_mobile_welcome_hints({"workspace_enabled": False}) == [
                    "Tap the prompt.",
                    "Use the mobile menu.",
                ]
                assert load_mobile_welcome_hints({"workspace_enabled": True}) == [
                    "Tap the prompt.",
                    "Use Files from the mobile menu.",
                    "Use the mobile menu.",
                ]
        finally:
            os.unlink(path)


class TestAutocompleteContextLoading:
    def test_container_smoke_test_commands_include_registry_examples_and_workflows(self):
        registry_context = {
            "dig": {
                "examples": [
                    {"value": "dig darklab.sh A", "description": "A lookup"},
                    {"value": "dig darklab.sh MX", "description": "MX lookup"},
                ]
            },
            "curl": {
                "examples": [
                    {"value": "curl -I https://darklab.sh", "description": "Headers"},
                ]
            },
        }
        workflows = [
            {
                "title": "DNS",
                "steps": [
                    {"cmd": "dig darklab.sh MX", "note": "Duplicate on purpose"},
                    {"cmd": "host darklab.sh", "note": "Workflow-only command"},
                ],
            },
            {
                "title": "HTTP",
                "steps": [
                    {"cmd": "curl -I https://darklab.sh", "note": "Duplicate on purpose"},
                    {"cmd": "wget -S --spider https://darklab.sh", "note": "Workflow-only command"},
                ],
            },
        ]

        with mock.patch("commands.load_autocomplete_context_from_commands_registry", return_value=registry_context):
            with mock.patch("commands.load_all_workflows", return_value=workflows):
                result = load_container_smoke_test_commands()

        assert result == [
            "dig darklab.sh A",
            "curl -I https://darklab.sh",
            "dig darklab.sh MX",
            "host darklab.sh",
            "wget -S --spider https://darklab.sh",
        ]

    def test_container_smoke_test_commands_spread_sensitive_roots(self):
        registry_context = {
            "dig": {
                "examples": [
                    {"value": "dig darklab.sh A", "description": "A lookup"},
                    {"value": "dig darklab.sh MX", "description": "MX lookup"},
                    {"value": "dig darklab.sh NS", "description": "NS lookup"},
                ]
            },
            "whois": {
                "examples": [
                    {"value": "whois darklab.sh", "description": "Domain ownership"},
                    {"value": "whois 104.21.4.35", "description": "IP ownership"},
                ]
            },
            "curl": {
                "examples": [
                    {"value": "curl -I https://darklab.sh", "description": "Headers"},
                ]
            },
            "host": {
                "examples": [
                    {"value": "host darklab.sh", "description": "Host lookup"},
                ]
            },
        }

        with mock.patch("commands.load_autocomplete_context_from_commands_registry", return_value=registry_context):
            with mock.patch("commands.load_all_workflows", return_value=[]):
                result = load_container_smoke_test_commands()

        assert result == [
            "dig darklab.sh A",
            "curl -I https://darklab.sh",
            "whois darklab.sh",
            "host darklab.sh",
            "dig darklab.sh MX",
            "whois 104.21.4.35",
            "dig darklab.sh NS",
        ]
        for previous, current in zip(result, result[1:]):
            prev_root = previous.split()[0]
            curr_root = current.split()[0]
            assert prev_root != curr_root
        dig_positions = [idx for idx, command in enumerate(result) if command.startswith("dig ")]
        whois_positions = [idx for idx, command in enumerate(result) if command.startswith("whois ")]
        assert dig_positions == [0, 4, 6]
        assert whois_positions == [2, 5]

    def test_container_smoke_test_commands_render_workflow_defaults(self):
        with mock.patch("commands.load_autocomplete_context_from_commands_registry", return_value={}):
            with mock.patch(
                "commands.load_all_workflows",
                return_value=[
                    {
                        "title": "DNS",
                        "inputs": [
                            {
                                "id": "domain",
                                "type": "domain",
                                "default": "darklab.sh",
                            }
                        ],
                        "steps": [
                            {"cmd": "dig {{domain}} A", "note": "Rendered from default"},
                        ],
                    }
                ],
            ):
                result = load_container_smoke_test_commands()

        assert result == ["dig darklab.sh A"]

    def test_container_smoke_test_commands_skip_workspace_required_examples(self):
        registry_context = {
            "curl": {
                "examples": [
                    {"value": "curl -I https://ip.darklab.sh", "description": "Headers"},
                    {
                        "value": "curl -L -o response.html https://noc.darklab.sh",
                        "description": "Save response",
                        "feature_required": "workspace",
                    },
                ],
            },
            "nmap": {
                "examples": [
                    {
                        "value": "nmap -sT -iL targets.txt -p 80,443 --open -oN nmap-web.txt",
                        "description": "Workspace targets",
                        "feature_required": "workspace",
                    },
                ],
            },
        }

        with mock.patch(
            "commands.load_autocomplete_context_from_commands_registry",
            return_value=registry_context,
        ) as load_context:
            with mock.patch("commands.load_all_workflows", return_value=[]):
                result = load_container_smoke_test_commands()

        load_context.assert_called_once_with({"workspace_enabled": False})
        assert result == ["curl -I https://ip.darklab.sh"]


class TestWordlistCatalog:
    def test_load_wordlist_catalog_filters_and_sorts_curated_matches(self, tmp_path):
        root = tmp_path / "seclists"
        (root / "Discovery" / "DNS").mkdir(parents=True)
        (root / "Discovery" / "DNS" / "b.txt").write_text("beta\n")
        (root / "Discovery" / "DNS" / "a.txt").write_text("alpha\n")
        (root / "Discovery" / "DNS" / "README.md").write_text("docs\n")
        config_path = tmp_path / "wordlists.yaml"
        config_path.write_text(textwrap.dedent(f"""
        root: {root}
        categories:
          - key: dns
            label: DNS
            description: DNS lists
            include:
              - Discovery/DNS/*.txt
              - Discovery/DNS/README.md
        """))

        catalog = wordlists.load_wordlist_catalog(config_path=config_path)

        assert [item["relpath"] for item in catalog["items"]] == [
            "Discovery/DNS/a.txt",
            "Discovery/DNS/b.txt",
        ]
        assert catalog["items"][0]["category"] == "dns"
        assert catalog["items"][0]["path"].endswith("/Discovery/DNS/a.txt")

    def test_wordlist_catalog_search_path_and_all_scan(self, tmp_path):
        root = tmp_path / "seclists"
        (root / "Discovery" / "Web-Content").mkdir(parents=True)
        (root / "Passwords").mkdir(parents=True)
        (root / "Discovery" / "Web-Content" / "common.txt").write_text("admin\n")
        (root / "Passwords" / "top.txt").write_text("password\n")
        (root / "Passwords" / "archive.7z").write_text("compressed\n")
        config_path = tmp_path / "wordlists.yaml"
        config_path.write_text(textwrap.dedent(f"""
        root: {root}
        categories:
          - key: web-content
            label: Web Content
            include:
              - Discovery/Web-Content/common.txt
        """))

        catalog = wordlists.load_wordlist_catalog(config_path=config_path, include_all=True)
        matches = wordlists.filter_wordlists(catalog["items"], search="common")
        found = wordlists.find_wordlist("common.txt", catalog["items"])

        assert [item["name"] for item in matches] == ["common.txt"]
        assert found is not None
        assert found["relpath"] == "Discovery/Web-Content/common.txt"
        assert [item["relpath"] for item in catalog["all_items"]] == [
            "Discovery/Web-Content/common.txt",
            "Passwords/top.txt",
        ]

    def test_wordlist_catalog_missing_root_returns_empty_items(self, tmp_path):
        config_path = tmp_path / "wordlists.yaml"
        config_path.write_text(textwrap.dedent(f"""
        root: {tmp_path / "missing"}
        categories:
          - key: dns
            include:
              - Discovery/DNS/*.txt
        """))

        catalog = wordlists.load_wordlist_catalog(config_path=config_path)

        assert catalog["items"] == []
        assert catalog["categories"][0]["key"] == "dns"


class TestWorkflowInputLoading:
    def test_load_workflows_keeps_declared_inputs(self):
        payload = textwrap.dedent(
            """
            - title: "DNS Workflow"
              description: "Custom workflow"
              inputs:
                - id: domain
                  label: Domain
                  type: domain
                  required: true
                  placeholder: example.com
                  help: Use the fully qualified domain.
              steps:
                - cmd: "dig {{domain}} A"
                  note: "Check the answer section."
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflows.yaml"
            path.write_text(payload)
            with mock.patch("commands.WORKFLOWS_FILE", str(path)):
                result = load_workflows()

        assert result == [
            {
                "title": "DNS Workflow",
                "description": "Custom workflow",
                "inputs": [
                    {
                        "id": "domain",
                        "label": "Domain",
                        "type": "domain",
                        "required": True,
                        "placeholder": "example.com",
                        "default": "",
                        "help": "Use the fully qualified domain.",
                    }
                ],
                "steps": [
                    {"cmd": "dig {{domain}} A", "note": "Check the answer section."},
                ],
            }
        ]

    def test_load_workflows_drops_steps_with_undeclared_tokens(self):
        payload = textwrap.dedent(
            """
            - title: "Broken workflow"
              description: "Unknown token"
              inputs:
                - id: host
                  type: host
                  required: true
              steps:
                - cmd: "ping {{host}}"
                - cmd: "dig {{domain}} A"
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflows.yaml"
            path.write_text(payload)
            with mock.patch("commands.WORKFLOWS_FILE", str(path)):
                result = load_workflows()

        assert result == [
            {
                "title": "Broken workflow",
                "description": "Unknown token",
                "inputs": [
                    {
                        "id": "host",
                        "label": "Host",
                        "type": "host",
                        "required": True,
                        "placeholder": "",
                        "default": "",
                        "help": "",
                    }
                ],
                "steps": [
                    {"cmd": "ping {{host}}", "note": ""},
                ],
            }
        ]

    def test_load_all_workflows_filters_workspace_required_workflows(self):
        disabled = load_all_workflows({"workspace_enabled": False})
        enabled = load_all_workflows({"workspace_enabled": True})

        disabled_titles = {item["title"] for item in disabled}
        enabled_titles = {item["title"] for item in enabled}

        assert "Subdomain HTTP Triage" not in disabled_titles
        assert "Crawl And Scan" not in disabled_titles
        assert "Subdomain HTTP Triage" in enabled_titles
        assert "Crawl And Scan" in enabled_titles

        subdomain = next(item for item in enabled if item["title"] == "Subdomain HTTP Triage")
        assert subdomain["feature_required"] == "workspace"
        assert [step["cmd"] for step in subdomain["steps"]] == [
            "subfinder -d {{domain}} -silent -o subdomains.txt",
            "pd-httpx -l subdomains.txt -silent -o live-urls.txt",
            "pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt",
        ]


class TestSeedHistoryFixtures:
    def test_visual_flows_fixture_only_stars_two_commands(self):
        seed_history = _load_seed_history_module()

        assert seed_history.VISUAL_HISTORY_FIXTURES["visual-flows"]["star"] == 2

    def test_seed_history_uses_runtime_command_registry_examples(self):
        seed_history = _load_seed_history_module()
        commands_from_seed = seed_history._load_autocomplete_example_commands()

        expected_examples = []
        seen = set()
        for spec in load_autocomplete_context_from_commands_registry().values():
            if not isinstance(spec, dict):
                continue
            for example in spec.get("examples") or []:
                if not isinstance(example, dict):
                    continue
                value = str(example.get("value") or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                expected_examples.append(value)

        assert commands_from_seed == expected_examples
        assert "bogus-command" not in commands_from_seed

    def test_seed_runs_avoids_adjacent_duplicate_commands(self):
        seed_history = _load_seed_history_module()

        class _FakeConn:
            def executemany(self, *_args, **_kwargs):
                return None

            def commit(self):
                return None

        @contextmanager
        def _fake_db_connect():
            yield _FakeConn()

        command_pool = [
            "dig darklab.sh +short",
            "curl -I https://ip.darklab.sh",
            "ping -c 4 darklab.sh",
        ]

        with mock.patch.object(
            seed_history,
            "_load_autocomplete_example_commands",
            return_value=command_pool,
        ), mock.patch.object(seed_history, "db_connect", _fake_db_connect):
            seeded_commands = seed_history.seed_runs(
                "tok_deadbeefdeadbeefdeadbeefdeadbeef",
                40,
                7,
                random.Random(4242),
            )

        assert len(seeded_commands) == 40
        assert all(
            current != previous
            for previous, current in zip(seeded_commands, seeded_commands[1:])
        )


# ── rewrite_command idempotency ───────────────────────────────────────────────

class TestRewriteIdempotent:
    def test_mtr_already_report_wide_unchanged(self):
        cmd, notice = rewrite_command("mtr --report-wide google.com")
        assert "--report-wide --report-wide" not in cmd
        assert notice is None

    def test_mtr_report_flag_unchanged(self):
        cmd, notice = rewrite_command("mtr --report google.com")
        assert "--report-wide" not in cmd
        assert notice is None

    def test_nmap_already_connect_scan_unchanged(self):
        cmd, _ = rewrite_command("nmap -sT -sV 10.0.0.1")
        assert cmd.count("-sT") == 1

    def test_nuclei_already_ud_unchanged(self):
        cmd, _ = rewrite_command("nuclei -ud /my/templates -u https://darklab.sh")
        assert cmd.count("-ud") == 1

# ── _expiry_note ──────────────────────────────────────────────────────────────

class TestExpiryNote:
    def test_returns_empty_when_retention_zero(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0}):
            result = _expiry_note("2024-01-01T00:00:00+00:00")
        assert result == ""

    def test_returns_expiry_text_when_not_expired(self):
        # Created 5 days ago, retention 30 days → ~25 days remaining
        created = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 30}):
            result = _expiry_note(created)
        assert "expires in" in result
        assert "days" in result

    def test_returns_expires_today_when_less_than_24h(self):
        # Created just under retention_days ago so < 24 h remains
        created = (datetime.now(timezone.utc) - timedelta(days=6, hours=23)).isoformat()
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 7}):
            result = _expiry_note(created)
        assert "expires today" in result

    def test_returns_empty_when_already_expired(self):
        # Created longer ago than retention
        created = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 30}):
            result = _expiry_note(created)
        assert result == ""

    def test_returns_empty_on_invalid_date(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 30}):
            result = _expiry_note("not-a-date")
        assert result == ""

    def test_includes_expiry_date(self):
        created = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 30}):
            result = _expiry_note(created)
        # Should include a YYYY-MM-DD formatted date
        import re
        assert re.search(r'\d{4}-\d{2}-\d{2}', result)


# ── _prompt_echo_text + synthesized prompt-echo lines ────────────────────────

class TestPromptEchoText:
    def test_uses_configured_prompt_identity(self):
        with mock.patch.dict("permalinks.CFG", {"prompt_username": "ops", "prompt_domain": "darklab"}):
            assert _prompt_echo_text("ls -la") == "ops@darklab:~ $ ls -la"

    def test_falls_back_to_default_identity_when_parts_are_missing(self):
        with mock.patch.dict("permalinks.CFG", {"prompt_username": "", "prompt_domain": ""}):
            assert _prompt_echo_text("ls -la") == "anon@darklab.sh:~ $ ls -la"

    def test_strips_trailing_space_when_label_empty(self):
        with mock.patch.dict("permalinks.CFG", {"prompt_username": "anon", "prompt_domain": "darklab.sh"}):
            assert _prompt_echo_text("") == "anon@darklab.sh:~ $"


class TestNormalizePermalinkLinesPromptEcho:
    """Regression guard: when a history snapshot does not already carry a
    prompt-echo line, the normalizer synthesizes one using the configured
    prompt identity — not a reduced bare `$` — so permalink pages render the
    same prompt identity as the live shell."""

    def test_unstructured_content_uses_configured_prefix(self):
        with mock.patch.dict("permalinks.CFG", {"prompt_username": "ops", "prompt_domain": "darklab"}):
            lines = _normalize_permalink_lines(["hello", "world"], label="echo hello")
        assert lines[0]["cls"] == "prompt-echo"
        assert lines[0]["text"] == "ops@darklab:~ $ echo hello"

    def test_structured_snapshot_without_echo_gets_configured_prefix(self):
        content = [
            {"text": "hello", "cls": "", "tsC": "", "tsE": ""},
            {"text": "[process exited with code 0 in 0.1s]", "cls": "exit-ok"},
        ]
        with mock.patch.dict("permalinks.CFG", {"prompt_username": "ops", "prompt_domain": "darklab"}):
            lines = _normalize_permalink_lines(content, label="echo hello")
        assert lines[0]["cls"] == "prompt-echo"
        assert lines[0]["text"] == "ops@darklab:~ $ echo hello"

    def test_structured_snapshot_with_existing_echo_is_preserved(self):
        content = [
            {"text": "anon@darklab:~$ echo hello", "cls": "prompt-echo"},
            {"text": "hello", "cls": ""},
        ]
        with mock.patch.dict("permalinks.CFG", {"prompt_username": "ops", "prompt_domain": "darklab"}):
            lines = _normalize_permalink_lines(content, label="echo hello")
        # Existing echo survives; normalizer does not prepend a second one.
        echo_lines = [entry for entry in lines if entry["cls"] == "prompt-echo"]
        assert len(echo_lines) == 1
        assert echo_lines[0]["text"] == "anon@darklab:~$ echo hello"


# ── _permalink_error_page ─────────────────────────────────────────────────────

class TestPermalinkErrorPage:
    def test_returns_404_status(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "testshell"}):
            with shell_app.app.app_context():
                resp = _permalink_error_page("snapshot")
        assert resp.status_code == 404

    def test_includes_noun_in_body(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "testshell"}):
            with shell_app.app.app_context():
                resp = _permalink_error_page("run")
        assert b"run" in resp.data

    def test_includes_app_name(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "my-shell"}):
            with shell_app.app.app_context():
                resp = _permalink_error_page("snapshot")
        assert b"my-shell" in resp.data

    def test_mentions_retention_when_configured(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 30, "app_name": "testshell"}):
            with shell_app.app.app_context():
                resp = _permalink_error_page("snapshot")
        assert b"30 days" in resp.data or b"1 month" in resp.data

    def test_no_retention_mention_when_unlimited(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "testshell"}):
            with shell_app.app.app_context():
                resp = _permalink_error_page("snapshot")
        # Unlimited mode should not mention an automatic deletion period
        assert b"retention" not in resp.data.lower()


# ── database init and pruning ─────────────────────────────────────────────────

class TestDatabaseInit:
    def _fresh_db(self, tmp):
        """Return a path to a new empty DB file in tmp."""
        return os.path.join(tmp, "test.db")

    def _create_tables(self, db_path):
        with mock.patch("database.DB_PATH", db_path):
            with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                database.db_init()

    def test_creates_runs_and_snapshots_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            conn = sqlite3.connect(db_path)
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            conn.close()
        assert "runs" in tables
        assert "snapshots" in tables
        assert "session_variables" in tables

    def test_creates_session_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()
            conn = sqlite3.connect(db_path)
            indexes = {row[1] for row in conn.execute("PRAGMA index_list('runs')").fetchall()}
            snapshot_indexes = {row[1] for row in conn.execute("PRAGMA index_list('snapshots')").fetchall()}
            workflow_indexes = {
                row[1] for row in conn.execute("PRAGMA index_list('user_workflows')").fetchall()
            }
            conn.close()

        assert "idx_session" in indexes
        assert "idx_runs_session_started" in indexes
        assert "idx_runs_session_command_started" in indexes
        assert "idx_snapshots_session" in snapshot_indexes
        assert "idx_snapshots_session_created" in snapshot_indexes
        assert "idx_user_workflows_session_updated_created" in workflow_indexes

    def test_init_is_idempotent(self):
        # Calling db_init() twice on the same DB must not raise
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()  # second call

    def test_retention_prunes_old_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            # Insert a run timestamped 100 days ago
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) "
                "VALUES ('old-run', 'sess', 'ping', datetime('now', '-100 days'))"
            )
            conn.commit()
            conn.close()
            # Re-init with 30-day retention — old run should be pruned
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 30}):
                    database.db_init()
            conn = sqlite3.connect(db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE id='old-run'"
            ).fetchone()[0]
            conn.close()
        assert count == 0

    def test_retention_prunes_old_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) "
                "VALUES ('old-snap', 'sess', 'lbl', datetime('now', '-50 days'), '[]')"
            )
            conn.commit()
            conn.close()
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 30}):
                    database.db_init()
            conn = sqlite3.connect(db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM snapshots WHERE id='old-snap'"
            ).fetchone()[0]
            conn.close()
        assert count == 0

    def test_zero_retention_does_not_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) "
                "VALUES ('keep-run', 'sess', 'ping', datetime('now', '-100 days'))"
            )
            conn.commit()
            conn.close()
            # Re-init with retention=0 — nothing should be pruned
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()
            conn = sqlite3.connect(db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE id='keep-run'"
            ).fetchone()[0]
            conn.close()
        assert count == 1

    def test_recent_runs_not_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            self._create_tables(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) "
                "VALUES ('recent-run', 'sess', 'ping', datetime('now', '-5 days'))"
            )
            conn.commit()
            conn.close()
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 30}):
                    database.db_init()
            conn = sqlite3.connect(db_path)
            count = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE id='recent-run'"
            ).fetchone()[0]
            conn.close()
        assert count == 1

    def test_legacy_runs_table_gets_session_id_column_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = self._fresh_db(tmp)
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE runs (
                    id       TEXT PRIMARY KEY,
                    command  TEXT NOT NULL,
                    started  TEXT NOT NULL,
                    finished TEXT,
                    exit_code INTEGER,
                    output   TEXT
                )
            """)
            conn.execute(
                "INSERT INTO runs (id, command, started) VALUES ('legacy-run', 'ping', datetime('now'))"
            )
            conn.commit()
            conn.close()

            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()

            conn = sqlite3.connect(db_path)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
            session_id = conn.execute(
                "SELECT session_id FROM runs WHERE id='legacy-run'"
            ).fetchone()[0]
            conn.close()

        assert "session_id" in columns
        assert session_id == ""

    def test_migrate_schema_ignores_existing_column_error(self):
        conn = mock.MagicMock()
        conn.execute.side_effect = sqlite3.OperationalError("duplicate column name: session_id")

        database._migrate_schema(conn)

        assert conn.execute.call_count >= 1
        assert conn.execute.call_args_list[0].args[0] == "ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''"


class TestSessionVariables:
    def test_set_list_unset_and_expand_variables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "vars.db")
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()
                session_variables.set_session_variable("sess-vars", "HOST", "ip.darklab.sh")
                session_variables.set_session_variable("sess-vars", "PORT", "443")
                expansion = session_variables.expand_session_variables(
                    "openssl s_client -connect ${HOST}:$PORT",
                    "sess-vars",
                )
                assert expansion.command == "openssl s_client -connect ip.darklab.sh:443"
                assert expansion.used_names == ("HOST", "PORT")
                quoted = session_variables.expand_session_variables(
                    "curl 'https://$HOST'",
                    "sess-vars",
                )
                assert quoted.command == "curl 'https://ip.darklab.sh'"
                assert session_variables.list_session_variables("sess-vars") == {
                    "HOST": "ip.darklab.sh",
                    "PORT": "443",
                }
                assert session_variables.unset_session_variable("sess-vars", "PORT") is True
                assert session_variables.unset_session_variable("sess-vars", "PORT") is False

    def test_rejects_invalid_names_and_undefined_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "vars.db")
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()
                with pytest.raises(session_variables.InvalidSessionVariableName):
                    session_variables.set_session_variable("sess-vars", "host", "ip.darklab.sh")
                with pytest.raises(session_variables.UndefinedSessionVariable):
                    session_variables.expand_session_variables("curl https://$HOST", "sess-vars")
                with pytest.raises(session_variables.InvalidSessionVariableReference):
                    session_variables.expand_session_variables("curl https://${HOST:-darklab.sh}", "sess-vars")


class TestBuiltinStatus:
    def test_includes_session_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "status.db")
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()

            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                ("run-1", "tok_statusdemo", "ping darklab.sh"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                ("run-2", "tok_statusdemo", "curl darklab.sh"),
            )
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, datetime('now'), ?)",
                ("snap-1", "tok_statusdemo", "demo snapshot", "[]"),
            )
            conn.execute(
                "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                ("tok_statusdemo", "ping darklab.sh"),
            )
            conn.execute(
                "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, datetime('now'))",
                ("tok_statusdemo", '{"theme":"matrix"}'),
            )
            conn.commit()
            conn.close()

            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("builtin_commands.active_runs_for_session", return_value=[{"id": "job-1"}]):
                    with mock.patch("builtin_commands.redis_client", None):
                        lines = builtin_commands._run_builtin_status("tok_statusdemo")

        text = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", line["text"]) for line in lines)
        assert re.search(r"session\s+tok_stat••••", text)
        assert "tok_statusdemo" not in text
        assert re.search(r"session type\s+session token", text)
        assert re.search(r"database\s+online", text)
        assert re.search(r"redis\s+n/a", text)
        assert re.search(r"runs in session\s+2", text)
        assert re.search(r"snapshots\s+1", text)
        assert re.search(r"starred commands\s+1", text)
        assert re.search(r"saved options\s+yes", text)
        assert re.search(r"active runs\s+1", text)


class TestBuiltinStats:
    def test_reports_session_activity_and_command_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "stats.db")
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()

            conn = sqlite3.connect(db_path)
            runs = [
                (
                    "run-1",
                    "tok_statsdemo",
                    "nmap -sV ip.darklab.sh",
                    "2026-01-01 00:00:00",
                    "2026-01-01 00:00:10",
                    0,
                ),
                (
                    "run-2",
                    "tok_statsdemo",
                    "nmap -p 443 ip.darklab.sh",
                    "2026-01-01 00:01:00",
                    "2026-01-01 00:01:20",
                    1,
                ),
                (
                    "run-3",
                    "tok_statsdemo",
                    "dig darklab.sh",
                    "2026-01-01 00:02:00",
                    "2026-01-01 00:02:02",
                    0,
                ),
                (
                    "run-4",
                    "tok_statsdemo",
                    "curl https://darklab.sh",
                    "2026-01-01 00:03:00",
                    None,
                    None,
                ),
                (
                    "run-5",
                    "tok_statsdemo",
                    "status",
                    "2026-01-01 00:03:30",
                    "2026-01-01 00:03:31",
                    0,
                ),
                (
                    "run-6",
                    "tok_statsdemo",
                    "sslscan ip.darklab.sh",
                    "2026-01-01 00:04:00",
                    "2026-01-01 00:05:23",
                    0,
                ),
                (
                    "run-7",
                    "tok_statsdemo",
                    "ping ip.darklab.sh",
                    "2026-01-01 00:05:30",
                    "2026-01-01 00:05:45",
                    -15,
                ),
                (
                    "other-session-run",
                    "tok_other",
                    "whois darklab.sh",
                    "2026-01-01 00:06:00",
                    "2026-01-01 00:06:01",
                    0,
                ),
            ]
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code) VALUES (?, ?, ?, ?, ?, ?)",
                runs,
            )
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, datetime('now'), ?)",
                ("snap-1", "tok_statsdemo", "demo snapshot", "[]"),
            )
            conn.execute(
                "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                ("tok_statsdemo", "nmap -sV ip.darklab.sh"),
            )
            conn.commit()
            conn.close()

            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("builtin_commands.active_runs_for_session", return_value=[{"id": "job-1"}]):
                    lines = builtin_commands._run_builtin_stats("tok_statsdemo")

        text = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", line["text"]) for line in lines)
        assert re.search(r"session\s+tok_stat••••", text)
        assert "tok_statsdemo" not in text
        assert re.search(r"runs\s+7", text)
        assert re.search(r"snapshots\s+1", text)
        assert re.search(r"starred commands\s+1", text)
        assert re.search(r"active runs\s+1", text)
        assert re.search(r"success rate\s+80% \(4 ok / 1 failed\)", text)
        assert re.search(r"average duration\s+21\.[78]s", text)
        assert "  command      runs         ok       avg" in text
        assert "  nmap       2 runs     50% ok     15.0s" in text
        assert "  dig         1 run    100% ok      2.0s" in text
        assert "  curl        1 run     n/a ok       n/a" in text
        assert "  sslscan     1 run    100% ok    1m 23s" in text
        assert "  ping        1 run     n/a ok     15.0s" in text
        assert "incomplete" not in text
        assert not re.search(r"status\s+1 run", text)
        assert "whois" not in text

    def test_top_commands_empty_state_ignores_builtin_only_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "stats-builtin-only.db")
            with mock.patch("database.DB_PATH", db_path):
                with mock.patch("database.CFG", {"permalink_retention_days": 0}):
                    database.db_init()

            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "run-1",
                    "tok_builtinonly",
                    "status",
                    "2026-01-01 00:00:00",
                    "2026-01-01 00:00:01",
                    0,
                ),
            )
            conn.commit()
            conn.close()

            with mock.patch("database.DB_PATH", db_path):
                lines = builtin_commands._run_builtin_stats("tok_builtinonly")

        text = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", line["text"]) for line in lines)
        assert re.search(r"runs\s+1", text)
        assert re.search(r"success rate\s+100% \(1 ok / 0 failed\)", text)
        assert "No external tool runs for this session yet." in text
        assert not re.search(r"status\s+1 run", text)
