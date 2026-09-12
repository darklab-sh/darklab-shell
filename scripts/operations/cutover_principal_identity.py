#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preflight, reset, or convert the retired session identity inside the app image."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(os.environ.get("APP_SOURCE_DIR") or ROOT / "app")
TOOLS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(TOOLS_ROOT))

from core.database import DB_BACKEND, DB_PATH, db_connect  # noqa: E402
from core.database_backend import DatabaseBackend, connect_sqlite  # noqa: E402
from core.migrations.runner import acquire_postgres_migration_lock  # noqa: E402
from services.auth.legacy_cutover import (  # noqa: E402
    convert_selected_owner,
    discard_other_legacy_owners,
    legacy_inventory,
    plan_other_legacy_discard,
)
from services.workspace.settings import workspace_root as configured_workspace_root, workspace_settings  # noqa: E402
from restore_system import verify_backup_archive  # noqa: E402


CONFIRM_RESET = "erase-current-application-data"
CONFIRM_CONVERSION = "convert-the-selected-operator"
CONFIRM_DISCARD = "discard-other-development-owners"
CONFIRM_ROLLBACK = "restore-staged-application-data"


def _require_development_discard(args: argparse.Namespace, backup: dict[str, Any]) -> None:
    if DB_BACKEND != DatabaseBackend.POSTGRES:
        raise RuntimeError("development legacy discard supports Postgres only")
    if not getattr(args, "allow_development_backup", False) or backup.get("repository_free") is not False:
        raise RuntimeError("legacy discard requires an explicitly accepted development backup")


def _check_discard_counts(args: argparse.Namespace, counts: dict[str, Any]) -> None:
    expected = (
        ("credentials", getattr(args, "expected_discard_credentials", None)),
        ("owned_rows", getattr(args, "expected_discard_rows", None)),
        ("team_members", getattr(args, "expected_discard_team_members", None)),
    )
    for key, value in expected:
        if value is None or value < 0 or value != counts[key]:
            raise RuntimeError(f"reviewed discard {key} count does not match; run preflight again")


def _inside_container() -> bool:
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _require_container() -> None:
    if not _inside_container():
        raise RuntimeError(
            "principal cutover must run inside the darklab_shell application container"
        )


def _require_sqlite_backend(*, action: str) -> None:
    if DB_BACKEND != DatabaseBackend.SQLITE:
        raise RuntimeError(
            f"{action} is only available for SQLite deployments; "
            "Postgres deployments must use selected conversion or restore a verified backup"
        )


def _database_path(args: argparse.Namespace) -> Path:
    return Path(args.database or DB_PATH).expanduser().resolve()


def _workspace_root(args: argparse.Namespace) -> Path:
    configured = configured_workspace_root(workspace_settings())
    return Path(args.workspace_root or configured).expanduser().resolve(strict=False)


def _verify_inputs(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "allow_development_backup", False):
        backup = verify_backup_archive(
            Path(args.backup), allow_development_backup=True
        )
    else:
        backup = verify_backup_archive(Path(args.backup))
    backup_backend = str(backup.get("database_backend") or "").strip().lower()
    if backup_backend not in {backend.value for backend in DatabaseBackend}:
        raise RuntimeError("backup is missing a supported database backend")
    if backup_backend != DB_BACKEND.value:
        raise RuntimeError(
            f"backup database backend {backup_backend!r} does not match configured backend "
            f"{DB_BACKEND.value!r}"
        )
    if not args.confirm_no_external_users:
        raise RuntimeError(
            "recheck the deployment assumption and pass --confirm-no-external-users"
        )
    return backup


def _require_stopped_application(args: argparse.Namespace) -> None:
    if not getattr(args, "confirm_application_stopped", False):
        raise RuntimeError(
            "offline cutover requires --confirm-application-stopped"
        )


@contextmanager
def _database_connection(args: argparse.Namespace):
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        with db_connect() as conn:
            yield conn
        return
    database = _database_path(args)
    if not database.is_file():
        raise RuntimeError("SQLite database was not found")
    with connect_sqlite(str(database)) as conn:
        yield conn


def _inventory(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    backup = _verify_inputs(args)
    with _database_connection(args) as conn:
        inventory = legacy_inventory(conn, _workspace_root(args))
    expected = args.expected_legacy_credentials
    if expected is not None and inventory["legacy_credentials"] != expected:
        raise RuntimeError(
            "legacy credential count changed since review; stop and recheck the deployment assumption"
        )
    return backup, inventory


def _read_selected_credential(path_value: str) -> str:
    path = Path(path_value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("selected credential file must be a regular file, not a symlink")
    if path.stat().st_size > 512:
        raise RuntimeError("selected credential file is unexpectedly large")
    if path.stat().st_mode & 0o077:
        raise RuntimeError("selected credential file must not be readable by group or other users")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value:
        raise RuntimeError("selected credential file must contain exactly one credential")
    return value


def _open_secret_file(path_value: str) -> tuple[int, Path]:
    path = Path(path_value).expanduser()
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("new credential parent must be an existing directory, not a symlink")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"could not create the new credential file securely: {exc}") from exc
    if os.geteuid() == 0:
        parent_stat = parent.stat()
        os.fchown(descriptor, parent_stat.st_uid, parent_stat.st_gid)
    return descriptor, path


def _convert(args: argparse.Namespace) -> dict[str, Any]:
    _require_stopped_application(args)
    if args.confirm_selected_conversion != CONFIRM_CONVERSION:
        raise RuntimeError(
            f"selected conversion requires --confirm-selected-conversion {CONFIRM_CONVERSION}"
        )
    backup, before = _inventory(args)
    discard_requested = bool(getattr(args, "confirm_discard_other_legacy_data", ""))
    reviewed_team_snapshot_ids = tuple(getattr(args, "reviewed_team_snapshot_id", ()) or ())
    if reviewed_team_snapshot_ids and not discard_requested:
        raise RuntimeError("reviewed Team snapshot IDs require the development discard confirmation")
    expected_team_recent_values = getattr(args, "expected_discard_team_recent_values", None)
    if expected_team_recent_values is not None and not discard_requested:
        raise RuntimeError("reviewed Team recent values require the development discard confirmation")
    if discard_requested:
        if args.confirm_discard_other_legacy_data != CONFIRM_DISCARD:
            raise RuntimeError(f"development discard requires --confirm-discard-other-legacy-data {CONFIRM_DISCARD}")
        _require_development_discard(args, backup)
    selected = _read_selected_credential(args.selected_credential_file)
    workspace_root = _workspace_root(args)
    secret_candidate = Path(args.new_credential_file).expanduser().resolve(strict=False)
    try:
        secret_candidate.relative_to(workspace_root)
    except ValueError:
        pass
    else:
        raise RuntimeError("the new credential file must be outside the workspace root")
    descriptor, secret_path = _open_secret_file(args.new_credential_file)
    committed = False
    discard_counts = None
    try:
        with _database_connection(args) as conn:
            if DB_BACKEND == DatabaseBackend.POSTGRES:
                acquire_postgres_migration_lock(conn)
            else:
                conn.execute("BEGIN IMMEDIATE")
            try:
                if discard_requested:
                    discard_plan = plan_other_legacy_discard(
                        conn,
                        selected_credential=selected,
                        reviewed_team_snapshot_ids=reviewed_team_snapshot_ids,
                        expected_team_recent_values=expected_team_recent_values,
                    )
                    discard_counts = discard_plan.to_safe_dict()
                    _check_discard_counts(args, discard_counts)
                    discard_other_legacy_owners(conn, discard_plan)
                bundle, evidence = convert_selected_owner(
                    conn,
                    selected_credential=selected,
                    workspace_root=workspace_root,
                    credential_label=args.label,
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    descriptor = -1
                    handle.write(bundle.credential.secret + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                conn.commit()
                committed = True
            except BaseException:
                if not committed:
                    conn.rollback()
                raise
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if not committed:
            try:
                secret_path.unlink()
            except OSError:
                pass
        raise
    result = {
        "action": "selected_conversion",
        "backup": backup,
        "before": before,
        "principal": bundle.principal.to_safe_dict(),
        "workspace": bundle.workspace.to_safe_dict(),
        "credential": bundle.credential.metadata.to_safe_dict(),
        "new_credential_file": str(secret_path),
        "database_backend": DB_BACKEND.value,
        "database_integrity": evidence.to_safe_dict(),
        "workspace_directory_moved": False,
    }
    if discard_counts is not None:
        result["discarded_other_legacy_data"] = discard_counts
    return result


def _fresh_reset(args: argparse.Namespace) -> dict[str, Any]:
    _require_sqlite_backend(action="fresh reset")
    _require_stopped_application(args)
    if args.confirm_fresh_reset != CONFIRM_RESET:
        raise RuntimeError(f"fresh reset requires --confirm-fresh-reset {CONFIRM_RESET}")
    backup, inventory = _inventory(args)
    database = _database_path(args)
    root = _workspace_root(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    database_stash = database.parent / f".principal-cutover-database-rollback-{stamp}"
    workspace_stash = root.parent / (
        f".principal-cutover-{root.name}-workspace-rollback-{stamp}"
    )
    if database_stash.exists() or workspace_stash.exists():
        raise RuntimeError("rollback staging path already exists")

    with connect_sqlite(str(database)) as conn:
        conn.execute("BEGIN EXCLUSIVE")
        conn.rollback()
    database_stash.mkdir(mode=0o700)
    root.mkdir(parents=True, exist_ok=True)
    workspace_stash.mkdir(mode=0o700)
    moved_database: list[Path] = []
    moved_workspace: list[Path] = []
    try:
        for candidate in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
            if candidate.exists():
                destination = database_stash / candidate.name
                os.replace(candidate, destination)
                moved_database.append(destination)
        for child in list(root.iterdir()):
            if child == workspace_stash:
                continue
            destination = workspace_stash / child.name
            os.replace(child, destination)
            moved_workspace.append(destination)
    except BaseException:
        for source in reversed(moved_workspace):
            os.replace(source, root / source.name)
        for source in reversed(moved_database):
            os.replace(source, database.parent / source.name)
        shutil.rmtree(workspace_stash, ignore_errors=True)
        shutil.rmtree(database_stash, ignore_errors=True)
        raise
    return {
        "action": "fresh_reset",
        "backup": backup,
        "before": inventory,
        "database_rollback_path": str(database_stash),
        "workspace_rollback_path": str(workspace_stash),
        "next_step": "retain the rollback paths, then start the application to create a fresh principal schema",
    }


def _validated_rollback_directory(path_value: str, *, kind: str) -> Path:
    candidate = Path(path_value).expanduser()
    if candidate.is_symlink():
        raise RuntimeError(f"{kind} rollback path must be a directory, not a symlink")
    path = candidate.resolve(strict=False)
    if not path.is_dir():
        raise RuntimeError(f"{kind} rollback path must be a directory, not a symlink")
    valid_name = (
        path.name.startswith(".principal-cutover-database-rollback-")
        if kind == "database"
        else path.name.startswith(".principal-cutover-")
        and "-workspace-rollback-" in path.name
    )
    if not valid_name:
        raise RuntimeError(f"{kind} rollback path does not have the expected cutover name")
    return path


def _rollback_reset(args: argparse.Namespace) -> dict[str, Any]:
    _require_sqlite_backend(action="reset rollback")
    _require_stopped_application(args)
    if args.confirm_reset_rollback != CONFIRM_ROLLBACK:
        raise RuntimeError(
            f"reset rollback requires --confirm-reset-rollback {CONFIRM_ROLLBACK}"
        )
    database = _database_path(args)
    root = _workspace_root(args)
    database_stash = _validated_rollback_directory(
        args.database_rollback_path,
        kind="database",
    )
    workspace_stash = _validated_rollback_directory(
        args.workspace_rollback_path,
        kind="workspace",
    )
    if database.exists() or Path(f"{database}-wal").exists() or Path(f"{database}-shm").exists():
        raise RuntimeError("database destination is not empty; refusing to discard post-reset state")
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise RuntimeError("workspace destination is not empty; refusing to discard post-reset state")

    restored_database: list[Path] = []
    restored_workspace: list[Path] = []
    try:
        for child in list(database_stash.iterdir()):
            destination = database.parent / child.name
            os.replace(child, destination)
            restored_database.append(destination)
        for child in list(workspace_stash.iterdir()):
            destination = root / child.name
            os.replace(child, destination)
            restored_workspace.append(destination)
    except BaseException:
        for destination in reversed(restored_workspace):
            os.replace(destination, workspace_stash / destination.name)
        for destination in reversed(restored_database):
            os.replace(destination, database_stash / destination.name)
        raise
    database_stash.rmdir()
    workspace_stash.rmdir()
    return {
        "action": "fresh_reset_rollback",
        "database_restored": True,
        "workspace_restored": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare the principal identity clean cutover.")
    parser.add_argument("--database", default="")
    parser.add_argument("--workspace-root", default="")
    commands = parser.add_subparsers(dest="command", required=True)

    def common(command: argparse.ArgumentParser) -> None:
        command.add_argument("--backup", required=True)
        command.add_argument(
            "--allow-development-backup",
            action="store_true",
            help="Explicitly accept a checksum-verified non-managed development backup.",
        )
        command.add_argument("--confirm-no-external-users", action="store_true")
        command.add_argument("--expected-legacy-credentials", type=int)

    preflight = commands.add_parser("preflight", help="Verify the backup and print safe cutover counts.")
    common(preflight)
    preflight.add_argument("--selected-credential-file")
    preflight.add_argument("--reviewed-team-snapshot-id", action="append", default=[])
    preflight.add_argument("--expected-discard-team-recent-values", type=int)

    reset = commands.add_parser("reset", help="Stage current data for rollback and start fresh.")
    common(reset)
    reset.add_argument("--confirm-application-stopped", action="store_true")
    reset.add_argument("--confirm-fresh-reset", required=True)

    convert = commands.add_parser("convert", help="Convert the explicitly selected operator workspace.")
    common(convert)
    convert.add_argument("--confirm-application-stopped", action="store_true")
    convert.add_argument("--selected-credential-file", required=True)
    convert.add_argument("--new-credential-file", required=True)
    convert.add_argument("--confirm-selected-conversion", required=True)
    convert.add_argument("--label", default="Migrated operator access")
    convert.add_argument("--confirm-discard-other-legacy-data", default="")
    convert.add_argument("--expected-discard-credentials", type=int)
    convert.add_argument("--expected-discard-rows", type=int)
    convert.add_argument("--expected-discard-team-members", type=int)
    convert.add_argument("--reviewed-team-snapshot-id", action="append", default=[])
    convert.add_argument("--expected-discard-team-recent-values", type=int)

    rollback = commands.add_parser(
        "rollback-reset",
        help="Restore a staged reset before any new application state is created.",
    )
    rollback.add_argument("--confirm-application-stopped", action="store_true")
    rollback.add_argument("--database-rollback-path", required=True)
    rollback.add_argument("--workspace-rollback-path", required=True)
    rollback.add_argument("--confirm-reset-rollback", required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "preflight":
        reviewed_team_snapshot_ids = tuple(getattr(args, "reviewed_team_snapshot_id", ()) or ())
        if reviewed_team_snapshot_ids and not getattr(args, "selected_credential_file", None):
            raise RuntimeError("reviewed Team snapshot IDs require --selected-credential-file")
        expected_team_recent_values = getattr(args, "expected_discard_team_recent_values", None)
        if expected_team_recent_values is not None and not getattr(args, "selected_credential_file", None):
            raise RuntimeError("reviewed Team recent values require --selected-credential-file")
        backup, inventory = _inventory(args)
        result = {
            "action": "preflight",
            "backup": backup,
            "inventory": inventory,
            "deployment_assumption_confirmed": True,
            "recommended_action": (
                "selected_conversion"
                if DB_BACKEND == DatabaseBackend.POSTGRES
                else "fresh_reset"
            ),
            "selected_conversion_requires_explicit_confirmation": True,
        }
        if getattr(args, "selected_credential_file", None):
            _require_development_discard(args, backup)
            selected = _read_selected_credential(args.selected_credential_file)
            with _database_connection(args) as conn:
                result["development_discard_review"] = plan_other_legacy_discard(
                    conn,
                    selected_credential=selected,
                    reviewed_team_snapshot_ids=reviewed_team_snapshot_ids,
                    expected_team_recent_values=expected_team_recent_values,
                ).to_safe_dict()
        return result
    if args.command == "reset":
        return _fresh_reset(args)
    if args.command == "convert":
        return _convert(args)
    if args.command == "rollback-reset":
        return _rollback_reset(args)
    raise RuntimeError("unknown cutover command")


def main(argv: list[str] | None = None) -> int:
    try:
        _require_container()
        payload = run(_parser().parse_args(argv))
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
