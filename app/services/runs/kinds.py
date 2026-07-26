# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Run kind helpers.

The history table stores whether a run came from the built-in command layer or
from an external/runtime command so later project and findings logic does not
have to re-infer that from command text.
"""

from functools import lru_cache

from services.commands.registry import command_root

RUN_KIND_BUILTIN = "builtin"
RUN_KIND_EXTERNAL = "external"
RUN_KIND_VALUES = frozenset({RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL})


@lru_cache(maxsize=1)
def builtin_command_roots_for_storage() -> frozenset[str]:
    from services.commands.builtins import get_registered_builtin_command_roots

    return frozenset(get_registered_builtin_command_roots())


def infer_run_kind(command: str) -> str:
    root = command_root(command)
    if root and root.lower() in builtin_command_roots_for_storage():
        return RUN_KIND_BUILTIN
    return RUN_KIND_EXTERNAL


def normalize_run_kind(value, *, command: str = "") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in RUN_KIND_VALUES:
        return normalized
    return infer_run_kind(command)


def run_kind_for_cmd_type(cmd_type: str) -> str:
    return RUN_KIND_BUILTIN if str(cmd_type or "").lower() in {"builtin", "client-builtin"} else RUN_KIND_EXTERNAL


def is_project_linkable_run_kind(value) -> bool:
    return normalize_run_kind(value) == RUN_KIND_EXTERNAL
