#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Measure a disposable database container without inspecting its environment."""

import json
from pathlib import Path
import resource
import subprocess
import sys
import time


def read_container_metrics(container: str) -> dict:
    command = ["docker", "exec", container, "sh", "-c",
               "cat /sys/fs/cgroup/cpu.stat; printf '\\nMEMORY_PEAK '; "
               "cat /sys/fs/cgroup/memory.peak; postgres --version"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_container_metrics(result.stdout)


def parse_container_metrics(output: str) -> dict:
    metrics = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in {"usage_usec", "user_usec", "system_usec", "MEMORY_PEAK"}:
            if parts[1].isdigit():
                metrics[parts[0]] = int(parts[1])
        if len(parts) == 3 and parts[:2] == ["postgres", "(PostgreSQL)"]:
            if all(part.isdigit() for part in parts[2].split(".")):
                metrics["postgres"] = parts[2]
    return metrics


def run_measured(container: str, command: list[str]) -> int:
    before = read_container_metrics(container)
    cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    result = subprocess.run(command, check=False)
    elapsed = time.monotonic() - started
    after_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    after = read_container_metrics(container)
    database_cpu = {
        name: (after[key] - before[key]) / 1_000_000
        for name, key in (("total", "usage_usec"), ("user", "user_usec"), ("system", "system_usec"))
        if key in before and key in after and after[key] >= before[key]
    }
    summary = {
        "schema_version": 1,
        "mode": "disposable-container",
        "postgres": after.get("postgres"),
        "wall_seconds": elapsed,
        "client_cpu_seconds": {"user": after_cpu.ru_utime - cpu.ru_utime,
                               "system": after_cpu.ru_stime - cpu.ru_stime},
        "database_cpu_seconds": database_cpu or None,
        "container_lifetime_peak_memory_bytes": after.get("MEMORY_PEAK"),
        "exitstatus": result.returncode,
    }
    destination = Path("test-results/timings/postgres-container.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2) + "\n")
    print("DARKLAB_POSTGRES_TIMINGS " + json.dumps(summary), flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(run_measured(sys.argv[1], sys.argv[2:]))
