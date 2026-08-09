# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded identity snapshots for the app-managed Nuclei template cache."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from services.nuclei.provenance import MANAGED_TEMPLATE_DIR


MAX_CHECKSUM_BYTES = 8 * 1024 * 1024
MAX_CHECKSUM_ENTRIES = 25_000
MAX_CONFIG_BYTES = 65_536
_VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class NucleiTemplateCacheSnapshot:
    state: str
    release_version: str = ""
    content_digest: str = ""
    manifest_entry_count: int = 0

    def public(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "source_label": "Managed local cache",
            "release_version": self.release_version,
            "content_digest": self.content_digest,
            "manifest_entry_count": self.manifest_entry_count,
        }


def managed_nuclei_template_snapshot(
    template_dir: str | Path = MANAGED_TEMPLATE_DIR,
    *,
    config_path: str | Path | None = None,
) -> NucleiTemplateCacheSnapshot:
    root = Path(template_dir)
    checksum = root / ".checksum"
    root_stat = _regular_stat(root, directory=True)
    checksum_stat = _regular_stat(checksum)
    if root_stat is None or checksum_stat is None:
        return NucleiTemplateCacheSnapshot("missing")
    if checksum_stat.st_size > MAX_CHECKSUM_BYTES:
        return NucleiTemplateCacheSnapshot("oversized")
    selected_config = Path(config_path) if config_path else _default_config_path()
    config_stat = _regular_stat(selected_config)
    config_key = _stat_key(config_stat)
    return _snapshot_for_files(
        str(root.absolute()), str(checksum), _stat_key(checksum_stat),
        str(selected_config), config_key,
    )


def nuclei_template_cache_unavailable_reason(snapshot: NucleiTemplateCacheSnapshot) -> str:
    if snapshot.state == "ready":
        return ""
    state = {
        "missing": "isn't installed",
        "oversized": "has an oversized manifest",
        "invalid": "has an invalid manifest",
        "unreadable": "can't be read safely",
    }.get(snapshot.state, "isn't ready")
    return (
        f"The managed Nuclei template cache {state}. Run nuclei -update-templates "
        "explicitly, then review this action again."
    )


@lru_cache(maxsize=16)
def _snapshot_for_files(
    root_text: str,
    checksum_text: str,
    checksum_key: tuple[int, ...],
    config_text: str,
    config_key: tuple[int, ...],
) -> NucleiTemplateCacheSnapshot:
    del checksum_key, config_key
    payload = _read_bounded(Path(checksum_text), MAX_CHECKSUM_BYTES)
    if payload is None:
        return NucleiTemplateCacheSnapshot("unreadable")
    try:
        entries = _checksum_entries(payload, Path(root_text))
    except (UnicodeDecodeError, ValueError):
        entries = []
    if not entries:
        return NucleiTemplateCacheSnapshot("invalid")
    canonical = "".join(f"{path}\0{digest}\n" for path, digest in sorted(entries))
    digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    version = _release_version(Path(config_text), Path(root_text))
    return NucleiTemplateCacheSnapshot("ready", version, digest, len(entries))


def _checksum_entries(payload: bytes, root: Path) -> list[tuple[str, str]]:
    root_text = os.path.abspath(root)
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_entry in payload.decode("utf-8", errors="strict").split(";"):
        if not raw_entry.strip():
            continue
        if len(entries) >= MAX_CHECKSUM_ENTRIES or "," not in raw_entry:
            return []
        raw_path, checksum = raw_entry.rsplit(",", 1)
        candidate = os.path.abspath(raw_path if os.path.isabs(raw_path) else root / raw_path)
        if os.path.commonpath((root_text, candidate)) != root_text:
            return []
        relative = os.path.relpath(candidate, root_text).replace(os.sep, "/")
        if relative in seen or not re.fullmatch(r"[a-fA-F0-9]{32}", checksum.strip()):
            return []
        seen.add(relative)
        entries.append((relative, checksum.strip().lower()))
    return entries


def _release_version(config_path: Path, root: Path) -> str:
    payload = _read_bounded(config_path, MAX_CONFIG_BYTES)
    if payload is None:
        return ""
    try:
        config = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if not isinstance(config, dict):
        return ""
    configured = os.path.abspath(str(config.get("nuclei-templates-directory") or ""))
    version = str(config.get("nuclei-templates-version") or "").strip()
    return version if configured == os.path.abspath(root) and _VERSION_RE.fullmatch(version) else ""


def _default_config_path() -> Path:
    base = os.environ.get("NUCLEI_CONFIG_DIR")
    if base:
        return Path(base) / ".templates-config.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg or Path.home() / ".config") / "nuclei" / ".templates-config.json"


def _regular_stat(path: Path, *, directory: bool = False):
    try:
        value = path.lstat()
    except OSError:
        return None
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    return value if expected(value.st_mode) and not path.is_symlink() else None


def _stat_key(value) -> tuple[int, ...]:
    return () if value is None else (value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _read_bounded(path: Path, limit: int) -> bytes | None:
    info = _regular_stat(path)
    if info is None or info.st_size > limit:
        return None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            payload = handle.read(limit + 1)
            return payload if len(payload) <= limit else None
    except OSError:
        return None
