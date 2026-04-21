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
Instead, we use mock.patch.object on shell_app.log to intercept calls directly.

Run with: pytest tests/ (from the repo root)
"""

import io
import json
import logging
import sqlite3
import uuid
import unittest.mock as mock

import pytest

import app as shell_app
import database as db_module
from database import DB_PATH, db_connect, db_init
from logging_setup import GELFFormatter, _TextFormatter, _extra_fields, configure_logging


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


def get_client(*, use_forwarded_for=True):
    shell_app.app.config["TESTING"] = True
    shell_app.app.config["RATELIMIT_ENABLED"] = False
    client = shell_app.app.test_client()
    if use_forwarded_for:
        client.environ_base["HTTP_X_FORWARDED_FOR"] = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    return client


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
            extra={"ip": "1.2.3.4", "run_id": "abc", "exit_code": 0}
        ))
        assert data["_ip"] == "1.2.3.4"
        assert data["_run_id"] == "abc"
        assert data["_exit_code"] == 0

    def test_stdlib_attrs_not_leaked_as_underscore_fields(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        for attr in ("levelname", "lineno", "process", "thread", "module", "pathname"):
            assert f"_{attr}" not in data, f"stdlib attr '_{attr}' should not appear in GELF payload"

    def test_app_name_in_payload(self):
        data = json.loads(_emit(GELFFormatter("myapp"), logging.INFO, "TEST"))
        assert data["_app"] == "myapp"

    def test_app_version_in_payload_comes_from_config(self):
        data = json.loads(_emit(GELFFormatter(), logging.INFO, "TEST"))
        assert data["_app_version"] == shell_app.APP_VERSION

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
        configure_logging(shell_app.CFG)

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
        assert formatter._app_version == shell_app.APP_VERSION

    def test_log_level_info_by_default(self):
        configure_logging({})
        assert self._logger().level == logging.INFO

    def test_log_level_debug_from_cfg(self):
        configure_logging({"log_level": "DEBUG"})
        assert self._logger().level == logging.DEBUG

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
        with mock.patch.object(shell_app.log, "info") as mock_info:
            configure_logging(shell_app.CFG)
        mock_info.assert_called_once()
        _, kwargs = mock_info.call_args
        assert kwargs["extra"]["app_version"] == shell_app.APP_VERSION

    def test_exactly_one_handler_attached(self):
        configure_logging(shell_app.CFG)
        assert len(self._logger().handlers) == 1

    def test_reconfigure_does_not_duplicate_handlers(self):
        configure_logging(shell_app.CFG)
        configure_logging(shell_app.CFG)
        assert len(self._logger().handlers) == 1

    def test_werkzeug_logger_silenced_to_error(self):
        configure_logging({})
        assert logging.getLogger("werkzeug").level == logging.ERROR

    def test_log_level_lowercase_accepted(self):
        configure_logging({"log_level": "debug"})
        assert self._logger().level == logging.DEBUG


# ── Log event emission ────────────────────────────────────────────────────────

class TestCmdDeniedEvent:
    """CMD_DENIED is emitted at WARNING when is_command_allowed() returns False.

    Uses a dedicated X-Forwarded-For IP so these tests get their own rate-limit
    bucket and don't pollute the shared 127.0.0.1 counter used by test_routes.py.
    """

    # RFC 5737 TEST-NET-1 — never routed, guaranteed unique from real traffic
    _IP = "192.0.2.10"

    def _post_run(self, client, command):
        return client.post(
            "/run", json={"command": command},
            headers={"X-Forwarded-For": self._IP},
        )

    def test_cmd_denied_emits_warning(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        denied = [c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED"]
        assert len(denied) == 1

    def test_cmd_denied_extra_has_ip(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED")
        assert "ip" in call.kwargs["extra"]

    def test_cmd_denied_extra_has_reason(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED")
        assert "reason" in call.kwargs["extra"]
        assert call.kwargs["extra"]["reason"]  # non-empty

    def test_cmd_denied_extra_has_cmd(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
                self._post_run(client, "cat /etc/passwd")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED")
        assert call.kwargs["extra"]["cmd"] == "cat /etc/passwd"

    def test_shell_operator_block_also_emits_cmd_denied(self):
        # Shell operator blocks are a special case of is_command_allowed returning False
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("commands.load_allowed_commands", return_value=(["ping"], [])):
                self._post_run(client, "ping google.com | cat /etc/passwd")
        denied = [c for c in mock_warn.call_args_list if c[0][0] == "CMD_DENIED"]
        assert len(denied) == 1


class TestRateLimitEvent:
    """RATE_LIMIT is emitted at WARNING when a 429 is returned."""

    def test_rate_limit_emits_warning(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "5 per 1 second"
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with shell_app.app.test_request_context("/run", method="POST"):
                shell_app._rate_limit_handler(e)
        rl_calls = [c for c in mock_warn.call_args_list if c[0][0] == "RATE_LIMIT"]
        assert len(rl_calls) == 1

    def test_rate_limit_extra_has_ip(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "5 per 1 second"
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with shell_app.app.test_request_context("/run", method="POST"):
                shell_app._rate_limit_handler(e)
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "RATE_LIMIT")
        assert "ip" in call.kwargs["extra"]

    def test_rate_limit_extra_has_limit_description(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "5 per 1 second"
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with shell_app.app.test_request_context("/run", method="POST"):
                shell_app._rate_limit_handler(e)
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "RATE_LIMIT")
        assert call.kwargs["extra"]["limit"] == "5 per 1 second"

    def test_rate_limit_returns_json_429(self):
        from werkzeug.exceptions import TooManyRequests
        e = TooManyRequests()
        e.description = "30 per 1 minute"
        with shell_app.app.test_request_context("/run", method="POST"):
            response, status = shell_app._rate_limit_handler(e)
        assert status == 429
        data = json.loads(response.data)
        assert "error" in data


class TestHealthFailEvents:
    """HEALTH_DB_FAIL and HEALTH_REDIS_FAIL are emitted at ERROR."""

    def test_db_fail_emits_error(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "error") as mock_err:
            with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db down")):
                client.get("/health")
        db_fail = [c for c in mock_err.call_args_list if c[0][0] == "HEALTH_DB_FAIL"]
        assert len(db_fail) == 1

    def test_redis_fail_emits_error(self):
        client = get_client()
        fake_redis = mock.MagicMock()
        fake_redis.ping.side_effect = Exception("redis down")
        with mock.patch.object(shell_app.log, "error") as mock_err:
            with mock.patch("blueprints.assets.redis_client", fake_redis):
                client.get("/health")
        redis_fail = [c for c in mock_err.call_args_list if c[0][0] == "HEALTH_REDIS_FAIL"]
        assert len(redis_fail) == 1


class TestShareCreatedEvent:
    """SHARE_CREATED is emitted at INFO when POST /share succeeds."""

    def test_share_created_emits_info(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            client.post(
                "/share",
                json={"label": "test label", "content": ["line1"]},
                headers={"X-Session-ID": "test-session"},
            )
        share_calls = [c for c in mock_info.call_args_list if c[0][0] == "SHARE_CREATED"]
        assert len(share_calls) == 1

    def test_share_created_extra_has_label(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            client.post(
                "/share",
                json={"label": "my-label", "content": []},
                headers={"X-Session-ID": "test-session"},
            )
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_CREATED")
        assert call.kwargs["extra"]["label"] == "my-label"

    def test_share_created_extra_has_share_id(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            resp = client.post(
                "/share",
                json={"label": "lbl", "content": []},
                headers={"X-Session-ID": "test-session"},
            )
        share_id = json.loads(resp.data)["id"]
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_CREATED")
        assert call.kwargs["extra"]["share_id"] == share_id


class TestCmdRewriteEvent:
    """CMD_REWRITE is emitted at INFO when a command is silently rewritten.

    Uses a dedicated X-Forwarded-For IP so these tests get a fresh rate-limit
    bucket. Flask-Limiter 4.x increments in-memory counters even when
    RATELIMIT_ENABLED=False; using a unique IP prevents counter overflow from
    prior tests in the same second.
    """

    # RFC 5737 TEST-NET-3 — never routed, guaranteed unique from real traffic
    _IP = "203.0.113.42"

    def _post_run(self, client, command):
        return client.post(
            "/run", json={"command": command},
            headers={"X-Forwarded-For": self._IP},
        )

    def test_nmap_rewrite_emits_info(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                # Popen raises so we don't actually spawn — CMD_REWRITE fires before Popen
                with mock.patch("subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "nmap 8.8.8.8")
        rewrite_calls = [c for c in mock_info.call_args_list if c[0][0] == "CMD_REWRITE"]
        assert len(rewrite_calls) == 1

    def test_nmap_rewrite_extra_has_original(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                with mock.patch("subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "nmap 8.8.8.8")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CMD_REWRITE")
        assert call.kwargs["extra"]["original"] == "nmap 8.8.8.8"

    def test_nmap_rewrite_extra_has_privileged_flag(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                with mock.patch("subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "nmap 8.8.8.8")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CMD_REWRITE")
        assert "--privileged" in call.kwargs["extra"]["rewritten"]

    def test_unrewritten_command_does_not_emit_cmd_rewrite(self):
        # A plain allowed command (ping) is not rewritten — no CMD_REWRITE log
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                with mock.patch("subprocess.Popen", side_effect=OSError("no spawn")):
                    self._post_run(client, "ping google.com")
        rewrite_calls = [c for c in mock_info.call_args_list if c[0][0] == "CMD_REWRITE"]
        assert len(rewrite_calls) == 0


class TestRunLifecycleEvents:
    def test_run_start_emits_info(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n", ""])

        with mock.patch.object(shell_app.log, "info") as mock_info, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = client.post("/run", json={"command": "echo hello"})
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_info.call_args_list if c[0][0] == "RUN_START"]
        assert len(calls) == 1

    def test_run_end_emits_info_with_exit_code(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n", ""], returncode=7)

        with mock.patch.object(shell_app.log, "info") as mock_info, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]):
            resp = client.post("/run", json={"command": "echo hello"})
            _ = resp.get_data(as_text=True)

        call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_END")
        assert call.kwargs["extra"]["exit_code"] == 7

    def test_run_kill_emits_info(self):
        client = get_client()

        with mock.patch.object(shell_app.log, "info") as mock_info, \
             mock.patch("blueprints.run.pid_pop", return_value=1234), \
             mock.patch("blueprints.run.os.getpgid", return_value=4321), \
             mock.patch("blueprints.run.os.killpg"):
            resp = client.post("/kill", json={"run_id": "run-123"})

        assert resp.status_code == 200
        calls = [c for c in mock_info.call_args_list if c[0][0] == "RUN_KILL"]
        assert len(calls) == 1

    def test_kill_miss_emits_debug(self):
        client = get_client()

        with mock.patch.object(shell_app.log, "debug") as mock_debug, \
             mock.patch("blueprints.run.pid_pop", return_value=None):
            resp = client.post("/kill", json={"run_id": "missing-run"})

        assert resp.status_code == 404
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "KILL_MISS"]
        assert len(calls) == 1


class TestRunFailureEvents:
    def test_cmd_timeout_emits_warning(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["still running\n"], returncode=-15)

        with mock.patch.object(shell_app.log, "warning") as mock_warn, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run.os.getpgid", return_value=4321), \
             mock.patch("blueprints.run.os.killpg"), \
             mock.patch.dict("config.CFG", {"command_timeout_seconds": -1}):
            resp = client.post("/run", json={"command": "sleep forever"})
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_warn.call_args_list if c[0][0] == "CMD_TIMEOUT"]
        assert len(calls) == 1

    def test_run_saved_error_emits_error(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["saved line\n", ""])

        with mock.patch.object(shell_app.log, "error") as mock_error, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=[True, True]), \
             mock.patch("blueprints.run.db_connect", side_effect=Exception("db write failed")):
            resp = client.post("/run", json={"command": "echo saved"})
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_SAVED_ERROR"]
        assert len(calls) == 1

    def test_run_stream_error_emits_error(self):
        client = get_client()
        fake_proc = _FakeProc(lines=["hello\n"])

        with mock.patch.object(shell_app.log, "error") as mock_error, \
             mock.patch("blueprints.run.is_command_allowed", return_value=(True, "")), \
             mock.patch("blueprints.run.subprocess.Popen", return_value=fake_proc), \
             mock.patch("blueprints.run.pid_register"), \
             mock.patch("blueprints.run.pid_pop"), \
             mock.patch("blueprints.run._stdout_ready", side_effect=RuntimeError("stream exploded")):
            resp = client.post("/run", json={"command": "echo boom"})
            _ = resp.get_data(as_text=True)

        calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_STREAM_ERROR"]
        assert len(calls) == 1


class TestRequestResponseDebugEvents:
    """REQUEST and RESPONSE are only emitted when the logger is at DEBUG level."""

    def test_request_not_logged_at_info_level(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            request_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
            assert len(request_calls) == 0
        finally:
            shell_app.log.setLevel(original_level)

    def test_response_not_logged_at_info_level(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.INFO)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            response_calls = [c for c in mock_debug.call_args_list if c[0][0] == "RESPONSE"]
            assert len(response_calls) == 0
        finally:
            shell_app.log.setLevel(original_level)

    def test_request_logged_at_debug_level(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            request_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
            assert len(request_calls) >= 1
        finally:
            shell_app.log.setLevel(original_level)

    def test_request_debug_extra_has_path(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "REQUEST")
            assert call.kwargs["extra"]["path"] == "/health"
        finally:
            shell_app.log.setLevel(original_level)

    def test_request_debug_extra_has_method(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "REQUEST")
            assert call.kwargs["extra"]["method"] == "GET"
        finally:
            shell_app.log.setLevel(original_level)

    def test_response_logged_at_debug_level(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            response_calls = [c for c in mock_debug.call_args_list if c[0][0] == "RESPONSE"]
            assert len(response_calls) >= 1
        finally:
            shell_app.log.setLevel(original_level)

    def test_response_debug_extra_has_status(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/health")
            call = next(c for c in mock_debug.call_args_list if c[0][0] == "RESPONSE")
            assert call.kwargs["extra"]["status"] == 200
        finally:
            shell_app.log.setLevel(original_level)

    def test_query_string_included_in_request_debug_when_present(self):
        original_level = shell_app.log.level
        shell_app.log.setLevel(logging.DEBUG)
        try:
            with mock.patch.object(shell_app.log, "debug") as mock_debug:
                get_client().get("/history/nonexistent?json")
            request_calls = [c for c in mock_debug.call_args_list if c[0][0] == "REQUEST"]
            assert len(request_calls) >= 1
            call = request_calls[0]
            assert "qs" in call.kwargs["extra"]
            assert "json" in call.kwargs["extra"]["qs"]
        finally:
            shell_app.log.setLevel(original_level)


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
            patched_cfg = {**shell_app.CFG, "permalink_retention_days": 5}
            with mock.patch("database.CFG", patched_cfg):
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
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO runs (id, session_id, command, started) "
            "VALUES (?, 'test', 'ping prune-test', datetime('now', '-10 days'))",
            (old_run_id,)
        )
        conn.commit()
        conn.close()

        try:
            patched_cfg = {**shell_app.CFG, "permalink_retention_days": 5}
            with mock.patch("database.CFG", patched_cfg):
                with mock.patch.object(db_module.log, "info") as mock_info:
                    db_init()

            call = next(c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED")
            assert call.kwargs["extra"]["runs"] >= 1
            assert call.kwargs["extra"]["retention_days"] == 5
        finally:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM runs WHERE id=?", (old_run_id,))
            conn.commit()
            conn.close()

    def test_db_pruned_not_emitted_when_retention_disabled(self):
        # permalink_retention_days=0 means disabled — no prune, no log
        patched_cfg = {**shell_app.CFG, "permalink_retention_days": 0}
        with mock.patch("database.CFG", patched_cfg):
            with mock.patch.object(db_module.log, "info") as mock_info:
                db_init()

        prune_calls = [c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED"]
        assert len(prune_calls) == 0

    def test_db_pruned_not_emitted_when_no_old_records(self):
        # Retention is active but no records are old enough to prune
        patched_cfg = {**shell_app.CFG, "permalink_retention_days": 3650}  # 10 years
        with mock.patch("database.CFG", patched_cfg):
            with mock.patch.object(db_module.log, "info") as mock_info:
                db_init()

        prune_calls = [c for c in mock_info.call_args_list if c[0][0] == "DB_PRUNED"]
        assert len(prune_calls) == 0


# ── LOGGING_CONFIGURED startup event ─────────────────────────────────────────

class TestLoggingConfiguredEvent:
    """LOGGING_CONFIGURED is emitted at INFO when configure_logging() completes."""

    def teardown_method(self, method):  # noqa: ARG002
        configure_logging(shell_app.CFG)

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
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            client.get("/health")
        ok_calls = [c for c in mock_debug.call_args_list if c[0][0] == "HEALTH_OK"]
        assert len(ok_calls) == 1

    def test_health_ok_not_emitted_when_db_fails(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db down")):
                client.get("/health")
        ok_calls = [c for c in mock_debug.call_args_list if c[0][0] == "HEALTH_OK"]
        assert len(ok_calls) == 0

    def test_health_degraded_emits_warning_when_db_fails(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db down")):
                client.get("/health")
        degraded = [c for c in mock_warn.call_args_list if c[0][0] == "HEALTH_DEGRADED"]
        assert len(degraded) == 1

    def test_health_degraded_extra_has_db_false(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            with mock.patch("blueprints.assets.db_connect", side_effect=Exception("db down")):
                client.get("/health")
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "HEALTH_DEGRADED")
        assert call.kwargs["extra"]["db"] is False


# ── KILL_FAILED ───────────────────────────────────────────────────────────────

class TestKillFailedEvent:
    """KILL_FAILED is emitted at WARNING when the kill signal cannot be delivered."""

    def test_kill_failed_emits_warning_on_os_error(self):
        client = get_client()
        with mock.patch("blueprints.run.pid_pop", return_value=99999):
            with mock.patch("os.getpgid", side_effect=ProcessLookupError("no such process")):
                with mock.patch.object(shell_app.log, "warning") as mock_warn:
                    client.post("/kill", json={"run_id": "fake-run-id"})
        kill_failed = [c for c in mock_warn.call_args_list if c[0][0] == "KILL_FAILED"]
        assert len(kill_failed) == 1

    def test_kill_failed_extra_has_run_id(self):
        client = get_client()
        with mock.patch("blueprints.run.pid_pop", return_value=99999):
            with mock.patch("os.getpgid", side_effect=ProcessLookupError("no such process")):
                with mock.patch.object(shell_app.log, "warning") as mock_warn:
                    client.post("/kill", json={"run_id": "test-run-xyz"})
        call = next(c for c in mock_warn.call_args_list if c[0][0] == "KILL_FAILED")
        assert call.kwargs["extra"]["run_id"] == "test-run-xyz"


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
        with mock.patch.object(shell_app.log, "info") as mock_info:
            client.get(f"/share/{share_id}")
        viewed = [c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED"]
        assert len(viewed) == 1

    def test_share_viewed_extra_has_share_id(self):
        client = get_client()
        share_id = self._create_share(client)
        with mock.patch.object(shell_app.log, "info") as mock_info:
            client.get(f"/share/{share_id}")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED")
        assert call.kwargs["extra"]["share_id"] == share_id

    def test_share_viewed_extra_has_label(self):
        client = get_client()
        share_id = self._create_share(client)
        with mock.patch.object(shell_app.log, "info") as mock_info:
            client.get(f"/share/{share_id}")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "SHARE_VIEWED")
        assert call.kwargs["extra"]["label"] == "test-snap"

    def test_share_viewed_not_emitted_for_missing_share(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "info") as mock_info:
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
            with mock.patch.object(shell_app.log, "info") as mock_info:
                get_client().get(f"/history/{run_id}")
            viewed = [c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED"]
            assert len(viewed) == 1
        finally:
            self._delete_run(run_id)

    def test_run_viewed_extra_has_run_id(self):
        run_id = "rv-test-run-2"
        self._insert_run(run_id, "ping test")
        try:
            with mock.patch.object(shell_app.log, "info") as mock_info:
                get_client().get(f"/history/{run_id}")
            call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED")
            assert call.kwargs["extra"]["run_id"] == run_id
        finally:
            self._delete_run(run_id)

    def test_run_viewed_extra_has_cmd(self):
        run_id = "rv-test-run-3"
        self._insert_run(run_id, "nmap 8.8.8.8")
        try:
            with mock.patch.object(shell_app.log, "info") as mock_info:
                get_client().get(f"/history/{run_id}")
            call = next(c for c in mock_info.call_args_list if c[0][0] == "RUN_VIEWED")
            assert call.kwargs["extra"]["cmd"] == "nmap 8.8.8.8"
        finally:
            self._delete_run(run_id)

    def test_run_viewed_not_emitted_for_missing_run(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
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
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().delete(f"/history/{run_id}", headers={"X-Session-ID": "hd-session"})
        deleted = [c for c in mock_info.call_args_list if c[0][0] == "HISTORY_DELETED"]
        assert len(deleted) == 1

    def test_history_deleted_extra_has_run_id(self):
        run_id = "hd-test-run-2"
        self._insert_run(run_id)
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().delete(f"/history/{run_id}", headers={"X-Session-ID": "hd-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_DELETED")
        assert call.kwargs["extra"]["run_id"] == run_id

    def test_history_deleted_not_emitted_for_wrong_session(self):
        run_id = "hd-test-run-3"
        self._insert_run(run_id, session_id="owner-session")
        with mock.patch.object(shell_app.log, "info") as mock_info:
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
        with mock.patch.object(shell_app.log, "info") as mock_info:
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
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().delete("/history", headers={"X-Session-ID": session})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_CLEARED")
        assert call.kwargs["extra"]["count"] == 2

    def test_history_cleared_count_is_zero_for_empty_session(self):
        # Clearing a session with no history still emits HISTORY_CLEARED with count=0
        with mock.patch.object(shell_app.log, "info") as mock_info:
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
            with mock.patch.object(shell_app.log, "info") as mock_info:
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
            with mock.patch.object(shell_app.log, "info") as mock_info:
                get_client().get("/history", headers={"X-Session-ID": "hv-session"})
            call = next(c for c in mock_info.call_args_list if c[0][0] == "HISTORY_VIEWED")
            assert call.kwargs["extra"]["count"] == 1
            assert call.kwargs["extra"]["session"] == "hv-session"
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()


# ── PAGE_LOAD ─────────────────────────────────────────────────────────────────

class TestPageLoadEvent:
    """PAGE_LOAD is emitted at INFO on every GET /."""

    def test_page_load_emits_info(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get("/")
        loaded = [c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD"]
        assert len(loaded) == 1

    def test_page_load_extra_has_ip(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get("/", headers={"X-Forwarded-For": "9.9.9.9"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        assert call.kwargs["extra"]["ip"] == "9.9.9.9"

    def test_page_load_extra_has_session_when_present(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get("/", headers={"X-Session-ID": "page-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        assert call.kwargs["extra"]["session"] == "page-session"

    def test_page_load_extra_has_theme(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get("/")
        call = next(c for c in mock_info.call_args_list if c[0][0] == "PAGE_LOAD")
        assert call.kwargs["extra"]["theme"]


class TestThemeSelectedDebugEvent:
    """THEME_SELECTED is emitted at DEBUG when the current theme is resolved."""

    def test_theme_selected_emits_debug(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
            get_client().get("/themes")
        calls = [c for c in mock_debug.call_args_list if c[0][0] == "THEME_SELECTED"]
        assert len(calls) == 1

    def test_theme_selected_extra_has_theme_and_source(self):
        with mock.patch.object(shell_app.log, "debug") as mock_debug:
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
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get(route, headers={"X-Session-ID": "content-session"})
        calls = [c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED"]
        assert len(calls) == 1
        call = calls[0]
        assert call.kwargs["extra"]["route"] == route
        assert call.kwargs["extra"]["session"] == "content-session"

    def test_config_viewed_extra_has_key_count(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get("/config", headers={"X-Session-ID": "cfg-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/config"
        assert call.kwargs["extra"]["session"] == "cfg-session"
        assert call.kwargs["extra"]["key_count"] >= 1

    def test_themes_viewed_extra_has_current_and_count(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            get_client().get("/themes", headers={"X-Session-ID": "themes-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/themes"
        assert call.kwargs["extra"]["session"] == "themes-session"
        assert call.kwargs["extra"]["current"]
        assert call.kwargs["extra"]["count"] >= 1

    def test_allowed_commands_viewed_extra_reflects_restricted_list(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            with mock.patch("blueprints.content.load_allowed_commands", return_value=(["ping", "curl"], [])):
                with mock.patch("blueprints.content.load_allowed_commands_grouped", return_value=[]):
                    get_client().get("/allowed-commands", headers={"X-Session-ID": "ac-session"})
        call = next(c for c in mock_info.call_args_list if c[0][0] == "CONTENT_VIEWED")
        assert call.kwargs["extra"]["route"] == "/allowed-commands"
        assert call.kwargs["extra"]["session"] == "ac-session"
        assert call.kwargs["extra"]["restricted"] is True
        assert call.kwargs["extra"]["count"] == 2

    def test_allowed_commands_viewed_extra_reflects_unrestricted_mode(self):
        with mock.patch.object(shell_app.log, "info") as mock_info:
            with mock.patch("blueprints.content.load_allowed_commands", return_value=(None, [])):
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
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            get_client().get("/history/no-such-run")
        calls = [c for c in mock_warn.call_args_list if c[0][0] == "RUN_NOT_FOUND"]
        assert len(calls) == 1

    def test_run_not_found_extra_has_run_id(self):
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
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
            with mock.patch.object(shell_app.log, "warning") as mock_warn:
                get_client().get(f"/history/{run_id}")
            calls = [c for c in mock_warn.call_args_list if c[0][0] == "RUN_NOT_FOUND"]
            assert len(calls) == 0
        finally:
            with db_connect() as conn:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
                conn.commit()

    def test_share_not_found_emits_warning(self):
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            get_client().get("/share/no-such-share")
        calls = [c for c in mock_warn.call_args_list if c[0][0] == "SHARE_NOT_FOUND"]
        assert len(calls) == 1

    def test_share_not_found_extra_has_share_id(self):
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
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
        with mock.patch.object(shell_app.log, "warning") as mock_warn:
            client.get(f"/share/{share_id}")
        calls = [c for c in mock_warn.call_args_list if c[0][0] == "SHARE_NOT_FOUND"]
        assert len(calls) == 0


# ── RUN_SPAWN_ERROR ────────────────────────────────────────────────────────────

class TestRunSpawnErrorEvent:
    """RUN_SPAWN_ERROR is emitted at ERROR when subprocess.Popen raises."""

    # RFC 5737 TEST-NET-3 — never routed, gives this class its own rate-limit bucket
    _IP = "203.0.113.99"

    def _post_run(self, client, cmd):
        return client.post(
            "/run",
            json={"command": cmd},
            headers={"X-Forwarded-For": self._IP, "X-Session-ID": "rse-session"},
        )

    def test_spawn_error_returns_500(self):
        client = get_client()
        with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
            with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                    resp = self._post_run(client, "ping 8.8.8.8")
        assert resp.status_code == 500

    def test_spawn_error_emits_error_log(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "error") as mock_error:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                        self._post_run(client, "ping 8.8.8.8")
        calls = [c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_ERROR"]
        assert len(calls) == 1

    def test_spawn_error_extra_has_ip(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "error") as mock_error:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                        self._post_run(client, "ping 8.8.8.8")
        call = next(c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_ERROR")
        assert "ip" in call.kwargs["extra"]

    def test_spawn_error_extra_has_cmd(self):
        client = get_client()
        with mock.patch.object(shell_app.log, "error") as mock_error:
            with mock.patch("commands.load_allowed_commands", return_value=(None, [])):
                with mock.patch("blueprints.run.runtime_missing_command_name", return_value=None):
                    with mock.patch("blueprints.run.subprocess.Popen", side_effect=OSError("spawn failed")):
                        self._post_run(client, "ping 8.8.8.8")
        call = next(c for c in mock_error.call_args_list if c[0][0] == "RUN_SPAWN_ERROR")
        assert call.kwargs["extra"]["cmd"] == "ping 8.8.8.8"
