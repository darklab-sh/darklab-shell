#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reuse a private, runtime-qualified dependency environment in Compose tests."""

import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import sysconfig


ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ("app/requirements.txt", "requirements-dev.txt")


def environment_key(root: Path) -> str:
    """Invalidate on dependency, helper, interpreter, ABI, or base-image changes."""
    runtime = {
        "python": sys.version,
        "executable": str(Path(sys.executable).resolve()),
        "platform": sysconfig.get_platform(),
        "abi": sysconfig.get_config_var("SOABI"),
        "libc": platform.libc_ver(),
        "os_release": Path("/etc/os-release").read_text() if Path("/etc/os-release").exists() else "",
        "base_packages": sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions()),
    }
    digest = hashlib.sha256(json.dumps(runtime, sort_keys=True).encode())
    digest.update(Path(__file__).read_bytes())
    for name in REQUIREMENTS:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("The Postgres dependency cache must be a private directory owned by this user")


def _build_environment(path: Path, root: Path) -> None:
    # Build at its permanent path: virtualenv console scripts contain absolute paths.
    subprocess.run([sys.executable, "-m", "venv", str(path)], check=True, stdout=sys.stderr)
    python = str(path / "bin/python")
    requirements = [arg for name in REQUIREMENTS for arg in ("-r", str(root / name))]
    subprocess.run([python, "-m", "pip", "install", "-q", *requirements], check=True, stdout=sys.stderr)
    subprocess.run([python, "-m", "pip", "check"], check=True, stdout=sys.stderr)


def prepare_environment(parent: Path, root: Path = ROOT) -> Path:
    cache = parent / "darklab-postgres-test-venvs"
    _private_directory(cache)
    key = environment_key(root)
    target = cache / key
    # Serialize construction, including recovery after interruption. Completed
    # environments are immutable and can serve concurrent isolated pytest runs.
    descriptor = os.open(cache / "build.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.is_symlink():
            raise RuntimeError("Refusing a symlink in the Postgres dependency cache")
        if target.exists():
            _private_directory(target)
        marker = target / "ready.json"
        if marker.is_file() and not marker.is_symlink():
            try:
                ready = json.loads(marker.read_text()) == {"key": key}
            except (ValueError, OSError):
                ready = False
            if ready and (target / "bin/python").is_file():
                print("[postgres-tests] reusing Python dependency environment", file=sys.stderr)
                return target / "bin/python"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(mode=0o700)
        try:
            _build_environment(target, root)
            marker.write_text(json.dumps({"key": key}) + "\n")
        except BaseException:
            shutil.rmtree(target)
            raise
        print("[postgres-tests] prepared Python dependency environment", file=sys.stderr)
        return target / "bin/python"


if __name__ == "__main__":
    try:
        print(prepare_environment(Path(os.environ.get("DARKLAB_TEST_COMPOSE_VENV_PARENT", "/data"))))
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[postgres-tests] dependency preparation failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
