#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Create an operator backup for a darklab_shell deployment."""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import traceback
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml


def _application_root(script_path: Path) -> Path:
    for candidate in (script_path.resolve().parent, *script_path.resolve().parents):
        if (candidate / "app" / "config.py").is_file():
            return candidate
        if (candidate / "config.py").is_file() and (candidate / "core").is_dir():
            return candidate
    raise RuntimeError("could not locate the darklab_shell application root")


ROOT = Path(os.environ.get("DARKLAB_BACKUP_ROOT") or _application_root(Path(__file__)))
APP_DIR = Path(os.environ.get("DARKLAB_BACKUP_APP_DIR") or ROOT / "app")
DEFAULT_BACKUP_PREFIX = "darklab-backup"
DEFAULT_SQLITE_NAME = "history.db"
CHECKSUM_CHUNK_SIZE = 1024 * 1024
SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_-])(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|database[_-]?url|dsn)(?:$|[_-])",
    re.I,
)
DOCKER_VOLUME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
COMPOSE_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-|-)([^}]*))?\}")


class _ComposeLoader(yaml.SafeLoader):
    pass


def _compose_unknown_tag(loader: yaml.SafeLoader, _tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_ComposeLoader.add_multi_constructor("!", _compose_unknown_tag)


class BackupError(RuntimeError):
    """Raised when the requested backup cannot be completed safely."""


@dataclass
class BackupContext:
    args: argparse.Namespace
    output_dir: Path
    warnings: list[str] = field(default_factory=list)
    included: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    env_files_loaded: list[str] = field(default_factory=list)
    requested_inputs_prepared: bool = False
    retention: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceSource:
    kind: str
    logical_root: str
    source: str
    container: str = ""
    mount_destination: str = ""
    mount_type: str = ""


@dataclass(frozen=True)
class DataDirSource:
    kind: str
    logical_dir: str
    source: str
    source_label: str
    container: str = ""
    mount_destination: str = ""
    mount_type: str = ""


def _info(message: str) -> None:
    print(message, flush=True)


def _warn(ctx: BackupContext, message: str) -> None:
    ctx.warnings.append(message)
    print(f"warning: {message}", file=sys.stderr, flush=True)


def _record_command(ctx: BackupContext, label: str, command: Sequence[str], *, redacted: Sequence[str] | None = None) -> None:
    ctx.commands.append({
        "label": label,
        "command": list(redacted or command),
    })


def _run(
    ctx: BackupContext,
    command: Sequence[str],
    *,
    label: str,
    timeout: int,
    env: Mapping[str, str] | None = None,
    stdout: Any = subprocess.PIPE,
    redacted: Sequence[str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[Any]:
    _record_command(ctx, label, command, redacted=redacted)
    try:
        proc = subprocess.run(
            list(command),
            cwd=ROOT,
            env=dict(env) if env is not None else None,
            stdout=stdout,
            stderr=subprocess.PIPE,
            text=stdout is subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        if check:
            raise BackupError(f"{label} command not found: {command[0]}") from exc
        return subprocess.CompletedProcess(list(command), 127, "", str(exc))
    if check and proc.returncode != 0:
        stderr = proc.stderr if isinstance(proc.stderr, str) else (proc.stderr or b"").decode("utf-8", "replace")
        raise BackupError(f"{label} failed with exit code {proc.returncode}: {stderr.strip()}")
    return proc


def _parse_env_line(line: str) -> tuple[str, str] | None:
    value = line.strip()
    if not value or value.startswith("#"):
        return None
    if value.startswith("export "):
        value = value[len("export "):].lstrip()
    if "=" not in value:
        return None
    key, raw_value = value.split("=", 1)
    key = key.strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
        return None
    raw_value = raw_value.strip()
    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
        raw_value = raw_value[1:-1]
    return key, raw_value


def load_env_file(path: Path, *, override: bool = False) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        values[key] = value
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)
    return values


def _import_app_config(conf_dir: str | None):
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    import config as app_config  # noqa: PLC0415

    cfg = app_config.load_config(conf_dir=conf_dir) if conf_dir else app_config.load_config()
    return app_config, cfg


def _redact_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY_RE.search(key):
        if value in (None, "", []):
            return value
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(child_key): _redact_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _redact_config(cfg: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _redact_value(str(key), value) for key, value in cfg.items()}


def _path_for_manifest(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _safe_archive_rel(path: Path, *, category: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        return Path(category) / resolved.relative_to(ROOT)
    except ValueError:
        parts = [part for part in resolved.parts if part not in {resolved.anchor, os.sep, ""}]
        if resolved.drive:
            parts.insert(0, resolved.drive.rstrip(":"))
        return Path(category) / "absolute" / Path(*parts)


def _is_permission_error(exc: BaseException) -> bool:
    return isinstance(exc, PermissionError) or (
        isinstance(exc, OSError) and exc.errno in {errno.EACCES, errno.EPERM}
    )


def _shutil_error_has_permission_denial(exc: shutil.Error) -> bool:
    errors = exc.args[0] if exc.args else []
    if not isinstance(errors, list):
        return False
    for item in errors:
        if not isinstance(item, tuple) or len(item) < 3:
            continue
        detail = item[2]
        if isinstance(detail, BaseException) and _is_permission_error(detail):
            return True
        message = str(detail).lower()
        if "permission denied" in message or "operation not permitted" in message:
            return True
    return False


def _raise_unreadable_source(kind: str, source: Path | str, exc: BaseException) -> None:
    label = kind.replace("_", " ")
    hint = "Run the backup as a user that can read this path, or choose a readable source."
    if kind in {"database", "data_dir", "workspaces"}:
        hint = (
            "Docker bind-mounted deployments often lock these paths down to the image's app users. "
            "Run the backup as root on the Docker host, or use --data-source/--workspace-source "
            "with a readable bind path, Docker volume, or container source."
        )
    raise BackupError(f"{label} source is not readable by the current user: {source}. {hint}") from exc


def _stat_readable_source(path: Path, *, kind: str, missing_ok: bool = False) -> os.stat_result | None:
    try:
        return path.stat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    except OSError as exc:
        if _is_permission_error(exc):
            _raise_unreadable_source(kind, path, exc)
        raise


def _copy_file(ctx: BackupContext, source: Path, stage: Path, *, category: str, missing_ok: bool = False) -> Path | None:
    try:
        resolved = source.expanduser().resolve()
        source_stat = _stat_readable_source(resolved, kind=category, missing_ok=True)
    except OSError as exc:
        if _is_permission_error(exc):
            _raise_unreadable_source(category, source, exc)
        raise
    if source_stat is None:
        if missing_ok:
            excluded = {"kind": category, "source": str(source), "reason": "missing"}
            if excluded not in ctx.excluded:
                ctx.excluded.append(excluded)
            return None
        raise BackupError(f"requested file does not exist: {source}")
    if not stat.S_ISREG(source_stat.st_mode):
        raise BackupError(f"requested path is not a file: {source}")
    dest = stage / _safe_archive_rel(resolved, category=category)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(resolved, dest, follow_symlinks=False)
    except OSError as exc:
        if _is_permission_error(exc):
            _raise_unreadable_source(category, resolved, exc)
        raise
    ctx.included.append({"kind": category, "source": str(resolved), "archive_path": dest.relative_to(stage).as_posix()})
    return dest


def _copy_directory_contents(
    ctx: BackupContext,
    source: Path,
    destination: Path,
    *,
    kind: str,
    exclude: set[Path] | None = None,
    required: bool = True,
) -> None:
    try:
        resolved = source.expanduser().resolve()
        source_stat = _stat_readable_source(resolved, kind=kind, missing_ok=True)
    except OSError as exc:
        if _is_permission_error(exc):
            _raise_unreadable_source(kind, source, exc)
        raise
    if source_stat is None:
        if required:
            raise BackupError(f"{kind} source does not exist: {source}")
        ctx.excluded.append({"kind": kind, "source": str(source), "reason": "missing"})
        return
    if not stat.S_ISDIR(source_stat.st_mode):
        raise BackupError(f"{kind} source is not a directory: {source}")

    exclude_resolved = {path.resolve(strict=False) for path in (exclude or set())}

    def ignore(directory: str, names: list[str]) -> list[str]:
        ignored: list[str] = []
        for name in names:
            candidate = (Path(directory) / name).resolve(strict=False)
            if candidate in exclude_resolved:
                ignored.append(name)
                rel = candidate.relative_to(resolved).as_posix() if candidate.is_relative_to(resolved) else str(candidate)
                ctx.excluded.append({
                    "kind": kind,
                    "source": str(candidate),
                    "reason": "live-sqlite-snapshot",
                    "relative_path": rel,
                })
        return ignored

    destination.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(resolved, destination, symlinks=True, ignore=ignore, dirs_exist_ok=True)
    except shutil.Error as exc:
        if _shutil_error_has_permission_denial(exc):
            _raise_unreadable_source(kind, resolved, exc)
        raise
    except OSError as exc:
        if _is_permission_error(exc):
            _raise_unreadable_source(kind, resolved, exc)
        raise
    count, size = _directory_stats(destination)
    ctx.included.append({
        "kind": kind,
        "source": str(resolved),
        "archive_path": destination.name,
        "file_count": count,
        "bytes": size,
    })


def _directory_stats(path: Path) -> tuple[int, int]:
    count = 0
    size = 0
    if not path.exists():
        return count, size
    for item in path.rglob("*"):
        if item.is_symlink():
            continue
        if not item.is_file():
            continue
        count += 1
        try:
            size += item.stat().st_size
        except OSError:
            pass
    return count, size


def _sqlite_sidecar_paths(sqlite_db: Path) -> set[Path]:
    return {
        sqlite_db,
        Path(str(sqlite_db) + "-wal"),
        Path(str(sqlite_db) + "-shm"),
    }


def backup_sqlite_database(source_db: Path, destination_db: Path) -> None:
    source_stat = _stat_readable_source(source_db, kind="database", missing_ok=True)
    if source_stat is None:
        raise BackupError(f"SQLite database does not exist: {source_db}")
    if not stat.S_ISREG(source_stat.st_mode):
        raise BackupError(f"SQLite database source is not a file: {source_db}")
    destination_db.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source_db}?mode=ro"
    try:
        source_conn = sqlite3.connect(source_uri, uri=True)
    except sqlite3.OperationalError as exc:
        if "unable to open database file" in str(exc).lower():
            _raise_unreadable_source("database", source_db, exc)
        raise
    try:
        dest_conn = sqlite3.connect(destination_db)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()


def _postgres_env_from_url(database_url: str) -> tuple[dict[str, str], dict[str, str]]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise BackupError("DATABASE_URL must use postgresql:// for local pg_dump mode")
    database = parsed.path.lstrip("/")
    if not database:
        raise BackupError("DATABASE_URL must include a database name for local pg_dump mode")
    env: dict[str, str] = {
        "PGDATABASE": unquote(database),
    }
    redacted: dict[str, str] = {"PGDATABASE": env["PGDATABASE"]}
    if parsed.hostname:
        env["PGHOST"] = parsed.hostname
        redacted["PGHOST"] = parsed.hostname
    if parsed.port:
        env["PGPORT"] = str(parsed.port)
        redacted["PGPORT"] = str(parsed.port)
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
        redacted["PGUSER"] = env["PGUSER"]
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
        redacted["PGPASSWORD"] = "[redacted]"
    query = parse_qs(parsed.query)
    if query.get("sslmode"):
        env["PGSSLMODE"] = query["sslmode"][-1]
        redacted["PGSSLMODE"] = env["PGSSLMODE"]
    return env, redacted


def _database_url(cfg: Mapping[str, Any]) -> str:
    return str(cfg.get("database_url") or os.environ.get("DATABASE_URL") or "").strip()


def _postgres_identity_from_url(database_url: str) -> tuple[str, str]:
    parsed = urlparse(database_url)
    user = unquote(parsed.username) if parsed.username else os.environ.get("POSTGRES_USER", "darklab")
    database = (
        unquote(parsed.path.lstrip("/"))
        if parsed.path and parsed.path != "/"
        else os.environ.get("POSTGRES_DB", "darklab_shell")
    )
    return user or "darklab", database or "darklab_shell"


def _postgres_url_hostname(database_url: str) -> str:
    if not database_url:
        return ""
    parsed = urlparse(database_url)
    return (parsed.hostname or "").strip().lower()


def _postgres_url_uses_compose_service(
    ctx: BackupContext,
    cfg: Mapping[str, Any],
    compose_files: Sequence[Path],
) -> bool:
    host = _postgres_url_hostname(_database_url(cfg))
    if not host:
        return False
    service_names = _compose_service_names(ctx, compose_files)
    return host == ctx.args.postgres_service.lower() or host in {name.lower() for name in service_names}


def _postgres_dump_plan(ctx: BackupContext, cfg: Mapping[str, Any], compose_files: Sequence[Path]) -> dict[str, Any]:
    mode = ctx.args.postgres_dump_mode
    database_url = _database_url(cfg)
    compose_network_url = _postgres_url_uses_compose_service(ctx, cfg, compose_files)
    use_compose = mode == "compose" or (mode == "auto" and compose_network_url)
    compose_container = (
        _compose_service_container(ctx, compose_files, ctx.args.postgres_service)
        if use_compose and compose_files
        else ""
    )
    if mode == "compose":
        planned_mode = "compose"
    elif mode == "auto" and compose_network_url:
        planned_mode = "compose"
    else:
        planned_mode = "local"
    return {
        "requested_mode": mode,
        "planned_mode": planned_mode,
        "compose_service": ctx.args.postgres_service,
        "compose_container": compose_container,
        "database_url_host": _postgres_url_hostname(database_url),
    }


def _compose_base_command(args: argparse.Namespace, compose_files: Sequence[Path]) -> list[str]:
    command = ["docker", "compose"]
    if args.env_file:
        command.extend(["--env-file", str(Path(args.env_file).expanduser())])
    for compose_file in compose_files:
        command.extend(["-f", str(compose_file)])
    return command


def _default_compose_files(args: argparse.Namespace) -> list[Path]:
    if args.compose_file:
        return [Path(path).expanduser().resolve() for path in args.compose_file]
    default = ROOT / "docker-compose.yml"
    return [default] if default.exists() else []


def _compose_service_container(ctx: BackupContext, compose_files: Sequence[Path], service: str) -> str:
    if not compose_files:
        return ""
    command = [*_compose_base_command(ctx.args, compose_files), "ps", "-q", service]
    proc = _run(ctx, command, label=f"docker compose ps {service}", timeout=30, check=False)
    if proc.returncode != 0:
        return ""
    return str(proc.stdout or "").strip().splitlines()[0] if str(proc.stdout or "").strip() else ""


def _docker_inspect_mounts(ctx: BackupContext, container: str) -> list[dict[str, Any]] | None:
    if not container:
        return None
    command = ["docker", "inspect", container, "--format", "{{json .Mounts}}"]
    proc = _run(ctx, command, label="docker inspect mounts", timeout=30, check=False)
    if proc.returncode != 0:
        return None
    try:
        parsed = json.loads(str(proc.stdout or "[]"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _posix_relative(child: str, parent: str) -> str | None:
    child_path = PurePosixPath(child)
    parent_path = PurePosixPath(parent)
    if child_path == parent_path:
        return ""
    try:
        return child_path.relative_to(parent_path).as_posix()
    except ValueError:
        return None


def _configured_data_dir(cfg: Mapping[str, Any]) -> tuple[str, str]:
    env_data_dir = str(os.environ.get("APP_DATA_DIR") or "").strip()
    if env_data_dir:
        return env_data_dir, "APP_DATA_DIR"
    cfg_data_dir = str(cfg.get("data_dir") or "").strip()
    if cfg_data_dir:
        return cfg_data_dir, "data_dir"
    return "/data", "default"


def _interpolate_compose_value(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        operator = match.group(2) or ""
        fallback = match.group(3) or ""
        env_value = os.environ.get(name)
        if env_value is None or (operator == ":-" and env_value == ""):
            return fallback
        return env_value

    return COMPOSE_ENV_RE.sub(replace, value)


def _compose_project_dir(compose_files: Sequence[Path]) -> Path:
    return compose_files[0].parent if compose_files else ROOT


def _load_compose_file(ctx: BackupContext, compose_file: Path) -> Mapping[str, Any] | None:
    if not compose_file.exists():
        return None
    try:
        compose = yaml.load(compose_file.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}
    except yaml.YAMLError as exc:
        _warn(ctx, f"could not parse Compose file {compose_file}: {exc}")
        return None
    if not isinstance(compose, Mapping):
        return None
    return compose


def _compose_service_config(ctx: BackupContext, compose_file: Path, service: str) -> Mapping[str, Any] | None:
    compose = _load_compose_file(ctx, compose_file)
    if compose is None:
        return None
    services = compose.get("services")
    if not isinstance(services, Mapping):
        return None
    service_config = services.get(service)
    return service_config if isinstance(service_config, Mapping) else None


def _compose_service_names(ctx: BackupContext, compose_files: Sequence[Path]) -> set[str]:
    names: set[str] = set()
    for compose_file in compose_files:
        compose = _load_compose_file(ctx, compose_file)
        if compose is None:
            continue
        services = compose.get("services")
        if isinstance(services, Mapping):
            names.update(str(name) for name in services)
    return names


def _compose_mount_source_path(project_dir: Path, source: str) -> str:
    raw = _interpolate_compose_value(source).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = project_dir / path
    return str(path.resolve(strict=False))


def _split_compose_volume_short_syntax(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    brace_depth = 0
    index = 0
    while index < len(value):
        char = value[index]
        if char == "$" and index + 1 < len(value) and value[index + 1] == "{":
            brace_depth += 1
            current.extend(["$", "{"])
            index += 2
            continue
        if char == "}" and brace_depth:
            brace_depth -= 1
            current.append(char)
            index += 1
            continue
        if char == ":" and brace_depth == 0:
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _compose_volume_mount(entry: Any, project_dir: Path) -> tuple[str, str, str] | None:
    if isinstance(entry, str):
        parts = _split_compose_volume_short_syntax(entry)
        if len(parts) < 2:
            return None
        source = _interpolate_compose_value(parts[0]).strip()
        target = _interpolate_compose_value(parts[1]).strip()
        if not source or not target.startswith("/"):
            return None
        kind = "bind" if source.startswith(("/", ".", "~")) else "volume"
        if kind == "bind":
            source = _compose_mount_source_path(project_dir, source)
        return kind, target, source

    if not isinstance(entry, Mapping):
        return None
    target = str(entry.get("target") or entry.get("dst") or entry.get("destination") or "").strip()
    if not target.startswith("/"):
        return None
    kind = str(entry.get("type") or "").strip().lower()
    source = str(entry.get("source") or entry.get("src") or "").strip()
    if not kind:
        kind = "bind" if source.startswith(("/", ".", "~")) else "volume"
    if kind == "tmpfs":
        return "tmpfs", target, ""
    if not source:
        return None
    source = _interpolate_compose_value(source).strip()
    if kind == "bind":
        source = _compose_mount_source_path(project_dir, source)
    return kind, target, source


def _data_source_from_mount(
    *,
    logical_dir: str,
    kind: str,
    source: str,
    destination: str,
    source_label: str,
    container: str = "",
    mount_type: str = "",
) -> DataDirSource | None:
    relative = _posix_relative(logical_dir, destination)
    if relative is None:
        return None
    if kind == "bind":
        source_path = Path(source).expanduser()
        if relative:
            source_path = source_path / relative
        return DataDirSource(
            kind="bind",
            logical_dir=logical_dir,
            source=str(source_path.resolve(strict=False)),
            source_label=source_label,
            container=container,
            mount_destination=destination,
            mount_type=mount_type or kind,
        )
    if kind == "volume":
        return DataDirSource(
            kind="volume",
            logical_dir=logical_dir,
            source=source,
            source_label=source_label,
            container=container,
            mount_destination=destination,
            mount_type=mount_type or kind,
        )
    if kind == "tmpfs":
        if not container:
            return None
        return DataDirSource(
            kind="container",
            logical_dir=logical_dir,
            source=logical_dir,
            source_label=source_label,
            container=container,
            mount_destination=destination,
            mount_type=mount_type or kind,
        )
    return None


def _compose_data_dir_source(
    ctx: BackupContext,
    compose_files: Sequence[Path],
    service: str,
    logical_dir: str,
) -> DataDirSource | None:
    source: DataDirSource | None = None
    project_dir = _compose_project_dir(compose_files)
    for compose_file in compose_files:
        service_config = _compose_service_config(ctx, compose_file, service)
        if service_config is None:
            continue
        volumes = service_config.get("volumes") or []
        if not isinstance(volumes, Sequence) or isinstance(volumes, (str, bytes)):
            continue
        for entry in volumes:
            mount = _compose_volume_mount(entry, project_dir)
            if mount is None:
                continue
            kind, destination, mount_source = mount
            resolved = _data_source_from_mount(
                logical_dir=logical_dir,
                kind=kind,
                source=mount_source,
                destination=destination,
                source_label=f"compose:{compose_file}",
                mount_type=kind,
            )
            if resolved is not None:
                source = resolved
    return source


def _container_data_dir_source(
    ctx: BackupContext,
    compose_files: Sequence[Path],
    logical_dir: str,
) -> DataDirSource | None:
    container = str(ctx.args.docker_container or "").strip()
    if not container:
        container = _compose_service_container(ctx, compose_files, ctx.args.compose_service)
    if not container and ctx.args.compose_service == "shell":
        container = "darklab_shell"
    if not container:
        return None

    mounts = _docker_inspect_mounts(ctx, container)
    if mounts is None:
        return None
    for mount in mounts:
        destination = str(mount.get("Destination") or "")
        mount_type = str(mount.get("Type") or "")
        source = str(mount.get("Source") or mount.get("Name") or "")
        resolved = _data_source_from_mount(
            logical_dir=logical_dir,
            kind=mount_type,
            source=source,
            destination=destination,
            source_label="docker-inspect",
            container=container,
            mount_type=mount_type,
        )
        if resolved is not None:
            return resolved
    return None


def _parse_data_source(value: str, logical_dir: str) -> DataDirSource:
    if value.startswith("bind:"):
        source = value[len("bind:"):].strip()
        if not source:
            raise BackupError("--data-source bind: requires a path")
        return DataDirSource(kind="bind", logical_dir=logical_dir, source=str(Path(source).expanduser()), source_label="operator")
    if value.startswith("volume:"):
        source = value[len("volume:"):].strip()
        if not DOCKER_VOLUME_RE.match(source):
            raise BackupError("--data-source volume: requires a Docker volume name")
        return DataDirSource(kind="volume", logical_dir=logical_dir, source=source, source_label="operator")
    if value.startswith("container:"):
        rest = value[len("container:"):]
        container, sep, path = rest.partition(":")
        if not sep or not container.strip() or not path.strip():
            raise BackupError("--data-source container: requires container:/path")
        logical = path.strip()
        return DataDirSource(
            kind="container",
            logical_dir=logical,
            source=logical,
            source_label="operator",
            container=container.strip(),
        )
    raise BackupError("--data-source must use bind:/path, volume:name, or container:name:/path")


def resolve_data_dir_source(
    ctx: BackupContext,
    app_config: Any,
    cfg: Mapping[str, Any],
    compose_files: Sequence[Path],
) -> DataDirSource:
    logical_dir, source_label = _configured_data_dir(cfg)
    if ctx.args.data_source:
        return _parse_data_source(ctx.args.data_source, logical_dir)

    logical_host_path = Path(logical_dir).expanduser()
    if source_label != "default" and logical_host_path.exists():
        return DataDirSource(
            kind="bind",
            logical_dir=logical_dir,
            source=str(logical_host_path.resolve(strict=False)),
            source_label=source_label,
        )

    compose_source = _compose_data_dir_source(ctx, compose_files, ctx.args.compose_service, logical_dir)
    if compose_source is not None and compose_source.kind == "bind":
        return compose_source

    container_source = _container_data_dir_source(ctx, compose_files, logical_dir)
    if container_source is not None:
        return container_source
    if compose_source is not None:
        return compose_source

    if logical_host_path.exists():
        return DataDirSource(
            kind="bind",
            logical_dir=logical_dir,
            source=str(logical_host_path.resolve(strict=False)),
            source_label=source_label,
        )

    resolved = Path(app_config.resolve_data_dir(cfg)).expanduser().resolve()
    if source_label == "default" and str(resolved) != logical_dir:
        _warn(ctx, f"data_dir default {logical_dir!r} was not resolved from Compose/Docker; using local fallback {resolved}")
    return DataDirSource(kind="local", logical_dir=logical_dir, source=str(resolved), source_label=source_label)


def _host_data_dir_path(source: DataDirSource) -> Path:
    if source.kind in {"bind", "local"}:
        return Path(source.source).expanduser().resolve()
    raise BackupError(
        f"data_dir {source.logical_dir!r} is backed by {source.kind!r}; "
        "SQLite online backups require a host-readable bind path. Use --data-source bind:/path "
        "or run the script where data_dir is mounted locally."
    )


def _compose_service_environment_value(
    ctx: BackupContext,
    compose_files: Sequence[Path],
    service: str,
    name: str,
) -> str:
    value = ""
    for compose_file in compose_files:
        service_config = _compose_service_config(ctx, compose_file, service)
        if service_config is None:
            continue
        environment = service_config.get("environment") or {}
        if isinstance(environment, Mapping):
            if name in environment:
                raw = environment.get(name)
                value = "" if raw is None else _interpolate_compose_value(str(raw)).strip()
            continue
        if not isinstance(environment, Sequence) or isinstance(environment, (str, bytes)):
            continue
        for item in environment:
            raw_item = str(item)
            key, sep, raw_value = raw_item.partition("=")
            if key.strip() != name:
                continue
            if sep:
                value = _interpolate_compose_value(raw_value).strip()
            else:
                value = str(os.environ.get(name) or "").strip()
    return value


def _workspace_logical_root(ctx: BackupContext, cfg: Mapping[str, Any], compose_files: Sequence[Path]) -> str:
    explicit = str(ctx.args.workspace_root or "").strip()
    if explicit:
        return explicit
    if ctx.args.compose_file:
        compose_root = _compose_service_environment_value(ctx, compose_files, ctx.args.compose_service, "WORKSPACE_ROOT")
        if compose_root:
            return compose_root
    return str(cfg.get("workspace_root") or "").strip()


def _compose_workspace_source(
    ctx: BackupContext,
    compose_files: Sequence[Path],
    service: str,
    logical_root: str,
) -> WorkspaceSource | None:
    source: WorkspaceSource | None = None
    project_dir = _compose_project_dir(compose_files)
    for compose_file in compose_files:
        service_config = _compose_service_config(ctx, compose_file, service)
        if service_config is None:
            continue
        volumes = service_config.get("volumes") or []
        if not isinstance(volumes, Sequence) or isinstance(volumes, (str, bytes)):
            continue
        for entry in volumes:
            mount = _compose_volume_mount(entry, project_dir)
            if mount is None:
                continue
            kind, destination, mount_source = mount
            relative = _posix_relative(logical_root, destination)
            if relative is None:
                continue
            if kind == "bind":
                source_path = Path(mount_source).expanduser()
                if relative:
                    source_path = source_path / relative
                source = WorkspaceSource(
                    kind="bind",
                    logical_root=logical_root,
                    source=str(source_path.resolve(strict=False)),
                    mount_destination=destination,
                    mount_type=kind,
                )
            elif kind == "volume":
                source = WorkspaceSource(
                    kind="volume",
                    logical_root=logical_root,
                    source=mount_source,
                    mount_destination=destination,
                    mount_type=kind,
                )
    return source


def _parse_workspace_source(value: str, logical_root: str) -> WorkspaceSource:
    if value.startswith("bind:"):
        source = value[len("bind:"):].strip()
        if not source:
            raise BackupError("--workspace-source bind: requires a path")
        return WorkspaceSource(kind="bind", logical_root=logical_root, source=source)
    if value.startswith("volume:"):
        source = value[len("volume:"):].strip()
        if not DOCKER_VOLUME_RE.match(source):
            raise BackupError("--workspace-source volume: requires a Docker volume name")
        return WorkspaceSource(kind="volume", logical_root=logical_root, source=source)
    if value.startswith("container:"):
        rest = value[len("container:"):]
        container, sep, path = rest.partition(":")
        if not sep or not container.strip() or not path.strip():
            raise BackupError("--workspace-source container: requires container:/path")
        return WorkspaceSource(kind="container", logical_root=path.strip(), source=path.strip(), container=container.strip())
    raise BackupError("--workspace-source must use bind:/path, volume:name, or container:name:/path")


def _skip_ephemeral_workspace(ctx: BackupContext, logical_root: str, reason: str) -> WorkspaceSource | None:
    message = (
        f"workspace root {logical_root!r} is ephemeral; "
        "use --include-ephemeral-workspaces or --workspace-source to include it"
    )
    ctx.excluded.append({"kind": "workspaces", "source": logical_root, "reason": reason})
    if ctx.args.include_workspaces == "always":
        raise BackupError(message)
    return None


def _skip_missing_ephemeral_container(ctx: BackupContext, logical_root: str, container: str) -> WorkspaceSource | None:
    target = f"container {container!r}" if container else f"Compose service {ctx.args.compose_service!r}"
    message = (
        f"workspace root {logical_root!r} is ephemeral but {target} is not running or inspectable; "
        "start the app container or use --workspace-source"
    )
    ctx.excluded.append({"kind": "workspaces", "source": logical_root, "reason": "container-unavailable"})
    if ctx.args.include_workspaces == "always":
        raise BackupError(message)
    _warn(ctx, message)
    return None


def resolve_workspace_source(
    ctx: BackupContext,
    cfg: Mapping[str, Any],
    compose_files: Sequence[Path],
) -> WorkspaceSource | None:
    if ctx.args.include_workspaces == "never":
        ctx.excluded.append({"kind": "workspaces", "reason": "disabled-by-operator"})
        return None

    logical_root = _workspace_logical_root(ctx, cfg, compose_files)
    if ctx.args.workspace_source:
        if not logical_root:
            raise BackupError(
                "--workspace-source requires a logical workspace root from "
                "--workspace-root, Compose, or app config"
            )
        return _parse_workspace_source(ctx.args.workspace_source, logical_root)

    if not bool(cfg.get("workspace_enabled")):
        ctx.excluded.append({"kind": "workspaces", "reason": "workspace-disabled"})
        return None

    if not logical_root:
        if ctx.args.include_workspaces == "always":
            raise BackupError("workspace_enabled is true but workspace_root is empty")
        _warn(ctx, "workspace_enabled is true but workspace_root is empty; skipping workspaces")
        return None

    workspace_backend = str(cfg.get("workspace_backend") or "tmpfs").strip().lower()
    if workspace_backend == "tmpfs" and not ctx.args.include_ephemeral_workspaces:
        return _skip_ephemeral_workspace(ctx, logical_root, "tmpfs-workspace")

    compose_source = _compose_workspace_source(ctx, compose_files, ctx.args.compose_service, logical_root)
    if compose_source is not None:
        return compose_source

    container = str(ctx.args.docker_container or "").strip()
    if not container:
        container = _compose_service_container(ctx, compose_files, ctx.args.compose_service)
    if not container and ctx.args.compose_service == "shell":
        container = "darklab_shell"

    container_available = False
    if container:
        mounts = _docker_inspect_mounts(ctx, container)
        if mounts is not None:
            container_available = True
        for mount in mounts or []:
            destination = str(mount.get("Destination") or "")
            relative = _posix_relative(logical_root, destination)
            if relative is None:
                continue
            mount_type = str(mount.get("Type") or "")
            if mount_type == "bind":
                source = Path(str(mount.get("Source") or ""))
                if relative:
                    source = source / relative
                return WorkspaceSource(
                    kind="bind",
                    logical_root=logical_root,
                    source=str(source),
                    container=container,
                    mount_destination=destination,
                    mount_type=mount_type,
                )
            if mount_type == "volume":
                return WorkspaceSource(
                    kind="volume",
                    logical_root=logical_root,
                    source=str(mount.get("Name") or mount.get("Source") or ""),
                    container=container,
                    mount_destination=destination,
                    mount_type=mount_type,
                )
            if mount_type == "tmpfs":
                if ctx.args.include_ephemeral_workspaces:
                    return WorkspaceSource(
                        kind="container",
                        logical_root=logical_root,
                        source=logical_root,
                        container=container,
                        mount_destination=destination,
                        mount_type=mount_type,
                    )
                return _skip_ephemeral_workspace(ctx, logical_root, "tmpfs-mount")

    if workspace_backend == "tmpfs":
        if ctx.args.include_ephemeral_workspaces and container_available:
            return WorkspaceSource(kind="container", logical_root=logical_root, source=logical_root, container=container)
        if ctx.args.include_ephemeral_workspaces:
            return _skip_missing_ephemeral_container(ctx, logical_root, container)
        return _skip_ephemeral_workspace(ctx, logical_root, "tmpfs-workspace")

    host_path = Path(logical_root).expanduser()
    if host_path.exists():
        return WorkspaceSource(kind="bind", logical_root=logical_root, source=str(host_path))

    if ctx.args.include_ephemeral_workspaces and container_available:
        return WorkspaceSource(kind="container", logical_root=logical_root, source=logical_root, container=container)

    message = (
        f"workspace root {logical_root!r} is enabled but no host/volume source was resolved; "
        "use --workspace-source or --include-ephemeral-workspaces"
    )
    if ctx.args.include_workspaces == "always":
        raise BackupError(message)
    _warn(ctx, message)
    ctx.excluded.append({"kind": "workspaces", "source": logical_root, "reason": "unresolved-source"})
    return None


def _docker_cp(ctx: BackupContext, container: str, source_path: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    command = ["docker", "cp", f"{container}:{source_path.rstrip('/')}/.", str(destination)]
    _run(ctx, command, label="docker cp workspace", timeout=ctx.args.command_timeout)


def _export_docker_volume(ctx: BackupContext, volume_name: str, destination: Path) -> None:
    if not DOCKER_VOLUME_RE.match(volume_name):
        raise BackupError(f"invalid Docker volume name: {volume_name}")
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{volume_name}:/source:ro",
        "-v",
        f"{destination}:/backup",
        ctx.args.volume_export_image,
        "sh",
        "-c",
        "cd /source && tar cf - . | tar xf - -C /backup",
    ]
    _run(ctx, command, label="docker volume export", timeout=ctx.args.command_timeout)


def copy_workspace(ctx: BackupContext, source: WorkspaceSource, stage: Path) -> None:
    destination = stage / "workspaces"
    if source.kind == "bind":
        _copy_directory_contents(ctx, Path(source.source), destination, kind="workspaces")
    elif source.kind == "container":
        _docker_cp(ctx, source.container, source.logical_root, destination)
        count, size = _directory_stats(destination)
        ctx.included.append({
            "kind": "workspaces",
            "source": f"{source.container}:{source.logical_root}",
            "archive_path": "workspaces",
            "file_count": count,
            "bytes": size,
        })
    elif source.kind == "volume":
        if source.container:
            _docker_cp(ctx, source.container, source.logical_root, destination)
        else:
            _export_docker_volume(ctx, source.source, destination)
        count, size = _directory_stats(destination)
        ctx.included.append({
            "kind": "workspaces",
            "source": source.source,
            "archive_path": "workspaces",
            "file_count": count,
            "bytes": size,
            "mount_type": source.mount_type or "volume",
        })
    else:
        raise BackupError(f"unsupported workspace source kind: {source.kind}")


def copy_data_dir(ctx: BackupContext, source: DataDirSource, stage: Path, *, exclude: set[Path]) -> None:
    destination = stage / "data"
    if source.kind in {"bind", "local"}:
        _copy_directory_contents(ctx, Path(source.source), destination, kind="data_dir", exclude=exclude)
    elif source.kind == "container":
        _docker_cp(ctx, source.container, source.logical_dir, destination)
        count, size = _directory_stats(destination)
        ctx.included.append({
            "kind": "data_dir",
            "source": f"{source.container}:{source.logical_dir}",
            "archive_path": "data",
            "file_count": count,
            "bytes": size,
        })
    elif source.kind == "volume":
        if source.container:
            _docker_cp(ctx, source.container, source.logical_dir, destination)
        else:
            _export_docker_volume(ctx, source.source, destination)
        count, size = _directory_stats(destination)
        ctx.included.append({
            "kind": "data_dir",
            "source": source.source,
            "archive_path": "data",
            "file_count": count,
            "bytes": size,
            "mount_type": source.mount_type or "volume",
        })
    else:
        raise BackupError(f"unsupported data_dir source kind: {source.kind}")


def backup_postgres(ctx: BackupContext, cfg: Mapping[str, Any], destination: Path, compose_files: Sequence[Path]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    plan = _postgres_dump_plan(ctx, cfg, compose_files)
    mode = str(plan["requested_mode"])
    planned_mode = str(plan["planned_mode"])
    if mode == "compose" and not compose_files:
        raise BackupError("Postgres dump mode 'compose' requires a Compose file")

    if planned_mode == "compose":
        user, database = _postgres_identity_from_url(_database_url(cfg))
        command = [
            *_compose_base_command(ctx.args, compose_files),
            "exec",
            "-T",
            ctx.args.postgres_service,
            "pg_dump",
            "-U",
            user,
            "-d",
            database,
            "--format=custom",
            "--no-owner",
            "--no-acl",
        ]
        with destination.open("wb") as handle:
            _run(ctx, command, label="compose pg_dump", timeout=ctx.args.command_timeout, stdout=handle)
        return

    database_url = _database_url(cfg)
    if not database_url:
        raise BackupError("database_backend is postgres but DATABASE_URL/database_url is empty")
    pg_env, redacted_env = _postgres_env_from_url(database_url)
    command_env = os.environ.copy()
    command_env.update(pg_env)
    command = [ctx.args.pg_dump_command, "--format=custom", "--no-owner", "--no-acl", "--file", str(destination)]
    _record_command(ctx, "pg_dump environment", [f"{key}={value}" for key, value in redacted_env.items()])
    _run(ctx, command, label="pg_dump", timeout=ctx.args.command_timeout, env=command_env)


def include_config_files(ctx: BackupContext, stage: Path, compose_files: Sequence[Path]) -> None:
    conf_dir = Path(ctx.args.conf_dir).expanduser().resolve() if ctx.args.conf_dir else APP_DIR / "conf"
    if getattr(ctx.args, "repository_free", False):
        local_conf_dir = Path(ctx.args.local_conf_dir).expanduser().resolve()
        _copy_directory_contents(
            ctx,
            local_conf_dir,
            stage / "operator" / "conf",
            kind="local_config",
        )
        env_file = Path(ctx.args.env_file).expanduser().resolve()
        operator_env = stage / "operator" / ".env"
        operator_env.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_file, operator_env)
        operator_env.chmod(0o600)
        ctx.included.append({
            "kind": "env",
            "source": str(env_file),
            "archive_path": "operator/.env",
        })
        release_dir = stage / "release"
        release_dir.mkdir()
        for compose_file in compose_files:
            if compose_file.exists():
                destination = release_dir / compose_file.name
                shutil.copy2(compose_file, destination)
                ctx.included.append({
                    "kind": "compose",
                    "source": str(compose_file),
                    "archive_path": destination.relative_to(stage).as_posix(),
                })
        for extra in ctx.args.extra_file or []:
            source = Path(extra).expanduser().resolve()
            destination = release_dir / source.name
            if destination.exists():
                raise BackupError(f"duplicate repository-free release file name: {source.name}")
            source_stat = _stat_readable_source(source, kind="extra", missing_ok=True)
            if source_stat is None:
                if ctx.args.ignore_missing_extra_file:
                    ctx.excluded.append({"kind": "extra", "source": str(source), "reason": "missing"})
                    continue
                raise BackupError(f"requested file does not exist: {source}")
            shutil.copy2(source, destination)
            ctx.included.append({
                "kind": "extra",
                "source": str(source),
                "archive_path": destination.relative_to(stage).as_posix(),
            })
        return

    copied: set[Path] = set()

    def copy_once(path: Path, *, missing_ok: bool = False) -> None:
        resolved = path.expanduser().resolve()
        if resolved in copied:
            return
        copied.add(resolved)
        _copy_file(ctx, resolved, stage, category="config", missing_ok=missing_ok)

    for path in sorted(conf_dir.rglob("*.yaml")):
        copy_once(path)
    for path in sorted(conf_dir.rglob("*.local.*")):
        copy_once(path, missing_ok=True)

    root_compose_files = sorted(ROOT.glob("docker-compose*.yml")) + sorted(ROOT.glob("docker-compose*.yaml"))
    for path in [*root_compose_files, *compose_files]:
        if path.exists():
            copy_once(path)

    env_file = Path(ctx.args.env_file).expanduser().resolve() if ctx.args.env_file else ROOT / ".env"
    if env_file.exists():
        copy_once(env_file)
    for extra_env_file in ctx.args.env_file_multi or []:
        path = Path(extra_env_file).expanduser().resolve()
        if path.exists():
            copy_once(path)

    for extra in ctx.args.extra_file or []:
        _copy_file(ctx, Path(extra), stage, category="extra", missing_ok=ctx.args.ignore_missing_extra_file)


def write_restore_notes(stage: Path) -> None:
    notes = stage / "RESTORE.md"
    notes.write_text(
        "\n".join([
            "# darklab_shell Backup Restore Notes",
            "",
            "This archive contains sensitive deployment data. Protect it like production secrets.",
            "",
            "Restore outline:",
            "",
            "1. Stop the running darklab_shell app before replacing database or filesystem state.",
            "2. Restore `data/` to the host path mounted as `/data`, keeping owner-only permissions.",
            "3. Restore `config/` files, including `.env` or local overlays, before starting containers.",
            "4. Restore `database/history.db` for SQLite, or restore `database/postgres.dump` with `pg_restore` for Postgres.",
            "5. Restore `workspaces/` to the host bind mount or Docker volume recorded in `manifest.json`.",
            "6. Keep the same `SECRETS_MASTER_KEY` value or restored `.secrets_master_key` file "
            "so encrypted vault rows stay readable.",
            "",
            "For Docker bind mounts, preserve the numeric app user/group ownership documented for the image. ",
            "For Docker named volumes, import the workspace files back through Docker instead of writing under "
            "Docker's internal volume path.",
            "",
        ]),
        encoding="utf-8",
    )


def _git_sha() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return "unknown"
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def build_manifest(
    ctx: BackupContext,
    *,
    cfg: Mapping[str, Any],
    app_version: str,
    data_source: DataDirSource,
    database: dict[str, Any],
    workspace_source: WorkspaceSource | None,
    stage: Path,
) -> dict[str, Any]:
    file_count, total_bytes = _directory_stats(stage)
    manifest = {
        "format": "darklab_shell.backup.v1",
        "repository_free": bool(getattr(ctx.args, "repository_free", False)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "app_version": app_version,
        "git_sha": _git_sha(),
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "database": database,
        "data_dir": {
            "kind": data_source.kind,
            "logical_dir": data_source.logical_dir,
            "source": data_source.source,
            "source_label": data_source.source_label,
            "container": data_source.container,
            "mount_destination": data_source.mount_destination,
            "mount_type": data_source.mount_type,
        },
        "workspace": None,
        "config": {
            "env_files_loaded": ctx.env_files_loaded,
            "effective_config_redacted": _redact_config(cfg),
        },
        "included": ctx.included,
        "excluded": ctx.excluded,
        "commands": ctx.commands,
        "warnings": ctx.warnings,
        "retention": ctx.retention,
        "totals": {
            "files": file_count,
            "bytes": total_bytes,
        },
    }
    if workspace_source is not None:
        manifest["workspace"] = {
            "kind": workspace_source.kind,
            "logical_root": workspace_source.logical_root,
            "source": workspace_source.source,
            "container": workspace_source.container,
            "mount_destination": workspace_source.mount_destination,
            "mount_type": workspace_source.mount_type,
        }
    return manifest


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _sha256_file(path: Path, *, chunk_size: int = CHECKSUM_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(stage: Path) -> None:
    rows: list[str] = []
    for path in sorted(stage.rglob("*")):
        if path.name == "checksums.sha256":
            continue
        if path.is_symlink():
            target = os.readlink(path)
            digest = hashlib.sha256(f"symlink:{target}".encode("utf-8")).hexdigest()
            rows.append(f"{digest}  {path.relative_to(stage).as_posix()}")
            continue
        if not path.is_file():
            continue
        digest = _sha256_file(path)
        rows.append(f"{digest}  {path.relative_to(stage).as_posix()}")
    checksum_path = stage / "checksums.sha256"
    checksum_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    checksum_path.chmod(0o600)


def _archive_stage(stage: Path, archive_path: Path, top_level: str) -> None:
    descriptor, tmp_name = tempfile.mkstemp(
        prefix=f".{archive_path.name}.",
        suffix=".tmp",
        dir=archive_path.parent,
    )
    os.close(descriptor)
    tmp_archive = Path(tmp_name)
    try:
        with tarfile.open(tmp_archive, "w:gz") as tar:
            for item in sorted(stage.iterdir()):
                tar.add(item, arcname=str(Path(top_level) / item.name), recursive=True)
        tmp_archive.chmod(0o600)
        try:
            os.link(tmp_archive, archive_path)
        except FileExistsError as exc:
            raise BackupError(f"backup destination already exists: {archive_path}") from exc
    finally:
        tmp_archive.unlink(missing_ok=True)


def _check_output_permissions(ctx: BackupContext, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(output_dir.stat().st_mode)
    except OSError:
        return
    if mode & 0o077:
        _warn(ctx, f"backup output directory {output_dir} is accessible by group/other; backups contain secrets")


@contextmanager
def _backup_lock(ctx: BackupContext) -> Iterator[None]:
    lock_path = Path(ctx.args.lock_file).expanduser() if ctx.args.lock_file else ctx.output_dir / ".backup.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BackupError(f"another backup is already running: {lock_path}") from exc
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        try:
            yield
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _warn(ctx, f"could not remove backup lock file {lock_path}: {exc}")
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _retention_plan(ctx: BackupContext) -> tuple[dict[str, Any], list[tuple[Path, bool]]]:
    keep_days = ctx.args.keep_days
    summary: dict[str, Any] = {
        "enabled": keep_days is not None and keep_days >= 0,
        "keep_days": keep_days,
        "cutoff": "",
        "candidates_examined": 0,
        "removal_candidates": 0,
        "inspection_failures": 0,
    }
    if keep_days is None or keep_days < 0:
        return summary, []
    cutoff = datetime.now(timezone.utc).timestamp() - (keep_days * 86400)
    summary["cutoff"] = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    candidates: list[tuple[Path, bool]] = []
    for path in ctx.output_dir.iterdir():
        if not path.name.startswith(f"{DEFAULT_BACKUP_PREFIX}-"):
            continue
        summary["candidates_examined"] += 1
        try:
            path_stat = path.stat()
            if path_stat.st_mtime >= cutoff:
                continue
        except OSError as exc:
            summary["inspection_failures"] += 1
            _warn(ctx, f"could not inspect retention candidate {path.name}: {type(exc).__name__}: {exc}")
            continue
        candidates.append((path, stat.S_ISDIR(path_stat.st_mode)))
    summary["removal_candidates"] = len(candidates)
    return summary, candidates


def _apply_retention_plan(
    ctx: BackupContext,
    summary: dict[str, Any],
    candidates: Sequence[tuple[Path, bool]],
) -> None:
    if not summary.get("enabled"):
        return
    removed = 0
    removal_failures = 0
    for path, is_directory in candidates:
        try:
            if is_directory:
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except OSError as exc:
            removal_failures += 1
            _warn(ctx, f"could not remove retention candidate {path.name}: {type(exc).__name__}: {exc}")
    summary["removed"] = removed
    summary["removal_failures"] = removal_failures
    failures = int(summary.get("inspection_failures") or 0) + removal_failures
    summary["failures"] = failures
    if not getattr(ctx.args, "result_path_only", False):
        _info(
            f"Retention: examined {int(summary.get('candidates_examined') or 0)} backup(s), "
            f"removed {removed}, failures {failures}."
        )


def _prepare_requested_inputs(ctx: BackupContext) -> None:
    if ctx.requested_inputs_prepared:
        return

    if getattr(ctx.args, "repository_free", False) and (
        not ctx.args.env_file or not getattr(ctx.args, "local_conf_dir", "")
    ):
        raise BackupError(
            "repository-free backups require --env-file and --local-conf-dir"
        )

    env_paths = [Path(path).expanduser().resolve() for path in (ctx.args.env_file_multi or [])]
    if ctx.args.env_file:
        env_paths.append(Path(ctx.args.env_file).expanduser().resolve())

    for path in env_paths:
        source_stat = _stat_readable_source(path, kind="env file", missing_ok=True)
        if source_stat is None:
            raise BackupError(f"env file does not exist: {path}")
        if not stat.S_ISREG(source_stat.st_mode):
            raise BackupError(f"env file is not a file: {path}")

    for extra in ctx.args.extra_file or []:
        path = Path(extra).expanduser().resolve()
        source_stat = _stat_readable_source(path, kind="extra", missing_ok=True)
        if source_stat is None:
            if ctx.args.ignore_missing_extra_file:
                ctx.excluded.append({"kind": "extra", "source": str(path), "reason": "missing"})
                continue
            raise BackupError(f"requested file does not exist: {path}")
        if not stat.S_ISREG(source_stat.st_mode):
            raise BackupError(f"requested path is not a file: {path}")

    for path in env_paths:
        try:
            load_env_file(path)
        except OSError as exc:
            if _is_permission_error(exc):
                _raise_unreadable_source("env file", path, exc)
            raise
        ctx.env_files_loaded.append(str(path))
    ctx.requested_inputs_prepared = True


def _available_backup_name(ctx: BackupContext) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S.%fZ")
    base_name = f"{DEFAULT_BACKUP_PREFIX}-{timestamp}"
    extension = "" if ctx.args.compress == "none" else ".tar.gz"
    candidate = base_name
    sequence = 1
    while (ctx.output_dir / f"{candidate}{extension}").exists():
        candidate = f"{base_name}-{sequence}"
        sequence += 1
    return candidate


def create_backup(ctx: BackupContext) -> Path:
    os.umask(0o077)
    _prepare_requested_inputs(ctx)
    _check_output_permissions(ctx, ctx.output_dir)

    app_config, cfg = _import_app_config(ctx.args.conf_dir)
    compose_files = _default_compose_files(ctx.args)
    data_source = resolve_data_dir_source(ctx, app_config, cfg, compose_files)
    workspace_source = resolve_workspace_source(ctx, cfg, compose_files)

    backup_name = _available_backup_name(ctx)
    stage = Path(tempfile.mkdtemp(prefix=f".{backup_name}.", dir=ctx.output_dir))
    stage.chmod(0o700)

    try:
        database_backend = str(cfg.get("database_backend") or "sqlite").strip().lower()
        database_manifest: dict[str, Any] = {"backend": database_backend}
        if database_backend == "sqlite":
            data_dir = _host_data_dir_path(data_source)
            source_db = data_dir / DEFAULT_SQLITE_NAME
            dest_db = stage / "database" / DEFAULT_SQLITE_NAME
            backup_sqlite_database(source_db, dest_db)
            database_manifest.update({"source": str(source_db), "archive_path": dest_db.relative_to(stage).as_posix()})
            ctx.included.append({
                "kind": "database",
                "source": str(source_db),
                "archive_path": dest_db.relative_to(stage).as_posix(),
            })
            exclude = _sqlite_sidecar_paths(source_db)
        elif database_backend == "postgres":
            dest_dump = stage / "database" / "postgres.dump"
            backup_postgres(ctx, cfg, dest_dump, compose_files)
            database_manifest.update({"archive_path": dest_dump.relative_to(stage).as_posix(), "dump_format": "custom"})
            ctx.included.append({
                "kind": "database",
                "source": "postgres",
                "archive_path": dest_dump.relative_to(stage).as_posix(),
            })
            exclude = set()
        else:
            raise BackupError(f"unsupported database_backend: {database_backend}")

        copy_data_dir(ctx, data_source, stage, exclude=exclude)
        if workspace_source is not None:
            copy_workspace(ctx, workspace_source, stage)
        include_config_files(ctx, stage, compose_files)
        write_restore_notes(stage)
        ctx.retention, retention_candidates = _retention_plan(ctx)

        manifest = build_manifest(
            ctx,
            cfg=cfg,
            app_version=str(getattr(app_config, "APP_VERSION", "")),
            data_source=data_source,
            database=database_manifest,
            workspace_source=workspace_source,
            stage=stage,
        )
        write_json(stage / "manifest.json", manifest)
        write_checksums(stage)

        if ctx.args.compress == "none":
            final_dir = ctx.output_dir / backup_name
            if final_dir.exists():
                raise BackupError(f"backup destination already exists: {final_dir}")
            stage.rename(final_dir)
            result = final_dir
        else:
            archive_path = ctx.output_dir / f"{backup_name}.tar.gz"
            _archive_stage(stage, archive_path, backup_name)
            shutil.rmtree(stage)
            result = archive_path
        _apply_retention_plan(ctx, ctx.retention, retention_candidates)
        return result
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def build_dry_run_plan(ctx: BackupContext) -> dict[str, Any]:
    _prepare_requested_inputs(ctx)
    app_config, cfg = _import_app_config(ctx.args.conf_dir)
    compose_files = _default_compose_files(ctx.args)
    data_source = resolve_data_dir_source(ctx, app_config, cfg, compose_files)
    workspace_source = resolve_workspace_source(ctx, cfg, compose_files)
    database_backend = str(cfg.get("database_backend") or "sqlite").strip().lower()
    database_plan: dict[str, Any] = {"backend": database_backend}
    if database_backend == "postgres":
        database_plan["dump"] = _postgres_dump_plan(ctx, cfg, compose_files)
    return {
        "dry_run": True,
        "database": database_plan,
        "database_backend": database_backend,
        "data_dir": data_source.__dict__,
        "workspace": None if workspace_source is None else workspace_source.__dict__,
        "compose_files": [str(path) for path in compose_files],
        "env_files_loaded": ctx.env_files_loaded,
        "excluded": ctx.excluded,
        "extra_files": list(ctx.args.extra_file or []),
        "warnings": ctx.warnings,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a comprehensive darklab_shell operator backup.")
    parser.add_argument("--output-dir", default=str(ROOT / "backups"), help="Directory where backups are written.")
    parser.add_argument("--compress", choices=("gzip", "none"), default="gzip", help="Archive format. Default: gzip.")
    parser.add_argument("--env-file", default="", help="Primary .env file to load and include in the backup.")
    parser.add_argument(
        "--env-file-extra",
        dest="env_file_multi",
        action="append",
        default=[],
        help="Additional env file to load.",
    )
    parser.add_argument("--conf-dir", default="", help="Config directory to load instead of app/conf.")
    parser.add_argument(
        "--local-conf-dir",
        default="",
        help="Operator config overlay directory included by repository-free backups.",
    )
    parser.add_argument(
        "--repository-free",
        action="store_true",
        help="Write operator and release files in the managed deployment restore layout.",
    )
    parser.add_argument("--extra-file", action="append", default=[], help="Extra deployment-specific file to include.")
    parser.add_argument(
        "--ignore-missing-extra-file",
        action="store_true",
        help="Do not fail when an --extra-file path is missing.",
    )
    parser.add_argument("--compose-file", action="append", default=[], help="Docker Compose file used for service detection.")
    parser.add_argument("--compose-service", default="shell", help="Compose service name for the app container. Default: shell.")
    parser.add_argument(
        "--postgres-service",
        default="postgres",
        help="Compose service name for bundled Postgres. Default: postgres.",
    )
    parser.add_argument("--postgres-dump-mode", choices=("auto", "local", "compose"), default="auto")
    parser.add_argument("--pg-dump-command", default="pg_dump", help="Local pg_dump executable for Postgres backups.")
    parser.add_argument("--docker-container", default="", help="App container name or id for Docker mount detection.")
    parser.add_argument(
        "--data-source",
        default="",
        help="Explicit data_dir source: bind:/path, volume:name, or container:name:/path.",
    )
    parser.add_argument(
        "--workspace-source",
        default="",
        help="Explicit workspace source: bind:/path, volume:name, or container:name:/path.",
    )
    parser.add_argument(
        "--workspace-root",
        default="",
        help="Logical workspace root used by the app, such as /workspaces. Overrides config and Compose WORKSPACE_ROOT.",
    )
    parser.add_argument("--include-workspaces", choices=("auto", "always", "never"), default="auto")
    parser.add_argument(
        "--include-ephemeral-workspaces",
        action="store_true",
        help="Allow Docker copy from tmpfs/container-only workspaces.",
    )
    parser.add_argument("--volume-export-image", default="alpine:3.22", help="Helper image for explicit Docker volume exports.")
    parser.add_argument("--keep-days", type=int, default=None, help="Delete matching backups older than this many days.")
    parser.add_argument("--lock-file", default="", help="Lock file path. Defaults to <output-dir>/.backup.lock.")
    parser.add_argument("--command-timeout", type=int, default=3600, help="Timeout for pg_dump and Docker copy/export commands.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve config and planned sources without writing a backup.")
    parser.add_argument(
        "--result-path-only",
        action="store_true",
        help="Print only the completed backup path to stdout for machine callers.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    ctx = BackupContext(args=args, output_dir=output_dir)
    try:
        _prepare_requested_inputs(ctx)
        if args.dry_run:
            plan = build_dry_run_plan(ctx)
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        with _backup_lock(ctx):
            result = create_backup(ctx)
        output_uid = os.environ.get("DARKLAB_BACKUP_OUTPUT_UID", "")
        output_gid = os.environ.get("DARKLAB_BACKUP_OUTPUT_GID", "")
        if output_uid.isdigit() and output_gid.isdigit():
            os.chown(result, int(output_uid), int(output_gid))
        if args.result_path_only:
            print(result, flush=True)
        else:
            _info(f"Backup written to {result}")
            if ctx.warnings:
                _info(f"Completed with {len(ctx.warnings)} warning(s). Review the warning output and manifest.json.")
        return 0
    except BackupError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"backup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
