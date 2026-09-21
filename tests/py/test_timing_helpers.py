# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Timing reports keep useful phase evidence without recording private inputs."""

import json
from types import SimpleNamespace

from timing_helpers import PytestTimings


def test_pytest_timing_report_preserves_phases_and_omits_private_context(tmp_path, monkeypatch):
    secret = "private-database-credential"
    monkeypatch.setenv("DARKLAB_TEST_POSTGRES_DSN", f"postgresql://user:{secret}@localhost/test")
    output = tmp_path / "nested" / "timings.json"
    reporter = PytestTimings(output)
    session = SimpleNamespace(
        items=[SimpleNamespace(nodeid="test_example.py::test_case")],
        config=SimpleNamespace(getoption=lambda option: secret),
    )
    reporter.pytest_collection(session)
    reporter.pytest_collection_finish(session)
    for phase, duration, outcome in (("setup", 0.2, "passed"), ("call", 0.3, "failed"), ("teardown", 0.1, "passed")):
        reporter.pytest_runtest_logreport(SimpleNamespace(
            nodeid="test_example.py::test_case", when=phase, duration=duration, outcome=outcome,
            longrepr=secret, sections=[("Captured stdout", secret)],
        ))
    reporter.pytest_sessionfinish(session, 1)
    raw = output.read_text()
    data = json.loads(raw)
    assert secret not in raw
    assert "postgresql" not in raw
    assert data["environment_present"]["DARKLAB_TEST_POSTGRES_DSN"] is True
    assert data["postgres_option_present"] is True
    assert data["selected"] == ["test_example.py::test_case"]
    assert [phase["phase"] for phase in data["phases"]] == ["setup", "call", "teardown"]
    assert sum(phase["seconds"] for phase in data["phases"]) == 0.6
    assert data["phases"][1]["outcome"] == "failed"
    assert data["exitstatus"] == 1
    assert data["collection_seconds"] >= 0
    assert set(data["process_cpu_seconds"]) == {"user", "system"}
