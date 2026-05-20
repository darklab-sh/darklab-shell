"""Tests for the generic webhook notification channel."""

from __future__ import annotations

import json
from email.message import Message
import socket
from urllib.error import HTTPError

import pytest

import config
from services.notifications.channels.webhook import WebhookChannel
from services.notifications.models import ChannelResult, NotificationChannel
from services.notifications.payloads import build_run_complete_payload


class FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status


def _channel(*, secrets=None, config=None) -> NotificationChannel:
    return NotificationChannel(
        id="ntc_webhook",
        session_token="tok_notifications",
        kind="webhook",
        label="Webhook",
        secrets=secrets or {"url": "NOTIFY_WEBHOOK_URL"},
        config=config or {},
        triggers=("test",),
        muted=False,
        created="2026-05-20T00:00:00+00:00",
        updated="2026-05-20T00:00:00+00:00",
    )


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


@pytest.fixture(autouse=True)
def _skip_real_dns(monkeypatch):
    monkeypatch.setattr("services.notifications.channels._http.socket.getaddrinfo", lambda *_args, **_kwargs: [])


def test_webhook_channel_posts_json_payload(monkeypatch):
    captured = {}

    def fake_get_secret(session_token, secret_name):
        assert session_token == "tok_notifications"
        assert secret_name == "NOTIFY_WEBHOOK_URL"
        return "https://hooks.example.invalid/darklab"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.headers["Content-type"]
        return FakeResponse(204)

    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", fake_get_secret)
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = WebhookChannel(_channel(config={"timeout_seconds": 4})).send({"trigger": "test", "ok": True})

    assert result == ChannelResult.success()
    assert captured == {
        "url": "https://hooks.example.invalid/darklab",
        "timeout": 4.0,
        "body": {"ok": True, "trigger": "test"},
        "content_type": "application/json",
    }


def test_webhook_channel_uses_short_timeout_for_test_send(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        return FakeResponse(204)

    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid/hook")
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)
    monkeypatch.setitem(
        config.CFG,
        "notifications",
        {"http_timeout_seconds": 9, "test_timeout_seconds": 2},
    )

    result = WebhookChannel(_channel(config={"timeout_seconds": 9})).send({"trigger": "test", "ok": True})

    assert result == ChannelResult.success()
    assert captured["timeout"] == 2.0


def test_webhook_channel_retries_5xx_then_succeeds(monkeypatch):
    calls = [0]

    def fake_urlopen(request, timeout):
        calls[0] += 1
        if calls[0] == 1:
            raise _http_error(503)
        return FakeResponse(200)

    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid")
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    channel = WebhookChannel(_channel())
    first = channel.send({"trigger": "test"})
    second = channel.send({"trigger": "test"})

    assert first.ok is False
    assert first.retryable is True
    assert "503" in first.error
    assert second == ChannelResult.success()


def test_webhook_channel_treats_4xx_as_terminal(monkeypatch):
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid")
    monkeypatch.setattr(
        "services.notifications.channels._http.urlopen",
        lambda *_args, **_kwargs: _raise(_http_error(400)),
    )

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is False
    assert "400" in result.error


@pytest.mark.parametrize("bad_url", ["", "not-a-url", "ftp://example.invalid/hook", "https:///missing-host"])
def test_webhook_channel_rejects_malformed_urls(monkeypatch, bad_url):
    urlopen_called = False

    def fake_urlopen(request, timeout):
        nonlocal urlopen_called
        urlopen_called = True
        return FakeResponse(200)

    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: bad_url)
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is False
    assert "URL" in result.error
    assert not urlopen_called


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1/hook",
        "http://localhost/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/hook",
        "http://172.16.0.5/hook",
        "http://192.168.1.5/hook",
        "http://[::1]/hook",
    ],
)
def test_webhook_channel_rejects_private_and_local_urls(monkeypatch, blocked_url):
    urlopen_called = False

    def fake_urlopen(request, timeout):
        nonlocal urlopen_called
        urlopen_called = True
        return FakeResponse(200)

    monkeypatch.setitem(config.CFG, "notifications", {"http_private_host_allowlist": []})
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: blocked_url)
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is False
    assert "not allowed" in result.error
    assert not urlopen_called


def test_webhook_channel_rejects_dns_resolved_private_hosts(monkeypatch):
    monkeypatch.setitem(config.CFG, "notifications", {"http_private_host_allowlist": []})
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://hooks.example.test")
    monkeypatch.setattr(
        "services.notifications.channels._http.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.10", 443))],
    )

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is False
    assert "not allowed" in result.error


def test_webhook_channel_allows_explicit_private_host_allowlist(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse(200)

    monkeypatch.setitem(config.CFG, "notifications", {"http_private_host_allowlist": ["10.0.0.5"]})
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "http://10.0.0.5/hook")
    monkeypatch.setattr("services.notifications.channels._http.urlopen", fake_urlopen)

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result == ChannelResult.success()
    assert captured["url"] == "http://10.0.0.5/hook"


def test_webhook_channel_retries_timeout(monkeypatch):
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid")
    monkeypatch.setattr(
        "services.notifications.channels._http.urlopen",
        lambda *_args, **_kwargs: _raise(socket.timeout("timed out")),
    )

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is True
    assert "timed out" in result.error


def test_run_complete_payload_exposes_command_root_without_full_command(monkeypatch):
    monkeypatch.setitem(config.CFG, "app_name", "Ops Shell")
    payload = build_run_complete_payload(
        {
            "id": "run-1",
            "session_token": "tok_abcdef",
            "command": "curl -H 'Authorization: Bearer secret' https://example.invalid",
            "exit_code": 0,
        },
        {"critical": 1},
    )

    assert payload == {
        "trigger": "run_complete",
        "app_name": "Ops Shell",
        "occurred_at": payload["occurred_at"],
        "session_token_hint": "cdef",
        "run_id": "run-1",
        "command_root": "curl",
        "exit_code": 0,
        "summary_fields": {"critical": 1},
    }
    assert "Authorization" not in json.dumps(payload)
