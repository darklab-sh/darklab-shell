# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest
from darklab_cli_test_support import install_cli_harness


@pytest.fixture
def cli_harness(monkeypatch):
    return install_cli_harness(monkeypatch)


def test_darklab_cli_run_history_and_service_evidence_commands(cli_harness, capsys):
    cli_main = cli_harness.cli_main
    assert cli_main.main(["history"]) == 0
    history_lines = capsys.readouterr().out.splitlines()
    assert history_lines[0].startswith("FINISHED")
    assert history_lines[2].startswith("2026-05-19T00:00:01+00:00  run_old")
    assert history_lines[3].startswith("2026-05-19T00:00:02+00:00  run_cli")
    assert cli_main.main(["history", "--format", "ndjson"]) == 0
    ndjson_lines = capsys.readouterr().out.splitlines()
    assert json.loads(ndjson_lines[0])["id"] == "run_old"
    assert json.loads(ndjson_lines[1])["id"] == "run_cli"
    assert cli_main.main(["history", "--type", "runs_external"]) == 0
    assert "run_external" in capsys.readouterr().out
    assert cli_main.main(["grep", "needle", "--context", "1"]) == 0
    assert "run_cli:2: needle here" in capsys.readouterr().out
    assert cli_main.main(["output", "run_cli"]) == 0
    assert capsys.readouterr().out == "ok\n"
    assert cli_main.main(["run", "echo ok", "--no-follow", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "run_cli"
    assert cli_main.main(["active"]) == 0
    active_output = capsys.readouterr().out
    assert "STARTED" in active_output
    assert "run_active" in active_output
    assert cli_main.main(["run", "echo linked", "--link-project", "CLI Project", "--wait"]) == 0
    assert "run_wait  succeeded  0  echo linked" in capsys.readouterr().out
    assert cli_main.main(["tail", "run_cli", "--format", "ndjson", "--after", "1-0"]) == 0
    tail_output = capsys.readouterr().out
    assert '"event":"schema"' in tail_output
    assert '"event":"output"' in tail_output
    assert '"event_id":"2-0"' in tail_output
    assert cli_main.main([
        "evidence", "services", "run_cli", "--limit", "25", "--offset", "5",
    ]) == 0
    service_evidence = capsys.readouterr().out
    assert "104.161.46.133:443/tcp" in service_evidence
    assert "ssl-cert" in service_evidence
    assert cli_main.main([
        "evidence", "services", "run_cli", "--limit", "25", "--offset", "5",
        "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["observations"][0]["id"] == "nse_cli"
    assert cli_main.main([
        "evidence", "services", "run_cli", "--limit", "25", "--offset", "5",
        "--format", "ndjson",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "nse_cli"
    assert cli_main.main(["evidence", "services", "run_empty"]) == 0
    assert capsys.readouterr().out == "No service evidence.\n"
    assert cli_main.main(["evidence", "services", "run_cli", "--limit", "101"]) == 1
    assert "limit must be between 1 and 100" in capsys.readouterr().err
