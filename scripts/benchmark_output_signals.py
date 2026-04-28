#!/usr/bin/env python3
"""Manual benchmark for backend output-signal classification.

This intentionally stays out of normal CI. It gives release work a stable way
to spot large regex-performance regressions without making test runs flaky.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import perf_counter


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app"))

from output_signals import OutputSignalClassifier  # noqa: E402


SAMPLE_LINES = [
    "Starting Nmap 7.95 ( https://nmap.org ) at 2026-04-27 12:00 UTC",
    "Nmap scan report for ip.darklab.sh (107.178.109.44)",
    "80/tcp open http",
    "443/tcp open https",
    "Service Info: Host: darklab",
    "darklab.sh has address 104.21.4.35",
    "darklab.sh mail is handled by 10 mail.darklab.sh.",
    "[medium] exposed-panel [http] [matched-at: https://ip.darklab.sh/admin]",
    "WARNING: rate limited, retrying request",
    "ERROR: connection refused",
    "[workspace] reading nmap/nmap_input.txt",
    "[workspace] writing nmap/nmap_results.xml",
    "Nmap done: 1 IP address (1 host up) scanned in 2.31 seconds",
    "plain scanner chatter " + ("x" * 512),
    "long non-matching line " + ("abcdef0123456789" * 256),
]


def _synthetic_lines(size_mb: int) -> list[str]:
    target_bytes = size_mb * 1024 * 1024
    lines: list[str] = []
    total = 0
    index = 0
    while total < target_bytes:
        line = SAMPLE_LINES[index % len(SAMPLE_LINES)]
        lines.append(line)
        total += len(line) + 1
        index += 1
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark output_signals.py against synthetic scanner output.")
    parser.add_argument("--size-mb", type=int, default=10, help="Synthetic transcript size in MiB. Default: 10")
    parser.add_argument("--iterations", type=int, default=3, help="Benchmark iterations. Default: 3")
    parser.add_argument("--command", default="nmap -sV ip.darklab.sh", help="Command context for classification.")
    args = parser.parse_args()

    if args.size_mb <= 0:
        parser.error("--size-mb must be greater than zero")
    if args.iterations <= 0:
        parser.error("--iterations must be greater than zero")

    lines = _synthetic_lines(args.size_mb)
    runs: list[float] = []
    signal_lines = 0

    for _ in range(args.iterations):
        classifier = OutputSignalClassifier(args.command)
        signal_lines = 0
        started = perf_counter()
        for line in lines:
            metadata = classifier.classify_line(line)
            if metadata.get("signals"):
                signal_lines += 1
        runs.append(perf_counter() - started)

    best = min(runs)
    average = sum(runs) / len(runs)
    print(f"output_signals benchmark: {len(lines):,} lines, ~{args.size_mb} MiB, {args.iterations} iterations")
    print(f"signal lines: {signal_lines:,}")
    print(f"best: {best:.3f}s")
    print(f"average: {average:.3f}s")
    print(f"throughput: {args.size_mb / best:.2f} MiB/s best")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
