"""Prometheus runtime environment setup."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from config import CFG

DEFAULT_PROMETHEUS_MULTIPROC_DIR = Path(tempfile.gettempdir()) / "darklab_shell-prom"
log = logging.getLogger("shell")


def setup_prometheus_multiproc_dir(cfg: Mapping[str, Any] | None = None) -> str:
    active_cfg = CFG if cfg is None else cfg
    configured = str(active_cfg.get("prometheus_multiproc_dir") or "").strip()
    path = Path(configured).expanduser() if configured else DEFAULT_PROMETHEUS_MULTIPROC_DIR
    source = "config" if configured else "default"
    try:
        path.mkdir(parents=True, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(path)
        os.environ.setdefault("DARKLAB_APP_START_TIME_SECONDS", str(int(time.time())))
    except Exception:
        log.error(
            "METRICS_ENVIRONMENT_SETUP_FAILED",
            exc_info=True,
            extra={"prometheus_multiproc_dir": str(path), "source": source},
        )
        raise
    log.info(
        "METRICS_ENVIRONMENT_CONFIGURED",
        extra={
            "prometheus_multiproc_dir": str(path),
            "source": source,
            "app_start_time_set": bool(os.environ.get("DARKLAB_APP_START_TIME_SECONDS")),
        },
    )
    return str(path)
