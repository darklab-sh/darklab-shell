"""HTTP clients for app-native external intel providers."""

from __future__ import annotations

import http.client
import json
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from services.intel.base import ProviderApiError


class JsonApiClient:
    timeout_seconds = 12

    def __init__(self):
        self.last_status: int | None = None

    def _json_request(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderApiError("provider URL must use HTTPS")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn: http.client.HTTPSConnection | None = None
        try:
            conn = http.client.HTTPSConnection(parsed.netloc, timeout=self.timeout_seconds)
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            self.last_status = int(response.status)
            raw_bytes = response.read()
            raw = raw_bytes.decode("utf-8", errors="replace")
            reset_at = _header_float(response.getheader("x-ratelimit-reset"))
            if response.status >= 400:
                message = _provider_error_message(response.status, raw)
                raise ProviderApiError(message, status=int(response.status), reset_at=reset_at)
        except OSError as exc:
            raise ProviderApiError(str(exc)) from exc
        finally:
            if conn is not None:
                conn.close()
        try:
            loaded = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderApiError("provider returned invalid JSON", status=self.last_status) from exc
        if not isinstance(loaded, dict):
            raise ProviderApiError("provider returned an unexpected JSON shape", status=self.last_status)
        return loaded


class ShodanApiClient(JsonApiClient):
    base_url = "https://api.shodan.io"

    def lookup_ip(self, value: str, *, api_key: str) -> dict[str, Any]:
        path = quote(value, safe="")
        query = urlencode({"key": api_key})
        return self._json_request(f"{self.base_url}/shodan/host/{path}?{query}")


class VirusTotalApiClient(JsonApiClient):
    base_url = "https://www.virustotal.com/api/v3"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"x-apikey": api_key, "accept": "application/json"}

    def lookup_domain(self, value: str, *, api_key: str) -> dict[str, Any]:
        path = quote(value, safe="")
        return self._json_request(f"{self.base_url}/domains/{path}", headers=self._headers(api_key))

    def lookup_hash(self, value: str, *, api_key: str) -> dict[str, Any]:
        path = quote(value, safe="")
        return self._json_request(f"{self.base_url}/files/{path}", headers=self._headers(api_key))


class GreyNoiseApiClient(JsonApiClient):
    base_url = "https://api.greynoise.io/v3"

    def lookup_ip(self, value: str, *, api_key: str) -> dict[str, Any]:
        path = quote(value, safe="")
        headers = {"key": api_key, "accept": "application/json"}
        return self._json_request(f"{self.base_url}/community/{path}", headers=headers)


def _header_float(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _provider_error_message(status: int, raw: str) -> str:
    try:
        loaded = json.loads(raw or "{}")
    except json.JSONDecodeError:
        loaded = {}
    if isinstance(loaded, dict):
        error = loaded.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        message = loaded.get("message") or loaded.get("error")
        if message:
            return str(message)
    return f"provider returned HTTP {int(status)}"
