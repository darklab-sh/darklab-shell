# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stage Nikto reports before copying them into an authorized workspace file."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Sequence


_FORMAT_SUFFIXES = {
    "csv": "csv",
    "htm": "htm",
    "html": "htm",
    "json": "json",
    "sql": "sql",
    "txt": "txt",
    "xml": "xml",
}


def _output_argument(argv: Sequence[str]) -> tuple[int, str, bool] | None:
    for index, token in enumerate(argv[1:], start=1):
        if token in {"-o", "--output"} and index + 1 < len(argv):
            return index + 1, str(argv[index + 1]), False
        if token.startswith("--output="):
            return index, token.split("=", 1)[1], True
    return None


def _report_format(argv: Sequence[str], destination: Path) -> tuple[str, bool]:
    for index, token in enumerate(argv[1:], start=1):
        if token.lower() == "-format" and index + 1 < len(argv):
            value = str(argv[index + 1]).strip().lower()
            return _FORMAT_SUFFIXES.get(value, "txt"), True
    suffix = destination.suffix.lower().lstrip(".")
    return _FORMAT_SUFFIXES.get(suffix, "txt"), False


def _authorized_destination(raw_path: str) -> Path:
    destination = Path(raw_path)
    if not destination.is_absolute():
        raise ValueError("Nikto workspace output must be an absolute path.")
    path_stat = destination.lstat()
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise ValueError("Nikto workspace output must be a regular file.")
    return destination


def _copy_report(source: Path, destination: Path) -> None:
    flags = os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags)
    try:
        destination_stat = os.fstat(descriptor)
        if not stat.S_ISREG(destination_stat.st_mode):
            raise ValueError("Nikto workspace output must be a regular file.")
        os.ftruncate(descriptor, 0)
        with source.open("rb") as report, os.fdopen(descriptor, "wb") as target:
            descriptor = -1
            shutil.copyfileobj(report, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def run_nikto_workspace(
    argv: Sequence[str],
    *,
    run_command: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    """Run Nikto and copy its generated report to the validated output path."""
    arguments = [str(value) for value in argv]
    if not arguments or os.path.basename(arguments[0]).lower() != "nikto":
        print("Nikto workspace adapter requires a Nikto command.", file=sys.stderr)
        return 2

    output = _output_argument(arguments)
    if output is None:
        return int(run_command(arguments, check=False).returncode)

    output_index, raw_destination, attached = output
    try:
        destination = _authorized_destination(raw_destination)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report_format, format_present = _report_format(arguments, destination)
    with tempfile.TemporaryDirectory(prefix="darklab-nikto-") as temporary_directory:
        temporary_base = Path(temporary_directory) / "report"
        if attached:
            arguments[output_index] = f"--output={temporary_base}"
        else:
            arguments[output_index] = str(temporary_base)
        if not format_present:
            arguments.extend(["-Format", report_format])

        completed = run_command(arguments, check=False)
        generated = Path(f"{temporary_base}.{report_format}")
        if generated.is_file():
            try:
                _copy_report(generated, destination)
            except (OSError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 2
        elif completed.returncode == 0:
            print("Nikto completed without creating its requested report.", file=sys.stderr)
            return 1
        return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    return run_nikto_workspace(list(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
