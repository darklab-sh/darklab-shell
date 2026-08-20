# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Execute Nuclei while holding the managed-cache read lock."""

from __future__ import annotations

import os
import re
import sys

from services.nuclei.template_cache import managed_nuclei_template_snapshot
from services.nuclei.template_lock import (
    NucleiTemplateLockBusy,
    NucleiTemplateLockError,
    managed_nuclei_template_lock,
)


LOCK_RETRY_EXIT_CODE = 75
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def locked_nuclei_argv(command_argv: list[str], expected_digest: str = "") -> list[str]:
    argv = [sys.executable, "-m", "services.nuclei.template_run"]
    if expected_digest:
        argv.extend(("--expected-digest", expected_digest))
    return [*argv, "--", *command_argv]


def run_locked_nuclei(command_argv: list[str], expected_digest: str = "") -> int:
    if not command_argv or (expected_digest and not _DIGEST_RE.fullmatch(expected_digest)):
        return 64
    try:
        with managed_nuclei_template_lock(
            exclusive=False,
            blocking=False,
            inheritable=True,
        ):
            if expected_digest:
                snapshot = managed_nuclei_template_snapshot(acquire_lock=False)
                if snapshot.state != "ready" or snapshot.content_digest != expected_digest:
                    print(
                        "[nuclei templates] The approved managed template snapshot changed; "
                        "rebuild and approve the plan again.",
                        flush=True,
                    )
                    return LOCK_RETRY_EXIT_CODE
            try:
                os.execvpe(command_argv[0], command_argv, os.environ)
            except OSError:
                print("[nuclei templates] Nuclei couldn't be started.", flush=True)
                return 127
    except NucleiTemplateLockBusy:
        print(
            "[nuclei templates] Managed templates are being updated; retry after "
            "the refresh finishes.",
            flush=True,
        )
        return LOCK_RETRY_EXIT_CODE
    except NucleiTemplateLockError:
        print("[nuclei templates] The managed template lock is unavailable.", flush=True)
        return LOCK_RETRY_EXIT_CODE
    return 127


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    expected_digest = ""
    if values[:1] == ["--expected-digest"] and len(values) >= 2:
        expected_digest = values[1]
        values = values[2:]
    if values[:1] != ["--"]:
        return 64
    return run_locked_nuclei(values[1:], expected_digest)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["LOCK_RETRY_EXIT_CODE", "locked_nuclei_argv", "main", "run_locked_nuclei"]
