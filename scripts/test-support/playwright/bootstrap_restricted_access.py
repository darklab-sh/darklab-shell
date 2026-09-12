# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Create one restricted Playwright principal without printing its credential."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))

from runtime_bootstrap import init_database  # noqa: E402
from services.auth.lifecycle import operator_bootstrap  # noqa: E402


def _write_owner_file(path: Path, secret: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(secret + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-file", required=True)
    parser.add_argument("--label", default="Playwright restricted access")
    args = parser.parse_args()
    init_database()
    bundle = operator_bootstrap(credential_label=args.label)
    _write_owner_file(Path(args.secret_file), bundle.credential.secret)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
