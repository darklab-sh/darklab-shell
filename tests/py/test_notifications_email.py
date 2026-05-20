"""Tests for the SMTP email notification channel."""

from __future__ import annotations

import smtplib

from services.notifications.channels import register_builtin_channels
from services.notifications.channels.email import EmailChannel
from services.notifications.base import registered_channels
from services.notifications.models import CHANNEL_KIND_EMAIL, ChannelResult, NotificationChannel


class FakeSMTP:
    instances = []

    def __init__(self, host, port, *, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.messages = []
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        self.messages.append(message)


class FailingSMTP(FakeSMTP):
    def send_message(self, message):
        raise smtplib.SMTPException("temporary SMTP outage")


def _channel(*, config=None) -> NotificationChannel:
    return NotificationChannel(
        id="ntc_email",
        session_token="tok_notifications",
        kind=CHANNEL_KIND_EMAIL,
        label="Email",
        secrets={},
        config=config or {"recipients": ["ops@example.invalid"]},
        triggers=("test",),
        muted=False,
        created="2026-05-20T00:00:00+00:00",
        updated="2026-05-20T00:00:00+00:00",
    )


def _payload() -> dict[str, object]:
    return {
        "trigger": "run_complete",
        "app_name": "Test Shell",
        "occurred_at": "2026-05-20T00:00:00+00:00",
        "run_id": "run-123",
        "command_root": "nmap",
        "exit_code": 0,
        "message": "<b>done</b>",
        "summary_fields": {"critical": 1, "unsafe": "<script>alert(1)</script>"},
    }


def _smtp_config():
    return {
        "host": "smtp.example.invalid",
        "port": 587,
        "user": "mailer",
        "password_secret_id": "DARKLAB_SMTP_PASSWORD",
        "from_address": "darklab@example.invalid",
        "tls": "starttls",
    }


def test_email_channel_is_registered():
    register_builtin_channels()

    assert registered_channels()[CHANNEL_KIND_EMAIL] is EmailChannel


def test_email_channel_rejects_missing_smtp_transport(monkeypatch):
    monkeypatch.setattr("services.notifications.database.CFG", {"notifications": {}})

    errors = EmailChannel(_channel()).validate_config({"recipients": ["ops@example.invalid"]})

    assert "SMTP host is required" in errors
    assert "SMTP from_address is required" in errors
    assert "SMTP user is required" in errors
    assert "SMTP password_secret_id is required" in errors


def test_email_channel_requires_recipients(monkeypatch):
    monkeypatch.setenv("DARKLAB_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr("services.notifications.database.CFG", {"notifications": {"smtp": _smtp_config()}})

    errors = EmailChannel(_channel(config={})).validate_config({})

    assert errors == ["at least one email recipient is required"]


def test_email_channel_sends_starttls_message(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setenv("DARKLAB_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr("services.notifications.database.CFG", {"notifications": {"smtp": _smtp_config()}})
    monkeypatch.setattr("services.notifications.channels.email.smtplib.SMTP", FakeSMTP)

    channel = EmailChannel(
        _channel(config={"recipients": "ops@example.invalid; sec@example.invalid", "reply_to": "reply@example.invalid"})
    )

    result = channel.send(_payload())

    assert result == ChannelResult.success()
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.example.invalid", 587, 15.0)
    assert smtp.started_tls is True
    assert smtp.login_args == ("mailer", "smtp-secret")
    message = smtp.messages[0]
    assert message["Subject"] == "[Test Shell] run_complete: nmap"
    assert message["From"] == "darklab@example.invalid"
    assert message["To"] == "ops@example.invalid, sec@example.invalid"
    assert message["Reply-To"] == "reply@example.invalid"
    assert "Command: nmap" in message.get_body(preferencelist=("plain",)).get_content()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.get_body(preferencelist=("html",)).get_content()


def test_email_channel_uses_smtp_ssl_without_starttls(monkeypatch):
    FakeSMTP.instances = []
    config = dict(_smtp_config(), port=465, tls="ssl")
    monkeypatch.setenv("DARKLAB_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr("services.notifications.database.CFG", {"notifications": {"smtp": config}})
    monkeypatch.setattr("services.notifications.channels.email.smtplib.SMTP_SSL", FakeSMTP)

    result = EmailChannel(_channel()).send(_payload())

    assert result == ChannelResult.success()
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.invalid", 465)
    assert smtp.started_tls is False


def test_email_channel_reports_missing_password_secret_without_leak(monkeypatch):
    monkeypatch.delenv("DARKLAB_SMTP_PASSWORD", raising=False)
    monkeypatch.setattr("services.notifications.database.CFG", {"notifications": {"smtp": _smtp_config()}})

    result = EmailChannel(_channel()).send(_payload())

    assert result.ok is False
    assert result.retryable is False
    assert "SMTP password secret is unavailable" in result.error
    assert "DARKLAB_SMTP_PASSWORD" not in result.error


def test_email_channel_retries_smtp_exceptions(monkeypatch):
    FailingSMTP.instances = []
    monkeypatch.setenv("DARKLAB_SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr("services.notifications.database.CFG", {"notifications": {"smtp": _smtp_config()}})
    monkeypatch.setattr("services.notifications.channels.email.smtplib.SMTP", FailingSMTP)

    result = EmailChannel(_channel()).send(_payload())

    assert result.ok is False
    assert result.retryable is True
    assert "temporary SMTP outage" in result.error
    assert "smtp-secret" not in result.error
