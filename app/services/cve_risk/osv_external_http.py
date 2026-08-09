# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fixed HTTP and response-validation boundary for explicit OSV queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .osv_parser import OsvDatasetError, ParsedOsvDataset, parse_osv_dataset


OSV_QUERY_URL = "https://api.osv.dev/v1/query"


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def allowed_query_url(settings: Mapping[str, Any]) -> str:
    parsed = urlparse(OSV_QUERY_URL)
    allowed_hosts = {
        str(host or "").strip().casefold()
        for host in settings.get("allowed_hosts", [])
        if str(host or "").strip()
    }
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() not in allowed_hosts
    ):
        raise OsvDatasetError("OSV query URL is outside the configured HTTPS allowlist")
    return OSV_QUERY_URL


def validate_response_url(url: str, settings: Mapping[str, Any]) -> None:
    allowed_query_url(settings)
    parsed = urlparse(str(url or ""))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.osv.dev"
        or parsed.port not in {None, 443}
        or parsed.path != "/v1/query"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise OsvDatasetError("OSV query redirected outside the configured HTTPS allowlist")


def download_osv_query(
    settings: Mapping[str, Any],
    package_purl: str,
    version: str,
) -> bytes:
    payload = json.dumps({
        "package": {"purl": package_purl},
        "version": version,
    }, separators=(",", ":")).encode()
    request = Request(
        allowed_query_url(settings),
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "darklab_shell-osv-query/1",
        },
        method="POST",
    )
    timeout = max(3, min(int(settings.get("http_timeout_seconds") or 30), 120))
    max_bytes = max(
        1024,
        min(int(settings.get("max_download_bytes") or 67108864), 268435456),
    )
    # The endpoint is fixed, redirects are rejected before they can cross the
    # boundary, and the final response must be the exact allowlisted URL.
    opener = build_opener(RejectRedirects())
    with opener.open(request, timeout=timeout) as response:
        validate_response_url(response.geturl(), settings)
        response_payload = response.read(max_bytes + 1)
    if len(response_payload) > max_bytes:
        raise OsvDatasetError("OSV query response exceeds the configured download limit")
    return response_payload


def parse_osv_response(
    payload: bytes,
    *,
    package_purl: str,
    settings: Mapping[str, Any],
) -> ParsedOsvDataset | None:
    try:
        root = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OsvDatasetError("OSV query response must be valid UTF-8 JSON") from exc
    if not isinstance(root, dict):
        raise OsvDatasetError("OSV query response must be an object")
    vulns = root.get("vulns", [])
    if vulns is None:
        vulns = []
    if not isinstance(vulns, list):
        raise OsvDatasetError("OSV query vulnerabilities must be an array")
    if not vulns:
        return None
    parsed = parse_osv_dataset(
        json.dumps(vulns, separators=(",", ":")).encode(),
        max_uncompressed_bytes=int(settings.get("max_download_bytes") or 67108864),
        max_records=int(settings.get("advisory_max_records") or 500000),
    )
    records = tuple(
        record for record in parsed.records
        if str(record.get("package_purl") or "") == package_purl
    )
    if not records:
        raise OsvDatasetError("OSV query response has no exact package applicability")
    return replace(parsed, records=records)


__all__ = [
    "OSV_QUERY_URL",
    "RejectRedirects",
    "allowed_query_url",
    "download_osv_query",
    "parse_osv_response",
    "validate_response_url",
]
