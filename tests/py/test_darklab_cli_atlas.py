# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json

import pytest
from darklab_cli_test_support import install_cli_harness


@pytest.fixture
def cli_harness(monkeypatch):
    return install_cli_harness(monkeypatch)


def test_darklab_cli_project_and_atlas_readers(cli_harness, capsys):
    cli_main = cli_harness.cli_main
    assert cli_main.main(["project-runs", "prj_cli"]) == 0
    assert "run_cli" in capsys.readouterr().out
    assert cli_main.main(["project-link", "run_cli", "prj_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["link"]["entity_id"] == "run_cli"
    assert cli_main.main(["project-unlink", "run_cli", "prj_cli", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli_main.main(["project-entities", "prj_cli", "--entity-type", "domain"]) == 0
    assert "darklab.sh" in capsys.readouterr().out
    assert cli_main.main(["atlas", "summary"]) == 0
    assert "entities: 1" in capsys.readouterr().out
    assert cli_main.main(["atlas", "runs"]) == 0
    assert "run_cli" in capsys.readouterr().out
    assert cli_main.main(["atlas", "entities", "--entity-type", "domain"]) == 0
    assert "darklab.sh" in capsys.readouterr().out
    assert cli_main.main(["atlas", "entity", "ent_cli"]) == 0
    entity_output = capsys.readouterr().out
    assert "OCCURRENCES" in entity_output
    assert "ent_cli" in entity_output
    assert cli_main.main(["atlas", "findings"]) == 0
    assert "Open port" in capsys.readouterr().out
    assert cli_main.main(["atlas", "finding", "fnd_cli"]) == 0
    finding_output = capsys.readouterr().out
    assert "SEVERITY" in finding_output
    assert "fnd_cli" in finding_output
    assert cli_main.main(["project", "missing"]) == 1
    assert "not_found: missing" in capsys.readouterr().err
