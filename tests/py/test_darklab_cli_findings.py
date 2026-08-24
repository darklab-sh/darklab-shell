# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
from io import StringIO
from unittest import mock

import pytest
from darklab_cli_test_support import install_cli_harness


@pytest.fixture
def cli_harness(monkeypatch):
    return install_cli_harness(monkeypatch)


def test_darklab_cli_finding_and_evidence_commands(cli_harness, capsys, tmp_path):
    cli_main = cli_harness.cli_main
    finding_requests = cli_harness.finding_requests
    create_input = tmp_path / "finding-create.json"
    create_input.write_text(json.dumps({
        "target_id": "ent_cli",
        "title": "Manual CLI finding",
        "severity": "high",
        "summary": "Confirmed from the headless client",
        "evidence": [{"evidence_type": "run", "evidence_id": "run_cli"}],
    }), encoding="utf-8")
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(create_input),
    ]) == 0
    assert "fnd_manual_cli" in capsys.readouterr().out
    assert finding_requests[-1] == (
        "POST",
        "/projects/prj_cli/findings",
        {
            "target_id": "ent_cli",
            "title": "Manual CLI finding",
            "severity": "high",
            "summary": "Confirmed from the headless client",
            "evidence": [{"evidence_type": "run", "evidence_id": "run_cli"}],
        },
    )
    edit_input = tmp_path / "finding-edit.json"
    edit_input.write_text('{"summary":"Updated from automation"}', encoding="utf-8")
    assert cli_main.main([
        "finding", "edit", "prj_cli", "fnd_manual_cli",
        "--expected-revision", "1", "--input", str(edit_input), "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["finding"]["manual_revision"] == 2
    assert finding_requests[-1] == (
        "PATCH",
        "/projects/prj_cli/findings/fnd_manual_cli",
        {"summary": "Updated from automation", "expected_revision": 1},
    )
    assert cli_main.main([
        "finding", "edit", "prj_cli", "fnd_manual_cli",
        "--expected-revision", "0", "--input", str(edit_input),
    ]) == 1
    stale_error = capsys.readouterr().err
    assert "review the current record" in stale_error
    assert "current revision is 2" in stale_error
    duplicate_input = tmp_path / "finding-duplicate.json"
    duplicate_input.write_text(json.dumps({
        "target_id": "ent_cli",
        "title": "Possible duplicate",
        "severity": "medium",
    }), encoding="utf-8")
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(duplicate_input),
    ]) == 1
    duplicate_error = capsys.readouterr().err
    assert "--allow-duplicate" in duplicate_error
    assert "fnd_existing" in duplicate_error
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(duplicate_input),
        "--allow-duplicate",
    ]) == 0
    assert "Duplicate override: yes" in capsys.readouterr().out
    assert finding_requests[-1][2]["allow_duplicate"] is True
    forbidden_input = tmp_path / "finding-forbidden.json"
    forbidden_input.write_text(json.dumps({
        "target_id": "ent_cli",
        "title": "Forbidden finding",
        "severity": "low",
    }), encoding="utf-8")
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(forbidden_input),
    ]) == 1
    assert "TRIAGE_FINDINGS capability" in capsys.readouterr().err
    invalid_input = tmp_path / "finding-invalid.json"
    invalid_input.write_text("[]", encoding="utf-8")
    request_count = len(finding_requests)
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(invalid_input),
    ]) == 1
    assert "must contain one JSON object" in capsys.readouterr().err
    assert len(finding_requests) == request_count
    control_input = tmp_path / "finding-control.json"
    control_input.write_text(json.dumps({
        "target_id": "ent_cli",
        "title": "Hidden control",
        "severity": "low",
        "allow_duplicate": True,
    }), encoding="utf-8")
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(control_input),
    ]) == 1
    assert "use --allow-duplicate" in capsys.readouterr().err
    assert len(finding_requests) == request_count
    oversized_input = tmp_path / "finding-oversized.json"
    oversized_input.write_text(" " * (1024 * 1024 + 1), encoding="utf-8")
    assert cli_main.main([
        "finding", "create", "prj_cli", "--input", str(oversized_input),
    ]) == 1
    assert "structured input exceeds 1048576 bytes" in capsys.readouterr().err
    assert len(finding_requests) == request_count
    with mock.patch("darklab_cli.payloads.sys.stdin", new=StringIO(json.dumps({
        "target_id": "ent_cli",
        "title": "Finding from stdin",
        "severity": "info",
    }))):
        assert cli_main.main([
            "finding", "create", "prj_cli", "--input", "-", "--format", "json",
        ]) == 0
    assert json.loads(capsys.readouterr().out)["finding"]["title"] == "Finding from stdin"
    assert finding_requests[-1][2] == {
        "target_id": "ent_cli",
        "title": "Finding from stdin",
        "severity": "info",
    }
    assert cli_main.main([
        "evidence", "list", "prj_cli", "fnd_manual_cli",
    ]) == 0
    assert "fev_cli" in capsys.readouterr().out
    assert cli_main.main([
        "evidence", "list", "prj_cli", "fnd_manual_cli", "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 1
    assert cli_main.main([
        "evidence", "list", "prj_cli", "fnd_manual_cli", "--format", "ndjson",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "fev_cli"
    assert cli_main.main([
        "evidence", "link", "prj_cli", "fnd_manual_cli",
        "run_line", "run_new", "--line-number", "3", "--snippet", "matched line",
    ]) == 0
    assert "Evidence linked." in capsys.readouterr().out
    assert finding_requests[-1][2] == {
        "evidence_type": "run_line",
        "evidence_id": "run_new",
        "line_number": 3,
        "snippet": "matched line",
    }
    assert cli_main.main([
        "evidence", "link", "prj_cli", "fnd_manual_cli", "run", "run_cli",
    ]) == 0
    assert "already exists; no changes" in capsys.readouterr().out
    request_count = len(finding_requests)
    assert cli_main.main([
        "evidence", "link", "prj_cli", "fnd_manual_cli", "run_line", "run_new",
    ]) == 1
    assert "requires a zero-based --line-number" in capsys.readouterr().err
    assert len(finding_requests) == request_count
    assert cli_main.main([
        "evidence", "link", "prj_cli", "fnd_manual_cli", "run", "run_forbidden",
    ]) == 1
    assert "TRIAGE_FINDINGS capability" in capsys.readouterr().err
    assert cli_main.main([
        "evidence", "unlink", "prj_cli", "fnd_manual_cli", "fev_cli",
        "--format", "json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["evidence"]["id"] == "fev_cli"
    assert finding_requests[-1] == (
        "DELETE",
        "/projects/prj_cli/findings/fnd_manual_cli/evidence/fev_cli",
        None,
    )
