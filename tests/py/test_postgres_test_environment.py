# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compose dependency reuse preserves invalidation and interrupted-build recovery."""

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/development/prepare_postgres_test_env.py"
spec = importlib.util.spec_from_file_location("postgres_test_environment", SCRIPT)
assert spec and spec.loader
environment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(environment)


@pytest.fixture
def environment_cache(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    for name in environment.REQUIREMENTS:
        (root / name).write_text("example==1\n")
    builds = []

    def build(path, _root):
        builds.append(path)
        (path / "bin").mkdir()
        (path / "bin/python").symlink_to(sys.executable)

    monkeypatch.setattr(environment, "_build_environment", build)
    return tmp_path / "cache", root, builds


def test_dependency_cache_reuses_environment_and_invalidates_requirements_and_runtime(environment_cache, monkeypatch):
    parent, root, builds = environment_cache
    first = environment.prepare_environment(parent, root)
    assert environment.prepare_environment(parent, root) == first
    assert len(builds) == 1
    (root / "requirements-dev.txt").write_text("example==2\n")
    second = environment.prepare_environment(parent, root)
    assert second != first
    monkeypatch.setattr(environment.sysconfig, "get_platform", lambda: "different-runtime")
    assert environment.prepare_environment(parent, root) not in {first, second}
    assert len(builds) == 3
    assert first.is_file()  # An older invocation may still be using it.


def test_failed_dependency_build_is_removed_and_can_be_retried(environment_cache, monkeypatch):
    parent, root, builds = environment_cache
    build = environment._build_environment

    def fail(path, _root):
        (path / "partial").touch()
        raise subprocess.CalledProcessError(1, ["pip"])

    monkeypatch.setattr(environment, "_build_environment", fail)
    with pytest.raises(subprocess.CalledProcessError):
        environment.prepare_environment(parent, root)
    assert not list(parent.rglob("partial"))
    monkeypatch.setattr(environment, "_build_environment", build)
    assert environment.prepare_environment(parent, root).is_file()
    assert len(builds) == 1


def test_incomplete_dependency_cache_is_rebuilt(environment_cache):
    parent, root, builds = environment_cache
    first = environment.prepare_environment(parent, root)
    (first.parent.parent / "ready.json").write_text("interrupted")
    assert environment.prepare_environment(parent, root) == first
    assert len(builds) == 2


def test_dependency_cache_rejects_shared_directory_and_symlink(environment_cache):
    parent, root, _ = environment_cache
    cache = parent / "darklab-postgres-test-venvs"
    cache.mkdir(parents=True, mode=0o755)
    # Set the rejected permissions explicitly; mkdir() applies the caller's umask.
    cache.chmod(0o755)
    with pytest.raises(RuntimeError, match="private directory"):
        environment.prepare_environment(parent, root)
    cache.rmdir()
    elsewhere = parent / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    cache.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(RuntimeError, match="private directory"):
        environment.prepare_environment(parent, root)
    assert list(elsewhere.iterdir()) == []


def test_concurrent_dependency_builds_publish_one_complete_environment(environment_cache):
    parent, root, _ = environment_cache
    program = '''
import importlib.util, pathlib, sys, time
spec = importlib.util.spec_from_file_location("env", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def build(path, root):
    with (path.parent / "build-count").open("a") as count:
        count.write("build\\n")
    time.sleep(0.15)
    (path / "bin").mkdir()
    (path / "bin/python").symlink_to(sys.executable)
module._build_environment = build
print(module.prepare_environment(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])))
'''
    command = [sys.executable, "-c", program, str(SCRIPT), str(parent), str(root)]
    processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    try:
        results = [process.communicate(timeout=15) for process in processes]
        assert all(process.returncode == 0 for process in processes), results
        assert results[0][0] == results[1][0]
        assert (parent / "darklab-postgres-test-venvs/build-count").read_text() == "build\n"
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_postgres_container_metrics_only_accepts_safe_numeric_fields():
    metrics_spec = importlib.util.spec_from_file_location("pg_metrics", SCRIPT.with_name("postgres_test_metrics.py"))
    assert metrics_spec and metrics_spec.loader
    metrics = importlib.util.module_from_spec(metrics_spec)
    metrics_spec.loader.exec_module(metrics)
    assert metrics.parse_container_metrics(
        "usage_usec 250000\nuser_usec 200000\nsystem_usec 50000\nMEMORY_PEAK 12345\n"
        "postgres (PostgreSQL) 18.0\nPASSWORD private\nusage_usec bad-secret\n"
    ) == {"usage_usec": 250000, "user_usec": 200000, "system_usec": 50000,
          "MEMORY_PEAK": 12345, "postgres": "18.0"}
    assert metrics.parse_container_metrics("Docker unavailable: private configuration") == {}


def test_postgres_metrics_preserves_failure_status_when_counters_are_unavailable(tmp_path, monkeypatch, capsys):
    import json
    from types import SimpleNamespace

    metrics_spec = importlib.util.spec_from_file_location("pg_metrics", SCRIPT.with_name("postgres_test_metrics.py"))
    assert metrics_spec and metrics_spec.loader
    metrics = importlib.util.module_from_spec(metrics_spec)
    metrics_spec.loader.exec_module(metrics)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(metrics, "read_container_metrics", lambda _: {})
    monkeypatch.setattr(metrics.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=7))
    assert metrics.run_measured("private-container", ["private-command"]) == 7
    output = capsys.readouterr().out
    assert "private" not in output
    data = json.loads((tmp_path / "test-results/timings/postgres-container.json").read_text())
    assert data["database_cpu_seconds"] is None
    assert data["exitstatus"] == 7
    assert data["wall_seconds"] >= 0
