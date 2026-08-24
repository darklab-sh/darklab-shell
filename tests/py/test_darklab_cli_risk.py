# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest
from darklab_cli_test_support import install_cli_harness


@pytest.fixture
def cli_harness(monkeypatch):
    return install_cli_harness(monkeypatch)


def test_darklab_cli_risk_and_advisory_commands(cli_harness, capsys):
    cli_main = cli_harness.cli_main
    osv_requests = cli_harness.osv_requests
    assert cli_main.main(["risk", "status"]) == 0
    risk_status = capsys.readouterr().out
    assert "stale" in risk_status
    assert "unavailable" in risk_status
    assert cli_main.main(["risk", "status", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 2
    assert cli_main.main(["risk", "status", "--format", "ndjson"]) == 0
    assert [json.loads(line)["source"] for line in capsys.readouterr().out.splitlines()] == [
        "epss", "kev",
    ]
    assert osv_requests == []
    assert cli_main.main([
        "advisory", "osv", "pkg:pypi/requests", "2.30.0",
    ]) == 0
    advisory_output = capsys.readouterr().out
    assert "outcome: negative_cached" in advisory_output
    assert "record_count: 0" in advisory_output
    assert osv_requests[-1] == {
        "purl": "pkg:pypi/requests",
        "version": "2.30.0",
    }
    assert cli_main.main([
        "advisory", "osv", "pkg:pypi/requests", "2.30.0", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "outcome": "negative_cached",
        "record_count": 0,
        "source": "osv",
    }
    request_count = len(osv_requests)
    assert cli_main.main(["advisory", "osv", "", "2.30.0"]) == 1
    assert "PURL must not be empty" in capsys.readouterr().err
    assert cli_main.main(["advisory", "osv", "pkg:pypi/requests", ""]) == 1
    assert "VERSION must not be empty" in capsys.readouterr().err
    assert len(osv_requests) == request_count
    for purl, message in (
        ("pkg:pypi/forbidden", "requires the TRIAGE_FINDINGS capability"),
        ("pkg:pypi/disabled", "Set cve_risk.osv_advisory_mode to external"),
        ("pkg:pypi/busy", "lookup budget is temporarily busy"),
        ("pkg:pypi/provider-failure", "Check outbound access and provider availability"),
    ):
        assert cli_main.main(["advisory", "osv", purl, "2.30.0"]) == 1
        assert message in capsys.readouterr().err
