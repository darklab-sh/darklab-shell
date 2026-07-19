# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from datetime import datetime
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tarfile

import pytest


pytestmark = pytest.mark.release_integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "operations" / "backup_system.py"
SPEC = importlib.util.spec_from_file_location("backup_system", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
backup_system = importlib.util.module_from_spec(SPEC)
sys.modules["backup_system"] = backup_system
SPEC.loader.exec_module(backup_system)


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "APP_DATA_DIR",
        "DATABASE_BACKEND",
        "DATABASE_URL",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "WORKSPACE_BACKEND",
        "WORKSPACE_ENABLED",
        "WORKSPACE_ROOT",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_config(conf_dir: Path, body: str) -> None:
    conf_dir.mkdir(parents=True)
    (conf_dir / "config.yaml").write_text(body, encoding="utf-8")


def _write_sqlite_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, command TEXT)")
        conn.execute("INSERT INTO runs (command) VALUES ('ping -c 4 darklab.sh')")


def _backup_dirs(output_dir: Path) -> list[Path]:
    return sorted(path for path in output_dir.iterdir() if path.name.startswith("darklab-backup-"))


def _manifest(backup_dir: Path) -> dict:
    return json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))


def test_sqlite_backup_uses_snapshot_and_excludes_live_database_from_data_dir(
    tmp_path, monkeypatch, capsys
):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    (data_dir / "run-output").mkdir()
    (data_dir / "run-output" / "artifact.txt").write_text("artifact body", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  shell:\n    volumes:\n      - ./data:/data\n", encoding="utf-8")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, "workspace_enabled: false\n")
    output_dir = tmp_path / "backups"

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--compose-file",
        str(compose_file),
        "--output-dir",
        str(output_dir),
        "--compress",
        "none",
        "--result-path-only",
    ])

    assert rc == 0
    backup_dir = _backup_dirs(output_dir)[0]
    captured = capsys.readouterr()
    assert captured.out == f"{backup_dir}\n"
    assert (backup_dir / "database" / "history.db").exists()
    assert not (backup_dir / "data" / "history.db").exists()
    assert (backup_dir / "data" / "run-output" / "artifact.txt").read_text(encoding="utf-8") == "artifact body"
    manifest = _manifest(backup_dir)
    assert manifest["data_dir"]["logical_dir"] == "/data"
    assert manifest["data_dir"]["source"] == str(data_dir)
    with sqlite3.connect(backup_dir / "database" / "history.db") as conn:
        assert conn.execute("SELECT command FROM runs").fetchone()[0] == "ping -c 4 darklab.sh"


def test_extra_and_env_files_are_included_without_logging_secret_values(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    theme_dir = conf_dir / "themes"
    theme_dir.mkdir()
    (theme_dir / "custom.local.yaml").write_text("name: Custom\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=postgresql://darklab:secret@postgres:5432/darklab_shell\n", encoding="utf-8")
    extra_file = tmp_path / "docker-compose.local.yml"
    extra_file.write_text("services: {}\n", encoding="utf-8")
    output_dir = tmp_path / "backups"

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
        "--env-file",
        str(env_file),
        "--extra-file",
        str(extra_file),
        "--compress",
        "none",
    ])

    assert rc == 0
    backup_dir = _backup_dirs(output_dir)[0]
    manifest = _manifest(backup_dir)
    assert "[redacted]" in json.dumps(manifest["config"]["effective_config_redacted"])
    assert "darklab:secret" not in json.dumps(manifest)
    assert any(path.name == ".env" for path in (backup_dir / "config").rglob(".env"))
    assert any(path.name == "custom.local.yaml" for path in (backup_dir / "config").rglob("custom.local.yaml"))
    assert any(path.name == "docker-compose.local.yml" for path in (backup_dir / "extra").rglob("docker-compose.local.yml"))


def test_repository_free_backup_uses_operator_restore_layout(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    (data_dir / ".secrets_master_key").write_text("vault-key\n", encoding="utf-8")
    conf_dir = tmp_path / "shipped-conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    local_conf_dir = tmp_path / "operator-conf"
    local_conf_dir.mkdir()
    (local_conf_dir / "config.local.yaml").write_text("log_level: INFO\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DARKLAB_IMAGE=docker.io/darklabsh/darklab-shell:2.6.0\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    release_manifest = tmp_path / "release-manifest.json"
    release_manifest.write_text('{"version":"2.6.0"}\n', encoding="utf-8")
    managed_checksums = tmp_path / "managed-files.sha256"
    managed_checksums.write_text("test  compose.yaml\n", encoding="utf-8")
    output_dir = tmp_path / "backups"

    rc = backup_system.main([
        "--repository-free",
        "--conf-dir",
        str(conf_dir),
        "--local-conf-dir",
        str(local_conf_dir),
        "--env-file",
        str(env_file),
        "--compose-file",
        str(compose_file),
        "--data-source",
        f"bind:{data_dir}",
        "--extra-file",
        str(release_manifest),
        "--extra-file",
        str(managed_checksums),
        "--output-dir",
        str(output_dir),
        "--compress",
        "none",
    ])

    assert rc == 0
    backup_dir = _backup_dirs(output_dir)[0]
    assert (backup_dir / "operator" / ".env").read_bytes() == env_file.read_bytes()
    assert (backup_dir / "operator" / "conf" / "config.local.yaml").read_bytes() == (
        local_conf_dir / "config.local.yaml"
    ).read_bytes()
    assert (backup_dir / "release" / "compose.yaml").is_file()
    assert (backup_dir / "release" / "release-manifest.json").is_file()
    assert (backup_dir / "release" / "managed-files.sha256").is_file()
    assert (backup_dir / "data" / ".secrets_master_key").is_file()
    manifest = _manifest(backup_dir)
    assert manifest["repository_free"] is True


def test_missing_extra_file_fails_unless_operator_allows_it(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    missing = tmp_path / "missing.local.yml"

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(tmp_path / "backups"),
        "--extra-file",
        str(missing),
        "--compress",
        "none",
    ])

    assert rc == 2
    assert not (tmp_path / "backups" / ".backup.lock").exists()

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(tmp_path / "backups-ok"),
        "--extra-file",
        str(missing),
        "--ignore-missing-extra-file",
        "--compress",
        "none",
    ])
    assert rc == 0


def test_dry_run_rejects_missing_requested_inputs_before_writing(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    missing_env = tmp_path / "missing.env"
    missing_extra_env = tmp_path / "missing-extra.env"
    missing_extra = tmp_path / "missing.local.yml"

    for option, missing_path in (
        ("--env-file", missing_env),
        ("--env-file-extra", missing_extra_env),
        ("--extra-file", missing_extra),
    ):
        output_dir = tmp_path / f"dry-run-{option.removeprefix('--')}"
        rc = backup_system.main([
            "--conf-dir",
            str(conf_dir),
            "--output-dir",
            str(output_dir),
            option,
            str(missing_path),
            "--dry-run",
        ])

        assert rc == 2
        assert not output_dir.exists()
        assert str(missing_path) in capsys.readouterr().err

    allowed_output = tmp_path / "dry-run-allowed"
    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(allowed_output),
        "--extra-file",
        str(missing_extra),
        "--ignore-missing-extra-file",
        "--dry-run",
    ])

    assert rc == 0
    assert not allowed_output.exists()
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert {"kind": "extra", "source": str(missing_extra), "reason": "missing"} in plan["excluded"]


def test_unreadable_data_dir_reports_root_guidance_and_cleans_lock(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    output_dir = tmp_path / "backups"

    def unreadable_copytree(source, destination, **kwargs):
        raise PermissionError(errno.EACCES, "Permission denied", str(source))

    monkeypatch.setattr(backup_system.shutil, "copytree", unreadable_copytree)

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
        "--compress",
        "none",
    ])

    captured = capsys.readouterr()
    assert rc == 2
    assert "data dir source is not readable by the current user" in captured.err
    assert "Run the backup as root on the Docker host" in captured.err
    assert not (output_dir / ".backup.lock").exists()


def test_workspace_tmpfs_skips_host_path_unless_bind_source_is_explicit(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    ephemeral_root = tmp_path / "tmpfs-workspaces"
    ephemeral_root.mkdir()
    tmpfs_conf_dir = tmp_path / "conf-tmpfs"
    _write_config(
        tmpfs_conf_dir,
        f"workspace_enabled: true\nworkspace_backend: tmpfs\nworkspace_root: {ephemeral_root}\n",
    )

    ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--conf-dir",
            str(tmpfs_conf_dir),
            "--output-dir",
            str(tmp_path / "dry-run-backups"),
            "--dry-run",
        ]),
        output_dir=tmp_path / "dry-run-backups",
    )
    plan = backup_system.build_dry_run_plan(ctx)

    assert plan["workspace"] is None
    assert {"kind": "workspaces", "source": str(ephemeral_root), "reason": "tmpfs-workspace"} in plan["excluded"]

    monkeypatch.setattr(backup_system, "_docker_inspect_mounts", lambda ctx_arg, container: None)
    ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--output-dir",
            str(tmp_path / "ephemeral-backups"),
            "--include-ephemeral-workspaces",
        ]),
        output_dir=tmp_path / "ephemeral-backups",
    )
    source = backup_system.resolve_workspace_source(
        ctx,
        {"workspace_enabled": True, "workspace_backend": "tmpfs", "workspace_root": str(ephemeral_root)},
        [],
    )

    assert source is None
    assert {"kind": "workspaces", "source": str(ephemeral_root), "reason": "container-unavailable"} in ctx.excluded
    assert "not running or inspectable" in ctx.warnings[0]

    monkeypatch.setattr(
        backup_system,
        "_docker_inspect_mounts",
        lambda ctx_arg, container: [{"Destination": str(ephemeral_root), "Type": "tmpfs"}],
    )
    ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--output-dir",
            str(tmp_path / "ephemeral-ok-backups"),
            "--include-ephemeral-workspaces",
        ]),
        output_dir=tmp_path / "ephemeral-ok-backups",
    )
    source = backup_system.resolve_workspace_source(
        ctx,
        {"workspace_enabled": True, "workspace_backend": "tmpfs", "workspace_root": str(ephemeral_root)},
        [],
    )

    assert source is not None
    assert source.kind == "container"
    assert source.container == "darklab_shell"

    workspace_dir = tmp_path / "workspaces"
    workspace_dir.mkdir()
    base_compose = tmp_path / "docker-compose.yml"
    base_compose.write_text(
        "\n".join([
            "services:",
            "  shell:",
            "    environment:",
            "      - WORKSPACE_ROOT=${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}",
            "    volumes:",
            "      - ./data:/data",
        ]),
        encoding="utf-8",
    )
    prod_compose = tmp_path / "examples" / "docker-compose.prod.yml"
    prod_compose.parent.mkdir()
    prod_compose.write_text(
        "\n".join([
            "services:",
            "  shell:",
            "    ports: !reset []",
            "    environment:",
            "      - WORKSPACE_ROOT=/workspaces",
            "    volumes:",
            "      - ./workspaces:/workspaces",
        ]),
        encoding="utf-8",
    )
    compose_conf_dir = tmp_path / "conf-compose"
    _write_config(
        compose_conf_dir,
        f"data_dir: {data_dir}\nworkspace_enabled: true\nworkspace_backend: volume\n",
    )

    ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--conf-dir",
            str(compose_conf_dir),
            "--output-dir",
            str(tmp_path / "compose-dry-run-backups"),
            "--compose-file",
            str(base_compose),
            "--compose-file",
            str(prod_compose),
            "--dry-run",
        ]),
        output_dir=tmp_path / "compose-dry-run-backups",
    )
    plan = backup_system.build_dry_run_plan(ctx)

    assert plan["workspace"]["kind"] == "bind"
    assert plan["workspace"]["logical_root"] == "/workspaces"
    assert plan["workspace"]["source"] == str(workspace_dir)
    assert plan["workspace"]["mount_destination"] == "/workspaces"

    workspace_dir = tmp_path / "host-workspaces"
    workspace_dir.mkdir()
    (workspace_dir / "sess_abc").mkdir()
    (workspace_dir / "sess_abc" / "targets.txt").write_text("darklab.sh\n", encoding="utf-8")
    conf_dir = tmp_path / "conf-volume"
    _write_config(
        conf_dir,
        f"data_dir: {data_dir}\nworkspace_enabled: false\nworkspace_backend: volume\nworkspace_root: /workspaces\n",
    )
    output_dir = tmp_path / "backups"

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
        "--workspace-source",
        f"bind:{workspace_dir}",
        "--compress",
        "none",
    ])

    assert rc == 0
    backup_dir = _backup_dirs(output_dir)[0]
    assert (backup_dir / "workspaces" / "sess_abc" / "targets.txt").read_text(encoding="utf-8") == "darklab.sh\n"
    assert _manifest(backup_dir)["workspace"]["source"] == str(workspace_dir)


def test_postgres_backup_uses_pg_dump_environment_without_password_argument(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    conf_dir = tmp_path / "conf"
    database_url = "postgresql://darklab:secret@localhost:5432/darklab_shell?sslmode=require"
    _write_config(conf_dir, f"data_dir: {data_dir}\ndatabase_backend: postgres\ndatabase_url: {database_url!r}\n")
    recorder = tmp_path / "pg-env.json"
    fake_pg_dump = tmp_path / "pg_dump"
    fake_pg_dump.write_text(
        "\n".join([
            "#!/usr/bin/env python3",
            "import json, os, sys",
            f"recorder = {str(recorder)!r}",
            "output = sys.argv[sys.argv.index('--file') + 1]",
            "open(output, 'wb').write(b'postgres dump')",
            "payload = {key: os.environ.get(key) for key in "
            "('PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'PGDATABASE', 'PGSSLMODE')}",
            "open(recorder, 'w', encoding='utf-8').write(json.dumps(payload, sort_keys=True))",
        ]),
        encoding="utf-8",
    )
    fake_pg_dump.chmod(fake_pg_dump.stat().st_mode | stat.S_IXUSR)
    output_dir = tmp_path / "backups"

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
        "--pg-dump-command",
        str(fake_pg_dump),
        "--postgres-dump-mode",
        "local",
        "--compress",
        "none",
    ])

    assert rc == 0
    backup_dir = _backup_dirs(output_dir)[0]
    assert (backup_dir / "database" / "postgres.dump").read_bytes() == b"postgres dump"
    recorded_env = json.loads(recorder.read_text(encoding="utf-8"))
    assert recorded_env["PGPASSWORD"] == "secret"
    manifest_text = (backup_dir / "manifest.json").read_text(encoding="utf-8")
    assert "darklab:secret" not in manifest_text
    assert "--file" in manifest_text

    compose_ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--output-dir",
            str(tmp_path / "compose-backups"),
            "--postgres-dump-mode",
            "compose",
        ]),
        output_dir=tmp_path / "compose-backups",
    )
    with pytest.raises(backup_system.BackupError, match="requires a Compose file"):
        backup_system.backup_postgres(compose_ctx, {}, tmp_path / "postgres.dump", [])

    calls = []

    def fake_run(ctx_arg, command, **kwargs):
        calls.append((kwargs.get("label"), list(command)))
        if kwargs.get("label") == "compose pg_dump":
            kwargs["stdout"].write(b"compose postgres dump")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_system, "_compose_service_container", lambda ctx_arg, compose_files, service: "")
    monkeypatch.setattr(backup_system, "_run", fake_run)
    compose_cfg = {"database_url": "postgresql://darklab:secret@postgres:5432/darklab_shell"}
    compose_dump = tmp_path / "compose-postgres.dump"
    backup_system.backup_postgres(compose_ctx, compose_cfg, compose_dump, [tmp_path / "docker-compose.yml"])

    assert compose_dump.read_bytes() == b"compose postgres dump"
    assert any(label == "compose pg_dump" and "exec" in command for label, command in calls)
    assert not any(command and command[0] == str(fake_pg_dump) for _, command in calls)

    def failed_compose_exec(ctx_arg, command, **kwargs):
        if kwargs.get("label") == "compose pg_dump":
            raise backup_system.BackupError("compose pg_dump failed with exit code 1: service postgres is not running")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_system, "_run", failed_compose_exec)
    unavailable_ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--output-dir",
            str(tmp_path / "auto-compose-backups"),
        ]),
        output_dir=tmp_path / "auto-compose-backups",
    )
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  postgres:\n    image: postgres:18-alpine\n", encoding="utf-8")
    with pytest.raises(backup_system.BackupError, match="compose pg_dump failed"):
        backup_system.backup_postgres(unavailable_ctx, compose_cfg, tmp_path / "auto-postgres.dump", [compose_file])


def test_postgres_auto_mode_keeps_remote_urls_on_local_pg_dump(tmp_path, monkeypatch):
    ctx = backup_system.BackupContext(
        args=backup_system.parse_args([
            "--output-dir",
            str(tmp_path / "backups"),
            "--pg-dump-command",
            "/usr/local/bin/pg_dump",
        ]),
        output_dir=tmp_path / "backups",
    )
    cfg = {"database_url": "postgresql://darklab:secret@db.example.com:5432/darklab_shell"}
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services:\n  postgres:\n    image: postgres:18-alpine\n", encoding="utf-8")
    container_checks = []
    calls = []

    monkeypatch.setattr(backup_system, "_compose_service_names", lambda ctx_arg, compose_files: {"postgres"})

    def running_container(ctx_arg, compose_files, service):
        container_checks.append(service)
        return "running-postgres-container"

    def fake_run(ctx_arg, command, **kwargs):
        calls.append((kwargs.get("label"), list(command)))
        Path(command[command.index("--file") + 1]).write_bytes(b"remote postgres dump")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(backup_system, "_compose_service_container", running_container)
    monkeypatch.setattr(backup_system, "_run", fake_run)
    destination = tmp_path / "remote-postgres.dump"

    backup_system.backup_postgres(ctx, cfg, destination, [compose_file])

    assert destination.read_bytes() == b"remote postgres dump"
    assert container_checks == []
    assert calls == [("pg_dump", [
        "/usr/local/bin/pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(destination),
    ])]


def test_checksum_hashing_reads_large_files_in_chunks():
    read_sizes = []

    class RecordingReader(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            read_sizes.append(size)
            return super().read(size)

    payload = b"abcdefghij"
    reader = RecordingReader(payload)

    class FakePath:
        def open(self, mode):
            assert mode == "rb"
            return reader

    digest = backup_system._sha256_file(FakePath(), chunk_size=4)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert read_sizes == [4, 4, 4, 4]


@pytest.mark.parametrize("compress", ("gzip", "none"))
def test_same_timestamp_backups_get_unique_paths_without_overwriting(tmp_path, monkeypatch, compress):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    output_dir = tmp_path / "backups"

    class FixedDatetime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 7, 10, 12, 34, 56, 123456, tzinfo=tz)

    monkeypatch.setattr(backup_system, "datetime", FixedDatetime)
    argv = [
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
        "--compress",
        compress,
    ]

    assert backup_system.main(argv) == 0
    first_backup = _backup_dirs(output_dir)[0]
    first_contents = first_backup.read_bytes() if first_backup.is_file() else _manifest(first_backup)
    assert backup_system.main(argv) == 0

    backups = _backup_dirs(output_dir)
    assert len(backups) == 2
    second_backup = next(path for path in backups if path != first_backup)
    assert first_backup.name.startswith("darklab-backup-20260710-123456.123456Z")
    assert second_backup.name.startswith("darklab-backup-20260710-123456.123456Z-1")
    assert (first_backup.read_bytes() if first_backup.is_file() else _manifest(first_backup)) == first_contents
    if compress == "gzip":
        stage = tmp_path / "existing-archive-stage"
        stage.mkdir()
        (stage / "sentinel.txt").write_text("must not replace", encoding="utf-8")
        with pytest.raises(backup_system.BackupError, match="destination already exists"):
            backup_system._archive_stage(stage, first_backup, "collision")
        assert first_backup.read_bytes() == first_contents


def test_default_gzip_archive_contains_valid_restore_payload_and_checksums(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    (data_dir / "run-output").mkdir()
    (data_dir / "run-output" / "artifact.txt").write_text("archive payload\n", encoding="utf-8")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    output_dir = tmp_path / "backups"

    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
    ])

    assert rc == 0
    archives = list(output_dir.glob("darklab-backup-*.tar.gz"))
    assert len(archives) == 1
    archive = archives[0]
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    top_level = archive.name.removesuffix(".tar.gz")
    with tarfile.open(archive, "r:gz") as tar:
        names = set(tar.getnames())
        required = {
            f"{top_level}/RESTORE.md",
            f"{top_level}/manifest.json",
            f"{top_level}/checksums.sha256",
            f"{top_level}/database/history.db",
            f"{top_level}/data/run-output/artifact.txt",
        }
        assert required <= names
        checksum_file = tar.extractfile(f"{top_level}/checksums.sha256")
        assert checksum_file is not None
        checksum_rows = checksum_file.read().decode("utf-8").splitlines()
        assert checksum_rows
        for row in checksum_rows:
            expected_digest, relative_path = row.split("  ", 1)
            member_file = tar.extractfile(f"{top_level}/{relative_path}")
            assert member_file is not None
            assert hashlib.sha256(member_file.read()).hexdigest() == expected_digest
    assert not any(path.name.startswith(".darklab-backup-") for path in output_dir.iterdir())
    assert not (output_dir / ".backup.lock").exists()


def test_retention_reports_removed_backups_and_inspection_failures(tmp_path, monkeypatch, capsys):
    _clean_env(monkeypatch)
    data_dir = tmp_path / "data"
    _write_sqlite_database(data_dir / "history.db")
    conf_dir = tmp_path / "conf"
    _write_config(conf_dir, f"data_dir: {data_dir}\nworkspace_enabled: false\n")
    output_dir = tmp_path / "backups"
    output_dir.mkdir()
    old_backup = output_dir / "darklab-backup-old"
    old_backup.mkdir()
    recent_backup = output_dir / "darklab-backup-recent"
    recent_backup.mkdir()
    broken_backup = output_dir / "darklab-backup-broken.tar.gz"
    broken_backup.write_bytes(b"broken metadata")
    old_timestamp = datetime.now().timestamp() - (3 * 86400)
    os.utime(old_backup, (old_timestamp, old_timestamp))
    original_stat = Path.stat

    def stat_with_failure(path, *args, **kwargs):
        if path == broken_backup:
            raise OSError("metadata unavailable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_with_failure)
    rc = backup_system.main([
        "--conf-dir",
        str(conf_dir),
        "--output-dir",
        str(output_dir),
        "--keep-days",
        "1",
        "--compress",
        "none",
    ])

    captured = capsys.readouterr()
    monkeypatch.setattr(Path, "stat", original_stat)
    assert rc == 0
    assert not old_backup.exists()
    assert recent_backup.exists()
    assert broken_backup.exists()
    created_backup = next(
        path
        for path in output_dir.iterdir()
        if path not in {recent_backup, broken_backup} and path.name.startswith("darklab-backup-")
    )
    retention = _manifest(created_backup)["retention"]
    assert retention == {
        "enabled": True,
        "keep_days": 1,
        "cutoff": retention["cutoff"],
        "candidates_examined": 3,
        "removal_candidates": 1,
        "inspection_failures": 1,
    }
    assert retention["cutoff"].endswith("+00:00")
    assert "could not inspect retention candidate darklab-backup-broken.tar.gz" in captured.err
    assert "Retention: examined 3 backup(s), removed 1, failures 1." in captured.out


def test_unexpected_backup_failures_print_traceback(tmp_path, monkeypatch, capsys):
    def fail_unexpectedly(ctx):
        raise RuntimeError("archive metadata exploded")

    monkeypatch.setattr(backup_system, "_prepare_requested_inputs", fail_unexpectedly)

    rc = backup_system.main(["--output-dir", str(tmp_path / "backups")])

    captured = capsys.readouterr()
    assert rc == 1
    assert "backup failed: RuntimeError: archive metadata exploded" in captured.err
    assert "Traceback (most recent call last)" in captured.err
    assert "fail_unexpectedly" in captured.err


def test_workspace_volume_source_with_container_exports_with_docker_cp(tmp_path, monkeypatch):
    ctx = backup_system.BackupContext(
        args=backup_system.parse_args(["--output-dir", str(tmp_path)]),
        output_dir=tmp_path,
    )
    calls = []

    def fake_run(ctx_arg, command, **kwargs):
        calls.append(list(command))
        destination = Path(command[-1])
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "team_abc").mkdir()
        (destination / "team_abc" / "notes.txt").write_text("shared\n", encoding="utf-8")
        return subprocess_completed(command)

    monkeypatch.setattr(backup_system, "_run", fake_run)
    source = backup_system.WorkspaceSource(
        kind="volume",
        logical_root="/workspaces",
        source="darklab_shell_workspaces",
        container="darklab_shell",
        mount_destination="/workspaces",
        mount_type="volume",
    )

    backup_system.copy_workspace(ctx, source, tmp_path / "stage")

    assert calls == [["docker", "cp", "darklab_shell:/workspaces/.", str(tmp_path / "stage" / "workspaces")]]
    assert (tmp_path / "stage" / "workspaces" / "team_abc" / "notes.txt").read_text(encoding="utf-8") == "shared\n"


def subprocess_completed(command):
    return subprocess.CompletedProcess(command, 0, "", "")
