# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Wordlist built-in command handler."""

from __future__ import annotations

from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    build_builtin_command_spec,
)
from services.commands.builtins_format import output_line
from services.commands.registry import split_command_argv
from services.commands.wordlists import filter_wordlists, find_wordlist, load_wordlist_catalog


def _wordlist_usage() -> list[dict[str, object]]:
    return [
        output_line("Usage: wordlist [list [category] | search <term> | path <name-or-path> | --all]", "builtin-note"),
        output_line("  wordlist", "builtin-help-row"),
        output_line("  wordlist list dns", "builtin-help-row"),
        output_line("  wordlist search raft", "builtin-help-row"),
        output_line("  wordlist path common.txt", "builtin-help-row"),
    ]


def _wordlist_rows(items: list[dict], *, heading: str) -> list[dict[str, object]]:
    if not items:
        return [output_line("No matching wordlists found.", "builtin-note")]
    widths = {
        "category": max(len("category"), *(len(str(item.get("category") or "")) for item in items)),
        "name": max(len("name"), *(len(str(item.get("name") or "")) for item in items)),
    }
    lines = [
        output_line(heading, "builtin-section"),
        output_line(
            f"  {'category':<{widths['category']}}  {'name':<{widths['name']}}  path",
            "builtin-table-header",
        ),
    ]
    for item in items:
        category = str(item.get("category") or "")
        name = str(item.get("name") or "")
        path = str(item.get("path") or "")
        lines.append(output_line(f"  {category:<{widths['category']}}  {name:<{widths['name']}}  {path}", "builtin-table-row"))
    return lines


def run_builtin_wordlist(command: str) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    args = parts[1:]
    catalog = load_wordlist_catalog(include_all="--all" in args)
    curated_items = catalog.get("items") or []
    all_items = catalog.get("all_items") or []
    root = str(catalog.get("root") or "")
    category_keys = {str(item.get("key") or "") for item in catalog.get("categories") or []}

    if not curated_items and not all_items:
        return [
            output_line("Installed SecLists wordlists were not found.", "builtin-note"),
            output_line(f"Expected path: {root}", "builtin-help-row"),
        ]

    if not args or args == ["list"]:
        return _wordlist_rows(curated_items, heading="Curated wordlists:")
    if args == ["--all"]:
        return _wordlist_rows(all_items, heading="All installed SecLists files:")

    subcommand = args[0].lower()
    if subcommand == "list":
        if len(args) > 2:
            return _wordlist_usage()
        category = args[1].lower() if len(args) == 2 else ""
        if category and category not in category_keys:
            return [output_line(f"Unknown wordlist category: {category}", "builtin-note")] + _wordlist_usage()
        items = filter_wordlists(curated_items, category=category or None)
        heading = f"Curated {category} wordlists:" if category else "Curated wordlists:"
        return _wordlist_rows(items, heading=heading)

    if subcommand == "search":
        if len(args) < 2:
            return _wordlist_usage()
        term = " ".join(args[1:])
        items = filter_wordlists(curated_items, search=term)
        return _wordlist_rows(items, heading=f"Wordlist search: {term}")

    if subcommand == "path":
        if len(args) != 2:
            return _wordlist_usage()
        item = find_wordlist(args[1], curated_items)
        if not item:
            return [output_line(f"Wordlist not found: {args[1]}", "builtin-note")]
        return [output_line(str(item.get("path") or ""), "builtin-plain")]

    return _wordlist_usage()


_BUILTIN_AUTOCOMPLETE = {
    "wordlist": {
        "root": "wordlist",
        "description": "built-in: list and search installed SecLists wordlists",
        "autocomplete": {
            "subcommands": [
                {
                    "value": "list",
                    "description": "List curated wordlists",
                    "takes_value": True,
                    "insert": "list ",
                    "value_hint": {"value": "<category>", "hint_only": True, "description": "Wordlist category"},
                },
                {
                    "value": "search",
                    "description": "Search curated wordlists",
                    "takes_value": True,
                    "insert": "search ",
                    "value_hint": {"value": "<term>", "hint_only": True, "description": "Search term"},
                },
                {
                    "value": "path",
                    "description": "Print one wordlist path",
                    "takes_value": True,
                    "insert": "path ",
                    "value_hint": {"value": "<name>", "hint_only": True, "description": "Wordlist name or relative path"},
                },
            ],
            "flags": [{"value": "--all", "description": "List every installed SecLists file"}],
        },
    }
}


def builtin_command_specs() -> tuple[BuiltinCommandSpec, ...]:
    return (
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["wordlist"],
            handler_key="wordlist",
            handler=lambda command, _context: run_builtin_wordlist(command),
            name="wordlist",
            description="List and search installed SecLists wordlists.",
        ),
    )
