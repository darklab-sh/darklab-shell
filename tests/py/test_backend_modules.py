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

import os
import sqlite3
import tempfile
import textwrap
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import process
import database
import commands  # noqa: F401 — used as mock.patch("commands.X") target
from commands import (
    split_chained_commands, load_allowed_commands, load_faq,
    load_welcome, load_autocomplete, load_allowed_commands_grouped,
    is_command_allowed, rewrite_command,
)
from permalinks import _format_retention, _expiry_note, _permalink_error_page


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

    def test_empty_string_returns_empty_list(self):
        assert split_chained_commands("") == []


# ── load_allowed_commands ─────────────────────────────────────────────────────

class TestLoadAllowedCommands:
    def _write(self, content, tmp_dir):
        path = os.path.join(tmp_dir, "allowed_commands.txt")
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
        assert allow is not None
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
        assert allow is not None
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


# ── load_autocomplete ─────────────────────────────────────────────────────────

class TestAutocompleteLoading:
    def test_missing_file_returns_empty_list(self):
        with mock.patch("commands.AUTOCOMPLETE_FILE", "/nonexistent/auto_complete.txt"):
            result = load_autocomplete()
        assert result == []

    def test_valid_entries_returned(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("nmap -sV\nping -c 4\ndig @1.1.1.1\n")
            path = f.name
        try:
            with mock.patch("commands.AUTOCOMPLETE_FILE", path):
                result = load_autocomplete()
        finally:
            os.unlink(path)
        assert result == ["nmap -sV", "ping -c 4", "dig @1.1.1.1"]

    def test_comment_lines_filtered(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# this is a comment\nnmap -sV\n# another comment\n")
            path = f.name
        try:
            with mock.patch("commands.AUTOCOMPLETE_FILE", path):
                result = load_autocomplete()
        finally:
            os.unlink(path)
        assert result == ["nmap -sV"]

    def test_blank_lines_filtered(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("ping -c 4\n\n\ndig google.com\n")
            path = f.name
        try:
            with mock.patch("commands.AUTOCOMPLETE_FILE", path):
                result = load_autocomplete()
        finally:
            os.unlink(path)
        assert result == ["ping -c 4", "dig google.com"]


# ── load_allowed_commands_grouped ─────────────────────────────────────────────

class TestAllowedCommandsGroupingBasics:
    def _write(self, content, tmp_dir):
        path = os.path.join(tmp_dir, "allowed_commands.txt")
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def test_missing_file_returns_none(self):
        with mock.patch("commands.ALLOWED_COMMANDS_FILE", "/nonexistent/path.txt"):
            result = load_allowed_commands_grouped()
        assert result is None

    def test_commands_grouped_by_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                "## Network\nping\ncurl\n## Scanning\nnmap\n", tmp
            )
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                result = load_allowed_commands_grouped()
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "Network"
        assert result[0]["commands"] == ["ping", "curl"]
        assert result[1]["name"] == "Scanning"
        assert result[1]["commands"] == ["nmap"]

    def test_commands_without_header_get_empty_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("ping\nnmap\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                result = load_allowed_commands_grouped()
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == ""
        assert "ping" in result[0]["commands"]

    def test_deny_entries_excluded_from_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("## Scanning\nnmap\n!nmap -sU\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                result = load_allowed_commands_grouped()
        assert result is not None
        commands_list = result[0]["commands"]
        assert "nmap" in commands_list
        assert "!nmap -su" not in commands_list
        assert all(not c.startswith("!") for c in commands_list)

    def test_empty_groups_filtered_out(self):
        # A header with only deny entries under it produces no commands → excluded
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("## Empty\n!nmap -sU\n## Real\nping\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                result = load_allowed_commands_grouped()
        assert result is not None
        names = [g["name"] for g in result]
        assert "Empty" not in names
        assert "Real" in names

    def test_empty_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write("", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", path):
                result = load_allowed_commands_grouped()
        assert result is None


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

    def test_nmap_already_privileged_unchanged(self):
        cmd, _ = rewrite_command("nmap --privileged -sV 10.0.0.1")
        assert cmd.count("--privileged") == 1

    def test_nuclei_already_ud_unchanged(self):
        cmd, _ = rewrite_command("nuclei -ud /my/templates -u https://example.com")
        assert cmd.count("-ud") == 1

    def test_wapiti_already_output_unchanged(self):
        cmd, notice = rewrite_command("wapiti -u http://example.com -o /tmp/report")
        assert "/dev/stdout" not in cmd
        assert notice is None


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


# ── _permalink_error_page ─────────────────────────────────────────────────────

class TestPermalinkErrorPage:
    def test_returns_404_status(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "testshell"}):
            resp = _permalink_error_page("snapshot")
        assert resp.status_code == 404

    def test_includes_noun_in_body(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "testshell"}):
            resp = _permalink_error_page("run")
        assert b"run" in resp.data

    def test_includes_app_name(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "my-shell"}):
            resp = _permalink_error_page("snapshot")
        assert b"my-shell" in resp.data

    def test_mentions_retention_when_configured(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 30, "app_name": "testshell"}):
            resp = _permalink_error_page("snapshot")
        assert b"30 days" in resp.data or b"1 month" in resp.data

    def test_no_retention_mention_when_unlimited(self):
        with mock.patch("permalinks.CFG", {"permalink_retention_days": 0, "app_name": "testshell"}):
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
