# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Offline clean-cutover coverage for the retired session identity."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from core.database_backend import DatabaseBackend, connect_sqlite
from core.migrations import MIGRATIONS
from core.migrations.runner import applied_versions, run_migrations
from services.auth.legacy_cutover import (
    SHARED_ANONYMOUS_STORAGE_KEY,
    convert_selected_owner,
    legacy_inventory,
)
from services.auth.resolver import AuthenticationState, resolve_authentication
from services.secrets.vault import reset_master_key_cache_for_tests
from services.workspace.settings import session_workspace_name


LEGACY_CREDENTIAL = "tok_operator_cutover_only"


def _load_cutover_script():
    script = Path(__file__).resolve().parents[2] / "scripts" / "operations" / "cutover_principal_identity.py"
    spec = importlib.util.spec_from_file_location("cutover_principal_identity_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_database(path: Path, *, owner: str = LEGACY_CREDENTIAL) -> int:
    with connect_sqlite(str(path)) as conn:
        run_migrations(
            conn,
            tuple(migration for migration in MIGRATIONS if migration.version < "0082"),
            backend=DatabaseBackend.SQLITE,
        )
        conn.execute(
            "INSERT INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
            (owner, "2026-09-10T00:00:00+00:00", "2026-09-10T01:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO runs "
            "(id, personal_workspace_id, command, started, output_search_text) "
            "VALUES ('run_offline_cutover', ?, 'printf operator-cutover-marker', ?, "
            "'operator cutover marker')",
            (owner, "2026-09-10T01:00:00+00:00"),
        )
        conn.commit()
        return int(
            conn.execute("SELECT rowid FROM runs WHERE id = 'run_offline_cutover'").fetchone()[0]
        )


def _conversion_args(tmp_path: Path, database: Path, workspace_root: Path) -> SimpleNamespace:
    selected_file = tmp_path / "selected-credential.txt"
    selected_file.write_text(LEGACY_CREDENTIAL + "\n", encoding="utf-8")
    selected_file.chmod(0o600)
    return SimpleNamespace(
        backup=str(tmp_path / "verified-backup.tar.gz"),
        confirm_no_external_users=True,
        confirm_application_stopped=True,
        expected_legacy_credentials=1,
        database=str(database),
        workspace_root=str(workspace_root),
        selected_credential_file=str(selected_file),
        new_credential_file=str(tmp_path / "new-credential.txt"),
        confirm_selected_conversion="convert-the-selected-operator",
        label="Migrated operator access",
    )


@pytest.fixture
def cutover_environment(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    database = data_dir / "history.db"
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_master_key_cache_for_tests()
    rowid = _legacy_database(database)
    storage_key = session_workspace_name(LEGACY_CREDENTIAL)
    workspace_path = workspace_root / storage_key
    workspace_path.mkdir()
    evidence = workspace_path / "evidence.txt"
    evidence.write_text("do not move this workspace\n", encoding="utf-8")
    yield SimpleNamespace(
        database=database,
        workspace_root=workspace_root,
        workspace_path=workspace_path,
        evidence=evidence,
        rowid=rowid,
    )
    reset_master_key_cache_for_tests()


def test_preflight_reports_safe_counts_and_recommends_a_fresh_reset(
    cutover_environment,
    tmp_path,
    monkeypatch,
):
    module = _load_cutover_script()
    monkeypatch.setattr(
        module,
        "verify_backup_archive",
        lambda _path: {
            "format": "darklab_shell.backup.v1",
            "created_at": "2026-09-10T02:00:00+00:00",
            "repository_free": True,
            "checked_files": 4,
            "database_backend": "sqlite",
        },
    )
    args = SimpleNamespace(
        command="preflight",
        backup=str(tmp_path / "verified-backup.tar.gz"),
        confirm_no_external_users=True,
        expected_legacy_credentials=1,
        database=str(cutover_environment.database),
        workspace_root=str(cutover_environment.workspace_root),
    )

    payload = module.run(args)

    assert payload["recommended_action"] == "fresh_reset"
    assert payload["deployment_assumption_confirmed"] is True
    assert payload["inventory"]["legacy_credentials"] == 1
    assert payload["inventory"]["legacy_credentials_seen"] == 1
    assert payload["inventory"]["legacy_owned_rows_by_table"]["runs"] == 1
    assert LEGACY_CREDENTIAL not in json.dumps(payload)


def test_selected_conversion_is_atomic_preserves_rowids_and_never_moves_the_workspace(
    cutover_environment,
    tmp_path,
    monkeypatch,
):
    module = _load_cutover_script()
    monkeypatch.setattr(
        module,
        "verify_backup_archive",
        lambda _path: {"repository_free": True, "database_backend": "sqlite"},
    )
    args = _conversion_args(
        tmp_path,
        cutover_environment.database,
        cutover_environment.workspace_root,
    )

    payload = module._convert(args)
    secret_file = Path(args.new_credential_file)
    secret = secret_file.read_text(encoding="utf-8").strip()

    assert secret.startswith("dlc_v1_crd_")
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
    assert payload["workspace"]["storage_key"] == cutover_environment.workspace_path.name
    assert payload["database_backend"] == "sqlite"
    assert payload["database_integrity"]["run_count"] == 1
    assert payload["database_integrity"]["known_search_matches"] == 1
    assert payload["workspace_directory_moved"] is False
    assert cutover_environment.workspace_path.is_dir()
    assert cutover_environment.evidence.read_text(encoding="utf-8") == "do not move this workspace\n"
    assert LEGACY_CREDENTIAL not in json.dumps(payload)
    assert secret.encode("utf-8") not in cutover_environment.database.read_bytes()

    with connect_sqlite(str(cutover_environment.database)) as conn:
        assert "0082" in applied_versions(conn)
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'session_tokens'"
        ).fetchone() is None
        run = conn.execute(
            "SELECT rowid, personal_workspace_id FROM runs WHERE id = 'run_offline_cutover'"
        ).fetchone()
        assert int(run["rowid"]) == cutover_environment.rowid
        assert run["personal_workspace_id"] == payload["workspace"]["id"]
        matches = conn.execute(
            "SELECT rowid FROM runs_fts WHERE runs_fts MATCH 'operator'"
        ).fetchall()
        assert [int(row["rowid"]) for row in matches] == [cutover_environment.rowid]
        assert resolve_authentication(
            {"X-Darklab-Credential": secret},
            conn=conn,
        ).state == AuthenticationState.VALID
        assert resolve_authentication(
            {"X-Darklab-Credential": LEGACY_CREDENTIAL},
            conn=conn,
        ).state == AuthenticationState.MALFORMED_CREDENTIAL


def test_selected_conversion_failure_rolls_back_schema_data_fts_and_secret_file(
    cutover_environment,
    tmp_path,
    monkeypatch,
):
    module = _load_cutover_script()
    monkeypatch.setattr(
        module,
        "verify_backup_archive",
        lambda _path: {"repository_free": True, "database_backend": "sqlite"},
    )
    original_convert = module.convert_selected_owner

    def fail_after_conversion(*args, **kwargs):
        original_convert(*args, **kwargs)
        raise RuntimeError("injected failure before commit")

    monkeypatch.setattr(module, "convert_selected_owner", fail_after_conversion)
    args = _conversion_args(
        tmp_path,
        cutover_environment.database,
        cutover_environment.workspace_root,
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        module._convert(args)

    assert not Path(args.new_credential_file).exists()
    assert cutover_environment.workspace_path.is_dir()
    with connect_sqlite(str(cutover_environment.database)) as conn:
        assert "0082" not in applied_versions(conn)
        assert conn.execute(
            "SELECT COUNT(*) FROM session_tokens WHERE token = ?",
            (LEGACY_CREDENTIAL,),
        ).fetchone()[0] == 1
        run = conn.execute(
            "SELECT rowid, personal_workspace_id FROM runs WHERE id = 'run_offline_cutover'"
        ).fetchone()
        assert int(run["rowid"]) == cutover_environment.rowid
        assert run["personal_workspace_id"] == LEGACY_CREDENTIAL
        assert conn.execute(
            "SELECT COUNT(*) FROM runs_fts WHERE runs_fts MATCH 'operator'"
        ).fetchone()[0] == 1


def test_shared_anonymous_workspace_requires_an_explicit_disposition(
    cutover_environment,
):
    shared = cutover_environment.workspace_root / SHARED_ANONYMOUS_STORAGE_KEY
    shared.mkdir()
    (shared / "mixed.txt").write_text("mixed ownership\n", encoding="utf-8")
    with connect_sqlite(str(cutover_environment.database)) as conn:
        inventory = legacy_inventory(conn, cutover_environment.workspace_root)
        assert inventory["shared_anonymous_workspace"] == {
            "exists": True,
            "entry_count": 1,
            "bytes": len("mixed ownership\n"),
        }
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(RuntimeError, match="explicit disposition"):
            convert_selected_owner(
                conn,
                selected_credential=LEGACY_CREDENTIAL,
                workspace_root=cutover_environment.workspace_root,
            )
        conn.rollback()


def test_fresh_reset_can_be_rolled_back_before_new_state_is_created(
    cutover_environment,
    tmp_path,
    monkeypatch,
):
    module = _load_cutover_script()
    monkeypatch.setattr(
        module,
        "verify_backup_archive",
        lambda _path: {"repository_free": True, "database_backend": "sqlite"},
    )
    reset_args = SimpleNamespace(
        backup=str(tmp_path / "verified-backup.tar.gz"),
        confirm_no_external_users=True,
        confirm_application_stopped=True,
        expected_legacy_credentials=1,
        confirm_fresh_reset="erase-current-application-data",
        database=str(cutover_environment.database),
        workspace_root=str(cutover_environment.workspace_root),
    )

    staged = module._fresh_reset(reset_args)

    assert not cutover_environment.database.exists()
    assert list(cutover_environment.workspace_root.iterdir()) == []
    assert Path(staged["workspace_rollback_path"]).parent == cutover_environment.workspace_root.parent

    rollback_args = SimpleNamespace(
        confirm_application_stopped=True,
        confirm_reset_rollback="restore-staged-application-data",
        database=str(cutover_environment.database),
        workspace_root=str(cutover_environment.workspace_root),
        database_rollback_path=staged["database_rollback_path"],
        workspace_rollback_path=staged["workspace_rollback_path"],
    )
    restored = module._rollback_reset(rollback_args)

    assert restored == {
        "action": "fresh_reset_rollback",
        "database_restored": True,
        "workspace_restored": True,
    }
    assert cutover_environment.database.is_file()
    assert cutover_environment.evidence.read_text(encoding="utf-8") == "do not move this workspace\n"
    with connect_sqlite(str(cutover_environment.database)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM session_tokens WHERE token = ?",
            (LEGACY_CREDENTIAL,),
        ).fetchone()[0] == 1


def test_cutover_tool_refuses_host_execution_and_insecure_selected_files(
    cutover_environment,
    tmp_path,
    monkeypatch,
):
    development_app = tmp_path / "source-mounted-app"
    monkeypatch.setenv("APP_SOURCE_DIR", str(development_app))
    module = _load_cutover_script()
    assert module.APP_ROOT == development_app
    monkeypatch.setattr(module, "_inside_container", lambda: False)
    with pytest.raises(RuntimeError, match="inside the darklab_shell application container"):
        module._require_container()

    monkeypatch.setattr(module, "DB_BACKEND", DatabaseBackend.POSTGRES)
    with pytest.raises(RuntimeError, match="only available for SQLite deployments"):
        module._require_sqlite_backend(action="fresh reset")

    monkeypatch.setattr(
        module,
        "verify_backup_archive",
        lambda _path: {"repository_free": True, "database_backend": "sqlite"},
    )
    mismatch_args = SimpleNamespace(
        backup=str(tmp_path / "verified-backup.tar.gz"),
        confirm_no_external_users=True,
    )
    with pytest.raises(RuntimeError, match="does not match configured backend"):
        module._verify_inputs(mismatch_args)

    verified_paths = []

    def verify_development_backup(path, *, allow_development_backup=False):
        verified_paths.append((path, allow_development_backup))
        return {"repository_free": False, "database_backend": "postgres"}

    monkeypatch.setattr(module, "verify_backup_archive", verify_development_backup)
    mismatch_args.allow_development_backup = True
    assert module._verify_inputs(mismatch_args)["repository_free"] is False
    assert verified_paths == [(Path(mismatch_args.backup), True)]
    parsed = module._parser().parse_args(
        ["preflight", "--backup", mismatch_args.backup, "--allow-development-backup"]
    )
    assert parsed.allow_development_backup is True

    selected = tmp_path / "selected-readable.txt"
    selected.write_text(LEGACY_CREDENTIAL + "\n", encoding="utf-8")
    selected.chmod(0o644)
    with pytest.raises(RuntimeError, match="group or other"):
        module._read_selected_credential(str(selected))
