"""SMTP email notification channel."""

from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib
from typing import Any

from jinja2 import Environment, select_autoescape

from core import database
from services.notifications.base import Channel, register_channel
from services.notifications.channels._format import format_plain_text, format_summary_fields
from services.notifications.models import CHANNEL_KIND_EMAIL, ChannelResult, notification_app_name

DEFAULT_SMTP_TIMEOUT_SECONDS = 15.0
EMAIL_HTML_ENV = Environment(autoescape=select_autoescape(default=True))
EMAIL_HTML_TEMPLATE = EMAIL_HTML_ENV.from_string(
    """
<!doctype html>
<html>
  <body>
    <h2>{{ title }}</h2>
    {% if message %}<p>{{ message }}</p>{% endif %}
    {% if fields %}
    <table>
      <tbody>
        {% for label, value in fields %}
        <tr><th align="left">{{ label }}</th><td>{{ value }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
    {% endif %}
  </body>
</html>
""".strip()
)


def _notifications_cfg() -> dict[str, Any]:
    cfg = database.CFG.get("notifications", {})
    return cfg if isinstance(cfg, dict) else {}


def _smtp_cfg() -> dict[str, Any]:
    cfg = _notifications_cfg().get("smtp", {})
    return cfg if isinstance(cfg, dict) else {}


def _recipients(config: dict[str, Any]) -> list[str]:
    value = config.get("recipients")
    if isinstance(value, list):
        candidates = value
    elif isinstance(value, str):
        candidates = value.replace(";", ",").split(",")
    else:
        candidates = []
    return [str(item).strip() for item in candidates if str(item or "").strip()]


def _port(value: Any) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _timeout_seconds(config: dict[str, Any]) -> float:
    raw = config.get("timeout_seconds", _notifications_cfg().get("http_timeout_seconds", DEFAULT_SMTP_TIMEOUT_SECONDS))
    if raw is None:
        return DEFAULT_SMTP_TIMEOUT_SECONDS
    try:
        return max(1.0, min(60.0, float(raw)))
    except (TypeError, ValueError):
        return DEFAULT_SMTP_TIMEOUT_SECONDS


def _tls_mode(value: Any) -> str:
    if isinstance(value, bool):
        return "starttls" if value else "none"
    mode = str(value or "starttls").strip().lower()
    if mode in {"true", "yes", "on"}:
        return "starttls"
    if mode in {"false", "no", "off"}:
        return "none"
    if mode in {"starttls", "ssl", "none"}:
        return mode
    return "starttls"


def _smtp_config_errors(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(config.get("host") or "").strip():
        errors.append("SMTP host is required")
    if _port(config.get("port")) is None:
        errors.append("SMTP port must be between 1 and 65535")
    if not str(config.get("from_address") or "").strip():
        errors.append("SMTP from_address is required")
    if not str(config.get("user") or "").strip():
        errors.append("SMTP user is required")
    password_secret_id = str(config.get("password_secret_id") or "").strip()
    if not password_secret_id:
        errors.append("SMTP password_secret_id is required")
    elif not os.environ.get(password_secret_id):
        errors.append("SMTP password secret is unavailable")
    return errors


def _message_subject(payload: dict[str, Any]) -> str:
    trigger = str(payload.get("trigger") or "notification").strip() or "notification"
    command_root = str(payload.get("command_root") or "").strip()
    app_name = str(payload.get("app_name") or "").strip() or notification_app_name()
    suffix = f": {command_root}" if command_root else ""
    return f"[{app_name}] {trigger}{suffix}"[:180]


def _html_body(payload: dict[str, Any]) -> str:
    return EMAIL_HTML_TEMPLATE.render(
        title=_message_subject(payload),
        message=str(payload.get("message") or "").strip(),
        fields=format_summary_fields(payload),
    )


class EmailChannel(Channel):
    """Send notifications through the operator-configured SMTP relay."""

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors = _smtp_config_errors(_smtp_cfg())
        recipients = _recipients(config)
        if not recipients:
            errors.append("at least one email recipient is required")
        reply_to = str(config.get("reply_to") or "").strip()
        if reply_to and "@" not in reply_to:
            errors.append("reply_to must be an email address")
        return errors

    def send(self, payload: dict[str, Any]) -> ChannelResult:
        config = _smtp_cfg()
        errors = _smtp_config_errors(config)
        if errors:
            return ChannelResult.terminal("; ".join(errors))
        recipients = _recipients(self.channel.config)
        if not recipients:
            return ChannelResult.terminal("at least one email recipient is required")

        password_secret_id = str(config.get("password_secret_id") or "").strip()
        password = os.environ.get(password_secret_id)
        if password is None:
            return ChannelResult.terminal("SMTP password secret is unavailable")

        message = EmailMessage()
        message["Subject"] = _message_subject(payload)
        message["From"] = str(config.get("from_address") or "").strip()
        message["To"] = ", ".join(recipients)
        reply_to = str(self.channel.config.get("reply_to") or "").strip()
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content(format_plain_text(payload))
        message.add_alternative(_html_body(payload), subtype="html")

        host = str(config.get("host") or "").strip()
        port = _port(config.get("port"))
        if port is None:
            return ChannelResult.terminal("SMTP port must be between 1 and 65535")
        tls_mode = _tls_mode(config.get("tls"))
        timeout = _timeout_seconds(self.channel.config)
        try:
            if tls_mode == "ssl":
                with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                    smtp.login(str(config.get("user") or ""), password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                    if tls_mode == "starttls":
                        smtp.starttls()
                    smtp.login(str(config.get("user") or ""), password)
                    smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            return ChannelResult.retry(f"email delivery failed: {exc}")
        return ChannelResult.success()


register_channel(CHANNEL_KIND_EMAIL, EmailChannel)
