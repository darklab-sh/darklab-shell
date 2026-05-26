"""HTTP clients for app-native external intel providers."""

from __future__ import annotations

import http.client
import json
import os
import ssl
import subprocess
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit

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

    def _raw_request(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        body: str | bytes | None = None,
        _redirects_remaining: int = 3,
    ) -> str:
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
            if body is None:
                conn.request(method.upper(), path, headers=headers or {})
            else:
                conn.request(method.upper(), path, body=body, headers=headers or {})
            response = conn.getresponse()
            self.last_status = int(response.status)
            location = response.getheader("location")
            if response.status in {301, 302, 303, 307, 308} and location and _redirects_remaining > 0:
                response.read()
                redirect_url = urljoin(url, location)
                if _url_origin(redirect_url) != _url_origin(url):
                    raise ProviderApiError(
                        "provider redirected to an untrusted host",
                        status=int(response.status),
                    )
                redirected_method = "GET" if response.status == 303 else method
                redirected_body = None if response.status == 303 else body
                return self._raw_request(
                    redirect_url,
                    headers=headers,
                    method=redirected_method,
                    body=redirected_body,
                    _redirects_remaining=_redirects_remaining - 1,
                )
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

    def _json_request_any(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        method: str = "GET",
        body: str | bytes | None = None,
    ) -> Any:
        raw = self._raw_request(url, headers=headers, method=method, body=body)
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

    def _json_post(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        active_headers = {"Content-Type": "application/json", **(headers or {})}
        loaded = self._json_request_any(
            url,
            headers=active_headers,
            method="POST",
            body=json.dumps(payload, separators=(",", ":")),
        )
        if not isinstance(loaded, dict):
            raise ProviderApiError("provider returned an unexpected JSON shape", status=self.last_status)
        return loaded

    def _form_post(
        self,
        url: str,
        payload: dict[str, str],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        active_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            **(headers or {}),
        }
        loaded = self._json_request_any(
            url,
            headers=active_headers,
            method="POST",
            body=urlencode(payload),
        )
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


def _url_origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port is None and parsed.scheme == "https":
        port = 443
    return parsed.scheme, host, port


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


class IpinfoApiClient(JsonApiClient):
    base_url = "https://api.ipinfo.io"
    legacy_base_url = "https://ipinfo.io"

    def lookup_ip(self, value: str, *, api_key: str = "") -> dict[str, Any]:
        path = quote(value, safe="")
        if api_key:
            query = urlencode({"token": api_key})
            return self._json_request(f"{self.base_url}/lookup/{path}?{query}")
        return self._json_request(f"{self.legacy_base_url}/{path}/json")


class CensysApiClient(JsonApiClient):
    base_url = "https://api.platform.censys.io/v3"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.censys.api.v3.host.v1+json",
        }

    def lookup_host(self, value: str, *, api_key: str, organization_id: str = "") -> dict[str, Any]:
        path = quote(value, safe="")
        query = urlencode({"organization_id": organization_id}) if organization_id else ""
        suffix = f"?{query}" if query else ""
        return self._json_request(f"{self.base_url}/global/asset/host/{path}{suffix}", headers=self._headers(api_key))


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


class VulnersApiClient(JsonApiClient):
    base_url = "https://vulners.com/api/v3"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"X-Api-Key": api_key, "Accept": "application/json"}

    def lookup_cve(self, value: str, *, api_key: str) -> dict[str, Any]:
        return self._json_post(
            f"{self.base_url}/search/id/",
            {"id": value, "fields": ["*"]},
            headers=self._headers(api_key),
        )

    def lookup_exploits(self, value: str, *, api_key: str, size: int = 5) -> dict[str, Any]:
        return self._json_post(
            f"{self.base_url}/search/lucene/",
            {
                "query": f"bulletinFamily:exploit AND {value}",
                "skip": 0,
                "size": size,
                "fields": ["id", "title", "href", "published", "modified", "cvelist"],
            },
            headers=self._headers(api_key),
        )


class UrlscanApiClient(JsonApiClient):
    base_url = "https://urlscan.io/api/v1"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"API-Key": api_key, "Accept": "application/json"}

    def search(self, query: str, *, api_key: str, size: int = 5) -> dict[str, Any]:
        params = urlencode({"q": query, "size": size})
        return self._json_request(f"{self.base_url}/search/?{params}", headers=self._headers(api_key))

    def lookup_result(self, scan_id: str, *, api_key: str) -> dict[str, Any]:
        path = quote(scan_id, safe="")
        return self._json_request(f"{self.base_url}/result/{path}/", headers=self._headers(api_key))


class UrlhausApiClient(JsonApiClient):
    base_url = "https://urlhaus-api.abuse.ch/v1"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"Auth-Key": api_key, "Accept": "application/json"}

    def lookup_url(self, value: str, *, api_key: str) -> dict[str, Any]:
        return self._form_post(f"{self.base_url}/url/", {"url": value}, headers=self._headers(api_key))

    def lookup_host(self, value: str, *, api_key: str) -> dict[str, Any]:
        return self._form_post(f"{self.base_url}/host/", {"host": value}, headers=self._headers(api_key))

    def lookup_payload(self, value: str, *, api_key: str) -> dict[str, Any]:
        key = "md5_hash" if len(str(value or "").strip()) == 32 else "sha256_hash"
        return self._form_post(f"{self.base_url}/payload/", {key: value}, headers=self._headers(api_key))


class ThreatFoxApiClient(JsonApiClient):
    base_url = "https://threatfox-api.abuse.ch/api/v1/"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"Auth-Key": api_key, "Accept": "application/json"}

    def search_ioc(self, value: str, *, api_key: str) -> dict[str, Any]:
        return self._json_post(
            self.base_url,
            {"query": "search_ioc", "search_term": value, "exact_match": True},
            headers=self._headers(api_key),
        )

    def search_hash(self, value: str, *, api_key: str) -> dict[str, Any]:
        return self._json_post(
            self.base_url,
            {"query": "search_hash", "hash": value},
            headers=self._headers(api_key),
        )


class SecurityTrailsApiClient(JsonApiClient):
    base_url = "https://api.securitytrails.com/v1"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {"APIKEY": api_key, "Accept": "application/json"}

    def lookup_domain(self, value: str, *, api_key: str) -> dict[str, Any]:
        path = quote(value, safe="")
        domain = self._json_request(f"{self.base_url}/domain/{path}", headers=self._headers(api_key))
        whois = self._json_request(f"{self.base_url}/domain/{path}/whois", headers=self._headers(api_key))
        subdomains = self._json_request(f"{self.base_url}/domain/{path}/subdomains", headers=self._headers(api_key))
        return {"domain": domain, "whois": whois, "subdomains": subdomains}


class RouteViewsApiClient(JsonApiClient):
    base_url = "https://api.routeviews.org"

    def lookup_ip(self, value: str) -> dict[str, Any]:
        prefix = _routeviews_host_prefix(value)
        loaded = self._json_request_any(f"{self.base_url}/prefix/{quote(prefix, safe='/:')}")
        if isinstance(loaded, list):
            return {"prefixes": loaded}
        if isinstance(loaded, dict):
            return loaded
        raise ProviderApiError("provider returned an unexpected JSON shape", status=self.last_status)


def _routeviews_host_prefix(value: str) -> str:
    text = str(value or "").strip()
    if "/" in text:
        return text
    return f"{text}/128" if ":" in text else f"{text}/32"


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
