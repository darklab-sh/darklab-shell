#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
darklab_shell - Real-time bash command execution web app
Run: python3 app.py
Then open http://localhost:8888 or read the README.md for Docker instructions.
"""

import gzip
import logging
import os
from pathlib import Path
import time
import hashlib
import json
from uuid import uuid4

from flask import current_app, has_app_context, jsonify, request
from app_factory import create_app as _create_flask_app

from config import APP_VERSION, CFG
from runtime_bootstrap import bootstrap_runtime
from extensions import limiter
from core.helpers import get_client_ip, get_log_session_id, get_session_id
import core.process as process_state
from blueprints.assets import assets_bp
from blueprints.api_v1 import api_v1_bp
from blueprints.atlas import atlas_bp
from blueprints.content import content_bp
from blueprints.run import run_bp
from blueprints.history import history_bp
from blueprints.notifications import notifications_bp
from blueprints.schedules import schedules_bp
from blueprints.session import session_bp
from blueprints.secrets import secrets_bp
from blueprints.teams import teams_bp
from blueprints.watchers import watchers_bp
from blueprints.workspace import workspace_bp
from blueprints.workflows import workflows_bp
from blueprints.projects import projects_bp
from core.http_rate_limit import check_dynamic_route_rate_limit
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend
from core.process import redis_storage_uri
from services.workspace.files import cleanup_inactive_workspaces
from services.metrics_lazy import app_metrics
from services.api_v1.serialization import json_error

log = logging.getLogger("shell")

_WORKSPACE_CLEANUP_INTERVAL_SECONDS = 300
_SQLITE_WAL_CHECKPOINT_INTERVAL_SECONDS = 300
_last_workspace_cleanup_monotonic = 0.0
_last_sqlite_wal_checkpoint_monotonic = 0.0
_sqlite_wal_checkpoint_monotonic = time.monotonic
_REQUEST_COMPLETED_LOG_SKIP_PREFIXES = ("/static/", "/vendor/")
_REQUEST_COMPLETED_LOG_SKIP_PATHS = frozenset({"/favicon.ico"})
_REQUEST_COMPLETED_LOG_DEBUG_PATHS = frozenset({"/health", "/metrics", "/status"})
_IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
_IMMUTABLE_ASSET_PREFIXES = ("/static/", "/vendor/")
_REVALIDATED_STATIC_CACHE_CONTROL = "no-cache"
_REVALIDATED_STATIC_PREFIXES = ("/static/fragments/",)
_DYNAMIC_GZIP_MIN_BYTES = 1024
_DYNAMIC_GZIP_MIMETYPES = frozenset({"text/html"})
_ASSET_VERSION_CACHE: dict[str, str] = {}
_STATIC_ASSET_URL_CACHE: dict[str, str] = {}
_ASSET_MANIFEST_PATH = Path(__file__).resolve().parent / "static" / "build" / "manifest.json"
_VALID_ASSET_BUNDLE_MODES = frozenset({"source", "bundle"})
_WARNED_INVALID_ASSET_BUNDLE_MODES: set[str] = set()
_LOGGED_ASSET_BUNDLE_MODES: set[str] = set()
_REQUEST_ID_MAX_LENGTH = 64


def _bounded_request_id(value: object = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return uuid4().hex
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_", "."})
    return (safe or uuid4().hex)[:_REQUEST_ID_MAX_LENGTH]


def _current_request_id() -> str:
    return str(request.environ.get("darklab_request_id") or "")


def _active_static_folder() -> str:
    if has_app_context():
        return str(current_app.static_folder or "")
    return str(Path(__file__).resolve().parent / "static")


def _should_log_request_completed() -> bool:
    path = request.path or ""
    if path in _REQUEST_COMPLETED_LOG_SKIP_PATHS:
        return False
    return not path.startswith(_REQUEST_COMPLETED_LOG_SKIP_PREFIXES)


def _request_completed_log_level(status_code: int) -> int | None:
    if not _should_log_request_completed():
        return None
    path = request.path or ""
    if path in _REQUEST_COMPLETED_LOG_DEBUG_PATHS and 200 <= status_code < 400:
        return logging.DEBUG
    return logging.INFO


def _apply_immutable_asset_cache_headers(response):
    if request.method not in {"GET", "HEAD"} or response.status_code not in {200, 304}:
        return response
    path = request.path or ""
    if path.startswith(_REVALIDATED_STATIC_PREFIXES):
        response.headers["Cache-Control"] = _REVALIDATED_STATIC_CACHE_CONTROL
        return response
    if _is_source_module_asset(path) and _asset_bundle_mode() != "bundle":
        return response
    if path.startswith(_IMMUTABLE_ASSET_PREFIXES):
        response.headers["Cache-Control"] = _IMMUTABLE_ASSET_CACHE_CONTROL
    return response


def _gzip_dynamic_response(response):
    if request.method not in {"GET", "HEAD"} or response.status_code != 200:
        return response
    if response.direct_passthrough or response.headers.get("Content-Encoding"):
        return response
    if response.mimetype not in _DYNAMIC_GZIP_MIMETYPES:
        return response
    response.vary.add("Accept-Encoding")
    if request.accept_encodings.quality("gzip") <= 0:
        return response
    data = response.get_data()
    if len(data) < _DYNAMIC_GZIP_MIN_BYTES:
        return response
    compressed = gzip.compress(data, compresslevel=6)
    if len(compressed) >= len(data):
        return response
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    return response


def _versioned_asset_url(path: str) -> str:
    asset_path = str(path or "")
    if not asset_path.startswith(("/static/", "/vendor/")):
        return asset_path
    if asset_path not in _ASSET_VERSION_CACHE:
        _ASSET_VERSION_CACHE[asset_path] = _asset_version(asset_path)
    version = _ASSET_VERSION_CACHE[asset_path]
    separator = "&" if "?" in asset_path else "?"
    return f"{asset_path}{separator}v={version}" if version else asset_path


def _static_asset_url(path: str) -> str:
    asset_path = str(path or "")
    if not asset_path.startswith(("/static/", "/vendor/")):
        return asset_path
    if _asset_bundle_mode() != "bundle":
        if _is_source_module_asset(asset_path):
            return asset_path
        return _versioned_asset_url(asset_path)
    if asset_path not in _STATIC_ASSET_URL_CACHE:
        _STATIC_ASSET_URL_CACHE[asset_path] = _hashed_static_asset_url(asset_path)
    return _STATIC_ASSET_URL_CACHE[asset_path]


def _is_source_module_asset(path: str) -> bool:
    asset_path = str(path or "")
    return (
        asset_path.startswith("/static/js/")
        and asset_path.split("?", 1)[0].endswith(".js")
    )


def _hashed_static_asset_url(path: str) -> str:
    try:
        static_assets = _load_asset_manifest().get("static_assets")
    except RuntimeError:
        _log_asset_manifest_resolution_failed(logical_name=path, bundle_type="static", exc_info=True)
        raise
    if not isinstance(static_assets, dict):
        _log_asset_manifest_resolution_failed(logical_name=path, bundle_type="static")
        raise _asset_manifest_error("Asset manifest is incomplete: missing static_assets")
    entry = static_assets.get(path)
    if not isinstance(entry, dict):
        _log_asset_manifest_resolution_failed(logical_name=path, bundle_type="static")
        raise _asset_manifest_error(f"Asset manifest is incomplete: missing static asset {path}")
    built_path = str(entry.get("path") or "").strip()
    if not built_path:
        _log_asset_manifest_resolution_failed(logical_name=path, bundle_type="static")
        raise _asset_manifest_error(f"Asset manifest is incomplete: static asset {path} has no built path")
    return built_path


def _asset_version(path: str) -> str:
    local_path: Path | None = None
    if path.startswith("/static/"):
        local_path = Path(_active_static_folder()) / path.removeprefix("/static/")
    elif path.startswith("/vendor/"):
        vendor_path = path.removeprefix("/vendor/")
        if vendor_path.startswith("fonts/"):
            local_path = Path(_active_static_folder()) / vendor_path
        else:
            local_path = Path(_active_static_folder()) / "js/vendor" / vendor_path
    if local_path is None:
        return APP_VERSION
    try:
        return hashlib.sha256(local_path.read_bytes()).hexdigest()[:12]
    except OSError:
        log.warning("ASSET_VERSION_FALLBACK", exc_info=True, extra={
            "asset_path": path,
            "local_path": str(local_path),
            "fallback_version": APP_VERSION,
        })
        return APP_VERSION


def _asset_bundle_mode() -> str:
    mode = str(CFG.get("asset_bundle_mode") or "bundle").strip().lower()
    if mode in _VALID_ASSET_BUNDLE_MODES:
        if mode not in _LOGGED_ASSET_BUNDLE_MODES:
            _LOGGED_ASSET_BUNDLE_MODES.add(mode)
            extra = {"asset_bundle_mode": mode}
            if mode == "source":
                extra.update({
                    "source_request_profile": "direct-esm-import-graph",
                    "source_js_module_urls": "unversioned",
                })
            log.info("ASSET_BUNDLE_MODE_SELECTED", extra=extra)
        return mode
    if mode not in _WARNED_INVALID_ASSET_BUNDLE_MODES:
        _WARNED_INVALID_ASSET_BUNDLE_MODES.add(mode)
        log.warning("ASSET_BUNDLE_MODE_INVALID", extra={
            "configured_mode": mode,
            "fallback_mode": "bundle",
        })
    return "bundle"


def _asset_manifest_error(message: str) -> RuntimeError:
    return RuntimeError(f"{message}. Run assets:sync.")


def _log_asset_manifest_resolution_failed(
    *,
    logical_name: str,
    bundle_type: str = "",
    mode: str = "",
    exc_info=False,
) -> None:
    log.error("ASSET_MANIFEST_RESOLUTION_FAILED", exc_info=exc_info, extra={
        "bundle": logical_name,
        "bundle_type": bundle_type,
        "asset_bundle_mode": mode or _asset_bundle_mode(),
        "manifest_path": str(_ASSET_MANIFEST_PATH),
    })


def _load_asset_manifest() -> dict:
    try:
        with _ASSET_MANIFEST_PATH.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except OSError as exc:
        raise _asset_manifest_error(f"Asset manifest is missing at {_ASSET_MANIFEST_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise _asset_manifest_error(f"Asset manifest is invalid JSON at {_ASSET_MANIFEST_PATH}") from exc
    if not isinstance(manifest, dict):
        raise _asset_manifest_error("Asset manifest must be a JSON object")
    bundles = manifest.get("bundles")
    if not isinstance(bundles, dict):
        raise _asset_manifest_error("Asset manifest is incomplete: missing bundles")
    return manifest


def _asset_bundle_entry(logical_name: str) -> dict:
    bundle_name = str(logical_name or "").strip()
    if not bundle_name:
        _log_asset_manifest_resolution_failed(logical_name=bundle_name)
        raise _asset_manifest_error("Asset bundle name is required")
    try:
        bundles = _load_asset_manifest()["bundles"]
    except RuntimeError:
        _log_asset_manifest_resolution_failed(logical_name=bundle_name, exc_info=True)
        raise
    entry = bundles.get(bundle_name)
    if not isinstance(entry, dict):
        _log_asset_manifest_resolution_failed(logical_name=bundle_name)
        raise _asset_manifest_error(f"Asset manifest is incomplete: missing bundle {bundle_name}")
    return entry


def _asset_bundle(logical_name: str) -> list[str]:
    entry = _asset_bundle_entry(logical_name)
    bundle_type = str(entry.get("type") or "").strip()
    mode = _asset_bundle_mode()
    if bundle_type not in {"css", "js", "esm"}:
        _log_asset_manifest_resolution_failed(
            logical_name=logical_name,
            bundle_type=bundle_type,
            mode=mode,
        )
        raise _asset_manifest_error(f"Unsupported asset bundle type for {logical_name}: {bundle_type}")
    if mode == "bundle":
        built_path = str(entry.get("path") or "").strip()
        if not built_path:
            _log_asset_manifest_resolution_failed(
                logical_name=logical_name,
                bundle_type=bundle_type,
                mode=mode,
            )
            raise _asset_manifest_error(f"Asset manifest is incomplete: bundle {logical_name} has no built path")
        return [built_path]

    sources = entry.get("entries") if bundle_type == "esm" else entry.get("sources")
    if not isinstance(sources, list) or not sources:
        _log_asset_manifest_resolution_failed(
            logical_name=logical_name,
            bundle_type=bundle_type,
            mode=mode,
        )
        raise _asset_manifest_error(f"Asset manifest is incomplete: bundle {logical_name} has no sources")
    if bundle_type == "esm":
        return [str(source) for source in sources]
    return [_versioned_asset_url(str(source)) for source in sources]


def _asset_bundle_script_type(logical_name: str) -> str:
    entry = _asset_bundle_entry(logical_name)
    return "module" if str(entry.get("type") or "").strip() == "esm" else ""


def _rate_limit_handler(e):
    ip = get_client_ip()
    scope = "secrets" if request.path.startswith("/session/secrets") else "global"
    log.warning("RATE_LIMIT", extra={
        "ip": ip,
        "request_id": _current_request_id(),
        "path": request.path,
        "limit_policy": str(e.description),
        "scope": scope,
    })
    app_metrics.record_rate_limit_rejection(request.endpoint or "unknown", scope=scope)
    if request.path.startswith("/api/v1/"):
        return jsonify(json_error("rate_limited", "Rate limit exceeded. Please slow down.")), 429
    if request.path.startswith("/session/secrets"):
        retry_after = None
        limit = getattr(e, "limit", None)
        limit_item = getattr(limit, "limit", None)
        if limit_item and hasattr(limit_item, "get_expiry"):
            retry_after = int(limit_item.get_expiry())
        return jsonify({"error": "rate_limited", "retry_after": retry_after}), 429
    return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429


def _enforce_dynamic_route_rate_limit():
    result = check_dynamic_route_rate_limit(
        client_ip=get_client_ip(),
        path=request.path,
        cfg=CFG,
        redis_client=process_state.redis_client,
    )
    if result.allowed:
        return None
    log.warning("RATE_LIMIT", extra={
        "ip": get_client_ip(),
        "request_id": _current_request_id(),
        "path": request.path,
        "limit_policy": result.limit_policy,
        "scope": "http",
    })
    app_metrics.record_rate_limit_rejection(request.endpoint or "unknown", scope="http")
    if request.path.startswith("/api/v1/"):
        return jsonify(json_error("rate_limited", "Rate limit exceeded. Please slow down.")), 429
    return jsonify({"error": "rate_limited", "retry_after": result.retry_after}), 429


def _server_error_handler(e):
    app_metrics.record_unhandled_exception(request.endpoint or "unknown")
    try:
        session_for_log = get_log_session_id(get_session_id())
    except Exception:
        log.debug(
            "REQUEST_SESSION_RESOLUTION_FAILED",
            exc_info=True,
            extra={"method": request.method, "path": request.path, "request_id": _current_request_id()},
        )
        session_for_log = ""
    log.error("UNHANDLED_EXCEPTION", exc_info=True, extra={
        "ip": get_client_ip(),
        "session": session_for_log,
        "request_id": _current_request_id(),
        "method": request.method,
        "path": request.path,
        "status": 500,
    })
    if request.path.startswith("/api/v1/"):
        return jsonify(json_error("internal_error", "Internal server error.")), 500
    return jsonify({"error": "Internal server error"}), 500


def _run_periodic_workspace_cleanup():
    _maybe_cleanup_workspaces()
    _maybe_checkpoint_sqlite_wal()


def _maybe_cleanup_workspaces():
    global _last_workspace_cleanup_monotonic
    if not CFG.get("workspace_enabled"):
        return
    now = time.monotonic()
    if now - _last_workspace_cleanup_monotonic < _WORKSPACE_CLEANUP_INTERVAL_SECONDS:
        return
    _last_workspace_cleanup_monotonic = now
    try:
        removed = cleanup_inactive_workspaces(CFG, skip_session_id=get_session_id())
        if removed:
            log.info("WORKSPACE_CLEANUP", extra={"removed": removed})
    except Exception:
        log.exception("WORKSPACE_CLEANUP_ERROR")


def _maybe_checkpoint_sqlite_wal():
    global _last_sqlite_wal_checkpoint_monotonic
    if get_db_backend() != DatabaseBackend.SQLITE:
        return
    now = _sqlite_wal_checkpoint_monotonic()
    if now - _last_sqlite_wal_checkpoint_monotonic < _SQLITE_WAL_CHECKPOINT_INTERVAL_SECONDS:
        return
    _last_sqlite_wal_checkpoint_monotonic = now
    try:
        with get_db_connect()() as conn:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except Exception:
        log.warning("SQLITE_WAL_CHECKPOINT_FAILED", exc_info=True)
        return
    if not row:
        return
    busy = int(row[0] or 0)
    log_frames = int(row[1] or 0)
    checkpointed_frames = int(row[2] or 0)
    if busy or log_frames or checkpointed_frames:
        log.info("SQLITE_WAL_CHECKPOINT", extra={
            "busy": busy,
            "log_frames": log_frames,
            "checkpointed_frames": checkpointed_frames,
        })


def _log_request():
    request.environ["darklab_metrics_start"] = str(time.perf_counter())
    request.environ["darklab_request_id"] = _bounded_request_id(request.headers.get("X-Request-ID"))
    if log.isEnabledFor(logging.DEBUG):
        ip = get_client_ip()
        extra: dict = {"ip": ip, "request_id": _current_request_id(), "method": request.method, "path": request.path}
        if request.query_string:
            extra["query_keys"] = sorted(request.args.keys())
        log.debug("REQUEST", extra=extra)


def _log_response(response):
    response = _apply_immutable_asset_cache_headers(response)
    response = _gzip_dynamic_response(response)
    started = request.environ.get("darklab_metrics_start")
    try:
        elapsed = time.perf_counter() - float(started) if started else 0.0
    except (TypeError, ValueError):
        elapsed = 0.0
    app_metrics.record_http_request(
        request.method,
        request.endpoint or "unknown",
        response.status_code,
        elapsed,
    )
    request_completed_level = _request_completed_log_level(response.status_code)
    if request_completed_level is not None and log.isEnabledFor(request_completed_level):
        log_method = log.debug if request_completed_level <= logging.DEBUG else log.info
        log_method(
            "REQUEST_COMPLETED",
            extra={
                "ip": get_client_ip(),
                "session": get_log_session_id(),
                "request_id": _current_request_id(),
                "method": request.method,
                "path": request.path,
                "endpoint": request.endpoint or "unknown",
                "status": response.status_code,
                "duration_ms": int(elapsed * 1000),
            },
        )
    if log.isEnabledFor(logging.DEBUG):
        ip    = get_client_ip()
        extra = {
            "ip": ip, "request_id": _current_request_id(), "method": request.method,
            "path": request.path, "status": response.status_code,
        }
        if response.content_length is not None:
            extra["size"] = response.content_length
        log.debug("RESPONSE", extra=extra)
    return response


def create_app(config=None):
    active_config = CFG if config is None else config
    return _create_flask_app(
        active_config,
        import_name=__name__,
        template_folder="templates",
        limiter_extension=limiter,
        limiter_storage_uri=redis_storage_uri(active_config),
        jinja_globals={
            "static_asset": _static_asset_url,
            "asset_bundle": _asset_bundle,
            "asset_bundle_script_type": _asset_bundle_script_type,
        },
        blueprints=(
            assets_bp,
            api_v1_bp,
            atlas_bp,
            content_bp,
            run_bp,
            history_bp,
            notifications_bp,
            schedules_bp,
            session_bp,
            secrets_bp,
            teams_bp,
            watchers_bp,
            workspace_bp,
            workflows_bp,
            projects_bp,
        ),
        error_handlers={
            429: _rate_limit_handler,
            500: _server_error_handler,
        },
        before_request_handlers=(
            _enforce_dynamic_route_rate_limit,
            _run_periodic_workspace_cleanup,
            _log_request,
        ),
        after_request_handlers=(
            _log_response,
        ),
    )


def _log_app_initialized(config=None, *, flask_app=None, duration_ms: int | None = None) -> None:
    active_config = CFG if config is None else config
    storage_uri = redis_storage_uri(active_config)
    before_count = 0
    after_count = 0
    blueprint_count = 0
    app_name = ""
    if flask_app is not None:
        app_name = str(getattr(flask_app, "name", "") or "")
        blueprint_count = len(getattr(flask_app, "blueprints", {}) or {})
        before_count = sum(len(handlers) for handlers in getattr(flask_app, "before_request_funcs", {}).values())
        after_count = sum(len(handlers) for handlers in getattr(flask_app, "after_request_funcs", {}).values())
    log.info("APP_INITIALIZED", extra={
        "app_version": APP_VERSION,
        "database_backend": str(active_config.get("database_backend") or "sqlite"),
        "workspace_enabled": bool(active_config.get("workspace_enabled")),
        "pid": os.getpid(),
        "app_name": app_name,
        "blueprint_count": blueprint_count,
        "before_request_handlers": before_count,
        "after_request_handlers": after_count,
        "limiter_storage": "redis" if storage_uri.startswith("redis://") or storage_uri.startswith("rediss://") else "memory",
        "duration_ms": int(duration_ms or 0),
    })


def main() -> None:
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("darklab_shell running at http://localhost:8888")
    started = time.monotonic()
    bootstrap_runtime(CFG, cleanup_active_runs=True, runtime_name="dev")
    dev_app = create_app()
    _log_app_initialized(flask_app=dev_app, duration_ms=int((time.monotonic() - started) * 1000))
    dev_app.run(host="0.0.0.0", port=8888, threaded=True)  # nosec


if __name__ == "__main__":
    main()
