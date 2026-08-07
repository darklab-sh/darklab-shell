# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe normalization for passive historical URL discovery output."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

MAX_HISTORICAL_URLS = 256
MAX_URL_LENGTH = 2048
_DOMAIN_RE = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


def normalize_scope_domain(value: object) -> str | None:
    """Return one safe ASCII domain for suffix-based URL scope checks."""
    domain = str(value or "").strip().casefold().rstrip(".")
    return domain if _DOMAIN_RE.fullmatch(domain) else None


def normalize_historical_url(value: object, *, source: str = "gau", run_id: str = "") -> dict[str, str] | None:
    """Normalize one URL without probing it or treating it as a finding."""
    raw = str(value or "").strip()
    if not raw or len(raw) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.fragment:
        return None
    host = parsed.hostname.casefold()
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = host if port is None else f"{host}:{port}"
    normalized = urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    return {
        "url": normalized,
        "source": str(source or "gau").strip().lower()[:32],
        "source_run_id": str(run_id or "").strip()[:128],
    }


def normalize_historical_urls(values: object, *, source: str = "gau", run_id: str = "") -> list[dict[str, str]]:
    """Normalize, deduplicate, and bound passive URL results."""
    rows = values if isinstance(values, (list, tuple)) else []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in rows:
        row = normalize_historical_url(value, source=source, run_id=run_id)
        if not row or row["url"] in seen:
            continue
        seen.add(row["url"])
        result.append(row)
        if len(result) >= MAX_HISTORICAL_URLS:
            break
    return result


def normalize_domain_scoped_historical_urls(
    values: object,
    domain: object,
    *, source: str = "gau", run_id: str = "",
) -> list[dict[str, str]]:
    """Normalize and bound URLs whose host is one approved domain or subdomain."""
    scope_domain = normalize_scope_domain(domain)
    if not scope_domain:
        return []
    candidates = values if isinstance(values, (list, tuple)) else []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in candidates:
        row = normalize_historical_url(value, source=source, run_id=run_id)
        if not row:
            continue
        host = (urlsplit(row["url"]).hostname or "").casefold().rstrip(".")
        if (host != scope_domain and not host.endswith("." + scope_domain)) or row["url"] in seen:
            continue
        seen.add(row["url"])
        result.append(row)
        if len(result) >= MAX_HISTORICAL_URLS:
            break
    return result


def historical_url_entity_attributes(row: object) -> dict[str, str]:
    """Return bounded Atlas attributes for one passive URL observation."""
    if not isinstance(row, dict):
        return {}
    provider = str(row.get("source") or "").strip().lower()[:32]
    if not provider:
        return {}
    attributes = {
        "discovery_mode": "passive",
        "provider": provider,
    }
    source_run_id = str(row.get("source_run_id") or "").strip()[:128]
    if source_run_id:
        attributes["source_run_id"] = source_run_id
    return attributes


def filter_historical_urls(
    rows: object,
    *,
    allowed_hosts: object = (),
    scope_roots: object = (),
) -> list[dict[str, str]]:
    """Keep normalized URLs whose host and path match an explicit scope."""
    hosts = {str(host).strip().casefold().rstrip(".") for host in allowed_hosts if str(host).strip()}
    roots = [str(root).strip() for root in scope_roots if str(root).strip()]
    values = rows if isinstance(rows, list) else []
    filtered: list[dict[str, str]] = []
    for row in values:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        host = (parsed.hostname or "").casefold().rstrip(".")
        if hosts and host not in hosts:
            continue
        if roots and not any(
            url == root or url.startswith(root.rstrip("/") + "/")
            for root in roots
        ):
            continue
        filtered.append(dict(row))
    return filtered
