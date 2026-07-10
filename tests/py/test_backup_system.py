from __future__ import annotations

import errno
import importlib.util
import json
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "backup_system.py"
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


def test_sqlite_backup_uses_snapshot_and_excludes_live_database_from_data_dir(tmp_path, monkeypatch):
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
    ])

    assert rc == 0
    backup_dir = _backup_dirs(output_dir)[0]
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
        f"data_dir: {data_dir}\nworkspace_enabled: true\nworkspace_backend: volume\nworkspace_root: /workspaces\n",
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
