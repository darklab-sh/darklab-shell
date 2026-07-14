# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Slack incoming-webhook notification channel."""

from __future__ import annotations

from typing import Any

from services.notifications.channels._format import format_slack_payload
from services.notifications.channels.webhook import WebhookChannel
from services.notifications.models import ChannelResult


class SlackChannel(WebhookChannel):
    """Send notifications to Slack using an incoming webhook URL."""

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        return self._send_payload(
            format_slack_payload(payload),
            label="slack",
            test_send=str(payload.get("trigger") or "") == "test",
        )
