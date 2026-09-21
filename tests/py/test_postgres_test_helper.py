# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Postgres helper reporting flags preserve the intended integration selection."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def helper_invocation(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[2] / "scripts/run_postgres_tests.sh", scripts / "run_postgres_tests.sh")
    (scripts / "run_pytest.sh").write_text('printf "%s\\n" "$@" > "$TEST_ARGUMENT_OUTPUT"\n')
    python = tmp_path / "ready-python"
    python.write_text("#!/bin/sh\ncat >/dev/null\n")
    python.chmod(0o700)
    output = tmp_path / "arguments"
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env.update({"PYTHON_BIN": str(python), "DARKLAB_TEST_POSTGRES_DSN": "postgresql://unused",
                "TEST_ARGUMENT_OUTPUT": str(output)})

    def invoke(*args):
        subprocess.run(["bash", str(scripts / "run_postgres_tests.sh"), "--host", "--", *args],
                       cwd=tmp_path, env=env, check=True, capture_output=True, text=True)
        return output.read_text().splitlines()

    return invoke


@pytest.mark.parametrize("reporting", [[], ["--durations=0", "--junitxml=timings.xml"],
                                      ["--durations", "10", "--junit-xml", "timings.xml", "-v"],
                                      ["--collect-only", "--no-header"]])
def test_reporting_arguments_extend_default_postgres_selection(helper_invocation, reporting):
    args = helper_invocation(*reporting)
    assert "tests/py/test_postgres_backend.py" in args
    assert "tests/py/test_operator_diagnostics.py" in args
    assert "not sqlite_backend" in args
    assert "tests/py/test_output_search.py" not in args
    assert not any("test_backend_modules.py" in arg for arg in args)
    if reporting:
        assert args[-len(reporting):] == reporting


def test_explicit_test_selection_preserves_every_argument(helper_invocation):
    focused = ["-c", ".tooling/pytest.ini", "--rootdir=.",
               "tests/py/test_operator_grants.py", "-k", "sqlite", "--durations=0"]
    assert helper_invocation(*focused) == focused
