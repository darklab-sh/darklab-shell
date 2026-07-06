"""Explicit runtime startup steps for web and worker processes."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from collections.abc import Mapping
from typing import Any

from config import APP_CONF_DIR, CONFIG_LOAD_WARNINGS, resolve_effective_cfg
from core.logging_setup import configure_logging
from services.metrics_environment import setup_prometheus_multiproc_dir

log = logging.getLogger("shell")

_ACTIVE_RUN_STARTUP_CLEANUP_LOCK_KEY = "active-run-metadata:startup-cleanup"
_ACTIVE_RUN_STARTUP_CLEANUP_LOCK_TTL_SECONDS = 60


def configure_runtime_logging(cfg: Mapping[str, Any] | None = None) -> None:
    configure_logging(resolve_effective_cfg(cfg))


def log_loaded_config(cfg: Mapping[str, Any] | None = None) -> None:
    active_cfg = resolve_effective_cfg(cfg)
    for warning in CONFIG_LOAD_WARNINGS:
        log.warning("CONFIG_LOCAL_LOAD_FAILED", extra=dict(warning))
    conf_dir = Path(APP_CONF_DIR) if APP_CONF_DIR else Path(__file__).resolve().parent / "conf"
    log.info(
        "CONFIG_LOADED",
        extra={
            "conf_dir": str(conf_dir),
            "local_overlay": (conf_dir / "config.local.yaml").exists(),
            "database_backend": str(active_cfg.get("database_backend") or ""),
            "workspace_enabled": bool(active_cfg.get("workspace_enabled")),
            "log_level": str(active_cfg.get("log_level") or ""),
            "log_format": str(active_cfg.get("log_format") or ""),
        },
    )


def setup_metrics_environment(cfg: Mapping[str, Any] | None = None) -> str:
    path = setup_prometheus_multiproc_dir(resolve_effective_cfg(cfg))
    os.environ.setdefault("DARKLAB_APP_START_TIME_SECONDS", str(int(time.time())))
    return path


def warn_workspace_root_config_drift(
    cfg: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Warn when container env and app config point at different workspace roots."""
    active_cfg = resolve_effective_cfg(cfg)
    active_environ = os.environ if environ is None else environ
    env_root = str(active_environ.get("WORKSPACE_ROOT") or "").strip()
    cfg_root = str(active_cfg.get("workspace_root") or "").strip()
    if not env_root or not cfg_root:
        return
    normalized_env_root = Path(env_root).expanduser().resolve(strict=False)
    normalized_cfg_root = Path(cfg_root).expanduser().resolve(strict=False)
    if normalized_env_root == normalized_cfg_root:
        return
    log.warning(
        "WORKSPACE_ROOT_MISMATCH",
        extra={
            "workspace_root_env": str(normalized_env_root),
            "workspace_root_config": str(normalized_cfg_root),
        },
    )


def init_process_runtime(cfg: Mapping[str, Any] | None = None) -> object | None:
    from core.process import init_process  # noqa: PLC0415

    return init_process(resolve_effective_cfg(cfg))


def init_database() -> None:
    from core.database import db_init  # noqa: PLC0415

    db_init()


def _acquire_active_run_startup_cleanup_lock() -> tuple[bool, str]:
    from core import process  # noqa: PLC0415

    redis_client = process.redis_client
    redis_context = {
        "redis_client_present": redis_client is not None,
        "redis_client_type": type(redis_client).__name__ if redis_client is not None else "",
        "redis_configured": bool(getattr(process, "REDIS_URL", "")),
        "lock_key": _ACTIVE_RUN_STARTUP_CLEANUP_LOCK_KEY,
        "lock_ttl_seconds": _ACTIVE_RUN_STARTUP_CLEANUP_LOCK_TTL_SECONDS,
    }
    if redis_client is None:
        log.warning(
            "ACTIVE_RUN_METADATA_STARTUP_CLEANUP_DEGRADED",
            extra={**redis_context, "reason": "lock_unavailable", "fallback": "per_worker", "pid": os.getpid()},
        )
        return True, "none"
    try:
        lock_acquired = bool(redis_client.set(
            _ACTIVE_RUN_STARTUP_CLEANUP_LOCK_KEY,
            f"{os.getpid()}:{int(time.time())}",
            ex=_ACTIVE_RUN_STARTUP_CLEANUP_LOCK_TTL_SECONDS,
            nx=True,
        ))
        log.debug(
            "ACTIVE_RUN_METADATA_STARTUP_CLEANUP_LOCK_ACQUIRED"
            if lock_acquired
            else "ACTIVE_RUN_METADATA_STARTUP_CLEANUP_LOCK_HELD",
            extra={**redis_context, "pid": os.getpid(), "lock_type": "redis"},
        )
        return lock_acquired, "redis"
    except Exception:
        log.warning(
            "ACTIVE_RUN_METADATA_STARTUP_CLEANUP_DEGRADED",
            exc_info=True,
            extra={**redis_context, "reason": "lock_failed", "fallback": "per_worker", "pid": os.getpid()},
        )
        return True, "none"


def cleanup_active_run_metadata_on_startup() -> None:
    from core.process import cleanup_stale_active_run_metadata  # noqa: PLC0415

    cleanup_owner, lock_type = _acquire_active_run_startup_cleanup_lock()
    if not cleanup_owner:
        log.debug("ACTIVE_RUN_METADATA_STARTUP_CLEANUP_SKIPPED", extra={"reason": "lock_held", "pid": os.getpid()})
        return
    try:
        result = cleanup_stale_active_run_metadata()
    except Exception:
        log.exception("ACTIVE_RUN_METADATA_STARTUP_CLEANUP_ERROR")
        return
    removed = int(result.get("metadata_removed", 0) or 0)
    session_members = int(result.get("session_members_removed", 0) or 0)
    team_members = int(result.get("team_members_removed", 0) or 0)
    if removed or session_members or team_members:
        log.info(
            "ACTIVE_RUN_METADATA_STARTUP_CLEANUP",
            extra={
                "metadata_removed": removed,
                "session_members_removed": session_members,
                "team_members_removed": team_members,
                "pid": os.getpid(),
                "cleanup_owner": True,
                "lock_type": lock_type,
            },
        )


def _bootstrap_step_flags(
    *,
    init_metrics: bool,
    init_logging: bool,
    init_process: bool,
    init_db: bool,
    cleanup_active_runs: bool,
) -> dict[str, bool]:
    return {
        "init_metrics": init_metrics,
        "init_logging": init_logging,
        "init_process": init_process,
        "init_db": init_db,
        "cleanup_active_runs": cleanup_active_runs,
    }


def _run_bootstrap_step(step: str, runtime_name: str, func, flags: dict[str, bool]) -> None:
    log.debug("RUNTIME_BOOTSTRAP_STEP_STARTED", extra={"step": step, "runtime": runtime_name})
    try:
        func()
    except Exception:
        log.error(
            "RUNTIME_BOOTSTRAP_FAILED",
            exc_info=True,
            extra={"phase": step, "runtime": runtime_name, **flags},
        )
        raise
    log.debug("RUNTIME_BOOTSTRAP_STEP_COMPLETED", extra={"step": step, "runtime": runtime_name})


def bootstrap_runtime(
    cfg: Mapping[str, Any] | None = None,
    *,
    init_metrics: bool = True,
    init_logging: bool = True,
    init_process: bool = True,
    init_db: bool = True,
    cleanup_active_runs: bool = False,
    runtime_name: str = "runtime",
) -> None:
    active_cfg = resolve_effective_cfg(cfg)
    started = time.monotonic()
    flags = _bootstrap_step_flags(
        init_metrics=init_metrics,
        init_logging=init_logging,
        init_process=init_process,
        init_db=init_db,
        cleanup_active_runs=cleanup_active_runs,
    )
    steps = (
        ("metrics", init_metrics, lambda: setup_metrics_environment(active_cfg)),
        ("logging", init_logging, lambda: (
            configure_runtime_logging(active_cfg),
            log_loaded_config(active_cfg),
            warn_workspace_root_config_drift(active_cfg),
        )),
        ("process", init_process, lambda: init_process_runtime(active_cfg)),
        ("database", init_db, init_database),
        ("active_run_cleanup", cleanup_active_runs, cleanup_active_run_metadata_on_startup),
    )
    for step, enabled, func in steps:
        if not enabled:
            log.debug(
                "RUNTIME_BOOTSTRAP_STEP_SKIPPED",
                extra={"step": step, "reason": "disabled_by_entrypoint", "runtime": runtime_name},
            )
            continue
        _run_bootstrap_step(step, runtime_name, func, flags)
    log.info(
        "RUNTIME_BOOTSTRAP_COMPLETED",
        extra={**flags, "runtime": runtime_name, "duration_ms": int((time.monotonic() - started) * 1000)},
    )


def bootstrap(config: Mapping[str, Any] | None = None):
    """Build the web app after all runtime side effects have run."""
    active_config = resolve_effective_cfg(config)
    started = time.monotonic()
    bootstrap_runtime(active_config, cleanup_active_runs=True, runtime_name="web")
    # app.create_app assembles the product app; app_factory.create_app is the
    # generic Flask constructor that app.create_app delegates to.
    from app import _log_app_initialized, create_app  # noqa: PLC0415

    flask_app = create_app(active_config)
    _log_app_initialized(active_config, flask_app=flask_app, duration_ms=int((time.monotonic() - started) * 1000))
    return flask_app
