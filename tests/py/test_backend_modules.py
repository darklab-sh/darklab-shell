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
  - run-output artifact capture/read helpers    (run_output_store.py)
Run with: pytest tests/ (from the repo root)
"""

import gzip
import os
import sqlite3
import tempfile
import textwrap
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import process
import database
import app as shell_app
import config as app_config
import commands  # noqa: F401 — used as mock.patch("commands.X") target
from commands import (
    split_chained_commands, load_allowed_commands, load_all_faq, load_faq,
    load_welcome, load_ascii_art, load_ascii_mobile_art, load_welcome_hints,
    load_mobile_welcome_hints, load_autocomplete,
    load_allowed_commands_grouped,
    is_command_allowed, rewrite_command,
)
from permalinks import _format_retention, _expiry_note, _permalink_error_page
from run_output_store import RunOutputCapture, RUN_OUTPUT_DIR, load_full_output_entries, load_full_output_lines


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


# ── load_allowed_commands ─────────────────────────────────────────────────────

class TestLoadConfig:
    def test_local_config_overrides_base_config_without_replacing_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "config.yaml")
            local_path = os.path.join(tmp, "config.local.yaml")
            with open(base_path, "w") as f:
                f.write(textwrap.dedent(
                    """
                    app_name: base-shell
                    project_readme: https://example.invalid/base.md
                    prompt_prefix: base@local:~$
                    default_theme: base-theme.yaml
                    rate_limit_per_minute: 30
                    """
                ))
            with open(local_path, "w") as f:
                f.write(textwrap.dedent(
                    """
                    app_name: local-shell
                    prompt_prefix: local@local:~$
                    project_readme: https://example.invalid/local.md
                    rate_limit_per_minute: 99
                    """
                ))
            cfg = app_config.load_config(tmp)

        assert cfg["app_name"] == "local-shell"
        assert cfg["prompt_prefix"] == "local@local:~$"
        assert cfg["project_readme"] == "https://example.invalid/local.md"
        assert cfg["default_theme"] == "base-theme.yaml"
        assert cfg["rate_limit_per_minute"] == 99
        assert cfg["trusted_proxy_cidrs"] == ["127.0.0.1/32", "::1/128"]

class TestLoadAllowedCommands:
    def _write(self, content, tmp_dir):
        path = os.path.join(tmp_dir, "allowed_commands.txt")
        with open(path, "w") as f:
            f.write(textwrap.dedent(content))
        return path

    def _write_local(self, content, tmp_dir):
        path = os.path.join(tmp_dir, "allowed_commands.local.txt")
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

    def test_local_overlay_appends_and_dedupes_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = self._write("ping\nnmap\n!curl -o\n", tmp)
            self._write_local("nmap\ncurl\n!curl -o\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", base_path):
                allow, deny = load_allowed_commands()
        assert allow == ["ping", "nmap", "curl"]
        assert deny == ["curl -o"]

    def test_local_overlay_merges_group_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = self._write("## Network\nping\n", tmp)
            self._write_local("## Network\ncurl\n## Scanning\nnmap\n", tmp)
            with mock.patch("commands.ALLOWED_COMMANDS_FILE", base_path):
                groups = load_allowed_commands_grouped()
        assert groups is not None
        assert [group["name"] for group in groups] == ["Network", "Scanning"]
        assert groups[0]["commands"] == ["ping", "curl"]
        assert groups[1]["commands"] == ["nmap"]


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


# ── load_theme_registry / load_theme ─────────────────────────────────────────

class TestThemeRegistry:
    def _write_theme(self, root, name, content):
        theme_dir = root / "themes"
        theme_dir.mkdir(parents=True, exist_ok=True)
        path = theme_dir / f"{name}.yaml"
        path.write_text(textwrap.dedent(content))
        return theme_dir, path

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

    def test_load_all_faq_appends_custom_entries_after_builtin_items(self):
        yaml_content = "- question: Custom question?\n  answer: Custom answer.\n"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name
        try:
            with mock.patch("commands.FAQ_FILE", path):
                result = load_all_faq("darklab shell", "https://example.invalid/README.md")
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
                result = load_all_faq("darklab shell", "https://example.invalid/README.md")
        finally:
            os.unlink(path)
        assert "https://example.invalid/README.md" in result[0]["answer_html"]


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
        cmd, _ = rewrite_command("NUCLEI -u https://darklab.sh")
        assert "-ud /tmp/nuclei-templates" in cmd

    def test_wapiti_uppercase(self):
        cmd, notice = rewrite_command("WAPITI http://darklab.sh")
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

    def test_local_overlay_appends_unique_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_path = os.path.join(tmp, "auto_complete.txt")
            local_path = os.path.join(tmp, "auto_complete.local.txt")
            with open(base_path, "w") as f:
                f.write("nmap -sV\nping -c 4\n")
            with open(local_path, "w") as f:
                f.write("ping -c 4\ncurl http://localhost:5001/health\n")
            with mock.patch("commands.AUTOCOMPLETE_FILE", base_path):
                result = load_autocomplete()
        assert result == ["nmap -sV", "ping -c 4", "curl http://localhost:5001/health"]


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
        cmd, _ = rewrite_command("nuclei -ud /my/templates -u https://darklab.sh")
        assert cmd.count("-ud") == 1

    def test_wapiti_already_output_unchanged(self):
        cmd, notice = rewrite_command("wapiti -u http://darklab.sh -o /tmp/report")
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
            conn.close()

        assert "idx_session" in indexes
        assert "idx_snapshots_session" in snapshot_indexes

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
