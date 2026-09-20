# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Console severity routing across app and Gunicorn logging boundaries."""

import json
import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from gunicorn.config import Config

from core.logging_setup import configure_logging
from gunicorn_conf import ConsoleSeverityLogger


@pytest.fixture(autouse=True)
def restore_loggers():
    loggers = [logging.getLogger(name) for name in ("shell", "gunicorn.error", "gunicorn.access", "werkzeug")]
    states = [(logger.handlers[:], logger.level, logger.propagate) for logger in loggers]
    yield
    for logger, (handlers, level, propagate) in zip(loggers, states, strict=True):
        for handler in logger.handlers:
            if handler not in handlers:
                handler.close()
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate


@pytest.mark.parametrize("log_format", ["text", "gelf"])
@pytest.mark.parametrize("threshold", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_application_routes_each_record_once_after_reconfiguration(capsys, log_format, threshold):
    for _ in range(3):
        configure_logging({"log_format": log_format, "log_level": threshold})
    capsys.readouterr()
    logger = logging.getLogger("shell")
    for severity in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        logger.log(getattr(logging, severity), f"STREAM_{severity}", extra={"http_status": 503, "phase": "probe"})
    captured = capsys.readouterr()
    for severity in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        expected, other = (captured.out, captured.err) if getattr(logging, severity) < logging.WARNING else (
            captured.err, captured.out
        )
        assert f"STREAM_{severity}" not in other
        assert expected.count(f"STREAM_{severity}") == int(getattr(logging, severity) >= getattr(logging, threshold))
    if log_format == "gelf":
        for line in (captured.out + captured.err).splitlines():
            record = json.loads(line)
            assert record["_http_status"] == 503
            assert record["_phase"] == "probe"
            assert record["_logger"] == "shell"


@pytest.mark.parametrize("log_format", ["text", "gelf"])
def test_application_exception_stays_with_its_record(capsys, log_format):
    configure_logging({"log_format": log_format})
    capsys.readouterr()
    try:
        raise RuntimeError("controlled failure")
    except RuntimeError:
        logging.getLogger("shell").exception("STREAM_EXCEPTION", extra={"phase": "probe"})
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("STREAM_EXCEPTION") == 1
    assert captured.err.count("RuntimeError: controlled failure") == 1
    if log_format == "gelf":
        record = json.loads(captured.err)
        assert record["level"] == 3
        assert "Traceback" in record["full_message"]
        assert record["_phase"] == "probe"


@pytest.mark.parametrize("threshold", ["debug", "warning"])
def test_gunicorn_routes_native_records_and_exceptions_once(capsys, threshold):
    cfg = Config()
    cfg.set("loglevel", threshold)
    logger = ConsoleSeverityLogger(cfg)
    logger.setup(cfg)
    logger.setup(cfg)
    for severity in ("debug", "info", "warning", "error", "critical"):
        getattr(logger, severity)("GUNICORN_STREAM_%s", severity.upper())
    try:
        raise RuntimeError("controlled gunicorn failure")
    except RuntimeError:
        logger.exception("GUNICORN_STREAM_EXCEPTION")
    captured = capsys.readouterr()
    for severity in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        expected, other = (captured.out, captured.err) if getattr(logging, severity) < logging.WARNING else (
            captured.err, captured.out
        )
        assert f"GUNICORN_STREAM_{severity}" not in other
        assert expected.count(f"[{severity}] GUNICORN_STREAM_{severity}") == int(
            getattr(logging, severity) >= getattr(logging, threshold.upper())
        )
    assert captured.err.count("[ERROR] GUNICORN_STREAM_EXCEPTION") == 1
    assert captured.err.count("RuntimeError: controlled gunicorn failure") == 1
    assert "Traceback" not in captured.out


def test_gunicorn_preserves_file_logging_and_console_reconfiguration(tmp_path, capsys):
    cfg = Config()
    cfg.set("accesslog", "-")
    logger = ConsoleSeverityLogger(cfg)
    destination = tmp_path / "gunicorn.log"
    cfg.set("errorlog", str(destination))
    logger.setup(cfg)
    logger.info("FILE_INFO")
    logger.warning("FILE_WARNING")
    assert capsys.readouterr() == ("", "")
    assert destination.read_text().count("FILE_INFO") == 1
    assert destination.read_text().count("FILE_WARNING") == 1
    cfg.set("errorlog", "-")
    logger.setup(cfg)
    logger.info("CONSOLE_INFO")
    logger.warning("CONSOLE_WARNING")
    logger.access_log.info("ACCESS_LINE")
    captured = capsys.readouterr()
    assert captured.out.count("CONSOLE_INFO") == 1
    assert captured.out.count("ACCESS_LINE") == 1
    assert "CONSOLE_WARNING" not in captured.out
    assert captured.err.count("CONSOLE_WARNING") == 1
    assert "CONSOLE_INFO" not in captured.err
    assert "CONSOLE" not in destination.read_text()


def test_gunicorn_logger_import_does_not_bootstrap_application():
    result = subprocess.run(
        [sys.executable, "-c", "import gunicorn_conf, sys; assert 'config' not in sys.modules; "
         "assert 'runtime_bootstrap' not in sys.modules"],
        cwd=Path(__file__).resolve().parents[2] / "app", capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


def test_gunicorn_preserves_explicit_logging_configuration():
    # dictConfig touches root and other loggers; keep that state in its own process.
    program = textwrap.dedent("""
        from gunicorn.config import Config
        from gunicorn_conf import ConsoleSeverityLogger
        cfg = Config()
        cfg.set('logconfig_dict', {
            'version': 1,
            'disable_existing_loggers': False,
            'root': {'handlers': [], 'level': 'WARNING'},
            'formatters': {'custom': {'format': 'CUSTOM %(levelname)s %(message)s'}},
            'handlers': {'custom': {'class': 'logging.StreamHandler', 'stream': 'ext://sys.stdout',
                                    'formatter': 'custom'}},
            'loggers': {'gunicorn.error': {'handlers': ['custom'], 'level': 'DEBUG', 'propagate': False}},
        })
        logger = ConsoleSeverityLogger(cfg)
        logger.setup(cfg)
        logger.info('CUSTOM_INFO')
        logger.warning('CUSTOM_WARNING')
    """)
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=Path(__file__).resolve().parents[2] / "app",
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["CUSTOM INFO CUSTOM_INFO", "CUSTOM WARNING CUSTOM_WARNING"]
    assert result.stderr == ""
