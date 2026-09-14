# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Operator suspension inventory, preserved user pauses, and explicit resumption."""

import sqlite3
from contextlib import nullcontext

import pytest

from core.database_backend import DatabaseBackend
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations
from services.auth import lifecycle, storage
from services.auth.suspended_work import operator_suspended_work
from services.notifications import channels_store
from services.projects import digests
from services.scheduler.service import create_schedule, resume_schedule
from services.secrets.vault import reset_master_key_cache_for_tests
from services.workspace.models import WorkspaceSettings


NOW = "2026-09-13T12:00:00+00:00"


@pytest.fixture
def suspended_db(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    reset_master_key_cache_for_tests()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
    monkeypatch.setattr("services.auth.background_runtime.stop_principal_active_work", lambda _principal: ())
    monkeypatch.setattr(channels_store.database, "db_connect", lambda: nullcontext(conn))
    monkeypatch.setattr(channels_store.database, "DB_BACKEND", DatabaseBackend.SQLITE)
    settings = WorkspaceSettings(True, "volume", tmp_path / "workspaces", 1024, 1024, 10, 1)
    bundles = [storage.create_principal_with_credential(settings=settings, conn=conn) for _ in range(2)]
    yield conn, bundles
    conn.close()
    reset_master_key_cache_for_tests()


def _insert(conn, table, **fields):
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(fields.values()))  # nosec


def _seed_work(conn, bundle, prefix, *, manually_paused=False, jobs=True):
    owner = {"personal_workspace_id": bundle.workspace.id, "principal_id": bundle.principal.id}
    timestamps = {"created": NOW, "updated": NOW}
    schedule = create_schedule(
        bundle.workspace.id, command_text="true", label=prefix, cadence_preset="hourly",
        enabled=not manually_paused, principal_id=bundle.principal.id,
        credential_id=bundle.credential.metadata.id, conn=conn,
    )
    _insert(conn, "watchers", id=f"watcher_{prefix}", **owner, **timestamps, label=prefix,
            command_text="true", schedule_id=schedule.id, baseline_run_id="",
            state="paused" if manually_paused else "ok", state_reason="paused" if manually_paused else "")
    channel = channels_store.create_notification_channel(
        bundle.workspace.id,
        {"kind": "webhook", "label": prefix, "secret_values": {"url": "https://notify.example.test/hook"},
         "triggers": ["run_complete"], "muted": manually_paused},
        audit_fields={"actor_principal_id": bundle.principal.id},
    )
    project = f"project_{prefix}"
    _insert(conn, "projects", id=project, personal_workspace_id=bundle.workspace.id,
            name=f"Project {prefix}", slug=prefix, **timestamps)
    _insert(conn, "project_digest_settings", project_id=project, **owner, **timestamps,
            enabled=not manually_paused)
    if not jobs:
        return schedule, channel, project
    _insert(conn, "workflow_executions", id=f"workflow_{prefix}", **owner, **timestamps,
            workflow_id="example", workflow_source="user", title=f"Workflow {prefix}")
    _insert(conn, "notification_events", id=f"delivery_{prefix}", **owner, created=NOW,
            channel_id=channel["id"], trigger="project_digest")
    _insert(conn, "ai_run_assists", id=f"assist_{prefix}", **owner, created_at=NOW,
            run_id=f"run_{prefix}", variant="summary")
    _insert(conn, "project_assessments", id=f"assessment_{prefix}", personal_workspace_id=bundle.workspace.id,
            project_id=project, title="Review", profile_key="web", profile_version="1.0",
            started_at=NOW, created_at=NOW, updated_at=NOW)
    _insert(conn, "project_assessment_checks", id=f"check_{prefix}", assessment_id=f"assessment_{prefix}",
            category="validation", check_key="private_oast", target_entity_id=f"entity_{prefix}",
            target_type="domain", target_value="app.example.test", target_value_hash="target-hash",
            policy_level="intrusive", recommended_action_key="oast_private_callback", created_at=NOW, updated_at=NOW)
    _insert(conn, "project_http_profiles", id=f"http_{prefix}", personal_workspace_id=bundle.workspace.id,
            project_id=project, name="Public", name_key="public", base_url="https://app.example.test",
            created_at=NOW, updated_at=NOW)
    _insert(conn, "zap_connector_jobs", id=f"zap_{prefix}", **owner, project_id=project,
            assessment_id=f"assessment_{prefix}", check_id=f"check_{prefix}", http_profile_id=f"http_{prefix}",
            http_profile_revision=1, policy_level="safe", target_count=1,
            created_at=NOW, updated_at=NOW, expires_at=NOW)
    _insert(conn, "oast_correlations", id=f"oast_{prefix}", **owner, project_id=project,
            assessment_id=f"assessment_{prefix}", check_id=f"check_{prefix}", target_entity_id=f"entity_{prefix}",
            action_key="oast_private_callback", callback_label=f"callback-{prefix}",
            allowed_domain="callbacks.example.test", service_origin_sha256="a" * 64,
            created_at=NOW, updated_at=NOW, active_until=NOW, purge_at=NOW)
    return schedule, channel, project


def test_status_lists_all_suspended_kinds_after_disable_and_enable(suspended_db):
    conn, (bundle, other) = suspended_db
    _seed_work(conn, bundle, "active")
    _seed_work(conn, bundle, "manual", manually_paused=True, jobs=False)
    _seed_work(conn, other, "other")
    conn.commit()
    assert operator_suspended_work(bundle.principal.id, connect=lambda: conn)["items"] == []
    for owner in (bundle, other):
        lifecycle.set_principal_enabled(owner.principal.id, enabled=False, reason="review", connect=lambda: conn)

    suspended = operator_suspended_work(bundle.principal.id, connect=lambda: conn)
    assert suspended["count"] == 9
    assert suspended["resumable_count"] == 4
    assert {item["kind"] for item in suspended["items"]} == {
        "schedule", "watcher", "notification_channel", "project_digest", "workflow_execution",
        "notification_delivery", "ai_assist", "zap_job", "oast_correlation",
    }
    assert {item["personal_workspace_id"] for item in suspended["items"]} == {bundle.workspace.id}
    assert all(item["review_in"] and item["reason"] == "principal_disabled" for item in suspended["items"])
    digest = next(item for item in suspended["items"] if item["kind"] == "project_digest")
    assert digest["label"] == "Project active"
    assert "manual" not in str(suspended)
    assert bundle.credential.secret not in str(suspended)
    lifecycle.set_principal_enabled(bundle.principal.id, enabled=True, connect=lambda: conn)
    assert operator_suspended_work(bundle.principal.id, connect=lambda: conn) == suspended
    assert conn.execute("SELECT state_reason FROM watchers WHERE id = 'watcher_manual'").fetchone()[0] == "paused"


def test_channel_and_digest_keep_reason_until_explicit_resume(suspended_db):
    conn, (bundle, _) = suspended_db
    schedule, channel, project = _seed_work(conn, bundle, "resume", jobs=False)
    conn.commit()
    lifecycle.set_principal_enabled(bundle.principal.id, enabled=False, reason="review", connect=lambda: conn)
    lifecycle.set_principal_enabled(bundle.principal.id, enabled=True, connect=lambda: conn)
    changed = channels_store.update_notification_channel(bundle.workspace.id, channel["id"], {"label": "Reviewed"})
    assert changed["muted"] and changed["muted_reason"] == "principal_disabled"
    settings = digests.get_digest_settings(bundle.workspace.id, project, conn=conn)
    assert settings is not None
    assert not settings["enabled"] and settings["paused_reason"] == "principal_disabled"
    settings = digests.save_digest_settings(bundle.workspace.id, project, {"enabled": False}, conn=conn)
    assert settings["paused_reason"] == "principal_disabled"

    resumed = channels_store.update_notification_channel(bundle.workspace.id, channel["id"], {"muted": False})
    assert not resumed["muted"] and resumed["muted_reason"] == ""
    settings = digests.save_digest_settings(bundle.workspace.id, project,
                                           {"enabled": True, "channel_ids": [channel["id"]]}, conn=conn)
    assert settings["enabled"] and settings["paused_reason"] == ""
    resume_schedule(schedule.id, conn=conn)
    assert [item["kind"] for item in operator_suspended_work(bundle.principal.id, connect=lambda: conn)["items"]] == [
        "watcher",
    ]


def test_upgrade_recovers_pause_reasons_only_for_disabled_principals(suspended_db):
    conn, (bundle, other) = suspended_db
    _seed_work(conn, bundle, "disabled", manually_paused=True, jobs=False)
    _seed_work(conn, other, "active", manually_paused=True, jobs=False)
    conn.execute("UPDATE principals SET status = 'disabled', disabled_at = ? WHERE id = ?", (NOW, bundle.principal.id))
    # Recreate the pre-migration columns and apply the real incremental upgrade.
    conn.execute("ALTER TABLE notification_channels DROP COLUMN muted_reason")
    conn.execute("ALTER TABLE project_digest_settings DROP COLUMN paused_reason")
    conn.execute("DELETE FROM schema_migrations WHERE version = '0085'")
    conn.commit()
    run_migrations(conn, MIGRATIONS, backend=DatabaseBackend.SQLITE)
    assert {item["kind"] for item in operator_suspended_work(bundle.principal.id, connect=lambda: conn)["items"]} == {
        "notification_channel", "project_digest",
    }
    assert operator_suspended_work(other.principal.id, connect=lambda: conn)["items"] == []
