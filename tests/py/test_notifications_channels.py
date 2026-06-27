"""Tests for chat and push notification channels."""

from __future__ import annotations

import json
from email.message import Message
import socket
from urllib.error import HTTPError
from urllib.parse import parse_qs

from services.notifications.base import Channel, registered_channels
from services.notifications.channels import register_builtin_channels
from services.notifications.channels._format import format_plain_text, format_summary_fields, notification_title
from services.notifications.channels.discord import DiscordChannel
from services.notifications.channels.pushover import PushoverChannel
from services.notifications.channels.slack import SlackChannel
from services.notifications.channels.telegram import TelegramChannel
from services.notifications.models import (
    CHANNEL_KIND_DISCORD,
    CHANNEL_KIND_PUSHOVER,
    CHANNEL_KIND_SLACK,
    CHANNEL_KIND_TELEGRAM,
    ChannelResult,
    NotificationChannel,
)


class FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status


def _channel(kind: str, *, secrets=None, config=None) -> NotificationChannel:
    return NotificationChannel(
        id=f"ntc_{kind}",
        session_token="tok_notifications",
        team_id="",
        kind=kind,
        label=kind.title(),
        secrets=secrets or {"url": f"{kind.upper()}_WEBHOOK_URL"},
        config=config or {},
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
        "summary_fields": {"critical": 1, "medium": 3},
    }


def _http_error(status: int) -> HTTPError:
    headers: Message = Message()
    return HTTPError(
        "https://example.invalid/webhook",
        status,
        f"HTTP {status}",
        hdrs=headers,
        fp=None,
    )


def _raise(exc: BaseException):
    raise exc


def test_phase2_channels_are_registered():
    register_builtin_channels()
    registered = registered_channels()

    assert registered[CHANNEL_KIND_SLACK] is SlackChannel
    assert registered[CHANNEL_KIND_DISCORD] is DiscordChannel
    assert registered[CHANNEL_KIND_TELEGRAM] is TelegramChannel
    assert registered[CHANNEL_KIND_PUSHOVER] is PushoverChannel


def test_registered_channels_implement_delivery_contract():
    register_builtin_channels()

    for kind, channel_cls in registered_channels().items():
        assert issubclass(channel_cls, Channel), kind
        assert channel_cls.validate_config is not Channel.validate_config, kind
        assert channel_cls.send is not Channel.send, kind


def test_slack_channel_formats_blocks(monkeypatch):
    captured = {}
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid/slack")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(200)

    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = SlackChannel(_channel(CHANNEL_KIND_SLACK, config={"timeout_seconds": 3})).send(_payload())

    assert result == ChannelResult.success()
    assert captured["timeout"] == 3.0
    assert captured["body"]["text"] == "Test Shell run complete: nmap"
    assert captured["body"]["blocks"][0] == {
        "type": "header",
        "text": {"type": "plain_text", "text": "Test Shell run complete: nmap"},
    }
    assert {"type": "mrkdwn", "text": "*Command*\nnmap"} in captured["body"]["blocks"][1]["fields"]


def test_summary_fields_truncate_long_run_ids():
    fields = format_summary_fields({"run_id": "12345678-1234-5678-1234-abcdef123456"})

    assert ("Run", "...ef123456") in fields


def test_summary_fields_format_structured_count_maps_as_text():
    fields = format_summary_fields({
        "summary_fields": {
            "output_entity_type_counts": {"ip": 2, "domain": 2},
            "output_signal_counts": {"findings": 2, "summaries": 1},
        },
    })

    assert ("Output Entity Type Counts", "domain 2, ip 2") in fields
    assert ("Output Signal Counts", "findings 2, summaries 1") in fields


def test_project_digest_payload_formats_for_chat_push_and_email_surfaces():
    payload = {
        "trigger": "project_digest",
        "app_name": "Test Shell",
        "project_name": "External Edge",
        "occurred_at": "2026-05-20T11:00:00+00:00",
        "top_changes": [{
            "severity": "critical",
            "fire_kind": "changed",
            "watcher_label": "Internet Edge",
            "label": "New open port 443/tcp https",
        }],
        "summary_fields": {
            "project": "External Edge",
            "window": "2026-05-20T10:00:00+00:00 to 2026-05-20T11:00:00+00:00",
            "changed": 1,
            "recovered": 0,
            "failed": 0,
            "highest_severity": "critical",
            "quiet": "no",
            "monitoring_link": "/projects/prj_digest/monitoring",
        },
    }

    fields = format_summary_fields(payload)
    plain_text = format_plain_text(payload)

    assert notification_title(payload) == "Test Shell project digest: External Edge"
    assert fields[:4] == [
        ("Project", "External Edge"),
        ("Window", "2026-05-20T10:00:00+00:00 to 2026-05-20T11:00:00+00:00"),
        ("Changed", "1"),
        ("Recovered", "0"),
    ]
    assert ("Monitoring", "/projects/prj_digest/monitoring") in fields
    assert ("Top Change 1", "critical: New open port 443/tcp https (Internet Edge)") in fields
    assert "Test Shell project digest: External Edge" in plain_text
    assert "Top Change 1: critical: New open port 443/tcp https (Internet Edge)" in plain_text


def test_discord_channel_formats_embed(monkeypatch):
    captured = {}
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid/discord")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(204)

    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = DiscordChannel(_channel(CHANNEL_KIND_DISCORD)).send(_payload())

    assert result == ChannelResult.success()
    assert captured["body"]["embeds"][0]["title"] == "Test Shell run complete: nmap"
    assert {"name": "Command", "value": "nmap", "inline": True} in captured["body"]["embeds"][0]["fields"]
    assert captured["body"]["embeds"][0]["footer"] == {"text": "2026-05-20T00:00:00+00:00"}


def test_chat_webhook_channels_share_retry_and_terminal_outcomes(monkeypatch):
    calls = [0]
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid/discord")

    def fake_urlopen(request, timeout):
        calls[0] += 1
        if calls[0] == 1:
            raise _http_error(503)
        raise _http_error(400)

    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    channel = DiscordChannel(_channel(CHANNEL_KIND_DISCORD))
    retry = channel.send(_payload())
    terminal = channel.send(_payload())

    assert retry.ok is False
    assert retry.retryable is True
    assert "503" in retry.error
    assert terminal.ok is False
    assert terminal.retryable is False
    assert "400" in terminal.error


def test_telegram_channel_requires_chat_id():
    channel = TelegramChannel(_channel(CHANNEL_KIND_TELEGRAM, secrets={"bot_token": "TELEGRAM_BOT_TOKEN"}))

    assert channel.validate_config({}) == ["Telegram chat_id is required"]


def test_telegram_channel_posts_plain_text_without_token_in_body(monkeypatch):
    captured = {}
    monkeypatch.setattr("services.notifications.channels.telegram.get_channel_secret", lambda *_: "123456:secret-token")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(200)

    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = TelegramChannel(
        _channel(
            CHANNEL_KIND_TELEGRAM,
            secrets={"bot_token": "TELEGRAM_BOT_TOKEN"},
            config={"chat_id": "-100123"},
        )
    ).send(_payload())

    assert result == ChannelResult.success()
    assert captured["url"] == "https://api.telegram.org/bot123456:secret-token/sendMessage"
    assert captured["body"]["chat_id"] == "-100123"
    assert captured["body"]["disable_web_page_preview"] is True
    assert "Test Shell run complete: nmap" in captured["body"]["text"]
    assert "123456:secret-token" not in captured["body"]["text"]


def test_telegram_channel_timeout_is_retryable_without_token_leak(monkeypatch):
    monkeypatch.setattr("services.notifications.channels.telegram.get_channel_secret", lambda *_: "123456:secret-token")
    monkeypatch.setattr(
        "services.notifications.channels._http.urlopen",
        lambda *_args, **_kwargs: _raise(socket.timeout("timed out")),
    )

    result = TelegramChannel(
        _channel(
            CHANNEL_KIND_TELEGRAM,
            secrets={"bot_token": "TELEGRAM_BOT_TOKEN"},
            config={"chat_id": "-100123"},
        )
    ).send(_payload())

    assert result.ok is False
    assert result.retryable is True
    assert "timed out" in result.error
    assert "secret-token" not in result.error


def test_pushover_channel_posts_form_payload(monkeypatch):
    captured = {}

    def fake_get_secret(session_token, secret_name):
        assert session_token == "tok_notifications"
        return {
            "PUSHOVER_APP_TOKEN": "app-secret",
            "PUSHOVER_USER_KEY": "user-secret",
        }[secret_name]

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = parse_qs(request.data.decode("utf-8"))
        return FakeResponse(200)

    monkeypatch.setattr("services.notifications.channels.pushover.get_channel_secret", fake_get_secret)
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = PushoverChannel(
        _channel(
            CHANNEL_KIND_PUSHOVER,
            secrets={"app_token": "PUSHOVER_APP_TOKEN", "user_key": "PUSHOVER_USER_KEY"},
            config={"priority": "1", "sound": "magic"},
        )
    ).send(_payload())

    assert result == ChannelResult.success()
    assert captured["url"] == "https://api.pushover.net/1/messages.json"
    assert captured["body"]["token"] == ["app-secret"]
    assert captured["body"]["user"] == ["user-secret"]
    assert captured["body"]["title"] == ["Test Shell run complete: nmap"]
    assert captured["body"]["priority"] == ["1"]
    assert captured["body"]["sound"] == ["magic"]
    assert "device" not in captured["body"]


def test_pushover_channel_requires_secret_refs():
    channel = PushoverChannel(_channel(CHANNEL_KIND_PUSHOVER, secrets={}))

    assert channel.validate_config({}) == [
        "Pushover app token secret is required",
        "Pushover user key secret is required",
    ]
