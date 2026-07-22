#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Restore a darklab_shell production backup inside the release image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


class RestoreError(RuntimeError):
    """Raised when a backup cannot be restored safely."""


_TARGET_LOCAL_ENV_NAMES = (
    "DARKLAB_IMAGE",
    "DATABASE_BACKEND",
    "DATABASE_URL",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)
_RESTORED_ENV_OUTPUT_ORDER = (*_TARGET_LOCAL_ENV_NAMES, "COMPOSE_PROFILES")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise RestoreError(f"backup contains an unsafe path: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise RestoreError(f"backup contains an unsupported special entry: {member.name}")
    return members


def _extract_and_verify(archive_path: Path, destination: Path) -> tuple[Path, dict[str, Any]]:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = _safe_archive_members(archive)
        archive.extractall(destination, members=members, filter="data")
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1 or not roots[0].name.startswith("darklab-backup-"):
        raise RestoreError("backup must contain one darklab-backup-* root directory")
    root = roots[0]
    manifest_path = root / "manifest.json"
    checksum_path = root / "checksums.sha256"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise RestoreError("backup is missing manifest.json or checksums.sha256")
    for row in checksum_path.read_text(encoding="utf-8").splitlines():
        try:
            expected, relative = row.split("  ", 1)
        except ValueError as exc:
            raise RestoreError("backup contains a malformed checksum row") from exc
        relative_path = PurePosixPath(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RestoreError(f"backup checksum contains an unsafe path: {relative}")
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise RestoreError(f"backup checksum mismatch: {relative}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "darklab_shell.backup.v1":
        raise RestoreError("backup manifest format is not supported")
    if manifest.get("repository_free") is not True:
        raise RestoreError("backup was not created by the managed deployment lifecycle")
    return root, manifest


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _chown_tree(path: Path, uid: int, gid: int) -> None:
    if path.is_dir() and not path.is_symlink():
        for root, directories, files in os.walk(path):
            for name in (*directories, *files):
                os.chown(Path(root) / name, uid, gid, follow_symlinks=False)
    os.chown(path, uid, gid, follow_symlinks=False)


def _restore_owner(args: argparse.Namespace) -> tuple[int, int] | None:
    raw_uid = str(getattr(args, "output_uid", "") or "").strip()
    raw_gid = str(getattr(args, "output_gid", "") or "").strip()
    if not raw_uid and not raw_gid:
        return None
    if not raw_uid or not raw_gid:
        raise RestoreError("restore output ownership requires both UID and GID")
    try:
        uid = int(raw_uid)
        gid = int(raw_gid)
    except ValueError as exc:
        raise RestoreError("restore output UID and GID must be non-negative integers") from exc
    if uid < 0 or gid < 0:
        raise RestoreError("restore output UID and GID must be non-negative integers")
    return uid, gid


class _DirectoryReplacement:
    """Stage and swap one bind-mounted directory while retaining rollback data."""

    def __init__(self, source: Path, destination: Path, owner: tuple[int, int] | None):
        if not source.is_dir():
            raise RestoreError(f"backup is missing directory: {source.name}")
        self.destination = destination
        self.destination_existed = destination.exists()
        destination.mkdir(parents=True, exist_ok=True)
        destination_stat = destination.stat()
        self.original_owner = (destination_stat.st_uid, destination_stat.st_gid)
        self.stage = Path(tempfile.mkdtemp(prefix=".darklab-restore-stage-", dir=destination))
        self.rollback_dir: Path
        self.moved_original_names: list[str] = []
        self.moved_new_names: list[str] = []
        self.root_owner_changed = False
        try:
            self.rollback_dir = Path(
                tempfile.mkdtemp(prefix=".darklab-restore-rollback-", dir=destination)
            )
            shutil.copytree(source, self.stage, dirs_exist_ok=True)
            if owner is not None:
                _chown_tree(self.stage, *owner)
        except Exception:
            _remove_path(self.stage)
            rollback_dir = getattr(self, "rollback_dir", None)
            if rollback_dir is not None:
                _remove_path(rollback_dir)
            raise
        self.owner = owner

    def commit(self) -> None:
        excluded = {self.stage.name, self.rollback_dir.name}
        original_names = [child.name for child in self.destination.iterdir() if child.name not in excluded]
        for name in original_names:
            os.replace(self.destination / name, self.rollback_dir / name)
            self.moved_original_names.append(name)
        for child in list(self.stage.iterdir()):
            os.replace(child, self.destination / child.name)
            self.moved_new_names.append(child.name)
        if self.owner is not None:
            os.chown(self.destination, *self.owner, follow_symlinks=False)
            self.root_owner_changed = True

    def rollback(self) -> None:
        for name in reversed(self.moved_new_names):
            _remove_path(self.destination / name)
        for name in reversed(self.moved_original_names):
            rollback_path = self.rollback_dir / name
            if rollback_path.exists() or rollback_path.is_symlink():
                os.replace(rollback_path, self.destination / name)
        if self.root_owner_changed:
            os.chown(self.destination, *self.original_owner, follow_symlinks=False)
        self.cleanup()
        if not self.destination_existed and self.destination.exists() and not any(self.destination.iterdir()):
            self.destination.rmdir()

    def cleanup(self) -> None:
        _remove_path(self.stage)
        _remove_path(self.rollback_dir)


class _FileReplacement:
    def __init__(self, destination: Path):
        self.destination = destination
        descriptor, stage_name = tempfile.mkstemp(
            prefix=f".{destination.name}.restore-stage-",
            dir=destination.parent,
        )
        os.close(descriptor)
        self.stage = Path(stage_name)
        self.rollback_path: Path
        try:
            descriptor, rollback_name = tempfile.mkstemp(
                prefix=f".{destination.name}.restore-rollback-",
                dir=destination.parent,
            )
            os.close(descriptor)
            self.rollback_path = Path(rollback_name)
            self.rollback_path.unlink()
        except Exception:
            _remove_path(self.stage)
            raise
        self.original_moved = False
        self.new_moved = False

    def commit(self) -> None:
        os.replace(self.destination, self.rollback_path)
        self.original_moved = True
        os.replace(self.stage, self.destination)
        self.new_moved = True

    def rollback(self) -> None:
        if self.new_moved:
            _remove_path(self.destination)
        if self.original_moved and self.rollback_path.exists():
            os.replace(self.rollback_path, self.destination)
        self.cleanup()

    def cleanup(self) -> None:
        _remove_path(self.stage)
        _remove_path(self.rollback_path)


def _env_values(path: Path, names: tuple[str, ...]) -> dict[str, str]:
    requested = set(names)
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name in requested:
            values[name] = value
    return values


def _stage_restored_env(
    source: Path,
    replacement: _FileReplacement,
    preserved_values: dict[str, str],
    owner: tuple[int, int] | None,
) -> None:
    if not source.is_file():
        raise RestoreError("backup is missing operator/.env")
    lines = source.read_text(encoding="utf-8").splitlines()
    restored_names: set[str] = set()
    output: list[str] = []
    for line in lines:
        name, separator, _value = line.partition("=")
        if separator and name in preserved_values:
            output.append(f"{name}={preserved_values[name]}")
            restored_names.add(name)
            continue
        output.append(line)
    for name in _RESTORED_ENV_OUTPUT_ORDER:
        if name in preserved_values and name not in restored_names:
            output.append(f"{name}={preserved_values[name]}")
    replacement.stage.write_text("\n".join(output) + "\n", encoding="utf-8")
    replacement.stage.chmod(0o600)
    if owner is not None:
        os.chown(replacement.stage, *owner, follow_symlinks=False)


def _postgres_command_context(database_url: str) -> tuple[str, dict[str, str]]:
    if not database_url:
        raise RestoreError("Postgres restore requires DATABASE_URL")
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.path.lstrip("/"):
        raise RestoreError("DATABASE_URL must be a complete postgresql:// URL")
    database = unquote(parsed.path.lstrip("/"))
    restore_env = os.environ.copy()
    if parsed.hostname:
        restore_env["PGHOST"] = parsed.hostname
    if parsed.port:
        restore_env["PGPORT"] = str(parsed.port)
    if parsed.username:
        restore_env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        restore_env["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query)
    if query.get("sslmode"):
        restore_env["PGSSLMODE"] = query["sslmode"][-1]
    return database, restore_env


def _require_empty_postgres_target(database_url: str) -> None:
    database, restore_env = _postgres_command_context(database_url)
    result = subprocess.run(
        [
            "psql",
            "--tuples-only",
            "--no-align",
            "--dbname",
            database,
            "--command",
            (
                "SELECT COUNT(*) FROM pg_catalog.pg_tables "
                "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
            ),
        ],
        env=restore_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RestoreError(
            "could not verify that the Postgres adoption target is empty: "
            f"{result.stderr.strip()}"
        )
    try:
        table_count = int(result.stdout.strip())
    except ValueError as exc:
        raise RestoreError("Postgres adoption target returned an invalid table count") from exc
    if table_count:
        raise RestoreError(
            "backend adoption requires a fresh Postgres database with no user tables"
        )


def _restore_postgres(database_url: str, dump_path: Path) -> None:
    database, restore_env = _postgres_command_context(database_url)
    result = subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--single-transaction",
            "--no-owner",
            "--no-acl",
            "--dbname",
            database,
            str(dump_path),
        ],
        env=restore_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()
        raise RestoreError(f"pg_restore failed with exit code {result.returncode}: {detail}")


def restore(args: argparse.Namespace) -> None:
    archive_path = Path(args.archive).resolve()
    if not archive_path.is_file():
        raise RestoreError(f"backup archive does not exist: {archive_path}")
    env_path = Path(args.env_file).resolve()
    current_env = _env_values(env_path, _TARGET_LOCAL_ENV_NAMES)
    if not current_env.get("DARKLAB_IMAGE"):
        raise RestoreError("current .env is missing DARKLAB_IMAGE")
    owner = _restore_owner(args)

    with tempfile.TemporaryDirectory(prefix="darklab-restore-") as temporary_dir:
        backup_root, manifest = _extract_and_verify(archive_path, Path(temporary_dir))
        database = manifest.get("database")
        if not isinstance(database, dict):
            raise RestoreError("backup manifest is missing database metadata")
        backend = str(database.get("backend") or "").lower()
        if backend not in {"sqlite", "postgres"}:
            raise RestoreError(f"unsupported database backend in backup: {backend}")
        current_backend = str(current_env.get("DATABASE_BACKEND") or "sqlite").strip().lower()
        adopt_backend = str(getattr(args, "adopt_database_backend", "") or "").strip().lower()
        if current_backend != backend:
            if adopt_backend != backend:
                raise RestoreError(
                    f"backup database backend {backend!r} does not match target backend "
                    f"{current_backend!r}"
                )
            current_env["DATABASE_BACKEND"] = backend
            if backend == "postgres":
                compose_profiles = str(getattr(args, "compose_profiles", "") or "").strip()
                if "postgres" not in {
                    profile.strip() for profile in compose_profiles.split(",") if profile.strip()
                }:
                    raise RestoreError(
                        "Postgres backend adoption requires a compose profile containing postgres"
                    )
                current_env["COMPOSE_PROFILES"] = compose_profiles
        elif adopt_backend and adopt_backend != backend:
            raise RestoreError(
                f"requested backend adoption {adopt_backend!r} does not match backup backend "
                f"{backend!r}"
            )
        if adopt_backend == "postgres":
            _require_empty_postgres_target(args.database_url)

        replacements: list[_DirectoryReplacement | _FileReplacement] = []
        try:
            conf_replacement = _DirectoryReplacement(
                backup_root / "operator" / "conf",
                Path(args.local_conf_dir),
                owner,
            )
            replacements.append(conf_replacement)
            data_replacement = _DirectoryReplacement(backup_root / "data", Path(args.data_dir), owner)
            replacements.append(data_replacement)
            workspace_source = backup_root / "workspaces"
            if workspace_source.exists():
                replacements.append(_DirectoryReplacement(workspace_source, Path(args.workspace_dir), owner))
            env_replacement = _FileReplacement(env_path)
            replacements.append(env_replacement)
            _stage_restored_env(
                backup_root / "operator" / ".env",
                env_replacement,
                current_env,
                owner,
            )

            if backend == "sqlite":
                sqlite_backup = backup_root / "database" / "history.db"
                if not sqlite_backup.is_file():
                    raise RestoreError("SQLite backup is missing database/history.db")
                staged_database = data_replacement.stage / "history.db"
                shutil.copy2(sqlite_backup, staged_database)
                if owner is not None:
                    os.chown(staged_database, *owner, follow_symlinks=False)
            else:
                dump_path = backup_root / "database" / "postgres.dump"
                if not dump_path.is_file():
                    raise RestoreError("Postgres backup is missing database/postgres.dump")
                _restore_postgres(args.database_url, dump_path)
            for replacement in replacements:
                replacement.commit()
        except Exception as exc:
            rollback_errors: list[str] = []
            for replacement in reversed(replacements):
                try:
                    replacement.rollback()
                except OSError as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            if rollback_errors:
                raise RestoreError(
                    f"{exc}; filesystem rollback also failed: {'; '.join(rollback_errors)}"
                ) from exc
            raise
        else:
            for replacement in replacements:
                replacement.cleanup()

    print(f"Restored verified {backend} backup from {archive_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--data-dir", default="/data")
    parser.add_argument("--local-conf-dir", default="/config")
    parser.add_argument("--workspace-dir", default="/workspaces")
    parser.add_argument("--env-file", default="/deployment/.env")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--adopt-database-backend", choices=("sqlite", "postgres"), default="")
    parser.add_argument("--compose-profiles", default="")
    parser.add_argument("--output-uid", default=os.environ.get("DARKLAB_RESTORE_OUTPUT_UID", ""))
    parser.add_argument("--output-gid", default=os.environ.get("DARKLAB_RESTORE_OUTPUT_GID", ""))
    return parser.parse_args()


def main() -> int:
    try:
        restore(parse_args())
        return 0
    except (OSError, json.JSONDecodeError, tarfile.TarError, RestoreError) as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
