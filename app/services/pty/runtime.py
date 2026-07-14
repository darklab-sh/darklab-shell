# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Low-level PTY runtime helpers."""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import struct
import subprocess
import tempfile
import termios
from typing import Any

from config import SCANNER_PREFIX

log = logging.getLogger("shell")

SUDO_BIN = "/usr/bin/sudo"
KILL_BIN = "/bin/kill"
RUN_SUBPROCESS_UMASK = 0o027
PTY_ENV_PASSTHROUGH_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "TMPDIR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NO_COLOR",
    "CLICOLOR",
    "COLORTERM",
)


def prepare_child() -> None:
    os.setsid()
    os.umask(RUN_SUBPROCESS_UMASK)


def bounded_dimension(value: object, default: int, min_value: int, max_value: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return min(max(number, min_value), max_value)


def set_pty_size(fd: int, rows: int, cols: int) -> None:
    try:
        packed = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)
    except OSError as exc:
        log.warning("PTY_RESIZE_IOCTL_FAILED", extra={"fd": fd, "rows": rows, "cols": cols, "error": str(exc)})


def command_env() -> dict[str, str]:
    env = {
        key: value
        for key in PTY_ENV_PASSTHROUGH_KEYS
        if (value := os.environ.get(key))
    }
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("HOME", tempfile.gettempdir())
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", env.get("LANG", "C.UTF-8"))
    env["TERM"] = "xterm-256color"
    return env


def terminate_run(run: Any) -> None:
    if run.proc.poll() is not None:
        return
    try:
        pgid = run.proc.pid
        if SCANNER_PREFIX:
            subprocess.run(
                [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                timeout=5,
            )
        else:
            os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError) as exc:
        log.warning(
            "PTY_TERMINATE_FAILED",
            exc_info=True,
            extra={"run_id": run.run_id, "pid": run.proc.pid, "cmd": run.command, "error": str(exc)},
        )
