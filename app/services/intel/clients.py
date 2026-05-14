"""HTTP clients for app-native external intel providers."""

from __future__ import annotations

import http.client
import json
import os
import ssl
import subprocess
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from services.intel.base import ProviderApiError


SYSTEM_CA_BUNDLE_PATHS = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
)


class JsonApiClient:
    timeout_seconds = 12

    def __init__(self):
        self.last_status: int | None = None

    def _raw_request(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ProviderApiError("provider URL must use HTTPS")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn: http.client.HTTPSConnection | None = None
        try:
            conn = http.client.HTTPSConnection(
                parsed.netloc,
                timeout=self.timeout_seconds,
                context=_default_ssl_context(),
            )
            conn.request("GET", path, headers=headers or {})
            response = conn.getresponse()
            self.last_status = int(response.status)
            raw_bytes = response.read()
            raw = raw_bytes.decode("utf-8", errors="replace")
            reset_at = _header_float(response.getheader("x-ratelimit-reset"))
            if response.status >= 400:
                message = _provider_error_message(response.status, raw)
                raise ProviderApiError(message, status=int(response.status), reset_at=reset_at)
            return raw
        except OSError as exc:
            raise ProviderApiError(str(exc)) from exc
        finally:
            if conn is not None:
                conn.close()

    def _json_request_any(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        raw = self._raw_request(url, headers=headers)
        try:
            loaded = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderApiError("provider returned invalid JSON", status=self.last_status) from exc
        return loaded

    def _json_request(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        loaded = self._json_request_any(url, headers=headers)
        if not isinstance(loaded, dict):
            raise ProviderApiError("provider returned an unexpected JSON shape", status=self.last_status)
        return loaded

    def _text_request(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        return self._raw_request(url, headers=headers)


def _default_ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    capath = os.environ.get("SSL_CERT_DIR")
    if cafile or capath:
        return ssl.create_default_context(cafile=cafile or None, capath=capath or None)
    for candidate in SYSTEM_CA_BUNDLE_PATHS:
        if os.path.exists(candidate):
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


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


class OtxApiClient(JsonApiClient):
    base_url = "https://otx.alienvault.com/api/v1"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"X-OTX-API-KEY": api_key, "Accept": "application/json"}

    def lookup_indicator(self, indicator_type: str, value: str, *, api_key: str) -> dict[str, Any]:
        type_path = quote(indicator_type, safe="")
        value_path = quote(value, safe="")
        return self._json_request(
            f"{self.base_url}/indicators/{type_path}/{value_path}/general",
            headers=self._headers(api_key),
        )


class AbuseIpdbApiClient(JsonApiClient):
    base_url = "https://api.abuseipdb.com/api/v2"

    def lookup_ip(self, value: str, *, api_key: str, max_age_days: int = 90) -> dict[str, Any]:
        query = urlencode({"ipAddress": value, "maxAgeInDays": max_age_days})
        headers = {"Key": api_key, "Accept": "application/json"}
        return self._json_request(f"{self.base_url}/check?{query}", headers=headers)


class CensysApiClient(JsonApiClient):
    base_url = "https://api.platform.censys.io/v3"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.censys.api.v3.host.v1+json",
        }

    def lookup_host(self, value: str, *, api_key: str) -> dict[str, Any]:
        path = quote(value, safe="")
        return self._json_request(f"{self.base_url}/global/asset/host/{path}", headers=self._headers(api_key))


class CrtshApiClient(JsonApiClient):
    base_url = "https://crt.sh"

    def lookup_domain(self, value: str) -> list[Any]:
        query = urlencode({"q": value, "output": "json"})
        loaded = self._json_request_any(f"{self.base_url}/?{query}")
        return loaded if isinstance(loaded, list) else []


class HibpPwnedPasswordsClient(JsonApiClient):
    base_url = "https://api.pwnedpasswords.com"

    def lookup_sha1_prefix(self, prefix: str) -> str:
        path = quote(prefix.upper(), safe="")
        headers = {
            "Add-Padding": "true",
            "User-Agent": "darklab_shell",
        }
        return self._text_request(f"{self.base_url}/range/{path}", headers=headers)


class NvdApiClient(JsonApiClient):
    base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def lookup_cve(self, value: str) -> dict[str, Any]:
        query = urlencode({"cveId": value})
        return self._json_request(f"{self.base_url}?{query}")


class TeamCymruDnsClient:
    last_status: int | None = None

    def lookup_ip(self, value: str) -> dict[str, Any]:
        query = _teamcymru_query(value)
        records = self._lookup_txt(query)
        asn_records = []
        for asn in _teamcymru_asns_from_origin_records(records):
            try:
                asn_records.extend(self._lookup_txt(_teamcymru_asn_query(asn)))
            except ProviderApiError:
                continue
        self.last_status = 200
        return {"records": records, "asn_records": asn_records}

    def _lookup_txt(self, query: str) -> list[str]:
        try:
            proc = subprocess.run(
                ["dig", "+short", "TXT", query],
                capture_output=True,
                check=False,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderApiError(str(exc)) from exc
        if proc.returncode != 0:
            raise ProviderApiError((proc.stderr or "Team Cymru DNS lookup failed").strip())
        return [line for line in proc.stdout.splitlines() if line.strip()]


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


def _teamcymru_query(value: str) -> str:
    import ipaddress

    ip = ipaddress.ip_address(str(value or "").strip())
    if ip.version == 4:
        reversed_ip = ".".join(reversed(ip.exploded.split(".")))
        return f"{reversed_ip}.origin.asn.cymru.com"
    nibbles = ip.exploded.replace(":", "")
    reversed_nibbles = ".".join(reversed(nibbles))
    return f"{reversed_nibbles}.origin6.asn.cymru.com"


def _teamcymru_asn_query(asn: str) -> str:
    return f"AS{str(asn).strip().upper().removeprefix('AS')}.asn.cymru.com"


def _teamcymru_asns_from_origin_records(records: list[str]) -> list[str]:
    asns = []
    seen = set()
    for record in records:
        cleaned = str(record or "").strip().strip('"')
        asn_field = cleaned.split("|", 1)[0]
        for token in asn_field.replace(",", " ").split():
            normalized = token.strip().upper().removeprefix("AS")
            if normalized.isdigit() and normalized not in seen:
                seen.add(normalized)
                asns.append(normalized)
    return asns
