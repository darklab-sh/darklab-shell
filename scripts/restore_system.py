#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Restore a repository-free darklab_shell backup inside the release image."""

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


def _replace_directory(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RestoreError(f"backup is missing directory: {source.name}")
    destination.mkdir(parents=True, exist_ok=True)
    for child in destination.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(source, destination, dirs_exist_ok=True)


def _env_value(path: Path, name: str) -> str:
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return ""


def _restore_env(source: Path, destination: Path, image: str) -> None:
    lines = source.read_text(encoding="utf-8").splitlines()
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith("DARKLAB_IMAGE="):
            output.append(f"DARKLAB_IMAGE={image}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"DARKLAB_IMAGE={image}")
    temporary = destination.with_name(f".{destination.name}.restore-{os.getpid()}")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(destination)


def _restore_postgres(database_url: str, dump_path: Path) -> None:
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
    result = subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
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
    current_image = _env_value(env_path, "DARKLAB_IMAGE")
    if not current_image:
        raise RestoreError("current .env is missing DARKLAB_IMAGE")

    with tempfile.TemporaryDirectory(prefix="darklab-restore-") as temporary_dir:
        backup_root, manifest = _extract_and_verify(archive_path, Path(temporary_dir))
        database = manifest.get("database")
        if not isinstance(database, dict):
            raise RestoreError("backup manifest is missing database metadata")
        backend = str(database.get("backend") or "").lower()
        if backend not in {"sqlite", "postgres"}:
            raise RestoreError(f"unsupported database backend in backup: {backend}")

        _replace_directory(backup_root / "operator" / "conf", Path(args.local_conf_dir))
        _replace_directory(backup_root / "data", Path(args.data_dir))
        workspace_source = backup_root / "workspaces"
        if workspace_source.exists():
            _replace_directory(workspace_source, Path(args.workspace_dir))
        _restore_env(backup_root / "operator" / ".env", env_path, current_image)

        if backend == "sqlite":
            sqlite_backup = backup_root / "database" / "history.db"
            if not sqlite_backup.is_file():
                raise RestoreError("SQLite backup is missing database/history.db")
            shutil.copy2(sqlite_backup, Path(args.data_dir) / "history.db")
        else:
            _restore_postgres(args.database_url, backup_root / "database" / "postgres.dump")

    print(f"Restored verified {backend} backup from {archive_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--data-dir", default="/data")
    parser.add_argument("--local-conf-dir", default="/config")
    parser.add_argument("--workspace-dir", default="/workspaces")
    parser.add_argument("--env-file", default="/deployment/.env")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
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
