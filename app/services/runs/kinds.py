"""
Run kind helpers.

The history table stores whether a run came from the built-in command layer or
from an external/runtime command so later project and findings logic does not
have to re-infer that from command text.
"""

from services.commands.builtins_catalog import (
    _BUILTIN_COMMANDS,
    _SPECIAL_BUILTIN_COMMANDS,
    _WORKSPACE_ALIAS_ROOTS,
)
from services.commands.registry import command_root

RUN_KIND_BUILTIN = "builtin"
RUN_KIND_EXTERNAL = "external"
RUN_KIND_VALUES = frozenset({RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL})


def builtin_command_roots_for_storage() -> set[str]:
    roots = {str(root).lower() for root in _BUILTIN_COMMANDS if root}
    roots.update(str(root).lower() for root in _WORKSPACE_ALIAS_ROOTS if root)
    for key in _SPECIAL_BUILTIN_COMMANDS:
        root = command_root(str(key))
        if root:
            roots.add(root.lower())
    return roots


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
