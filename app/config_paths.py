# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve immutable shipped configuration and operator-owned local overlays."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable


DEFAULT_SHIPPED_CONF_DIR = Path(__file__).resolve().parent / "conf"
FIXED_OVERLAY_ASSETS = (
    "config.yaml",
    "assessment_profiles.yaml",
    "commands.yaml",
    "faq.yaml",
    "welcome.yaml",
    "workflows.yaml",
    "ascii.txt",
    "ascii_mobile.txt",
    "app_hints.txt",
    "app_hints_mobile.txt",
)


@dataclass(frozen=True)
class ConfigRoots:
    shipped: Path
    local: Path


@dataclass(frozen=True)
class ConfigAssetPaths:
    shipped: Path
    local: Path
    relative_path: Path
    local_relative_path: Path


def _safe_relative_path(value: str | os.PathLike[str]) -> Path:
    raw = os.fspath(value)
    if not raw or "\x00" in raw:
        raise ValueError("config asset path must not be empty")
    path = Path(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"config asset path must be a safe relative path: {raw!r}")
    return path


def config_roots(
    shipped_conf_dir: str | os.PathLike[str] | None = None,
    local_conf_dir: str | os.PathLike[str] | None = None,
) -> ConfigRoots:
    shipped_value = shipped_conf_dir or os.environ.get("APP_CONF_DIR")
    shipped = Path(shipped_value) if shipped_value else DEFAULT_SHIPPED_CONF_DIR
    local_value = local_conf_dir or os.environ.get("APP_LOCAL_CONF_DIR")
    local = Path(local_value) if local_value else shipped
    return ConfigRoots(shipped=shipped, local=local)


def local_overlay_relative_path(value: str | os.PathLike[str]) -> Path:
    path = _safe_relative_path(value)
    if not path.suffix:
        raise ValueError(f"config asset path must have a file extension: {path}")
    return path.with_name(f"{path.stem}.local{path.suffix}")


def config_asset_paths(
    relative_path: str | os.PathLike[str],
    *,
    shipped_conf_dir: str | os.PathLike[str] | None = None,
    local_conf_dir: str | os.PathLike[str] | None = None,
) -> ConfigAssetPaths:
    relative = _safe_relative_path(relative_path)
    local_relative = local_overlay_relative_path(relative)
    roots = config_roots(shipped_conf_dir, local_conf_dir)
    return ConfigAssetPaths(
        shipped=roots.shipped / relative,
        local=roots.local / local_relative,
        relative_path=relative,
        local_relative_path=local_relative,
    )


def local_overlay_path_for(
    shipped_path: str | os.PathLike[str],
    *,
    shipped_conf_dir: str | os.PathLike[str] | None = None,
    local_conf_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Return an external overlay path, with sibling behavior for test/custom paths."""
    path = Path(shipped_path)
    roots = config_roots(shipped_conf_dir, local_conf_dir)
    try:
        relative = path.absolute().relative_to(roots.shipped.absolute())
    except ValueError:
        if not path.suffix:
            raise ValueError(f"config asset path must have a file extension: {path}")
        return path.with_name(f"{path.stem}.local{path.suffix}")
    return roots.local / local_overlay_relative_path(relative)


def configured_catalog_path(
    value: str | os.PathLike[str],
    *,
    shipped_conf_dir: str | os.PathLike[str] | None = None,
    local_conf_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Resolve relative local catalogs from the operator root and others from shipped config."""
    path = Path(value)
    if path.is_absolute():
        return path
    relative = _safe_relative_path(path)
    roots = config_roots(shipped_conf_dir, local_conf_dir)
    root = roots.local if ".local." in relative.name else roots.shipped
    return root / relative


def supported_overlay_assets(
    *,
    shipped_conf_dir: str | os.PathLike[str] | None = None,
) -> tuple[Path, ...]:
    """Return fixed assets plus shipped theme variants that accept overlays."""
    roots = config_roots(shipped_conf_dir, None)
    assets = [Path(value) for value in FIXED_OVERLAY_ASSETS]
    theme_dir = roots.shipped / "themes"
    if theme_dir.is_dir():
        assets.extend(
            Path("themes") / path.name
            for path in sorted(theme_dir.glob("*.yaml"))
            if not path.name.endswith(".local.yaml")
        )
    return tuple(assets)


def present_local_overlays(
    *,
    shipped_conf_dir: str | os.PathLike[str] | None = None,
    local_conf_dir: str | os.PathLike[str] | None = None,
    assets: Iterable[Path] | None = None,
) -> tuple[str, ...]:
    """Return safe relative names for present supported overlays, never values."""
    candidates = assets if assets is not None else supported_overlay_assets(
        shipped_conf_dir=shipped_conf_dir,
    )
    return tuple(
        paths.local_relative_path.as_posix()
        for relative_path in candidates
        if (
            paths := config_asset_paths(
                relative_path,
                shipped_conf_dir=shipped_conf_dir,
                local_conf_dir=local_conf_dir,
            )
        ).local.is_file()
    )
