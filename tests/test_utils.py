"""
Tests for pure utility functions across the app modules:
  - split_chained_commands      (commands.py)
  - load_allowed_commands       (commands.py)
  - load_faq                    (commands.py)
  - _is_denied edge cases       (commands.py)
  - is_command_allowed path-blocking edge cases (commands.py)
  - rewrite_command case-insensitivity          (commands.py)
  - pid_register / pid_pop in-process mode      (process.py)
  - _format_retention                           (permalinks.py)
Run with: pytest tests/ (from the repo root)
"""

import sys
import os
import tempfile
import textwrap
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import process
import commands  # noqa: F401 — used as mock.patch("commands.X") target
from commands import (
    split_chained_commands, load_allowed_commands, load_faq,
    is_command_allowed, rewrite_command,
)
from permalinks import _format_retention


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
        parts = split_chained_commands("curl example.com < /etc/hosts")
        assert len(parts) == 2

    def test_empty_parts_stripped(self):
        # Splitting "a | " should not produce an empty trailing element
        parts = split_chained_commands("a | ")
        assert all(p for p in parts)


# ── load_allowed_commands ─────────────────────────────────────────────────────

class TestLoadAllowedCommands:
    def _write(self, content, tmp_path):
        path = os.path.join(tmp_path, "allowed_commands.txt")
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def test_missing_file_returns_none_and_empty_deny(self):
        with mock.patch("commands.ALLOWED_COMMANDS_FILE", "/nonexistent/path.txt"):
            allow, deny = load_allowed_commands()
        assert allow is None
        assert deny == []

    def test_allow_entries_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("ping\nnmap\ndig\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                allow, deny = load_allowed_commands()
        assert allow == ["ping", "nmap", "dig"]
        assert deny == []

    def test_deny_entries_stripped_of_bang_and_lowercased(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("ping\n!NMAP -SU\n!curl -o\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                allow, deny = load_allowed_commands()
        assert "ping" in allow
        assert "nmap -su" in deny
        assert "curl -o" in deny

    def test_comments_and_blank_lines_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("# comment\n\nping\n  \n# another\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                allow, deny = load_allowed_commands()
        assert allow == ["ping"]

    def test_only_deny_entries_returns_none_allow(self):
        # File with only ! lines → no allow prefixes → unrestricted
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("!nmap -su\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                allow, deny = load_allowed_commands()
        assert allow is None
        assert deny == ["nmap -su"]

    def test_allow_entries_are_lowercased(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("PING\nNMAP\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                allow, _ = load_allowed_commands()
        assert "ping" in allow
        assert "nmap" in allow

    def test_empty_file_returns_none_allow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                allow, deny = load_allowed_commands()
        assert allow is None
        assert deny == []


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


# ── Path blocking edge cases ──────────────────────────────────────────────────

def _check(cmd, allow=None, deny=None):
    a = allow if allow is not None else ["curl", "nmap", "ls"]
    d = deny if deny is not None else []
    with mock.patch("commands.load_allowed_commands", return_value=(a, d)):
        return is_command_allowed(cmd)


class TestPathBlockingEdgeCases:
    def test_tmp_at_end_of_command(self):
        ok, _ = _check("ls /tmp")
        assert not ok

    def test_tmp_with_subdirectory(self):
        ok, _ = _check("curl /tmp/secret.txt")
        assert not ok

    def test_tmp_in_url_path_allowed(self):
        ok, _ = _check("curl https://example.com/tmp/file")
        assert ok

    def test_tmp_in_url_with_port_allowed(self):
        ok, _ = _check("curl https://example.com:8080/tmp/resource")
        assert ok

    def test_data_path_blocked(self):
        ok, _ = _check("curl /data/history.db")
        assert not ok

    def test_data_in_url_path_allowed(self):
        ok, _ = _check("curl https://example.com/data/file")
        assert ok

    def test_tmp_as_scheme_relative_blocked(self):
        # Ensure /tmp/... with no scheme is blocked regardless of position
        ok, _ = _check("nmap -sV /tmp/targets.txt")
        assert not ok


# ── _is_denied: multi-word tool prefix ───────────────────────────────────────

class TestIsDeniedMultiWordTool:
    def test_subcommand_specific_deny(self):
        # "gobuster dir -o" deny should NOT fire for "gobuster dns ..."
        ok, _ = _check("gobuster dns -d example.com", allow=["gobuster"], deny=["gobuster dir -o"])
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


# ── rewrite_command: case insensitivity ──────────────────────────────────────

class TestRewriteCaseInsensitive:
    def test_mtr_uppercase(self):
        cmd, notice = rewrite_command("MTR google.com")
        assert "--report-wide" in cmd
        assert notice is not None

    def test_nmap_uppercase(self):
        cmd, _ = rewrite_command("NMAP -sV 10.0.0.1")
        assert "--privileged" in cmd

    def test_nuclei_uppercase(self):
        cmd, _ = rewrite_command("NUCLEI -u https://example.com")
        assert "-ud /tmp/nuclei-templates" in cmd

    def test_wapiti_uppercase(self):
        cmd, notice = rewrite_command("WAPITI http://example.com")
        assert "/dev/stdout" in cmd
        assert notice is not None


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
