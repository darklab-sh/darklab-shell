"""Tests for the generic webhook notification channel."""

from __future__ import annotations

import json
import logging
from email.message import Message
from http.client import HTTPMessage
from io import BytesIO
import socket
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import config
from services.notifications.channels import _http as notification_http
from services.notifications.channels.webhook import WebhookChannel
from services.notifications.models import ChannelResult, NotificationChannel
from services.notifications.payloads import build_project_digest_payload, build_run_complete_payload


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
        team_id="",
        kind="webhook",
        label="Webhook",
        secrets=secrets or {"url": "NOTIFY_WEBHOOK_URL"},
        config=config or {},
        triggers=("test",),
        muted=False,
        created="2026-05-20T00:00:00+00:00",
        updated="2026-05-20T00:00:00+00:00",
    )


def _http_error(status: int, *, location: str = "") -> HTTPError:
    headers: Message = Message()
    if location:
        headers["Location"] = location
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
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_urlopen)

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
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_urlopen)
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
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_urlopen)

    channel = WebhookChannel(_channel())
    first = channel.send({"trigger": "test"})
    second = channel.send({"trigger": "test"})

    assert first.ok is False
    assert first.retryable is True
    assert "503" in first.error
    assert second == ChannelResult.success()


@pytest.mark.parametrize("location", ["http://127.0.0.1/hook", "/local-redirect"])
def test_notification_http_redirect_handler_refuses_redirects(location):
    assert notification_http._NoRedirectHandler().redirect_request(  # noqa: SLF001
        Request("https://example.invalid/webhook"),
        BytesIO(),
        302,
        "Found",
        HTTPMessage(),
        location,
    ) is None


@pytest.mark.parametrize("location", ["http://127.0.0.1/hook", "/local-redirect"])
def test_webhook_channel_does_not_follow_redirects(monkeypatch, location):
    captured_urls = []

    def fake_open(request, timeout):
        captured_urls.append(request.full_url)
        raise _http_error(302, location=location)

    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid")
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_open)

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is True
    assert "302" in result.error
    assert captured_urls == ["https://example.invalid"]


def test_webhook_channel_treats_4xx_as_terminal(monkeypatch):
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid")
    monkeypatch.setattr(
        "services.notifications.channels._http._open_http_request",
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
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_urlopen)

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
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_urlopen)

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
    monkeypatch.setattr("services.notifications.channels._http._open_http_request", fake_urlopen)

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result == ChannelResult.success()
    assert captured["url"] == "http://10.0.0.5/hook"


def test_webhook_channel_retries_timeout(monkeypatch):
    monkeypatch.setattr("services.notifications.channels.webhook.get_channel_secret", lambda *_: "https://example.invalid")
    monkeypatch.setattr(
        "services.notifications.channels._http._open_http_request",
        lambda *_args, **_kwargs: _raise(socket.timeout("timed out")),
    )

    result = WebhookChannel(_channel()).send({"trigger": "test"})

    assert result.ok is False
    assert result.retryable is True
    assert "timed out" in result.error


def test_webhook_channel_log_host_strips_url_userinfo(monkeypatch, caplog):
    monkeypatch.setattr(
        "services.notifications.channels.webhook.get_channel_secret",
        lambda *_: "https://user:secret-token@example.invalid:8443/hook",
    )
    monkeypatch.setattr(
        "services.notifications.channels._http._open_http_request",
        lambda *_args, **_kwargs: _raise(socket.timeout("timed out")),
    )

    with caplog.at_level(logging.DEBUG, logger="shell"):
        result = WebhookChannel(_channel()).send({"trigger": "run_complete"})

    assert result.ok is False
    assert result.retryable is True
    assert "secret-token" not in result.error
    assert "user:secret-token@" not in result.error
    records = [record for record in caplog.records if record.name == "shell"]
    http_records = [
        record for record in records
        if record.getMessage() in {"NOTIFICATION_HTTP_REQUEST", "NOTIFICATION_HTTP_NETWORK_ERROR"}
    ]
    assert [record.getMessage() for record in http_records] == [
        "NOTIFICATION_HTTP_REQUEST",
        "NOTIFICATION_HTTP_NETWORK_ERROR",
    ]
    assert {record.host for record in http_records} == {"example.invalid:8443"}
    serialized_extras = json.dumps([
        {"host": record.host, "error": getattr(record, "error", "")}
        for record in http_records
    ])
    assert "secret-token" not in serialized_extras
    assert "user:secret-token@" not in serialized_extras


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


def test_project_digest_payload_uses_configured_public_base_url_and_safe_top_changes(monkeypatch):
    monkeypatch.setitem(config.CFG, "app_name", "Ops Shell")
    monkeypatch.setitem(config.CFG, "app_public_base_url", "https://shell.example.test")
    payload = build_project_digest_payload(
        project={"id": "prj_digest", "name": "External Edge"},
        digest_identity={
            "project_id": "prj_digest",
            "session_id": "tok_digest",
            "team_id": "",
            "window_start": "2026-05-20T10:00:00+00:00",
            "window_end": "2026-05-20T11:00:00+00:00",
        },
        summary={
            "changed_monitor_count": 1,
            "recovered_monitor_count": 1,
            "failed_monitor_count": 0,
            "highest_severity": "critical",
            "links": {"project_monitoring": "/projects/prj_digest/monitoring"},
            "top_changes": [
                {
                    "severity": "critical",
                    "fire_kind": "changed",
                    "watcher_label": "Internet Edge",
                    "label": "New open port 443/tcp https with token secret-token " + ("x" * 200),
                    "run_id": "run-secret",
                    "baseline_run_id": "run-baseline-secret",
                }
            ],
        },
    )

    assert payload["project_monitoring_path"] == "/projects/prj_digest/monitoring"
    assert payload["project_monitoring_url"] == "https://shell.example.test/projects/prj_digest/monitoring"
    assert payload["summary_fields"]["monitoring_link"] == payload["project_monitoring_url"]
    assert payload["summary_fields"]["changed"] == 1
    assert payload["top_changes"][0] == {
        "severity": "critical",
        "fire_kind": "changed",
        "watcher_label": "Internet Edge",
        "label": payload["top_changes"][0]["label"],
        "created": "",
    }
    serialized = json.dumps(payload)
    assert "run-secret" not in serialized
    assert "baseline-secret" not in serialized
    assert len(payload["top_changes"][0]["label"]) <= 140


def test_project_digest_payload_uses_relative_link_without_public_base_url(monkeypatch):
    monkeypatch.setitem(config.CFG, "app_public_base_url", "")
    payload = build_project_digest_payload(
        project={"id": "prj_digest", "name": "External Edge"},
        digest_identity={
            "project_id": "prj_digest",
            "session_id": "tok_digest",
            "team_id": "",
            "window_start": "2026-05-20T10:00:00+00:00",
            "window_end": "2026-05-20T11:00:00+00:00",
        },
        summary={"links": {"project_monitoring": "/projects/prj_digest/monitoring"}},
    )

    assert payload["project_monitoring_url"] == "/projects/prj_digest/monitoring"
