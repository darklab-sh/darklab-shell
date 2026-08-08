# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Digest-pinned app-owned Nuclei templates for takeover review."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import Any

import yaml

from services.assessments.nuclei_takeover_observations import (
    ReviewedNucleiTakeoverTemplate,
)


NUCLEI_TAKEOVER_TEMPLATE_ID = "darklab-github-pages-dangling-domain"
NUCLEI_TAKEOVER_TEMPLATE_VERSION = "1.0.0"
NUCLEI_TAKEOVER_TEMPLATE_MAX_BYTES = 16 * 1024
_APP_DIR = Path(__file__).resolve().parents[2]
_TEMPLATE_ROOT = _APP_DIR / "conf" / "nuclei" / "takeovers"
_TEMPLATE_PATH = _TEMPLATE_ROOT / "github-pages-dangling-domain.yaml"
_TEMPLATE_DIGEST = "sha256:d3aaec86e2a73f02305476913b3e1972eba5117320e410d3b2eec99439d57fa9"
_EXPECTED_FINGERPRINT = "There isn't a GitHub Pages site here."


class NucleiTakeoverTemplateError(RuntimeError):
    """The app-owned takeover template failed its immutable review contract."""


@dataclass(frozen=True)
class ReviewedNucleiTakeoverLaunch:
    template: ReviewedNucleiTakeoverTemplate
    template_path: Path

    @property
    def trusted_execution_args(self) -> tuple[str, ...]:
        return ("-t", str(self.template_path), "-jsonl", "-dr")


def reviewed_nuclei_takeover_launch() -> ReviewedNucleiTakeoverLaunch:
    """Return the fixed template only after content and behavior validation."""
    raw = _read_regular_template(_TEMPLATE_PATH)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if digest != _TEMPLATE_DIGEST:
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template digest mismatch")
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template is invalid") from exc
    _validate_safe_template(document)
    return ReviewedNucleiTakeoverLaunch(
        template=ReviewedNucleiTakeoverTemplate(
            template_id=NUCLEI_TAKEOVER_TEMPLATE_ID,
            template_version=NUCLEI_TAKEOVER_TEMPLATE_VERSION,
            template_digest=digest,
            policy_level="safe",
        ),
        template_path=_TEMPLATE_PATH,
    )


def _read_regular_template(path: Path) -> bytes:
    try:
        owned_parents = (_APP_DIR / "conf", _APP_DIR / "conf" / "nuclei", _TEMPLATE_ROOT)
        if path.parent != _TEMPLATE_ROOT or any(parent.is_symlink() for parent in owned_parents):
            raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template path is invalid")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template is unavailable") from exc
    try:
        file_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_size <= 0
            or file_stat.st_size > NUCLEI_TAKEOVER_TEMPLATE_MAX_BYTES
        ):
            raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template file is invalid")
        chunks: list[bytes] = []
        remaining = NUCLEI_TAKEOVER_TEMPLATE_MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != file_stat.st_size:
            raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template changed while reading")
        return raw
    finally:
        os.close(descriptor)


def _validate_safe_template(document: Any) -> None:
    if not isinstance(document, dict) or set(document) != {"id", "info", "http"}:
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template shape is invalid")
    info = document.get("info")
    requests = document.get("http")
    if (
        document.get("id") != NUCLEI_TAKEOVER_TEMPLATE_ID
        or not isinstance(info, dict)
        or info.get("severity") != "info"
        or info.get("metadata") != {"max-request": 1}
        or not isinstance(requests, list)
        or len(requests) != 1
    ):
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover template metadata is invalid")
    request = requests[0]
    allowed_request_keys = {"method", "path", "redirects", "matchers-condition", "matchers"}
    if (
        not isinstance(request, dict)
        or set(request) != allowed_request_keys
        or request.get("method") != "GET"
        or request.get("path") != ["{{BaseURL}}"]
        or request.get("redirects") is not False
        or request.get("matchers-condition") != "and"
    ):
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover request is not safe")
    if request.get("matchers") != [
        {"type": "status", "status": [404]},
        {"type": "word", "part": "body", "words": [_EXPECTED_FINGERPRINT]},
    ]:
        raise NucleiTakeoverTemplateError("reviewed Nuclei takeover matchers are invalid")


__all__ = [
    "NUCLEI_TAKEOVER_TEMPLATE_ID",
    "NUCLEI_TAKEOVER_TEMPLATE_MAX_BYTES",
    "NUCLEI_TAKEOVER_TEMPLATE_VERSION",
    "NucleiTakeoverTemplateError",
    "ReviewedNucleiTakeoverLaunch",
    "reviewed_nuclei_takeover_launch",
]
