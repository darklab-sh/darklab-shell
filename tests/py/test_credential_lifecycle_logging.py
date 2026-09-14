# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Lifecycle milestones describe committed changes without credential material."""

import json
import logging
from types import SimpleNamespace

import pytest

import config
from conftest import build_test_config, copy_pristine_sqlite_database, make_test_app
from core import database
from core.database_access import get_db_connect
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import anonymous_session_id
from services.auth import lifecycle, lifecycle_logging, oidc, storage
from services.auth.resolver import resolve_authentication
from services.scheduler.service import create_schedule
from services.workspace.models import WorkspaceSettings


@pytest.fixture
def milestones(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "milestones.db")))
    app = make_test_app()
    app.config["DARKLAB_CONFIG"] = build_test_config({"audit_log_enabled": False})
    settings = WorkspaceSettings(True, "volume", tmp_path / "workspaces", 1024, 1024, 10, 1)
    settings.root.mkdir()
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append((record, _snapshot()))
    logger = logging.Logger("lifecycle-milestones", logging.INFO)
    logger.addHandler(handler)
    monkeypatch.setattr(lifecycle_logging, "log", logger)
    return SimpleNamespace(app=app, records=records, settings=settings)


def _snapshot():
    with get_db_connect()() as conn:
        return {
            "principals": {row["id"]: row["status"] for row in conn.execute("SELECT id, status FROM principals")},
            "credentials": {row["id"]: row["revoked_at"] for row in conn.execute("SELECT id, revoked_at FROM credentials")},
            "identities": conn.execute("SELECT COUNT(*) AS count FROM oidc_identities").fetchone()["count"],
        }


def _bundle(ctx):
    return storage.create_principal_with_credential(credential_label="private-initial-label", settings=ctx.settings)


def _context(bundle):
    context = resolve_authentication({"X-Darklab-Credential": bundle.credential.secret}).context
    assert context is not None
    return context


def _assert_private(records, *private):
    for record, _snapshot_at_emit in records:
        assert record.levelno == logging.INFO
        assert record.exc_info is None
        assert set(_extra_fields(record)) <= {
            "source",
            "request_id",
            "principal_id",
            "status",
            "credential_id",
            "credential_type",
            "scope_count",
            "previous_credential_id",
            "paused_work_count",
        }
        rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
        for value in private:
            assert value not in rendered
        assert json.loads(GELFFormatter().format(record))["short_message"] == record.msg


@pytest.mark.parametrize("surface", ["anonymous", "operator"])
@pytest.mark.parametrize("audit_enabled", [False, True])
def test_principal_creation_milestones_see_committed_data_with_or_without_audit(milestones, surface, audit_enabled, monkeypatch):
    ctx = milestones
    monkeypatch.setattr(config, "CFG", build_test_config({"audit_log_enabled": audit_enabled}))
    with ctx.app.app_context():
        if surface == "anonymous":
            bundle = lifecycle.create_principal(
                anonymous_id=anonymous_session_id("milestone upgrade"),
                credential_label="private-new-label",
                settings=ctx.settings,
                request_fields={"request_id": "request-123", "client_ip": "192.0.2.88", "user_agent": "private-agent"},
            )
        else:
            bundle = lifecycle.operator_bootstrap(credential_label="private-new-label", settings=ctx.settings)
    assert [record.msg for record, _ in ctx.records] == ["PRINCIPAL_CREATED", "CREDENTIAL_CREATED"]
    for record, snapshot in ctx.records:
        assert snapshot["principals"] == {bundle.principal.id: "active"}
        assert snapshot["credentials"] == {bundle.credential.metadata.id: None}
        assert record.request_id == ("request-123" if surface == "anonymous" else "unknown")
    with get_db_connect()() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM audit_events").fetchone()["count"]
    assert bool(count) == audit_enabled
    _assert_private(ctx.records, bundle.credential.secret, "private-new-label", "192.0.2.88", "private-agent")


@pytest.mark.parametrize("surface", ["self_service", "operator", "deferred"])
@pytest.mark.parametrize("kind", ["portable", "pat"])
def test_issue_rotate_and_revoke_log_exact_committed_outcomes(milestones, surface, kind):
    ctx = milestones
    bundle = _bundle(ctx)
    context = _context(bundle)
    options = {"credential_type": kind, "label": "private-device-label"}
    if kind == "pat":
        options["scopes"] = ["identity:read"]
    if surface == "operator":
        issued = lifecycle.operator_issue(bundle.principal.id, **options)
        replacement = lifecycle.operator_rotate(bundle.principal.id, issued.metadata.id)
    else:
        issued = lifecycle.issue(context, **options)
        replacement = lifecycle.rotate(context, issued.metadata.id, defer_revocation=surface == "deferred")
    target = issued if surface == "deferred" else replacement
    with get_db_connect()() as conn:
        create_schedule(
            bundle.workspace.id,
            command_text="true",
            cadence_preset="hourly",
            label="private-schedule-label",
            principal_id=bundle.principal.id,
            credential_id=target.metadata.id,
            conn=conn,
        )
        conn.commit()
    for _ in range(2):
        if surface == "operator":
            lifecycle.operator_revoke(
                bundle.principal.id, target.metadata.id, reason="private-revocation-reason", pause_related_work=True
            )
        else:
            lifecycle.revoke(context, target.metadata.id, reason="private-revocation-reason", pause_related_work=True)
    assert [record.msg for record, _ in ctx.records] == [
        "CREDENTIAL_CREATED",
        "CREDENTIAL_CREATED" if surface == "deferred" else "CREDENTIAL_ROTATED",
        "CREDENTIAL_REVOKED",
    ]
    created, rotation, revoked = [record for record, _ in ctx.records]
    assert created.credential_id == issued.metadata.id
    assert rotation.credential_id == replacement.metadata.id
    assert revoked.credential_id == target.metadata.id and revoked.paused_work_count == 1
    assert all(record.credential_type == kind for record, _ in ctx.records)
    assert (ctx.records[1][1]["credentials"][issued.metadata.id] is None) == (surface == "deferred")
    assert ctx.records[2][1]["credentials"][target.metadata.id] is not None
    if surface == "deferred":
        assert not hasattr(rotation, "previous_credential_id")
    else:
        assert rotation.previous_credential_id == issued.metadata.id
    _assert_private(
        ctx.records,
        issued.secret,
        replacement.secret,
        "private-device-label",
        "private-revocation-reason",
        "private-schedule-label",
    )


def test_operator_recovery_emits_only_for_new_revocations_after_replacement_commits(milestones):
    ctx = milestones
    bundle = _bundle(ctx)
    second = storage.issue_credential(bundle.principal.id, credential_type="pat", scopes=["identity:read"])
    retired = storage.issue_credential(bundle.principal.id)
    storage.revoke_credential(bundle.principal.id, retired.metadata.id)
    replacement = lifecycle.operator_recover(bundle.principal.id, label="private-recovery-label")
    revoked = [record for record, _ in ctx.records if record.msg == "CREDENTIAL_REVOKED"]
    assert {record.credential_id for record in revoked} == {bundle.credential.metadata.id, second.metadata.id}
    assert [record.msg for record, _ in ctx.records] == ["CREDENTIAL_REVOKED", "CREDENTIAL_REVOKED", "CREDENTIAL_CREATED"]
    for record, snapshot in ctx.records:
        assert record.source == "local_operator_recovery"
        assert [key for key, value in snapshot["credentials"].items() if value is None] == [replacement.metadata.id]
    _assert_private(ctx.records, bundle.credential.secret, second.secret, replacement.secret, "private-recovery-label")


def test_principal_status_logs_only_transitions_after_commit(milestones):
    ctx = milestones
    bundle = _bundle(ctx)
    for enabled in (True, False, False, True, True):
        lifecycle.set_principal_enabled(bundle.principal.id, enabled=enabled, reason="private-disable-reason")
    assert [(record.msg, record.status) for record, _ in ctx.records] == [
        ("PRINCIPAL_STATUS_CHANGED", "disabled"),
        ("PRINCIPAL_STATUS_CHANGED", "active"),
    ]
    for record, snapshot in ctx.records:
        assert snapshot["principals"][bundle.principal.id] == record.status
    _assert_private(ctx.records, "private-disable-reason")


def _provider_identity():
    flow = oidc.OIDCFlow("private-state", "private-nonce", "private-verifier", "login", "", "", "/")
    return oidc.complete_identity(
        {"oidc_provisioning": "auto"}, flow, "https://private-provider.example", "private-provider-subject"
    )


def test_provider_provisioning_logs_one_committed_principal_without_provider_identity(milestones):
    ctx = milestones
    identity = _provider_identity()
    assert _provider_identity() == identity
    assert len(ctx.records) == 1
    record, snapshot = ctx.records[0]
    assert record.msg == "PRINCIPAL_CREATED" and record.principal_id == identity.principal_id
    assert record.source == "provider_provisioning" and snapshot["identities"] == 1
    _assert_private(ctx.records, "private-state", "private-nonce", "private-verifier", "private-provider", identity.id)


@pytest.mark.parametrize("operation", ["create", "issue", "rotate", "revoke", "status", "recovery", "provider"])
def test_commit_failure_emits_no_success_and_rolls_back_every_lifecycle(operation, milestones, monkeypatch):
    ctx = milestones
    bundle = _bundle(ctx)
    context = _context(bundle)
    before = _snapshot()
    real_transaction = lifecycle_logging.run_transaction
    connect = get_db_connect()

    class FailedCommit:
        def __enter__(self):
            self.conn = connect()
            self.conn.__enter__()
            return self

        def __exit__(self, *args):
            return self.conn.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def commit(self):
            raise RuntimeError("private-commit-failure")

    monkeypatch.setattr(
        lifecycle_logging, "run_transaction", lambda callback, **_kwargs: real_transaction(callback, connect=FailedCommit)
    )
    operations = {
        "create": lambda: lifecycle.create_principal(
            anonymous_id=anonymous_session_id("failed milestone creation"), settings=ctx.settings
        ),
        "issue": lambda: lifecycle.issue(context),
        "rotate": lambda: lifecycle.rotate(context, bundle.credential.metadata.id),
        "revoke": lambda: lifecycle.revoke(context, bundle.credential.metadata.id, confirm_lockout=True),
        "status": lambda: lifecycle.set_principal_enabled(bundle.principal.id, enabled=False, reason="private-reason"),
        "recovery": lambda: lifecycle.operator_recover(bundle.principal.id),
        "provider": _provider_identity,
    }
    with pytest.raises(RuntimeError, match="private-commit-failure"):
        operations[operation]()
    assert not ctx.records
    assert _snapshot() == before


def test_recovery_rollback_drops_already_queued_revocation_events(milestones, monkeypatch):
    ctx = milestones
    bundle = _bundle(ctx)
    before = _snapshot()

    def failed_issue(*_args, **_kwargs):
        raise RuntimeError("private-replacement-failure")

    monkeypatch.setattr(storage, "issue_credential", failed_issue)
    with pytest.raises(RuntimeError, match="private-replacement-failure"):
        lifecycle.operator_recover(bundle.principal.id)
    assert not ctx.records
    assert _snapshot() == before


def test_rejected_lockout_and_failed_bootstrap_output_emit_no_milestones(milestones):
    ctx = milestones

    def failed_sink(_secret):
        raise RuntimeError("private-output-failure")

    with pytest.raises(RuntimeError, match="private-output-failure"):
        lifecycle.operator_bootstrap(settings=ctx.settings, credential_sink=failed_sink)
    assert not _snapshot()["principals"] and not ctx.records
    bundle = _bundle(ctx)
    from services.auth.contracts import LastCredentialLockout

    with pytest.raises(LastCredentialLockout):
        lifecycle.revoke(_context(bundle), bundle.credential.metadata.id)
    assert not ctx.records
