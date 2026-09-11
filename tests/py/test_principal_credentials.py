# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import uuid

import pytest

from core.database_backend import DatabaseBackend
from core.migrations import v0078_principal_credential_persistence, v0079_credential_scopes
from services.auth import storage
from services.auth.contracts import (
    IdentityStorageError,
    PrincipalDisabled,
    VerifierKeyError,
    WorkspaceAlreadyAttached,
    WorkspaceStorageError,
)
from services.auth.schema_guard import PostCutoverSchemaMismatch, assert_post_cutover_schema
from services.auth.verifier_keys import (
    delete_retired_verifier_root,
    rewrap_verifier_roots,
    rotate_verifier_root,
)
from services.auth.workspace_storage import (
    anonymous_workspace_storage_key,
    resolve_workspace_storage_path,
    validate_workspace_storage_key,
)
from services.secrets.vault import reset_master_key_cache_for_tests
from services.workspace.models import WorkspaceSettings


@pytest.fixture
def principal_db(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir()
    reset_master_key_cache_for_tests()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for statement in v0078_principal_credential_persistence.MIGRATION.statements_for(DatabaseBackend.SQLITE):
        conn.execute(statement)
    for statement in v0079_credential_scopes.MIGRATION.statements_for(DatabaseBackend.SQLITE):
        conn.execute(statement)
    yield conn
    conn.close()
    reset_master_key_cache_for_tests()


def _workspace_settings(root: Path) -> WorkspaceSettings:
    root.mkdir(parents=True, exist_ok=True)
    return WorkspaceSettings(
        enabled=True,
        backend="volume",
        root=root,
        quota_bytes=1024,
        max_file_bytes=1024,
        max_files=10,
        inactivity_ttl_hours=1,
    )


def test_principal_schema_enforces_workspace_credential_and_key_contracts(principal_db):
    conn = principal_db
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert {
        "principals",
        "personal_workspaces",
        "credentials",
        "credential_verifier_roots",
    }.issubset(tables)

    created = "2026-09-06T12:00:00+00:00"
    conn.execute(
        "INSERT INTO principals VALUES (?, 'active', '', ?, ?, NULL)",
        ("prn_" + "1" * 32, created, created),
    )
    conn.execute(
        "INSERT INTO personal_workspaces VALUES (?, ?, ?, ?)",
        ("wsp_" + "2" * 32, "prn_" + "1" * 32, "ws_" + "3" * 32, created),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO personal_workspaces VALUES (?, ?, ?, ?)",
            ("wsp_" + "4" * 32, "prn_" + "1" * 32, "ws_" + "5" * 32, created),
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO principals VALUES (?, 'active', ?, ?, ?, NULL)",
            ("prn_" + "6" * 32, "x" * 257, created, created),
        )

    indexes = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    }
    assert "idx_credentials_active_lookup" in indexes
    assert "idx_credentials_principal_active" in indexes
    assert "idx_credential_verifier_roots_active" in indexes


def test_anonymous_attachment_preserves_storage_and_never_persists_reusable_secret(
    principal_db,
    tmp_path,
):
    anonymous_id = str(uuid.uuid4())
    settings = _workspace_settings(tmp_path / "workspaces")
    preserved = anonymous_workspace_storage_key(anonymous_id)
    anonymous_dir = settings.root / preserved
    anonymous_dir.mkdir()
    evidence = anonymous_dir / "evidence.txt"
    evidence.write_text("keep me\n", encoding="utf-8")

    bundle = storage.create_principal_with_credential(
        anonymous_id=anonymous_id,
        credential_label="Laptop",
        settings=settings,
        conn=principal_db,
    )

    assert bundle.workspace.storage_key == preserved
    assert storage.get_personal_workspace_path(
        bundle.principal.id,
        settings=settings,
        conn=principal_db,
    ) == anonymous_dir
    assert evidence.read_text(encoding="utf-8") == "keep me\n"
    assert bundle.credential.secret.startswith(f"dlc_v1_{bundle.credential.metadata.id}_")
    assert bundle.credential.secret not in repr(bundle)
    assert "secret" not in bundle.to_safe_dict()["credential"]

    dump = "\n".join(principal_db.iterdump())
    reusable_component = bundle.credential.secret.removeprefix(
        f"dlc_v1_{bundle.credential.metadata.id}_"
    )
    assert bundle.credential.secret not in dump
    assert reusable_component not in dump
    columns = [row[1] for row in principal_db.execute("PRAGMA table_info(credentials)")]
    assert "secret" not in columns
    assert "token" not in columns


def test_credential_lifecycle_keeps_principal_workspace_and_path_stable(principal_db, tmp_path):
    settings = _workspace_settings(tmp_path / "workspaces")
    bundle = storage.create_principal_with_credential(
        credential_label="First device",
        settings=settings,
        conn=principal_db,
    )
    before = storage.get_personal_workspace(bundle.principal.id, conn=principal_db)
    before_path = storage.get_personal_workspace_path(
        bundle.principal.id,
        settings=settings,
        conn=principal_db,
    )

    renamed = storage.rename_credential(
        bundle.principal.id,
        bundle.credential.metadata.id,
        "Primary laptop",
        conn=principal_db,
    )
    assert renamed.label == "Primary laptop"
    expires = datetime(2026, 10, 1, tzinfo=timezone.utc)
    expiring = storage.set_credential_expiry(
        bundle.principal.id,
        renamed.id,
        expires,
        conn=principal_db,
    )
    assert expiring.expires_at == expires.isoformat()

    replacement = storage.rotate_credential(
        bundle.principal.id,
        renamed.id,
        conn=principal_db,
    )
    credentials = {item.id: item for item in storage.list_credentials(bundle.principal.id, conn=principal_db)}
    assert credentials[renamed.id].revoked_at is not None
    assert credentials[replacement.metadata.id].created_by_credential_id == renamed.id
    assert replacement.metadata.principal_id == bundle.principal.id

    after = storage.get_personal_workspace(bundle.principal.id, conn=principal_db)
    after_path = storage.get_personal_workspace_path(
        bundle.principal.id,
        settings=settings,
        conn=principal_db,
    )
    assert after == before
    assert after_path == before_path
    assert not before_path.exists()

    revoked = storage.revoke_credential(
        bundle.principal.id,
        replacement.metadata.id,
        reason="device lost",
        allow_lockout=True,
        conn=principal_db,
    )
    assert revoked.revocation_reason == "device lost"
    disabled = storage.disable_principal(
        bundle.principal.id,
        reason="operator hold",
        conn=principal_db,
    )
    assert disabled.status == "disabled"
    with pytest.raises(PrincipalDisabled):
        storage.issue_credential(bundle.principal.id, conn=principal_db)
    assert storage.enable_principal(bundle.principal.id, conn=principal_db).status == "active"


def test_last_used_updates_are_bounded(principal_db, tmp_path):
    bundle = storage.create_principal_with_credential(
        settings=_workspace_settings(tmp_path / "workspaces"),
        conn=principal_db,
    )
    credential_id = bundle.credential.metadata.id
    first = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    assert storage.touch_credential_last_used(credential_id, used_at=first, conn=principal_db) is True
    assert storage.touch_credential_last_used(
        credential_id,
        used_at=first + timedelta(minutes=1),
        conn=principal_db,
    ) is False
    assert storage.touch_credential_last_used(
        credential_id,
        used_at=first + timedelta(minutes=6),
        conn=principal_db,
    ) is True


def test_workspace_validator_rejects_traversal_symlinks_duplicates_and_wrong_types(
    principal_db,
    tmp_path,
):
    settings = _workspace_settings(tmp_path / "workspaces")
    for unsafe in ("../bad", "../other-session", "/tmp/ws_" + "a" * 32, "sess_not-a-digest"):
        with pytest.raises(WorkspaceStorageError):
            validate_workspace_storage_key(unsafe, settings)

    outside = tmp_path / "outside"
    outside.mkdir()
    symlink_key = "ws_" + "a" * 32
    (settings.root / symlink_key).symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceStorageError, match="symlink"):
        resolve_workspace_storage_path(symlink_key, settings)

    bundle = storage.create_principal_with_credential(settings=settings, conn=principal_db)
    with pytest.raises(WorkspaceAlreadyAttached):
        validate_workspace_storage_key(
            bundle.workspace.storage_key,
            settings,
            conn=principal_db,
        )


def test_injected_creation_failure_rolls_back_database_and_leaves_anonymous_data(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(data_dir))
    reset_master_key_cache_for_tests()
    db_path = tmp_path / "principal.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for statement in v0078_principal_credential_persistence.MIGRATION.statements_for(DatabaseBackend.SQLITE):
            conn.execute(statement)
        for statement in v0079_credential_scopes.MIGRATION.statements_for(DatabaseBackend.SQLITE):
            conn.execute(statement)

    def connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    settings = _workspace_settings(tmp_path / "workspaces")
    anonymous_id = str(uuid.uuid4())
    anonymous_dir = settings.root / anonymous_workspace_storage_key(anonymous_id)
    anonymous_dir.mkdir()
    evidence = anonymous_dir / "evidence.txt"
    evidence.write_text("unchanged\n", encoding="utf-8")

    monkeypatch.setattr(storage, "_insert_credential", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")))
    with pytest.raises(RuntimeError, match="injected"):
        storage.create_principal_with_credential(
            anonymous_id=anonymous_id,
            settings=settings,
            connect=connect,
        )

    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM principals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM personal_workspaces").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM credentials").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM credential_verifier_roots").fetchone()[0] == 0
    assert evidence.read_text(encoding="utf-8") == "unchanged\n"
    assert list(settings.root.iterdir()) == [anonymous_dir]


def test_caller_connection_failure_rolls_back_verifier_root_and_attachment(
    principal_db,
    tmp_path,
    monkeypatch,
):
    settings = _workspace_settings(tmp_path / "workspaces")
    anonymous_id = str(uuid.uuid4())
    anonymous_dir = settings.root / anonymous_workspace_storage_key(anonymous_id)
    anonymous_dir.mkdir()
    evidence = anonymous_dir / "evidence.txt"
    evidence.write_text("unchanged\n", encoding="utf-8")

    monkeypatch.setattr(
        storage,
        "_insert_credential",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        storage.create_principal_with_credential(
            anonymous_id=anonymous_id,
            settings=settings,
            conn=principal_db,
        )

    for table_name in (
        "principals",
        "personal_workspaces",
        "credentials",
        "credential_verifier_roots",
    ):
        assert principal_db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] == 0
    assert evidence.read_text(encoding="utf-8") == "unchanged\n"


def test_verifier_roots_rotate_rewrap_and_reject_referenced_deletion(principal_db, tmp_path):
    bundle = storage.create_principal_with_credential(
        settings=_workspace_settings(tmp_path / "workspaces"),
        conn=principal_db,
    )
    before = principal_db.execute(
        "SELECT wrapped_root, wrap_nonce FROM credential_verifier_roots WHERE version = 1"
    ).fetchone()
    assert rewrap_verifier_roots(principal_db) == 1
    after = principal_db.execute(
        "SELECT wrapped_root, wrap_nonce FROM credential_verifier_roots WHERE version = 1"
    ).fetchone()
    assert (bytes(after[0]), bytes(after[1])) != (bytes(before[0]), bytes(before[1]))

    assert rotate_verifier_root(principal_db) == 2
    second = storage.issue_credential(bundle.principal.id, conn=principal_db)
    assert second.metadata.verifier_root_version == 2
    with pytest.raises(VerifierKeyError, match="referenced"):
        delete_retired_verifier_root(principal_db, 1)


def test_schema_guard_can_be_scoped_for_pre_cutover_fixture_inspection(principal_db):
    principal_db.execute("CREATE TABLE session_tokens (token TEXT PRIMARY KEY)")
    assert_post_cutover_schema(principal_db, DatabaseBackend.SQLITE)
    with pytest.raises(PostCutoverSchemaMismatch, match="session_tokens"):
        assert_post_cutover_schema(principal_db, DatabaseBackend.SQLITE, enabled=True)


def test_metadata_bounds_are_enforced_before_sql(principal_db, tmp_path):
    bundle = storage.create_principal_with_credential(
        settings=_workspace_settings(tmp_path / "workspaces"),
        conn=principal_db,
    )
    with pytest.raises(IdentityStorageError, match="64"):
        storage.rename_credential(
            bundle.principal.id,
            bundle.credential.metadata.id,
            "x" * 65,
            conn=principal_db,
        )
