# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Opt-in pytest timings without captured logs, environment values, or DSNs."""

import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import time


def revision_metadata():
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], capture_output=True, check=False).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return {"revision": "unknown", "working_tree_dirty": None}
    return {"revision": revision, "working_tree_dirty": dirty}


class PytestTimings:
    def __init__(self, output: Path, *, app_data_dir_supplied: bool = False):
        self.output = output
        self.started = time.monotonic()
        self.cpu = resource.getrusage(resource.RUSAGE_SELF)
        self.children = resource.getrusage(resource.RUSAGE_CHILDREN)
        self.collection_started = self.started
        self.collection_seconds = 0.0
        self.selected = []
        self.phases = []
        self.environment = {
            key: bool(os.environ.get(key))
            for key in ("DARKLAB_TEST_POSTGRES_DSN", "APP_DATA_DIR", "PYTEST_ADDOPTS")
        }
        self.environment["APP_DATA_DIR"] = app_data_dir_supplied

    def pytest_collection(self, session):
        self.collection_started = time.monotonic()

    def pytest_collection_finish(self, session):
        self.collection_seconds = time.monotonic() - self.collection_started
        self.selected = [item.nodeid for item in session.items]

    def pytest_runtest_logreport(self, report):
        self.phases.append({
            "id": report.nodeid,
            "phase": report.when,
            "seconds": report.duration,
            "outcome": report.outcome,
        })

    def pytest_sessionfinish(self, session, exitstatus):
        cpu = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        payload = {
            "schema_version": 1,
            **revision_metadata(),
            "python": platform.python_version(),
            "platform": platform.system(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "ci_runner_id": int(os.environ["CI_RUNNER_ID"]) if os.environ.get("CI_RUNNER_ID", "").isdigit() else None,
            "environment_present": self.environment,
            "postgres_option_present": bool(session.config.getoption("--postgres-dsn")),
            "session_seconds": time.monotonic() - self.started,
            "collection_seconds": self.collection_seconds,
            "process_cpu_seconds": {
                "user": cpu.ru_utime - self.cpu.ru_utime,
                "system": cpu.ru_stime - self.cpu.ru_stime,
            },
            "child_process_cpu_seconds": {
                "user": children.ru_utime - self.children.ru_utime,
                "system": children.ru_stime - self.children.ru_stime,
            },
            "exitstatus": int(exitstatus),
            "selected": self.selected,
            "phases": self.phases,
        }
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
