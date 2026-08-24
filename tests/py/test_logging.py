# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Tests for the structured logging system.

Covers:
  - _extra_fields helper    (logging_setup.py)
  - _TextFormatter          (logging_setup.py)
  - GELFFormatter           (logging_setup.py)
  - configure_logging       (logging_setup.py)
  - Log event emission      (app.py routes, database.py)

Log event tests avoid pytest's caplog because the 'shell' logger has
propagate=False (records don't reach the root handler that caplog attaches).
Instead, we use mock.patch.object on shell_app_module.log to intercept calls directly.

Run with: pytest tests/ (from the repo root)
"""

import io
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import uuid
import unittest.mock as mock
from pathlib import Path

import pytest

import app as shell_app_module
import config as app_config
from conftest import build_test_config
from conftest import make_test_app as _test_app
import core.database as db_module
from core.database import DB_PATH, db_connect, db_init
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields, configure_logging
from services.assessments import profiles as assessment_profiles
from services.assessments.batch import active_monitor as assessment_active_monitor

# ── Helpers ───────────────────────────────────────────────────────────────────

def _emit(formatter, level, msg, extra=None):
    """Emit one log record through a formatter and return the formatted string."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(formatter)
    logger = logging.getLogger(f"_test_fmt_{id(formatter)}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.log(level, msg, extra=extra or {})
    return buf.getvalue().strip()


def _run_config_startup(
    tmp_path: Path,
    *,
    base_config: str,
    local_config: str = "",
    fatal: bool = False,
    configure_twice: bool = False,
) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    shipped_dir = tmp_path / "shipped"
    local_dir = tmp_path / "local"
    shipped_dir.mkdir()
    local_dir.mkdir()
    (shipped_dir / "config.yaml").write_text(base_config, encoding="utf-8")
    if local_config:
        (local_dir / "config.local.yaml").write_text(local_config, encoding="utf-8")

    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith(("AI_", "DATABASE_")) or name in {
            "APP_CONF_DIR",
            "APP_LOCAL_CONF_DIR",
            "ASSET_BUNDLE_MODE",
            "PROMETHEUS_MULTIPROC_DIR",
            "INTERACTIVE_PTY_ENABLED",
            "RAW_PACKET_SCANNING_ENABLED",
            "ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED",
            "RESTRICTED_COMMAND_INPUT_CIDRS",
            "WORKSPACE_BACKEND",
            "WORKSPACE_ENABLED",
            "WORKSPACE_ROOT",
        }:
            env.pop(name, None)
    env.update({
        "APP_CONF_DIR": str(shipped_dir),
        "APP_LOCAL_CONF_DIR": str(local_dir),
        "PYTHONPATH": str(repo_root / "app"),
    })

    if fatal:
        program = "import config"
    else:
        calls = ["configure_runtime_logging()"]
        if configure_twice:
            calls.append("configure_runtime_logging()")
        calls.append("log_loaded_config()")
        program = (
            "from runtime_bootstrap import configure_runtime_logging, log_loaded_config; "
            + "; ".join(calls)
        )
    return subprocess.run(
        [sys.executable, "-c", program],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _gelf_records(stderr: str) -> list[dict]:
    return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]


def get_client(*, use_forwarded_for=True):
    client = _test_app().test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


def _post_brokered_run(client, command, *, headers=None):
    request_headers = dict(headers or {})
    request_headers.setdefault("X-Session-ID", "log-test-session")
    with mock.patch("blueprints.run.broker_available", return_value=True):
        start_resp = client.post("/runs", json={"command": command}, headers=request_headers)
    if start_resp.status_code != 202:
        return start_resp
    stream = json.loads(start_resp.data)["stream"]
    stream_resp = client.get(stream, headers=request_headers)
    for _ in range(10):
        if stream_resp.status_code != 404:
            return stream_resp
        time.sleep(0.01)
        stream_resp = client.get(stream, headers=request_headers)
    return stream_resp


class _FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else ""

    def close(self):
        pass


class _FakeProc:
    def __init__(self, lines=None, pid=4321, returncode=0):
        self.pid = pid
        self.returncode = returncode
        self.stdout = _FakeStdout(lines or [])

    def wait(self):
        return self.returncode

    def poll(self):
        if getattr(self.stdout, "_lines", []):
            return None
        return self.returncode


# ── _extra_fields ─────────────────────────────────────────────────────────────

class TestExtraFields:
    def _make_record(self, **kwargs):
        record = logging.LogRecord(
            name="shell", level=logging.INFO, pathname="",
            lineno=0, msg="TEST", args=(), exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_bare_record_returns_no_extras(self):
        assert _extra_fields(self._make_record()) == {}

    def test_custom_field_is_returned(self):
        extras = _extra_fields(self._make_record(ip="1.2.3.4"))
        assert extras["ip"] == "1.2.3.4"

    def test_multiple_custom_fields_all_returned(self):
        extras = _extra_fields(self._make_record(ip="1.2.3.4", run_id="abc", cmd="ping"))
        assert extras["ip"] == "1.2.3.4"
        assert extras["run_id"] == "abc"
        assert extras["cmd"] == "ping"

    def test_stdlib_attrs_excluded(self):
        extras = _extra_fields(self._make_record())
        for attr in ("levelname", "levelno", "lineno", "module", "process", "thread", "threadName"):
            assert attr not in extras, f"stdlib attr '{attr}' should be excluded"

    def test_underscore_prefixed_attr_excluded(self):
        extras = _extra_fields(self._make_record(_private="secret"))
        assert "_private" not in extras

    def test_result_keys_are_sorted(self):
        extras = _extra_fields(self._make_record(z="last", a="first", m="mid"))
        assert list(extras.keys()) == sorted(extras.keys())


# ── _TextFormatter ────────────────────────────────────────────────────────────

class TestTextFormatter:
    def test_output_starts_with_iso_timestamp(self):
        import re
        out = _emit(_TextFormatter(), logging.INFO, "TEST")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", out)

    def test_timestamp_is_utc_z_suffix(self):
        out = _emit(_TextFormatter(), logging.INFO, "TEST")
        # Timestamp must end with Z, not an offset like +00:00
        ts = out.split(" ")[0]
        assert ts.endswith("Z")

    def test_debug_level_label(self):
        assert "[DEBUG]" in _emit(_TextFormatter(), logging.DEBUG, "X")

    def test_info_level_label(self):
        assert "[INFO ]" in _emit(_TextFormatter(), logging.INFO, "X")

    def test_warn_level_label(self):
        assert "[WARN ]" in _emit(_TextFormatter(), logging.WARNING, "X")

    def test_error_level_label(self):
        assert "[ERROR]" in _emit(_TextFormatter(), logging.ERROR, "X")

    def test_message_present_in_output(self):
        assert "RUN_START" in _emit(_TextFormatter(), logging.INFO, "RUN_START")

    def test_extra_field_appended(self):
        out = _emit(_TextFormatter(), logging.INFO, "RUN_START", extra={"ip": "1.2.3.4"})
        assert "ip=1.2.3.4" in out

    def test_extra_fields_sorted_alphabetically(self):
        out = _emit(_TextFormatter(), logging.INFO, "X", extra={"z": "last", "a": "first"})
        assert out.index("a=first") < out.index("z=last")

    def test_string_with_spaces_is_repr_quoted(self):
        out = _emit(_TextFormatter(), logging.INFO, "CMD_DENIED", extra={"cmd": "nmap 8.8.8.8"})
        assert "cmd='nmap 8.8.8.8'" in out

    def test_empty_string_extra_is_repr_quoted(self):
        out = _emit(_TextFormatter(), logging.INFO, "TEST", extra={"label": ""})
        assert "label=''" in out

    def test_string_without_spaces_not_quoted(self):
        out = _emit(_TextFormatter(), logging.INFO, "RUN_START", extra={"ip": "1.2.3.4"})
        assert "ip=1.2.3.4" in out
        assert "ip='1.2.3.4'" not in out

    def test_integer_extra_not_quoted(self):
        out = _emit(_TextFormatter(), logging.INFO, "RUN_END", extra={"exit_code": 0})
        assert "exit_code=0" in out

    def test_no_extras_produces_clean_line(self):
        out = _emit(_TextFormatter(), logging.INFO, "HEALTH_OK")
        # Only timestamp, level label, and message — no trailing whitespace
        assert not out.endswith(" ")
        parts = out.split("] ", 1)
        assert len(parts) == 2
        assert parts[1].strip() == "HEALTH_OK"

    def test_stdlib_attrs_not_leaked_as_extras(self):
        out = _emit(_TextFormatter(), logging.INFO, "TEST")
        # Nothing after the message except the message itself
        after_msg = out.split("] TEST", 1)[-1]
        for attr in ("levelname", "lineno", "process", "thread"):
            assert attr not in after_msg

    def test_exception_traceback_appended(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(_TextFormatter())
        logger = logging.getLogger("_test_text_exc")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        try:
            raise ValueError("test error")
        except ValueError:
            logger.error("ERR", exc_info=True)
        out = buf.getvalue()
        assert "Traceback" in out
        assert "ValueError" in out
        assert "test error" in out


# ── GELFFormatter ─────────────────────────────────────────────────────────────

class TestGELFFormatter:
    def test_output_is_valid_json(self):
        out = _emit(GELFFormatter(), logging.INFO, "TEST")
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_gelf_version_11(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert data["version"] == "1.1"

    def test_short_message_is_event_name(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "RUN_START"))
        assert data["short_message"] == "RUN_START"

    def test_timestamp_is_numeric(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert isinstance(data["timestamp"], (int, float))

    def test_debug_level_maps_to_7(self):
        data = json.loads(_emit(GELFFormatter(), logging.DEBUG, "TEST"))
        assert data["level"] == 7

    def test_info_level_maps_to_6(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert data["level"] == 6

    def test_warning_level_maps_to_4(self):
        data = json.loads(_emit(GELFFormatter(), logging.WARNING, "TEST"))
        assert data["level"] == 4

    def test_error_level_maps_to_3(self):
        data = json.loads(_emit(GELFFormatter(), logging.ERROR, "TEST"))
        assert data["level"] == 3

    def test_extra_field_prefixed_with_underscore(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "RUN_START", extra={"ip": "1.2.3.4"}))
        assert data["_ip"] == "1.2.3.4"

    def test_extra_field_not_present_without_underscore_prefix(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "RUN_START", extra={"ip": "1.2.3.4"}))
        assert "ip" not in data

    def test_multiple_extras_all_prefixed(self):
        data = json.loads(_emit(
            GELFFormatter(), logging.INFO, "RUN_START",
            extra={
                "assist_status": "completed",
                "fire_status": "fired",
                "http_status": 202,
                "ip": "1.2.3.4",
                "project_status": "active",
                "provider_status": "ok",
                "run_id": "abc",
                "exit_code": 0,
                "version": "2.6.0",
                "source": "config.local.yaml",
                "workflow_status": "completed",
            },
        ))
        numeric_status = json.loads(_emit(
            GELFFormatter(), logging.INFO, "LEGACY_HTTP_EVENT",
            extra={"status": 200},
        ))
        text_status = json.loads(_emit(
            GELFFormatter(), logging.INFO, "LEGACY_STATE_EVENT",
            extra={"status": "error"},
        ))
        explicit_status = json.loads(_emit(
            GELFFormatter(), logging.INFO, "MIXED_COMPAT_EVENT",
            extra={"http_status": 202, "status": 500},
        ))
        invalid_http_status = json.loads(_emit(
            GELFFormatter(), logging.INFO, "INVALID_HTTP_STATUS_EVENT",
            extra={"http_status": "upstream_error"},
        ))
        normalized_feature_status = json.loads(_emit(
            GELFFormatter(), logging.INFO, "INVALID_FEATURE_STATUS_EVENT",
            extra={"provider_status": 503},
        ))
        assert data["_assist_status"] == "completed"
        assert data["_fire_status"] == "fired"
        assert data["_http_status"] == 202
        assert data["_ip"] == "1.2.3.4"
        assert data["_project_status"] == "active"
        assert data["_provider_status"] == "ok"
        assert data["_run_id"] == "abc"
        assert data["_exit_code"] == 0
        assert data["_event_version"] == "2.6.0"
        assert data["_event_source"] == "config.local.yaml"
        assert data["_workflow_status"] == "completed"
        assert "_version" not in data
        assert "_source" not in data
        assert numeric_status["_http_status"] == 200
        assert text_status["_event_status"] == "error"
        assert explicit_status["_http_status"] == 202
        assert invalid_http_status["_event_http_status"] == "upstream_error"
        assert normalized_feature_status["_provider_status"] == "503"
        assert "_status" not in numeric_status
        assert "_status" not in text_status
        assert "_http_status" not in invalid_http_status

    def test_stdlib_attrs_not_leaked_as_underscore_fields(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        for attr in ("levelname", "lineno", "process", "thread", "module", "pathname"):
            assert f"_{attr}" not in data, f"stdlib attr '_{attr}' should not appear in GELF payload"

    def test_app_name_in_payload(self):
        data = json.loads(_emit(GELFFormatter("myapp"), logging.INFO, "TEST"))
        assert data["_app"] == "myapp"

    def test_app_version_in_payload_comes_from_config(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert data["_app_version"] == shell_app_module.APP_VERSION

    def test_logger_name_in_payload(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert "_logger" in data

    def test_host_field_present_and_non_empty(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert "host" in data
        assert data["host"]

    def test_full_message_present_on_exception(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(GELFFormatter())
        logger = logging.getLogger("_test_gelf_exc")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        try:
            raise RuntimeError("oops")
        except RuntimeError:
            logger.error("ERR", exc_info=True)
        data = json.loads(buf.getvalue())
        assert "full_message" in data
        assert "RuntimeError" in data["full_message"]
        assert "oops" in data["full_message"]

    def test_compact_json_separators(self):
        # Keys and values should not be separated by ": " (with space), only ":"
        out = _emit(GELFFormatter(), logging.INFO, "TEST")
        # Check the structure — compact JSON uses "key":"value", not "key": "value"
        data = json.loads(out)
        # Re-encode compact to compare
        assert out == json.dumps(data, separators=(",", ":"), default=str)

    def test_extra_with_special_json_chars_serialises_correctly(self):
        # Values containing quotes, backslashes, and newlines must survive JSON round-trip
        value = 'nmap "target"\n--scan'
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST", extra={"cmd": value}))
        assert data["_cmd"] == value


# ── configure_logging ─────────────────────────────────────────────────────────

class TestConfigureLogging:
    def teardown_method(self, method):  # noqa: ARG002
        """Restore the 'shell' logger to the app's normal state after each test."""
        configure_logging(shell_app_module.CFG)

    def _logger(self):
        return logging.getLogger("shell")

    def test_text_format_is_default(self):
        configure_logging({})
        assert isinstance(self._logger().handlers[0].formatter, _TextFormatter)

    def test_text_format_explicit(self):
        configure_logging({"log_format": "text"})
        assert isinstance(self._logger().handlers[0].formatter, _TextFormatter)

    def test_gelf_format_selected_by_config(self):
        configure_logging({"log_format": "gelf"})
        assert isinstance(self._logger().handlers[0].formatter, GELFFormatter)

    def test_gelf_formatter_receives_app_name(self):
        configure_logging({"log_format": "gelf", "app_name": "test-app"})
        formatter = self._logger().handlers[0].formatter
        assert isinstance(formatter, GELFFormatter)
        assert formatter._app_name == "test-app"
        assert formatter._app_version == shell_app_module.APP_VERSION

    def test_log_level_info_by_default(self):
        configure_logging({})
        assert self._logger().level == logging.INFO

    def test_log_level_debug_and_assessment_events_use_pipeline(self):
        configure_logging({"log_level": "DEBUG"})
        assert self._logger().level == logging.DEBUG
        output = io.StringIO()
        handler = self._logger().handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        handler.setStream(output)

        assessment_profiles.log.info(
            "ASSESSMENT_PROFILE_CATALOG_LOADED",
            extra={"profile_count": 5},
        )
        assessment_active_monitor.log.warning(
            "ACTIVE_ASSESSMENT_BATCH_MONITOR_ERROR",
            extra={"session": "masked-session"},
        )

        rendered = output.getvalue()
        assert "ASSESSMENT_PROFILE_CATALOG_LOADED" in rendered
        assert "profile_count=5" in rendered
        assert "ACTIVE_ASSESSMENT_BATCH_MONITOR_ERROR" in rendered
        assert "session=masked-session" in rendered

    def test_log_level_warn_from_cfg(self):
        configure_logging({"log_level": "WARN"})
        assert self._logger().level == logging.WARNING

    def test_log_level_error_from_cfg(self):
        configure_logging({"log_level": "ERROR"})
        assert self._logger().level == logging.ERROR

    def test_unknown_level_falls_back_to_info(self):
        configure_logging({"log_level": "BOGUS"})
        assert self._logger().level == logging.INFO

    def test_propagate_is_false(self):
        configure_logging({})
        assert self._logger().propagate is False

    def test_logging_configured_includes_app_version(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            configure_logging(shell_app_module.CFG)
        mock_info.assert_called_once()
        _, kwargs = mock_info.call_args
        assert kwargs["extra"]["app_version"] == shell_app_module.APP_VERSION

    def test_exactly_one_handler_attached(self):
        configure_logging(shell_app_module.CFG)
        assert len(self._logger().handlers) == 1

    def test_reconfigure_does_not_duplicate_handlers(self):
        configure_logging(shell_app_module.CFG)
        configure_logging(shell_app_module.CFG)
        assert len(self._logger().handlers) == 1

    def test_werkzeug_logger_silenced_to_error(self):
        configure_logging({})
        assert logging.getLogger("werkzeug").level == logging.ERROR

    def test_log_level_lowercase_accepted(self):
        configure_logging({"log_level": "debug"})
        assert self._logger().level == logging.DEBUG


class TestConfigStartupLogging:
    @pytest.mark.parametrize("log_format", ["text", "gelf"])
    def test_debug_startup_replays_forgiving_warning_once(self, tmp_path, log_format):
        result = _run_config_startup(
            tmp_path,
            base_config=(
                "app_name: startup-test\n"
                "log_level: DEBUG\n"
                f"log_format: {log_format}\n"
                "raw_packet_scanning_enabled: banana\n"
            ),
            configure_twice=True,
        )

        assert result.returncode == 0, result.stderr
        assert result.stderr.count("CONFIG_SOURCE_SELECTED") == 1
        assert result.stderr.count("CONFIG_VALUE_DEFAULTED") == 1
        assert result.stderr.count("CONFIG_VALIDATED") == 1
        assert result.stderr.count("CONFIG_LOADED") == 1
        if log_format == "gelf":
            records = _gelf_records(result.stderr)
            warning = next(item for item in records if item["short_message"] == "CONFIG_VALUE_DEFAULTED")
            loaded = next(item for item in records if item["short_message"] == "CONFIG_LOADED")
            assert warning["_key"] == "raw_packet_scanning_enabled"
            assert warning["_reason"] == "invalid_bool"
            assert warning["_fallback"] is False
            assert loaded["_warning_count"] == 1
        else:
            warning = next(
                line for line in result.stderr.splitlines()
                if "CONFIG_VALUE_DEFAULTED" in line
            )
            loaded = next(
                line for line in result.stderr.splitlines()
                if "CONFIG_LOADED" in line
            )
            assert "key=raw_packet_scanning_enabled" in warning
            assert "reason=invalid_bool" in warning
            assert "fallback=False" in warning
            assert "warning_count=1" in loaded

    def test_error_threshold_filters_nonfatal_config_records(self, tmp_path):
        result = _run_config_startup(
            tmp_path,
            base_config=(
                "log_level: ERROR\n"
                "log_format: text\n"
                "raw_packet_scanning_enabled: banana\n"
                "unknown_startup_key: ignored\n"
            ),
        )

        assert result.returncode == 0
        assert result.stderr == ""

    def test_unknown_local_key_keeps_source_but_not_value(self, tmp_path):
        secret_value = "release-secret-must-not-appear"
        result = _run_config_startup(
            tmp_path,
            base_config="log_level: INFO\nlog_format: text\n",
            local_config=f"unknown_password: {secret_value}\n",
        )

        assert result.returncode == 0, result.stderr
        assert result.stderr.count("CONFIG_UNKNOWN_KEY_IGNORED") == 1
        warning = next(
            line for line in result.stderr.splitlines()
            if "CONFIG_UNKNOWN_KEY_IGNORED" in line
        )
        loaded = next(
            line for line in result.stderr.splitlines()
            if "CONFIG_LOADED" in line
        )
        assert "key=unknown_password" in warning
        assert str(tmp_path / "local" / "config.local.yaml") in warning
        assert "warning_count=1" in loaded
        assert secret_value not in result.stderr

    @pytest.mark.parametrize("log_format", ["text", "gelf"])
    def test_fatal_local_overlay_uses_safe_structured_fallback(self, tmp_path, log_format):
        secret_value = "release-secret-must-not-appear"
        result = _run_config_startup(
            tmp_path,
            base_config=(
                "app_name: startup-test\n"
                "log_level: DEBUG\n"
                f"log_format: {log_format}\n"
            ),
            local_config=(
                "notifications:\n"
                "  smtp:\n"
                f"    password_secret_id: [{secret_value}\n"
            ),
            fatal=True,
        )

        assert result.returncode != 0
        assert result.stderr.count("CONFIG_LOAD_FAILED") == 1
        assert secret_value not in result.stderr
        if log_format == "gelf":
            records = _gelf_records(result.stderr)
            assert len(records) == 1
            failure = records[0]
            assert failure["short_message"] == "CONFIG_LOAD_FAILED"
            assert failure["level"] == 3
            assert failure["_app"] == "startup-test"
            assert failure["_phase"] == "yaml_parse"
            assert failure["_event_source"] == str(tmp_path / "local" / "config.local.yaml")
            assert failure["_error"] == "ParserError"
            assert "full_message" not in failure
        else:
            failure = next(
                line for line in result.stderr.splitlines()
                if "CONFIG_LOAD_FAILED" in line
            )
            assert "[ERROR]" in failure
            assert "phase=yaml_parse" in failure
            assert f"source={tmp_path / 'local' / 'config.local.yaml'}" in failure
            assert "error=ParserError" in failure


# ── Log event emission ────────────────────────────────────────────────────────

class TestCmdDeniedEvent:
    """CMD_DENIED is emitted at WARNING when is_command_allowed() returns False.
    """

    # RFC 5737 TEST-NET-1 — never routed, guaranteed unique from real traffic
    _IP = "192.0.2.10"

    def _post_run(self, client, command):
        return _post_brokered_run(
            client, command,
            headers={"X-Forwarded-For": self._IP},
        )

    def test_cmd_denied_emits_warning(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        denied = [c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED"]
        assert len(denied) == 1

    def test_cmd_denied_extra_has_ip(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED")
        assert "ip" in call.kwargs["extra"]

    def test_cmd_denied_extra_has_reason(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED")
        assert "reason" in call.kwargs["extra"]
        assert call.kwargs["extra"]["reason"]  # non-empty

    def test_cmd_denied_extra_has_cmd(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED")
        assert call.kwargs["extra"]["cmd"] == "cat /etc/passwd"
        assert call.kwargs["extra"]["deny_kind"] == "policy"
        assert "rule_id" in call.kwargs["extra"]

        from blueprints import run as run_routes
        readiness = run_routes._cmd_denied_log_extra(
            self._IP,
            "log-test-session",
            "nmap -sS example.com",
            "nmap raw mode (-sS) requires raw-packet readiness",
        )
        assert readiness["deny_kind"] == "raw_packet"
        assert readiness["rule_id"] == "raw_packet_readiness"

    def test_shell_operator_block_also_emits_cmd_denied(self):
        # Shell operator blocks are a special case of is_command_allowed returning False
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(["ping"], [])):
                self._post_run(client, "ping google.com | cat /etc/passwd")
        denied = [c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED"]
        assert len(denied) == 1


class TestRateLimitEvent:
    """RATE_LIMIT is emitted at WARNING when a 429 is returned."""

    def test_rate_limit_emits_warning(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "5 per 1 second"
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with _test_app().test_request_context("/runs", method="POST"):
                shell_app_module._rate_limit_handler(e)
        rl_calls = [c for c in mock_warn.call_args_list if c[0][0] == "RATE_LIMIT"]
        assert len(rl_calls) == 1

    def test_rate_limit_extra_has_ip(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "5 per 1 second"
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with _test_app().test_request_context("/runs", method="POST"):
                shell_app_module._log_request()
                shell_app_module._rate_limit_handler(e)
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "RATE_LIMIT")
        assert "ip" in call.kwargs["extra"]
        assert "request_id" in call.kwargs["extra"]

    def test_rate_limit_extra_has_limit_description(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "5 per 1 second"
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with _test_app().test_request_context("/runs", method="POST"):
                shell_app_module._rate_limit_handler(e)
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "RATE_LIMIT")
        assert call.kwargs["extra"]["limit_policy"] == "5 per 1 second"
        assert call.kwargs["extra"]["scope"] == "global"
        data = json.loads(_emit(
            GELFFormatter(),
            logging.WARNING,
            "RATE_LIMIT",
            extra=call.kwargs["extra"],
        ))
        assert data["_limit_policy"] == "5 per 1 second"
        assert "_limit" not in data

    def test_rate_limit_returns_json_429(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "30 per 1 minute"
        with _test_app().test_request_context("/runs", method="POST"):
            response, status = shell_app_module._rate_limit_handler(e)
        assert status == 429
        data = json.loads(response.data)
        assert "error" in data

        with _test_app().test_request_context("/session/secrets", method="POST"):
            response, status = shell_app_module._rate_limit_handler(e)
        assert status == 429
        data = json.loads(response.data)
        assert data["error"] == "rate_limited"
        assert "retry_after" in data


class TestHealthFailEvents:
    """HEALTH_DB_FAIL and HEALTH_REDIS_FAIL are emitted at ERROR."""

    def test_db_fail_emits_error(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "error") as mock_err:
            with mock.patch("services.assets.diagnostics._database_context", side_effect=Exception("db down")):
                client.get("/health")
        db_fail = [c for c in mock_err.call_args_list if c[0][0] == "HEALTH_DB_FAIL"]
        assert len(db_fail) == 1

    def test_redis_fail_emits_error(self):
        client = get_client()
        fake_redis = mock.MagicMock()
        fake_redis.ping.side_effect = Exception("redis down")
        with mock.patch.object(shell_app_module.log, "error") as mock_err:
            with mock.patch("blueprints.assets.redis_client", fake_redis):
                client.get("/health")
        redis_fail = [c for c in mock_err.call_args_list if c[0][0] == "HEALTH_REDIS_FAIL"]
        assert len(redis_fail) == 1


class TestShareCreatedEvent:
    """SHARE_CREATED is emitted at INFO when POST /share succeeds."""

    def test_share_created_emits_info(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.post(
                "/share",
                json={"label": "test label", "content": ["line1"]},
                headers={"X-Session-ID": "test-session"},
            )
        share_calls = [c for c in mock_info.call_args_list if c[0][0] == "SHARE_CREATED"]
        assert len(share_calls) == 1

    def test_share_created_extra_has_label(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.post(
                "/share",
                json={"label": "my-label", "content": []},
                headers={"X-Session-ID": "test-session"},
            )
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_CREATED")
        assert call.kwargs["extra"]["label"] == "my-label"

    def test_share_created_extra_has_share_id(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = client.post(
                "/share",
                json={"label": "lbl", "content": []},
                headers={"X-Session-ID": "test-session"},
            )
        share_id = json.loads(resp.data)["id"]
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_CREATED")
        assert call.kwargs["extra"]["share_id"] == share_id


class TestCmdRewriteEvent:
    """CMD_REWRITE_APPLIED is emitted at DEBUG when a command is silently rewritten."""

    # RFC 5737 TEST-NET-3 — never routed, guaranteed unique from real traffic
    _IP = "203.0.113.42"

    def _post_run(self, client, command):
        return _post_brokered_run(
            client, command,
            headers={"X-Forwarded-For": self._IP},
        )

    def test_nmap_rewrite_emits_debug(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                # Popen raises so we don't actually spawn — rewrite logging fires before Popen
                with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "nmap 8.8.8.8")
        rewrite_calls = [c for c in mock_debug.call_args_list if c[0][0] == "CMD_REWRITE_APPLIED"]
        assert len(rewrite_calls) == 1

    def test_nmap_rewrite_extra_omits_raw_commands(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "nmap 8.8.8.8")
        call = next(c for c in mock_debug.call_args_list if c[0][0] == "CMD_REWRITE_APPLIED")
        extra = call.kwargs["extra"]
        assert "original" not in extra
        assert "rewritten" not in extra
        assert extra["command_root"] == "nmap"

    def test_nmap_rewrite_extra_has_structured_fields(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "nmap 8.8.8.8")
        call = next(c for c in mock_debug.call_args_list if c[0][0] == "CMD_REWRITE_APPLIED")
        extra = call.kwargs["extra"]
        assert extra["ip"] == self._IP
        assert extra["workspace_read_count"] == 0
        assert extra["workspace_write_count"] == 0
        assert extra["workspace_exec_path_count"] == 0
        assert extra["runtime_env_names"] == []

    def test_unrewritten_command_does_not_emit_cmd_rewrite(self):
        # A plain allowed command (ping) is not rewritten — no rewrite log
        client = get_client()
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "ping google.com")
        rewrite_calls = [c for c in mock_debug.call_args_list if c[0][0] == "CMD_REWRITE_APPLIED"]
        assert len(rewrite_calls) == 0


class TestSecretEnvironmentLogging:
    def test_secret_vault_resolution_failure_logs_error(self):
        from blueprints import run as run_routes
        from services.secrets.vault import MasterKeyError

        with mock.patch("blueprints.run.get_secret_value_for_env", side_effect=MasterKeyError("locked")), \
                mock.patch.object(run_routes.log, "error") as error_log:
            with pytest.raises(run_routes._RunPreparationError, match="Secrets vault unavailable"):
                run_routes._resolve_secret_environment("shodan host 8.8.8.8", "tok_secret_failure")

        error_log.assert_called_once()
        assert error_log.call_args.args == ("SECRET_ENV_RESOLVE_FAILED",)
        assert error_log.call_args.kwargs["exc_info"] is True
        extra = error_log.call_args.kwargs["extra"]
        assert extra["session"] == "tok_secr********"
        assert extra["command_root"] == "shodan"
        assert extra["secret_name"] == "SHODAN_API_KEY"
        assert extra["lookup_env_names"] == ["SHODAN_API_KEY"]
        assert extra["error_type"] == "MasterKeyError"


class TestRunLifecycleEvents:
    def test_run_start_emits_info(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n", ""])

        with mock.patch.object(shell_app_module.log, "info") as mock_info, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_brokered_run(client, "echo hello")
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_info.call_args_list if c[0][0] == "RUN_START"]
        assert len(calls) == 1
        assert "scan_transport" not in calls[0].kwargs["extra"]

    def test_run_start_masks_token_session_id(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        fake_proc = _FakeProc(lines=["hello\n", ""])

        with mock.patch.object(shell_app_module.log, "info") as mock_info, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_brokered_run(client, "echo hello", headers={"X-Session-ID": token})
            _ = resp.get_data(as_text=True)

        call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_START")
        extra = call.kwargs["extra"]
        assert extra["session"] != token
        assert extra["session"].startswith(token[:8])
        assert token not in extra.values()

    def test_run_end_emits_info_with_exit_code(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n", ""], returncode=7)

        with mock.patch.object(shell_app_module.log, "info") as mock_info, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = _post_brokered_run(client, "echo hello")
            _ = resp.get_data(as_text=True)

        call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_END")
        assert call.kwargs["extra"]["exit_code"] == 7

    def test_run_kill_emits_info(self):
        client = get_client()

        with mock.patch.object(shell_app_module.log, "info") as mock_info, \
             mock.patch("blueprints.run.pid_for_session", return_value=1234), \
             mock.patch("blueprints.run.os.getpgid", return_value=4321), \
             mock.patch("blueprints.run.os.killpg"):
            resp = client.post("/kill", headers={"X-Session-ID": "session-1"}, json={"run_id": "run-123"})

        assert resp.status_code == 200
        calls = [c for c in mock_info.call_args_list if c[0][0] == "RUN_KILL"]
        assert len(calls) == 1

    def test_kill_miss_emits_debug(self):
        client = get_client()

        with mock.patch.object(shell_app_module.log, "debug") as mock_debug, \
             mock.patch("blueprints.run.pid_for_session", return_value=None):
            resp = client.post("/kill", headers={"X-Session-ID": "session-1"}, json={"run_id": "missing-run"})

        assert resp.status_code == 404
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "KILL_MISS"]
        assert len(calls) == 1


class TestRunFailureEvents:
    def test_cmd_timeout_emits_warning(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["still running\n"], returncode=-15)

        with mock.patch.object(shell_app_module.log, "warning") as mock_warn, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run.os.getpgid", return_value=4321), \
             mock.patch("blueprints.run.os.killpg"), \
             mock.patch.dict("config.CFG", {"command_timeout_seconds": -1}):
            resp = _post_brokered_run(client, "sleep forever")
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_warn.call_args_list if c[0][0] == "CMD_TIMEOUT"]
        assert len(calls) == 1

    def test_run_saved_error_emits_error(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["saved line\n", ""])

        with mock.patch.object(shell_app_module.log, "error") as mock_error, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]), \
             mock.patch("blueprints.run.run_persistence_transaction", side_effect=Exception("db write failed")):
            resp = _post_brokered_run(client, "echo saved")
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_SAVED_ERROR"]
        assert len(calls) == 1

    def test_run_stream_error_emits_error(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n"])

        with mock.patch.object(shell_app_module.log, "error") as mock_error, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=RuntimeError("stream exploded")):
            resp = _post_brokered_run(client, "echo boom")
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_BROKER_STREAM_ERROR"]
        assert len(calls) == 1

        from services.runs import broker_worker

        cleanup_calls = []
        removed = []
        published = []
        with mock.patch.object(broker_worker.log, "error") as mock_error:
            broker_worker.brokered_real_run_worker(
                proc=fake_proc,
                run_id="run-broker-config",
                session_id="broker-config-session",
                team_id="team-config",
                client_ip="203.0.113.44",
                original_command="echo bad-config",
                run_started="2026-05-20T12:00:00+00:00",
                capture=object(),
                signal_classifier=object(),
                postfilter=object(),
                workspace_path_filter=object(),
                variable_notice="",
                rewrite_notice="",
                workspace_notices=[],
                workspace_artifacts=[],
                owner_tab_id="",
                cfg={},
                trufflehog_output_filter_cls=lambda _command: object(),
                publish_broker_captured_line_fn=lambda *args, **kwargs: None,
                output_batcher_cls=object,
                make_nonblocking_stream_reader_fn=lambda _stdout: {},
                stdout_ready_fn=lambda *_args: False,
                read_available_stream_lines_fn=lambda *_args, **_kwargs: ([], True),
                wait_for_proc_exit_code_fn=lambda _proc: 0,
                timeout_notice_fn=lambda _timeout: "",
                terminate_process_group_fn=lambda _proc: None,
                finalize_completed_run_fn=lambda *args, **kwargs: {"elapsed": 0},
                publish_project_finalize_notices_fn=lambda *args: None,
                publish_run_event_fn=lambda *args: published.append(args),
                cleanup_proc_stream_fn=lambda _proc: cleanup_calls.append(True),
                pid_pop_fn=lambda run_id: removed.append(("pid", run_id)),
                active_run_remove_fn=lambda run_id: removed.append(("active", run_id)),
                poll_seconds=0.01,
            )

            config_calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_BROKER_STREAM_CONFIG_ERROR"]
        assert len(config_calls) == 1
        assert config_calls[0].kwargs["extra"]["missing_key"] == "command_timeout_seconds"
        assert published == [("run-broker-config", "error", {"text": "'command_timeout_seconds'"})]
        assert cleanup_calls == [True]
        assert removed == [("pid", "run-broker-config"), ("active", "run-broker-config")]


class TestRequestResponseDebugEvents:
    """REQUEST/RESPONSE stay DEBUG-only while REQUEST_COMPLETED keeps routine probes quiet."""

    def test_request_not_logged_at_info_level(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            request_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
            assert len(request_calls) == 0
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_response_not_logged_at_info_level(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            response_calls = [c for c in mock_debug.call_args_list if c[0][0] == "RESPONSE"]
            assert len(response_calls) == 0
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_completed_logged_at_info_level(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get("/config")
            completed_calls = [c for c in mock_info.call_args_list if c[0][0] == "REQUEST_COMPLETED"]
            assert len(completed_calls) == 1
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_completed_demotes_successful_probe_paths_to_debug(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get("/health")
                get_client().get("/status")
                with mock.patch.dict(
                    shell_app_module.CFG,
                    {"diagnostics_allowed_cidrs": ["127.0.0.1/32"], "metrics_enabled": True},
                ):
                    get_client(use_forwarded_for=False).get("/metrics")
            completed_calls = [c for c in mock_info.call_args_list if c[0][0] == "REQUEST_COMPLETED"]
            assert len(completed_calls) == 0
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_completed_probe_debug_event_keeps_bounded_fields(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            completed_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST_COMPLETED"]
            assert len(completed_calls) == 1
            assert completed_calls[0].kwargs["extra"]["path"] == "/health"
            assert completed_calls[0].kwargs["extra"]["http_status"] == 200
            assert "request_id" in completed_calls[0].kwargs["extra"]
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_completed_extra_has_bounded_request_fields(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get("/config?debug=1")
            call = next(c for c in mock_info.call_args_list if c[0][0] == "REQUEST_COMPLETED")
            assert call.kwargs["extra"]["method"] == "GET"
            assert call.kwargs["extra"]["path"] == "/config"
            assert call.kwargs["extra"]["endpoint"] == "content.get_config"
            assert call.kwargs["extra"]["http_status"] == 200
            assert "duration_ms" in call.kwargs["extra"]
            assert "request_id" in call.kwargs["extra"]
            assert "qs" not in call.kwargs["extra"]
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_completed_skips_static_asset_noise(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get("/favicon.ico")
            completed_calls = [c for c in mock_info.call_args_list if c[0][0] == "REQUEST_COMPLETED"]
            assert len(completed_calls) == 0
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_logged_at_debug_level(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            request_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
            assert len(request_calls) >= 1
            assert "request_id" in request_calls[0].kwargs["extra"]
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_debug_extra_has_path(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "REQUEST")
            assert call.kwargs["extra"]["path"] == "/health"
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_debug_extra_has_method(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "REQUEST")
            assert call.kwargs["extra"]["method"] == "GET"
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_response_logged_at_debug_level(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            response_calls = [c for c in mock_debug.call_args_list if c[0][0] == "RESPONSE"]
            assert len(response_calls) >= 1
            assert "request_id" in response_calls[0].kwargs["extra"]
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_response_debug_extra_has_http_status(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/health")
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "RESPONSE")
            assert call.kwargs["extra"]["http_status"] == 200
        finally:
            shell_app_module.log.setLevel(original_level)

    def test_request_debug_logs_query_keys_without_raw_query_values(self):
        original_level = shell_app_module.log.level
        shell_app_module.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                get_client().get("/history/nonexistent?json&token=secret-token&debug=1")
            request_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
            assert len(request_calls) >= 1
            call = request_calls[0]
            assert call.kwargs["extra"]["query_keys"] == ["debug", "json", "token"]
            assert "qs" not in call.kwargs["extra"]
            assert "secret-token" not in json.dumps(call.kwargs["extra"])
        finally:
            shell_app_module.log.setLevel(original_level)


# ── worker entrypoint logging setup ──────────────────────────────────────────

class TestWorkerEntrypointLoggingSetup:
    """Dedicated worker processes configure structured logging before they run."""

    def test_app_main_bootstraps_before_serving_dev_app(self):
        order = []
        fake_app = mock.Mock()

        def fake_bootstrap(*_args, **_kwargs):
            order.append("bootstrap")

        def fake_create_app(*_args, **_kwargs):
            order.append("create_app")
            return fake_app

        def fake_log_initialized(*_args, **_kwargs):
            order.append("log_initialized")

        fake_app.run.side_effect = lambda **_kwargs: order.append("run")

        with mock.patch.object(shell_app_module, "bootstrap_runtime", side_effect=fake_bootstrap) as bootstrap_runtime, \
             mock.patch.object(shell_app_module, "create_app", side_effect=fake_create_app) as create_app, \
             mock.patch.object(shell_app_module, "_log_app_initialized", side_effect=fake_log_initialized) as log_initialized, \
             mock.patch.object(shell_app_module.time, "monotonic", side_effect=[10.0, 10.25]), \
             mock.patch("builtins.print"):
            shell_app_module.main()

        assert order == ["bootstrap", "create_app", "log_initialized", "run"]
        bootstrap_runtime.assert_called_once_with(shell_app_module.CFG, cleanup_active_runs=True, runtime_name="dev")
        create_app.assert_called_once_with()
        log_initialized.assert_called_once_with(flask_app=fake_app, duration_ms=250)
        fake_app.run.assert_called_once_with(host="0.0.0.0", port=8888, threaded=True)

    def test_ai_worker_main_bootstraps_loads_dependencies_then_runs(self, monkeypatch):
        from services.ai import worker

        order = []
        replacement_cfg = build_test_config({"app_name": "late-ai-worker-config"})
        monkeypatch.setattr(app_config, "CFG", replacement_cfg)

        with mock.patch.object(
            worker,
            "bootstrap_runtime",
            side_effect=lambda *_args, **_kwargs: order.append("bootstrap")
        ) as bootstrap_runtime, \
             mock.patch.object(
                 worker, "_load_runtime_dependencies",
                 side_effect=lambda: order.append("load_dependencies")
            ) as load_runtime_dependencies, \
             mock.patch.object(
                 worker,
                 "run_forever", side_effect=lambda: order.append("run_forever")
            ) as run_forever:
            worker.main()

        assert order == ["bootstrap", "load_dependencies", "run_forever"]
        bootstrap_runtime.assert_called_once_with(
            replacement_cfg,
            init_process=True,
            init_db=True,
            runtime_name="ai_worker",
        )
        load_runtime_dependencies.assert_called_once_with()
        run_forever.assert_called_once_with()

    def test_notification_worker_main_configures_logging(self, monkeypatch):
        from services.notifications import worker

        replacement_cfg = build_test_config({"app_name": "late-notification-worker-config"})
        monkeypatch.setattr(app_config, "CFG", replacement_cfg)

        with mock.patch.object(worker, "bootstrap_runtime") as bootstrap_runtime, \
             mock.patch.object(worker, "run_forever") as run_forever:
            worker.main()

        bootstrap_runtime.assert_called_once_with(
            replacement_cfg,
            init_metrics=False,
            init_process=False,
            init_db=True,
            runtime_name="notification_worker",
        )
        run_forever.assert_called_once_with()

    def test_scheduler_worker_main_configures_logging(self, monkeypatch):
        from services.scheduler import worker

        replacement_cfg = build_test_config({"app_name": "late-scheduler-worker-config"})
        monkeypatch.setattr(app_config, "CFG", replacement_cfg)

        with mock.patch.object(worker, "bootstrap_runtime") as bootstrap_runtime, \
             mock.patch.object(worker, "run_forever") as run_forever:
            worker.main()

        bootstrap_runtime.assert_called_once_with(
            replacement_cfg,
            init_metrics=False,
            init_process=True,
            init_db=True,
            runtime_name="scheduler_worker",
        )
        run_forever.assert_called_once_with()

    def test_app_initialized_extra_has_factory_context(self):
        flask_app = _test_app()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            shell_app_module._log_app_initialized(flask_app=flask_app, duration_ms=12)

        call = next(c for c in mock_info.call_args_list if c[0][0] == "APP_INITIALIZED")
        extra = call.kwargs["extra"]
        assert extra["app_version"] == shell_app_module.APP_VERSION
        assert "version" not in extra
        assert extra["pid"] > 0
        assert extra["app_name"] == flask_app.name
        assert extra["blueprint_count"] == len(flask_app.blueprints)
        assert extra["before_request_handlers"] >= 1
        assert extra["after_request_handlers"] >= 1
        assert extra["limiter_storage"] in {"redis", "memory"}
        assert extra["duration_ms"] == 12


# ── DB_PRUNED log event ───────────────────────────────────────────────────────

class TestDbPrunedEvent:
    """DB_PRUNED is emitted at INFO when retention pruning deletes records."""

    def test_db_pruned_emits_info_when_records_deleted(self):
        old_run_id = "log-prune-test-run-001"
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started) "
            "VALUES (?, 'test', 'ping prune-test', datetime('now', '-10 days'))",
            (old_run_id,)
        )
        conn.commit()
        conn.close()

        try:
            patched_cfg = build_test_config({"permalink_retention_days": 5})
            with mock.patch("core.database.CFG", patched_cfg):
                with mock.patch.object(db_module.log, "info") as mock_info:
                    db_init()

            prune_calls = [c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED"]
            assert len(prune_calls) == 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE id=?", (old_run_id,))
            conn.commit()
            conn.close()

    def test_db_pruned_extra_has_run_count(self):
        old_run_id = "log-prune-test-run-002"
        project_id = "log-prune-project-002"
        link_id = "log-prune-project-link-002"
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started) "
            "VALUES (?, 'test', 'ping prune-test', datetime('now', '-10 days'))",
            (old_run_id,)
        )
        conn.execute(
            "INSERT OR REPLACE INTO projects "
            "(id, session_id, name, slug, created, updated) "
            "VALUES (?, 'test', 'Prune Project', 'prune-project', datetime('now'), datetime('now'))",
            (project_id,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'manual', datetime('now'))",
            (link_id, project_id, old_run_id),
        )
        conn.commit()
        conn.close()

        try:
            patched_cfg = build_test_config({"permalink_retention_days": 5})
            with mock.patch("core.database.CFG", patched_cfg):
                with mock.patch.object(db_module.log, "info") as mock_info, \
                     mock.patch.object(db_module.log, "warning") as mock_warning:
                    db_init()

            call = next(c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED")
            assert call.kwargs["extra"]["runs"] >= 1
            assert call.kwargs["extra"]["retention_days"] == 5
            warning = next(c for c in mock_warning.call_args_list if c[0][0] == "PROJECT_RETENTION_WARNING")
            assert warning.kwargs["extra"]["linked_runs"] >= 1
            assert warning.kwargs["extra"]["projects"] >= 1
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE id=?", (old_run_id,))
            conn.execute("DELETE FROM project_links WHERE id=?", (link_id,))
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.commit()
            conn.close()

    def test_db_pruned_not_emitted_when_retention_disabled(self):
        # permalink_retention_days=0 means disabled — no prune, no log
        patched_cfg = build_test_config({"permalink_retention_days": 0})
        with mock.patch("core.database.CFG", patched_cfg):
            with mock.patch.object(db_module.log, "info") as mock_info:
                db_init()

        prune_calls = [c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED"]
        assert len(prune_calls) == 0

    def test_db_pruned_not_emitted_when_no_old_records(self):
        # Retention is active but no records are old enough to prune
        patched_cfg = build_test_config({"permalink_retention_days": 3650})  # 10 years
        with mock.patch("core.database.CFG", patched_cfg):
            with mock.patch.object(db_module.log, "info") as mock_info:
                db_init()

        prune_calls = [c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED"]
        assert len(prune_calls) == 0


# ── LOGGING_CONFIGURED startup event ─────────────────────────────────────────

class TestLoggingConfiguredEvent:
    """LOGGING_CONFIGURED is emitted at INFO when configure_logging() completes."""

    def teardown_method(self, method):  # noqa: ARG002
        configure_logging(shell_app_module.CFG)

    def test_logging_configured_emits_info(self):
        with mock.patch.object(logging.getLogger("shell"), "info") as mock_info:
            configure_logging({"log_level": "INFO", "log_format": "text"})
        cfg_calls = [c for c in mock_info.call_args_list if c[0][0] == "LOGGING_CONFIGURED"]
        assert len(cfg_calls) == 1

    def test_logging_configured_extra_has_level(self):
        with mock.patch.object(logging.getLogger("shell"), "info") as mock_info:
            configure_logging({"log_level": "DEBUG", "log_format": "text"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "LOGGING_CONFIGURED")
        assert "level" in call.kwargs["extra"]

    def test_logging_configured_extra_has_format(self):
        with mock.patch.object(logging.getLogger("shell"), "info") as mock_info:
            configure_logging({"log_level": "INFO", "log_format": "gelf"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "LOGGING_CONFIGURED")
        assert call.kwargs["extra"]["format"] == "gelf"


# ── HEALTH_OK / HEALTH_DEGRADED ───────────────────────────────────────────────

class TestHealthStatusEvents:
    """HEALTH_OK is emitted at DEBUG on a clean health check; HEALTH_DEGRADED at WARNING."""

    def test_health_ok_emits_debug(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            client.get("/health")
        ok_calls = [c for c in mock_debug.call_args_list if c[0][0] == "HEALTH_OK"]
        assert len(ok_calls) == 1

    def test_health_ok_not_emitted_when_db_fails(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            with mock.patch("services.assets.diagnostics._database_context", side_effect=Exception("db down")):
                client.get("/health")
        ok_calls = [c for c in mock_debug.call_args_list if c[0][0] == "HEALTH_OK"]
        assert len(ok_calls) == 0

    def test_health_degraded_emits_warning_when_db_fails(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.assets.diagnostics._database_context", side_effect=Exception("db down")):
                client.get("/health")
        degraded = [c for c in mock_warn.call_args_list if c[0][0] == "HEALTH_DEGRADED"]
        assert len(degraded) == 1

    def test_health_degraded_extra_has_db_false(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            with mock.patch("services.assets.diagnostics._database_context", side_effect=Exception("db down")):
                client.get("/health")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "HEALTH_DEGRADED")
        assert call.kwargs["extra"]["db"] is False


# ── KILL_FAILED ───────────────────────────────────────────────────────────────

class TestKillFailedEvent:
    """KILL_FAILED is emitted at WARNING when the kill signal cannot be delivered."""

    def test_kill_failed_emits_warning_on_os_error(self):
        client = get_client()
        with mock.patch("blueprints.run.pid_for_session", return_value=99999):
            with mock.patch("blueprints.run.os.killpg", side_effect=ProcessLookupError("no such process")):
                with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
                    client.post("/kill", headers={"X-Session-ID": "session-1"}, json={"run_id": "fake-run-id"})
        kill_failed = [c for c in mock_warn.call_args_list if c[0][0] == "KILL_FAILED"]
        assert len(kill_failed) == 1

    def test_kill_failed_extra_has_run_id(self):
        client = get_client()
        team_scope = mock.Mock(team_id="team-1", is_team=True, member={"id": "tmem-killer", "role": "operator"})
        with mock.patch("blueprints.run.current_request_scope", return_value=team_scope), \
             mock.patch("blueprints.run.active_runs_for_team", return_value=[{"run_id": "test-run-xyz"}]), \
             mock.patch("blueprints.run.pid_for_team", return_value=99999), \
             mock.patch("blueprints.run.os.killpg", side_effect=ProcessLookupError("no such process")), \
             mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            client.post(
                "/kill",
                headers={"X-Session-ID": "member-session", "X-Team-ID": "team-1"},
                json={"run_id": "test-run-xyz"},
            )
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "KILL_FAILED")
        extra = call.kwargs["extra"]
        assert extra["run_id"] == "test-run-xyz"
        assert extra["team_id"] == "team-1"
        assert extra["actor_member_id"] == "tmem-killer"
        assert extra["team_role"] == "operator"
        assert extra["pid"] == 99999
        assert extra["pgid"] == 99999


# ── SHARE_VIEWED ──────────────────────────────────────────────────────────────

class TestShareViewedEvent:
    """SHARE_VIEWED is emitted at INFO when a snapshot permalink is retrieved."""

    def _create_share(self, client):
        resp = client.post(
            "/share",
            json={"label": "test-snap", "content": []},
            headers={"X-Session-ID": "sv-session"},
        )
        return json.loads(resp.data)["id"]

    def test_share_viewed_emits_info(self):
        client = get_client()
        share_id = self._create_share(client)
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.get(f"/share/{share_id}")
        viewed = [c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED"]
        assert len(viewed) == 1

    def test_share_viewed_extra_has_share_id(self):
        client = get_client()
        share_id = self._create_share(client)
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.get(f"/share/{share_id}")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED")
        assert call.kwargs["extra"]["share_id"] == share_id

    def test_share_viewed_extra_has_label(self):
        client = get_client()
        share_id = self._create_share(client)
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.get(f"/share/{share_id}")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED")
        assert call.kwargs["extra"]["label"] == "test-snap"

    def test_share_viewed_not_emitted_for_missing_share(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.get("/share/nonexistent-id")
        viewed = [c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED"]
        assert len(viewed) == 0


# ── RUN_VIEWED ────────────────────────────────────────────────────────────────

class TestRunViewedEvent:
    """RUN_VIEWED is emitted at INFO when a run permalink is retrieved."""

    def _insert_run(self, run_id, command):
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, "rv-session", command, "2026-01-01T00:00:00", "2026-01-01T00:00:01", 0, "[]"),
            )
            conn.commit()

    def _delete_run(self, run_id):
        with db_connect() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()

    def test_run_viewed_emits_info(self):
        run_id = "rv-test-run-1"
        self._insert_run(run_id, "ping test")
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "rv-session"})
            viewed = [c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED"]
            assert len(viewed) == 1
        finally:
            self._delete_run(run_id)

    def test_run_viewed_extra_has_run_id(self):
        run_id = "rv-test-run-2"
        self._insert_run(run_id, "ping test")
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "rv-session"})
            call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED")
            assert call.kwargs["extra"]["run_id"] == run_id
        finally:
            self._delete_run(run_id)

    def test_run_viewed_extra_has_cmd(self):
        run_id = "rv-test-run-3"
        self._insert_run(run_id, "nmap 8.8.8.8")
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "rv-session"})
            call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED")
            assert call.kwargs["extra"]["cmd"] == "nmap 8.8.8.8"
        finally:
            self._delete_run(run_id)

    def test_run_viewed_not_emitted_for_missing_run(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/history/nonexistent-run-id")
        viewed = [c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED"]
        assert len(viewed) == 0


# ── HISTORY_DELETED ───────────────────────────────────────────────────────────

class TestHistoryDeletedEvent:
    """HISTORY_DELETED is emitted at INFO when a run is deleted from history."""

    def _insert_run(self, run_id, session_id="hd-session"):
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, session_id, "ping test", "2026-01-01T00:00:00", "2026-01-01T00:00:01", 0, "[]"),
            )
            conn.commit()

    def test_history_deleted_emits_info(self):
        run_id = "hd-test-run-1"
        self._insert_run(run_id)
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().delete(f"/history/{run_id}", headers={"X-Session-ID": "hd-session"})
        deleted = [c for c in mock_info.call_args_list if c[0][0] == "HISTORY_DELETED"]
        assert len(deleted) == 1

    def test_history_deleted_extra_has_run_id(self):
        run_id = "hd-test-run-2"
        self._insert_run(run_id)
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().delete(f"/history/{run_id}", headers={"X-Session-ID": "hd-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_DELETED")
        assert call.kwargs["extra"]["run_id"] == run_id

    def test_history_deleted_not_emitted_for_wrong_session(self):
        run_id = "hd-test-run-3"
        self._insert_run(run_id, session_id="owner-session")
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().delete(f"/history/{run_id}", headers={"X-Session-ID": "other-session"})
        deleted = [c for c in mock_info.call_args_list if c[0][0] == "HISTORY_DELETED"]
        assert len(deleted) == 0
        # clean up
        with db_connect() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()


# ── HISTORY_CLEARED ───────────────────────────────────────────────────────────

class TestHistoryClearedEvent:
    """HISTORY_CLEARED is emitted at INFO when all history for a session is deleted."""

    def test_history_cleared_emits_info(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().delete("/history", headers={"X-Session-ID": "hc-session"})
        cleared = [c for c in mock_info.call_args_list if c[0][0] == "HISTORY_CLEARED"]
        assert len(cleared) == 1

    def test_history_cleared_extra_has_count(self):
        # Insert two runs for this session then clear
        session = "hc-count-session"
        with db_connect() as conn:
            for i in range(2):
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"hc-run-{i}", session, "ping test", "2026-01-01T00:00:00",
                     "2026-01-01T00:00:01", 0, "[]"),
                )
            conn.commit()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().delete("/history", headers={"X-Session-ID": session})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_CLEARED")
        assert call.kwargs["extra"]["count"] == 2

    def test_history_cleared_count_is_zero_for_empty_session(self):
        # Clearing a session with no history still emits HISTORY_CLEARED with count=0
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().delete("/history", headers={"X-Session-ID": "hc-empty-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_CLEARED")
        assert call.kwargs["extra"]["count"] == 0


# ── HISTORY_VIEWED ───────────────────────────────────────────────────────────

class TestHistoryViewedEvent:
    """HISTORY_VIEWED is emitted at INFO when the history list is requested."""

    def _insert_run(self, run_id, session_id="hv-session"):
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, session_id, "ping test", "2026-01-01T00:00:00", "2026-01-01T00:00:01", 0, "[]"),
            )
            conn.commit()

    def test_history_viewed_emits_info(self):
        run_id = "hv-test-run-1"
        self._insert_run(run_id)
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get("/history", headers={"X-Session-ID": "hv-session"})
            viewed = [c for c in mock_info.call_args_list if c[0][0] == "HISTORY_VIEWED"]
            assert len(viewed) == 1
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()

    def test_history_viewed_extra_has_count(self):
        run_id = "hv-test-run-2"
        self._insert_run(run_id)
        try:
            with mock.patch.object(shell_app_module.log, "info") as mock_info:
                get_client().get("/history?q=ping", headers={"X-Session-ID": "hv-session"})
            call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_VIEWED")
            assert call.kwargs["extra"]["count"] == 1
            assert call.kwargs["extra"]["session"] == "hv-session"
            assert call.kwargs["extra"]["query_present"] is True
            assert call.kwargs["extra"]["query_len"] == len("ping")
            assert "q" not in call.kwargs["extra"]
            assert "ping" not in str(call.kwargs["extra"])
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()


# ── HISTORY_COMMANDS_VIEWED ───────────────────────────────────────────────────

class TestHistoryCommandsViewedEvent:
    """HISTORY_COMMANDS_VIEWED is emitted at DEBUG when command recall hydrates."""

    def test_history_commands_masks_token_session_id(self):
        client = get_client()
        generate_resp = client.get("/session/token/generate")
        token = json.loads(generate_resp.data)["session_token"]
        run_id = "hcv-test-run-" + uuid.uuid4().hex[:8]
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, token, "dig darklab.sh", "2026-01-01T00:00:00", "2026-01-01T00:00:01", 0, "[]"),
            )
            conn.commit()
        try:
            with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
                resp = client.get("/history/commands", headers={"X-Session-ID": token})
            assert resp.status_code == 200
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "HISTORY_COMMANDS_VIEWED")
            extra = call.kwargs["extra"]
            assert extra["session"] != token
            assert extra["session"].startswith(token[:8])
            assert token not in extra.values()
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()


# ── PAGE_LOAD ─────────────────────────────────────────────────────────────────

class TestPageLoadEvent:
    """PAGE_LOAD is emitted at INFO on every GET /."""

    def test_page_load_emits_info(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/")
        loaded = [c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD"]
        assert len(loaded) == 1

    def test_page_load_extra_has_ip(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/", headers={"X-Forwarded-For": "9.9.9.9"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        assert call.kwargs["extra"]["ip"] == "9.9.9.9"

    def test_page_load_extra_has_session_when_present(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/", headers={"X-Session-ID": "page-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        assert call.kwargs["extra"]["session"] == "page-session"

    def test_page_load_masks_token_session_id(self):
        client = get_client()
        token = json.loads(client.get("/session/token/generate").data)["session_token"]
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            client.get("/", headers={"X-Session-ID": token})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        extra = call.kwargs["extra"]
        assert extra["session"] != token
        assert extra["session"].startswith(token[:8])
        assert token not in extra.values()

    def test_page_load_extra_has_theme(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        assert call.kwargs["extra"]["theme"]


class TestThemeSelectedDebugEvent:
    """THEME_SELECTED is emitted at DEBUG when the current theme is resolved."""

    def test_theme_selected_emits_debug(self):
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            get_client().get("/themes")
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "THEME_SELECTED"]
        assert len(calls) == 1

    def test_theme_selected_extra_has_theme_and_source(self):
        with mock.patch.object(shell_app_module.log, "debug") as mock_debug:
            get_client().get("/themes", headers={"X-Session-ID": "theme-session"})
        call = next(c for c in mock_debug.call_args_list if c[0][0] == "THEME_SELECTED")
        assert call.kwargs["extra"]["theme"]
        assert call.kwargs["extra"]["source"] in {"pref_theme_name", "pref_theme", "default_theme", "fallback"}
        assert call.kwargs["extra"]["session"] == "theme-session"


class TestContentViewedEvents:
    """CONTENT_VIEWED is emitted at INFO for content/config read routes."""

    @pytest.mark.parametrize(
        "route",
        [
            "/config",
            "/themes",
            "/allowed-commands",
            "/faq",
            "/autocomplete",
            "/welcome",
            "/welcome/ascii",
            "/welcome/ascii-mobile",
            "/welcome/hints",
            "/welcome/hints-mobile",
        ],
    )
    def test_content_viewed_emits_info(self, route):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get(route, headers={"X-Session-ID": "content-session"})
        calls = [c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED"]
        assert len(calls) == 1
        call = calls[0]
        assert call.kwargs["extra"]["route"] == route
        assert call.kwargs["extra"]["session"] == "content-session"

    def test_config_viewed_extra_has_key_count(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/config", headers={"X-Session-ID": "cfg-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/config"
        assert call.kwargs["extra"]["session"] == "cfg-session"
        assert call.kwargs["extra"]["key_count"] >= 1

    def test_themes_viewed_extra_has_current_and_count(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            get_client().get("/themes", headers={"X-Session-ID": "themes-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/themes"
        assert call.kwargs["extra"]["session"] == "themes-session"
        assert call.kwargs["extra"]["current"]
        assert call.kwargs["extra"]["count"] >= 1

    def test_allowed_commands_viewed_extra_reflects_restricted_list(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            with mock.patch("blueprints.content.load_commands_registry", return_value={
                "commands": [
                    {"root": "ping", "category": "Network", "policy": {"allow": ["ping"], "deny": []}},
                    {"root": "curl", "category": "Web", "policy": {"allow": ["curl"], "deny": []}},
                ],
                "pipe_helpers": [],
            }):
                get_client().get("/allowed-commands", headers={"X-Session-ID": "ac-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/allowed-commands"
        assert call.kwargs["extra"]["session"] == "ac-session"
        assert call.kwargs["extra"]["restricted"] is True
        assert call.kwargs["extra"]["count"] == 2

    def test_allowed_commands_viewed_extra_reflects_unrestricted_mode(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            with mock.patch("blueprints.content.load_commands_registry", return_value={"commands": [], "pipe_helpers": []}):
                get_client().get("/allowed-commands", headers={"X-Session-ID": "ac-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/allowed-commands"
        assert call.kwargs["extra"]["session"] == "ac-session"
        assert call.kwargs["extra"]["restricted"] is False
        assert call.kwargs["extra"]["count"] == 0


# ── RUN_NOT_FOUND / SHARE_NOT_FOUND ──────────────────────────────────────────

class TestNotFoundEvents:
    """RUN_NOT_FOUND and SHARE_NOT_FOUND are emitted at WARN for missing permalinks."""

    def test_run_not_found_emits_warning(self):
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            get_client().get("/history/no-such-run")
        calls = [c for c in mock_warn.call_args_list if c[0][0] == "RUN_NOT_FOUND"]
        assert len(calls) == 1

    def test_run_not_found_extra_has_run_id(self):
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            get_client().get("/history/missing-run-id")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "RUN_NOT_FOUND")
        assert call.kwargs["extra"]["run_id"] == "missing-run-id"

    def test_run_not_found_not_emitted_when_run_exists(self):
        run_id = "pnf-test-run"
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, "pnf-session", "ping test", "2026-01-01T00:00:00",
                 "2026-01-01T00:00:01", 0, "[]"),
            )
            conn.commit()
        try:
            with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
                get_client().get(f"/history/{run_id}", headers={"X-Session-ID": "pnf-session"})
            calls = [c for c in mock_warn.call_args_list if c[0][0] == "RUN_NOT_FOUND"]
            assert len(calls) == 0
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()

    def test_share_not_found_emits_warning(self):
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            get_client().get("/share/no-such-share")
        calls = [c for c in mock_warn.call_args_list if c[0][0] == "SHARE_NOT_FOUND"]
        assert len(calls) == 1

    def test_share_not_found_extra_has_share_id(self):
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            get_client().get("/share/missing-share-id")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "SHARE_NOT_FOUND")
        assert call.kwargs["extra"]["share_id"] == "missing-share-id"

    def test_share_not_found_not_emitted_when_share_exists(self):
        client = get_client()
        resp = client.post(
            "/share",
            json={"label": "exists", "content": []},
            headers={"X-Session-ID": "pnf-share-session"},
        )
        share_id = json.loads(resp.data)["id"]
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            client.get(f"/share/{share_id}")
        calls = [c for c in mock_warn.call_args_list if c[0][0] == "SHARE_NOT_FOUND"]
        assert len(calls) == 0


# ── Session state events ─────────────────────────────────────────────────────

class TestSessionStateEvents:
    """Session-token, preference, and starred-command state changes emit logs."""

    def test_session_token_generate_emits_info_without_token_field(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = get_client().get("/session/token/generate")
        assert resp.status_code == 200
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SESSION_TOKEN_GENERATED")
        assert "session_kind" in call.kwargs["extra"]
        assert "token" not in call.kwargs["extra"]

    def test_session_token_revoke_not_found_emits_warning_without_token_field(self):
        with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
            resp = get_client().post("/session/token/revoke", json={"token": "tok_" + "a" * 32})
        assert resp.status_code == 404
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "SESSION_TOKEN_REVOKE_DENIED")
        assert call.kwargs["extra"]["reason"] == "not_found"
        assert "token" not in call.kwargs["extra"]

    def test_session_token_revoke_masks_token_session_id(self):
        client = get_client()
        generate_resp = client.get("/session/token/generate")
        token = json.loads(generate_resp.data)["session_token"]
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = client.post(
                "/session/token/revoke",
                json={"token": token},
                headers={"X-Session-ID": token},
            )
        assert resp.status_code == 200
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SESSION_TOKEN_REVOKED")
        extra = call.kwargs["extra"]
        assert extra["session"] != token
        assert extra["session"].startswith(token[:8])
        assert token not in extra.values()

    def test_session_migrate_emits_counts_and_session_kinds(self):
        client = get_client()
        from_id = "log-migrate-from-" + uuid.uuid4().hex[:8]
        to_id = str(uuid.uuid4())
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = client.post(
                "/session/migrate",
                json={"from_session_id": from_id, "to_session_id": to_id},
                headers={"X-Session-ID": from_id},
            )
        assert resp.status_code == 200
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SESSION_MIGRATED")
        extra = call.kwargs["extra"]
        assert extra["from_session_kind"] == "anonymous"
        assert extra["to_session_kind"] == "anonymous"
        assert "migrated_preferences" in extra
        assert "from_session_id" not in extra
        assert "to_session_id" not in extra

    def test_session_preferences_save_emits_key_count(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = get_client().post(
                "/session/preferences",
                json={"preferences": {"pref_theme_name": "darklab_obsidian.yaml", "ignored": "x"}},
                headers={"X-Session-ID": "prefs-log-session"},
            )
        assert resp.status_code == 200
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SESSION_PREFERENCES_SAVED")
        assert call.kwargs["extra"]["key_count"] == 1

    def test_session_preferences_invalid_json_emits_warning(self):
        from services.session.storage import decode_preferences

        session_id = "prefs-invalid-" + uuid.uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session_preferences (session_id, preferences, updated) "
                "VALUES (?, ?, datetime('now'))",
                (session_id, "{not-json"),
            )
            conn.commit()
        try:
            with mock.patch.object(shell_app_module.log, "warning") as mock_warn:
                resp = get_client().get("/session/preferences", headers={"X-Session-ID": session_id})
                token_id = "tok_" + uuid.uuid4().hex
                decode_preferences("{not-json", session_id=token_id)
            assert resp.status_code == 200
            calls = [c for c in mock_warn.call_args_list if c[0][0] == "SESSION_PREFERENCES_INVALID"]
            assert len(calls) == 2
            extra = calls[0].kwargs["extra"]
            assert extra["error_type"] == "JSONDecodeError"
            assert "not-json" not in str(extra)
            token_extra = calls[-1].kwargs["extra"]
            assert token_extra["session_kind"] == "token"
            assert token_extra["session"] != token_id
            assert token_id not in str(token_extra)
        finally:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM session_preferences WHERE session_id = ?", (session_id,))
                conn.commit()

    def test_starred_command_add_logs_command_root_not_full_command(self):
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = get_client().post(
                "/session/starred",
                json={"command": "curl -H Authorization:secret https://darklab.sh"},
                headers={"X-Session-ID": "star-log-session"},
            )
        assert resp.status_code == 200
        call = next(c for c in mock_info.call_args_list if c[0][0] == "STARRED_COMMAND_ADDED")
        extra = call.kwargs["extra"]
        assert extra["command_root"] == "curl"
        assert "command" not in extra

    def test_starred_commands_clear_logs_count(self):
        client = get_client()
        session_id = "star-clear-log-" + uuid.uuid4().hex[:8]
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO starred_commands (session_id, command) VALUES (?, ?)",
                (session_id, "dig darklab.sh"),
            )
            conn.commit()
        with mock.patch.object(shell_app_module.log, "info") as mock_info:
            resp = client.delete("/session/starred", headers={"X-Session-ID": session_id})
        assert resp.status_code == 200
        call = next(c for c in mock_info.call_args_list if c[0][0] == "STARRED_COMMANDS_CLEARED")
        assert call.kwargs["extra"]["count"] >= 1


# ── RUN_SPAWN_ERROR ────────────────────────────────────────────────────────────

class TestRunSpawnErrorEvent:
    """RUN_SPAWN_ERROR is emitted at ERROR when subprocess.Popen raises."""

    def _post_run(self, client, cmd):
        # RFC 5737 TEST-NET-3 — never routed, unique per request so Flask-Limiter's
        # in-memory counter cannot leak into this class during full-suite runs.
        ip = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
        return _post_brokered_run(
            client,
            cmd,
            headers={"X-Forwarded-For": ip, "X-Session-ID": "rse-session"},
        )

    def test_spawn_error_returns_500(self):
        client = get_client()
        with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
            with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                    resp = self._post_run(client, "ping 8.8.8.8")
        assert resp.status_code == 500

    def test_spawn_error_emits_error_log(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "error") as mock_error:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                        self._post_run(client, "ping 8.8.8.8")
        calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_ERROR"]
        assert len(calls) == 1

        with mock.patch.object(shell_app_module.log, "error") as mock_error:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run._WorkspacePathOutputFilter", side_effect=RuntimeError("filter setup failed")):
                        self._post_run(client, "ping 8.8.4.4")
        setup_calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_SETUP_FAILED"]
        assert len(setup_calls) == 1
        extra = setup_calls[0].kwargs["extra"]
        assert extra["cfg_source"] == "explicit"
        assert extra["workspace_filter"] == "init"
        assert extra["cmd"] == "ping 8.8.4.4"

    def test_spawn_error_extra_has_ip(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "error") as mock_error:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                        self._post_run(client, "ping 8.8.8.8")
        call = next(c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_ERROR")
        assert "ip" in call.kwargs["extra"]

    def test_spawn_error_extra_has_cmd(self):
        client = get_client()
        with mock.patch.object(shell_app_module.log, "error") as mock_error:
            with mock.patch("services.commands.registry.load_command_policy", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                        self._post_run(client, "ping 8.8.8.8")
        call = next(c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_ERROR")
        assert call.kwargs["extra"]["cmd"] == "ping 8.8.8.8"
