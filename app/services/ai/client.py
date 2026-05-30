"""OpenAI-compatible provider client for optional AI assists."""

from __future__ import annotations

from dataclasses import dataclass, field
import http.client
import ipaddress
import json
import logging
import socket
import ssl
import time
from collections.abc import Iterator
from typing import Any, Callable
from urllib.parse import urlparse

from services import metrics as app_metrics
from services.ai import ai_cfg
from services.ai.schemas import AISchemaError

log = logging.getLogger("shell")


class AIClientError(RuntimeError):
    """Provider-facing error with a stable UI/metric code."""

    def __init__(self, code: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class AIProviderResult:
    payload: dict[str, Any]
    raw_content: str
    finish_reason: str
    duration_ms: int
    output_chars: int
    provider_timings: dict[str, int | float] = field(default_factory=dict)


AIProgressCallback = Callable[[dict[str, Any]], None]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that dials a vetted IP while preserving SNI."""

    def __init__(self, connect_host: str, original_host: str, *args, read_timeout: float, **kwargs):
        super().__init__(connect_host, *args, **kwargs)
        self._original_host = original_host
        self._read_timeout = read_timeout

    def connect(self) -> None:
        sock = socket.create_connection(
            (self.host, self.port),
            timeout=self.timeout,
            source_address=getattr(self, "source_address", None),
        )
        sock.settimeout(self._read_timeout)
        context = getattr(self, "_context", None) or ssl.create_default_context()
        self.sock = context.wrap_socket(sock, server_hostname=self._original_host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, read_timeout: float, **kwargs):
        super().__init__(*args, **kwargs)
        self._read_timeout = read_timeout

    def connect(self) -> None:
        super().connect()
        if self.sock:
            self.sock.settimeout(self._read_timeout)


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise AIClientError("ai_malformed", "Provider response was not valid JSON") from None
        try:
            parsed = json.loads(content[start:end + 1])
        except json.JSONDecodeError as exc:
            raise AIClientError("ai_malformed", f"Provider response was not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise AIClientError("ai_malformed", "Provider response JSON must be an object")
    return parsed


def _provider_timings(response: dict[str, Any]) -> dict[str, int | float]:
    raw = response.get("timings")
    usage = response.get("usage")
    timings: dict[str, int | float] = {}
    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if isinstance(prompt_tokens, (int, float)):
            timings["prompt_n"] = int(prompt_tokens)
        if isinstance(completion_tokens, (int, float)):
            timings["predicted_n"] = int(completion_tokens)
        if isinstance(total_tokens, (int, float)):
            timings["total_n"] = int(total_tokens)
    if not isinstance(raw, dict):
        return timings
    for key in ("prompt_n", "prompt_ms", "predicted_n", "predicted_ms"):
        value = raw.get(key)
        if not isinstance(value, (int, float)):
            continue
        timings[key] = int(value) if key.endswith("_n") else float(value)
    return timings


def _stream_progress(
    started: float,
    content: str,
    *,
    usage: dict[str, Any],
    timings: dict[str, Any],
) -> dict[str, Any]:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    prompt_tokens = _int_or_none(usage.get("prompt_tokens")) if isinstance(usage, dict) else None
    completion_tokens = _int_or_none(usage.get("completion_tokens")) if isinstance(usage, dict) else None
    total_tokens = _int_or_none(usage.get("total_tokens")) if isinstance(usage, dict) else None
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    if total_tokens is None and isinstance(timings, dict):
        prompt_n = _int_or_none(timings.get("prompt_n"))
        predicted_n = _int_or_none(timings.get("predicted_n"))
        if prompt_n is not None and predicted_n is not None:
            total_tokens = prompt_n + predicted_n
        elif predicted_n is not None:
            total_tokens = predicted_n
    progress = {
        "phase": "generating",
        "elapsed_ms": elapsed_ms,
        "output_chars_seen": len(content),
    }
    if total_tokens is not None:
        progress["tokens_seen"] = total_tokens
    if prompt_tokens is not None:
        progress["input_tokens_seen"] = prompt_tokens
    if completion_tokens is not None:
        progress["output_tokens_seen"] = completion_tokens
    return progress


def _int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _metric_status_for_error(exc: AIClientError) -> str:
    return "rate_limited" if exc.code == "ai_rate_limited" else "error"


def _allowed_ai_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address, allowed_cidrs: list[str]) -> bool:
    if address.is_loopback or address.is_private or address.is_link_local:
        return True
    for cidr in allowed_cidrs:
        try:
            if address in ipaddress.ip_network(str(cidr), strict=False):
                return True
        except ValueError:
            continue
    return False


def _resolve_allowed_host(hostname: str, port: int, allowed_cidrs: list[str]) -> str:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _allowed_ai_address(literal, allowed_cidrs):
            return str(literal)
        raise AIClientError("ai_base_url_not_allowed", "AI_BASE_URL resolved outside allowed private ranges")

    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AIClientError("ai_unavailable", f"AI provider DNS lookup failed: {exc}") from exc
    for info in infos:
        address_text = str(info[4][0])
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError:
            continue
        if _allowed_ai_address(address, allowed_cidrs):
            return address_text
    raise AIClientError("ai_base_url_not_allowed", "AI_BASE_URL resolved outside allowed private ranges")


class OpenAICompatibleClient:
    def __init__(
        self,
        cfg: dict | None = None,
        *,
        session_token: str | None = None,
        secret_scope_token: str | None = None,
        progress_callback: AIProgressCallback | None = None,
    ):
        self.cfg = ai_cfg(cfg)
        self.session_token = session_token
        self.secret_scope_token = secret_scope_token or session_token
        self.progress_callback = progress_callback
        self.base_url = self.cfg["base_url"]
        self.model = self.cfg["model"]
        self.connect_timeout = max(1.0, float(self.cfg["connect_timeout_seconds"]))
        self.read_timeout = max(1.0, float(self.cfg["timeout_seconds"]))

    def _api_key(self) -> str:
        secret_name = str(self.cfg.get("api_key_secret_name") or "").strip()
        if secret_name and self.secret_scope_token:
            try:
                from services.secrets.storage import get_secret_value_for_env  # noqa: PLC0415

                value = get_secret_value_for_env(
                    self.secret_scope_token,
                    secret_name,
                    audit_session_id=self.session_token or "",
                    team_id=self.secret_scope_token if self.secret_scope_token != self.session_token else "",
                )
                if value:
                    return value
            except Exception:
                log.warning("AI_SECRET_LOOKUP_FAILED", exc_info=True, extra={"secret_name": secret_name})
        return str(self.cfg.get("api_key") or "").strip()

    def _connection_target(self):
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AIClientError("ai_unavailable", "AI_BASE_URL must be an absolute http(s) URL")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        original_host = parsed.hostname
        if self.cfg.get("require_private_base_url", True):
            connect_host = _resolve_allowed_host(
                original_host,
                port,
                list(self.cfg.get("base_url_allowed_cidrs") or []),
            )
        else:
            connect_host = original_host
        path_prefix = parsed.path.rstrip("/")
        host_header = parsed.netloc
        return parsed.scheme, connect_host, original_host, port, path_prefix, host_header

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.cfg["enabled"]:
            raise AIClientError("ai_disabled", "AI is disabled")
        if self.cfg["provider"] != "openai_compatible":
            raise AIClientError("ai_unavailable", "Unsupported AI provider")
        if not self.base_url or not self.model:
            raise AIClientError("ai_unavailable", "AI_BASE_URL and AI_MODEL must be configured")

        scheme, connect_host, original_host, port, path_prefix, host_header = self._connection_target()
        request_path = f"{path_prefix}{path}" if path_prefix else path
        body = b""
        headers = {
            "Accept": "application/json",
            "Host": host_header,
            "User-Agent": "darklab_shell-ai/1",
        }
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        api_key = self._api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if scheme == "https":
            conn = _PinnedHTTPSConnection(
                connect_host,
                original_host,
                port=port,
                timeout=self.connect_timeout,
                read_timeout=self.read_timeout,
            )
        else:
            conn = _PinnedHTTPConnection(connect_host, port=port, timeout=self.connect_timeout, read_timeout=self.read_timeout)
        try:
            conn.request(method.upper(), request_path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read(1024 * 1024)
        except (TimeoutError, socket.timeout, OSError, http.client.HTTPException) as exc:
            raise AIClientError("ai_unavailable", f"AI provider request failed: {exc}") from exc
        finally:
            conn.close()

        status = int(response.status)
        if status == 429:
            raise AIClientError("ai_rate_limited", "AI provider rate limited the request", status=status)
        if status >= 500:
            raise AIClientError("ai_unavailable", f"AI provider returned HTTP {status}", status=status)
        if status < 200 or status >= 300:
            raise AIClientError("ai_unavailable", f"AI provider returned HTTP {status}", status=status)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AIClientError("ai_malformed", "AI provider returned non-UTF-8 JSON") from exc
        try:
            parsed = json.loads(decoded or "{}")
        except json.JSONDecodeError as exc:
            raise AIClientError("ai_malformed", f"AI provider returned invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise AIClientError("ai_malformed", "AI provider JSON response must be an object")
        return parsed

    def list_models(self) -> dict[str, Any]:
        return self._request_json("GET", "/v1/models")

    def _request_stream(self, method: str, path: str, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        if not self.cfg["enabled"]:
            raise AIClientError("ai_disabled", "AI is disabled")
        if self.cfg["provider"] != "openai_compatible":
            raise AIClientError("ai_unavailable", "Unsupported AI provider")
        if not self.base_url or not self.model:
            raise AIClientError("ai_unavailable", "AI_BASE_URL and AI_MODEL must be configured")

        scheme, connect_host, original_host, port, path_prefix, host_header = self._connection_target()
        request_path = f"{path_prefix}{path}" if path_prefix else path
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Host": host_header,
            "User-Agent": "darklab_shell-ai/1",
        }
        api_key = self._api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if scheme == "https":
            conn = _PinnedHTTPSConnection(
                connect_host,
                original_host,
                port=port,
                timeout=self.connect_timeout,
                read_timeout=self.read_timeout,
            )
        else:
            conn = _PinnedHTTPConnection(connect_host, port=port, timeout=self.connect_timeout, read_timeout=self.read_timeout)
        try:
            conn.request(method.upper(), request_path, body=body, headers=headers)
            response = conn.getresponse()
            status = int(response.status)
            if status == 429:
                raise AIClientError("ai_rate_limited", "AI provider rate limited the request", status=status)
            if status >= 500:
                raise AIClientError("ai_unavailable", f"AI provider returned HTTP {status}", status=status)
            if status < 200 or status >= 300:
                raise AIClientError("ai_unavailable", f"AI provider returned HTTP {status}", status=status)
            for raw_line in response:
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError as exc:
                    raise AIClientError("ai_malformed", "AI provider returned non-UTF-8 stream data") from exc
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    item = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise AIClientError("ai_malformed", f"AI provider returned invalid stream JSON: {exc.msg}") from exc
                if isinstance(item, dict):
                    yield item
        except (TimeoutError, socket.timeout, OSError, http.client.HTTPException) as exc:
            raise AIClientError("ai_unavailable", f"AI provider request failed: {exc}") from exc
        finally:
            conn.close()

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        validate: Callable[[Any], dict[str, Any]],
        max_tokens: int | None = None,
        metric_variant: str = "diag_test",
        retry_on_schema_error: bool = True,
    ) -> AIProviderResult:
        started = time.perf_counter()
        request_payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": int(max_tokens or self.cfg["max_output_tokens"]),
        }
        if self.cfg.get("cache_prompt"):
            request_payload["cache_prompt"] = True
        try:
            for attempt in (1, 2):
                if self.progress_callback:
                    response = self._stream_chat_completion(request_payload, started)
                else:
                    response = self._request_json("POST", "/v1/chat/completions", request_payload)
                provider_timings = _provider_timings(response)
                choices = response.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise AIClientError("ai_malformed", "AI provider response had no choices")
                choice = choices[0] if isinstance(choices[0], dict) else {}
                finish_reason = str(choice.get("finish_reason") or "")
                message_value = choice.get("message")
                message = message_value if isinstance(message_value, dict) else {}
                content = str(message.get("content") or "")
                try:
                    parsed = _parse_json_object(content)
                    payload = validate(parsed)
                    duration_ms = int((time.perf_counter() - started) * 1000)
                    app_metrics.record_ai_request(
                        metric_variant,
                        "success",
                        duration_ms / 1000,
                        error_code="",
                        provider=self.cfg["provider"],
                        provider_timings=provider_timings,
                    )
                    return AIProviderResult(
                        payload=payload,
                        raw_content=content,
                        finish_reason=finish_reason,
                        duration_ms=duration_ms,
                        output_chars=len(content),
                        provider_timings=provider_timings,
                    )
                except (AIClientError, AISchemaError) as exc:
                    provider_truncated = finish_reason == "length"
                    error_message = "AI provider truncated the JSON response" if provider_truncated else str(exc)
                    if attempt == 1 and retry_on_schema_error and not provider_truncated:
                        log.warning(
                            "AI_PROVIDER_SCHEMA_RETRY",
                            extra={
                                "variant": metric_variant,
                                "attempt": attempt,
                                "model": self.model,
                                "finish_reason": finish_reason,
                                "output_chars": len(content),
                                "error_type": type(exc).__name__,
                                "provider_truncated": provider_truncated,
                            },
                        )
                        request_payload["messages"] = [
                            *messages,
                            {
                                "role": "user",
                                "content": (
                                    "Your last response failed schema validation with: "
                                    f"{error_message}. Reply with valid JSON only."
                                ),
                            },
                        ]
                        continue
                    raise AIClientError("ai_malformed", error_message) from exc
            raise AIClientError("ai_malformed", "AI provider returned malformed JSON")
        except AIClientError as exc:
            app_metrics.record_ai_request(
                metric_variant,
                _metric_status_for_error(exc),
                int((time.perf_counter() - started) * 1000) / 1000,
                error_code=exc.code,
                provider=self.cfg["provider"],
            )
            raise

    def _stream_chat_completion(self, request_payload: dict[str, Any], started: float) -> dict[str, Any]:
        stream_payload = {
            **request_payload,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        content_parts: list[str] = []
        finish_reason = ""
        usage: dict[str, Any] = {}
        timings: dict[str, Any] = {}
        for event in self._request_stream("POST", "/v1/chat/completions", stream_payload):
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            if isinstance(event.get("timings"), dict):
                timings = event["timings"]
            choices = event.get("choices")
            if isinstance(choices, list) and choices:
                raw_choice = choices[0]
                choice = raw_choice if isinstance(raw_choice, dict) else {}
                finish_reason = str(choice.get("finish_reason") or finish_reason)
                raw_delta = choice.get("delta")
                raw_message = choice.get("message")
                delta = raw_delta if isinstance(raw_delta, dict) else {}
                message = raw_message if isinstance(raw_message, dict) else {}
                content = str(delta.get("content") or message.get("content") or "")
                if content:
                    content_parts.append(content)
            progress = _stream_progress(
                started,
                "".join(content_parts),
                usage=usage,
                timings=timings,
            )
            if progress and self.progress_callback:
                self.progress_callback(progress)
        response: dict[str, Any] = {
            "choices": [{
                "finish_reason": finish_reason,
                "message": {"content": "".join(content_parts)},
            }],
        }
        if usage:
            response["usage"] = usage
        if timings:
            response["timings"] = timings
        return response
