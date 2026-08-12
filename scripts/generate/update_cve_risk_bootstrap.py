#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Download, validate, and pin public EPSS/KEV bootstrap snapshots."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from services.cve_risk.constants import (  # noqa: E402
    EPSS_SOURCE_URL,
    EPSS_TERMS_URL,
    KEV_SOURCE_URL,
    KEV_TERMS_URL,
    SOURCE_ATTRIBUTION,
)
from services.cve_risk.parsers import iso_now, parse_source  # noqa: E402


ASSET_ROOT = APP_ROOT / "resources" / "cve_risk"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "darklab_shell-cve-risk-bootstrap/1"})
    with urlopen(request, timeout=45) as response:  # nosec B310 - fixed HTTPS source URLs
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise RuntimeError("download exceeded the bootstrap size limit")
    return payload


def normalized_asset(source: str, payload: bytes) -> bytes:
    if payload.startswith(b"\x1f\x8b"):
        return payload
    return gzip.compress(payload, compresslevel=9, mtime=0)


def main() -> int:
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    retrieved_at = iso_now()
    source_specs = (
        ("epss", EPSS_SOURCE_URL, EPSS_TERMS_URL, "epss.csv.gz"),
        ("kev", KEV_SOURCE_URL, KEV_TERMS_URL, "kev.json.gz"),
    )
    manifest_sources = []
    for source, source_url, terms_url, filename in source_specs:
        asset = normalized_asset(source, download(source_url))
        parsed = parse_source(source, asset)
        path = ASSET_ROOT / filename
        path.write_bytes(asset)
        manifest_sources.append({
            "source": source,
            "filename": filename,
            "source_url": source_url,
            "terms_url": terms_url,
            "attribution": SOURCE_ATTRIBUTION[source],
            "source_version": parsed.version,
            "model_version": parsed.model_version,
            "published_at": parsed.published_at,
            "retrieved_at": retrieved_at,
            "record_count": len(parsed.records),
            "compressed_bytes": len(asset),
            "sha256": hashlib.sha256(asset).hexdigest(),
        })
    manifest = {
        "schema_version": 1,
        "generated_at": retrieved_at,
        "sources": manifest_sources,
    }
    (ASSET_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
