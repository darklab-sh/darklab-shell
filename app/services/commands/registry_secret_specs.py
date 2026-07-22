# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scoped command-secret registry normalization and catalog helpers."""

from __future__ import annotations

import re
from typing import Callable

from services.commands.registry_validation import command_root, split_command_argv


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def normalize_required_secrets(
    items: object,
    *,
    secret_env_re: re.Pattern[str],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    by_key: dict[tuple[str, str, tuple[str, ...]], dict[str, object]] = {}
    raw_items = items if isinstance(items, list) else []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        env = str(item.get("env") or "").strip().upper()
        inject_env = str(item.get("inject_env") or item.get("as") or env).strip().upper()
        if not secret_env_re.fullmatch(env) or not secret_env_re.fullmatch(inject_env):
            continue
        fallback_envs = _dedupe([
            value
            for fallback in item.get("fallback_envs", []) or []
            if (value := str(fallback or "").strip().upper()) != env
            and secret_env_re.fullmatch(value)
        ])
        subcommands = _dedupe([
            str(subcommand or "").strip().lower()
            for subcommand in item.get("subcommands", []) or []
            if str(subcommand or "").strip()
        ])
        optional = bool(item.get("optional", False))
        key = (env, inject_env, tuple(subcommands))
        if key in by_key:
            existing = by_key[key]
            existing["optional"] = bool(existing.get("optional")) and optional
            raw_existing_fallbacks = existing.get("fallback_envs")
            existing_fallbacks = (
                raw_existing_fallbacks if isinstance(raw_existing_fallbacks, list) else []
            )
            existing["fallback_envs"] = _dedupe([
                *existing_fallbacks,
                *fallback_envs,
            ])
            if not existing["fallback_envs"]:
                existing.pop("fallback_envs", None)
            continue
        normalized: dict[str, object] = {"env": env, "optional": optional}
        if inject_env != env:
            normalized["inject_env"] = inject_env
        if fallback_envs:
            normalized["fallback_envs"] = fallback_envs
        if subcommands:
            normalized["subcommands"] = subcommands
        by_key[key] = normalized
        result.append(normalized)
    return result


def required_secrets_for_command(
    command: str,
    registry: dict,
    *,
    is_help_invocation: Callable[[str, str | None, dict | None], bool],
) -> list[dict[str, object]]:
    root = command_root(command)
    if not root or is_help_invocation(command, root, registry):
        return []
    for entry in registry.get("commands", []) or []:
        if str(entry.get("root") or "").strip().lower() != root:
            continue
        return scoped_required_secrets(command, entry.get("requires_secrets"))
    return []


def scoped_required_secrets(command: str, items: object) -> list[dict[str, object]]:
    """Return declarations that apply to the command's first subcommand."""
    tokens = split_command_argv(command)
    subcommand = tokens[1].strip().lower() if len(tokens) > 1 else ""
    raw_items = items if isinstance(items, list) else []
    return [
        dict(item)
        for item in raw_items
        if isinstance(item, dict)
        and (
            not item.get("subcommands")
            or subcommand in {
                str(value or "").strip().lower()
                for value in item.get("subcommands", []) or []
            }
        )
    ]


def catalog_required_secrets(items: object) -> list[dict[str, object]]:
    secrets = []
    if not isinstance(items, list):
        return secrets
    for item in items:
        if not isinstance(item, dict):
            continue
        env = str(item.get("env") or "").strip().upper()
        if not env:
            continue
        entry: dict[str, object] = {"env": env, "optional": bool(item.get("optional", False))}
        inject_env = str(item.get("inject_env") or "").strip().upper()
        if inject_env and inject_env != env:
            entry["inject_env"] = inject_env
        fallback_envs = _dedupe([
            str(fallback or "").strip().upper()
            for fallback in item.get("fallback_envs", []) or []
            if str(fallback or "").strip()
        ])
        subcommands = _dedupe([
            str(subcommand or "").strip().lower()
            for subcommand in item.get("subcommands", []) or []
            if str(subcommand or "").strip()
        ])
        if fallback_envs:
            entry["fallback_envs"] = fallback_envs
        if subcommands:
            entry["subcommands"] = subcommands
        secrets.append(entry)
    return secrets


def command_secret_consumers(registry: dict) -> list[dict[str, object]]:
    consumers: list[dict[str, object]] = []
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if not root:
            continue
        for secret in catalog_required_secrets(entry.get("requires_secrets")):
            raw_subcommands = secret.get("subcommands")
            subcommands = raw_subcommands if isinstance(raw_subcommands, list) else []
            names = [f"{root} {subcommand}" for subcommand in subcommands] or [root]
            for name in names:
                consumers.append({
                    **secret,
                    "source": "command_registry",
                    "consumer": name,
                })
    return consumers
